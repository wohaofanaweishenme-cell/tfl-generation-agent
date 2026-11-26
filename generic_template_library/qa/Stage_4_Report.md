# 阶段 4 报告：铺开全部模板、审阅答复与全量匹配评估

日期：2026-11-24　依据：`00_CONVENTIONS_v1.0.md` §4–§11；阶段 3 报告 §6
状态：16 个模板全部可用（pilot 状态），待你查看样例和评估结果

## 1 模板库现状

| 模板 | 类型 | 来源 | Study | 证据等级 | Preset 数 |
|---|---|---:|---:|---|---:|
| TBL_VARIABLE_SUMMARY | 变量分布汇总 | 26 | 6 | multi_study | 3 |
| TBL_CRITERION_COUNTS | 按条件计数 | 39 | 6 | multi_study | 8 |
| TBL_CODED_TERM_HIERARCHY | 编码层级（SOC/PT 等） | 34 | 6 | multi_study | 3 |
| TBL_PARAMETER_BY_VISIT | 参数×访视 | 39 | 6 | multi_study | 8 |
| TBL_TIMEPOINT_STATISTICS_COLUMNS | 统计量作列的时间点表 | 3 | 3 | multi_study | 1 |
| TBL_SHIFT_CROSSTAB | 交叉分类 / shift | 16 | 5 | multi_study | 4 |
| TBL_RESPONSE_RATE | 率终点 | 15 | 5 | multi_study | 2 |
| TBL_TIME_TO_EVENT | 生存终点 | 4 | 3 | multi_study | 1 |
| TBL_CONTINUOUS_COMPARISON | 连续终点组间比较 | 28 | 2 | multi_study | 2 |
| LST_SUBJECT_RECORDS | 受试者记录清单 | 206 | 6 | multi_study | 23 |
| FIG_KAPLAN_MEIER | KM | 3 | 3 | multi_study | 2 |
| FIG_SUMMARY_OVER_TIME | 组统计量随时间 | 3 | 3 | multi_study | 3 |
| FIG_INDIVIDUAL_PROFILE | 个体轨迹 | 5 | 2 | multi_study | 3 |
| FIG_BOX_PLOT | 箱线图 | 6 | 1 | single_source | 1 |
| FIG_WATERFALL | 瀑布图 | 2 | 1 | single_source | 1 |
| FIG_TORNADO | Tornado | 1 | 1 | single_source | 1 |

合计 16 个模板、66 个 Preset，覆盖 430/431 份来源（1 份非标准）。`tools/build_index.py` 全部校验通过，并生成了 Template_Index、Keyword_Index（316 个检索词）和 Library_Bundle。

## 2 本阶段新增

**Schema 扩展**
- Shell Spec 新增四类行块：`criterion`、`endpoint`、`parameter_visit`、`timepoint_stats`、`crosstab`（含 `items`、`visits`、`timepoints`、`parameters`、`row_variable` 等）。
- 新增三类列：统计量作列、类别作列、组间比较列。
- 新增 `listing` 结构：记录粒度、字段（可多字段同格）、排序、分组、重复标识。
- Study Settings 新增 `comparisons`（是否比较、估计量与检验标签、方法）和 `timepoints`。
- Style Guide 升到 v1.1：增加终点类占位符和 Listing 版式。

**Listing Preset 的生成方式**
23 个主题 Preset 是从来源 Listing 的列名统计出来的：
1. 把 "A/ B" 形式的堆叠列头拆开；
2. 归一到标准字段名；
3. 保留在 ≥2 个 Study 出现过的字段。

每个 Preset 里记录了各字段来自哪些 Study（`source_frequency`）。有 9 个 Preset 做了人工修正（如补上结果列、去掉误匹配字段），修正说明也写在文件里。

**图形**
新增 `renderer/figure/shells.py`，包含箱线图、瀑布图、Tornado、个体轨迹、组均值随时间五个绘图函数。接口与 KM 相同：`plot(spec, data=None)`，目前都是 `shell_only`（只画空白框）。

