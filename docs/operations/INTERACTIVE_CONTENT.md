# 互动 HTML 内容制作与接入

管理端入口：`/admin/resources/interactive`。学生可见内容按账号学段与服务端状态筛选；本地比赛模式还支持管理员显式开启的本地演示内容。小学的“动画讲解”“趣味练习”分别展示 `LESSON` 和 `GAME`，初高中的“互动探索／实验”展示 `EXPERIMENT`。内容作者制作离线 HTML，管理员负责上传、配置问题、预览、人工审校和发布。第一版不执行包内构建命令，也不从 CDN 加载脚本。

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

用途固定为 `LESSON`、`GAME`、`EXPERIMENT`。管理端选择的学段和用途必须与 ZIP 清单一致；清单不会覆盖管理员已经选择的值。版本号由服务端分配。场景 ID、问题 ID 在每个版本中必须唯一。每个场景最多一个 `SCENE_ENTER` 自动问题，其他可标成 `MANUAL`；活动结束后的问题用 `ACTIVITY_COMPLETE`。音频可放入 ZIP，或在尚未发布的版本中单独上传 MP3、OGG、WAV。没有音频时，播放器优先使用可用的普通话声音；声音下拉框按普通话、粤语及其他声音分组，手动选择按账号保存在当前浏览器。默认不会自动选择粤语；没有普通话或记住的声音不可用时明确提示，保留文字。绑定音频的段落使用课件音频，声音选择不可修改该音频的音色。

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

`K12.scene.enter(sceneId)` 通知场景；`K12.narration.play(promptId)` 只请求朗读已保存的问题 ID；`K12.checkpoint.save(jsonObject)` 等待后端提交成功才 resolve；`K12.complete(gameResult)` 原子地保存最后检查点和活动完成事件；`K12.askTeacher()` 打开当前场景的统一问老师面板；`K12.assets.url("assets/name.png")` 返回已打包素材的数据 URL，供 JavaScript 动态加载。`K12.narration.onState(listener)` 可订阅朗读状态并返回取消订阅函数。预览环境里 `context.preview === true`；预览保存回执带 `persisted: false`，不得视为学生记录。`K12.ready()` 返回的 `gameState` 只在启用 `CHECKPOINTS` 的内容中可用于恢复。

保存失败时 Promise 会 reject，作者应保留当前内存中的操作状态并允许重试。检查点只接收 JSON 对象，最大 64 KB；不要放音频、图片或大量历史操作。游戏 `score`、`maxScore` 是内容上报的活动结果，不是平台的正式练习成绩。

## 导入、预览与版本

1. 管理端先选默认学段和用途，再选择一个或多个文件。每项可单独改标题、学段、用途、学科；失败项可重试，已成功项不会再次创建。
2. 上传后在版本配置中查看和编辑场景、问题、知识点与摘要。修改后的清单须符合上述格式。问题音频可单独上传并试听。
3. 用桌面和移动预览检查画面、素材、SDK 事件和问题。预览不写学生学习记录。
4. 管理员完成真实人工审校后发布。发布版本锁定；改动问题、音频或 HTML 时上传新版本。已有进行中活动固定使用旧版本，重新开始才使用当前版本。下架后不能启动或继续播放，历史记录保留。

支持普通 HTML/CSS/JavaScript、DOM/SVG/Canvas、本地图片、SVG、字体和音效。多文件需 ZIP；源码工程请先打包成离线可运行内容。HTML 与 CSS 的本地素材会归一化到受限 `srcdoc` 文档，普通脚本和样式保持加载顺序。运行时由 JavaScript 动态拼接的素材路径请改用 `K12.assets.url`。不支持外部接口、CDN、ES module、CSS `@import`、多页跳转、表单、iframe 或需要服务器的应用；导入会明确报错，不会静默发布。上传包上限 20 MB、解压上限 100 MB、最多 500 个文件，并拒绝路径穿越和符号链接。

学生播放失败时，先检查管理端预览与事件列表，确认入口、引用文件、场景 ID 和问题 ID。若保存出现冲突，通常是同一账号另一个标签页已更新该活动；请保留当前页面操作，重新读取远端活动或开始新一轮，不要用旧版本号强行覆盖。宿主消息采用 `k12-interactive-v1`，iframe 无账号 Cookie、CSRF token、下载票据或 Knodo 凭据。

