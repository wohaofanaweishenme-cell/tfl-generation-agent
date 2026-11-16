# CPX-POM-001 剩余九份完成报告

本轮完成剩余九份的来源表示提取、原生可编辑 DOCX 构建及同一项目级 Library 的 pending 登记。第三 Study 累计 **61/61** 个实际 Shell（27 Table、33 Listing、1 Figure）；项目共 **231** 份（63 approved、168 pending）。所有第三 Study 条目保持 pending、formal_use_eligible=false，未加入 approved_view 或可调用 Keyword Index。

| 本轮检查 | 结果 |
|---|---|
| 来源原图、字符坐标与逐单元格内容 | 9/9 pass，同一 agent 核对 |
| 物理结构、表头、空白与连续页 | 9/9 pass |
| 原生可编辑 Word Table／Listing | 9/9；无整页图片替代 |
| 实际渲染及逐页视觉核对 | 9 份／22 页 pass，LibreOffice 导出 |
| 书签唯一、边界包含、occurrence 原文与引用、DOCX 哈希 | 9/9 pass |
| 工作成果／共享 Library／Study 快照 | DOCX、Structure、Map、Source Record SHA-256 一致 |
| v2.4 schema | 187 项 pass；不代表语义正确 |
| 已登记 52 份及前两个 Study | 5143 个本轮保护文件 SHA-256 零差异；原 222 条索引未变 |
| 人工批准、独立临床／统计语义审核、Microsoft Word 实际显示 | not_run |

## 九份正式成果

路径以项目根为基准，均已同步共享 `Library/TFL_Template_Library/` 与下列 Study 快照。完整 SHA-256、各页渲染路径和相关结构文件哈希见 Registered_Artifact_Manifest.json。

