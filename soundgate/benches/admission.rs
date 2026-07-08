//! In-process admission latency (Criterion). The paper's Overhead section
//! reports both this and the socket round-trip; this file measures the pure
//! gate decision cost, isolating it from TCP.
//!
//! Design notes (brutal-reviewer proofing):
//! - The gate is constructed ONCE per benchmark, outside the timed closure;
//!   constructing it per-iteration would benchmark the allocator.
//! - The dimension that matters in-process is not payload size (that is a
//!   socket-path concern) but STATE SIZE: admission cost against a gate whose
//!   released set is already large. `*_populated` benches pre-fill 100k
//!   released identities.
//! - `submit_release_unique` grows the set across iterations by design:
//!   Criterion drives millions of iterations, so the reported time is the
//!   amortized insert cost on a realistically large and growing set.
//! - Refusal fast paths (duplicate hit, cancellation fence) do not mutate
//!   state and are measured against the populated gate.
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use soundgate::{Effect, Gate};

fn eff(run: &str, key: String, approval: bool) -> Effect {
    Effect { run_id: run.into(), effect_key: key, needs_approval: approval }
}

fn populated_gate(n: usize) -> Gate {
    let mut g = Gate::new();
    for i in 0..n {
        g.submit(eff("warm", format!("k{i}"), false));
    }
    g.cancel("dead_run");
    g
}

fn bench_admission(c: &mut Criterion) {
    // 1. Happy path: unique release, set growing across iterations.
    c.bench_function("submit_release_unique_growing", |b| {
        let mut g = Gate::new();
        let mut i = 0u64;
        b.iter(|| {
            i += 1;
            black_box(g.submit(eff("r", format!("k{i}"), false)))
        });
    });

    // 2. Unique release against a 100k-identity gate.
    c.bench_function("submit_release_unique_populated_100k", |b| {
        let mut g = populated_gate(100_000);
        let mut i = 0u64;
        b.iter(|| {
            i += 1;
            black_box(g.submit(eff("r", format!("n{i}"), false)))
        });
    });

    // 3. Dedup hit (refused_duplicate) against the populated gate.
    c.bench_function("submit_refused_duplicate_populated_100k", |b| {
        let mut g = populated_gate(100_000);
        b.iter(|| black_box(g.submit(eff("warm", "k5000".into(), false))));
    });

    // 4. Cancellation fence fast path (refused_canceled).
    c.bench_function("submit_refused_cancelled", |b| {
        let mut g = populated_gate(100_000);
        b.iter(|| black_box(g.submit(eff("dead_run", "any".into(), false))));
    });

    // 5. Full approval round: submit(held) + decide(approve). Mutates two
    //    maps per round; keys unique per iteration.
    c.bench_function("held_then_decide_approve", |b| {
        let mut g = Gate::new();
        let mut i = 0u64;
        b.iter(|| {
            i += 1;
            let k = format!("a{i}");
            g.submit(eff("r", k.clone(), true));
            black_box(g.decide("r", &k, true))
        });
    });
}

criterion_group!(benches, bench_admission);
criterion_main!(benches);