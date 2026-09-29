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

For the competition demo, build the pinned image and start the loopback control
plane in a separate terminal:

```text
./scripts/build-runner.sh
RUNNER_CONTROL_TOKEN=<local-random-token> ./scripts/codelab-runner-server.sh
```

Configure the API with `CODELAB_RUNNER_URL=http://127.0.0.1:18090` and the same
value as `CODELAB_RUNNER_TOKEN`. The API never receives Docker access. If the
runner is not configured, CodeLab keeps the draft and reports
`RUNNER_UNAVAILABLE`; that state is a platform failure and is not counted as a
student mistake.
