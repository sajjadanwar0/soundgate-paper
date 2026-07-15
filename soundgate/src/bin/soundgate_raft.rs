use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use axum::{
    Json, Router,
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
};
use openraft::{BasicNode, raft::{AppendEntriesRequest, InstallSnapshotRequest, VoteRequest}};
use serde::Deserialize;
use serde_json::json;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use soundgate::Admission;

#[path = "../raft_gate/mod.rs"]
mod raft_gate;
use raft_gate::{
    GateOp, SoundGateAdaptor, SoundGateNetworkFactory, SoundGateRaft, SoundGateStore,
    SoundGateTypeConfig, build_raft_config, open_db,
};

struct AppState {
    raft: SoundGateRaft,
    node_id: u64,
    this_url: String,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
enum Request {
    Submit {
        run_id: String,
        effect_key: String,
        #[serde(default)]
        needs_approval: bool,
    },
    Decide {
        run_id: String,
        effect_key: String,
        approved: bool,
    },
    Cancel {
        run_id: String,
    },
    Ping,
}

fn verdict_line(admission: Option<Admission>) -> String {
    match admission {
        Some(a) => serde_json::to_string(&a).unwrap(),
        None => json!({"verdict":"ack"}).to_string(),
    }
}

async fn serve_effect(state: Arc<AppState>, stream: TcpStream) {
    let (r, mut w) = stream.into_split();
    let mut lines = BufReader::new(r).lines();

    while let Ok(Some(line)) = lines.next_line().await {
        if line.trim().is_empty() {
            continue;
        }

        let out = match serde_json::from_str::<Request>(&line) {
            Ok(Request::Ping) => json!({"verdict":"pong"}).to_string(),
            Ok(req) => {
                let op = match req {
                    Request::Submit {
                        run_id,
                        effect_key,
                        needs_approval,
                    } => GateOp::Submit {
                        run_id,
                        effect_key,
                        needs_approval,
                    },
                    Request::Decide {
                        run_id,
                        effect_key,
                        approved,
                    } => GateOp::Decide {
                        run_id,
                        effect_key,
                        approved,
                    },
                    Request::Cancel { run_id } => GateOp::Cancel { run_id },
                    Request::Ping => unreachable!(),
                };

                match state.raft.client_write(op).await {
                    Ok(resp) => verdict_line(resp.data.admission),
                    Err(e) => json!({"verdict":"error","message":format!("{e}")}).to_string(),
                }
            }
            Err(e) => json!({"verdict":"error","message":format!("bad request: {e}")}).to_string(),
        };

        let mut buf = out.into_bytes();
        buf.push(b'\n');

        if w.write_all(&buf).await.is_err() {
            break;
        }
    }
}

async fn rpc_append(
    State(s): State<Arc<AppState>>,
    Json(req): Json<AppendEntriesRequest<SoundGateTypeConfig>>,
) -> impl IntoResponse {
    match s.raft.append_entries(req).await {
        Ok(r) => (StatusCode::OK, Json(serde_json::to_value(r).unwrap())),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("{e}")})),
        ),
    }
}

async fn rpc_vote(
    State(s): State<Arc<AppState>>,
    Json(req): Json<VoteRequest<u64>>,
) -> impl IntoResponse {
    match s.raft.vote(req).await {
        Ok(r) => (StatusCode::OK, Json(serde_json::to_value(r).unwrap())),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("{e}")})),
        ),
    }
}

async fn rpc_snapshot(
    State(s): State<Arc<AppState>>,
    Json(req): Json<InstallSnapshotRequest<SoundGateTypeConfig>>,
) -> impl IntoResponse {
    match s.raft.install_snapshot(req).await {
        Ok(r) => (StatusCode::OK, Json(serde_json::to_value(r).unwrap())),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("{e}")})),
        ),
    }
}

async fn admin_init(State(s): State<Arc<AppState>>) -> impl IntoResponse {
    let mut members = BTreeMap::new();
    members.insert(s.node_id, BasicNode { addr: s.this_url.clone() });
    match s.raft.initialize(members).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status":"initialized","node_id":s.node_id}))),
        Err(e) => (StatusCode::CONFLICT, Json(json!({"error": format!("{e}")}))),
    }
}

