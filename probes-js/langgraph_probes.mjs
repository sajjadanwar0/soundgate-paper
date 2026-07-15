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

  await graph.invoke(new Command({ resume: "reject" }), cfg);
  const effectTotal = LOG.count("EFFECT:executed");

  record("reject_after_effect", paused && effectTotal >= 1, {
    effect_total_after_reject: effectTotal,
  });
}


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