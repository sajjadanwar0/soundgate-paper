//! soundgate server: line-delimited JSON over TCP.
//!
//! One request per line, one response per line. Any language can drive it.
//! Requests:
//!   {"op":"submit","run_id":"r1","effect_key":"send_email","needs_approval":true}
//!   {"op":"decide","run_id":"r1","effect_key":"send_email","approved":false}
//!   {"op":"cancel","run_id":"r1"}
//!   {"op":"ping"}
//! Responses: the Admission enum as JSON, e.g. {"verdict":"held_for_approval"}
//! or {"verdict":"release"}; cancel -> {"verdict":"ack"}; ping -> {"verdict":"pong"}.
//!
//! PROTOCOL NOTE (G1 fix): "decide" REQUIRES run_id. Effect identity is the
//! pair (run_id, effect_key) -- a key alone is ambiguous when concurrent runs
//! reuse keys, and key-only decisions were the root of the cross-run
//! collision counterexample. Requests without run_id get a parse error, not
//! a guess.
//!
//! Single-threaded with a mutex-guarded Gate: the gate must serialize
//! decisions anyway (it is the arbitration point), so this keeps semantics
//! obvious. Bind address defaults to 127.0.0.1:8799 (override: arg 1).
//!
//! DURABILITY (failure-model obligation 1): pass a WAL path as arg 2 to make
//! the fences durable. State-changing verdicts (release, reject, cancel) are
//! appended as JSON lines and fsynced BEFORE the reply is written, so no
//! acknowledged release can be forgotten by a crash. On startup the WAL is
//! replayed into a fresh gate BEFORE the listener opens (fail-closed
//! recovery: nothing is admitted until state is restored). Held-but-undecided
//! effects are deliberately not durable -- losing a hold is the conservative
//! outcome (see lib.rs::Event). Torn tail lines are skipped; replay is
//! idempotent. Without arg 2 the gate runs in-memory as before.

use serde::{Deserialize, Serialize};
use soundgate::{Admission, Effect, Event, Gate};
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::mpsc::{sync_channel, Receiver, SyncSender};
use std::sync::{Arc, Mutex};

mod hmac;

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
        /// HMAC-SHA256 over (run_id, effect_key, approved) as lowercase hex.
        /// Required iff the gate was started with a decision secret; ignored
        /// (may be absent) otherwise. Verified before any state change.
        #[serde(default)]
        mac: Option<String>,
    },
    Cancel {
        run_id: String,
    },
    Ping,
}

#[derive(Debug, Serialize)]
#[serde(tag = "verdict", rename_all = "snake_case")]
enum Reply {
    Release,
    HeldForApproval,
    RefusedCancelled,
    RefusedDuplicate,
    RefusedRejected,
    /// Acknowledgement for state-changing ops with no admission verdict
    /// (currently: cancel).
    Ack,
    Pong,
    Error { message: String },
}

impl From<Admission> for Reply {
    fn from(a: Admission) -> Self {
        match a {
            Admission::Release => Reply::Release,
            Admission::HeldForApproval => Reply::HeldForApproval,
            Admission::RefusedCancelled => Reply::RefusedCancelled,
            Admission::RefusedDuplicate => Reply::RefusedDuplicate,
            Admission::RefusedRejected => Reply::RefusedRejected,
        }
    }
}

/// Derive the durable event implied by an (operation, verdict) pair. Exact
/// by construction: only Release and RefusedRejected verdicts mutate durable
/// state on submit/decide, and cancel always records its fence.
fn event_for(req: &Request, reply: &Reply) -> Option<Event> {
    match (req, reply) {
        (Request::Submit { run_id, effect_key, .. }, Reply::Release)
        | (Request::Decide { run_id, effect_key, .. }, Reply::Release) => Some(Event::Released {
            run_id: run_id.clone(),
            effect_key: effect_key.clone(),
        }),
        (Request::Decide { run_id, effect_key, .. }, Reply::RefusedRejected) => {
            Some(Event::Rejected { run_id: run_id.clone(), effect_key: effect_key.clone() })
        }
        (Request::Cancel { run_id }, Reply::Ack) => {
            Some(Event::Cancelled { run_id: run_id.clone() })
        }
        _ => None,
    }
}

/// GROUP COMMIT: a single WAL-writer thread batches concurrent state-changing
/// events behind one fsync. Handlers send (serialized line, ack) and block on
/// the ack, so the fsync-before-acknowledge discipline is preserved PER EVENT:
/// a reply is written only after the fsync that covers that event's record.
/// Under one client this degenerates to one fsync per event (identical to the
/// unbatched server); under N clients up to WAL_BATCH events share a flush.
type WalMsg = (String, SyncSender<Result<(), String>>);
const WAL_BATCH: usize = 512;

