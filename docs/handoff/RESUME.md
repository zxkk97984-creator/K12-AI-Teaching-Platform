# Resume note

## Start here

1. cd /home/zxk/Projects/K12
2. read AGENTS.md and .rebuild-kit/progress.json
3. run git status --short and confirm no other writer
4. read docs/acceptance/T30.md, T31.md, T32.md, T33.md and this handoff

## Current task state

- T30: local synthetic scope DONE; baseline browser matrix was 21 passed + 1 historical skip, then the
  affected animation spec was rerun with explicit T06 fixtures and passed 1/1. Formal human-reviewed
  senior animation content remains an external requirement.
- T31: BLOCKED by G_API_CONTRACT and G_LIVE_BUDGET; offline eval framework is committed.
- T32: DONE as the required draft deliverable; report, demo and integration docs are committed, with
  T31 live metrics explicitly marked pending.
- T33: BLOCKED by T31 and G_HUMAN_CONTENT_REVIEW; T32 draft delivery is complete. Latest implementation
  checkpoint is 5821daa, and the final handoff pointer will follow the current documentation commit.

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
