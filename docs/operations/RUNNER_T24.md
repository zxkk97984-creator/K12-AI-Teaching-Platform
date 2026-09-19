# T24 runner operating boundary

The runner is deliberately split into two pieces:

1. `runner/host/runner.py` is a small launcher with Docker CLI access. It is
   a runner-side process, not the FastAPI API process. The application API
   must not mount `/var/run/docker.sock` or receive the Docker client.
2. `runner/container/worker.py` is copied into the digest-pinned image. It
   receives one case only and returns a structured observation. It does not
   contain the trusted oracle, hidden case list, Knodo PAT, application
   session secret, or a student account token.

Build the local image with:

```text
./scripts/build-runner.sh
```

The image build uses `runner/image.lock`, `runner/Dockerfile`, and
`--pull=false`; the base reference is pinned by digest and the worker has no
third-party packages. Run the real Docker acceptance with:

```text
./scripts/runner-live-test.sh
```

The live tests cover correct JSON output, syntax/runtime failure, timeout,
stdout flooding, network denial, read-only root, unsupported request fields,
missing Docker/image fail-closed behavior, and exact project/owner/expired
lease cleanup. Test containers use synthetic code and labels only. The test
cleanup removes only the exact containers it creates; it never invokes
`docker prune`.

The local controls are necessary constraints, not an absolute security
certification. Do not expose this launcher as a public arbitrary-code API
until T28 and deployment review verify the remaining identity, storage,
resource, and operational boundaries.
