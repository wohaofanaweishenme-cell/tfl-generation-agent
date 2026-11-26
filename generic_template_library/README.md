# Generic TFL Template Library v1.0.0

由 6 个 Study 的 431 份来源 Shell（`../Library/`，只读）归纳出的通用模板库。规则见 `00_CONVENTIONS_v1.0.md`。

**状态：16 个模板、66 个 Preset 和 House Style Guide 已于 2026-11-26 经项目负责人批准（v1.0.0）**。批准记录见 `approvals/Approval_Record.json`。

## 目录与分工

```
Generic_Template_Build/
├─ README.md、00_CONVENTIONS_v1.0.md
│
├─ TFL_Template_Library/            给人看：只放 DOCX，每个"模板 + Preset"一份（66 份）
│   ├─ table/     TBL_<模板>__<preset>.docx（32）
│   ├─ listing/   LST_SUBJECT_RECORDS__<preset>.docx（23）
│   └─ figure/    FIG_<模板>__<preset>.docx（11）
│
├─ templates/ presets/ style/ vocab/   真值（JSON）：唯一允许编辑的地方
├─ schemas/                         Shell Spec、Template、Preset、Study Settings 的结构定义
├─ Template_Index.json              给 Agent 读：模板摘要 + 参考 DOCX 路径与哈希（自动生成）
├─ Keyword_Index.json               关键词 / 别名倒排索引（自动生成）
├─ Library_Bundle.json              全库合成一个文件（自动生成）
├─ approvals/                       批准记录（含每个文件的 SHA-256）
├─ reference/                       参考 DOCX 用的中性设置、生成清单和对应的 Shell Spec
│
├─ renderer/  tools/  .venv/        代码与环境
├─ inventory/                       阶段 1–2：来源签名、归类、非标准来源
├─ examples/                        示例输入与生成结果（stage4 为当前版本）
└─ qa/                              各阶段报告、渲染预览、匹配评估
```

## 三条规则

1. **JSON 是真值，DOCX 是派生的**。`TFL_Template_Library/` 里的文件由 `tools/build_reference_library.py` 生成，不手改；要改就改 JSON，再重新生成。
2. **批准即锁定**。批准后任何模板、Preset 或 Style Guide 的改动，都会让 `tools/build_index.py` 报错（哈希与批准记录不一致）。修改后必须重新审阅，并运行 `tools/record_approval.py` 记录新的批准。
3. **批准的范围**：
   - 批准的是模板结构、边界、必填字段、配置项、模板自带的脚注和 Programming Note（批准的展示惯例，生成时标 resolved），以及 Preset 作为"候选内容"。
   - Preset 里的变量、类别、字段清单在每个研究中仍标 needs_review，需由该研究确认。
   - 分析定义（分母、删失、比较方法、字典版本等）在研究设置提供之前始终是 unresolved。

## 参考 DOCX 怎么读

参考 Shell 使用 `reference/Reference_Study_Settings.json`：组名为 `[Treatment A]` / `[Treatment B]`、有 Total 列、不含任何研究定义。因此 DOCX 中的黄色 `<<UNRESOLVED …>>` 正好是**每个研究必须提供的信息**。编号统一为 `x.x.x`。

## 首次使用

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
```

工具会按以下顺序查找原始来源 Library（只读）：
1. 环境变量 `TFL_SOURCE_LIBRARY`；
2. 同级目录 `../library`（GitHub 仓库中的布局）；
3. 同级目录 `../Library`（本地工作区）。

只使用模板、生成 Shell 时不需要原始 Library。只有 `generate.py`（读取 content list）、`evaluate_matching.py` 和阶段 1 的脚本需要它。

渲染预览需要 LibreOffice（`soffice`）和 poppler（`pdftoppm`），可以用 `SOFFICE=`、`POPPLER_BIN=` 指定路径。

## 常用命令（在本目录下）

```sh
.venv/bin/python tools/build_index.py                  # 校验（含批准哈希）并生成索引
.venv/bin/python tools/build_reference_library.py      # 重新生成 TFL_Template_Library/
.venv/bin/python tools/generate.py --entries examples/inputs/example_entries.json --out examples/stage4
.venv/bin/python tools/generate.py --entries examples/inputs/example_entries.json --out examples/stage4 --answers --round 2
sh tools/render_check.sh examples/stage4 qa/stage4_render
cd tools && ../.venv/bin/python evaluate_matching.py
```

修改模板后的顺序：
1. 改 JSON；
2. `sync_template_evidence.py`（仅当归类变化时）；
3. 审阅；
4. `record_approval.py`；
5. `build_reference_library.py`；
6. `build_index.py`。

环境：`.venv`（Python 3.12，依赖版本见 `requirements.lock.txt`）。渲染预览使用本机已有的 LibreOffice，未在 Microsoft Word 中核对。
