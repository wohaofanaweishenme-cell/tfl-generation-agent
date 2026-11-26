# 阶段 2 报告：候选模板清单与来源归类

日期：2026-11-24　依据：`00_CONVENTIONS_v1.0.md` §2.2–2.4、§10
状态：**待你审阅归类**（这是约定 §10 中最关键的人工决策点；审完才进入阶段 3）

## 1 做了什么

把阶段 1 的 431 份结构签名，按约定 §2.2 的判定树聚成候选 Template，并给每份来源标出归属。

| 文件 | 内容 |
|---|---|
| `inventory/Template_Candidates.json` | 16 个候选模板：用途、不适用情况、接受哪些签名、初步识别的配置项；另含少量逐来源的归属调整（每条有理由）和非标准清单 |
| `inventory/Template_Clustering.csv` | **主审阅表**：一行一来源，列出归属模板、匹配程度（fit）、用到的配置项、描述信息、建议 Preset、旧半成品归属（对照） |
| `inventory/Template_Coverage.csv` | 一行一模板：来源数、Study 数、证据等级、匹配程度分布、Preset 候选 |
| `inventory/Nonstandard_Sources.json` | 不进主库的来源 |
| `tools/stage2_cluster.py` | 归类脚本，可重复运行；任何来源没有归属时脚本直接报错 |

`fit` 的含义：
- `core`：用模板的默认形式即可表示；
- `config` / `config_extension`：需要用到配置项（已列在 `config_used` 列）。`config_extension` 表示是我人工调整过归属的；
- `partial`：只能部分表示，将来 Agent 遇到这类条目要标 needs_review。

## 2 候选模板清单（16 个）

| # | 模板 | 用途 | 来源 | Study | 证据等级 | core / config / partial |
|---|---|---|---:|---:|---|---|
| 1 | TBL_VARIABLE_SUMMARY | 变量分布汇总：连续变量统计量行、分类变量互斥类别行 n(%) | 26 | 6 | multi_study | 22 / 4 / 0 |
| 2 | TBL_CRITERION_COUNTS | 按条件计数：处置、分析集、方案偏离、死亡、AE 总览、DLT、ADA、阈值类别（非互斥） | 39 | 6 | multi_study | 32 / 7 / 0 |
| 3 | TBL_CODED_TERM_HIERARCHY | 字典编码层级：SOC/PT、ATC/PN、AESI/PT、仅 PT | 34 | 6 | multi_study | 22 / 12 / 0 |
| 4 | TBL_PARAMETER_BY_VISIT | 参数×访视：连续统计量（含变化值）或分类 n(%) | 39 | 6 | multi_study | 38 / 0 / 1 |
| 5 | TBL_TIMEPOINT_STATISTICS_COLUMNS | 时间点为行、统计量为列（PK 浓度等） | 3 | 3 | multi_study | 3 / 0 / 0 |
| 6 | TBL_SHIFT_CROSSTAB | 交叉分类：基线×基线后 shift、两种评估一致性 | 16 | 5 | multi_study | 12 / 4 / 0 |
| 7 | TBL_RESPONSE_RATE | 二分类/类别终点：率 + CI，可选组间比较 | 15 | 5 | multi_study | 13 / 1 / 1 |
| 8 | TBL_TIME_TO_EVENT | 生存终点：事件/删失、KM 分位数 + CI、HR | 4 | 3 | multi_study | 4 / 0 / 0 |
| 9 | TBL_CONTINUOUS_COMPARISON | 连续终点 + 组间估计（LS Mean、差值、Hodges-Lehmann） | 28 | 2 | multi_study | 27 / 1 / 0 |
| 10 | LST_SUBJECT_RECORDS | 通用受试者记录清单 | 206 | 6 | multi_study | 29 / 177 / 0 |
| 11 | FIG_KAPLAN_MEIER | KM 曲线 | 3 | 3 | multi_study | 3 / 0 / 0 |
| 12 | FIG_SUMMARY_OVER_TIME | 组均值/百分比随时间变化 | 3 | 3 | multi_study | 3 / 0 / 0 |
| 13 | FIG_INDIVIDUAL_PROFILE | 个体轨迹（spider、个体 PK） | 5 | 2 | multi_study | 5 / 0 / 0 |
| 14 | FIG_BOX_PLOT | 分组箱线图 | 6 | 1 | single_source | 6 / 0 / 0 |
| 15 | FIG_WATERFALL | 瀑布图 | 2 | 1 | single_source | 2 / 0 / 0 |
| 16 | FIG_TORNADO | Tornado 图 | 1 | 1 | single_source | 1 / 0 / 0 |

非标准（不进主库）：`CPXPOM001_L_16_2_1_1_1_1`（入排标准原文目录，不含受试者，仅 1 个 Study）。

合计：430 份归入 16 个模板，1 份非标准。Table 9 个、Listing 1 个、Figure 6 个。

### Listing 为什么只有 1 个模板
206 份 Listing 的差别都可以用配置表达：

