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
    c.bench_function("submit_release_unique_growing", |b| {
        let mut g = Gate::new();
        let mut i = 0u64;

        b.iter(|| {
            i += 1;
            black_box(g.submit(eff("r", format!("k{i}"), false)))
        });
    });

    c.bench_function("submit_release_unique_populated_100k", |b| {
        let mut g = populated_gate(100_000);
        let mut i = 0u64;
        b.iter(|| {
            i += 1;
            black_box(g.submit(eff("r", format!("n{i}"), false)))
        });
    });

    c.bench_function("submit_refused_duplicate_populated_100k", |b| {
        let mut g = populated_gate(100_000);
        b.iter(|| black_box(g.submit(eff("warm", "k5000".into(), false))));
    });

    c.bench_function("submit_refused_cancelled", |b| {
        let mut g = populated_gate(100_000);
        b.iter(|| black_box(g.submit(eff("dead_run", "any".into(), false))));
    });

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