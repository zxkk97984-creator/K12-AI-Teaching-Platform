# T24: the base is pinned by digest, not a mutable latest tag.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ENV PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

RUN addgroup --gid 65532 --system runner \
    && adduser --uid 65532 --gid 65532 --system --disabled-password runner

WORKDIR /runner
COPY --chown=65532:65532 container/worker.py /runner/worker.py
USER 65532:65532

ENTRYPOINT ["python", "/runner/worker.py"]
