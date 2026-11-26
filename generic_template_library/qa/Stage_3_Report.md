# 阶段 3 报告：统一 Schema、试点模板与端到端试跑

日期：2026-11-24　依据：`00_CONVENTIONS_v1.0.md` §4–§9、§10；阶段 2 决策 Q1–Q9 按建议执行
状态：试点完成，待你查看样例 Shell 后决定是否进入阶段 4（铺开其余 13 个模板）

## 1 新增内容

| 类别 | 文件 | 说明 |
|---|---|---|
| Schema | `schemas/Shell_Spec.schema.json` | 统一 Shell Spec v3.0：Table/Listing/Figure 共用；每个可替换元素都是 Slot，记录 `source` 和 `status`；`unresolved` 必须带问题编号 |
| | `schemas/Template.schema.json` | 模板定义：用途、不适用、关键词、匹配线索、必填字段、允许默认值、可编辑元素、配置项、Preset、骨架、证据；Figure 另含 `figure_plot` 绘图契约 |
| | `schemas/Preset.schema.json` | 主题预设：只提供内容默认值，不改结构 |
| | `schemas/Study_Settings.schema.json` | 用户确认的研究设置：组别、Total 列、人群、访视、编码字典版本、分析定义、时间单位 |
| Style | `style/House_Style_Guide.json` + `.md` | D3–D8、D11 的落地：占位符、统计量格式、小数位、脚注顺序、Programming Note 样式、页面、Bookmark 命名 |
| 模板 | `templates/table/TBL_VARIABLE_SUMMARY.json` | 26 份来源 / 6 Study |
| | `templates/table/TBL_CODED_TERM_HIERARCHY.json` | 34 份来源 / 6 Study |
| | `templates/figure/FIG_KAPLAN_MEIER.json` | 3 份来源 / 3 Study；`implementation_status: shell_only` |
| Preset | `presets/<模板>/*.json`，共 7 个 | demographics、exposure_compliance；teae_soc_pt、medical_history_soc_pt、prior_concomitant_medications；overall_survival、event_free_time |
| 词表 | `vocab/Keywords.json` | 受控关键词 |
| 索引（自动生成） | `Template_Index.json`、`Keyword_Index.json`、`Library_Bundle.json` | 由 `tools/build_index.py` 生成并校验，不手改 |
| 工具 | `tools/sync_template_evidence.py` | 从阶段 2 审定的归类表同步各模板的 evidence |
| | `tools/build_index.py` | Schema 校验 + 关键词在词表中 + evidence 来源存在 + Preset 互相对应；通过后生成三份索引 |
| | `tools/build_spec.py` | 规则版"选模板 + 填 Spec"（Agent 的基线）：匹配并解释理由；逐元素标注来源；缺失的研究信息变成 unresolved 和问题，不编造 |
| | `tools/run_pilot.py` | 端到端试跑；输出 Spec、DOCX、Output_Inventory、Clarification_Log |
| | `tools/render_check.sh` | DOCX → PDF → PNG，用于目视检查 |
| Renderer | `renderer/common.py`、`render_table.py`、`render_figure.py`、`figure/plot_km.py` | Table、Figure 各一个通用渲染器，只读 Shell Spec，没有按模板写的代码；KM 绘图函数为 `plot(spec, data=None)` |
| 环境 | `.venv/`、`requirements.lock.txt` | 项目内 Python 3.12 环境：python-docx 1.2.0、matplotlib 3.11.2、jsonschema 4.26.0 |

## 2 端到端试跑结果

输入为 3 个 Study 的 10 条真实 content list 条目（从 Library 只读）；研究设置是根据各自来源 Shell 抄写的试点样例，**不是**用户确认的设置，文件中已注明。

| Study | 编号 | 标题（节选） | 结果 | 模板 / Preset | 待审元素 | unresolved |
|---|---|---|---|---|---:|---:|
| P-VCNA | 14.1.2.1 | Demographics and Baseline Characteristics | 生成 | VARIABLE_SUMMARY / demographics | 31 | 0 |
| P-VCNA | 14.1.3 | Medical History | 生成 | CODED_TERM / medical_history_soc_pt | 6 | 2 |
| P-VCNA | F 14.2.1 | Kaplan-Meier Plot of Overall Survival | 生成 | KAPLAN_MEIER / overall_survival | 5 | 0 |
| P-VCNA | 14.3.4.6 | Shift Table of Biochemistry Parameters | **无兼容模板**（预期内） | — | — | — |
| WTX | 14.1.4.1 | Demographic Characteristics – Dose Escalation | 生成 | VARIABLE_SUMMARY / demographics | 31 | 2 |
| WTX | 14.3.2.1.1 | TEAE by SOC and PT – Dose Escalation | 生成 | CODED_TERM / teae_soc_pt | 6 | 4 |
| ARV | 14.1.11 | Compliance and Exposure | 生成 | VARIABLE_SUMMARY / exposure_compliance | 15 | 6 |
| ARV | 14.3.2.8 | TEAE by Preferred Term | 生成（自动选层级深度 = 1） | CODED_TERM / teae_soc_pt | 6 | 1 |
| ARV | 14.3.2.10 | TEAE by SOC, PT and Maximum CTCAE Grade | 生成（自动选等级子行） | CODED_TERM / teae_soc_pt | 8 | 1 |
| ARV | F 14.3.2.8 | Tornado Plot for TEAE by PT | **无兼容模板**（预期内） | — | — | — |

