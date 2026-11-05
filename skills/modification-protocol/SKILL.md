---
name: modification-protocol
description: Compare an existing workflow executor and a proposed revision using identical contracts before adopting either.
---

# Modification protocol

1. Search existing implementations using a research subagent. Record primary sources, versions, reuse boundaries, and unknowns in research/candidates.json.
2. Freeze the input/output contract, model, reasoning level, tools, allowed Context, fixtures, and mandatory gates before comparison. Keep forbidden evaluator data in the controller only; no OS isolation claim without an access-denial test.
3. Analyze dependency and failure causes. Resolve input boundaries and terminal-state meanings before adding parallelism or retries. Order workflow nodes by dependencies, not their list order.
4. Reuse existing adapters and workflow libraries where possible. Save a proposed plan as a new revision; never mutate an active run's plan or overwrite the baseline.
5. Execute both candidates against the same fixtures. Separate deterministic state-machine tests, live provider tests, and model-quality evaluations.
6. Run adversarial cases: malformed output, extra control fields, missing usage, cancel race, late completion, duplicate completion, restart/retry and changed comparison contracts.
7. Select only within the tested contract. Mandatory gates precede pass rate. Retain the existing implementation on a tie. If neither qualifies, select none. Never select a new implementation solely because you built it.
8. Record evidence, exact commands, limitations, and reusable modules. Global installation and deleting old artifacts are separate operations.

Project commands (run from the project root):

- `python -m unittest tests_runner tests_adversarial tests_adapter -v`
- `python protocol.py`
- `python runner.py --db state/runs.sqlite3 run examples/workflow.json examples/input.json`
- `python runner.py --db state/runs.sqlite3 status RUN_ID`
- `python runner.py --db state/runs.sqlite3 cancel RUN_ID`
- `python runner.py --db state/runs.sqlite3 revise RUN_ID NEW_PLAN.json`

`recover` requires the former worker to be stopped. `retry` is an explicit new attempt. A late result from the former attempt must remain rejected. Token budgets are post-response gates, not guaranteed generation caps.
