#![cfg(feature = "conformance")]

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
impl ModelGate {
    fn submit(&mut self, r: u16, k: u16, na: bool) -> Admission {
        let id = (r, k);

        if self.cancelled.contains(&r) || self.closed.contains(&r) { return Admission::RefusedCancelled; }

        if self.released.contains(&id) { return Admission::RefusedDuplicate; }

        if self.rejected.contains(&id) { return Admission::RefusedRejected; }

        if self.pending.contains(&id) { return Admission::HeldForApproval; }

        if na { self.pending.insert(id); Admission::HeldForApproval }
        else { self.released.insert(id); Admission::Release }
    }

    fn decide(&mut self, r: u16, k: u16, ap: bool) -> Admission {
        let id = (r, k);

        if self.pending.remove(&id) {
            if self.cancelled.contains(&r) || self.closed.contains(&r) { return Admission::RefusedCancelled; }
            return if ap { self.released.insert(id); Admission::Release }
            else { self.rejected.insert(id); Admission::RefusedRejected };
        }

        if self.cancelled.contains(&r) || self.closed.contains(&r) { return Admission::RefusedCancelled; }

        if self.released.contains(&id) { return Admission::RefusedDuplicate; }

        if !ap { self.rejected.insert(id); return Admission::RefusedRejected; }
        Admission::RefusedDuplicate
    }

    fn cancel(&mut self, r: u16) { self.cancelled.insert(r); self.pending.retain(|(rr, _)| *rr != r); }

    fn close_run(&mut self, r: u16) {
        self.closed.insert(r);
        self.pending.retain(|(rr, _)| *rr != r);
        self.released.retain(|(rr, _)| *rr != r);
        self.rejected.retain(|(rr, _)| *rr != r);
    }

    fn state(&self) -> State {
        (self.released.clone(), self.rejected.clone(), self.pending.clone(),
         self.cancelled.clone(), self.closed.clone())
    }
}
type State = (BTreeSet<(u16,u16)>, BTreeSet<(u16,u16)>, BTreeSet<(u16,u16)>, BTreeSet<u16>, BTreeSet<u16>);

fn apply(g: &mut Gate, m: &mut ModelGate, t: u32) -> (Admission, Admission, String) {
    match t {
        0..=7 => { let r=((t>>2)&1) as u16; let k=((t>>1)&1) as u16; let na=(t&1)==1;
            let rv=g.submit(Effect{run_id:r.to_string(), effect_key:k.to_string(), needs_approval:na});
            let mv=m.submit(r,k,na); (rv,mv,format!("submit(r{r},k{k},na={na})")) }
        8..=15 => { let t=t-8; let r=((t>>2)&1) as u16; let k=((t>>1)&1) as u16; let ap=(t&1)==1;
            let rv=g.decide(&r.to_string(), &k.to_string(), ap);
            let mv=m.decide(r,k,ap); (rv,mv,format!("decide(r{r},k{k},ap={ap})")) }
        16..=17 => { let r=(t-16) as u16; g.cancel(&r.to_string()); m.cancel(r);
            (Admission::RefusedCancelled, Admission::RefusedCancelled, format!("cancel(r{r})")) }
        _ => { let r=(t-18) as u16; g.close_run(&r.to_string()); m.close_run(r);
            (Admission::RefusedCancelled, Admission::RefusedCancelled, format!("close(r{r})")) }
    }
}

fn real_state(g: &Gate) -> State { g.conformance_snapshot() }

const RADIX: u64 = 20;

#[test]
fn model_and_code_equivalent_exhaustively() {
    let k: u32 = std::env::var("SG_EXHAUSTIVE_K").ok()
        .and_then(|s| s.parse().ok()).unwrap_or(5);
    let total: u64 = RADIX.pow(k);

    let mut checked: u64 = 0;
    let mut seen_by_depth: Vec<BTreeSet<State>> = vec![BTreeSet::new(); (k as usize)+1];
    let cancel_free_verdict_checks;
    let mut verdict_checks: u64 = 0;

    for seq in 0..total {
        let mut g = Gate::new();
        let mut m = ModelGate::default();
        let mut code = seq;

        for depth in 1..=k {
            let t = (code % RADIX) as u32;
            code /= RADIX;
            let (rv, mv, label) = apply(&mut g, &mut m, t);
            verdict_checks += 1;
            assert!(rv == mv,
                    "VERDICT DIVERGENCE at seq={seq} depth={depth} op={label}: real={rv:?} model={mv:?}");
            let rs = real_state(&g);
            let ms = m.state();
            assert!(rs == ms,
                    "STATE DIVERGENCE at seq={seq} depth={depth} op={label}: real={rs:?} model={ms:?}");
            seen_by_depth[depth as usize].insert(ms);
        }
        checked += 1;
    }

    cancel_free_verdict_checks = verdict_checks;

    let mut cumulative: BTreeSet<State> = BTreeSet::new();
    println!("exhaustive conformance: K={k}, sequences checked={checked}, per-op checks={cancel_free_verdict_checks}");

    for d in 1..=(k as usize) {
        let before = cumulative.len();
        for s in &seen_by_depth[d] { cumulative.insert(s.clone()); }
        println!("  depth {d}: cumulative distinct reachable states = {} (+{} new)",
                 cumulative.len(), cumulative.len()-before);
    }
    println!("  => total distinct reachable states over the 2x2 domain = {}", cumulative.len());
    assert!(checked == total);
}

