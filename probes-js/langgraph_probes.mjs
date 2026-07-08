/**
 * langgraph_probes.mjs -- keyless control-plane probes for LangGraph.js.
 * Cross-language column: same graph topologies as the Python FW-A probes,
 * on the JavaScript runtime, to separate framework semantics from
 * host-language concurrency semantics.
 *
 * Host-language fact that motivates this column: JavaScript promises are not
 * cancellable. Where Python asyncio can cancel a pure-async node at an await
 * point (making the Python "pure async" cancellation contrast clean),
 * a JS node's in-flight promise chain cannot be interrupted; AbortSignal only
 * makes the CALLER stop waiting. The sync-thread / pure-async split of the
 * Python probes therefore does not exist here (marked n/a by construction).
 *
 * Violation predicates -- fixed BEFORE first execution:
 *
 *  J1  SIBLING LEAK: fan-out from START to {gate (interrupt()), side_effect}.
 *      Violation: invoke returns with __interrupt__ pending AND the sibling
 *      effect executed before any resume decision.
 *  J1r REJECT-AFTER-EFFECT: resume with Command({resume:false}). Violation:
 *      the effect had already executed (count >= 1 at rejection).
 *  J2  RESUME REPLAY: single node logs an effect BEFORE calling interrupt();
 *      human approves via Command({resume:true}). Violation: effect count >
 *      1 after resume (node re-executed from its top).
 *  J3  ABORT-SIGNAL CANCELLATION: node awaits a 600 ms sleep then logs the
 *      effect; caller aborts at 150 ms via config.signal. Violation: caller
 *      observes the abort, effect had not landed at that moment, and the
 *      effect lands afterward (orphaned promise chain).
 *  J4  ABORT-SIGNAL TIMEOUT: same node under AbortSignal.timeout(200).
 *      Violation: caller observes the timeout abort, effect had not landed,
 *      effect lands afterward.
 *
 * BRUTAL-REVIEWER NOTES (scope limits these probes do NOT escape):
 *  - config.signal is LangGraph.js's documented cancellation surface; J3/J4
 *    test that native surface, not a host-level wrapper. Label accordingly.
 *  - Effects are in-process array appends; the Phase-0 out-of-process sink
 *    upgrade applies here identically.
 *  - Node >= 18 required (AbortSignal.timeout).
 */

import {
  Annotation,
  Command,
  END,
  interrupt,
  MemorySaver,
  START,
  StateGraph,
} from "@langchain/langgraph";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class EventLog {
  constructor() {
    this.events = [];
  }
  log(e) {
    this.events.push(e);
  }
  clear() {
    this.events = [];
  }
  contains(sub) {
    return this.events.some((e) => e.includes(sub));
  }
  count(sub) {
    return this.events.filter((e) => e.includes(sub)).length;
  }
}
const LOG = new EventLog();

const results = [];
function record(name, violation, detail) {
  results.push({ name, violation, detail });
  const tag = violation ? "VIOLATION" : "clean/contrast";
  console.log(`${name.padEnd(32)} -> ${tag}  ${JSON.stringify(detail)}`);
}

