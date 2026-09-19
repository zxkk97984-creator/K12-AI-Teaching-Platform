# 本地开发与隔离测试

目标：在新数据库、端口和卷中运行 `k12r1`，不触碰旧 `shuangling-*`、旧 K12 卷或端口 `5432/6379/9000/9001`。

## 固定边界

| 服务 | 绑定 | 数据库/卷 |
|---|---|---|
| 前端 | `127.0.0.1:15173` | 无 |
| FastAPI | `127.0.0.1:18081` | 开发配置/测试配置显式注入 |
| PostgreSQL 开发 | `127.0.0.1:55433` | `k12r1_dev` / `k12r1-postgres-dev-data` |
| PostgreSQL 测试 | `127.0.0.1:55434` | `k12r1_test` / `k12r1-postgres-test-data` |

## 首次启动

配置只从进程环境读取，不自动读取或覆盖 `.env`。新终端可按 `.env.example` 注入以下占位值：

```bash
export POSTGRES_DEV_PASSWORD='<local-dev-random>'
export POSTGRES_TEST_PASSWORD='<local-test-random>'
export APP_SESSION_SECRET='<at-least-32-random-characters>'
export DATABASE_URL="postgresql+asyncpg://k12r1_app:${POSTGRES_DEV_PASSWORD}@127.0.0.1:55433/k12r1_dev"
export TEST_DATABASE_URL="postgresql+asyncpg://k12r1_test:${POSTGRES_TEST_PASSWORD}@127.0.0.1:55434/k12r1_test"
export APP_ENV=development
./scripts/bootstrap.sh
```

现有临时数据库凭据由 `/tmp/k12r1-t04.env` 保存，模式为 `600`；它不是可提交配置。持久配置/安全恢复仍待用户处理，不得打印连接串或轮换已有卷密码。

脚本不会复制 `.env`、不会覆盖已有 `.env`、不会删除卷，也不会杀掉占用端口的进程。端口被非本项目进程占用时会报冲突。

## 常用命令

```bash
./scripts/doctor.sh
APP_SESSION_SECRET="$APP_SESSION_SECRET" TEST_DATABASE_URL="$TEST_DATABASE_URL" ./scripts/check.sh
./scripts/dev.sh
```

后端测试缺少 `TEST_DATABASE_URL`、URL 不是 `postgresql+asyncpg`、数据库不以 `_test` 结尾、端口不是 `55434` 或缺少专用凭据时会在迁移、清表和 fixture 写入前拒绝启动。

## 请求边界

- `GET /health/live`：只证明进程可响应。
- `GET /health/ready`：执行真实 `SELECT 1`，失败返回 503。
- 错误统一为 `{error:{code,message,request_id,details}}`。
- `X-Request-ID` 由服务接受合法值，否则生成新 ID；日志不得记录 PAT、Cookie、密钥或完整上游正文。

## 当前未实现

课程、教学状态、Knodo 真实调用、runner、发布和人工审校仍未在本阶段实现。身份、会话、四档档案和偏好已在本轮接通。

## T05 身份接口

公共前缀为 `/api/v1`：

- `GET /auth/csrf` 设置非 HttpOnly 的 `sl_csrf` Cookie并返回双提交令牌。
- `POST /auth/login`、`POST /auth/logout`、`PATCH /me/profile`、`PATCH /me/preferences` 必须有精确 `Origin` 和匹配的 `X-CSRF-Token`。
- `GET /me` 从 `sl_session` HttpOnly Cookie 解析服务端会话。
- 档案/偏好 PATCH 必须携带 `base_revision`，冲突返回 409。
- production 要求 `COOKIE_SECURE=true` 且所有 Origin 使用 HTTPS；缺少配置时启动失败。

日常开发：

```bash
APP_ENV=development DATABASE_URL="$DATABASE_URL" APP_SESSION_SECRET="$APP_SESSION_SECRET" ./scripts/dev.sh
```

浏览器身份链路：

```bash
export T05_DEMO_STUDENT_A_USERNAME='demo.student.a'
export T05_DEMO_STUDENT_A_PASSWORD='<synthetic-only>'
export T05_DEMO_STUDENT_B_USERNAME='demo.student.b'
export T05_DEMO_STUDENT_B_PASSWORD='<synthetic-only>'
export T05_DEMO_ADMIN_USERNAME='demo.admin'
export T05_DEMO_ADMIN_PASSWORD='<synthetic-only>'
./scripts/identity-e2e.sh
```

demo 脚本只创建缺失账户，不覆盖已有密码、档案或偏好；production 固定拒绝运行。
