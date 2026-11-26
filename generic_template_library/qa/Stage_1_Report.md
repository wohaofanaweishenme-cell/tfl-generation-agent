# 阶段 1 报告：结构签名提取

日期：2026-11-24　依据：`00_CONVENTIONS_v1.0.md` §2.1、§10
状态：完成，待用户抽查（阶段门：抽查通过后进入阶段 2 聚类）

## 1 做了什么

对 Library 中全部 **431 份来源**（6 个 Study）逐份记录结构签名 S1–S6。只读 Library，未写入 Library 或旧 `Template_Generalization/`。

| 步骤 | 工具 | 产物 |
|---|---|---|
| A 摘要 | `tools/stage1_digest.py` | `inventory/Source_Digests.jsonl`：每份来源的标题、行/列标签、统计量、占位符、脚注、Programming Notes、Figure 轴与图例 |
| B 签名 | `tools/stage1_signatures.py` + `inventory/Signature_Overrides.json` | `inventory/Signatures.csv`（主产物，一行一来源）、`inventory/Signature_Vocabulary.json`（各维度取值定义） |

两个脚本可重复运行（从 `content list` 目录执行），结果确定。

### 判定方式
- 先用有序规则判定（依据标题核心词、行列标签、统计量）。标题里的人群名（如 "Safety Analysis Set"）和 study 部分（"Dose Escalation"、"Part 1"）会先剥离，不参与判定。
- 规则判不准的，用 `Signature_Overrides.json` 人工判定，**每条都写明理由**。共 46 条（Table 26、Listing 20），在 CSV 中 `basis=manual`。
- 我逐份查看了全部 204 份 Table、207 份 Listing、20 份 Figure 的摘要来核对结果。
- `content_tag`（临床主题）只作检索辅助，**不参与签名**，符合约定 §2.2。
- `legacy_family_reference` 列出旧半成品中的归属，仅供对照。

## 2 结果概览

| S1 | 来源数 | 说明 |
|---|---:|---|
| table | 204 | 来源登记为 table 的 208 份中，4 份实际是 Listing 结构，按结构归入 listing（见 §4） |
| listing | 207 | |
| figure | 20 | |

不同的签名组合（S1+S2+S3+S4，Figure 加 S6）共 **37 种**；其中最多的 7 种组合覆盖 345 份来源（80%）。

### Table（204）

| S2 行轴 | 数量 | 典型来源 |
|---|---:|---|
| ENDPOINT_ANALYSIS 终点分析 | 47 | 应答率+CI、KM 中位数、LS Mean/Hodges-Lehmann 估计 |
| BY_TIMEPOINT 参数×访视 | 42 | 实验室/生命体征/ECG 按访视描述或分类计数，PK 浓度 |
| CATEGORY_LIST 预定义类别 | 37 | 处置、分析集、方案偏离、死亡、AE 总览 |
| CODED_HIERARCHY 编码层级 | 34 | SOC/PT、ATC/PN、AESI/PT、仅 PT |
| VAR_BLOCKS 变量块 | 29 | 人口学、疾病特征、暴露、阈值类别（无访视） |
| CROSSTAB 交叉表 | 15 | 基线×基线后 shift、两种评估的一致性 |

主要签名组合（来源数 / 覆盖 Study 数）：

| 签名 | 来源 | Study |
|---|---:|---:|
| CATEGORY_LIST · GROUPS · SUBJ_N_PCT | 32 | 6 |
| CODED_HIERARCHY · GROUPS · SUBJ_N_PCT | 27 | 5 |
| ENDPOINT_ANALYSIS · GROUPS_PLUS_COMPARISON · MODEL_EST | 23 | **1**（全部 ARV） |
| BY_TIMEPOINT · GROUPS · DESC | 20 | 6 |
| VAR_BLOCKS · GROUPS · DESC_MIXED | 19 | 5 |
| BY_TIMEPOINT · GROUPS · SUBJ_N_PCT | 18 | 6 |
| CROSSTAB · CATEGORY_COLS · SUBJ_N_PCT | 12 | 4 |
| ENDPOINT_ANALYSIS · GROUPS_PLUS_COMPARISON · RATE_CI | 9 | 2 |

其余 21 种组合各 1–6 份，多数是上面几类的列布局差异（如单列 vs 分组列、组内拆子列、统计量作列）。

### Listing（207）

行轴全部是"受试者记录"（另有 1 份 CPX 入排标准目录不含受试者）。差异主要在**记录粒度**（S5）：

| 粒度 | 数量 | 例子 |
|---|---:|---|
| LISTING_SUBJECT_EVENT 受试者×事件/条目 | 55 | AE、病史、合并用药、方案偏离、既往治疗 |
| LISTING_SUBJECT 一人一行 | 54 | 人口学、处置、分析集、衍生疗效变量 |
| LISTING_SUBJECT_VISIT 受试者×访视（宽表） | 49 | 给药记录、生命体征宽表、ECOG、肿瘤应答 |
| LISTING_SUBJECT_PARAM_VISIT 受试者×参数×访视（长表） | 48 | 实验室、生命体征长表、病灶×访视 |
| LISTING_CATALOG 目录 | 1 | CPX 入排标准原文目录 |

