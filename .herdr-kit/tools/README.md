# 辅助工具：材料检查和源码比对，不是自动Agent

这些工具只读取文件并向标准输出打印结果，不调用Herdr、模型、数据库，也不修改progress或业务文件。测试只使用临时合成目录。

## 检查包

在项目根目录执行：

```bash
python3 .herdr-kit/tools/verify_package.py
```

验证SHA256、原任务元数据、依赖图、32张对照卡和模板。失败时核对差异，不重新生成原执行包的checksum掩盖变更。本检查不证明用户项目功能通过。

## 查看一项对照卡

```bash
python3 .herdr-kit/tools/task_brief.py T06 --project /home/zxk/Projects/K12
```

带project时比较本地TASKS和当前原卡与参考版本；漂移则停止而不是覆盖。只是打印材料，不确认依赖/预算/审核满足，不实际派工。选择下一任务仍由A读取原progress与有效复核记录完成，可参考既有prompt_helper的只读输出，但不能把它当独立验收。

## 源码范围哈希

先由A从templates/scope.example.json制定本单实际scope，去掉不存在或无关路径，加入受影响公共契约。模板不是自动生产配置。仅对显式目录/文件比对，不允许对整个根目录无范围扫密钥。

```bash
python3 .herdr-kit/tools/scope_manifest.py capture \
  --root /home/zxk/Projects/K12 \
  --scope .herdr-control/本单实际scope.json
```

输出包含选定文件的路径、字节数和SHA256，不含内容。保存到新的、本单唯一manifest文件，不能覆盖旧记录；命令失败或结果未完整时不能引用为有效manifest。源码真正备份仍使用现有受限快照方案，此工具只产生哈希，不备份或恢复代码。

复核前后：

```bash
python3 .herdr-kit/tools/scope_manifest.py verify \
  --root /home/zxk/Projects/K12 \
  --manifest .herdr-control/manifests/本单实际manifest.json
```

退出码0表示选定范围字节未变；1表示发现新增/删除/修改；2表示路径、限额、符号链接或格式错误。跳过.env、私钥、数据库和常见运行目录；如果敏感内容误放进源码，本工具不会自动识别其语义，更不能代替秘密扫描。

哈希只检测范围内变化，不证明程序正确、权限隔离、没有范围外变化，也不能阻止同用户进程绕过协作规则。A仍需读文件清单与实际代码，确认范围足够覆盖此次验收；两Agent必须遵守提交后冻结协议。

## 本工具单元测试

```bash
python3 -m unittest discover -s .herdr-kit/tests -v
```

会在系统临时目录建立合成文件，不触碰用户数据库或现存项目源码。它测试的是这些辅助工具，不是业务应用、Docker隔离或真实Knodo。
