use std::io::Cursor;
use std::sync::Arc;
use openraft::{BasicNode, Config, Entry, SnapshotPolicy, storage::Adaptor};
use serde::{Deserialize, Serialize};
use soundgate::Admission;

pub mod network;
pub mod store;

pub use network::SoundGateNetworkFactory;
pub use store::{SoundGateStore, open_db};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum GateOp {
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
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GateWriteResponse {
    pub admission: Option<Admission>,
}

impl GateWriteResponse {
    pub fn none() -> Self {
        Self { admission: None }
    }
    pub fn some(a: Admission) -> Self {
        Self { admission: Some(a) }
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct SoundGateTypeConfig;

impl openraft::RaftTypeConfig for SoundGateTypeConfig {
    type D = GateOp;
    type R = GateWriteResponse;
    type NodeId = u64;
    type Node = BasicNode;
    type Entry = Entry<Self>;
    type SnapshotData = Cursor<Vec<u8>>;
}

pub type SoundGateAdaptor = Adaptor<SoundGateTypeConfig, SoundGateStore>;

pub type SoundGateRaft = openraft::Raft<
    SoundGateTypeConfig,
    SoundGateNetworkFactory,
    SoundGateAdaptor,
    SoundGateAdaptor,
>;

pub fn build_raft_config() -> Arc<Config> {
    Arc::new(Config {
        cluster_name: "soundgate-cluster".into(),
        heartbeat_interval: 250,
        election_timeout_min: 500,
        election_timeout_max: 1000,
        max_in_snapshot_log_to_keep: 200,
        snapshot_policy: SnapshotPolicy::LogsSinceLast(500),
        max_payload_entries: 64,
        ..Default::default()
    })
}