# ADR-006：本地身份、会话 Cookie 与 CSRF

状态：ACCEPTED  
日期：2026-09-18

## 决策

- 本地 `/api/v1` 身份接口固定为 `GET /auth/csrf`、`POST /auth/login`、`POST /auth/logout`、`GET /me`、`PATCH /me/profile`、`PATCH /me/preferences`。
- 会话 Cookie 名为 `sl_session`，属性为 `HttpOnly; SameSite=Lax; Path=/`；生产必须 `Secure`。会话原始令牌不落库，只保存 SHA-256 哈希、用户归属、有效期与撤销状态。
- CSRF 采用双提交 Cookie + 请求头：`sl_csrf` 为非 HttpOnly Cookie，写请求必须带相等 `X-CSRF-Token`。
- 所有 `/api/v1` 非安全方法必须有精确匹配允许列表的 `Origin`；缺失、`null`、恶意 Origin 一律拒绝，不信任 `Referer` 或任意 `X-Forwarded-*`。
- `user_id`、`role`、`is_admin` 不接受客户端提供；权限从服务端会话关联的用户记录读取。
- `profile_revision` 是档案/偏好的并发版本。PATCH 必须携带 `base_revision`，不匹配返回 409，不在冲突后部分覆盖。
- `grade` 可空；未选年级时返回 `null`，不推导虚构年级。`stage` 是四档枚举，有 grade 时必须与 stage 一致。
- 语音偏好只记录用户意图；在真实 ASR/TTS 验证前，能力状态仍为不可用。

## 开发例外

仅 `APP_ENV=development/test` 允许 `COOKIE_SECURE=false`。`APP_ENV=production` 缺少安全 Cookie 或 HTTPS Origin 时启动失败，不能静默降级。