| Shell ID | PDF 来源页 | 渲染页数 | 正式 DOCX |
|---|---|---:|---|
| CPXPOM001_T_14_1_1_1 | 9,10 | 2 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_1_1_1.docx` |
| CPXPOM001_T_14_1_1_2 | 11,12,13 | 3 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_1_1_2.docx` |
| CPXPOM001_T_14_1_3_1 | 16,17,18,19 | 4 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_1_3_1.docx` |
| CPXPOM001_T_14_1_5_1_1 | 22,23,24,25 | 4 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_1_5_1_1.docx` |
| CPXPOM001_T_14_2_2_1 | 34,35 | 2 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_2_2_1.docx` |
| CPXPOM001_T_14_3_3_2_1 | 67,68,69 | 3 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_3_3_2_1.docx` |
| CPXPOM001_T_14_3_4_2_1 | 72,73 | 2 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_3_4_2_1.docx` |
| CPXPOM001_T_14_3_1_8_1 | 47 | 1 | `Library/studies/CPX-POM-001/TFL_Template_Library/table/CPXPOM001_T_14_3_1_8_1.docx` |
| CPXPOM001_L_16_2_9_1_1 | 121 | 1 | `Library/studies/CPX-POM-001/TFL_Template_Library/listing/CPXPOM001_L_16_2_9_1_1.docx` |

## 来源结构确认与修正

- 14.1-1.1：第 10 页 Pregnancy 治疗组格真实为空；保持空白。完成两个来源页的标题、七剂量列、周期行、随访折行、Time on Study 统计及各页脚注。
- 14.1-1.2：三个来源页治疗列横向位置分别确认。第 11 页无标签数值行原样保留，Cycle 3 的 Cisplatin 列为空，其余两列有占位数值；不补造行名，不因临床常识重排数值。
- 14.1-3.1：四页使用同一 DOCX，保留 Age、Sex、Country、Height、Weight、BMI、BSA、ECOG 分组及跨行标签。第 16 页来源的 Native Hawaiian or／Other Pacific Islander 两行均显示数值，物理显示按来源保留；不同页 BMI ^2／**2 原文不统一改写。
- 14.1-5.1.1：第 22 页长的整行分组说明使用来源支持的跨列单元格；Metastatic Disease 的层级与 No/Yes 行独立保留。第 25 页仅有 Programming Notes，作为第 4 页保留，没有补造数据页。
- 14.2-2.1：响应的 Visit→Target／Non-Target／Overall→类别层级保留；第 35 页只有 Programming Notes，仍归入同一 DOCX。
- 14.3-3.2.1：三页分别为 Pulse／Systolic／Diastolic，保留 BAS 和 C1 TRT D2 行上的 XX 分母、阈值行上的 n (%)、比较符号和重复说明；不把分母移到阈值行。
- 14.3-4.2.1：两页的 QTcF／PR／QRS 分组、Change／Percent Change、条件折行、msec／ms、≥／>／< 与脚注范围证据保留。

## 两处原阻断的实际复查结论

**PDF 47：物理归属障碍已解决，统计语义仍未独立审核。** 原图放大与字符坐标同时确认 SOC 行无数值；每个 PT1–PT3 行各有六个严重程度单元格。两处 `<etc>` 的原始数值基线低于标签约 3.36 和 10.08 PDF points，DOCX 通过同一物理行中各单元格的独立段前位置保留偏移，没有把数值抬到 SOC 行或自动填充。原图区域、候选解释、坐标及原文在 batch_015/Geometry_Resolution.json、page47_rows_detail.png 和 page47_body_characters.json。

**PDF 121：空白网格物理拓扑已解决。** 原始黑色 0.72pt 实线矩形确认边界 x≈72.384/128.66/186.98/298.01/343.01/414.07；水平边界 y≈221.33/234.53/247.73/261.05/293.69。首段仅从 Visit 开始，随后包含 Patient。底部五个连续空白矩形覆盖右侧 Oxygen／Weight／Temperature 三个显示行，仅这五个可见连续区域在 Word 中建立有来源依据的 span；没有自动复制 Patient、Visit、日期，也没有增加来源不存在的 Date/Time 内部分线。修复了首次候选中合并格延续部分的边框未闭合问题，最终实际渲染已核对。原始线段、字符和放大图保存在 batch_015/Page121_Line_Geometry.json、page121_grid_detail.png、page121_body_characters.json。

## 仍需审核的事项

- 独立临床／统计语义审核、脚注条款级语义范围与人工批准未执行；同一 agent 的来源表示核对不能替代它们。Metadata 中相关 needs_review 保留。
- 第 11 页无标签数值行、Cycle 3 组标题上的数值，第 16 页拆分种族占位行，第 47 页 `<etc>` 值的统计含义均未猜测修正。
- 第 121 页来源写作 Oxygen Saturation (mmHg)，按原文保留，未改成 %。
- 既有第 106 页直径表头下 DDMMMYYYY 以及 Figure 的 PFS 横轴／RFS 标题差异继续保留 needs_review。
- Figure 继续使用真实来源图像，noneditable；Python 可编辑生成 not_implemented；没有加入批准／可调用集合。
- DOCX 为原生可编辑的来源表示重建，字体、留白和排版不是 PDF 像素复制；实际显示验证为 LibreOffice，不是 Microsoft Word。

## 登记与历史完整性

原工作目录、共享 Library、Study 快照、Metadata、Locator Map、source_elements、Source Records、DOCX 哈希、注册表、Metadata_Index、Pending_Index、Template_Status 和 QA 已核对。原有 52 份模板及其 Metadata 记录未改变；原有 222 条索引逐字段相同。前两个 Study 的文件、ID、批准状态和历史保留，approved_view 和 Keyword Index 哈希未变。

旧的 52/61 状态及阶段报告已归档至本检查点 history；原 Continuous_Extraction_20261113 入口指向当前完成结果。旧 Nine_Sample_Visual_QA、Structural_Repair_Gate 等失败记录保留为历史，并未宣称旧统一分列方法通过。未重建现有 52 份、未重新打包全部 Study、未同步或改写 GitHub。

当前来源提取及 pending 登记 **无剩余、无阻断**。Extraction_Progress 的 full_study_complete=false 仅表示独立语义审核／批准等完整 QA 尚未完成，并非还有来源模板未登记。


## 单模板视觉状态复核：CPXPOM001_T_14_3_2_5_1

最终 DOCX（SHA-256 `03742c71facb5d598aeba420f55ea17197605af7b513e5e2060f90d4f2deb604`）已重新实际渲染并与来源 PDF 第 64 页、既有放大证据逐项比较：七个剂量表头、SCR/BAS 分组、28 个数值占位格、真实空白及脚注完整，当前视觉检查 **pass**，无需重建 DOCX。原视觉 `needs_review` 与后续 DETAIL_RECHECK 已移入 Targeted_Visual_Reconciliation_20261113/Historical_Visual_Checks.json，旧状态未改写。当前 QA 只保留本次有效视觉结论，因此与累计视觉通过统计一致。仍存在的 `needs_review` 指向独立临床／统计及脚注条款语义审核，不是未解决的表头显示问题；模板仍 pending。此处视觉核对为同一 agent 使用 LibreOffice 实际渲染，不是 Microsoft Word 显示验证。
