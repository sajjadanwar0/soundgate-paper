/* E-E2E-JS: SoundGate wired into a REAL LangGraph.js agent (keyless).
 *
 * The FW-F column of the measurement matrix shows what the JavaScript
 * runtime permits (sibling leak, resume replay, AbortSignal orphan). This
 * harness is the repaired twin: the same @langchain/langgraph 1.4.7 graphs,
 * with every side effect routed through the identical ~20-line wrapper shape
 * used by the four Python integrations, submitting to the live Rust gate
 * over its line-delimited TCP protocol and executing only on "release".
 *
 * Three scenarios, each the repaired twin of a measured FW-F violation:
 *   A. SIBLING LEAK REPAIRED  (measured probe J1/J1r): fan-out from START to
 *      {gate node calling interrupt(), sibling node whose effect is
 *      mediated with needs_approval:true}. During the pause the sibling's
 *      effect is HELD, not executed; the human rejects -> refused_rejected;
 *      resume completes with zero effects executed.
 *   B. REPLAY REPAIRED        (measured probe J2): a node performs a
 *      mediated effect then interrupt()s; on resume LangGraph.js re-executes
 *      the node body (documented, and measured); the wrapper's resubmission
 *      is refused_duplicate -> the effect executes EXACTLY once although the
 *      node body ran twice.
 *   C. ORPHAN FENCED          (measured probe J3): a worker node sleeps then
 *      fires its effect; the caller aborts at 150 ms via AbortSignal (the
 *      framework's single documented cancellation surface). Unmediated, the
 *      effect lands AFTER the caller observed the abort (measured). Here the
 *      cancellation shim tells the gate (gate.cancel) when the abort is
 *      observed; the orphan's later submission meets the fence
 *      (refused_cancelled) and the effect never executes.
 *
 * Run (gate binary must be built; deps: npm ci in probes-js/):
 *   cd soundgate && cargo build --release
 *   cd ../probes-js && node e2e_langgraph_js.mjs
 */
import { spawn } from "node:child_process";
import net from "node:net";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  Annotation,
  Command,
  END,
  interrupt,
  MemorySaver,
  START,
  StateGraph,
} from "@langchain/langgraph";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BIN = path.resolve(HERE, "..", "soundgate", "target", "release", "soundgate");
const HOST = "127.0.0.1";
const PORT = 8798;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const EXECUTED = []; // the demo's effect log: what actually ran

/* ------------------------- the integration surface ------------------------
 * The whole integration contract, same shape as the Python GateClient:
 * submit the effect's identity, perform the effect only on "release". */
class GateClient {
  constructor(host = HOST, port = PORT) {
    this.sock = net.connect(port, host);
    this.buf = "";
    this.waiters = [];
    this.sock.on("data", (d) => {
      this.buf += d.toString("utf8");
      let i;
      while ((i = this.buf.indexOf("\n")) >= 0) {
        const line = this.buf.slice(0, i);
        this.buf = this.buf.slice(i + 1);
        const w = this.waiters.shift();
        if (w) w(JSON.parse(line).verdict);
      }
    });
    this.ready = new Promise((res, rej) => {
      this.sock.once("connect", res);
      this.sock.once("error", rej);
    });
  }
  _call(req) {
    return new Promise((resolve) => {
      this.waiters.push(resolve);
      this.sock.write(JSON.stringify(req) + "\n");
    });
  }
  async mediatedEffect(runId, effectKey, doEffect, needsApproval = false) {
    const v = await this._call({
      op: "submit", run_id: runId, effect_key: effectKey,
      needs_approval: needsApproval,
    });
    if (v === "release") doEffect();
    return v;
  }
  decide(runId, effectKey, approved) {
    return this._call({ op: "decide", run_id: runId, effect_key: effectKey, approved });
  }
  cancel(runId) {
    return this._call({ op: "cancel", run_id: runId });
  }
  close() { this.sock.end(); }
}

const State = Annotation.Root({
  note: Annotation({ reducer: (_p, n) => n, default: () => "" }),
});