## 内置知识讲解与台词编辑

`./k12 setup` 导入四个 HTML 讲解、一款 AI 通识小游戏及关联课程。四个讲解分别是：小学低段 AI 认图片、小学高段二进制卡片、初中条件与循环、高中二分查找。
内容源在 `curriculum/interactive/computing-ai-v1/`；公共样式和宿主控制脚本随内容包打包为离线素材。
重复导入沿用已有资源和版本，不覆盖管理端已编辑的同一内容包。

在互动内容管理中选择版本，点击“复制为可编辑版本”，修改清单中的 `prompts[].text`，保存、预览后设为当前版本。
修改 HTML 时使用“上传新 HTML／ZIP 版本”。进行中的学生活动继续使用原版本；重新开始后使用当前版本。

本地演示需要批量切换已有进度时，可在加载本机配置及项目 Python 路径后运行 `python -m app.scripts.upgrade_interactive_sessions` 查看兼容性，再加 `--apply --backup <仓库外私有目录>/before.json` 执行。此维护命令仅处理场景、讲解与功能定义一致的已核对课件；实验还会核对恢复逻辑和保存参数。它保留原活动与事件，创建继承当前环节、实验参数的新版活动；已结束记录不变。执行后刷新学习页即可续学，不会在项目重启或内容导入时自动迁移。
“本地比赛演示可见”开关可用于本机展示，下架仍会阻止继续访问；它不改变审核结果。

学生点击“开始学习”或“继续学习”后，本环节的 `SCENE_ENTER` 讲解自动播放一次；此动作仅开启当前工作区朗读，不修改全局语音偏好，也不开启麦克风。静音时跳过声音，没有预设进入讲解时不自动播放。面板切换、专注模式和页面重绘不重复触发。系统 Chrome／Edge 需要有可用中文声音；没有声音或播放失败时保留字幕并给出提示。
`K12.narration.onState(listener)` 接收 `{status, prompt_id, subtitle}`，状态为 idle/loading/speaking/paused/ended/unavailable/error；
HTML 可在 speaking 时强调当前画面。桌宠说话状态跟随真实语音事件，固定台词不调用 Knodo 生成。

AI 认图片支持一键自动演示，开始或继续学习后从当前环节连续播放；二进制卡片也可点击“自动播放”。每段先展示对应画面，再朗读，收到本段 `ended` 后停留片刻进入下一段，语速调整自然影响该段停留时间。暂停、打开教师或隐藏页面会停止推进，继续时重播当前段。没有可用声音、音频失败或静音时，明确提示并按字幕阅读时间播放。演示结束保留最后画面，不自动完成课程；“自己试一试”恢复手动实验状态。自动演示的样例操作不写入检查点。

在这两个课件的 `activity.js` 中，`demonstrations` 按讲解 ID 提供画面状态；新增自动讲解可以沿用公共 `bootstrap.js`，在 `manifest.json` 中为每段提供相应 `scene_id` 与讲解。先让画面与讲解保持段落级对应，不用猜测语音时长去截断朗读。

浏览器回归使用隔离测试库与 fixture：先运行 `./k12 check`，再运行 `./scripts/test-learning-browser.sh`。该脚本使用临时端口 18082／15174、隔离测试库与本地测试素材目录，结束后停止自身服务；不要与后端 pytest 并发运行。
合成接口回归继续使用 `npm run test:e2e:ui --prefix frontend`；声音实播应单独在目标系统浏览器验收。

## 内置 AI 通识小游戏

“趣味练习”包含小学 1—3 年级的 **训练小小 AI·水果分类员**，绑定《人工智能启蒙》第 3 课。三关依次体验贴标签、补充不同样例和纠正错误标签；先观察误判，再改进并重新测试，最后主动领取徽章确认完成。

源码在 `curriculum/interactive/computing-ai-v1/ai-fruit-trainer/`。`index.html` 内联所有样式、脚本和 SVG，可直接离线打开；独立模式只保留当前页面的进度。平台模式通过现有 SDK 保存、恢复操作并提供朗读与问老师。分类使用预设颜色、形状特征的最近邻教学模拟，测试图卡与训练图卡分开，不代表真实图片识别模型或正式练习成绩。

