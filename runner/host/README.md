# Host runner boundary

`runner.host.runner.DockerRunner` is the only host-side launcher in this
prototype. It accepts an allowlisted task/revision, one JSON input, a bounded
student source string, and owner/lease identifiers. The request has no image,
volume, command, environment, or Docker option fields; those are fixed in
code.

Each case runs in the digest-pinned image with:

- `--network none`, non-root UID 65532, read-only root, `cap-drop=ALL`, and
  `no-new-privileges`;
- bounded CPU, memory, PIDs, `/tmp` tmpfs, and host-side wall-clock timeout;
- bind mounts for only the current request and student source, both read-only;
- no host environment inheritance other than the Docker CLI `PATH`;
- selectors-based streaming stdout/stderr reads, terminating on the byte
  limit instead of collecting an unbounded pipe.

The host launcher never evaluates student code itself. If Docker or the fixed
image is unavailable it raises `RunnerUnavailable`; there is no Python,
subprocess, or shell fallback. Cleanup filters by the exact project and owner
labels and removes only stopped containers whose lease has expired. It never
uses `docker prune`, a prefix kill, or a host-wide scan.

This is a constrained local runner, not an absolute sandbox guarantee. T28
still owns broader cross-user and data-governance review.
