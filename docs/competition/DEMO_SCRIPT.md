# 演示脚本（合成数据、无付费调用）

## 开始前

    ./scripts/bootstrap.sh

演示账号只在 development/test profile 使用，密码从安全环境注入；不把真实学生或 PAT 放入
命令、浏览器、截图或报告。若需要真实 Docker CodeLab，另启 T24 loopback runner；否则页面
会如实显示 runner unavailable。

## 建议顺序

1. 打开 /settings：展示 session、四档 profile、CSRF/owner 边界。
2. 打开 /courses → /lessons：进入章节，观察 fixture Tutor 卡、phase/lifecycle、暂停/恢复、
   活动与刷新恢复；强调这是本地 fixture，不是 Knodo 真实教师。
3. 打开 /practice：答错、提示、再答、刷新；展示服务端快照和确定性结果。
4. 打开 /resources：用 T20 合成 Word/PPT/video 展示下载、视频播放、stage 过滤和撤回后旧入口失效。
5. 打开 /animations：在 development/test profile 选择明确标注的合成 fixture，展示单步/暂停/重置、
   文字替代说明和低动效；正式 profile 若没有 human-approved senior chapter，展示“没有已发布动画”的
   fail-closed 空态，不把 fixture 当正式内容。
6. 打开 /code?task=temperature-converter：错误实现 → PARTIAL/10 → 修正 →真实 Docker runner
   PASSED/70 → fixture feedback；强调 AI feedback 不改 deterministic score。
7. 打开 /growth 和 /learn：展示证据、记忆确认/质疑/遗忘、下一步投影；不展示掌握度百分比或排行榜。
8. 如需异常演示：停止 runner 看 UNAVAILABLE；换账号看不到对方 draft/run；用无 CSRF 删除请求得到 403。

## 评委复现入口

- 离线全回归：PYTHONPATH=. backend/.venv/bin/pytest backend/tests -q
- 前端：npm test --prefix frontend && npm run typecheck --prefix frontend && npm run build --prefix frontend
- 浏览器：scripts/verify.sh（需本机合成账号和 T22 revision）
- 真实 sandbox：./scripts/runner-live-test.sh
- 平台 live：当前必须停在门禁说明，scripts/verify-live.sh 会 fail-closed。

## 不可宣称

不能宣称已接入真实 Knodo、已验证真实成本/usage、已完成四档人工审校、已开放真实未成年人、
已证明学习效果、已完成平台删除或绝对安全。
