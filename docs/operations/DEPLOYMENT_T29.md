# T29 clean deployment and recovery boundary

This is the local deployment entrypoint for the synthetic competition
prototype. It never reads or overwrites `.env`, never resets a database volume,
and never contacts Knodo. The host must provide `POSTGRES_DEV_PASSWORD`,
`POSTGRES_TEST_PASSWORD`, and an `APP_SESSION_SECRET` of at least 32
characters. Demo credentials are optional `T05_DEMO_*` variables and are only
provisioned outside production.

## One bootstrap path

```bash
./scripts/bootstrap.sh
```

The script runs doctor, locked host dependencies, PostgreSQL health checks,
Alembic migrations, the legacy content importer, development-only synthetic
content, CodeLab task import, and optional synthetic accounts. Re-running it
reuses immutable course/task revisions and does not reseed or overwrite
accounts. Set `BOOTSTRAP_DEPLOY=1` on a clean local machine to additionally
build and start the API, worker, and web services:

```bash
BOOTSTRAP_DEPLOY=1 ./scripts/bootstrap.sh
```

`APP_ENV=production` skips synthetic content/accounts and `Settings` rejects
`GATEWAY_MODE=fixture`. The default local Compose profile leaves the runner
disabled; CodeLab reports `UNAVAILABLE` until a separately authorized runner
control plane is configured with `CODELAB_RUNNER_URL` and its token.

## Service topology

- `postgres-dev` and `postgres-test` are separate PostgreSQL services and
  named volumes on ports 55433/55434.
- `api` is FastAPI on 18081; `worker` polls durable teaching/authoring rows
  with `TEACHING_AUTORUN=false` and `AUTHORING_AUTORUN=false` in the Compose
  deployment.
- `web` is an Nginx static image on 15173. Same-origin `/api/` and `/health/`
  requests are proxied to `api`; the browser never receives a database or
  runner token.
- `k12r1-app-storage` is shared by API and worker for resource/authoring
  files. Database remains the authority for metadata and job state.
- The Docker runner is deliberately not granted a socket through this Compose
  file. It runs as the separate T24 host control plane, or remains disabled;
  the API never falls back to host execution.

## Readiness and recovery

`/health/live` only proves the API process responds. `/health/ready` checks the
database migration boundary, storage parents, and configured runner health;
it returns `runner=disabled` when CodeLab is intentionally off and never calls
paid AI. The worker recovers stale teaching/authoring rows at startup, claims
queued work, and can be checked without mutating data:

```bash
WORKER_ONESHOT=1 python -m app.jobs.worker
```

Stop only this Compose project with `docker compose stop api worker web`.
Rollback application code by deploying the prior local Git commit, then run
the matching migration plan; do not drop volumes or run `docker system prune`.
Old K12/CareerMate containers, ports, and volumes are outside this project.
