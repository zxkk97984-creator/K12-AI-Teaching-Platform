# 互动 HTML 内容制作与接入

管理端入口：`/admin/resources/interactive`。学生只会看到账号当前学段已发布的内容；小学的“动画讲解”“趣味练习”分别展示 `LESSON` 和 `GAME`，初高中的“互动探索／实验”展示 `EXPERIMENT`。内容作者制作离线 HTML，管理员负责上传、配置问题、预览、人工审校和发布。第一版不执行包内构建命令，也不从 CDN 加载脚本。

## 最小内容包

单个 UTF-8 `.html` 可以直接导入。管理端登记的标题、学段、用途、学科会生成基础清单。它可以运行并使用播放器外侧的预设问题，但无法把 HTML 内部的关卡或输入自动保存；学生可主动标记活动完成。

包含本地素材或要使用 SDK 时，请上传 `.zip`：

```text
manifest.json
index.html
assets/app.js
assets/style.css
assets/cover.svg
audio/prompt-1.mp3
```

清单的固定格式是 `k12-interactive-v1`：

```json
{
  "schema_version": "k12-interactive-v1",
  "content_key": "fractions-interactive-01",
  "title": "分数互动探索",
  "purpose": "LESSON",
  "stage": "PRIMARY_UPPER",
  "subject": "数学",
  "entry": "index.html",
  "cover": "assets/cover.svg",
  "summary": "观察同一个整体被平均分成不同份数后的大小变化。",
  "knowledge_points": ["单位分数"],
  "capabilities": ["SCENES", "CHECKPOINTS", "COMPLETION"],
  "scenes": [
    { "id": "start", "title": "先观察", "summary": "观察平均分成两份和三份时每份的大小。" }
  ],
  "prompts": [
    { "id": "prompt-1", "scene_id": "start", "text": "你发现每一份的大小有什么变化？", "trigger": "SCENE_ENTER", "audio": "audio/prompt-1.mp3" }
  ]
}
```

用途固定为 `LESSON`、`GAME`、`EXPERIMENT`。管理端选择的学段和用途必须与 ZIP 清单一致；清单不会覆盖管理员已经选择的值。版本号由服务端分配。场景 ID、问题 ID 在每个版本中必须唯一。每个场景最多一个 `SCENE_ENTER` 自动问题，其他可标成 `MANUAL`；活动结束后的问题用 `ACTIVITY_COMPLETE`。音频可放入 ZIP，或在尚未发布的版本中单独上传 MP3、OGG、WAV。没有音频时，播放器会寻找可用的中文系统声音；没有声音时保留字幕并明确提示。

## SDK

平台会在包内普通脚本之前注入 `window.K12`，无需从网络下载 SDK。请先等待宿主初始化，再恢复检查点并绑定操作：

```html
<p id="level">准备开始</p>
<button id="next">下一步</button>
<button id="finish">完成</button>
<script>
  function renderLevel(level) {
    document.getElementById("level").textContent = `第 ${level} 关`;
  }
  K12.ready().then((context) => {
    const state = context.gameState || {};
    renderLevel(state.level || 1);
    document.getElementById("next").onclick = async () => {
      await K12.scene.enter("start");
      await K12.checkpoint.save({ level: 2 });
      renderLevel(2);
    };
    document.getElementById("finish").onclick = async () => {
      await K12.complete({ score: 8, maxScore: 10 });
    };
  });
</script>
```

`K12.scene.enter(sceneId)` 通知场景；`K12.narration.play(promptId)` 只请求朗读已保存的问题 ID；`K12.checkpoint.save(jsonObject)` 等待后端提交成功才 resolve；`K12.complete(gameResult)` 原子地保存最后检查点和活动完成事件；`K12.askTeacher()` 打开当前场景桌宠；`K12.assets.url("assets/name.png")` 返回已打包素材的数据 URL，供 JavaScript 动态加载。`K12.narration.onState(listener)` 可订阅朗读状态并返回取消订阅函数。预览环境里 `context.preview === true`；预览保存回执带 `persisted: false`，不得视为学生记录。`K12.ready()` 返回的 `gameState` 只在启用 `CHECKPOINTS` 的内容中可用于恢复。

保存失败时 Promise 会 reject，作者应保留当前内存中的操作状态并允许重试。检查点只接收 JSON 对象，最大 64 KB；不要放音频、图片或大量历史操作。游戏 `score`、`maxScore` 是内容上报的活动结果，不是平台的正式练习成绩。

## 导入、预览与版本

1. 管理端先选默认学段和用途，再选择一个或多个文件。每项可单独改标题、学段、用途、学科；失败项可重试，已成功项不会再次创建。
2. 上传后在版本配置中查看和编辑场景、问题、知识点与摘要。修改后的清单须符合上述格式。问题音频可单独上传并试听。
3. 用桌面和移动预览检查画面、素材、SDK 事件和问题。预览不写学生学习记录。
4. 管理员完成真实人工审校后发布。发布版本锁定；改动问题、音频或 HTML 时上传新版本。已有进行中活动固定使用旧版本，重新开始才使用当前版本。下架后不能启动或继续播放，历史记录保留。

支持普通 HTML/CSS/JavaScript、DOM/SVG/Canvas、本地图片、SVG、字体和音效。多文件需 ZIP；源码工程请先打包成离线可运行内容。HTML 与 CSS 的本地素材会归一化到受限 `srcdoc` 文档，普通脚本和样式保持加载顺序。运行时由 JavaScript 动态拼接的素材路径请改用 `K12.assets.url`。不支持外部接口、CDN、ES module、CSS `@import`、多页跳转、表单、iframe 或需要服务器的应用；导入会明确报错，不会静默发布。上传包上限 20 MB、解压上限 100 MB、最多 500 个文件，并拒绝路径穿越和符号链接。

学生播放失败时，先检查管理端预览与事件列表，确认入口、引用文件、场景 ID 和问题 ID。若保存出现冲突，通常是同一账号另一个标签页已更新该活动；请保留当前页面操作，重新读取远端活动或开始新一轮，不要用旧版本号强行覆盖。宿主消息采用 `k12-interactive-v1`，iframe 无账号 Cookie、CSRF token、下载票据或 Knodo 凭据。