版式标记（`layout_flags`）另行记录：多面板 12 份、组标题行（按组分页）64 份、单元格内多字段堆叠（如 "Start Date/ End Date"）158 份。

### Figure（20）

| S6 图形 | 数量 | 来源 Study |
|---|---:|---|
| BOX 箱线图 | 6 | ARV |
| INDIVIDUAL_PROFILE 个体轨迹（spider/个体 PK） | 5 | ARV、WTX |
| KM | 3 | P-VCNA、CPX、OMO |
| SUMMARY_OVER_TIME 组均值/百分比随时间 | 3 | P-VCNA（ECOG）、WTX（平均 PK）、SP（ANC 均值） |
| WATERFALL 瀑布图 | 2 | ARV |
| TORNADO | 1 | ARV |

## 3 对阶段 2 的初步观察（假设，阶段 2 聚类时再定）

1. **Listing 很可能只需 1 个通用模板**：结构完全相同，差异是记录粒度、字段、宽/长表和分面，都能做成配置。临床主题（AE、Lab、CM……）全部成为 Preset。CPX 入排标准目录是唯一例外，按 §2.3 记入非标准。
2. **DESC 与 DESC_MIXED 很可能合并**：纯连续变量的表就是"只开连续块"的变量块表。
3. **列轴差异多数是配置**：SINGLE（只有 All Subjects 一列）、GROUPS_X_SUBCOL（组内拆 n(%) 与事件数）、Total 列，都可作为列配置项，不必单开模板。
4. **CODED_HIERARCHY 的等级展示有两种**：等级作子行（SUBROWS_BY_CATEGORY，5 份）或作列（CATEGORY_COLS，2 份）。需要决定这是同一模板的两种配置，还是两个模板。
5. **ENDPOINT_ANALYSIS 内部按 S4 明显分成三类**：RATE_CI（应答/发生率）、TTE_EST（生存）、MODEL_EST（模型估计）。三者行结构不同，预计是 3 个模板。
6. **证据门槛（D2：≥2 个 Study）会影响以下几类**：
   - MODEL_EST（LS Mean + Difference 列）的 23 份全部来自 ARV；SP 有 5 份 Hodges-Lehmann 估计，结构接近（组列 + 比较行），可能和 ARV 合为一个"连续终点比较"模板，从而满足 2 个 Study。
   - Figure 的 BOX、WATERFALL、TORNADO 都只来自 ARV。它们是行业常见图形，按 D2 可作为 `single_source` 收录。
7. **阈值类别表**（QTc > 450 ms、xULN、生命体征显著变化等，共 9 份）结构上分散在 BY_TIMEPOINT 和 VAR_BLOCKS，已加 `threshold_categories` 标记。它们的语义特点是类别不互斥、分母因参数而异，阶段 2 决定是作为 Preset 还是单独模板。

## 4 需要你知道的判定

- **4 份登记为 table、实际是 Listing 结构**：`PVCNA003_T_14_3_2_1`（AE 致死清单）、`PVCNA003_T_14_3_3`（异常实验室值清单）、`OMO10301_T_14_3_1_6`（SAE 清单）、`OMO10301_T_14_3_2_1`（超范围生化值）。S1 按结构记为 listing，原登记类型保留在 `source_output_type` 列。
- **OMO 的几份表结构信息较少**（如 "Statistical summaries of ECOG/Physical Examination by visit"），只能从访视行和类别行判断，签名可信度较低。人工判定的理由已写在 overrides 中。
- **P-VCNA 的 shift 表采用长表布局**：分类计数按访视展开，再加 "Normal -> Normal" 转移行，与其他 Study 的"基线类别 × 基线后类别"矩阵不同。现记为 CROSSTAB · GROUPS（3 份），阶段 2 需决定是否作为 CROSSTAB 模板的一种布局配置。

## 5 建议抽查方式

打开 `inventory/Signatures.csv`（Excel 可直接打开），按 `signature_key` 排序后：
1. 每种签名挑 1–2 行，对照来源 DOCX 看签名是否合理；
2. 重点看 `basis=manual` 的 46 行及其 `rule_or_reason`；
3. 看 §4 列出的几类边界情况。

发现问题时，直接告诉我 source_id 和应改成什么；我会加进 overrides 并重新生成。

## 6 未做的事

- 未生成任何模板、Schema 或 DOCX（这些属于阶段 2–3）。
- 未用来源 DOCX 做视觉核对；签名依据的是 Library 中已批准的 Structured_Shell 结构记录。