const State = Annotation.Root({
  note: Annotation({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
});

// ------------------------------------------------------------- J1 / J1r
async function runJ1() {
  LOG.clear();
  const graph = new StateGraph(State)
    .addNode("gate", async () => {
      LOG.log("gate:before_interrupt");
      const decision = interrupt({ question: "approve?" });
      LOG.log(`gate:resumed_with=${JSON.stringify(decision)}`);
      return { note: "gated" };
    })
    .addNode("side_effect", async () => {
      LOG.log("EFFECT:executed"); // stands in for an email send
      return { note: "effect" };
    })
    .addEdge(START, "gate")
    .addEdge(START, "side_effect")
    .addEdge("gate", END)
    .addEdge("side_effect", END)
    .compile({ checkpointer: new MemorySaver() });

  const cfg = { configurable: { thread_id: "j1" } };
  const first = await graph.invoke({ note: "" }, cfg);
  const paused = Boolean(first.__interrupt__ && first.__interrupt__.length);
  const effectWhilePaused = LOG.contains("EFFECT:executed");
  const traceAtPause = [...LOG.events];
  record("sibling_leak[fan_out]", paused && effectWhilePaused, {
    paused,
    effect_while_paused: effectWhilePaused,
    trace_at_pause: traceAtPause,
  });

  // Human REJECTS:
  // JS API footgun (recorded as a datum): falsy resume payloads such as
  // `false` are rejected as "Received empty Command input"; the rejection
  // decision is therefore carried as a string. Semantics unchanged: the
  // resume value is opaque to the framework.
  await graph.invoke(new Command({ resume: "reject" }), cfg);
  const effectTotal = LOG.count("EFFECT:executed");
  record("reject_after_effect", paused && effectTotal >= 1, {
    effect_total_after_reject: effectTotal,
  });
}

// ------------------------------------------------------------------- J2
async function runJ2() {
  LOG.clear();
  const graph = new StateGraph(State)
    .addNode("act_then_gate", async () => {
      LOG.log("J2_EFFECT:executed");
      const decision = interrupt({ question: "approve?" });
      LOG.log(`gate:resumed_with=${JSON.stringify(decision)}`);
      return { note: "done" };
    })
    .addEdge(START, "act_then_gate")
    .addEdge("act_then_gate", END)
    .compile({ checkpointer: new MemorySaver() });

  const cfg = { configurable: { thread_id: "j2" } };
  const first = await graph.invoke({ note: "" }, cfg);
  const paused = Boolean(first.__interrupt__ && first.__interrupt__.length);
  if (!paused) throw new Error("J2 harness failure: interrupt() did not pause");
  const countAtPause = LOG.count("J2_EFFECT:executed");
  await graph.invoke(new Command({ resume: "approve" }), cfg); // human APPROVES
  const countAfter = LOG.count("J2_EFFECT:executed");
  record("replay[resume_after_approve]", countAfter > 1, {
    paused,
    effect_count_at_pause: countAtPause,
    effect_count_after_approve: countAfter,
  });
}

// ------------------------------------------------------------------- J3
async function runJ3() {
  LOG.clear();
  const graph = new StateGraph(State)
    .addNode("worker", async () => {
      LOG.log("J3:node_started");
      await sleep(600);
      LOG.log("J3_EFFECT:executed_after_delay");
      return { note: "done" };
    })
    .addEdge(START, "worker")
    .addEdge("worker", END)
    .compile({ checkpointer: new MemorySaver() });

  const controller = new AbortController();
  const cfg = { configurable: { thread_id: "j3" }, signal: controller.signal };
  const run = graph.invoke({ note: "" }, cfg);
  await sleep(150); // user cancels mid-node
  controller.abort();
  let abortSeen = false;
  let callerSaw = null;
  try {
    await run;
  } catch (e) {
    callerSaw = e && e.name ? e.name : String(e);
    abortSeen = true;
  }
  const effectAtCancel = LOG.contains("J3_EFFECT");
  await sleep(800);
  const effectAfter = LOG.contains("J3_EFFECT");
  record(
    "cancellation[abort_signal]",
    abortSeen && !effectAtCancel && effectAfter,
    {
      abort_seen: abortSeen,
      caller_saw: callerSaw,
      effect_at_cancel: effectAtCancel,
      effect_after_cancel: effectAfter,
      note: "no sync/async split exists in JS: promises are not cancellable",
    }
  );
}

// ------------------------------------------------------------------- J4
async function runJ4() {
  LOG.clear();
  const graph = new StateGraph(State)
    .addNode("worker", async () => {
      LOG.log("J4:node_started");
      await sleep(800);
      LOG.log("J4_EFFECT:executed_after_delay");
      return { note: "done" };
    })
    .addEdge(START, "worker")
    .addEdge("worker", END)
    .compile({ checkpointer: new MemorySaver() });

  const cfg = {
    configurable: { thread_id: "j4" },
    signal: AbortSignal.timeout(200),
  };
  let timedOut = false;
  let callerSaw = null;
  try {
    await graph.invoke({ note: "" }, cfg);
  } catch (e) {
    callerSaw = e && e.name ? e.name : String(e);
    timedOut = true;
  }
  const effectAtTimeout = LOG.contains("J4_EFFECT");
  await sleep(1000);
  const effectAfter = LOG.contains("J4_EFFECT");
  record(
    "timeout_zombie[abort_timeout]",
    timedOut && !effectAtTimeout && effectAfter,
    {
      caller_saw: callerSaw,
      effect_at_timeout: effectAtTimeout,
      effect_after_timeout: effectAfter,
    }
  );
}

async function main() {
  const pkg = (await import("./node_modules/@langchain/langgraph/package.json", {
    with: { type: "json" },
  })).default;
  console.log(`# FW-F @langchain/langgraph@${pkg.version} (Node ${process.version})\n`);
  await runJ1();
  await runJ2();
  await runJ3();
  await runJ4();
  const v = results.filter((r) => r.violation).length;
  console.log(`\nVIOLATION AXES CONFIRMED: ${v}/${results.length}`);
}

main().catch((e) => {
  console.error("PROBE HARNESS FAILURE:", e);
  process.exit(1);
});
