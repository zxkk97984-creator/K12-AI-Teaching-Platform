# platform/knodo —— Knodo 交付资产（PACKAGED，未部署）

本目录是**本地打包资产**：Tutor/Designer 两类 Bot 的系统提示词、三份 Skill、受控课堂知识包、
Designer 私有边界清单与部署登记。它**不是** Knodo 官方的一键 Bot 导入包，也不代表任何 Skill 已在线加载。

## 状态区分（必须保持）

| 事实 | 本仓现状 |
|---|---|
| 文件已打包（PACKAGED） | 是：`releases/<release_id>/` 内含 ZIP、逐条 SHA256 与 release manifest |
| Bot/Skill 已部署（DEPLOYED） | **否**：`deployment-manifest.json` 中 `deployment_status=NOT_DEPLOYED`、`bot_id=null` |
| 真实租户加载/教学效果 | **未验证**：没有平台执行证据，记为 NOT_RUN |

平台操作步骤见 `docs/integrations/knodo/DEPLOYMENT_GUIDE.md`；Tutor/Designer 资料边界见
`docs/integrations/knodo/ASSET_BOUNDARIES.md`。

## 目录

```
platform/knodo/
  VERSION.json                 包版本 + 契约版本
  contracts/                   T03 冻结契约副本（只读，不改）
  tutor/v1/                    Tutor 系统提示词、Bot profile 与配置说明
  designer/v1/                 Designer 系统提示词、Bot profile、题稿样例（样例只用于校验）
  skills/<name>/               SKILL.md + references/（schema 与冻结契约逐字节一致）
  bundles/classroom/           Tutor 可见课堂知识包（当前只有显式标记的测试内容）
  bundles/designer-private/    Designer 私有边界（本发布不含答案类素材）
  releases/<release_id>/       ZIP + SHA256SUMS + release-manifest.json
  deployment-manifest.json     PACKAGED 与 DEPLOYED 的分界登记
```

## 复现与校验

```bash
python3 scripts/package-knodo.py build-bundles          # 从 curriculum/releases 生成课堂知识包
python3 scripts/package-knodo.py build                  # 生成 ZIP + SHA 清单 + 部署登记
python3 scripts/package-knodo.py verify                 # 安全/哈希/schema/答案边界/部署状态全套校验
python3 scripts/package-knodo.py selftest               # 篡改、越界、绝对路径、密钥注入反例
```

ZIP 是可复现产物：条目顺序、时间戳与压缩级别固定，重复构建字节一致。