| 配置项 | 涉及来源数 |
|---|---:|
| 记录粒度（一人一行 54 / 一人多条事件 55 / 一人×访视 49 / 一人×参数×访视 48） | 206 |
| 一个单元格内堆叠多个字段（如 "Start Date/ End Date"） | 157 |
| 按组分页的组标题行 | 64 |
| 列太多时分面板，面板间重复受试者标识 | 12 |

临床主题（AE、实验室、合并用药、肿瘤病灶……）全部做成 Preset，提供常用字段的默认列表。

## 3 需要你决定的问题

每项都给了建议；你不提出异议的，我就按建议进入阶段 3。

| # | 问题 | 建议 | 理由 |
|---|---|---|---|
| Q1 | TBL_VARIABLE_SUMMARY 和 TBL_CRITERION_COUNTS 要不要合并？两者渲染出来都是"标签行 + 各组 n(%)" | **分开** | 输入不同：前者需要"变量 + 互斥类别 + 缺失规则"，后者需要"每行一个条件定义"，且行之间可以重叠、可以嵌套。分开后 Agent 的必填字段更清楚，匹配理由也更好解释 |
| Q2 | 阈值类别表（QTc > 450、xULN、生命体征显著变化）放哪里 | **无访视的放 TBL_CRITERION_COUNTS，按访视的放 TBL_PARAMETER_BY_VISIT** | 已经这样归类。WTX 两份、ARV 一份是我人工从变量汇总挪到条件计数的 |
| Q3 | SOC/PT 表里等级/严重程度/相关性作为子行（5 份）还是子列（2 份） | **同一模板的两种配置** | 行结构相同，只是类别放在行下还是列里 |
| Q4 | P-VCNA 的 3 份长表 shift（分类计数按访视展开 + "Normal -> Normal" 转移行） | **作为 TBL_SHIFT_CROSSTAB 的一种布局配置** | 内容同样是基线×基线后的交叉分类，只是排布方式不同 |
| Q5 | SP 的"按中心统计处置"（行 = 中心，列 = 处置状态） | **归入 TBL_SHIFT_CROSSTAB** | 本质是两个分类变量（中心 × 状态）的交叉计数；否则只能作为非标准 |
| Q6 | 只来自 ARV 的箱线图、瀑布图、Tornado | **按 D2 作为 single_source 收录** | 三者都是行业常见图形 |
| Q7 | TBL_CONTINUOUS_COMPARISON 合并了 ARV 的 LS Mean 表（23 份）和 SP 的 Hodges-Lehmann 表（5 份） | **合并** | 两者都是"描述统计 + 组间估计及 CI"，只是估计方法不同；方法名本来就必须来自 SAP/设置，不能由模板默认。合并后满足 ≥2 个 Study |
| Q8 | PK 浓度表（统计量作列）单独成模板 | **单独成模板（TBL_TIMEPOINT_STATISTICS_COLUMNS）** | 行是时间点、列是统计量，行列生成逻辑和"参数×访视"不同；有 3 个 Study 支持 |
| Q9 | 两份只能部分表示的来源 | **保留在模板内并标 partial** | OMO 的多终点长表（DCR/ORR/TTP/TTR/DOR 混在一张表）；SP 的免疫原性表（检测方法 × 阴/阳性作列）。Agent 遇到时会提示需要人工确认 |

## 4 与旧半成品的对照

旧方案有 88 个家族；新方案有 16 个模板，加上 Preset。主要差别：
- 旧方案按临床主题分 44 个 Listing 家族，新方案只有 1 个 Listing 模板。
- 旧方案把 AE、病史、用药的 SOC/PT 表分成多个家族，新方案统一为 TBL_CODED_TERM_HIERARCHY，用 Preset 区分。
- 旧方案的 "categorical_assessment"、"clinical_predicate"、"visit_change" 等，现在按结构分到 TBL_PARAMETER_BY_VISIT、TBL_CRITERION_COUNTS、TBL_VARIABLE_SUMMARY。

每行对应的旧归属都保留在 `legacy_family_reference` 列，方便对照。

## 5 建议的审阅方式

1. 先看本报告 §2 的清单和 §3 的 9 个问题；
2. 打开 `inventory/Template_Clustering.csv`，按 `template_id` 筛选，看每个模板下的来源标题是否"像一类"；
3. 重点看 `fit` 不是 `core` 的行，以及 `note` 不为空的行。

需要改动时，告诉我 source_id 和应归到哪个模板（或"非标准"）。也可以说"某两个模板合并 / 某模板拆开"，我会更新候选清单并重新生成。

## 6 下一步（阶段 3，待你确认后开始）

按 D9 先做 3 个试点：TBL_VARIABLE_SUMMARY（描述性汇总）、TBL_CODED_TERM_HIERARCHY（SOC/PT）、FIG_KAPLAN_MEIER。内容包括：
- 统一的 Shell Spec Schema 与 Template Schema；
- House Style Guide 的 JSON 版；
- 这 3 个模板的定义 JSON 及其 Preset；
- 通用 Renderer（Table 一个、Figure 一个）；
- 端到端试跑：content list 条目 → 选模板 → 填 Spec → 出 Word。