#[test]
fn model_reachable_state_space_bfs() {
    use std::collections::{BTreeSet, VecDeque};

    fn from_state(s: &State) -> ModelGate {
        ModelGate { released: s.0.clone(), rejected: s.1.clone(), pending: s.2.clone(),
            cancelled: s.3.clone(), closed: s.4.clone() }
    }

    let start = ModelGate::default().state();
    let mut seen: BTreeSet<State> = BTreeSet::new();
    let mut q: VecDeque<(State, u32)> = VecDeque::new();
    seen.insert(start.clone());
    q.push_back((start, 0));
    let mut diameter = 0u32;

    while let Some((st, d)) = q.pop_front() {
        diameter = diameter.max(d);
        for t in 0..(RADIX as u32) {
            let mut m = from_state(&st);
            let mut g = Gate::new();
            let _ = apply(&mut g, &mut m, t);
            let ns = m.state();
            if seen.insert(ns.clone()) { q.push_back((ns, d+1)); }
        }
    }

    println!("BFS reachable state space (2x2 domain): {} states, diameter {}", seen.len(), diameter);
}

#[test]
fn all_reachable_transitions_equivalent() {
    use std::collections::{BTreeMap, VecDeque};

    fn from_state(s: &State) -> ModelGate {
        ModelGate { released: s.0.clone(), rejected: s.1.clone(), pending: s.2.clone(),
            cancelled: s.3.clone(), closed: s.4.clone() }
    }

    let start = ModelGate::default().state();
    let mut witness: BTreeMap<State, Vec<u32>> = BTreeMap::new();
    let mut q: VecDeque<State> = VecDeque::new();
    witness.insert(start.clone(), vec![]);
    q.push_back(start);

    while let Some(st) = q.pop_front() {
        let w = witness[&st].clone();

        for t in 0..(RADIX as u32) {
            let mut m = from_state(&st);
            let mut dummy = Gate::new();
            let _ = apply(&mut dummy, &mut m, t);
            let ns = m.state();
            if !witness.contains_key(&ns) {
                let mut nw = w.clone(); nw.push(t);
                witness.insert(ns.clone(), nw);
                q.push_back(ns);
            }
        }
    }

    let n_states = witness.len();

    let mut transitions_checked: u64 = 0;

    for (state, w) in &witness {
        for t in 0..(RADIX as u32) {
            let mut g = Gate::new();
            let mut m = ModelGate::default();

            for &wt in w {
                let (rv, mv, lbl) = apply(&mut g, &mut m, wt);
                assert!(rv == mv, "replay verdict divergence op={lbl}: {rv:?} vs {mv:?}");
                assert!(real_state(&g) == m.state(), "replay state divergence after {lbl}");
            }

            assert!(&m.state() == state && real_state(&g) == *state,
                    "witness did not reproduce the target state");

            let (rv, mv, lbl) = apply(&mut g, &mut m, t);
            assert!(rv == mv,
                    "TRANSITION VERDICT DIVERGENCE from {state:?} via {lbl}: real={rv:?} model={mv:?}");
            assert!(real_state(&g) == m.state(),
                    "TRANSITION STATE DIVERGENCE from {state:?} via {lbl}");
            transitions_checked += 1;
        }
    }

    println!("COMPLETE transition-relation equivalence over the 2x2 domain: \
              {n_states} reachable states x {} transitions = {transitions_checked} checked, 0 divergences",
             RADIX);
    assert_eq!(n_states, 729);
    assert_eq!(transitions_checked, 729 * RADIX);
}