use serde::{Deserialize, Serialize};
use soundgate::{Admission, Effect, Event, Gate};
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
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
        #[serde(default)]
        mac: Option<String>,
    },
    Cancel {
        run_id: String,
    },
    // 2026-10-02 (final files): CloseRun over the wire. Marks the run terminal,
    // drops its per-identity state, and is logged so recovery replays it.
    Close {
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
        (Request::Close { run_id }, Reply::Ack) => {
            Some(Event::Closed { run_id: run_id.clone() })
        }
        _ => None,
    }
}

type Ack = SyncSender<Result<(), String>>;

// A WAL request. `Compact` is a barrier: appends queued before it are written
// and fsynced to the current file first; the snapshot then replaces the file
// atomically; appends queued after it go to the new file.
enum WalMsg {
    Append(String, Ack),
    Compact(Vec<String>, Ack),
}

const WAL_BATCH: usize = 512;

/// Atomically replace the WAL at `path` with `lines`: write a sibling temp
/// file, fsync it, rename it over the log, fsync the directory, reopen for
/// append. A crash before the rename leaves the old log intact; after it, the
/// new log is complete. Returns the append handle for the new log.
fn compact_wal(path: &str, lines: &[String]) -> std::io::Result<File> {
    let tmp = format!("{path}.compact");
    {
        let mut t = File::create(&tmp)?;
        let mut buf = String::with_capacity(lines.len() * 48);
        for l in lines {
            buf.push_str(l);
            buf.push('\n');
        }
        t.write_all(buf.as_bytes())?;
        t.sync_all()?;
    }
    std::fs::rename(&tmp, path)?;
    let dir = Path::new(path).parent().filter(|d| !d.as_os_str().is_empty());
    File::open(dir.unwrap_or(Path::new(".")))?.sync_all()?;
    OpenOptions::new().append(true).open(path)
}

