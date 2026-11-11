# P-VCNA-003 — 用户人工批准与来源范围内验收完成

最新状态日期：2026-11-11（America/New_York）。审核人：用户（本会话人工审核者）。

全部 **64/64** 个实际来源模板已获用户人工批准作为来源模板库使用，包含原先8个专项待核查模板。每个模板均有真实DOCX、结构记录、Locator Map及Metadata；本次仅更改批准、验收和问题处置记录。原始ZIP和checkpoint目录均保留。

人工决定见 [Human_Approval_2026-11-11.json](qa/Human_Approval_2026-11-11.json)，其中登记全部64个template_id。该记录是用户人工审核及接受已披露限制的决定，**不是Agent新完成独立视觉或临床审核**；未编造姓名、签名或更早日期。历史visual/semantic的not_run保持不变。历史阶段README不能用于推翻本次最新QA记录；批准前完整QA、Metadata及README快照见qa/history/pre_human_approval/。

completed_ids为64个，remaining_ids与blocked_ids为空，full_study_complete=true仅表示本次提供来源范围内的实际来源模板提取已完成并获验收。132个目录条目中的68个未独立展示条目仍未生成模板，不补建缺页内容。

## 保留并由用户接受的限制

- 提供PDF缺少印刷页4–29；缺失的SAP定义不推断、不补写。
- 原文中Figure 14.2.6题名/编程说明冲突、OS时间起点冲突、标题单复数差异、Listing 16.2.6.1示例行列不一致均保留。
- 脚注适用范围、p值行归属等仍按原记录保持未知、pending、needs_review或conflicting，不因批准改为确定。
- 稀疏行、空白单元格、上标及层级的当前保留形式已获人工接受；本次未改写DOCX、统计定义、脚注原文、适用范围或结构事实。
- 300个企业页眉/表单页脚排除项继续为null locator/unverified；来源study/date/path/page占位内容及实质注释保留。
- 独立visual/semantic仍为not_run；非TFL研究设计图的细节仍未验证。

每项问题的原文、原状态、处置理由及批准记录引用见qa/Issue_Dispositions_2026-11-11.json。resolved表示用户接受当前提取/排版后的验收处置；deferred表示来源不确定或独立核验限制仍保留。issues未机械清空。Corrections_Log保留2条真实历史来源修正，并新增行政状态变更审计；本次新增来源内容修正数为0。

## 本次实际验证

完整v2.4 --stage qa已执行，退出码0：pass_with_review_warnings，0个静态错误；警告{"occurrence_review":900,"review_not_passed":128}。本次实际结果为qa/Static_Validation.json，命令、执行时间、环境与退出码为qa/Validation_Execution_2026-11-11.json，stdout/stderr日志一并保留。静态通过不代表临床或视觉结论。

pypdf读取原始PDF时发出object offset警告，原始输出保存在stderr日志；未修复或重写源PDF。初次Windows默认编码读取失败及UTF-8重跑结果也分别保留，不冒用旧报告。

原始ZIP全部956个文件已逐文件核对一致，来源PDF和64份DOCX哈希匹配；完整核对证据见qa/Human_Approval_Integrity_Checks.json。

范围严格限于P-VCNA-003；未加入其余5个Study，未合并、去重或生成目标研究内容。
