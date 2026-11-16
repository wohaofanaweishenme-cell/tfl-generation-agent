# OMO-103-01 来源提取与 pending 登记完成报告

## 来源身份

实际文件名：`SAP_001_62 copy.pdf`。封面 Study ID：`OMO-103-01`。版本 `Final 2.0`，封面日期 `20Sep2022`；共 83 个物理 PDF 页。

SHA-256：`1aa3f12d5e1f3fba31e789edc9911b3dfb4622e3940c79acfab56a074b04255a`。

复用现有 83 页扫描和页图；本轮没有重新扫描整个来源。来源区域：1–3 封面/签字页，4–5 SAP 目录，6–7 缩写，8–29 SAP 正文，30–34 TFL 目录，35 版式说明，36–82 实际 Shell，83 正常值范围附件。参考图表不冒充输出 Shell。

## 实际数量和方法

实际 Shell 共 37 份：20 Table、16 Listing、1 Figure。两份来源类型为 Table 的实际结构采用 listing_spec；保留来源 output_type。目录实际有 57 项，37 项有物理 Shell，20 项只在目录或布局引用中出现；没有补建、去重、合并不同 Shell 或展开共用布局。

沿用原来 10 个样本，共 16 个实际 DOCX 页面。使用本地 Python 3.12、python-docx、pdfplumber、pypdf、Pillow、jsonschema 及配套 LibreOffice。小型测试 DOCX 实际构建、渲染并查看后恢复执行，旧环境失败日志完整保留。没有联网、下载依赖或修改全局 Python。

所有 Table/Listing 使用原生可编辑 Word 单元格；Figure 是来源文字规格，无模拟曲线、图像替代或补画绘图区。逐页核对本 Study 的列界、行归属、多层表头、真实空白、跨页、面板、数值占位符、大小写、单位、源行和脚注。没有套用前三 Study 的版式或统计规则。最终 37 份 DOCX 共 47 页，已实际通过 LibreOffice 渲染并逐页与来源比较；这不是 Microsoft Word 实际显示验证。

样本修正包括：PDF43 Median 的正文归属、PDF45 n/Mean 分行、PDF66 Physician 的下级表头归属、PDF67 周期数列归属和源缩进。批量中 PDF57 的 1–1.25 点字体基线差导致标签/数值误拆行，已只重建该项并复查。历史候选和 Corrections Log 保留。最终核验另将 PDF48 一条被分为两段的计数脚注修复成带显式换行的单个原生段落；已重算哈希、更新 Locator/Metadata，并重新渲染查看该页。

## 当前分层状态

| 项目 | 数量或状态 |
|---|---:|
| 已识别 / 已生成 / 已登记 | 37 / 37 / 37 |
| Structured Shell / Locator Map / Metadata | 37 / 37 / 37 |
| 来源内容 / 物理结构 / DOCX 静态 / DOCX 视觉检查 pass | 各 37 |
| 实际最终 DOCX 页面核对 | 47 |
| 来源脚注归属 needs_review | 2 个模板，各 1 条说明 |
| 来源编号/轴/引用冲突 | 3 个模板；保留原文 |
| 上述来源审核事项涉及的去重模板 | 4 |
| 来源文字或网格 blocked | 0 |
| 独立临床/统计语义审核 | not_run，37 份 |
| Microsoft Word 显示验证 | not_run |
| 人工批准 | not_run；approved 0 |
| 第四 Study review_status | pending，37 份 |
| 第四 Study formal_use_eligible | false，37 份 |

最终原版 v2.4 验证器：`pass_with_review_warnings`，静态 errors 0；review warnings 原样保留。字数/字符覆盖只作辅助检查，没有替代原始页面与最终 DOCX 的核对。不能将本报告解读成所有语义检查通过或已获批准。

## 明确未解决事项

1. `OMO10301_T_14_3_1_6`，PDF54：`SAE = Serious Adverse Event.` 的首面板没有直接显示 SAE 列，跨面板/整表适用范围未明确。文字已完整保留，须由临床/统计审核者判断归属。
2. `OMO10301_L_16_2_8_1`，PDF76：同样的首面板 SAE 缩写说明归属未明确；PDF77 的来源行另写 `Source Listing: 16.2.7.1`，与 AE Shell 16.2.8.1、PFS Listing 16.2.7.1 的用途不一致。均保留原文。
3. `OMO10301_T_14_2_5`，PDF44：`OMO 103-101` 与封面及目录的 `OMO-103-01 / OMO 103-01` 不一致，未擅自修正。
4. `OMO10301_F_14_2_6_1`，PDF47：TTP 的 `Time Post-Dose (h)`、图例 `OMO 103-101`、14.2.7.2 的自引用均按原文保留。需要来源作者澄清或有记录的语义审核决定。
5. Study 层面的封面日期与页脚 `Version Date 20 MAY 2021` 作为不同标签记录，不推定二者含义相同。

这些事项没有阻止来源表达和 pending 登记，但没有被改成 pass。完整 ID、说明、来源证据和所需判断见 `Unresolved_Items.json`。其余独立语义审核和人工批准仍适用于全部 37 份。

## 统一 Library 和保护范围

同一个项目级 `TFL_SOURCE_LIBRARY_v24` 现有 4 个 Study、268 份登记及 DOCX，63 approved、205 pending。第四 Study 37 份全部 pending，未进入 approved_view、正式可调用集合或批准关键词索引。

前三 Study 工作目录、Study 快照、共享旧文件、旧 ID/Metadata 对象、批准状态、历史记录和 approved_view 按既有 7,292 文件基线保护。最终完整性结果见 `Integrity_Result.json`；项目汇总仅追加第四 Study 和必要的当前状态。旧全量整合脚本未运行。

## 成果和续接路径

- `Study_OMO-103-01/TFL_Template_Library/`：37 份最终 DOCX。
- `intermediate/Structured_Shells/`、`intermediate/DOCX_Locator_Map/`、`Study_Metadata.json`：结构、所有出现位置/书签、来源证据和 Metadata。
- `source_registry/`：83 页索引、37 Shell Manifest、57 项目录及来源记录。
- `docx_previews/<template_id>/`：实际 LibreOffice PDF、PNG 和渲染日志。
- `batches/Samples`、`Batch_001`–`Batch_004`：按批结构、检查和 pending 登记证据。
- `qa/`：当前分层检查、修正记录及完成报告。
- `checkpoints/Source_Completion_20261113/`：当前 Status、完整验证、逐模板状态、47 页视觉索引、未解决事项及完整性结果。
- `Library/studies/OMO-103-01/`：本 Study 的一致快照；共享成果和项目注册索引同步。

**来源表达与 pending 登记已完成；独立语义审核未完成；人工批准未完成。** `full_study_complete` 保持 false，避免将来源成果完成误写为所有审核与批准完成。
