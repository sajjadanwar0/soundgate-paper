//! Regression tests for the WAL recovery barrier (soundgate 0.1.4).
//!
//! Reproduces the byte-prefix sweep of Cenab Batu Bora, "A Restart Is Not
//! Permission: When an Agent Gate Forgets 'No'" (Apart Research incident-
//! response sprint, September 2026), which found that soundgate 0.1.3 could
//! lose an acknowledged decision across two restarts: a torn final fragment
//! was skipped but left in the log, the next append landed on the same line,
//! and the second recovery skipped the merged line as a torn final record.
//!
//! Every byte prefix of a three-record log is used as the on-disk state at
//! the first recovery. Two decisions are then acknowledged over the wire, the
//! process is killed, and the second recovery must still enforce both. A
//! history counts as a prohibited execution when a submit that the log must
//! refuse is released instead.

use soundgate::Event;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

const BIN: &str = env!("CARGO_BIN_EXE_soundgate");

struct Server {
    child: Child,
    port: u16,
}

/// Start a gate on an ephemeral port with `wal` as its log. Returns the
/// server once it reports its listener, or the exit status and stderr if it
/// refused to start.
fn start(wal: &Path) -> Result<Server, String> {
    let mut child = Command::new(BIN)
        .arg("127.0.0.1:0")
        .arg(wal)
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn soundgate");
    let mut reader = BufReader::new(child.stderr.take().expect("stderr"));
    let mut log = String::new();
    loop {
        let mut line = String::new();
        let n = reader.read_line(&mut line).expect("read stderr");
        if n == 0 {
            let status = child.wait().expect("wait");
            return Err(format!("{status}: {}", log.trim()));
        }
        log.push_str(&line);
        if let Some(rest) = line.strip_prefix("soundgate listening on 127.0.0.1:") {
            let port: u16 = rest
                .split_whitespace()
                .next()
                .and_then(|p| p.parse().ok())
                .expect("port in listening line");
            // Keep draining stderr so the server never blocks on a full pipe.
            std::thread::spawn(move || {
                let mut sink = String::new();
                while reader.read_line(&mut sink).map(|n| n > 0).unwrap_or(false) {
                    sink.clear();
                }
            });
            return Ok(Server { child, port });
        }
    }
}

impl Server {
    fn call(&self, req: &str) -> String {
        let mut s = TcpStream::connect(("127.0.0.1", self.port)).expect("connect");
        s.write_all(req.as_bytes()).expect("send");
        s.write_all(b"\n").expect("send");
        let mut line = String::new();
        BufReader::new(s).read_line(&mut line).expect("reply");
        let v: serde_json::Value = serde_json::from_str(&line).expect("json reply");
        v["verdict"].as_str().expect("verdict").to_string()
    }

