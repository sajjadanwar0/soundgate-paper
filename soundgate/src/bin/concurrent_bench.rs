//! Concurrent-client throughput/latency benchmark for the SoundGate server.
//!
//! Closes the evaluation gap the paper previously deferred ("a
//! concurrent-client throughput benchmark is left to future work"): C
//! closed-loop clients, each on its own TCP connection, each issuing
//! sequential unique-key `submit` requests on the release path (the
//! state-growing common case). The server is thread-per-connection with a
//! single Mutex<Gate>, so this measures the gate as a serialization point
//! under contention -- exactly the scenario reviewers asked about.
//!
//! Usage:
//!   cargo run --release --bin concurrent_bench -- <addr> <clients> <ops_per_client> [label]
//! The server must already be running (with or without a WAL argument).
//! Prints: label, clients, total ops, wall seconds, throughput (adm/s),
//! and latency p50/p95/p99/p99.9/max in microseconds.

use std::env;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Instant;

fn main() {
    let args: Vec<String> = env::args().collect();
    let addr = args.get(1).cloned().unwrap_or_else(|| "127.0.0.1:8796".into());
    let clients: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let ops: usize = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(5000);
    let label = args.get(4).cloned().unwrap_or_else(|| "release-path".into());
    // Per-invocation nonce: guarantees fresh (run, key) identities on a shared
    // server, so every measured op takes the RELEASE path (a reused identity
    // would be a cheap RefusedDuplicate and skip the WAL fsync, silently
    // inflating durable-mode throughput -- caught by WAL-line accounting).
    let nonce = std::process::id();

    let start_flag = Arc::new(AtomicBool::new(false));
    let mut handles = Vec::with_capacity(clients);

    for c in 0..clients {
        let addr = addr.clone();
        let flag = Arc::clone(&start_flag);
        handles.push(thread::spawn(move || -> Vec<u64> {
            let stream = TcpStream::connect(&addr).expect("connect");
            stream.set_nodelay(true).unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut stream = stream;
            let mut line = String::new();

            // Per-connection warmup (excluded from measurement).
            for i in 0..200 {
                let req = format!(
                    "{{\"op\":\"submit\",\"run_id\":\"warm{nonce}-{c}\",\"effect_key\":\"w{i}\",\"needs_approval\":false}}\n"
                );
                stream.write_all(req.as_bytes()).unwrap();
                line.clear();
                reader.read_line(&mut line).unwrap();
            }
            while !flag.load(Ordering::Acquire) {
                std::hint::spin_loop();
            }
            let mut lat = Vec::with_capacity(ops);
            for i in 0..ops {
                let req = format!(
                    "{{\"op\":\"submit\",\"run_id\":\"bench{nonce}-{c}\",\"effect_key\":\"k{i}\",\"needs_approval\":false}}\n"
                );
                let t0 = Instant::now();
                stream.write_all(req.as_bytes()).unwrap();
                line.clear();
                reader.read_line(&mut line).unwrap();
                lat.push(t0.elapsed().as_nanos() as u64);
                debug_assert!(line.contains("release"), "unexpected verdict: {line}");
            }
            lat
        }));
    }

    // Give all threads time to finish warmup, then release simultaneously.
    thread::sleep(std::time::Duration::from_millis(700));
    let wall0 = Instant::now();
    start_flag.store(true, Ordering::Release);

    let mut all: Vec<u64> = Vec::with_capacity(clients * ops);
    for h in handles {
        all.extend(h.join().expect("client thread"));
    }
    let wall = wall0.elapsed().as_secs_f64();
    all.sort_unstable();
    let n = all.len();
    let pct = |p: f64| all[((n as f64 * p) as usize).min(n - 1)] as f64 / 1000.0;
    println!(
        "{label},clients={clients},ops={n},wall_s={wall:.3},thpt_adm_per_s={:.0},p50_us={:.1},p95_us={:.1},p99_us={:.1},p999_us={:.1},max_us={:.1}",
        n as f64 / wall,
        pct(0.50),
        pct(0.95),
        pct(0.99),
        pct(0.999),
        all[n - 1] as f64 / 1000.0
    );
}