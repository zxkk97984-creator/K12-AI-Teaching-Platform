# 霜铃 K12 自动播放教学样例 v1

本目录包含四档学段各 3 个、共 12 个离线教学动画样例。内容用于 K12 比赛演示和交互内容接入，不代表正式课程认证，也没有教学效果验证结论。

## 样例目录

| 学段 | 文件标识与标题 | 建议年级 | 主要学习目标 |
|---|---|---:|---|
| 小学低段 `PRIMARY_LOWER` | `input-process-output` · 小机器人收到指令以后会做什么 | 1—3 | 理解输入、按规则处理、输出结果的顺序。 |
| 小学低段 `PRIMARY_LOWER` | `sorting-by-rule` · 给图形找家：按规则分类 | 1—3 | 先明确规则，再按形状或颜色分组。 |
| 小学低段 `PRIMARY_LOWER` | `robot-instructions` · 箭头指令带机器人走到终点 | 1—3 | 观察指令顺序、逐格移动，以及遇障停止。 |
| 小学高段 `PRIMARY_UPPER` | `pixels-build-picture` · 小方格怎样组成一张图片 | 4—6 | 用同一颜色矩阵比较像素网格、局部细节和信息量。 |
| 小学高段 `PRIMARY_UPPER` | `cards-bubble-sort` · 数字卡片怎样排整齐 | 4—6 | 逐次比较相邻数字，需要时交换，得到升序结果。 |
| 小学高段 `PRIMARY_UPPER` | `message-packets` · 一条消息怎样通过网络送出去 | 4—6 | 观察发送、编号分块、传输、接收和重组。 |
| 初中 `JUNIOR` | `linear-search` · 从一排数据中找到目标：线性查找 | 7—9 | 按序比较数据，区分第几项与下标，并识别未命中。 |
| 初中 `JUNIOR` | `stack-and-queue` · 叠盘子和排队：栈与队列 | 7—9 | 比较栈的后进先出与队列的先进先出。 |
| 初中 `JUNIOR` | `training-and-testing` · 为什么学习样例和检查样例要分开 | 7—9 | 用最近邻规则预测独立测试点，再揭示真实类别。 |
| 高中 `SENIOR` | `shortest-path` · 怎样找到总路程最短的路线 | 10—12 | 通过非负边权、候选距离和前驱更新执行 Dijkstra。 |
| 高中 `SENIOR` | `gradient-descent` · 梯度下降怎样一步步靠近最低点 | 10—12 | 用公式更新 `f(x)=x²`，比较小步长与过大步长。 |
| 高中 `SENIOR` | `classification-metrics` · 分类模型的误报与漏报 | 10—12 | 用合成邮件样例计算混淆矩阵、准确率、精确率和召回率。 |

各样例的知识点、摘要、单文件路径、ZIP 路径和验证状态见 [catalog.json](catalog.json)。

## 打开课件

- 双击 [preview.html](preview.html) 打开本地目录；每张封面和“打开课件”链接都直接指向独立 HTML，不使用 iframe。
- 也可以直接打开 `standalone/<学段目录>/<文件标识>.html`。例如：`standalone/primary-lower/input-process-output.html`。
- 可选静态 HTTP 方式：在本目录运行 `python3 -m http.server 8000 --bind 127.0.0.1`，打开 `http://127.0.0.1:8000/preview.html`。
- 单文件 HTML 内联了 CSS、JavaScript、SVG 与课程场景，不需要 Node.js、npm、CDN、外部字体、联网服务或本地素材目录。

点击一次“开始播放”后，课件先展示当前场景，再逐段朗读；真实浏览器语音的 `end` 事件驱动有声场景推进。设备没有普通话声音、朗读接口不可用或选择静音时，课件显示原因并按字幕长度估算阅读时间继续。静音模式不会显示“正在朗读”。播放结束保留总结画面，不循环、不提交完成状态或成绩。按钮支持暂停、继续（从当前段开头重读）、重播本段、从头播放和“自己试一试”。

浏览器可能有或没有 `zh-CN` / `zh-Hans` 普通话声音；语音和语速使用设备浏览器能力。慢、正常、快和静音设置会从下一段开始生效。所有课件都可在完全无声时通过字幕继续观看。

## 平台内容包

`packages/` 下有 12 个 ZIP，每包根目录包含 `manifest.json`、`index.html` 和 `assets/cover.svg`。包内 `index.html` 与相同样例的独立 HTML 字节一致。12 个清单均使用 `purpose: "LESSON"`，并为每个教学场景生成一个 `SCENE_ENTER` 讲解；不含虚构课程 UUID、章节 UUID、音频路径或服务器资源 ID。