fn wal_writer(path: String, mut f: File, rx: Receiver<WalMsg>) {
    let mut hist = [0u64; 5];
    let (mut batches, mut events) = (0u64, 0u64);
    let mut carried: Option<WalMsg> = None;

    let stats_every: u64 = std::env::var("SOUNDGATE_WAL_STATS_EVERY")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);

    loop {
        let first = match carried.take() {
            Some(m) => m,
            None => match rx.recv() {
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
            },
        };

        let (line, ack) = match first {
            WalMsg::Compact(snapshot, ack) => {
                match compact_wal(&path, &snapshot) {
                    Ok(nf) => {
                        f = nf;
                        eprintln!("soundgate: wal compacted to {} record(s)", snapshot.len());
                        let _ = ack.send(Ok(()));
                    }
                    Err(e) => {
                        // Before the rename the old log is intact and `f` still
                        // appends to it; after the rename `f` would append to
                        // an unlinked inode, so stop rather than lose a record.
                        if Path::new(&format!("{path}.compact")).exists() {
                            let _ = ack.send(Err(format!("wal compaction: {e}")));
                        } else {
                            eprintln!("soundgate: wal reopen after compaction failed ({e}); stopping (fail-closed)");
                            std::process::exit(1);
                        }
                    }
                }
                continue;
            }
            WalMsg::Append(line, ack) => (line, ack),
        };

        let mut batch: Vec<(String, Ack)> = vec![(line, ack)];

        while batch.len() < WAL_BATCH {
            match rx.try_recv() {
                Ok(WalMsg::Append(l, a)) => batch.push((l, a)),
                Ok(m @ WalMsg::Compact(..)) => {
                    carried = Some(m);
                    break;
                }
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

/// Online compaction policy: on a close, rewrite the log as a snapshot once the
/// records appended since the last snapshot reach max(min, last snapshot size),
/// i.e. once the log has at least doubled. Each compaction writes at most as
/// many records as were appended since the previous one, so the amortized cost
/// is O(1) per event and the log stays within about twice its live size.
struct Compaction {
    min: u64,
    appended: AtomicU64,
    last_snapshot: AtomicU64,
}

fn snapshot_lines(g: &Gate) -> Vec<String> {
    g.durable_events()
        .iter()
        .map(|ev| serde_json::to_string(ev).expect("serialize event"))
        .collect()
}

fn handle(
    stream: TcpStream,
    gate: Arc<Mutex<Gate>>,
    wal: Option<SyncSender<WalMsg>>,
    secret: Option<Arc<Vec<u8>>>,
    compaction: Arc<Compaction>,
) {
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

        let mut compacted: Option<Receiver<Result<(), String>>> = None;

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
                    Request::Close { run_id } => {
                        g.close_run(run_id);
                        let due = compaction.min > 0
                            && compaction.appended.load(Ordering::Relaxed)
                                >= compaction.min.max(compaction.last_snapshot.load(Ordering::Relaxed));
                        // The snapshot is taken and its Compact message queued
                        // while the gate lock is held: every state change after
                        // the snapshot is queued after the barrier, so no
                        // acknowledged record can be lost by the rewrite.
                        if let Some(tx) = wal.as_ref().filter(|_| due) {
                            let snapshot = snapshot_lines(&g);
                            compaction.last_snapshot.store(snapshot.len() as u64, Ordering::Relaxed);
                            compaction.appended.store(0, Ordering::Relaxed);
                            let (ack_tx, ack_rx) = sync_channel::<Result<(), String>>(1);
                            if tx.send(WalMsg::Compact(snapshot, ack_tx)).is_ok() {
                                compacted = Some(ack_rx);
                            }
                        }
                        Reply::Ack
                    }
                    Request::Ping => Reply::Pong,
                };
                (reply, Some(req))
            }
            Err(e) => (Reply::Error { message: format!("bad request: {}", e) }, None),
        };

        if let (Some(req), Some(tx)) = (req.as_ref(), wal.as_ref()) {
            if let Some(ev) = event_for(req, &reply) {
                let persisted = serde_json::to_string(&ev)
                    .map_err(|e| e.to_string())
                    .and_then(|line| {
                        let (ack_tx, ack_rx) = sync_channel::<Result<(), String>>(1);
                        tx.send(WalMsg::Append(line, ack_tx)).map_err(|e| e.to_string())?;
                        ack_rx.recv().map_err(|e| e.to_string())??;
                        compaction.appended.fetch_add(1, Ordering::Relaxed);
                        Ok(())
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

        if let Some(rx) = compacted {
            if let Ok(Err(e)) = rx.recv() {
                eprintln!("soundgate: {e}; the uncompacted log stays authoritative");
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

    let mut gate = Gate::new();

    let mut recovered_records: u64 = 0;
    let wal_file = match &wal_path {
        Some(path) => {
            let mut recovered = 0usize;
            let mut saw_closed = false;
            match File::open(path) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => {
                    eprintln!("soundgate: cannot open WAL ({e}); refusing to start");
                    std::process::exit(1);
                }
                Ok(f) => {
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
                                saw_closed |= matches!(ev, Event::Closed { .. });
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

            eprintln!("soundgate: recovered {} event(s) from {}", recovered, path);

            // Compact at recovery only when the log holds a close: a log with
            // none has nothing to reclaim and stays byte-identical, so every
            // earlier receipt replays exactly as recorded.
            let f = if saw_closed {
                let snapshot = snapshot_lines(&gate);
                let f = compact_wal(path, &snapshot).unwrap_or_else(|e| {
                    eprintln!("soundgate: cannot compact WAL ({e}); refusing to start");
                    std::process::exit(1);
                });
                eprintln!("soundgate: wal compacted at recovery: {} -> {} record(s)", recovered, snapshot.len());
                recovered_records = snapshot.len() as u64;
                f
            } else {
                recovered_records = recovered as u64;
                OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(path)
                    .expect("open wal for append")
            };
            Some(f)
        }
        None => None,
    };

    let secret: Option<Arc<Vec<u8>>> = std::env::var("SOUNDGATE_DECISION_SECRET")
        .ok()
        .filter(|s| !s.is_empty())
        .map(|s| Arc::new(s.into_bytes()));

    if secret.is_some() {
        eprintln!("soundgate: decision authenticity ENABLED (HMAC-SHA256)");
    }

    let gate = Arc::new(Mutex::new(gate));

    let compaction = Arc::new(Compaction {
        min: std::env::var("SOUNDGATE_WAL_COMPACT_MIN")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(65_536),
        appended: AtomicU64::new(0),
        last_snapshot: AtomicU64::new(recovered_records),
    });

    let wal: Option<SyncSender<WalMsg>> = wal_file.map(|f| {
        let (tx, rx) = sync_channel::<WalMsg>(4096);
        let path = wal_path.clone().expect("wal path");
        std::thread::spawn(move || wal_writer(path, f, rx));
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
                let c = Arc::clone(&compaction);
                std::thread::spawn(move || handle(s, g, w, sec, c));
            }
            Err(e) => eprintln!("accept error: {}", e),
        }
    }
}