async function main() {
  const srv = spawn(BIN, [`${HOST}:${PORT}`], { stdio: ["ignore", "ignore", "ignore"] });
  await sleep(400);
  const gate = new GateClient();
  await gate.ready;
  const results = [];
  try {
    // ---------------- A. sibling leak repaired (twin of J1/J1r) ----------
    {
      const run = "jsA";
      const graph = new StateGraph(State)
        .addNode("gate_node", async () => {
          const decision = interrupt({ question: "approve the run's actions?" });
          return { note: `gate:${JSON.stringify(decision)}` };
        })
        .addNode("sibling", async () => {
          const v = await gate.mediatedEffect(
            run, "sibling_email",
            () => EXECUTED.push("sibling_email"),
            true, // needs_approval
          );
          return { note: `sibling:${v}` };
        })
        .addEdge(START, "gate_node")
        .addEdge(START, "sibling")
        .addEdge("gate_node", END)
        .addEdge("sibling", END)
        .compile({ checkpointer: new MemorySaver() });

      const cfg = { configurable: { thread_id: "tA" } };
      const first = await graph.invoke({ note: "" }, cfg);
      const paused = Boolean(first.__interrupt__ && first.__interrupt__.length);
      const duringPause = EXECUTED.length; // must be 0: sibling held
      const rej = await gate.decide(run, "sibling_email", false); // human REJECTS
      await graph.invoke(new Command({ resume: "reject" }), cfg);
      const aOk = paused && duringPause === 0 && rej === "refused_rejected"
        && EXECUTED.length === 0;
      results.push(aOk);
      console.log(
        `A sibling-leak repaired   : paused=${paused} ` +
        `effects_during_pause=${duringPause} reject=${rej} ` +
        `effects_total=${EXECUTED.length} -> ` +
        (aOk ? "HELD+REFUSED (repaired)" : "LEAK"));
    }

    // ---------------- B. replay repaired (twin of J2) ---------------------
    {
      const run = "jsB";
      let nodeRuns = 0;
      const verdicts = [];
      const graph = new StateGraph(State)
        .addNode("charge_then_ask", async () => {
          nodeRuns += 1;
          const v = await gate.mediatedEffect(
            run, "charge_card", () => EXECUTED.push("charge_card"));
          verdicts.push(v);
          const decision = interrupt({ question: "charged; continue?" });
          return { note: `b:${JSON.stringify(decision)}:${v}` };
        })
        .addEdge(START, "charge_then_ask")
        .addEdge("charge_then_ask", END)
        .compile({ checkpointer: new MemorySaver() });

      const cfg = { configurable: { thread_id: "tB" } };
      await graph.invoke({ note: "" }, cfg);
      await graph.invoke(new Command({ resume: "continue" }), cfg); // re-executes node body
      const charges = EXECUTED.filter((e) => e === "charge_card").length;
      const bOk = nodeRuns === 2 && charges === 1
        && verdicts.length === 2
        && verdicts[0] === "release" && verdicts[1] === "refused_duplicate";
      results.push(bOk);
      console.log(
        `B replay repaired         : node_body_ran=${nodeRuns}x ` +
        `verdicts=${JSON.stringify(verdicts)} effect_executed=${charges}x -> ` +
        (bOk ? "EXACTLY-ONCE (repaired)" : "DOUBLE-EXEC"));
    }

    // ---------------- C. AbortSignal orphan fenced (twin of J3) -----------
    {
      const run = "jsC";
      const zombieVerdict = [];
      const graph = new StateGraph(State)
        .addNode("worker", async () => {
          await sleep(600); // promise chain: not interruptible by AbortSignal
          zombieVerdict.push(await gate.mediatedEffect(
            run, "post_webhook", () => EXECUTED.push("post_webhook")));
          return { note: "done" };
        })
        .addEdge(START, "worker")
        .addEdge("worker", END)
        .compile({ checkpointer: new MemorySaver() });

      const controller = new AbortController();
      const cfg = { configurable: { thread_id: "tC" }, signal: controller.signal };
      const running = graph.invoke({ note: "" }, cfg);
      await sleep(150);
      controller.abort(); // user hits stop on the framework's native surface
      let abortSeen = false;
      try { await running; } catch { abortSeen = true; }
      await gate.cancel(run); // the cancellation shim informs the gate
      const effectAtCancel = EXECUTED.includes("post_webhook");
      await sleep(800); // let the orphaned promise fire against the fence
      const cOk = abortSeen && !effectAtCancel
        && zombieVerdict.length === 1 && zombieVerdict[0] === "refused_cancelled"
        && !EXECUTED.includes("post_webhook");
      results.push(cOk);
      console.log(
        `C orphan fenced           : abort_seen=${abortSeen} ` +
        `zombie_verdict=${JSON.stringify(zombieVerdict)} ` +
        `effect_executed=${EXECUTED.includes("post_webhook")} -> ` +
        (cOk ? "FENCED (repaired)" : "ORPHAN"));
    }

    const ok = results.every(Boolean);
    const lg = (await import("@langchain/langgraph/package.json", { with: { type: "json" } }))
      .default.version;
    console.log(
      `\nE-E2E-JS (real @langchain/langgraph==${lg}, node ${process.version}): ` +
      (ok ? "3/3 violations repaired in situ" : "FAILURE"));
    if (!ok) process.exitCode = 1;
  } finally {
    gate.close();
    srv.kill();
  }
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
