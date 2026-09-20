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
- T11: DONE；T13: DONE。真实 Tutor/Designer 与浏览器课堂竖切证据已提交候选，预算账本 16/20。
- T31: BLOCKED；API/预算门禁对 T11/T13 已 PASS，但 T31 专用调用未获授权，人工 rubric 未执行。
- T32: DONE as the required draft deliverable; report, demo and integration docs are committed, with
  T31 live metrics explicitly marked pending.
- T33: BLOCKED by T31 and G_HUMAN_CONTENT_REVIEW; T32 draft delivery is complete, and the local
  doctor/bootstrap repeat check passed twice. Latest T13 live implementation/evidence checkpoint is `5bb5653`.

## Recovery facts

- Repository: `/home/zxk/Projects/K12`, branch `main`, no remote, and the handoff worktree is clean.
- Latest implementation/evidence checkpoint: `5bb5653`; earlier T32/status checkpoints remain in local history.
- Load only the existing secure environment through the documented scripts (for example the local
  test harness); do not print or copy any values from it. No root `.env`, PAT, cookie, database dump,
  upload, or browser storage belongs in Git.
- No K12 API, Vite, Playwright, runner, or migration process was active at handoff. The historical
  `.herdr-control/shared-test.lock` is retained as recovery evidence; do not delete or claim it was
  released by this session.
- The latest `./scripts/check.sh` exited 1 at the read-only CareerMate source audit because that
  external reference tree's HEAD/tree/status/untracked state drifted. Preserve the failure; do not
  reset, checkout, delete, or bypass the old reference tree. K12-specific evidence remains in T30/T31.
- Continue from `.rebuild-kit/progress.json`, `docs/acceptance/T13.md`, `T31.md`, `T32.md`, `T33.md`, and the Knodo checklist. Do not spend the remaining four T11/T13-authorized requests on T31 without new authorization.

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