fn wal_writer(mut f: File, rx: Receiver<WalMsg>) {
    // Batch-size accounting (observation only; the write/fsync/ack discipline
    // below is untouched). Buckets: 1, 2-8, 9-64, 65-256, 257-512. Printed to
    // stderr when the channel closes so benchmarks can report the achieved
    // batching distribution alongside throughput.
    let mut hist = [0u64; 5];
    let (mut batches, mut events) = (0u64, 0u64);
    let stats_every: u64 = std::env::var("SOUNDGATE_WAL_STATS_EVERY")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);
    loop {
        // Block for the first event of a batch; exit when all senders drop.
        let first = match rx.recv() {
            Ok(m) => m,
            Err(_) => {
                if batches > 0 {
                    eprintln!(
                        "soundgate: wal group-commit batches={} events={} \
                         mean={:.1} hist[1|2-8|9-64|65-256|257-512]={:?}",
                        batches, events, events as f64 / batches as f64, hist
                    );
                }
                return;
            }
        };
        let mut batch: Vec<WalMsg> = vec![first];
        while batch.len() < WAL_BATCH {
            match rx.try_recv() {
                Ok(m) => batch.push(m),
                Err(_) => break,
            }
        }
        batches += 1;
        events += batch.len() as u64;
        hist[match batch.len() {
            1 => 0,
            2..=8 => 1,
            9..=64 => 2,
            65..=256 => 3,
            _ => 4,
        }] += 1;
        if stats_every > 0 && batches % stats_every == 0 {
            eprintln!(
                "soundgate: wal group-commit batches={} events={} \
                 mean={:.1} hist[1|2-8|9-64|65-256|257-512]={:?}",
                batches, events, events as f64 / batches as f64, hist
            );
        }
        let mut buf = String::new();
        for (line, _) in &batch {
            buf.push_str(line);
            buf.push('\n');
        }
        let res = f
            .write_all(buf.as_bytes())
            .and_then(|_| f.sync_data())
            .map_err(|e| e.to_string());
        for (_, ack) in batch {
            let _ = ack.send(res.clone());
        }
    }
}

fn handle(stream: TcpStream, gate: Arc<Mutex<Gate>>, wal: Option<SyncSender<WalMsg>>, secret: Option<Arc<Vec<u8>>>) {
    let peer = stream.peer_addr().map(|a| a.to_string()).unwrap_or_default();
    let reader = BufReader::new(stream.try_clone().expect("clone stream"));
    let mut writer = stream;
    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        if line.trim().is_empty() {
            continue;
        }
        let (reply, req) = match serde_json::from_str::<Request>(&line) {
            Ok(req) => {
                let mut g = gate.lock().unwrap();
                let reply = match &req {
                    Request::Submit { run_id, effect_key, needs_approval } => {
                        Reply::from(g.submit(Effect {
                            run_id: run_id.clone(),
                            effect_key: effect_key.clone(),
                            needs_approval: *needs_approval,
                        }))
                    }
                    Request::Decide { run_id, effect_key, approved, mac } => {
                        // Decision authenticity: if a secret is configured, a
                        // decision must carry a valid HMAC over its own fields.
                        // Verified BEFORE touching gate state, so a forged or
                        // absent token cannot approve or reject a held effect.
                        if let Some(sec) = secret.as_deref() {
                            let expected = hmac::decision_tag(sec, run_id, effect_key, *approved);
                            let ok = mac.as_deref().map(|m| hmac::verify(&expected, m)).unwrap_or(false);
                            if !ok {
                                Reply::Error { message: "unauthenticated decision: bad or missing mac".into() }
                            } else {
                                Reply::from(g.decide(run_id, effect_key, *approved))
                            }
                        } else {
                            Reply::from(g.decide(run_id, effect_key, *approved))
                        }
                    }
                    Request::Cancel { run_id } => {
                        g.cancel(run_id);
                        Reply::Ack
                    }
                    Request::Ping => Reply::Pong,
                };
                (reply, Some(req))
            }
            Err(e) => (Reply::Error { message: format!("bad request: {}", e) }, None),
        };
        // WAL discipline (group commit): serialize the state change, hand it
        // to the single writer thread, and block until the fsync covering it
        // completes -- the reply is still written only AFTER that fsync. If
        // the write/fsync fails, fail closed: report an error instead of the
        // verdict, so the client never acts on an unlogged release.
        if let (Some(req), Some(tx)) = (req.as_ref(), wal.as_ref()) {
            if let Some(ev) = event_for(req, &reply) {
                let persisted = serde_json::to_string(&ev)
                    .map_err(|e| e.to_string())
                    .and_then(|line| {
                        let (ack_tx, ack_rx) = sync_channel::<Result<(), String>>(1);
                        tx.send((line, ack_tx)).map_err(|e| e.to_string())?;
                        ack_rx.recv().map_err(|e| e.to_string())?
                    });
                if let Err(e) = persisted {
                    let mut out =
                        serde_json::to_string(&Reply::Error { message: format!("wal: {}", e) })
                            .unwrap();
                    out.push('\n');
                    let _ = writer.write_all(out.as_bytes());
                    continue;
                }
            }
        }
        let mut out = serde_json::to_string(&reply).unwrap();
        out.push('\n');
        if writer.write_all(out.as_bytes()).is_err() {
            break;
        }
    }
    let _ = peer;
}

