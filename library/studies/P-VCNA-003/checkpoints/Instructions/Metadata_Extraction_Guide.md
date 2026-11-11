# 来源模板提取指南 v2.4

## 来源优先级

Shell 描述实际显示结构、原始标题/编号、行列、占位符、脚注、轴与图例；SAP 正文提供 endpoint、人群、统计方法、时间起点和分析定义。两者冲突时分别保留证据，不以常识或另一个模板替换。Content List 是可选目录，不是物理模板清单，未展示的条目不补建。记录源文件版本与哈希；未知日期/ID 不猜测。

## 结构保真

Table 保存每一行列、层级、多层表头、合并关系、统计标签、真实空格/空单元格、稀疏单元格及占位符。Structured_Shell.physical_cells 记录二维位置、行列跨度和原文；复杂来源不能只转录线性文字。统计量顺序与来源一致，STD 不擅自改为 SD，不补常见统计量。

Listing 保存全部列、各面板列子集、原始示例占位行、空白延续单元格、记录单位和分组；无明确排序规则就留空并记录未找到或未核查。不得根据列名反推 ADaM/SDTM 变量。源类型为 Table 而结构类似 Listing 时保留 output_type=table，使用 structural_family=listing 和 listing_spec。

Figure 保存 description/code/image/mixed、各 panel 的变量/标签/单位/尺度/范围、分组、图例、注释和原始代码/图像。未给单位或轴范围不能填常识默认值。PROC 名称不等于完整可执行程序。只有文字说明时保留文字，不制造绘图区或结果曲线。参考图片须标注非可编辑区域。

## 脚注和位置

脚注、Programming Notes、Source line、表单页脚分别识别；一个物理脚注可包含多条语义规则。逐字保存标记、上标、单位、限定词、原始顺序和区域。每条脚注关联原文支持的行/列/单元格/panel/axis；无法确定就挂起，不默认适用于全表。多个分母用各自的 scope 和 semantic_rules，整表 denominator_rule 仅可作不掩盖差异的概括。

Step 2 可先保留 semantic_extraction_status=needs_review，Step 4 再提取含义。extracted 包括 abbreviation、display_convention，未识别规则须实际读过才可用 no_rule_identified。源研究规则不是项目批准默认值。

每个逻辑来源元素记录所有 occurrences，具有独立 ID、角色、原文、panel、证据和定位状态。完全相同的重复原文可记 exact_repeat；不同用途/限定条件/单位保留不同元素和 related_distinct。关系不能触发自动替换。不可编辑/未定位内容也登记，不因无法 verified 而删除。

Word 总边界包含所有所属标题、页、面板、脚注和说明；出现位置另设包围真实文字的 bookmark。START/END 是 collapsed bookmark，名称唯一，不能只在 JSON 写名字。native footnote/endnote 或页眉页脚中的实质内容要转为边界内可见正文并保留语义，不能静默丢弃。公司 wrapper 排除须有明确一致政策。QA 备注不混入来源正文。

## Metadata 与未来接口

关键词来自已核查的标题、主题、方法、显示结构与重要脚注概念，不把每个模板都标上所有统计术语。aliases 必须有语义依据。retrieval_text 是紧凑描述，不转录整页来源。不生成 embeddings，不设计检索排名。

provenance 的 document_id 必须在来源 inventory 中；引用页码与区域能回到实际文件。metadata_pointer 指向 template 对象，Listing row 引用中间 listing_rows。field_statuses 区分 unreviewed/explicit/inferred/not_found/not_applicable/conflicting；空值不代表不适用。没有批准 Style Guide 时 defaults=[]。

adaptation 容器可保留空数组；不强制 required_sap_fields、operation、target_field，不执行目标替换。当前人工/Agent 修正只能修复来源支持的提取错误，留 Corrections Log 并同步结构、定位、Metadata、文件哈希和受影响 QA。

## QA 与完成数

全文件扫描页数、实际 Shell 数、结构记录数、DOCX 数、Metadata 数、待处理/阻塞数分别报告。content-list-only 项不增加物理模板数。所有原文共用布局说明保留为 source_reference_notes，不复制或补建新模板。

静态工具检查实际文件、Schema、ID、引用、哈希、边界和文字；不能替代页图比较、统计语义判断或独立审核。visual/semantic 未执行必须 not_run。没有真实人工授权就 pending，不自动 approved。即使全部文件存在，也不能宣称完整可编辑或临床正确。