**渲染器**
- Table 渲染器扩展为三种列模式（分组列 / 统计量列 / 类别列）；
- 新增 Listing 渲染器：字段多时自动均匀分面板，每个面板重复受试者号；按组显示组标题行；每组 3 行占位。

**审阅答复与重新生成**
- `examples/inputs/answers_<study>.json`：审阅者按研究设置路径填写答复。重新生成时，答复并入研究设置，相应元素变为 `study_setting / resolved`。
- `Question_Registry.json`：问题编号按（输出编号 + 元素路径）登记，重新生成时编号不变。
- `Settings_To_Confirm.round<N>.csv`：把同一个缺失设置在各输出中引发的问题合并成一行，审阅者只需答一次（例如 WTX 的"百分比分母"出现在 5 张表里）。

**新增工具**
- `tools/generate.py`：通用批量生成。
- `tools/evaluate_matching.py`：全量匹配评估。
- `tools/render_check.sh`：可指定目录。

## 3 示例生成（25 条）

`examples/stage4/`：4 个 Study、25 条真实 content list 条目，每个模板至少一条。
- 25 条全部选对模板和 Preset，与预期一致。
- 原先我对 P-VCNA 14.3.4.6 的预期是 normal-range shift；工具选了 clinical-evaluation shift。核对来源后，来源确实用的是 Normal / Abnormal NCS / Abnormal CS，工具是对的，已把预期改正。
- 25 份 DOCX 共 31 页，已逐类目视检查（`qa/stage4_render/`）。检查中修正了三处：
  - 比较列里 p 值列误填了估计值；
  - Listing 分面板不均衡（最后一个面板只有一列）；
  - 连续终点比较表不应有 Total 列：改为由模板关闭，并标为待审。

**重新生成演示（WTX）**
- 第 1 轮共 39 个问题。
- WTX 审阅者答复了 MedDRA 版本和 TEAE 定义后，第 2 轮剩 36 个：Q007–Q009 消失，其余问题编号保持不变。
- 第 1 轮的 TEAE 表保存在 `examples/stage4/WTX-330x2101/round1_snapshot/`，便于对比。

## 4 全量匹配评估

`qa/matching_eval/`：6 个 Study 的全部 775 条 content list 条目。其中 431 条在 Library 中有直接对应的来源 Shell，可作为标准答案。

| 结果 | 数量 |
|---|---:|
| 选对 | **410（95.1%）** |
| 选错模板 | 11 |
| 歧义（交给人选） | 7 |
| 漏判为"无兼容模板" | 2 |
| 非标准来源被误配 | 1 |

按类型：Table 188/208，Listing 202/203，Figure 20/20。

**调整过程**
第一次评估准确率为 91.9%。主要问题是标题里的人群名（如 "Safety Analysis Set"）被当成了"分析集"主题，这和阶段 1 遇到的是同一个问题。匹配前去掉人群限定语，并给几个模板补上来源中实际出现的说法后，升到 95.1%。之后没有再针对评估集调参，以免过拟合。

**剩余错误主要有三类**
- 标题本身信息不足，例如 OMO 的 "Physical Examination"、"Autoimmune Values"，从标题无法区分"按访视计数"和"统计量作列"；
- 4 份登记为 table、实际是 Listing 的来源（如 "Listing of Abnormal Laboratory Values"），content list 的类型本身就标成了 table；
- 混合多个终点的表（OMO "DCR, ORR, OS, TTP…"）。

逐条明细见 `Matching_Evaluation.csv`。

**注意**：这是库内评估，模板正是从这 6 个 Study 推导的，衡量的是复现能力，不是对新研究的泛化能力（与 D1 一致）。另有 344 条没有直接对应的 Shell（共享布局或只在目录中出现），表中只列出了它们的预测分布。

## 5 局限与待决定事项

