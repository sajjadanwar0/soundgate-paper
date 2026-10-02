# Screened non-LangGraph-Python candidates -- title+snippet only (PENDING conservative classification)

Bodies were rate-limited on the shared unauthenticated IP; snippets below come from each issue page's og:description. Full verification per seeds.py protocol remains manual.

## [crewAIInc/crewAI#5802](https://github.com/crewAIInc/crewAI/issues/5802) [A1] created=2026-05-14 state=open
**Tool re-execution on task retry has no idempotency guard — duplicate payments, emails, trades possible**

> Description When a CrewAI task fails and is retried — via max_retry_limit, exception handling, or external re-trigger — any @tool decorated function that already executed runs again. There's no mec...

## [microsoft/agent-framework#2276](https://github.com/microsoft/agent-framework/issues/2276) [A2] created=2025-11-17 state=closed
**Python: Workflow Restarts Instead of Resuming After `request_info` Response**

> Description When using request_info with a @response_handler in a workflow running in DevUI, submitting a response causes DevUI to start a fresh workflow execution instead of resuming the paused wo...

## [microsoft/agent-framework#4411](https://github.com/microsoft/agent-framework/issues/4411) [A2] created=2026-03-03 state=closed
**Python: [Bug]: HandoffBuilder + OpenAIChatClient tool approval causes duplicate tool_calls messages (400 error)**

> Description When using HandoffBuilder with OpenAIChatClient (Chat Completions API) and a tool that has approval_mode="always_require", the workflow crashes with a 400 error after the user approves ...

## [langchain-ai/langgraphjs#2446](https://github.com/langchain-ai/langgraphjs/issues/2446) [A3] created=2026-05-28 state=open
**langgraphjs-api image exits with code 1 on graceful SIGTERM, sends signal twice**

> Summary When a container running the langchain/langgraphjs-api:20 image receives SIGTERM (e.g. from docker stop or a Kubernetes/ECS pod replacement), it shuts down cleanly — uvicorn shuts down, que...

## [microsoft/agent-framework#6910](https://github.com/microsoft/agent-framework/issues/6910) [A2] created=2026-07-04 state=open
**.NET: Python: [Bug]: AG-UI host loses tool calls when parallel calls require approval**

> Description 1. Summary When a model returns several tool calls in one turn and any of them requires human-in-the-loop approval, an agent hosted over AG-UI permanently loses every call in the batch ...

## [crewAIInc/crewAI#5888](https://github.com/crewAIInc/crewAI/issues/5888) [A4] created=2026-05-21 state=open
**[FEATURE]:Governance middleware hook for tool call authorization**

> Feature Area Agent capabilities Is your feature request related to a an existing bug? Please link it here. N/A Describe the solution you'd like Problem CrewAI agents execute tools autonomously duri...

## [crewAIInc/crewAI#4877](https://github.com/crewAIInc/crewAI/issues/4877) [A4] created=2026-03-14 state=open
**[FEATURE] GuardrailProvider interface for pre-tool-call authorization**

> Feature Area Core functionality Is your feature request related to an existing bug? Not a bug, but multiple open issues and PRs request tool-level authorization: #4502 - "Proposal: Governance Guard...

## [openai/openai-agents-python#3471](https://github.com/openai/openai-agents-python/issues/3471) [A3] created=2026-05-20 state=closed
**Support Responses API background mode in Runner (background=True + adaptive polling)**

> Summary Add first-class support for the Responses API's background mode to Runner, so users can run long agent turns (gpt-5.2-pro, deep-research-class workloads) without hitting HTTP / proxy / serv...

## [run-llama/llama_index#20210](https://github.com/run-llama/llama_index/issues/20210) [A3] created=2025-11-04 state=closed
**[Bug]: reactagent freezed in streaming mode**

> Bug Description HI, I have this problem since I switched from 0.14.5 to 0.14.7 and upgraded ollama to latest (0.12.9). It s difficult for myself to understand from which one the problem occurs, but...

## [langchain-ai/langgraphjs#1223](https://github.com/langchain-ai/langgraphjs/issues/1223) [A1] created=2025-05-27 state=closed
**Intermediate Messages Not Output Until All Interrupts Are Resolved in a Single Graph**

> In LangGraph, when a single graph contains multiple interrupts within a ReAct agent node, intermediate messages added to the state are not emitted via graph.stream (using stream_mode="updates") unt...