在霜铃平台互动内容管理中选择相应学段和 `LESSON` 用途后上传 ZIP。后续课程/章节关联在平台接入时指定。独立模式使用课件自己的播放控制器；平台返回 `embedded: true` 后由宿主接管场景、朗读和暂停，课件不会启动第二套语音或场景计时器。手动实践与自动演示状态分开保存在当前页面会话内，不调用 `K12.checkpoint.save`、`K12.complete`，也不生成练习成绩。

平台当前入口有学段差异：小学低段自动课件可在“开始学习”后由宿主直接进入自动播放；其他学段由宿主的“自动播放”按钮启动连续演示。四档单文件独立版都可在课件内点击一次“开始播放”连续观看。

平台内嵌播放会按可用高度分配绘图区和字幕区，图形随窗口缩放并完整显示。较矮窗口与手动实践使用自然滚动布局。已开始的学习活动保留原课件版本；更新包后，从“学习操作 → 重新开始学习”进入新版，旧活动记录仍保留。

本批 ZIP 使用当前仓库包解析器导入本机开发平台，四档各 3 个资源；本地演示可见，审核状态仍为未人工审校。独立模式的历史检查与平台播放检查分别记录。

## 内容边界

场景数据和讲解台词由同一份 `LessonDefinition` 生成。计算状态先由算法实际计算，再交给统一 SVG/DOM 播放器绘制；目录、独立 HTML 与 ZIP 清单从同一份定义生成。分组、像素矩阵、排序、查找、最近邻、Dijkstra、梯度下降和分类指标均为小型教学模型。

最近邻数据、邮件编号、分数和路线均为合成样例。网络课件不发起真实网络请求。课件不执行学生代码，不访问数据库，不保存账号数据，不产生正式成绩。讲解只覆盖画面实际展示的范围。

## 验证记录

- [静态与内容包检查](test-results/static-validation.md)：12 个样例、四档各 3 个；368 项检查通过，包括 ZIP 结构与限制、manifest/prompt 引用、无外部资源、目录链接、算法结果，以及当前仓库包解析器和 HTML 构建器。
- [浏览器检查](test-results/browser-validation.md)：Google Chrome 154；470 项检查通过。每个样例检查了 `320×568`、`390×844`、`768×1024`、`1366×768`，包含页面溢出、初始开始入口、播放控制可见性、暂停/继续/重播/从头播放、隐藏页暂停、可选实践和无声自动完成；保留 41 张桌面、关键步骤和低段手机截图。
- 浏览器回归的朗读 `start/end` 是合成事件，用来验证事件同步逻辑，不是真实发声证据。静音计时在全量自动化中被加速；独立浏览器观察确认设备没有普通话声音时显示无声提示并继续。当前环境没有听到真实中文 TTS，所以不宣称中文实播通过。本批没有媒体音频。
- K12 宿主命令用本地合成 SDK mock 检查了 `scene`、`demonstrate`、`demonstrate(prompt_id: null)`、`pause`、手动状态恢复和避免双重朗读。这是原交付的独立模式记录。本次已完成四档、十二课件的真实平台宿主回归，覆盖目录可见、播放、暂停、刷新续学、手动实践与三种平台窗口尺寸。声音事件仍为合成事件，未验证真实中文发声。

## 重新生成

在本目录运行 `python3 source/build.py`。该脚本使用 Python 标准库，根据 `source/build.py` 中的场景定义和算法重新生成 12 个独立 HTML、12 个 ZIP、封面、`catalog.json` 和 `preview.html`。共用播放与绘图逻辑位于 `source/runtime.js`。

可选的静态检查命令（需使用本仓库后端虚拟环境，因为它调用平台包解析器）：

```bash
../backend/.venv/bin/python source/verify.py
```

浏览器回归脚本 `source/browser-check.cjs` 是开发检查工具，不是课件运行依赖；它需要系统 Chrome 和 Playwright。报告及截图写入 `test-results/`。

## 本机接入与重复导入

从仓库根目录加载本机运行配置后执行：

```bash
source scripts/load-runtime-env.sh
export APP_ENV=development PYTHONPATH="$PWD:$PWD/backend"
uv run --project backend --locked python -m app.scripts.import_learning_activities --examples-root "$PWD/k12-autoplay-examples-v1"
```

使用 `/animations` 查看当前账号所属学段的三份新讲解。重复导入复用相同包；已编辑的当前版本会跳过，原有课件和学习记录保留。手动实践仅保留在当前页面内，刷新后不声称账号已经保存实验参数。宿主保存课程环节，HTML 初始化承接该场景。ZIP 使用固定时间戳，重复生成不会仅因打包时间产生新版本。

平台回归：`K12_AUTOPLAY_EXAMPLES_E2E=1 ./scripts/test-learning-browser.sh --grep "imported autoplay examples"`，使用隔离测试库。四个学段场景全部通过，每个场景验证三份课件；截图与本次验证记录位于 `frontend/test-results/autoplay-examples-platform/`。