    /// Crash the process (SIGKILL on Unix): no shutdown hook runs.
    fn crash(mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("soundgate-wal-barrier-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).expect("scratch dir");
    dir
}

/// Three acknowledged records: a release, a rejection and a cancellation.
fn baseline_records() -> Vec<Event> {
    vec![
        Event::Released { run_id: "r1".into(), effect_key: "k1".into() },
        Event::Rejected { run_id: "r1".into(), effect_key: "k2".into() },
        Event::Cancelled { run_id: "r2".into() },
    ]
}

fn encode(events: &[Event]) -> Vec<u8> {
    let mut b = Vec::new();
    for ev in events {
        b.extend(serde_json::to_vec(ev).expect("serialize"));
        b.push(b'\n');
    }
    b
}

/// The verdict the gate owes once a record is durable, and the submit that
/// tests it.
fn owed(ev: &Event) -> (String, &'static str) {
    match ev {
        Event::Released { run_id, effect_key } => (
            format!(r#"{{"op":"submit","run_id":"{run_id}","effect_key":"{effect_key}"}}"#),
            "refused_duplicate",
        ),
        Event::Rejected { run_id, effect_key } => (
            format!(r#"{{"op":"submit","run_id":"{run_id}","effect_key":"{effect_key}"}}"#),
            "refused_rejected",
        ),
        Event::Cancelled { run_id } | Event::Closed { run_id } => (
            format!(r#"{{"op":"submit","run_id":"{run_id}","effect_key":"any"}}"#),
            "refused_cancelled",
        ),
    }
}

/// After the barrier the log on disk must be a sequence of complete,
/// parsable, newline-terminated records.
fn well_formed(wal: &Path) -> Result<(), String> {
    let bytes = std::fs::read(wal).map_err(|e| e.to_string())?;
    if !(bytes.is_empty() || bytes.ends_with(b"\n")) {
        return Err("log does not end with a newline".into());
    }
    for (i, line) in bytes.split(|&b| b == b'\n').enumerate() {
        if line.is_empty() {
            continue;
        }
        serde_json::from_slice::<Event>(line).map_err(|e| format!("record {} unparsable: {e}", i + 1))?;
    }
    Ok(())
}

/// One acknowledged decision taken after the first restart, and the verdict
/// the gate owes for it after the second.
struct Arm {
    name: &'static str,
    decide: &'static str,
    acked: &'static str,
    probe: &'static str,
    owed: &'static str,
}

const ARMS: [Arm; 2] = [
    Arm {
        name: "rejection",
        decide: r#"{"op":"decide","run_id":"r3","effect_key":"k9","approved":false}"#,
        acked: "refused_rejected",
        probe: r#"{"op":"submit","run_id":"r3","effect_key":"k9"}"#,
        owed: "refused_rejected",
    },
    Arm {
        name: "release",
        decide: r#"{"op":"submit","run_id":"r3","effect_key":"k8"}"#,
        acked: "release",
        probe: r#"{"op":"submit","run_id":"r3","effect_key":"k8"}"#,
        owed: "refused_duplicate",
    },
];

#[test]
fn byte_prefix_sweep_keeps_acknowledged_decisions_across_two_restarts() {
    let records = baseline_records();
    let base = encode(&records);
    // End offset (past the newline) of each record in the encoded log.
    let ends: Vec<usize> = base
        .iter()
        .enumerate()
        .filter(|&(_, &b)| b == b'\n')
        .map(|(i, _)| i + 1)
        .collect();
    let dir = scratch("sweep");

    let mut histories = 0usize;
    let mut prohibited = 0usize;
    let mut refused = 0usize;
    let mut malformed = 0usize;

    for arm in &ARMS {
        for cut in 0..=base.len() {
            let wal = dir.join(format!("{}_{cut}.wal", arm.name));
            std::fs::write(&wal, &base[..cut]).expect("write prefix");
            histories += 1;

            // Recovery 1 must open the gate wherever the cut falls.
            let s1 = start(&wal)
                .unwrap_or_else(|e| panic!("{} prefix {cut}: first recovery refused: {e}", arm.name));
            // One decision acknowledged after the restart. The gate's reply is
            // its promise that the decision is durable.
            assert_eq!(s1.call(arm.decide), arm.acked, "{} prefix {cut}", arm.name);
            s1.crash();

            // Recovery 2 must enforce it.
            let s2 = match start(&wal) {
                Ok(s) => s,
                Err(e) => {
                    refused += 1;
                    eprintln!("{} prefix {cut}: second recovery refused: {e}", arm.name);
                    continue;
                }
            };
            let got = s2.call(arm.probe);
            if got != arm.owed {
                prohibited += 1;
                eprintln!("{} prefix {cut}: {} forgotten after restart (submit -> {got})", arm.name, arm.name);
            }
            // Every baseline record the prefix contained in full (with or
            // without its final newline) must still hold; a fragment was
            // never acknowledged, so nothing is owed for it.
            for (ev, end) in records.iter().zip(&ends) {
                if cut + 1 >= *end {
                    let (req, want) = owed(ev);
                    let got = s2.call(&req);
                    if got != want {
                        prohibited += 1;
                        eprintln!("{} prefix {cut}: {ev:?} forgotten after restart (submit -> {got})", arm.name);
                    }
                }
            }
            s2.crash();
            if let Err(e) = well_formed(&wal) {
                malformed += 1;
                eprintln!("{} prefix {cut}: log malformed after restart ({e})", arm.name);
            }
        }
    }

    eprintln!(
        "byte-prefix sweep: {histories} histories, {prohibited} prohibited executions, \
         {refused} refused restarts, {malformed} malformed logs"
    );
    assert_eq!(histories, 2 * (base.len() + 1));
    assert_eq!(prohibited, 0, "{prohibited} prohibited executions across {histories} histories");
    assert_eq!(refused, 0, "{refused} restarts refused across {histories} histories");
    assert_eq!(malformed, 0, "{malformed} malformed logs across {histories} histories");
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn log_merged_by_0_1_3_is_refused_not_silently_dropped() {
    // The on-disk state 0.1.3 left behind: a torn fragment, then a later
    // acknowledged record appended on the same line. The old recovery
    // skipped this line as a "torn final record" and forgot the rejection;
    // the barrier refuses to start instead.
    let base = encode(&baseline_records());
    let cut = base.iter().position(|&b| b == b'\n').expect("newline") + 10;
    let mut bytes = base[..cut].to_vec();
    bytes.extend(serde_json::to_vec(&Event::Rejected { run_id: "r3".into(), effect_key: "k9".into() }).unwrap());
    bytes.push(b'\n');

    let dir = scratch("merged");
    let wal = dir.join("merged.wal");
    std::fs::write(&wal, &bytes).expect("write");
    match start(&wal) {
        Ok(s) => {
            s.crash();
            panic!("gate started on a log with a merged, unparsable record");
        }
        Err(msg) => assert!(msg.contains("unparsable"), "unexpected refusal: {msg}"),
    }
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn second_gate_on_the_same_wal_is_refused() {
    let dir = scratch("lock");
    let wal = dir.join("locked.wal");
    std::fs::write(&wal, encode(&baseline_records())).expect("write");
    let first = start(&wal).expect("first gate starts");
    match start(&wal) {
        Ok(s) => {
            s.crash();
            first.crash();
            panic!("a second gate opened the same WAL");
        }
        Err(msg) => assert!(msg.contains("locked by another soundgate"), "unexpected refusal: {msg}"),
    }
    first.crash();
    // The lock dies with the process: a restart must succeed.
    let again = start(&wal).expect("restart after crash");
    again.crash();
    let _ = std::fs::remove_dir_all(&dir);
}
