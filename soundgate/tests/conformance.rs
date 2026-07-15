//! Run: cargo test --test conformance --release -- --nocapture

use std::collections::BTreeSet;

use soundgate::{Admission, Effect, Gate};

#[derive(Clone, Default)]
struct ModelGate {
    released: BTreeSet<(u16, u16)>,
    rejected: BTreeSet<(u16, u16)>,
    pending: BTreeSet<(u16, u16)>,
    cancelled: BTreeSet<u16>,
    closed: BTreeSet<u16>,
}

fn same_verdict(real: &Admission, model: &Admission) -> bool {
    real == model
}

impl ModelGate {
    fn submit(&mut self, r: u16, k: u16, needs_approval: bool) -> Admission {
        let id = (r, k);
        if self.cancelled.contains(&r) || self.closed.contains(&r) {
            return Admission::RefusedCancelled;
        }

        if self.released.contains(&id) {
            return Admission::RefusedDuplicate;
        }

        if self.rejected.contains(&id) {
            return Admission::RefusedRejected;
        }

        if self.pending.contains(&id) {
            return Admission::HeldForApproval;
        }

        if needs_approval {
            self.pending.insert(id);
            Admission::HeldForApproval
        } else {
            self.released.insert(id);
            Admission::Release
        }
    }

    fn decide(&mut self, r: u16, k: u16, approved: bool) -> Admission {
        let id = (r, k);

        if self.pending.remove(&id) {
            // Was pending. Cancellation/closure may have arrived meanwhile.
            if self.cancelled.contains(&r) || self.closed.contains(&r) {
                return Admission::RefusedCancelled;
            }
            return if approved {
                self.released.insert(id);
                Admission::Release
            } else {
                self.rejected.insert(id);
                Admission::RefusedRejected
            };
        }

        if self.cancelled.contains(&r) || self.closed.contains(&r) {
            return Admission::RefusedCancelled;
        }

        if self.released.contains(&id) {
            return Admission::RefusedDuplicate;
        }

        if !approved {
            self.rejected.insert(id);
            return Admission::RefusedRejected;
        }
        Admission::RefusedDuplicate
    }

    fn cancel(&mut self, r: u16) {
        self.cancelled.insert(r);
        self.pending.retain(|(rr, _)| *rr != r);
    }

    fn close_run(&mut self, r: u16) {
        self.closed.insert(r);
        self.pending.retain(|(rr, _)| *rr != r);
        self.released.retain(|(rr, _)| *rr != r);
        self.rejected.retain(|(rr, _)| *rr != r);
    }
}

fn real_state(g: &Gate) -> (BTreeSet<(u16, u16)>, BTreeSet<(u16, u16)>, BTreeSet<(u16, u16)>, BTreeSet<u16>, BTreeSet<u16>) {
    g.conformance_snapshot()
}

fn model_state(m: &ModelGate) -> (BTreeSet<(u16, u16)>, BTreeSet<(u16, u16)>, BTreeSet<(u16, u16)>, BTreeSet<u16>, BTreeSet<u16>) {
    (m.released.clone(), m.rejected.clone(), m.pending.clone(), m.cancelled.clone(), m.closed.clone())
}

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }

    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
}

#[test]
fn model_and_code_are_observationally_equivalent() {
    const RUNS: u16 = 8;
    const KEYS: u16 = 6;
    const TRACES: u64 = 200_000;
    const OPS_PER_TRACE: u64 = 60;

    let mut rng = Rng(0x5EED_1234_ABCD_0001);
    let mut checked: u64 = 0;

    for trace in 0..TRACES {
        let mut real = Gate::new();
        let mut model = ModelGate::default();
        let mut history: Vec<String> = Vec::new();

        for _ in 0..OPS_PER_TRACE {
            let r = rng.below(RUNS as u64) as u16;
            let k = rng.below(KEYS as u64) as u16;
            let run_s = r.to_string();
            let key_s = k.to_string();

            let (rv, mv, op) = match rng.below(5) {
                0 | 1 => {
                    let needs = rng.below(2) == 1;
                    let rv = real.submit(Effect {
                        run_id: run_s.clone(),
                        effect_key: key_s.clone(),
                        needs_approval: needs,
                    });
                    let mv = model.submit(r, k, needs);
                    (rv, mv, format!("submit(r{r},k{k},appr={needs})"))
                }
                2 | 3 => {
                    let approved = rng.below(2) == 1;
                    let rv = real.decide(&run_s, &key_s, approved);
                    let mv = model.decide(r, k, approved);
                    (rv, mv, format!("decide(r{r},k{k},appr={approved})"))
                }
                _ => {
                    if rng.below(2) == 0 {
                        real.cancel(&run_s);
                        model.cancel(r);
                        // cancel returns nothing; compare state only.
                        (Admission::Release, Admission::Release, format!("cancel(r{r})"))
                    } else {
                        real.close_run(&run_s);
                        model.close_run(r);
                        (Admission::Release, Admission::Release, format!("close(r{r})"))
                    }
                }
            };

            history.push(op.clone());

            if !op.starts_with("cancel") && !op.starts_with("close") {
                assert!(
                    same_verdict(&rv, &mv),
                    "VERDICT DIVERGENCE\ntrace {trace} op {op}\n  real  = {rv:?}\n  model = {mv:?}\nhistory:\n  {}",
                    history.join("\n  ")
                );
            }

            let rs = real_state(&real);
            let ms = model_state(&model);
            assert!(
                rs == ms,
                "STATE DIVERGENCE\ntrace {trace} after {op}\n  real (rel,rej,pend,canc,closed)  = {rs:?}\n  model                            = {ms:?}\nhistory:\n  {}",
                history.join("\n  ")
            );
            checked += 1;
        }
    }

    eprintln!(
        "conformance: {checked} operations across {TRACES} traces \
         (domain {RUNS} runs x {KEYS} keys) -- real Gate and Verus model \
         agreed on every verdict and every derived-state snapshot."
    );
    assert_eq!(checked, TRACES * OPS_PER_TRACE);
}