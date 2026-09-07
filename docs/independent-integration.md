# Independent integration assessment

**Milestone 2: incomplete.** Three public workflows were inspected on 2026-09-07.
No candidate was executed or modified, no adapter was completed, and no independent
bug discovery is claimed. The bounded candidate assessment is complete; the
integration milestone is not.

## Candidates and exact source revisions

| Candidate | Revision | Evidence and blocker |
| --- | --- | --- |
| [mallahim01/langgraph-support-operations-agent](https://github.com/mallahim01/langgraph-support-operations-agent/tree/5bc1927f57ab87367930add8e946ffe5443189c3) | `5bc1927f57ab87367930add8e946ffe5443189c3` | SQLite business commits in `backend/app/tools/ticket_tools.py`; SQLite checkpointer factory in `backend/app/graph/builder.py`. No license file in the checked-out tree, and no license grant found in README. License suitability is unresolved. |
| [niti007/langgraph-customer-support-agent](https://github.com/niti007/langgraph-customer-support-agent/tree/fd1148a2cdb919707ddf6d2a260b5090b87826f0) | `fd1148a2cdb919707ddf6d2a260b5090b87826f0` | MIT license; persistent SQLite checkpointer in `src/graph.py`. `resolve_case` and `escalate_case` in `src/nodes.py` return workflow-state updates/messages, with no external ticket/account business-write backend. Adding such writes would manufacture the missing integration target. |
| [langchain-ai/langsmith-agent-lifecycle-workshop](https://github.com/langchain-ai/langsmith-agent-lifecycle-workshop/tree/e1d3b7cfcd0ed54ed47d3baafc3b859cb9942d56) | `e1d3b7cfcd0ed54ed47d3baafc3b859cb9942d56` | Apache-2.0 license. `tools/database.py` contains read queries and an explicitly SELECT-only SQL tool. `agents/supervisor_hitl_agent.py` uses MemorySaver locally or deployment-owned persistence. The inspected workflow lacks external business writes for the agreed commit-recovery validation. |

The first two repositories were shallow-cloned for source inspection. The third
was fetched at a shallow revision and inspected with `git ls-tree` and `git show`.
No model credentials were used. License and source conclusions are limited to
these exact revisions and inspected workflow paths.

## Integration measurements

- Completed adapter files/lines: **0 / 0**; no successful integration to measure.
- Independently executed workflow behaviors and covered boundaries: **none**.
- Reused or added assertions in an independent adapter: **none**.
- Unknown defects found: **none claimed**.
- Controlled mutations detected: only the explicitly authored Fracture demo matrix.
- Elapsed integration time or adoption evidence: **not measured**.

The next useful input is a licensed, separately authored LangGraph workflow with
a resettable write backend and inspectable commit evidence, or clarification of
the first candidate's license from its owner. Do not contact maintainers without
user authorization. Integrate through fixtures, wrappers, and persistence wiring;
record those changes separately from any necessary business-logic changes.
