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
        _ => None,
    }
}

type WalMsg = (String, SyncSender<Result<(), String>>);
const WAL_BATCH: usize = 512;

fn wal_writer(mut f: File, rx: Receiver<WalMsg>) {
    let mut hist = [0u64; 5];
    let (mut batches, mut events) = (0u64, 0u64);

    let stats_every: u64 = std::env::var("SOUNDGATE_WAL_STATS_EVERY")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);

    loop {
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

    let mut gate = Gate::new();

    let wal_file = match &wal_path {
        Some(path) => {
            let mut recovered = 0usize;
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