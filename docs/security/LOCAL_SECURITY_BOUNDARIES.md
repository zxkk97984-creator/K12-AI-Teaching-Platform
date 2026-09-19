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
following gates remain `BLOCKED` in `.rebuild-kit/progress.json`:

- `G_AGENT_ISOLATION`: no authorized tenant evidence for cross-session files,
  memory, tools, execution identity, or revocation;
- `G_K12_TERMS`: the applicable competition tenant and under-16 terms are not
  confirmed;
- `G_API_CONTRACT` and `G_LIVE_BUDGET`: no authorized live wire/usage evidence;
- `G_HUMAN_CONTENT_REVIEW`: no human reviewer signature.

## T26 dependency gap

The project currently has no codelab HTTP routes or persistent code-run/data
export/deletion boundary. T26 is therefore recorded as `BLOCKED` under its
own allowed-path rules; T28 does not invent a second API or treat local
fixtures as a replacement. Once the codelab application boundary is approved,
T28 must add owner-scoped export/deletion tests and repeat the full cross-user
matrix against those real routes.
