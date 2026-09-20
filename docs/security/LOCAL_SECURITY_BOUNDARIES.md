# T28 local security boundary record

## Verified locally

- Same-origin + CSRF enforcement and revoked-session behavior are covered by
  T05 identity tests and browser evidence.
- Teaching run read/subscribe/cancel owner checks, quiz answer snapshots,
  content revision visibility, resource withdrawal, authoring admin/student
  separation, and memory dispute/forget projections are covered by the
  existing backend/browser regression suites.
- T23 rejects reference/hidden test fields from public task manifests and
  T24 verifies non-root, no-network, read-only, output-limited containers with
  exact owner/lease cleanup.
- T25 rejects feedback from another run/code hash or owner; AI feedback cannot
  add a deterministic score.
- The new T28 static tests ensure tracked frontend source has no runtime
  secret names/private key material and the API compose definition does not
  mount the Docker socket.

## Not a compliance or platform-isolation claim

The local tests do not prove Knodo workspace/session/file/memory/tool
isolation, legal K12 suitability, remote deletion, or platform retention. The
The following formal gates remain `BLOCKED` in `.rebuild-kit/progress.json`:

- `G_AGENT_ISOLATION`: no authorized tenant evidence for cross-session files,
  memory, tools, execution identity, or revocation;
- `G_API_CONTRACT` and `G_LIVE_BUDGET`: no authorized live wire/usage evidence;
- `G_HUMAN_CONTENT_REVIEW`: no human reviewer signature.

`G_K12_TERMS` is out of scope for the declared adult-contestant/synthetic-data prototype; any real
under-16 release must reopen this gate and obtain tenant terms evidence.

## T26 and local privacy boundary

T26 now has a minimal owner-scoped CodeLab application boundary. T28 covers
that real local surface with `/api/v1/me/data-export` and
`/api/v1/me/deletion-requests`: export is authenticated and owner-scoped;
deletion is CSRF-protected, idempotent, and deletes only the explicitly named
`CODELAB_ONLY` local drafts/runs. Local learning evidence outside that scope
is not silently claimed deleted. The response keeps
`platform_status=NOT_CONNECTED/NOT_REQUESTED`, so a local request is not
reported as Knodo deletion or retention confirmation.