1. **全部模板仍是 `pilot` 状态**：未经你的人工审阅批准，目前没有任何批准记录。
2. **待审元素多**：Preset 给出的变量、类别、字段清单都标为 needs_review。
3. ~~比较列标签按研究设置~~ **已改为按终点类型设置**（你确认后完成，见 §7）。
4. **Figure 只有空白框**：接数据绘图（`data_ready`）尚未开始。
5. **只在 LibreOffice 里预览过**，未在 Microsoft Word 中核对。
6. **只做了规则版"选模板 + 填 Spec"**：它是 Agent 的基线。项目要求的 Agent 和"与通用 LLM 对比"等评估还没做。
7. **阶段 3 的旧样例**（`examples/pilot/`）是用旧代码生成的，保留作历史记录，以 `examples/stage4/` 为准。

## 6 复现

在 `Generic_Template_Build/` 目录下：

```sh
.venv/bin/python tools/sync_template_evidence.py
.venv/bin/python tools/build_index.py
.venv/bin/python tools/generate.py --entries examples/inputs/example_entries.json --out examples/stage4 --round 1
.venv/bin/python tools/generate.py --entries examples/inputs/example_entries.json --out examples/stage4 --answers --round 2
sh tools/render_check.sh examples/stage4 qa/stage4_render
cd tools && ../.venv/bin/python evaluate_matching.py
```

## 7 补充：组间比较按终点类型设置（2026-11-24）

- `Study_Settings.comparisons` 改为分三类分别设置：`response_rate`、`time_to_event`、`continuous`。每类各有 `enabled`、`estimate_label`、`test_label`、`method`、`reference_group_id`。
- 三个终点模板的配置项 `comparison.setting_path` 分别指向对应的那一类。模板和 Preset 里写的 `{settings:comparisons.xxx}` 会自动换成该终点的路径，例如生存表读 `comparisons.time_to_event.method`。
- 估计量所在行的标签也改为直接取设置里的 `estimate_label`（如 "Odds Ratio (95% CI)"），不再写通用的 "Estimate (95% CI)"。
- 示例效果（P-VCNA）：
  - ORR 表（新增示例 14.2.2.7）：列头和行标签都是 "Odds Ratio (95% CI)"，脚注为 CMH 检验说明，全部来自研究设置。
  - OS 表：设置里只给了 p 值标签，没有 HR 标签和方法，于是列头和行标签显示为 unresolved。`Settings_To_Confirm` 把相关问题合并到 `comparisons.time_to_event.estimate_label`（2 个问题）和 `.method`（1 个问题）。
- 示例增至 26 条，全部选对；26 份 DOCX 共 32 页已重新渲染。全量匹配评估不受影响，仍为 410/431（95.1%）。

## 8 批准与参考库发布（2026-11-26）

- **批准**：项目负责人在工作会话中明确批准。16 个模板和 66 个 Preset 定版为 1.0.0，模板状态改为 `approved`。`approvals/Approval_Record.json` 记录了每个模板、Preset 和 Style Guide 的 SHA-256 与批准范围。
- **锁定检查**：`tools/build_index.py` 会核对批准哈希。已实测：改动一个已批准模板后，构建报错 "changed after approval"；恢复原文件后通过。
- **批准后的状态规则**：
  - 已批准模板自带的脚注和 Programming Note 视为批准的展示惯例，生成时标 `resolved`；
  - Preset 内容仍标 `needs_review`，需由每个研究确认；
  - 分析定义在研究设置提供前始终是 `unresolved`。
- **参考库**：新增 `TFL_Template_Library/{table,listing,figure}/`，只放 DOCX，每个"模板 + Preset"一份，共 66 份（Table 32、Listing 23、Figure 11）。
  - 用 `reference/Reference_Study_Settings.json` 这套中性设置生成，路径和哈希写入 `reference/Reference_Library_Manifest.json` 和 `Template_Index.json`。
  - 66 份共 77 页，已用 LibreOffice 转换，并用缩略图总览抽查，见 `qa/reference_render/_contact_*.png`。
- **示例**：用批准版本重新生成了 26 条示例，并重新渲染。现有目录和脚本路径均未移动。
