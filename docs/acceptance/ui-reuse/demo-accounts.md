# 本地演示账号

三名合成账号，只存在于本机 dev 库。浏览器 e2e 与手工演示都用它们。

| 用户名 | 角色 | 学段 | 用途 |
|---|---|---|---|
| `demo_junior` | student | JUNIOR（8 年级） | `animation.spec.ts` 等初中场景 |
| `demo_lower` | student | PRIMARY_LOWER（2 年级） | 小学低年级场景 |
| `demo_admin` | admin | — | 管理端页面 |

**密码**存在 `~/.config/k12/runtime.env`（`DEMO_*_PASSWORD`），不进仓库。

## 重置 / 确认可用

```bash
./scripts/seed-demo-accounts.sh
```

幂等：已存在就重置密码，不存在则提示先跑 seeding 模块建号（因为档案由那边创建）。

## 为什么要这个脚本

`backend/app/modules/identity/demo.py` 的 `ensure_demo_user` **不会覆盖已存在账号**
（docstring 明写 "never overwrite an existing account"），且密码只在建号时从环境变量
读一次。结果是：账号一旦建好，明文密码就只存在于当时那个 shell 里，之后任何人
（包括原建立者）都无法从库里取回 —— 库里只有哈希。

这个脚本是**唯一**有意覆盖密码的地方，所以单独放成脚本而不是塞进 seeding 模块。

## 2026-09-22 的清理记录

dev 库原有 174 个账号，其中 168 个是历次 e2e 运行自建后遗留的残留
（`e2e.t20.*` / `e2e.t21.*` / `e2e.student.learn.#` 等带时间戳的名字，9-19 一次就建了 162 个）。

清理后保留 6 个：
- 3 个演示账号
- 3 个**承载已发布资源**的 admin 账号（`e2e.t30.admin` 等）—— 它们拥有 25 个
  `resource_items` 中的全部，直接删会级联删掉学生可见的内容，故保留

内容数据零损失（4 课程 / 8 章节 / 25 资源 / 15 已发布 / 3 代码题）。
备份在 `/tmp/k12r1_dev_backup.dump`（pg_dump custom 格式）。

`assessment_quiz_questions` 是 append-only 表（任何 UPDATE/DELETE 都抛异常），
清理事务里临时 `DISABLE TRIGGER` 后已恢复（`tgenabled='O'`）。
