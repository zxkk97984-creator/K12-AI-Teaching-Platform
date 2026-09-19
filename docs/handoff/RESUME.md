# Resume note

## Start here

1. cd /home/zxk/Projects/K12
2. read AGENTS.md and .rebuild-kit/progress.json
3. run git status --short and confirm no other writer
4. read docs/acceptance/T30.md, T31.md, T32.md, T33.md and this handoff

## Current task state

- T30: BLOCKED only for the explicit animation human-review prerequisite; 21 browser tests passed.
- T31: BLOCKED by G_API_CONTRACT and G_LIVE_BUDGET; offline eval framework is committed.
- T32: BLOCKED/草稿; report and demo docs are committed.
- T33: BLOCKED by T31/T32 and G_HUMAN_CONTENT_REVIEW; latest handoff commit is 981ce93.

## Safe local commands

    ./scripts/doctor.sh
    ./scripts/bootstrap.sh
    PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q
    npm test --prefix frontend
    npm run typecheck --prefix frontend
    npm run build --prefix frontend

Do not run Knodo live, do not read unrelated environment keys, do not delete volumes, and do not
start old K12/CareerMate services. Existing synthetic Compose services may be stopped only by the
exact project command documented in docs/operations/DEPLOYMENT_T29.md.
