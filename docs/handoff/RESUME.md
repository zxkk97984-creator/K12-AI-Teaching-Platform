# Resume note

## Start here

1. cd /home/zxk/Projects/K12
2. read AGENTS.md and .rebuild-kit/progress.json
3. run git status --short and confirm no other writer
4. read docs/acceptance/T30.md, T31.md, T32.md, T33.md and this handoff
5. read docs/handoff/GOAL_COMPLETION_AUDIT.md for the requirement-by-requirement stop state

## Current task state

- T30: local synthetic scope DONE; baseline browser matrix was 21 passed + 1 historical skip, then the
  affected animation spec was rerun with explicit T06 fixtures and passed 1/1. Formal human-reviewed
  senior animation content remains an external requirement.
- T11: DONE；T13: DONE。真实 Tutor/Designer 与浏览器课堂竖切证据已提交候选，预算账本 16/20。
- T31: BLOCKED；16-case 真实执行已完成（13 OK、2 Schema失败、1超时），人工 rubric 未执行。
- T32: DONE as the required draft deliverable; report, demo and integration docs are committed, with
  T31 live metrics已补入验收材料，真人判断仍明确 pending。
- T33: BLOCKED by T31 human review and G_HUMAN_CONTENT_REVIEW; T32 draft delivery is complete, and the local
  doctor/bootstrap repeat check passed twice. Latest T31 review-handoff checkpoint is `0a7c7ab`.

## Recovery facts

- Repository: `/home/zxk/Projects/K12`, branch `main`, no remote, and the handoff worktree is clean.
- Latest implementation/evidence checkpoint: `0a7c7ab`; earlier T11/T13/T32 checkpoints remain in local history.
- Load only the existing secure environment through the documented scripts (for example the local
  test harness); do not print or copy any values from it. No root `.env`, PAT, cookie, database dump,
  upload, or browser storage belongs in Git.
- Full T31 synthetic model text and its exhausted private ledger remain local-only at
  `docs/acceptance/T31-live-results.synthetic.json` and `storage/private/t31-request-budget.json`;
  both are intentionally ignored. The committed summary is hash-bound to the local raw evidence.
- Human review starts from `docs/acceptance/T31-review-packet.local.md` and
  `docs/acceptance/T31-human-review.template.json`; validate a separately completed copy with
  `python evals/review_tools.py check-review --review <completed.json> --output docs/acceptance/T31-human-review.result.json`.
- No K12 API, Vite, Playwright, runner, or migration process was active at handoff. The historical
  `.herdr-control/shared-test.lock` is retained as recovery evidence; do not delete or claim it was
  released by this session.
- The latest `./scripts/check.sh` exited 1 at the read-only CareerMate source audit because that
  external reference tree's HEAD/tree/status/untracked state drifted. Preserve the failure; do not
  reset, checkout, delete, or bypass the old reference tree. K12-specific evidence remains in T30/T31.
- Continue from `.rebuild-kit/progress.json`, `docs/acceptance/T31.md`, `T31-live-summary.json`, `T31-HUMAN-REVIEW.md`, `T32.md`, `T33.md`, and the Knodo checklist. Do not rerun the exhausted 16-case T31 ledger.

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