`./k12 setup` 会导入该游戏。已有本机环境只补充这个资源时，在仓库根目录运行：

```bash
. scripts/load-runtime-env.sh
export PYTHONPATH="$PWD:$PWD/backend${PYTHONPATH:+:$PYTHONPATH}"
uv run --project backend --locked python -m app.scripts.import_learning_activities --content-key game-ai-fruit-trainer
```

重复导入沿用已存在的版本和管理员修改的台词；此命令不导入其他互动资源。刷新 `/practice` 后从游戏卡片进入。

## 学习工作区与旧课件兼容

学生播放器现在提供紧凑课程栏、环节导航、可收起的“本步讲解”面板与随桌宠定位的教师浮窗和一套朗读控制。底部朗读栏默认只显示播放、重播、简短状态和设置入口；声音、语速、静音在“声音设置”浮层中调整，学习操作按需展开，不挤压画布。浮层支持 Esc 或点击外侧关闭，小游戏默认收起右侧讲解，可点击“本步讲解”打开。“专注模式”只改变布局，不重新加载 iframe。长课件由画布内部滚动；窄屏讲解使用抽屉，教师浮窗沿用桌宠的屏幕边界适配。朗读结束、循环结束与课程完成分别处理，课程完成仍需明确操作。

四个内置课件在可用宿主中使用嵌入模式；不支持接管的历史 HTML 保留其内部控件。作者可在 `K12.ready()` 后调用可选接口：

- `K12.workspace.register(["scene", "pause", "reset", "complete"], async command => ...)` 注册实际支持的宿主命令。收到的对象包含 `command`，切换环节时还包含 `scene_id`。注册回执 `embedded === true` 才能隐藏被宿主接管的页面级控件；回执 `theme` 仅包含展示变量。
- `K12.workspace.report({scene_id, game_state, hint})` 汇报当前实验与简短提示，不代替 `K12.checkpoint.save()`；保存状态必须以检查点回执为准。
- `K12.workspace.onSession(listener)` 接收已确认的 `{scene_id}`，用于协调宿主导航和内部画面。

支持自动播放的内容可额外注册 `demonstrate` 命令，并将第三个参数设为 `{playback_steps: [{scene_id, prompt_id}, ...]}`。每段必须对应清单中同一场景的讲解，最多 100 段。宿主按顺序切换场景、发送 `{command: "demonstrate", prompt_id}` 展示画面，再播放保存的讲解；`prompt_id: null` 表示回到手动操作。只在确实实现演示逻辑时注册此命令，旧课件可继续保留原来的四项命令。

底层消息沿用 `k12-interactive-v1`，新增 `workspace_ready`、`activity_state`、`command_result`；宿主下发 `workspace_command`、`workspace_state`。消息校验当前窗口、不透明源、实例、会话、版本及数据结构，保留原 sandbox 和 CSP。不要向 iframe 发送账号凭据。原 SDK 接口和 manifest 格式不变。

问老师复用平台教师会话与草稿，桌宠可以自由拖动并记住位置，弹窗随桌宠重新定位；右侧讲解不再同时渲染聊天。发送前保存当前操作，后端从学生自己的活动读取实验状态，并标注为课件上报数据；它不是 runner 的执行验证。系统声音不可用或音频失败时仍可阅读文字和操作课件。声音与语速调整在下次播放生效；没有可靠时间戳时只使用段落级状态。

本机升级内置课件可使用 `python -m app.scripts.import_learning_activities --upgrade-from <已备份的旧课件源目录>`，运行前加载本机配置与项目 Python 路径。升级仅接管匹配内置模板的资源，保留当前清单编辑和音频，并创建、启用新版本；自定义脚本或结构不兼容时跳过。旧锁定文档和进行中的活动继续使用原版本，重新开始才切换新版。

浏览器回归继续运行 `./scripts/test-learning-browser.sh`，可附加 Playwright 参数筛选场景。覆盖四学段、五种窗口、Chrome 原生 200% 缩放、问答返回、保存失败恢复、确认重置、完成和退出。测试音频是用于验证真实媒体事件的本地 WAV；fixture 问答不代表真实 Knodo 返回。截图与声音能力记录位于 `frontend/test-results/learning-content-browser/`。
