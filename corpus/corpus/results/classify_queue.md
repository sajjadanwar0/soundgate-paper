# Corpus classification queue -- SET EVERY VERDICT BY HAND

Generated from results/sweep_results.jsonl. Rubric in the script header. Suggestions are heuristic and NOT authoritative; the paper's direct/adjacent/context counts update only after you confirm each.

## 1. [langchain-ai/langgraph#8240](https://github.com/langchain-ai/langgraph/issues/8240)  axis_hint=A1 suggest=A3 state=open
**perf: FuturesDict.on_done re-scans all completed futures on every callback (O(tasks^2) stop-check)**

> ### Summary  `FuturesDict.on_done` (in `langgraph/pregel/_runner.py`) runs once per task completion. It adds the future to `self.done` and then calls `self.should_stop(self.done)`:  ```python def on_done(self, task, fut):     ...     with self.lock:         self.done.add(fut)         self.counter -= 1         if self.counter == 0 or self.should_stop(self.done):   # re-scans the whole set             self.event.set() ```  `should_stop` is `_should_stop_others`, which iterates the set calling `fut.cancelled()` / `fut.exception()` on **every** future (both acquire the future's internal lock). Because `self.done` grows by one each callback, a superstep with `T` parallel tasks does `1 + 2 + ... +

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 2. [langchain-ai/langgraph#8102](https://github.com/langchain-ai/langgraph/issues/8102)  axis_hint=A1 suggest=A1 state=open
**RFC: Pre-execution tool call interception hooks for policy enforcement**

> # RFC: Pre-execution tool call interception hooks for policy enforcement  I am using `StateGraph` + `ToolNode` for production agents, and I keep hitting a gap around pre-execution control over tool calls.  ## Problem  LangGraph routes model tool calls into `ToolNode` (`_run_one` / `_arun_one`) and then executes the selected tool. In practice, there is no simple first-class `before_tool_call` hook with a stable contract to intercept, inspect, and block/modify a call before execution.  Today, the practical options are custom `ToolNode` subclassing and private execution-path overrides, which feels fragile over upgrades.  For teams using `Command`-based routing and `interrupt()` flows, this matt

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 3. [langchain-ai/langgraph#7907](https://github.com/langchain-ai/langgraph/issues/7907)  axis_hint=A1 suggest=A1 state=open
**RFC: Cross-node write-intent registry for parallel graph execution**

> > **Update 2026-05-25**: I've edited this issue to clarify the framing. The original wording made stronger empirical claims ("I've been running an experimental decorator", "~30% of multi-reviewer runs silently dropping 3 of 4 reviews", "we discovered a week later") than I can actually support — the design is from reading the Pregel runtime + `Send` / channel reducer code paths, not from a measured production deployment. The design discussion stands; the specific numbers and personal use-case framing have been removed.  ---  ## Summary  I'd like to gauge interest in a **cross-node write-intent registry** for parallel graph execution that detects *semantic* conflicts between concurrently-sched

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 4. [langchain-ai/langgraph#7844](https://github.com/langchain-ai/langgraph/issues/7844)  axis_hint=A1 suggest=A1 state=open
**Docs safety guidance: auditable final-state receipts for agent completion claims?**

> Hi, I maintain SACP, a small text-first receipt layer for AI agent work: https://github.com/aDragon0707/sacp  I noticed LangGraph emphasizes durable execution, human-in-the-loop review, stateful agents, and long-running workflows. That seems like a natural place for guidance on auditable final-state receipts.  I also saw that this repo's `examples/` directory is archived and points users to the consolidated LangChain docs, so I am opening an issue instead of sending a docs PR to the wrong place.  Would LangGraph docs accept a small safety-oriented section or example about final completion receipts?  The pattern would document:  - what the agent claimed - what evidence supports each claim - w

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 5. [langchain-ai/langgraph#7598](https://github.com/langchain-ai/langgraph/issues/7598)  axis_hint=A1 suggest=A1 state=open
**feat: add graph-level task scheduling policy (this is a feature proposal, not a bug)**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Related Issues / PRs  _No response_  ### Reproduction Steps / Example Code (Python)  ```python # 1. Static prior

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 6. [langchain-ai/langgraph#7417](https://github.com/langchain-ai/langgraph/issues/7417)  axis_hint=A1 suggest=A2 state=open
**Long tool calls (~180s+) silently re-executed from checkpoint on LangGraph Cloud**

> ### Problem  When a tool call takes longer than ~3 minutes on LangGraph Cloud, it gets silently re-dispatched from the last checkpoint while the original is still running. Both the original and the duplicate complete successfully, resulting in 2-3x redundant work and cost.  We're using deepagents' `SubAgentMiddleware`, where the main agent dispatches sub-agents via a `task()` tool that internally calls `subagent.ainvoke()`. These sub-agents are standard LangGraph agents making multiple sequential LLM + tool calls, and they routinely take 3-10 minutes.  ### What we observe  At ~180s after a long tool call starts, duplicate runs appear in the trace with: - Identical tool call arguments (same c

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 7. [langchain-ai/langgraph#6626](https://github.com/langchain-ai/langgraph/issues/6626)  axis_hint=A1 suggest=A1 state=closed
**`interrupt()` calls in parallel tools generate identical IDs, making multi-interrupt resume impossible**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python import asyncio from typing import Annotated, List from uuid import uuid4  from langchain_core.messages import AnyMessage, HumanMessage, AIMessage from langchain_core.tools import t

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 8. [langchain-ai/langgraph#6624](https://github.com/langchain-ai/langgraph/issues/6624)  axis_hint=A1 suggest=A1 state=closed
**ToolNode doesn't collect all interrupts from parallel tool execution**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python #!/usr/bin/env python3 """ Minimal test script to debug parallel interrupts with ToolNode.  This tests whether LangGraph's ToolNode properly collects all interrupts when multiple t

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 9. [langchain-ai/langgraph#6533](https://github.com/langchain-ai/langgraph/issues/6533)  axis_hint=A1 suggest=A2 state=closed
**Interrupt resume values misrouted between tools when using a ToolNode**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python import asyncio import logging import math import random from typing import Annotated, TypedDict  from langchain_core.messages import AIMessage, HumanMessage from langchain_core.too

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 10. [langchain-ai/langgraph#6362](https://github.com/langchain-ai/langgraph/issues/6362)  axis_hint=A1 suggest=A1 state=open
**Interrupts missing in thread_state on self-hosted LangGraph (1.x)**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python import asyncio from uuid import uuid4  from langchain.agents import create_agent from langchain.agents.middleware import HumanInTheLoopMiddleware from langchain_core.tools import t

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 11. [langchain-ai/langgraph#5952](https://github.com/langchain-ai/langgraph/issues/5952)  axis_hint=A1 suggest=A1 state=closed
**Resolved interrupts from nodes executed in parallel keep firing unnecessarily**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python #!/usr/bin/env python3  import asyncio from typing import Annotated, TypedDict from uuid import uuid4  from langgraph.checkpoint.memory import InMemorySaver from langgraph.graph im

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 12. [langchain-ai/langgraph#5710](https://github.com/langchain-ai/langgraph/issues/5710)  axis_hint=A1 suggest=A1 state=closed
**Refactor create_react_agent to use an internal helper**

> ### Privileged issue  - [x] I am a LangGraph maintainer, or was asked directly by a LangGraph maintainer to create an issue here.  ### Issue Content  The internal implementation of create_react_agent has become difficult to work with. We'd like you to refactor it to use a helper class called _AgentBuilder.  The goal of the refactor is to make things more maintainable and easier to understand/read. We do not want any unnecessary abstractions!  Here's a reference design:   ``` Here's a high-level **scaffold-style description** of `_AgentBuilder` suitable for guiding a future implementation:  ---  ### `_AgentBuilder`: Scaffold Overview  The `_AgentBuilder` class is an **internal scaffolding uti

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 13. [langchain-ai/langgraph#5692](https://github.com/langchain-ai/langgraph/issues/5692)  axis_hint=A1 suggest=A1 state=closed
**Refactor create_react_agent to use an internal helper**

> ### Privileged issue  - [x] I am a LangGraph maintainer, or was asked directly by a LangGraph maintainer to create an issue here.  ### Issue Content  The internal implementation of create_react_agent has become difficult to work with. We'd like you to refactor it to use a helper class called _AgentBuilder.  The goal of the refactor is to make things more maintainable and easier to understand/read. We do not want any unnecessary abstractions!  Here's a reference design:   ``` Here's a high-level **scaffold-style description** of `_AgentBuilder` suitable for guiding a future implementation:  ---  ### `_AgentBuilder`: Scaffold Overview  The `_AgentBuilder` class is an **internal scaffolding uti

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 14. [langchain-ai/langgraph#4973](https://github.com/langchain-ai/langgraph/issues/4973)  axis_hint=A1 suggest=A1 state=open
**🚧 LangGraph v1 roadmap – feedback wanted!**

> We're working towards LangGraph v1, and we're looking for input from our user base — you!  This is your chance to help shape the core of LangGraph — especially the low-level `StateGraph` API and related tooling. What we want to hear from you about:  * What parts of LangGraph are confusing or unclear? * What feels unnecessarily complex or boilerplate-heavy? * What's annoying or unintuitive when using `StateGraph`? * What's missing / what features should be top prio?  We'll use this feedback to prioritize changes for v1, including API cleanup, improved documentation, and new features.  Note: We're prioritizing backward compatibility for users and don't plan to make any major breaking changes t

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 15. [langchain-ai/langgraph#4754](https://github.com/langchain-ai/langgraph/issues/4754)  axis_hint=A1 suggest=A3 state=closed
**create_react_agent fails with a Runnable chain supplied as the model when bind_tools gets called**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from typing import (     Any,     Callable,     Dict,     List,     Literal,     Optional,     Sequence,     Type,     Union, )  from langchain_core.callbacks import CallbackManagerForLLMRun from langchain_core.l

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 16. [langchain-ai/langgraph#4671](https://github.com/langchain-ai/langgraph/issues/4671)  axis_hint=A1 suggest=A1 state=closed
**TypeError: unsupported operand type(s) for +: 'NoneType' and 'int' when streaming with stream_mode="messages" in create_react_agent**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from langgraph.errors import GraphRecursionError from langgraph.prebuilt import create_react_agent  from langchain_tavily import TavilySearch tool = TavilySearch(max_results=2)  agent = create_react_agent(     mo

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 17. [langchain-ai/langgraph#4355](https://github.com/langchain-ai/langgraph/issues/4355)  axis_hint=A1 suggest=A1 state=closed
**Unable to update state when using `interrupt` for a HITL implementation**

> ### Checked other resources  - [ ] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python class ConceptInputs(TypedDict):     case_name: str = None     fav_fruit: str = None     fav_book: str = None     total_budget: int = None     additional_instruction: str = None     generated_draft: str = None    

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 18. [langchain-ai/langgraph#4322](https://github.com/langchain-ai/langgraph/issues/4322)  axis_hint=A1 suggest=A1 state=closed
**Pandas Dataframe not handled when checkpointer is used**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from pydantic import BaseModel, Field from typing import Optional from langgraph.checkpoint.memory import MemorySaver  sample_df = pd.DataFrame({"foo": [1, 2, 3]})  # Define subgraph class SubgraphState(BaseModel

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 19. [langchain-ai/langgraph#4028](https://github.com/langchain-ai/langgraph/issues/4028)  axis_hint=A1 suggest=A2 state=closed
**Unable to resume multiple interrupts from a single graph invoke**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python import operator import uuid from typing import Optional, Annotated, List  from langgraph.checkpoint.memory import MemorySaver from langgraph.constants import START, END from langgraph.graph import StateGraph from

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 20. [langchain-ai/langgraph#3875](https://github.com/langchain-ai/langgraph/issues/3875)  axis_hint=A1 suggest=A1 state=closed
**Bug: Error when having multiple nodes, each with a single `interrupt`**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from pprint import pprint import operator from functools import partial from typing import TypedDict, Annotated from uuid import uuid4  from langchain_core.runnables import RunnableConfig from langgraph.checkpoin

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 21. [langchain-ai/langgraph#7065](https://github.com/langchain-ai/langgraph/issues/7065)  axis_hint=A1 suggest=A1 state=open
**Feature: Cryptographic action receipts (AAR) for provable agent execution**

> ## Problem  When LangGraph agents execute multi-step workflows, there's no standardized way to cryptographically prove what happened at each node. Audit logs exist, but they're mutable and unsigned — a compromised system can rewrite history without detection.  For regulated domains (finance, healthcare, legal), this is a blocker. Compliance teams need tamper-proof evidence that Agent X performed Action Y with Input Z at Time T.  ## Proposal: Agent Action Receipt (AAR) Integration  AAR is a lightweight spec for Ed25519-signed receipts that capture agent actions with cryptographic integrity:  ```json {   "receiptId": "uuid",   "agent": "langgraph-node-analyzer",   "action": "analyze_document",

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 22. [langchain-ai/langgraph#8218](https://github.com/langchain-ai/langgraph/issues/8218)  axis_hint=A2 suggest=A2 state=open
**interrupt() inside a tool is reported as a `tool-error` on the tools stream (structured Interrupt lost)**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I searched existing issues and didn't find a duplicate (related but distinct: #8217 covers the `awrap_tool_call` wrapper path). - [x] I reproduced on the latest `main`.  ### Description  When a tool calls `interrupt()` (directly, or via human-in-the-loop tooling), the resulting `GraphInterrupt` is reported on the `tools` stream channel as a **`tool-error`** event, with `message=str(error)`.  This is wrong in two ways:  1. **A pause is misclassified as a failure.** `GraphInterrupt` is a subclass of `GraphBubbleUp` - it is control flow (the run pauses and can be resumed), not a tool error. 2. **The structured payload

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 23. [langchain-ai/langgraph#8112](https://github.com/langchain-ai/langgraph/issues/8112)  axis_hint=A2 suggest=A2 state=open
**langgraph-runtime-inmem generates duplicate SSE ids for resumable streams within the same millisecond**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I searched existing issues for `_generate_ms_seq_id`, `For simplicity, always use sequence 0`, `stream_resumable duplicate id`, and `Last-Event-ID langgraph-runtime-inmem`, and did not find this exact issue. - [x] I believe this is in `langgraph-runtime-inmem`, not application code.  ### Package versions observed  ```text langgraph==1.0.9 langgraph-api==0.7.103 langgraph-runtime-inmem==0.27.4 ```  ### Description  `langgraph-runtime-inmem` can emit duplicate SSE event IDs for resumable run streams when multiple stream events are published in the same millisecond.  The in-memory runtime generates stream IDs with:  `

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 24. [langchain-ai/langgraph#8039](https://github.com/langchain-ai/langgraph/issues/8039)  axis_hint=A2 suggest=A2 state=open
**durability="sync": put_writes/put persistence order is unenforced, so post-crash recovery (replay vs re-execute) is host-dependent**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Related Issues / PRs  #7417, #7780 -- searched open and closed issues before filing. Both are distinct defects (

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 25. [langchain-ai/langgraph#8026](https://github.com/langchain-ai/langgraph/issues/8026)  axis_hint=A2 suggest=A2 state=open
**[Feature Request]: Add a high-level ApprovalNode for Human-in-the-Loop workflows**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Related Issues / PRs  ### Problem Currently, building Human-in-the-Loop (HITL) workflows in LangGraph requires m

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 26. [langchain-ai/langgraph#7895](https://github.com/langchain-ai/langgraph/issues/7895)  axis_hint=A2 suggest=A2 state=open
**Proposal: production HITL patterns example notebook**

> ## Motivation  `examples/human_in_the_loop/` currently has one notebook ([`wait-user-input.ipynb`](https://github.com/langchain-ai/langgraph/blob/main/examples/human_in_the_loop/wait-user-input.ipynb)) that demonstrates the basic `interrupt()` + `Command(resume=...)` pattern with terminal input.  That pattern is great for dev but breaks in production behind a load balancer:  - Worker restarts kill in-flight approvals (in-process `MemorySaver`) - No channel abstraction (the `interrupt()` payload is a dict — Slack / email / dashboard implementation is on the user) - No idempotency (duplicate `Command(resume=...)` calls both succeed; docs warn that code before `interrupt()` re-executes on resum

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 27. [langchain-ai/langgraph#7780](https://github.com/langchain-ai/langgraph/issues/7780)  axis_hint=A2 suggest=A2 state=open
**[BUG] Interrupt() in a loop will cause extra resumes**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Related Issues / PRs  _No response_  ### Reproduction Steps / Example Code (Python)  ```python from typing impor

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 28. [langchain-ai/langgraph#7714](https://github.com/langchain-ai/langgraph/issues/7714)  axis_hint=A2 suggest=A2 state=open
**LangGraph checkpoint serialization produces 85% storage bloat and 37.8% token overhead with no opt-out path - reproducible with drop-in fix**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Related Issues / PRs  - langchain-ai/langchain #36764 - Token-efficient serialization for agent message passing 

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 29. [langchain-ai/langgraph#7209](https://github.com/langchain-ai/langgraph/issues/7209)  axis_hint=A2 suggest=A1 state=open
**How to add CLI orchestration layer on top of LangGraph agents?**

> ## Context  I've been building workflows where LangGraph handles the agent logic (state machines, routing, memory) but I needed a way to **orchestrate multiple LangGraph-based agents from a single CLI** — queue tasks, track state, retry failures, and coordinate agents via messaging.  ## The Problem  When running 3+ LangGraph agents in parallel: - Which agent is handling which task? - What happens when one crashes? - How do agents hand off context to each other? - How do you enforce a review step before marking a task complete?  I ended up building **ORCH** to solve this — a CLI runtime that wraps any agent (including LangGraph apps) in a typed task queue with a validated state machine:  ``` 

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 30. [langchain-ai/langgraph#7201](https://github.com/langchain-ai/langgraph/issues/7201)  axis_hint=A2 suggest=A2 state=open
**Add restart-safety coverage for put_writes idempotency**

> Problem The shared conformance suite verifies duplicate `put_writes` calls within one saver instance, but it does not currently protect the retry-safe contract across saver restarts, which is the operational case users hit after process or network failure.  Why now `put_writes` is the pending-write boundary for resumed graphs. A restart-specific regression would not be caught by the existing `test_put_writes_idempotent` coverage even though the runtime contract is supposed to survive retries.  Evidence packet - Commit under test: `0f2478cecbd55de8beeb22f87dce5dbafd9ace78` - Runtime: macOS 15.3 / Darwin 25.3.0 arm64, Python `3.14.0` - Relevant codepaths:   - `libs/checkpoint-conformance/langg

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 31. [langchain-ai/langgraph#6956](https://github.com/langchain-ai/langgraph/issues/6956)  axis_hint=A2 suggest=A2 state=open
**`get_state().next` is empty after a node calls `interrupt()` twice**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Reproduction Steps / Example Code (Python)  ```python from langgraph.checkpoint.memory import InMemorySaver from

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 32. [langchain-ai/langgraph#6792](https://github.com/langchain-ai/langgraph/issues/6792)  axis_hint=A2 suggest=A2 state=open
**Resuming after interrupt doesn't reuse prior task outputs when interrupt is in subgraph**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Reproduction Steps / Example Code (Python)  ```python from langgraph.func import entrypoint, task from langgraph

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 33. [langchain-ai/langgraph#6731](https://github.com/langchain-ai/langgraph/issues/6731)  axis_hint=A2 suggest=A2 state=closed
**LangGraph [1.0.6] Bug - Agent infinite looping until recursion limit error is hit**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python async def _init_agent(self, llm_parameters: LLMParameters) -> CompiledStateGraph:         """         Initialize the agent instance.          Args:             llm_parameters: Para

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 34. [langchain-ai/langgraph#6663](https://github.com/langchain-ai/langgraph/issues/6663)  axis_hint=A2 suggest=A2 state=closed
**resume from the same interrupt using different values**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from typing import TypedDict from langgraph.graph import StateGraph, END, START from langgraph.types import Command, interrupt from langgraph.checkpoint.memory import InMemorySaver

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 35. [langchain-ai/langgraph#6064](https://github.com/langchain-ai/langgraph/issues/6064)  axis_hint=A2 suggest=A2 state=open
**Sub Agent sends back to starting agent after handoff even if it is waiting on further responses to finish it task from user**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python """Define a generalized multi-agent system with specialized agents and handoffs."""  from typing import Annotated from langchain_core.tools import tool, InjectedToolCallId from lan

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 36. [langchain-ai/langgraph#6040](https://github.com/langchain-ai/langgraph/issues/6040)  axis_hint=A2 suggest=A2 state=closed
**E11000 duplicate key error collection : checkpoint_writes_aio index**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python # 1. Setup AsyncMongoDBSaver checkpointer  from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver  checkpoint_memory = AsyncMongoDBSaver(     client=db.client,      db_name

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 37. [langchain-ai/langgraph#5672](https://github.com/langchain-ai/langgraph/issues/5672)  axis_hint=A2 suggest=A3 state=open
**Run Cancellation Causes Loss of Streamed State Not Yet Persisted as a Checkpoint**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [ ] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python # Minimal Example  # Start a streaming LangGraph run for chunk in graph.stream(input, config, stream_mode="values"):     process_streamed_value(chunk)     if should_cancel():      

suggestion: **direct?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 38. [langchain-ai/langgraph#4985](https://github.com/langchain-ai/langgraph/issues/4985)  axis_hint=A2 suggest=A2 state=open
**get_state values is not updated  in stream_mode="values". Reproducible rate 1/10.**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from time import sleep from typing_extensions import TypedDict from langgraph.graph import StateGraph, START, END from langgraph.types import Command, interrupt from langgraph.checkpoint.memory import MemorySaver

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 39. [langchain-ai/langgraph#4397](https://github.com/langchain-ai/langgraph/issues/4397)  axis_hint=A2 suggest=A2 state=open
**Multiple Tool Results for Single Tool Call with LangGraph Human Approval Flow**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python def routing_node_factory(agent_name, safe, sensitive):   def routing_node(state: GraphState) -> Command:     ai_message = state["messages"][-1]     tool_calls = getattr(ai_message, "tool_calls", []) or []     too

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 40. [langchain-ai/langgraph#7303](https://github.com/langchain-ai/langgraph/issues/7303)  axis_hint=A2 suggest=A2 state=open
**Collaboration: Trust-gated checkpoints and governance nodes for LangGraph**

> ## Summary  We've built a trust-aware governance integration for LangGraph in the [Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit) (MIT, 6,100+ tests). The adapter lives at [packages/agentmesh-integrations/langgraph-trust/](https://github.com/microsoft/agent-governance-toolkit/tree/main/packages/agentmesh-integrations/langgraph-trust).  ## What it provides  | Capability | Description | |---|---| | **Trust-gated checkpoint nodes** | Graph nodes that enforce trust thresholds before proceeding | | **Governance policy nodes** | Inline policy evaluation within graph execution | | **Trust routing** | Route execution paths based on agent trust scores | | **Audit tra

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 41. [langchain-ai/langgraph#4172](https://github.com/langchain-ai/langgraph/issues/4172)  axis_hint=A2 suggest=A2 state=closed
**Human in the loop: Validating human input - while loop example repeated based on number of invocation**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from langgraph.types import interrupt  def human_node(state: State):     """Human node with validation."""     question = "What is your age?"      while True:         answer = interrupt(question)          # Valid

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 42. [langchain-ai/langgraph#1464](https://github.com/langchain-ai/langgraph/issues/1464)  axis_hint=A2 suggest=A2 state=closed
**Before `interrupt_after`, is it necessary to first decide which node (execute the `path` function)?**

> ### Checked other resources  - [X] I added a very descriptive title to this issue. - [X] I searched the [LangGraph](https://langchain-ai.github.io/langgraph/)/LangChain documentation with the integrated search. - [X] I used the GitHub search to find a similar question and didn't find it. - [X] I am sure that this is a bug in LangGraph/LangChain rather than my code. - [X] I am sure this is better as an issue [rather than a GitHub discussion](https://github.com/langchain-ai/langgraph/discussions/new/choose), since this is a LangGraph bug and not a design question.  ### Example Code  ```python from collections.abc import Callable from typing import Annotated, Literal, TypedDict  f

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 43. [langchain-ai/langgraph#8029](https://github.com/langchain-ai/langgraph/issues/8029)  axis_hint=A3 suggest=A3 state=closed
**Event streaming v3 `stream.abort()` doesn't stop subgraphs**

> ### Checked other resources  - [x] This is a bug, not a usage question. - [x] I added a clear and descriptive title that summarizes this issue. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package). - [x] This is not related to the langchain-community package. - [x] I posted a self-contained, minimal, reproducible example. A maintainer can copy it and run it AS IS.  ### Related Issues / PRs  _No response_  ### Reproduction Steps / Example Code (Python)  ```python import asyncio fr

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 44. [langchain-ai/langgraph#7687](https://github.com/langchain-ai/langgraph/issues/7687)  axis_hint=A3 suggest=A2 state=open
**Add: Compliance-aware human-in-the-loop checkpoint example for regulated environments**

> **Gap:** None of the existing `examples/` cover regulated industry requirements — the current `human_in_the_loop/` example demonstrates interrupt/resume but has no compliance gates, risk classification, or audit logging.  **What this adds:** A self-contained example (`examples/compliance_checkpoint/`) for FCA/MiFID II/Basel III environments with: - 4-node pipeline: `analyse → compliance_gate → [human_review] → finalise` - `interrupt()` / `Command(resume=...)` for human escalation — graph pauses and resumes with full state preserved - Automatic escalation when AI confidence < 0.70 or risk is HIGH/CRITICAL - Hard FCA sanctions block (auto-reject, bypasses human review) - Append-only audit trai

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 45. [langchain-ai/langgraph#7412](https://github.com/langchain-ai/langgraph/issues/7412)  axis_hint=A3 suggest=A1 state=open
**fix(prebuilt): Default handle_tool_errors doesn't catch tool execution errors in parallel calls**

> ## Description  When `ToolNode` executes multiple tool calls in parallel using `asyncio.gather` (async) or `executor.map` (sync), the default error handler only catches `ToolInvocationError` (invalid arguments from the model). If a tool raises any other exception during execution (e.g. `ValueError`, `requests.HTTPError`, `TimeoutError`), the exception propagates through `asyncio.gather`, which discards results from sibling tool calls that already completed successfully.  ## How it happens  The default handler at `libs/prebuilt/langgraph/prebuilt/tool_node.py`, lines 381-389:  ```python def _default_handle_tool_errors(e: Exception) -> str:     if isinstance(e, ToolInvocationError):         re

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 46. [langchain-ai/langgraph#6367](https://github.com/langchain-ai/langgraph/issues/6367)  axis_hint=A3 suggest=A1 state=open
**AsyncPostgresStore cleanup leaves pending background batch tasks causing "Task was destroyed" warnings**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python import asyncio from langgraph.store.postgres.aio import AsyncPostgresStore  async def reproduce_bug():     """     Minimal reproducible example demonstrating the background task cl

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 47. [langchain-ai/langgraph#6341](https://github.com/langchain-ai/langgraph/issues/6341)  axis_hint=A3 suggest=A3 state=closed
**Python dependencies not getting installed when using langgraph up**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python clone https://github.com/langchain-ai/new-langgraph-project  Add      "langchain-google-genai>=2.1.9,<3.0.0", to dependencies  Add from langchain_google_genai import ChatGoogleGene

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 48. [langchain-ai/langgraph#5682](https://github.com/langchain-ai/langgraph/issues/5682)  axis_hint=A3 suggest=A3 state=open
**Can not stop sub graph when asyncio.CancelledError occurred**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python async def call_subgraph(state, config):     output = await subgraph.ainvoke(         input=state,         config=config,     )     messages = output["messages"]     messages = mess

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 49. [langchain-ai/langgraph#5675](https://github.com/langchain-ai/langgraph/issues/5675)  axis_hint=A3 suggest=A3 state=open
**AsyncPostgresSaver  consistently fails with psycopg.AsyncPipeline [BAD] / psycopg.OperationalError: consuming input failed: SSL connection has been closed unexpectedly**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use the LangChain Forum (https://forum.langchain.com/). - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python import asyncio import operator import os from typing import Annotated, TypedDict  from dotenv import load_dotenv from langchain_core.messages import AnyMessage, HumanMessage from l

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 50. [langchain-ai/langgraph#4996](https://github.com/langchain-ai/langgraph/issues/4996)  axis_hint=A3 suggest=A3 state=closed
**TypeError: 'NoneType' object is not callable**

> **TypeError: 'NoneType' object is not callable** File "/workspace/.venv/lib/python3.12/site-packages/langgraph/pregel/runner.py", line 108, in on_done self.callback()(task, exception(fut))   This seems to happen when the callback is set to `None` or when `self.callback()` returns `None`, but the code does not check for this before calling it.  Additionally, I noticed that even after the main handler is cancelled (due to client disconnect), langgraph's internal retry logic (e.g., `arun_with_retry`) may still be running. When these retry or sub-tasks finish, their completion callback may already be set to `None`, resulting in the above TypeError in the logs.   Example log:  ```python handle: <

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 51. [langchain-ai/langgraph#4218](https://github.com/langchain-ai/langgraph/issues/4218)  axis_hint=A3 suggest=A3 state=closed
**blockbuster causes blocking error via tiktoken in async context with latest langgraph-api**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python async def retrieve_relevant_docs(state: ChatState, config: RunnableConfig) -> dict:     """Retrieve relevant documents based on the latest user message."""     #configurable = ChatConfigurable.from_runnable_confi

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 52. [langchain-ai/langgraph#3716](https://github.com/langchain-ai/langgraph/issues/3716)  axis_hint=A3 suggest=A3 state=open
**langgraph-checkpoint-postgres (psycopg.OperationalError: sending query and params failed: SSL error: bad length) encountered across multiple version**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from psycopg import Connection from psycopg_pool import ConnectionPool from psycopg.rows import dict_row from langgraph.checkpoint.postgres import PostgresSaver  connection_kwargs = {"autocommit": True, "prepare_

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 53. [langchain-ai/langgraph#3538](https://github.com/langchain-ai/langgraph/issues/3538)  axis_hint=A3 suggest=A3 state=closed
**ToolNode not working. TypeError: Tool search returned unexpected type: <class 'str'>**

> ### Checked other resources  - [x] This is a bug, not a usage question. For questions, please use GitHub Discussions. - [x] I added a clear and detailed title that summarizes the issue. - [x] I read what a minimal reproducible example is (https://stackoverflow.com/help/minimal-reproducible-example). - [x] I included a self-contained, minimal example that demonstrates the issue INCLUDING all the relevant imports. The code run AS IS to reproduce the issue.  ### Example Code  ```python from typing import Literal  from langchain_anthropic import ChatAnthropic from langchain_core.tools import tool from langgraph.checkpoint.memory import MemorySaver from langgraph.graph import END, START, StateGra

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 54. [langchain-ai/langgraph#2003](https://github.com/langchain-ai/langgraph/issues/2003)  axis_hint=A3 suggest=A3 state=closed
**DOC: ValidationError in LangGraph Customer Support Bot Example**

> ### Issue with current documentation:  This Example: https://github.com/langchain-ai/langgraph/blob/main/docs/docs/tutorials/customer-support/customer-support.ipynb  Does not work, starting from `Part 2` Example Conversation  ![Screenshot at 2024-10-04 11-51-48](https://github.com/user-attachments/assets/f4fa8feb-f9da-4b5d-82f6-182028bd4320)  Error: ``` --------------------------------------------------------------------------- ValidationError                           Traceback (most recent call last) Cell In[18], [line 25](vscode-notebook-cell:?execution_count=18&line=25)      [21](vscode-notebook-cell:?execution_count=18&line=21) for question in tutorial_questions:      [22](v

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 55. [langchain-ai/langgraph#1866](https://github.com/langchain-ai/langgraph/issues/1866)  axis_hint=A3 suggest=A3 state=closed
**Intermittent issue when using SqliteSaver- TypeError: Object of type SecretStr is not serializable**

> ### Checked other resources  - [X] I added a very descriptive title to this issue. - [X] I searched the LangChain documentation with the integrated search. - [X] I used the GitHub search to find a similar question and didn't find it. - [X] I am sure that this is a bug in LangChain rather than my code. - [X] The bug is not resolved by updating to the latest stable version of LangChain (or the specific integration package).  ### Example Code  Have not been able to identify a minimal example to recreate this. It seems random.  ``` import sqlite3 from langgraph.checkpoint.sqlite import SqliteSaver from langgraph.graph import StateGraph  class State(TypedDict):     pth:Path     item:str

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 56. [langchain-ai/langgraph#1069](https://github.com/langchain-ai/langgraph/issues/1069)  axis_hint=A3 suggest=A3 state=closed
**BadRequestError with create_react_agent, tavily tool and ChatOpenAI model**

> ### Checked other resources  - [X] I added a very descriptive title to this issue. - [X] I searched the [LangGraph](https://langchain-ai.github.io/langgraph/)/LangChain documentation with the integrated search. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph/LangChain rather than my code. - [x] I am sure this is better as an issue [rather than a GitHub discussion](https://github.com/langchain-ai/langgraph/discussions/new/choose), since this is a LangGraph bug and not a design question.  ### Example Code  ```python from langchain_community.tools.tavily_search import TavilySearchResults from langchain_cor

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 57. [langchain-ai/langgraph#740](https://github.com/langchain-ai/langgraph/issues/740)  axis_hint=A3 suggest=A3 state=closed
**langgraph.errors.InvalidUpdateError: Must write to at least one of ['input', 'plan', 'past_steps', 'response']**

> ### Checked other resources  - [X] I added a very descriptive title to this issue. - [X] I searched the [LangGraph](https://langchain-ai.github.io/langgraph/)/LangChain documentation with the integrated search. - [X] I used the GitHub search to find a similar question and didn't find it. - [X] I am sure that this is a bug in LangGraph/LangChain rather than my code. - [X] I am sure this is better as an issue [rather than a GitHub discussion](https://github.com/langchain-ai/langgraph/discussions/new/choose), since this is a LangGraph bug and not a design question.  ### Example Code  ```python async def execute_step(state: PlanExecute):     objective = state["input"]     task = state["plan"][

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 58. [langchain-ai/langgraph#7313](https://github.com/langchain-ai/langgraph/issues/7313)  axis_hint=A4 suggest=A4 state=closed
**Update recursion limit magic number and explore changing to a sentinel value**

> LangGraph uses a magical number of 10_000 for recursion limit.   If recursion limit is set to 10_000 it may be reset to 25 during merging of configs (25 is another default value)  We'll change it to 10_103 in the immediate future, but it ideally would be a sentinel.  The magic number should actually be a sentinel so we should figure out how to fix that properly

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 59. [langchain-ai/langgraphjs#1223](https://github.com/langchain-ai/langgraphjs/issues/1223)  axis_hint=A1 suggest=A1 state=closed
**Intermediate Messages Not Output Until All Interrupts Are Resolved in a Single Graph**

> In LangGraph, when a single graph contains multiple interrupts within a ReAct agent node, intermediate messages added to the state are not emitted via graph.stream (using stream_mode="updates") until all interrupts are resolved.  **Context**  - _Setup_: Multiple ReAct agents, each with different tools, managed by a LangGraph supervisor. - _Issue_: Some tools bound to a ReAct agent trigger interrupts for user accept/decline actions. When multiple interrupted tools are called within a single agent, intermediate messages are not streamed until the last interrupt is resolved. - _Example_: When streaming a query with agent.stream, the supervisor delegates to Agent 1, which calls three interrupted

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 60. [langchain-ai/langgraphjs#1141](https://github.com/langchain-ai/langgraphjs/issues/1141)  axis_hint=A1 suggest=A1 state=open
**[bug] Unexpected parallel node execution scheduled in graph with multiple interrupts.**

> Given my graph has the shape illustrated in the image below.  ![Image](https://github.com/user-attachments/assets/df4407a4-9f7b-4f04-99b5-5a634ad85a36)  You can see that node outlined in blue make async calls to LLM and nodes outlined in yellow throw an interrupt like follows  ```typescript async function humanInput(state: typeof ConversationGraphState.State) {     const humanInput = interrupt('Waiting for human input...');      debug?.(`received humanInput: ${JSON.stringify(humanInput, null, 2)}`);      const humanMessage = createHumanMessage(       state,       humanInput.content,       humanInput.externalUserId,       humanInput.messageId,     );      return {       messages: [humanMessag

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 61. [langchain-ai/langgraphjs#992](https://github.com/langchain-ai/langgraphjs/issues/992)  axis_hint=A1 suggest=A1 state=open
**Feature: interruptible tool handler functions**

> Per #975, there are way too many complex concepts to understand if you want to implement a human-in-the-loop process for approving tool calls, especially in the case when you want to allow parallel tool calls _and_ execute all approved tool calls (as opposed to a denial of one call blocking execution of all parallel calls on the `AIMessage`).  It would be so much nicer if user code could simply call `interrupt` from within tool handler functions. Doing this today requires extra steps (e.g. fanning out individual tool calls to `ToolNode`), as otherwise you'll repeat the execution of all previously-approved tool calls on every resume.  A better approach (credit to @hinthornw for the idea) woul

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 62. [langchain-ai/langgraphjs#975](https://github.com/langchain-ai/langgraphjs/issues/975)  axis_hint=A1 suggest=A1 state=closed
**bug: BaseChatModel.invoke errors with a null chatMessage**

> The following error gets output upon a `graph.invoke` after a node in which there was an `interrupt`:  ``` file:///Users/user/code/foobar/node_modules/@langchain/core/dist/language_models/chat_models.js:64         return chatGeneration.message;                               ^  TypeError: Cannot read properties of undefined (reading 'message')     at ChatOpenAI.invoke (file:///Users/user/code/foobar/node_modules/@langchain/core/dist/language_models/chat_models.js:64:31)     at process.processTicksAndRejections (node:internal/process/task_queues:105:5)     at async RunnableCallable.agentNode [as func] (file:///Users/user/code/foobar/cqrsAgent-2.js:48:20)     at async RunnableCallable.invoke (f

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 63. [langchain-ai/langgraphjs#536](https://github.com/langchain-ai/langgraphjs/issues/536)  axis_hint=A2 suggest=A2 state=open
**Feature Request: Support for State Schema Versioning & Migration in LangGraph.js**

> ### Background  Today LangGraph allows me to persist application state via Checkpointers and Stores. Once the application is deployed to real users, you can expect that a history of persisted checkpoints will accumulate. However, LangGraph currently provides no built-in functionality for detecting or managing incompatible changes in the structure of this state over time.  As applications mature, it's common for the structure of the state to evolve. These changes can range from adding new fields, changing field types, or even restructuring objects. These changes may cause older persisted states to become incompatible with newer versions of the application, leading to failures when resumin

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 64. [langchain-ai/langgraphjs#792](https://github.com/langchain-ai/langgraphjs/issues/792)  axis_hint=A2 suggest=A2 state=closed
**Unexpected Behavior: Interrupt() when invoked for the second time, failed to wait for the user input**

> **Description** I am using `interrupt` function inside a subgraph, the first time it works as expected, it terminates the graph execution and I can type text in the console. But after I resume the graph and call `interrupt` for the second (or more) time, it returns the same previously cached value. So it does not work as expected. When I remove the subgraph and implement the same logic inside parent graph, it works fine, so I think it is a bug, and also I found some discussions here on Github explaining this behavior and a way to fix it, hope this helps!  https://github.com/langchain-ai/langgraph/issues/3072 https://github.com/langchain-ai/langgraph/compare/main...vigneshmj1997:langgraph:int

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 65. [langchain-ai/langgraphjs#2446](https://github.com/langchain-ai/langgraphjs/issues/2446)  axis_hint=A3 suggest=A3 state=open
**langgraphjs-api image exits with code 1 on graceful SIGTERM, sends signal twice**

> ## Summary  When a container running the `langchain/langgraphjs-api:20` image receives `SIGTERM` (e.g. from `docker stop` or a Kubernetes/ECS pod replacement), it shuts down cleanly — uvicorn shuts down, queue workers finish, remote graphs are shut down, the gRPC client pool closes — but the container exits with code **1** rather than 0. The Go supervisor that's PID 1 also appears to send `SIGTERM` to the Node subprocess **twice**, ~30ms apart.  Empirically the drain itself looks correct; this seems to be a cosmetic issue in the Go supervisor's shutdown path. The exit 1 is misleading to ECS / Kubernetes observability — it causes deploys to look like they failed even when everything drained c

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 66. [langchain-ai/langgraphjs#1692](https://github.com/langchain-ai/langgraphjs/issues/1692)  axis_hint=A3 suggest=A3 state=closed
**Langgraph Postgres and Redis checkpointers break when running in CloudFlare Workers**

> ### Checked other resources  - [x] I added a very descriptive title to this issue. - [x] I searched the LangGraph.js documentation with the integrated search. - [x] I used the GitHub search to find a similar question and didn't find it. - [x] I am sure that this is a bug in LangGraph.js rather than my code. - [x] The bug is not resolved by updating to the latest stable version of LangGraph (or the specific integration package).  ### Example Code  ```typescript // worker/index.ts import { PostgresSaver } from '@langchain/langgraph-checkpoint-postgres'; import { Annotation, END, MessagesAnnotation, START, StateGraph } from '@langchain/langgraph';  export default {   async fetch(req): Promise<R

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 67. [run-llama/llama_index#13925](https://github.com/run-llama/llama_index/issues/13925)  axis_hint=A1 suggest=A1 state=closed
**[Question]:  how to use the llamaindex+vllm correctly?**

> ### Question Validation  - [X] I have searched both the documentation and discord for an answer.  ### Question  I install the llamaindex with the command `pip install llama-index`  and install the vllm `pip install vllm`. The version of vllm is 0.4.2. The version of transformers is 4.40.0. The llamaindex version is 0.10.43  I run the following code from the document ``` from llama_index.llms.vllm import Vllm   llm = Vllm(     model="microsoft/Orca-2-7b",     # tensor_parallel_size=4,     max_new_tokens=100,     vllm_kwargs={"swap_space": 1, "gpu_memory_utilization": 0.5}, )    llm.complete(     ["[INST]You are a helpful assistant[/INST] What is a black hole ?"] )  

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 68. [run-llama/llama_index#10104](https://github.com/run-llama/llama_index/issues/10104)  axis_hint=A1 suggest=A1 state=closed
**[Bug]: Parallel Processing in Ingestion Pipeline**

> ### Bug Description  Setting `num_workers` to anything other than None causes the `IngestionPipeline.run` method to simply hang.    ### Version  0.9.31  ### Steps to Reproduce  `docs=[...]` `splitter = SentenceSplitter(chunk_overlap=0, chunk_size=128)` `model_name = 'sentence-transformers/all-miniLM-L6-v2'` `embed_model = HuggingFaceEmbedding(model_name=model_name, pooling='mean', embed_batch_size=64)` `pipeline = IngestionPipeline(transformations=[splitter, embed_model])` `nodes = pipeline.run(documents=docs, num_workers=os.cpu_count(), show_progress=True)`  ### Relevant Logs/Tracbacks  ```shell There isn't a traceback, the code simply hangs, but when I hit keyboard interrupt we get th

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 69. [run-llama/llama_index#21599](https://github.com/run-llama/llama_index/issues/21599)  axis_hint=A1 suggest=A1 state=closed
**[Question]: how to add human-in-the-loop capability to ReActAgent?**

> ### Question Validation  - [x] I have searched both the documentation and discord for an answer.  ### Question  I would like to add human-in-the-loop capability by extending ReActAgent class. Is it possible to achieve this please?

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 70. [run-llama/llama_index#18842](https://github.com/run-llama/llama_index/issues/18842)  axis_hint=A2 suggest=A2 state=closed
**[Bug]: Resuming AgentWorkflow after receiving InputRequiredEvent**

> ### Bug Description  I'm following the example provided in the [Introducing AgentWorkflow](https://youtu.be/MmiveeGxfX0?si=emLxKsCyhLj84S-s&t=546) video; specifically the "Human in the Loop" section around the 9 minute mark.  At this point in the video, the Context object is restored from a dict after the workflow has been interrupted by an `InputRequiredEvent` and the workflow is resumed using the `HumanResponseEvent`: ``` handler = workflow.run(ctx=restored_ctx) handler.ctx.send_event(      HumanResponseEvent(...) ) ```  However when running this code on v0.12.37, the following error is produced: `llama_index.core.workflow.errors.WorkflowRuntimeError: Error in step 'init_run': Must provide

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 71. [run-llama/llama_index#20210](https://github.com/run-llama/llama_index/issues/20210)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: reactagent freezed in streaming mode**

> ### Bug Description  HI,   I have this problem since I switched from 0.14.5 to 0.14.7 and upgraded ollama to latest (0.12.9).  It s difficult for myself to understand from which one the problem occurs, but I added some interesting debug logs   This is a reactagent with tools.  When the problem has occured I have not received any output from the llm  ### Version  0.14.7  ### Steps to Reproduce  ```python tools = [             FunctionTool.from_defaults(                 fn=orchestrator_tools.add_code_block,                 name="add_code_block",                 description="""Add a code block (function, class, method) at a semantic location."""),          .....]         self.agent = ReActAgent

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 72. [run-llama/llama_index#19811](https://github.com/run-llama/llama_index/issues/19811)  axis_hint=A3 suggest=A2 state=closed
**[Question]: Context management in multi-agent system in HITL**

> ### Question Validation  - [x] I have searched both the documentation and discord for an answer.  ### Question  We have a multi-agent system (agent 1 and agent 2) and a workflow which is included as a tool in agent 2. So, the flow looks like below:  User Request -> Agent 1 (ReAct agent) -> Agent 2 (FunctionAgent) -> CustomWorkflowTool -> Workflow.run(.., ctx=ctx)  Each of these agents and workflows have their own Context (Context -1, Context -2 and Context - 3). I am listening on workflow's events like below:   ``` #agent2's code below, this is similar to how the workflow tool is also calling the actual workflow.run(..) method:  def run(parent_ctx):    resume_ctx = load_ctx()    ctx = resume

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 73. [run-llama/llama_index#19734](https://github.com/run-llama/llama_index/issues/19734)  axis_hint=A3 suggest=A3 state=open
**[Question]: how to make azure open ai async**

> ### Question Validation  - [x] I have searched both the documentation and discord for an answer.  ### Question  ### How can i initialize the azure open ai with async llm call accuratly please help me out   from azure.core.credentials import AzureKeyCredential #from azure.search.documents import SearchClient from azure.search.documents.aio import SearchClient as AsyncSearchClient from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding from llama_index.llms.azure_openai import AzureOpenAI from llama_index.core.settings import Settings from llama_index.core.callbacks import CallbackManager, TokenCountingHandler import tiktoken  from config import (     AZURE_OPENAI_API_VERSION,    

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 74. [run-llama/llama_index#19487](https://github.com/run-llama/llama_index/issues/19487)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: AgentWorkflow Memory not working with Complex prompts**

> ### Bug Description  When passing in complex prompts with nested jsons xml tags and son on LlamaIndex Workflows stops working.  I've tested around and found out that something in the memory is getting lost. For example the user_msg gets added to the memory but then we can't fetch it . So the final payload being sent to the LLM only has the **system_message** and not the **user_msg**  ```` user_message = ChatMessage(     role="user",     blocks=[         TextBlock(             text=f"Analyze this complex error message and extract key information: {json.dumps(complex_content)}"         )     ] ) ````  If i pass in **memory** then it starts working  ````      from llama_index.core.memory import

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 75. [run-llama/llama_index#19446](https://github.com/run-llama/llama_index/issues/19446)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: LlamaIndex Workflow deployment as an MCP only works when invoked by a LlamaIndex agent**

> ### Bug Description  I deployed my LlamaIndex FunctionAgent as an MCP and tried to call it using a LangGraph react agent but it failed. It also failed when I called it with my LlamaIndex agent.  ### Version  0.12.49  ### Steps to Reproduce  Requirements: --- ```     "langchain>=0.3.26",     "langchain-ollama>=0.3.4",     "langchain-openai>=0.3.28",     "langgraph>=0.5.3",     "llama-index>=0.12.49",     "llama-index-llms-ollama>=0.6.2",     "llama-index-llms-openai-like>=0.4.0",     "ipykernel>=6.29.5",     "jupyter>=1.1.1",     "openai>=1.96.1",     "mcp[cli]>=1.11.0",     "langchain-mcp-adapters>=0.1.9",     "llama-index-tools-mcp>=0.2.6",     "ollama>=0.5.1", ```   weather_mcp.py --- ``` 

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 76. [run-llama/llama_index#19198](https://github.com/run-llama/llama_index/issues/19198)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: workflows.errors.WorkflowRuntimeError: Error in step 'run_agent_step': 'NoneType' object has no attribute 'automatic_function_calling_history'**

> ### Bug Description  Hi , i am usiing agent workflows which was running fine all this while but since today i get this error :       i tried updating google gen ai and llamindex libraries but issue persists .   please suggest a fix   ### Version  0.12.43  ### Steps to Reproduce  run agent workflow  ### Relevant Logs/Tracbacks  ```shell Traceback (most recent call last):   File "C:\Users\HP\anaconda3\envs\googleadsrecsys\lib\asyncio\events.py", line 80, in _run     self._context.run(self._callback, *self._args)   File "C:\Users\HP\anaconda3\envs\googleadsrecsys\lib\site-packages\llama_index_instrumentation\dispatcher.py", line 290, in handle_future_result     raise exception   File "C:\Users\

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 77. [run-llama/llama_index#18182](https://github.com/run-llama/llama_index/issues/18182)  axis_hint=A3 suggest=A3 state=closed
**[Question]: Optimizing LlamaIndex Workflow in FastAPI for Asynchronous Streaming and High Availability**

> ### Question Validation  - [x] I have searched both the documentation and discord for an answer.  ### Question  I am using LlamaIndex Workflow in FastAPI to handle RAG queries and would like to implement streaming output using StreamingResponse. However, it seems that Workflow.run() blocks the entire FastAPI process, making other API endpoints unresponsive. How can I optimize the implementation to support asynchronous execution while maintaining high availability for the API?

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 78. [run-llama/llama_index#18073](https://github.com/run-llama/llama_index/issues/18073)  axis_hint=A3 suggest=A4 state=closed
**[Bug]:**

> ### Bug Description  400 Bad Request Due to Invalid Tool Function Name in Llama Index Workflow  ### Version  0.12.23  ### Steps to Reproduce  agent = DocumentResearchAgent(timeout=600, verbose=True) handler = agent.run(     query="Tell me about the srv6 deployment",     tools=[bell_canada_tool], ) async for ev in handler.stream_events():     if isinstance(ev, ProgressEvent):         print(ev.progress) final_result = await handler print("------- Blog post ----------\n", final_result)  ### Relevant Logs/Tracbacks  ```shell **Section 5: SRv6 Deployment Challenges and Considerations** (approx. 300-400 words)  * Discussion of common challenges and considerations when deploying SRv6: 	+ Network co

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 79. [run-llama/llama_index#17728](https://github.com/run-llama/llama_index/issues/17728)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: Workflow still tries to set_result/set_exception when WorkflowHandler is cancelled.**

> ### Bug Description  When WorkflowHandler is cancelled the Workflow background task continues to run until completion and then tries to set the result (success or failure) on the WorkflowHandler future. This results in an unexpected exception getting thrown because you cannot set the result on a cancelled future.  If the workflow is nested inside of an async function which is being awaited on and then gets cancelled by something external like a request handler exceeding a timeout then this cancels the WorkflowHandler, and results in this exception.  ### Version  0.12.15  ### Steps to Reproduce  ``` import asyncio  from llama_index.core.workflow import (     Context,     StartEvent,     StopE

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 80. [run-llama/llama_index#17065](https://github.com/run-llama/llama_index/issues/17065)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: PropertyGraphIndex (Neo4J Aura): PydanticSerializationError: Error calling function `<lambda>`: AttributeError: 'str' object has no attribute  'value'**

> ### Bug Description  Initially I was following these tutorials:  - [Neo4J Graph Store](https://docs.llamaindex.ai/en/stable/examples/index_structs/knowledge_graph/Neo4jKGIndexDemo/) - [Using Qdrant Vector Store](https://docs.llamaindex.ai/en/stable/examples/vector_stores/QdrantIndexDemo/)  - [Llama Index PG Index](https://docs.llamaindex.ai/en/stable/examples/vector_stores/QdrantIndexDemo/) - [Defining a Custom Property Graph Retriever](https://docs.llamaindex.ai/en/stable/examples/property_graph/property_graph_custom_retriever/)   Which was working on Neo4J local free version (running on docker), but when I switched to Neo4J Aura DB (which is the cloud version), I started to get s

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 81. [run-llama/llama_index#14300](https://github.com/run-llama/llama_index/issues/14300)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: RuntimeError: Numpy is not available**

> ### Bug Description  ### Bug Description  I am using llama3 running local on my machine, with a huggingface embedding, with a connection to PostgreeSQL running local as well.  Part of my .env file:  # The provider for the AI models to use. MODEL_PROVIDER=ollama  # The name of LLM model to use. MODEL=llama3  # Name of the embedding model to use. EMBEDDING_MODEL=BAAI/bge-small-en-v1.5  When I start the backend server with the command python main.py, the server runs.  Then, I start the frontend, and after that, I open the interface on localhost.   After sending a message in the chat, I get an error in the frontend, and this error message appears in the terminal:       |   Fi

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 82. [run-llama/llama_index#13495](https://github.com/run-llama/llama_index/issues/13495)  axis_hint=A3 suggest=A3 state=closed
**[Bug]: Streaming with async_response_gen incompatible with FastAPI**

> ### Bug Description  I have a very simple FastAPI endpoint set up to test out streaming tokens back from a context chat engine. As written, the first request correctly streams the content back, but every subsequent request gives me an asyncio error:  ``` got Future <Future pending> attached to a different loop ```  The full stack trace is linked below.  ### Version  llama-index==0.10.36, fastapi==0.104.1  ### Steps to Reproduce  I'm running the above code in a docker container.  With that setup, I cURL `http://localhost:8000/copilot/stream_test?message=Hello` and get a streamed response. If I cURL the endpoint a second time, I get no response and the stack trace above is output by th

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 83. [run-llama/llama_index#21882](https://github.com/run-llama/llama_index/issues/21882)  axis_hint=A4 suggest=A4 state=open
**feat: Governance instrumentation handler for tool/query security (TealTiger integration)**

> A governance callback/instrumentation handler that evaluates deterministic security policies before tool calls and query execution in LlamaIndex pipelines.  I'm building `llamaindex-tealtiger` — a callback handler that integrates [TealTiger](https://github.com/agentguard-ai/tealtiger) governance into LlamaIndex's instrumentation system. It intercepts tool calls, retriever executions, and LLM calls to enforce policy, track cost, and produce structured audit records.  **Proposed API:**  ```python from llamaindex_tealtiger import TealTigerCallback  # Zero-config: observe tool calls, track cost, detect PII (no blocking) query_engine = index.as_query_engine(callbacks=[TealTigerCallback()])  # Wit

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 84. [run-llama/llama_index#20403](https://github.com/run-llama/llama_index/issues/20403)  axis_hint=A4 suggest=A4 state=closed
**[Bug]: Retry policy is completely broken - delay ignored AND attempt counter reset**

> ### Bug Description  # Bug Report: Retry policy is completely broken - delay ignored AND attempt counter reset  ## Description  There are **two bugs** in the workflow retry mechanism that together cause infinite immediate retries:  1. **Bug #1**: The `delay` parameter from retry policy is never applied - retries happen immediately 2. **Bug #2**: The `attempts` counter is discarded when processing retry events - `maximum_attempts` is never reached  ## Environment    - llama-index-core: 0.14.10   - llama-index-workflows: 2.11.5   - Python version: 3.12  ## Expected Behavior  When a step fails, the retry should wait for the specified delay (5 seconds in this case) before retrying.  ## Actual Be

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 85. [microsoft/agent-framework#6910](https://github.com/microsoft/agent-framework/issues/6910)  axis_hint=A1 suggest=A1 state=open
**.NET: Python: [Bug]: AG-UI host loses tool calls when parallel calls require approval**

> ### Description  ## 1. Summary  When a model returns **several tool calls in one turn** and **any of them requires human-in-the-loop approval**, an agent hosted over AG-UI permanently loses every call in the batch except the single one the user approves. The lost calls are never executed and never re-prompted; instead the AG-UI message sanitizer fabricates `"Tool execution skipped …"` results for them — so the model receives false tool results, concludes its calls failed, and re-issues them indefinitely. Auto-approved tools (e.g. `load_skill`, whose approval is supposed to be granted silently by `SkillsProvider.all_tools_auto_approval_rule`) **never execute at all** on this host.  The root c

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 86. [microsoft/agent-framework#4590](https://github.com/microsoft/agent-framework/issues/4590)  axis_hint=A1 suggest=A1 state=closed
**Python: [Bug]: `RUN_FINISHED.interrupt` Only Contains the Last Interrupt When Multiple Tools Need Approval**

> ### Description  **File:** `agent_framework_ag_ui/_run_common.py` · **Line:** 323  **Description**  When an agent calls multiple tools requiring approval in a single turn, each tool correctly emits a `CUSTOM(function_approval_request)` event. However, `RUN_FINISHED.interrupt` only contains the last interrupt — not all of them.  **Root cause**  In `_run_common.py` line 323, `flow.interrupts` is set via assignment, so each new interrupt overwrites the previous one:  ```python # ❌ Current — overwrites on every interrupt flow.interrupts = [{"id": str(confirm_id), "value": {...}}]  # ✅ Fix — accumulate all interrupts flow.interrupts.append({"id": str(confirm_id), "value": {...}}) ```  **Impact** 

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 87. [microsoft/agent-framework#2743](https://github.com/microsoft/agent-framework/issues/2743)  axis_hint=A1 suggest=A1 state=open
**Python: [Python] Inline HIL request and response in executor**

> The HIL requesting and handling pattern is a bit cumbersome:  We first need to call ctx.request_info() then handling the response from another method marked as @response_handler. The callback ends up in another method so that it is not easy to do more things after calling request_info (this forces developers to breakdown their executor logic making complex task much more cumbersome to read and maintain). It would be great to provide another API like response = await ctx.request_info_and_wait_for_response() (just to illustrate, not a good name) so that we could fire HIL event and receive response in one line before proceeding to the next logic. This would be extremely helpful when the main ex

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 88. [microsoft/agent-framework#819](https://github.com/microsoft/agent-framework/issues/819)  axis_hint=A1 suggest=A1 state=closed
**Python: Human in the loop with checkpoint not functioning correctly in stateless API**

> When using a workflow or workflow as agent with checkpoint and human in the loop i get the error: No request found with ID {REQUEST_ID}  This is an example whereby the API should continue if pending_responses_input is not empty ``` python @router.post("/execute/hitl_hil") async def execute_hitl_hil_workflow(request: Dict[str, Any]):     """Execute a custom workflow with specified agent sequence"""     user_question = request.get("user_question") or request.get("userQuestion")            if not user_question:         raise HTTPException(             status_code=status.HTTP_400_BAD_REQUEST,             detail="user_question is required"         )              context = request.get("context", {

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 89. [microsoft/agent-framework#6894](https://github.com/microsoft/agent-framework/issues/6894)  axis_hint=A1 suggest=A2 state=open
**Python: [Bug]: AG-UI: 'No tool output found' on Foundry provider**

> ### Description  **With CopilotKit and Foundry provider ...**  When an approval-gated tool (e.g. `microsoft_docs_search`, `approval_mode="always_require"`) is surfaced as an AG-UI `confirm_changes` human-in-the-loop card and the user clicks **Approve**, the backend **rejects the approval** with:  ``` WARNING:agent_framework_ag_ui._agent_run:Rejected approval response id=call_MPgkkd1maUPTs4ToqH4Pj7ja:     no matching pending approval request ```  The gated tool then never executes. Two symptoms follow from that single failure:  1. **UI:** the tool chip is stuck on **"Running"** forever (no result ever arrives). 2. **Backend crash on the next model call:**     ```    agent_framework.exceptions

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 90. [microsoft/agent-framework#2903](https://github.com/microsoft/agent-framework/issues/2903)  axis_hint=A1 suggest=A1 state=closed
**Python: AzureAIAgentClient creates new thread on each invocation in Magentic workflows, losing conversation context**

> ## Description  When using `AzureAIAgentClient` with a Magentic workflow and Human-in-the-Loop (HITL) tool approval via `@ai_function(approval_mode="always_require")`, each agent invocation creates a new server-side thread, causing the agent to lose conversation context.  ## Scenario  - Using `MagenticBuilder` with a `ChatAgent` backed by `AzureAIAgentClient` - Agent has a tool decorated with `@ai_function(approval_mode="always_require")` (e.g., `ask_user` for clarification) - When the agent calls the tool, workflow pauses for human approval via `MagenticHumanInterventionRequest` - User provides response via `MagenticHumanInterventionReply` - Agent is re-invoked to continue processing  ## Ex

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 91. [microsoft/agent-framework#2765](https://github.com/microsoft/agent-framework/issues/2765)  axis_hint=A1 suggest=A1 state=closed
**.NET Workflows - Investigate ability to support parallel execution (Fan Out / Fan In)**

> **Ask:** How can we enable Fanout in Declarative Agents workflows, given that only a foreach loop is currently supported and parallel execution isn’t available?

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 92. [microsoft/agent-framework#6909](https://github.com/microsoft/agent-framework/issues/6909)  axis_hint=A2 suggest=A2 state=open
**.NET: Python: [Bug]: AG-UI appends approval-resolved tool results out of order — invalid history for strict chat providers**

> ### Description  ## 1. Summary  When a run resumes after a tool-approval response, `agent_framework_ag_ui` executes the approved call and **appends its result message to the end of the reconstructed history** instead of seating it directly after the assistant message that contains the matching `tool_calls` entry. Because the thread snapshot stores the assistant's streamed text as a *separate message after* the tool-calls message (the deliberate format from issue [#3619](https://github.com/microsoft/agent-framework/issues/3619)), the appended result lands **after** that text:  ```text assistant: tool_calls [...] assistant: (streamed text)          <- snapshot's split-off text message tool:   

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 93. [microsoft/agent-framework#6828](https://github.com/microsoft/agent-framework/issues/6828)  axis_hint=A2 suggest=A2 state=open
**Python: [Bug]: AG-UI confirm_changes approval-gated tool reverts to "in progress" after completing**

> ## Description  When a tool is gated by human-in-the-loop approval over AG-UI using the `confirm_changes` flow (`AgentFrameworkAgent(require_confirmation=True)`, as CopilotKit uses), the tool's executed result is emitted **only** as a transient `TOOL_CALL_RESULT` event and is never recorded in `flow.tool_results`. As a result, the end-of-turn `MESSAGES_SNAPSHOT` omits the tool-result message.  Clients that reconcile rendered state from `MESSAGES_SNAPSHOT` (e.g. CopilotKit) then revert the **already-completed** tool call back to "in progress": the tool chip flips from done → running right after approval, and again on the next turn's snapshot.  ### Package Versions  agent-framework-core: 1.9.0

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 94. [microsoft/agent-framework#6652](https://github.com/microsoft/agent-framework/issues/6652)  axis_hint=A2 suggest=A2 state=open
**Python: [Feature]: AG-UI agent adapter should forward HITL approval to a hosted/remote FoundryAgent (mcp_approval_response) instead of executing locally**

> ### Is your feature request related to a problem? Please describe.  When a **deployed Foundry hosted agent** is exposed over AG-UI with the native `add_agent_framework_fastapi_endpoint(FoundryAgent(...))`, the human-in-the-loop (HITL) **approve** step never re-executes the gated tool.  The AG-UI *agent* adapter resolves approvals **locally**: `agent_framework_ag_ui/_agent_run.py` → `_resolve_approval_responses()` (`main`, line ~455) calls `_try_execute_function_calls()` (line ~568) — i.e. it tries to run the approved tool **in-process**. A hosted/remote agent has no local tool bodies, so nothing runs: the tool never re-executes server-side, and state is unchanged. The approval *request* surf

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 95. [microsoft/agent-framework#6385](https://github.com/microsoft/agent-framework/issues/6385)  axis_hint=A2 suggest=A1 state=closed
**Python: [Bug]: Mixed Tool Batch Applies Approval Wrapper To All Tool Calls**

> ### Description   ## Summary When the model emits multiple tool calls in one assistant turn, and only one of those tools has approval_mode set to always_require, the framework wraps all function calls in function_approval_request.  In AG-UI this results in confirm_changes being emitted for every tool call in the batch, including tools that should execute without approval.  ## Impact - Non-sensitive tools are incorrectly blocked behind approval dialogs. - UI shows duplicate or extra approval prompts. - User flow becomes confusing and slower.  ## Reproduction 1. Register two tools:    - add_comment with approval_mode="always_require"    - search_work_items with default approval_mode (never_req

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 96. [microsoft/agent-framework#5855](https://github.com/microsoft/agent-framework/issues/5855)  axis_hint=A2 suggest=A2 state=closed
**Python: [Bug]: AG-UI history replay can send invalid assistant/tool sequence to OpenAI (tool_calls without matching tool messages)**

> ### Description  When using `agent_framework.ag_ui` with persisted thread history, later requests can intermittently fail with OpenAI/Azure validation errors:  > `An assistant message with 'tool_calls' must be followed by tool messages responding to each 'tool_call_id'.`  The issue appears related to replay/history reconstruction logic where assistant tool-call messages and tool-result messages become inconsistently paired during outbound payload generation.  ### Code Sample  ```markdown  ```  ### Error Messages / Stack Traces  ```markdown {   "error": {     "message": "An assistant message with 'tool_calls' must be followed by tool messages responding to each 'tool_call_id'. The following t

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 97. [microsoft/agent-framework#5577](https://github.com/microsoft/agent-framework/issues/5577)  axis_hint=A2 suggest=A2 state=closed
**Python: [Bug]: executor.process spans intermittently never close, leaving child gen_ai.* spans orphan in App Insights**

> ### Description    ## Summary    When running a multi-executor workflow with HITL pauses, a dropped-type-mismatch edge group, and per-row `asyncio.gather` work, MAF's executor   instrumentation intermittently fails to close `executor.process` spans. The spans are created (their span_ids appear as `parent_id` of child spans    inside the executor), but are never `.end()`-ed, never exported via `SimpleSpanProcessor`, and never appear in App Insights / OTLP collectors.    The visible symptom is broken trace trees: child spans (LLM calls, manually-instrumented `gen_ai.*` spans inside per-row work) appear in App   Insights with `parent_id` values pointing at executor.process spans that don't exis

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 98. [microsoft/agent-framework#4411](https://github.com/microsoft/agent-framework/issues/4411)  axis_hint=A2 suggest=A2 state=closed
**Python: [Bug]: HandoffBuilder + OpenAIChatClient tool approval causes duplicate tool_calls messages (400 error)**

> ### Description  When using `HandoffBuilder` with `OpenAIChatClient` (Chat Completions API) and a tool that has `approval_mode="always_require"`, the workflow crashes with a 400 error after the user approves a tool call. The OpenAI API rejects the request because the message array contains a duplicate assistant message with `tool_calls` that has no matching `tool` response message.  ### Root cause  `HandoffAgentExecutor._run_agent_and_emit()` replays `_full_conversation` as the message cache. The default `InMemoryHistoryProvider` also independently stores and loads messages via the agent session. When the workflow resumes after tool approval, both sources contribute messages, causing the ass

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 99. [microsoft/agent-framework#4376](https://github.com/microsoft/agent-framework/issues/4376)  axis_hint=A2 suggest=A2 state=closed
**Python: [Bug]: HandoffBuilder store=False breaks FunctionInvocationLayer tool result submission**

> ### Description  # What happened When using HandoffBuilder with AzureOpenAIResponsesClient, the workflow crashes with openai.BadRequestError: Item with id 'rs_...' not found after a tool call completes and the framework tries to submit the tool result back to the model. HandoffBuilder._clone_chat_agent() forces store=False (line 373 of _handoff.py). This is intentional — handoff workflows manage conversation state explicitly. However, the FunctionInvocationLayer's streaming tool loop (_tools.py, line 2280-2282) still captures response.conversation_id from the streaming response and passes it as previous_response_id on the next iteration (the tool result submission). Since store=False means t

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 100. [microsoft/agent-framework#3938](https://github.com/microsoft/agent-framework/issues/3938)  axis_hint=A2 suggest=A2 state=open
**[Feature] Workaround for tool call side-effect replay on checkpoint-based retry after executor failure**

> ## Description  When an `AgentExecutor` fails mid-superstep (e.g., the underlying agent/LLM call crashes after some tool calls have already executed), the workflow engine does not save a checkpoint for the failed superstep. On resume from the last successful checkpoint, the entire agent turn is replayed from scratch — including tool calls that already completed and produced real-world side effects.  **What problem does it solve?**  Given a workflow `AgentExecutor "A" → AgentExecutor "B"`:  1. Superstep 1: A runs successfully → checkpoint saved 2. Superstep 2: B receives A's output, starts `agent.run()`:    - Tool call `send_email(to=bob)` → executed, email sent    - Tool call `update_databas

suggestion: **direct?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 101. [microsoft/agent-framework#3255](https://github.com/microsoft/agent-framework/issues/3255)  axis_hint=A2 suggest=A2 state=closed
**Python: [Bug]: WorkflowExecutor re-sends already-answered RequestInfoEvents after checkpoint restore**

> ### Description  ## Environment - **Package**: `agent-framework[azure]==1.0.0b260106` - **Python**: 3.12 - **OS**: Windows 11  ## Description  When using `request_response()` within a sub-workflow that is managed by a `WorkflowExecutor`, resuming from a checkpoint causes already-answered requests to be re-sent to the parent workflow. This results in either: 1. `ValueError: Response provided for unknown request ID: <uuid>` when trying to reply to duplicate requests 2. Workflow hanging because `expected_response_count` is incorrect  ## Reproduction Steps  1. Create a parent workflow with an Orchestrator executor 2. Create a sub-workflow (e.g., TicketingWorkflow) wrapped in a `WorkflowExecutor`

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 102. [microsoft/agent-framework#2276](https://github.com/microsoft/agent-framework/issues/2276)  axis_hint=A2 suggest=A2 state=closed
**Python: Workflow Restarts Instead of Resuming After `request_info` Response**

> ## Description  When using `request_info` with a `@response_handler` in a workflow running in DevUI, submitting a response causes DevUI to start a **fresh workflow execution** instead of resuming the paused workflow. The `@response_handler` method is never invoked, and the workflow restarts from the beginning.  ## Expected Behavior  1. Workflow calls `ctx.request_info()` and pauses 2. DevUI displays a popup for user input 3. User submits response 4. DevUI resumes the workflow from the checkpoint 5. `@response_handler` is invoked with the user's response 6. Workflow continues from where it paused  ## Actual Behavior  1. Workflow calls `ctx.request_info()` and pauses ✅ 2. DevUI displays a popu

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 103. [microsoft/agent-framework#827](https://github.com/microsoft/agent-framework/issues/827)  axis_hint=A2 suggest=A2 state=closed
**.NET: Python: when resuming from checkpoint, executor IDs in the workflow should match exactly to the executor IDs in the checkpoint**

> 1. Must perform validation whenever loading from a checkpoint. 2. Executor requires an ID to create 3. Check for duplicate IDs in workflow validation.

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 104. [microsoft/agent-framework#196](https://github.com/microsoft/agent-framework/issues/196)  axis_hint=A2 suggest=A2 state=closed
**Support long-running / resumable operations on Agent**

> Some agents can have very long-running tasks. We will need the ability in either an IRunnableAgent or a separate IResumableAgent to resume consumption of a previously invoked operation. This will need to compose with orchestrations, such that an agent representing an orchestration over such resumable agents will itself be resumable.  cc: @westey-m

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 105. [microsoft/agent-framework#6786](https://github.com/microsoft/agent-framework/issues/6786)  axis_hint=A2 suggest=A2 state=open
**.NET: [Bug]: HITL in Durable workflows the Executor TInput state is lost after approval is granted.**

> ### Description  When a durable workflow pauses for Human-in-the-Loop (HITL) approval and execution resumes after approval is granted the executor does not retain its original **TInput** state. As a result, the input passed to the executor before the approval is lost or reset, preventing the executor from continuing with the same context.   The executor should resume with the original **TInput** instance so that workflow execution can continue seamlessly without requiring the input to be reconstructed again.  In the code sample,"**isapproved**" property value is maintained post HITL approval that comes from the value passed during the workflow invocation. Other property values like "**inputn

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 106. [microsoft/agent-framework#4265](https://github.com/microsoft/agent-framework/issues/4265)  axis_hint=A2 suggest=A2 state=open
**.NET: [Feature]: Native Async Tool/Function Support — Agent Suspend & Resume on Long-Running Tool Calls**

> ## Description  **What problem does it solve?**  Currently, all tool/function invocations in the Agent Framework are synchronous within the agent's request-response cycle. When the LLM requests a function call, `FunctionInvokingChatClient` immediately invokes it, waits for the result, and feeds it back — all within a single `RunAsync` call. This doesn't work for real-world async operations where a tool triggers an external process (API call, workflow, human task) that takes seconds to hours to complete. The agent should not hold a connection/thread waiting; it should yield control and resume when the result arrives.  The existing `requireApproval` (human-in-the-loop) pattern is close — it su

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 107. [microsoft/agent-framework#184](https://github.com/microsoft/agent-framework/issues/184)  axis_hint=A2 suggest=A2 state=closed
**Overhaul orchestrations and their interaction with the agent runtime**

> The current orchestration layer uses IAgentRuntime as an integral part of its operation. A runtime actor is created for each agent, 1:1, with message passing via the runtime as the way that all communication between agents is achieved. For example, for a sequential orchestration, the equivalent of (pseudo-code): ```C# var input = ...; Agent[] agents = ...; AgentThread[] threads = ...; for (int i = 0; i < agents.Length; i++) {     input = await agents[i].InvokeAsync(input); } return input; ``` this gets implemented today as something like: ```C# var input = ...; Agent[] agents = ...; AgentThread[] threads = ...; IAgentRuntime runtime = ...; Actor[] actors = new Actor[agents.Length]; for (int 

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 108. [microsoft/agent-framework#4949](https://github.com/microsoft/agent-framework/issues/4949)  axis_hint=A3 suggest=A3 state=closed
**Usability + Reliability Issues in New Foundry (Graphic Agent Framework Lab)**

> # **Draft Feedback: Usability + Reliability Issues in New Foundry (Graphic Agent Framework Lab)**  Hi team,  While working through the *“Orchestrate a multi-agent solution using the Microsoft Agent Framework”* lab, I encountered several UX inconsistencies and reliability issues that may confuse users, especially since the experience is still in preview. I’m sharing a consolidated list of observations that may help improve the workflow.  ***  ## **1. Forced Agent Creation in “New Foundry” Flow**  *   When creating a new project in the *New Foundry*, switching from default to "New Foundry" experience, the user is presented with a welcome/introduction panel. Note that the project'agent is alrea

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 109. [openai/openai-agents-python#3004](https://github.com/openai/openai-agents-python/issues/3004)  axis_hint=A1 suggest=A1 state=closed
**HITL resume drops tool output when parallel calls mix approval-gated and non-approval tools**

> ### Please read this first  - **Have you read the docs?** [Agents SDK docs](https://openai.github.io/openai-agents-python/) - **Have you searched for related issues?** Yes — this is a sibling of #2798.  ### Describe the bug  Sibling of #2798 (same function, different dedup mechanism).  When a model issues parallel tool calls where **some require approval** (interrupted) and **some do not** (execute immediately), resuming after rejecting the interrupted calls fails with `BadRequestError: No tool output found for function call <call_id>`.  The `call_id` in the error belongs to the tool that **executed successfully** (no approval needed), not one of the rejected tools.  **Root cause:** `OpenAIS

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 110. [openai/openai-agents-python#636](https://github.com/openai/openai-agents-python/issues/636)  axis_hint=A1 suggest=A2 state=closed
**Human-In-The-Loop Architecture should be implemented on top priority!**

> ### Please read this first  - **Have you read the docs?** [Agents SDK docs](https://openai.github.io/openai-agents-python/) : Yes   - **Have you searched for related issues?** Others may have had similar requests : Yes  ---  ### Describe the feature  The OpenAI Agents SDK currently offers impressive capabilities for autonomous and tool-augmented agents. However, **a critical gap exists in supporting Human-In-The-Loop (HITL) workflows**, which are essential in many real-world applications where full automation is either unsafe, undesirable, or legally restricted.  This feature request is to **natively support a Human-In-The-Loop architecture** within the Agents SDK, enabling agent workflows t

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 111. [openai/openai-agents-python#2868](https://github.com/openai/openai-agents-python/issues/2868)  axis_hint=A1 suggest=A1 state=closed
**Per-tool authorization middleware for agent tool calls**

> ### Please read this first - **Have you read the docs?** Yes - **Have you searched for related issues?** Yes. Found no existing issue for per-tool authorization middleware in this SDK.  ### Describe the feature  The SDK has guardrails for input/output validation and human-in-the-loop for approval flows. What's missing is a per-tool authorization layer that evaluates whether a tool call should execute based on identity, scope, rate limits, and session context.  Guardrails check content. Authorization checks permission. Both are needed but they solve different problems.  **Example:** An agent with access to `send_email` and `query_database` passes every guardrail check but uses those tools to 

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 112. [openai/openai-agents-python#3115](https://github.com/openai/openai-agents-python/issues/3115)  axis_hint=A2 suggest=A2 state=closed
**Dynamic function tool is still executed after is_enabled becomes false**

> ### Please read this first  - [x] **Have you read the docs?** Yes. - [x] **Have you searched for related issues?** Yes. I searched existing issues and PRs.  I found related historical discussions and feature work around `is_enabled`, including #2232, #1877, #1097, #808, and #1193, but I did not find an issue or open PR for the specific case where a function tool is visible to the model, then dynamically disabled before execution, and still executes.  ### Describe the bug  A function tool with a dynamic `is_enabled` callback can still execute after the callback starts returning `False`.  The model only sees the tool when `is_enabled` initially returns `True`, which is expected. However, after

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 113. [openai/openai-agents-python#3471](https://github.com/openai/openai-agents-python/issues/3471)  axis_hint=A3 suggest=A4 state=closed
**Support Responses API background mode in Runner (background=True + adaptive polling)**

> ### Summary  Add first-class support for the Responses API's [background mode](https://platform.openai.com/docs/guides/background) to `Runner`, so users can run long agent turns (gpt-5.2-pro, deep-research-class workloads) without hitting HTTP / proxy / serverless timeouts.  Today, passing `background=True` through `model_settings.extra_args` reaches `client.responses.create()` but returns a non-terminal `Response` with `status="queued"`, and the turn loop has no path to poll it to completion — the turn breaks. This proposes adding that path at the model-adapter layer.  Related: openai/openai-agents-js#651 (same request on the JS sibling, still open, labeled `enhancement`). Microsoft Agent F

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 114. [openai/openai-agents-python#1425](https://github.com/openai/openai-agents-python/issues/1425)  axis_hint=A3 suggest=A4 state=closed
**Add `timeout` feature for agent runs**

> Have you read the docs? [Agents SDK docs](https://openai.github.io/openai-agents-python/) – *YES*  Have you searched for related issues? Others may have had similar requests – *YES*  Describe the feature It would be helpful to have a `max_time` parameter for the *run()* and *run_streamed()* methods, allowing users to automatically terminate runs that exceed a specified duration.  While this functionality is straightforward for users to implement manually, it would be convenient to have it built into the SDK.  Proposed behavior:  - If `run_time` > `max_time`, raise a **TimeoutError** (some relevant err).  - For streaming runs: `max_time` counts seconds before the first token is received.  - F

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 115. [openai/openai-agents-python#1061](https://github.com/openai/openai-agents-python/issues/1061)  axis_hint=A3 suggest=A3 state=closed
**Agent run with previous_response_id fails - No tool output found for function call call_WdnUUKXKvwy3jk....**

> - **Have you searched for related issues?** Others may have faced similar issues. These issues are related, but don't have a resolution: https://github.com/openai/openai-agents-python/issues/673 https://github.com/openai/openai-agents-python/issues/632  ### Describe the bug Agent runs using previous_response_id fail unexpectedly and sporadically following a tool call, with an error such as `"Error code: 400 - {'error': {'message': 'No tool output found for function call call_WdnUUKXKvwy3jksn4I9ERdRT.', 'type': 'invalid_request_error', 'param': 'input', 'code': None}}"`  Here's how the error looks in the trace console:  <img width="1272" height="318" alt="Image" src="https://github.com/user-a

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 116. [openai/openai-agents-python#576](https://github.com/openai/openai-agents-python/issues/576)  axis_hint=A3 suggest=A3 state=closed
**input_guardrail is skipped**

> ``` @input_guardrail async def rate_info_guardrail(     ctx: RunContextWrapper[OrchestratorContext],  # your context type     agent: Agent,     input: str | list[TResponseInputItem],  # same sig the SDK expects ) -> GuardrailFunctionOutput:     """     Abort the run if any critical rate-info fields are missing, or if     is_bid_request_sent is still False.     """      _REQUIRED_RATE_FIELDS = [         "maximum_rate",         "minimum_rate",         "rate_usd",         "is_bid_request_sent",     ]      rate = ctx.context.load_context.rate_info  # <-- your own object      # 2️⃣  Collect the names of missing / invalid fields.     missing: list[str] = []     for name in _REQUIRED_RATE_FIELDS:  

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 117. [crewAIInc/crewAI#2997](https://github.com/crewAIInc/crewAI/issues/2997)  axis_hint=A1 suggest=A1 state=closed
**[BUG] CREW getting stuck on any task as "THINKING" and gets FREEZE**

> ### Description  CLIENT DELIVERABLE IS TODAY. **NEED HELP URGENTLY**  Tasks are getting stuck as "THINKING" for any given task in a crew. No pattern is identified.  Executed crew flow in following order: 1) Have EmailAssignment Crew (custom built with multiple agents and tasks) a) I used dependencies = ["crewai==0.121.0"] in pyproject.toml file     Crew is stuck at:       Crew: crew ├── � Task: 1cd98e6d-2747-441d-9a3d-16f874e94025 │   Assigned to: Field Extraction Specialist │   Status: ✅ Completed └── � Task: c6282374-436b-43ab-9280-2ad676c469d5     Status: Executing Task...     └── � Thinking...  b) I used dependencies = ["crewai>=0.121.0"] in pyproject.toml file � Crew: crew └── � Task: b

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 118. [crewAIInc/crewAI#5802](https://github.com/crewAIInc/crewAI/issues/5802)  axis_hint=A1 suggest=A2 state=open
**Tool re-execution on task retry has no idempotency guard — duplicate payments, emails, trades possible**

> ### Description  When a CrewAI task fails and is retried — via max_retry_limit, exception handling, or external re-trigger — any @tool decorated function that already executed runs again. There's no mechanism to detect that a specific tool call already completed.  ### Steps to Reproduce  1. Create a CrewAI agent with a @tool that calls an external API (payment, email, etc.) 2. Have the tool execute successfully 3. Simulate a failure after tool execution but before the agent receives confirmation 4. Task retries 5. The tool fires again — duplicate side effect  ### Expected behavior  A retry of the same logical tool call should return the original result without re-executing the side effect.  

suggestion: **direct?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 119. [crewAIInc/crewAI#5262](https://github.com/crewAIInc/crewAI/issues/5262)  axis_hint=A1 suggest=A1 state=closed
**feat: Add Sensitivity Ratchet hook for irreversible permission narrowing**

> ---  ## Description  This is a proposal to add documentation for a **community-maintained** hook integration that uses CrewAI's existing `register_before_tool_call_hook` API to implement a session-scoped permission-narrowing pattern for LLM agents.  It is explicitly **not** a novel research contribution — the underlying idea has ~50 years of formal security precedent (Denning 1976, Biba 1977) and several recent AI-agent-specific implementations published in 2025–2026 (see [Related work](#related-work) below). The value proposition is that it gives a CrewAI user a 10-line-install of this pattern without having to wire up Fides, AIP, or the Agent Governance Toolkit themselves.  ## The threat m

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 120. [crewAIInc/crewAI#5049](https://github.com/crewAIInc/crewAI/issues/5049)  axis_hint=A1 suggest=A1 state=closed
**Integration: Cryptographic audit trails for agent actions with asqav**

> As AI agents take autonomous actions, there is a growing need to prove what they did and why. Proposing an asqav integration for CrewAI that signs agent actions with quantum-safe signatures.  **What it would do:** - Sign each agent task execution and tool call with ML-DSA-65 (NIST FIPS 204) - Create tamper-proof audit trails with public verification URLs - Policy enforcement gates (e.g., require approval before high-risk actions) - EU AI Act compliance evidence for autonomous AI systems  **Implementation:** Could work as a CrewAI callback or middleware that wraps task execution with asqav signing.  - SDK: https://github.com/jagmarques/asqav-sdk (MIT) - Website: https://asqav.com

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 121. [crewAIInc/crewAI#4877](https://github.com/crewAIInc/crewAI/issues/4877)  axis_hint=A1 suggest=A1 state=open
**[FEATURE] GuardrailProvider interface for pre-tool-call authorization**

> ## Feature Area  Core functionality  ## Is your feature request related to an existing bug?  Not a bug, but multiple open issues and PRs request tool-level authorization:  - **#4502** - "Proposal: Governance Guardrails Plugin for CrewAI" (closed as completed, but no interface was standardized) - **#4596** - PR proposing fail-closed defaults for unsafe code execution (unresolved safety gap in confirmation timing) - **#4682** - Feature request for Agent Loop Detection Middleware (proposes a `middleware` parameter on agents) - **#4840** - Suggestion for pre-install security scanning of tools - **#4810** - Feature request for Wasm-based sandboxed code execution  CrewAI's existing guardrail syste

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 122. [crewAIInc/crewAI#4560](https://github.com/crewAIInc/crewAI/issues/4560)  axis_hint=A1 suggest=A1 state=closed
**Feature: Cryptographic Identity for Crew Members**

> ## Problem  CrewAI crews currently have no mechanism for agents to cryptographically verify each other's identity. When agents collaborate in a crew:  - There's no proof that Agent A is who it claims to be - No trust scoring to inform task delegation decisions - No cryptographic audit trail of which agent performed what - No way to establish reputation across different crews  As crews get more complex and potentially span organizational boundaries, identity verification becomes critical.  ## Proposed Solution  Integrate a cryptographic identity layer so crew members can: 1. Register verifiable identities (Ed25519 keypairs + DIDs) 2. Verify other agents before collaborating 3. Build trust thr

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 123. [crewAIInc/crewAI#4554](https://github.com/crewAIInc/crewAI/issues/4554)  axis_hint=A1 suggest=A1 state=closed
**[FEATURE] EU AI Act compliance: audit logging & human oversight for autonomous agent crews**

> ## Feature Area  Core functionality / Agent capabilities  ## Is your feature request related to an existing bug?  NA — This is a proactive compliance feature request.  ## Describe the solution you'd like  The EU AI Act (Regulation 2024/1689) enters enforcement in August 2026 and places specific requirements on **autonomous AI agent systems** — exactly the kind CrewAI enables. Key articles relevant to multi-agent orchestration:  - **Article 9 (Risk Management)**: Agent crews performing high-risk tasks (healthcare, finance, legal) need documented risk assessment - **Article 13 (Transparency)**: Users must understand which agent made which decision, with what tools, and why - **Article 14 (Huma

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 124. [crewAIInc/crewAI#3015](https://github.com/crewAIInc/crewAI/issues/3015)  axis_hint=A1 suggest=A1 state=closed
**[FEATURE] Auto Improvement Agentic Pipeline**

> ### Feature Area  Core functionality  ### Is your feature request related to a an existing bug? Please link it here.  No  ### Describe the solution you'd like  ## Overview  The Auto Improve Agent is an intelligent optimization system that automatically improves crew configurations including task descriptions, expected outputs, agent goals, agent backstories, and manager configurations. This feature provides granular control over improvements while maintaining complete audit trails and rollback capabilities.  ### Core Design Principles  - **Separation of Concerns**: Data collection is separated from optimization - **Granular Control**: Selective improvement of specific agents/tasks - **Versio

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 125. [crewAIInc/crewAI#6180](https://github.com/crewAIInc/crewAI/issues/6180)  axis_hint=A2 suggest=A4 state=open
**Feature: Documentation for Production Code Execution in Crews**

> ## Problem  CrewAI teams building production crews need documented patterns for: - Agents executing generated code safely - Local repository and environment access - Production safety (sandboxing, resource limits, timeouts)  Currently this is undocumented, unlike other agent frameworks.  ## Today's Gap  Teams choose between: 1. **No code execution** — limits crew capabilities 2. **Cloud sandboxes** — external cost, context loss 3. **Custom implementations** — inconsistent, fragile  ## Comparison  - **AutoGen** — documents `code_execution_config` pattern - **MetaGPT** — documents local executor patterns - **CrewAI** — [no standard pattern documented]  ## Proposed Solution  Add to CrewAI docum

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 126. [crewAIInc/crewAI#6025](https://github.com/crewAIInc/crewAI/issues/6025)  axis_hint=A2 suggest=A2 state=open
**[FEATURE] Runtime release-control mediation layer before agent/tool execution**

> ### Feature Area  Core functionality  ### Is your feature request related to a an existing bug? Please link it here.  N/A  ### Describe the solution you'd like  I’ve been experimenting with a lightweight runtime mediation layer for agent execution systems.  Core idea: generation != release authority  Instead of treating every generated tool/action call as implicitly authorized, introduce a bounded runtime release-control layer between:  candidate generation → execution authorization  The mediation layer exposes tri-state runtime decisions:  - PROCEED - NEEDS_REVIEW - SILENCE  The goal is not to block autonomous workflows entirely.  The goal is introducing a lightweight execution review bound

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 127. [crewAIInc/crewAI#3259](https://github.com/crewAIInc/crewAI/issues/3259)  axis_hint=A2 suggest=A2 state=closed
**[FEATURE] Support client-initiated real-time human-input event stream (WebSocket/SSE/long-polling) for pending human input**

> ### Feature Area  Other (please specify in additional context)  ### Is your feature request related to a an existing bug? Please link it here.  Not a bug, builds on prior feature discussions that were closed as “not planned” (#654, #2051) but reframes the problem around offering alternative integration methods for human input delivery.  ### Describe the solution you'd like  ## Background / Problem  CrewAI currently signals that it needs human input (i.e., enters “Pending Human Input”) only via externally delivered webhooks. That creates integration friction in scenarios where hosting a publicly reachable webhook endpoint is hard or undesirable (local dev behind NAT, locked-down security envi

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 128. [crewAIInc/crewAI#667](https://github.com/crewAIInc/crewAI/issues/667)  axis_hint=A2 suggest=A2 state=closed
**allow delegation=True returns error**

> As descried in title, in agents.py configuring Agent setting `allow_delegation=True` results in errors:  `Error executing tool. Co-worker mentioned not found, it must to be one of the following options: - agent1 - agent2 - agent3`  I have changed `role=agent_name` same as the function name to debug with no difference.  Searching [stackoverflow.com](https://stackoverflow.com/questions/78466708/crewai-not-finding-co-worker) it seems someone else had similar bug.  `Python 3.11.8`  > Name                    Version                   Build  Channel  aiohttp                   3.9.5                    pypi_0    pypi aiosignal                 1.3.1                    pypi_0    pypi al

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 129. [crewAIInc/crewAI#5888](https://github.com/crewAIInc/crewAI/issues/5888)  axis_hint=A2 suggest=A2 state=open
**[FEATURE]:Governance middleware hook for tool call authorization**

> ### Feature Area  Agent capabilities  ### Is your feature request related to a an existing bug? Please link it here.  N/A  ### Describe the solution you'd like  ## Problem  CrewAI agents execute tools autonomously during crew runs. In production deployments, teams need governance controls: - Which tools each agent is authorized to use (beyond just assigning tools) - Cost tracking per agent across a crew run - Audit trail for compliance (who called what, when, why) - Ability to block specific tool calls based on runtime context (e.g., data sensitivity, time of day, budget remaining)  Currently, the only way to enforce this is by wrapping each tool's `_run` method individually, which doesn't c

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---
## 130. [crewAIInc/crewAI#2885](https://github.com/crewAIInc/crewAI/issues/2885)  axis_hint=A4 suggest=A4 state=closed
**[BUG] Invalid response from LLM call - None or empty.**

> ### Description  When using a custom tool, an error occurred. The tool itself returned a normal response, but it still shows that no response content was received, as follows:  ```  Received None or empty response from LLM call.  An unknown error occurred. Please check the details below.  Error details: Invalid response from LLM call - None or empty.  An unknown error occurred. Please check the details below.  Error details: Invalid response from LLM call - None or empty. ```  ![Image](https://github.com/user-attachments/assets/9785a2ca-9dc1-402b-90a0-2769cec03720)  --- The program eventually crashed. The logs are as follows:  Invalid type LLM for attribute 'function_calling_llm' value. Expe

suggestion: **adjacent/context?**   (heuristic only)

**VERDICT:** `UNSET`   <!-- set to: direct | adjacent | context -->
**why:** 

---