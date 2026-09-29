# Application image: the same Python 3.12 base family as the pinned runner.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/opt/python-site:/app:/app/backend

WORKDIR /app/backend
COPY backend/.venv/lib/python3.12/site-packages /opt/python-site

WORKDIR /app
COPY backend ./backend
COPY curriculum ./curriculum
COPY contracts ./contracts
COPY platform ./platform
COPY runner ./runner
COPY scripts ./scripts

RUN mkdir -p /app/backend/storage/resources /app/backend/storage/authoring
WORKDIR /app/backend

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18081"]