fn main() {
    let addr = std::env::args().nth(1).unwrap_or_else(|| "127.0.0.1:8799".into());
    let wal_path = std::env::args().nth(2);

    // Fail-closed recovery: replay the WAL into the gate BEFORE the listener
    // exists; no admission can be served against unrestored state.
    let mut gate = Gate::new();
    let wal_file = match &wal_path {
        Some(path) => {
            let mut recovered = 0usize;
            match File::open(path) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => {
                    // An EXISTING but unreadable WAL means fences may exist
                    // that we cannot restore; starting empty would be
                    // fail-open. Refuse.
                    eprintln!("soundgate: cannot open WAL ({e}); refusing to start");
                    std::process::exit(1);
                }
                Ok(f) => {
                    // Read all lines first so a parse failure can be classified:
                    // a torn FINAL record is the expected artifact of a crash
                    // mid-append and is safely ignored (its state change was never
                    // acknowledged, because fsync precedes the reply). An
                    // unparsable record with MORE records after it is mid-log
                    // corruption; recovering past it would silently drop fences
                    // and dedup entries, so we refuse to start (fail-closed).
                    let lines: Vec<String> = match BufReader::new(f)
                        .lines()
                        .collect::<Result<Vec<_>, _>>()
                    {
                        Ok(v) => v.into_iter().filter(|l| !l.trim().is_empty()).collect(),
                        Err(e) => {
                            eprintln!("soundgate: I/O error reading WAL ({e}); refusing to start");
                            std::process::exit(1);
                        }
                    };
                    for (i, line) in lines.iter().enumerate() {
                        match serde_json::from_str::<Event>(line) {
                            Ok(ev) => {
                                gate.apply(&ev);
                                recovered += 1;
                            }
                            Err(e) => {
                                if i + 1 == lines.len() {
                                    eprintln!(
                                        "soundgate: ignoring torn final WAL record ({})",
                                        e
                                    );
                                    break;
                                }
                                eprintln!(
                                    "soundgate: WAL record {} of {} is unparsable ({}); \
                                 mid-log corruption -- refusing to start with partial \
                                 fences (fail-closed). Repair or truncate the WAL.",
                                    i + 1,
                                    lines.len(),
                                    e
                                );
                                std::process::exit(1);
                            }
                        }
                    }
                }
            }
            let f = OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .expect("open wal for append");
            eprintln!("soundgate: recovered {} event(s) from {}", recovered, path);
            Some(f)
        }
        None => None,
    };

    // Optional decision secret: enables HMAC-authenticated decisions
    // (SOUNDGATE_DECISION_SECRET). Absent -> decisions are unauthenticated
    // (the reference/benchmark mode); present -> forged/absent MACs refuse.
    let secret: Option<Arc<Vec<u8>>> = std::env::var("SOUNDGATE_DECISION_SECRET")
        .ok()
        .filter(|s| !s.is_empty())
        .map(|s| Arc::new(s.into_bytes()));
    if secret.is_some() {
        eprintln!("soundgate: decision authenticity ENABLED (HMAC-SHA256)");
    }
    let gate = Arc::new(Mutex::new(gate));
    let wal: Option<SyncSender<WalMsg>> = wal_file.map(|f| {
        let (tx, rx) = sync_channel::<WalMsg>(4096);
        std::thread::spawn(move || wal_writer(f, rx));
        tx
    });
    let listener = TcpListener::bind(&addr).expect("bind");
    eprintln!("soundgate listening on {} ({})", addr,
              if wal_path.is_some() { "durable: WAL" } else { "in-memory" });
    for stream in listener.incoming() {
        match stream {
            Ok(s) => {
                let g = Arc::clone(&gate);
                let w = wal.clone();
                let sec = secret.clone();
                std::thread::spawn(move || handle(s, g, w, sec));
            }
            Err(e) => eprintln!("accept error: {}", e),
        }
    }
}