#[derive(Deserialize)]
struct AddLearnerReq {
    node_id: u64,
    addr: String,
}

async fn admin_add_learner(
    State(s): State<Arc<AppState>>,
    Json(req): Json<AddLearnerReq>,
) -> impl IntoResponse {
    match s
        .raft
        .add_learner(req.node_id, BasicNode { addr: req.addr }, true)
        .await
    {
        Ok(_) => (StatusCode::OK, Json(json!({"status":"learner_added","node_id":req.node_id}))),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("{e}")}))),
    }
}

#[derive(Deserialize)]
struct MembersReq {
    members: Vec<u64>,
}

async fn admin_change_membership(
    State(s): State<Arc<AppState>>,
    Json(req): Json<MembersReq>,
) -> impl IntoResponse {
    let set: BTreeSet<u64> = req.members.into_iter().collect();
    match s.raft.change_membership(set, false).await {
        Ok(_) => (StatusCode::OK, Json(json!({"status":"membership_changed"}))),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({"error": format!("{e}")}))),
    }
}

async fn metrics(State(s): State<Arc<AppState>>) -> impl IntoResponse {
    let m = s.raft.metrics().borrow().clone();
    Json(serde_json::to_value(m).unwrap())
}

async fn leader(State(s): State<Arc<AppState>>) -> impl IntoResponse {
    let m = s.raft.metrics().borrow().clone();
    Json(json!({"leader": m.current_leader, "node_id": s.node_id}))
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .init();

    let node_id: u64 = std::env::var("SOUNDGATE_RAFT_NODE_ID")
        .expect("SOUNDGATE_RAFT_NODE_ID")
        .parse()
        .expect("node id u64");
    let http_addr = std::env::var("SOUNDGATE_RAFT_HTTP").expect("SOUNDGATE_RAFT_HTTP");
    let effect_addr = std::env::var("SOUNDGATE_RAFT_EFFECT").expect("SOUNDGATE_RAFT_EFFECT");
    let this_url = std::env::var("SOUNDGATE_RAFT_URL")
        .unwrap_or_else(|_| format!("http://{http_addr}"));
    let data_dir = std::env::var("SOUNDGATE_RAFT_DATA")
        .unwrap_or_else(|_| format!("./raft-data-{node_id}"));

    let (logs, meta, fences) = open_db(&data_dir);
    let store = SoundGateStore::new(logs, meta, fences);
    let (log_store, state_machine) = SoundGateAdaptor::new(store);

    let raft = SoundGateRaft::new(
        node_id,
        build_raft_config(),
        SoundGateNetworkFactory::new(),
        log_store,
        state_machine,
    )
        .await
        .expect("raft node");

    let state = Arc::new(AppState {
        raft,
        node_id,
        this_url: this_url.clone(),
    });

    let effect_state = state.clone();
    let effect_addr_c = effect_addr.clone();

    tokio::spawn(async move {
        let listener = TcpListener::bind(&effect_addr_c)
            .await
            .expect("bind effect port");
        tracing::info!("soundgate-raft node {node_id}: effect protocol on {effect_addr_c}");

        loop {
            match listener.accept().await {
                Ok((stream, _)) => {
                    let s = effect_state.clone();
                    tokio::spawn(serve_effect(s, stream));
                }
                Err(e) => tracing::error!("effect accept: {e}"),
            }
        }
    });

    let app = Router::new()
        .route("/raft/append-entries", post(rpc_append))
        .route("/raft/vote", post(rpc_vote))
        .route("/raft/install-snapshot", post(rpc_snapshot))
        .route("/admin/init", post(admin_init))
        .route("/admin/add-learner", post(admin_add_learner))
        .route("/admin/change-membership", post(admin_change_membership))
        .route("/metrics", get(metrics))
        .route("/leader", get(leader))
        .with_state(state);

    let listener = TcpListener::bind(&http_addr).await.expect("bind http");
    tracing::info!("soundgate-raft node {node_id}: raft/admin HTTP on {http_addr} (url {this_url})");
    axum::serve(listener, app).await.expect("axum serve");
}