# Six-tracker corpus sweep -- CANDIDATES (pending manual verification)

Generated 2026-07-04. Queries: [A1] 'interrupt parallel'; [A1] 'human approval parallel'; [A2] 'resume duplicate'; [A2] 'resume executes again'; [A3] 'cancel still running'; [A4] 'timeout effect completed'.
Unauthenticated GitHub search, 20 hits/query cap, deduplicated per (repo, axis, query, issue).

| repo | unique candidate issues | A1 | A2 | A3 | A4 |
|---|---|---|---|---|---|
| langchain-ai/langgraph | 58 | 21 | 25 | 18 | 7 |
| langchain-ai/langgraphjs | 8 | 4 | 2 | 2 | 0 |
| run-llama/llama_index | 18 | 3 | 2 | 12 | 2 |
| microsoft/agent-framework | 24 | 7 | 18 | 1 | 1 |
| openai/openai-agents-python | 8 | 3 | 1 | 4 | 1 |
| crewAIInc/crewAI | 14 | 8 | 7 | 1 | 4 |

Every row above is a CANDIDATE: the corpus's conservative DIRECT/ADJACENT/CONTEXT classification requires reading each issue (seeds.py protocol) and is not performed by this tool.

Raw hits: 170 records in sweep_results.jsonl.