- 10 条全部与预期一致：8 条选对模板和 Preset，2 条（试点库中还没有的 shift 表和 Tornado 图）正确报告"无兼容模板"。
- 配置项能从标题自动识别："by Preferred Term" → 只显示 PT 一层；"Maximum CTCAE Grade" → 等级作为子行。识别结果在 Spec 里标为 `content_list / needs_review`，方便人工确认。
- 研究设置里缺少的信息（MedDRA 版本、TEAE 定义、百分比分母、暴露时长单位等）都变成了带问题编号的 unresolved，在 DOCX 中以黄色 `<<UNRESOLVED: … | Qxxx>>` 显示，并逐条写入 `Clarification_Log.csv`（共 16 条问题，另有 2 条无兼容模板记录）。
- P-VCNA 的设置里提供了年龄定义、分母规则、删失规则，这些元素就直接来自 `study_setting / resolved`，没有占位符。
- 每份 Spec 都通过了 Shell_Spec Schema 校验，记录了模板与 Preset 文件的 SHA-256、Style Guide 版本、研究设置版本和匹配理由，可以复现。

每个 Study 的产出在 `examples/pilot/<Study>/`：`*.spec.json`、`*.docx`、`Output_Inventory.csv`、`Clarification_Log.csv`。

## 3 渲染检查

8 份 DOCX 都用 LibreOffice 转成 PDF/PNG 并逐页看过（`qa/stage3_render/`）。看过后修正了：
- 列宽：改为固定表格布局，原来 LibreOffice 不认单元格宽度，导致 SOC/PT 名称挤成多行；
- 块标题行后多出的空行：把所有单元格段落间距设为 0；
- 页眉 "Page x of y" 和页脚运行日期没有右对齐：清除 Header/Footer 样式继承的默认制表位；
- 跨页时列头不重复：加了重复表头行；
- KM 风险表的组名被截断：加宽左边距并自动换行；
- 未解决的单位没有黄色高亮：已补上。

当前状态：
- 无截断，标签可读；跨页的表格自动重复列头。
- 每份 DOCX 恰好有 1 个 Bookmark（`OUT_<编号>`）。
- 正文里没有生成器自身的说明文字。
- Programming Note 为斜体灰色，放在脚注之后。

限制：
- 这是 LibreOffice 预览，未在 Microsoft Word 中检查。
- KM 图在 LibreOffice 预览里四周有一圈浅灰；PNG 本身背景是纯白（已核对像素），应是预览渲染造成的。

## 4 发现的问题与取舍

1. **"待审"元素偏多**（人口学表 31 个）。主要来自 Preset 的变量和类别清单，例如种族类别、ECOG 级别、年龄分组切点。这是有意为之：各 Study 的 CRF 不同，Preset 只能给出候选。阶段 4 可以加一个"审阅者确认后写回研究设置"的流程，让同一 Study 后续的表直接变为 resolved。
2. **匹配用的是规则打分**（标题词 + 关键词/别名 − 排除词）。在 10 条上全部正确，但还没有在全部 6 个 Study 的 content list 上系统评估。阶段 4 铺开模板后会做一次全量评估。
3. **Spec 中暂无"审阅者修改后重新生成"的入口**。项目要求审阅者能修订、重新生成，并保留编号和决定。计划在阶段 4 加一个 `answers.json`：按 question_id 或 element_path 填写答复，重新生成时作为已确认设置使用。
4. **SOC 下的等级子行**直接放在 SOC 行下面，没有单独的 "Any grade" 标签行。ARV 的来源也是这样排的；如需加标签，作为 Style 规则另行决定。

## 5 如何复现

在 `Generic_Template_Build/` 目录下：

```sh
.venv/bin/python tools/sync_template_evidence.py
.venv/bin/python tools/build_index.py
.venv/bin/python tools/run_pilot.py
sh tools/render_check.sh
```

## 6 下一步（阶段 4）

- 按同一套 Schema 和 Renderer 补齐其余 13 个模板：6 个 Table、1 个 Listing、5 个 Figure（KM 之外），以及它们的 Preset。Listing 需要实现 `listing` 子结构和 Listing 渲染器。
- 加入审阅答复与重新生成的流程（§4 第 3 点）。
- 用 6 个 Study 的全部 content list 跑一次匹配，统计选对率、无兼容模板和歧义。
