# 通用 TFL 模板库：提取与搭建约定 v1.0（定稿）

状态：已定稿（2026-11-24 用户确认）。原标【待确认】的条目均按建议值确定；修改需升版本并记录。
日期：2026-11-24（v1.0 定稿；v0.2：取消留出集；Programming Notes 进正文；总索引与 Keyword Index；Figure Python 绘图契约）

---

## 0 定位与范围

| 层 | 是什么 | 本约定下的处理 |
|---|---|---|
| v2.4 提取规范 | 来源 Shell 的忠实提取规则 | **不变**。只约束 Library 层。 |
| `Library/` | 6 个 Study、431 份来源模板（approved） | **只读证据层**。本次不改任何文件。 |
| `Template_Generalization/` | 旧通用化半成品（88 家族） | **只作参考**：可查阅其 source_mapping 和差异分析，不继承其家族划分、Schema、代码或计数。 |
| `Generic_Template_Build/`（本目录） | 新的通用模板库 | 按本约定从头搭建。 |

v2.4 的"不合并、不补建、无 Style Guide 则无默认值"是**提取层**原则。通用化层的任务正好相反：**合并结构相同的来源、写出 Style Guide、给出允许的默认值**。两层原则不冲突，因为通用化层不回写 Library。

通用模板库服务于项目目标：Agent 读取 content list 条目 + 已确认的 study settings → 选择模板 → 生成 Shell Spec → 渲染 Word。因此模板库的衡量标准是 **"Agent 能否据此选对、填对、标出缺失"**，而不是"是否完整复现每份来源"。

---

## 1 术语与分层

```
Source Template (Library, 431)
        │  证据
        ▼
Template（结构模板，~30–40 个）  ← 由"结构签名"定义
        │  + Preset（主题预设，可选，多个）
        │  + Style Guide（全库统一）
        │  + Study Settings（目标研究确认信息）
        │  + Content List Entry（单条目录）
        ▼
Shell Spec Instance（统一 Schema 的 JSON，逐元素标来源）
        │  通用 Renderer（按 Table / Listing / Figure 各一个）
        ▼
DOCX Shell + Output Inventory + Clarification Log
```

- **Template**：一种行列骨架 + 行块语法 + 统计含义的组合。与临床主题无关。
- **Preset**：同一 Template 下针对某主题的默认内容包（如 Vital Signs 的参数/单位列表、AE Listing 的常用列、常见脚注）。Preset 不改变结构，只提供 `template_default` 级别的候选值。
- **Variant**：不存在独立的"变体"层级。差异要么能用参数表达（→ 配置项），要么不能（→ 新 Template）。
- **Shell Spec**：唯一的结构化 Shell 表示，所有 Template 都产出同一种 Schema。
- **Slot（槽位）**：Shell Spec 中每一个可替换的元素。

---

## 2 模板粒度：判定规则

### 2.1 结构签名（Structural Signature）

每份来源 Shell 在通用化第一步只提取以下 6 个维度，作为是否归入同一 Template 的唯一依据：

| 维度 | 取值示例 |
|---|---|
| S1 输出类型 | table / listing / figure |
| S2 行轴语法 | 变量块（连续/分类）· 层级计数（SOC→PT）· 参数×访视 · 交叉表（基线×基线后）· 类别清单 · 模型/比较项 · 受试者记录 |
| S3 列轴语法 | 组列重复 · 组×统计量 · 组×访视 · 记录字段 · 无（单列） |
| S4 单元格统计含义 | n(%) 受试者 · n 事件 · 描述统计 · 估计值+CI · p 值 · 中位时间+CI · 原始值 |
| S5 嵌套/分层 | 无 · 参数分组 · 按访视分段 · 按组分页 · 按受试者分组 |
| S6 Figure 图形类型（仅 figure） | KM · 均值随时间 · 个体轨迹/spider · waterfall · box · forest · swimmer · bar/tornado |

### 2.2 判定树

```
同一 S1，且 S2、S3、S4 相同？
 ├─ 是 → 同一 Template。S5 和其余差异全部作为配置项。
 └─ 否 → 差异能否写成一个有限枚举参数，且不改变 Renderer 的行/列生成逻辑？
          ├─ 能 → 同一 Template，加配置项（例：统计量行是否分行、是否加 Total 列）
          └─ 不能 → 新 Template
```

以下**永远不构成新 Template**：临床主题、参数名称、组数、访视数、统计量行的增删、列的显示/隐藏、单位、标题措辞、人群、分页/分面方式、脚注内容。

以下**通常构成新 Template**：计数单位改变（受试者 vs 事件 vs 双计数）、行轴变成层级或交叉、单元格从描述统计变成模型估计、Figure 图形类型不同。

### 2.3 证据门槛

- 一个 Template 至少需要 **2 个 Study** 的来源支持；（已确定）
- 只有 1 个来源支持的结构：若属于行业常见类型（如 forest plot），可作为 Template 收录但标记 `evidence_level: single_source`；否则不进主库，记入 `Nonstandard_Sources.json`，Agent 遇到时应提示"无兼容模板"。
- 预期规模（假设，不是目标）：Table 15–25、Listing 3–6、Figure 8–10。

### 2.4 候选 Template 假设清单（阶段 1 用证据验证，不预先承诺）

- Table：描述性变量块汇总（人口学/基线/暴露/实验室描述）· 受试者分类计数（处置/分析集/方案偏离）· 层级 SOC/PT 受试者计数 · 层级计数按最高等级 · 事件+受试者双计数 · AE 总览 · 参数×访视描述与变化 · Shift 交叉表 · 阈值/异常类别计数 · 二分类终点率+CI · 组间比较模型估计（LSMeans/OR/HR）· TTE 汇总（中位时间+CI+事件数）· PK 浓度描述 · PK 参数描述
- Listing：扁平受试者记录 · 按受试者分组的嵌套记录 · 参数×访视长表 · 宽表多面板
- Figure：见 S6

---

## 3 来源范围（已确认：全部 6 个 Study）

通用模板库从全部 6 个 Study、431 份来源推导，不设留出集。

| Study | 来源数（T/L/F） |
|---|---|
| ARV-471-BC-201 | 64 / 29 / 13 |
| WTX-330x2101 | 35 / 56 / 2 |
| CPX-POM-001 | 27 / 33 / 1 |
| SP11631 | 37 / 32 / 1 |
| P-VCNA-003 | 25 / 37 / 2 |
| OMO-103-01 | 20 / 16 / 1 |

为了让 Template 真正"通用"而不是"6 个 Study 的拼盘"，执行两条规则：
- **去 study 化**：Template 与 Preset 中不得出现任何来源 Study 的专有内容（药名、剂量、队列名、具体访视、study ID、来源特有的临床定义）。这些只能出现在 `evidence` 指针里。
- **来源只作证据**：每个 Template 的 `evidence` 列出支持它的来源 ID；评估时用 content list 生成 Shell 并与来源 Shell 比较。
- **范围（已确认）**：目标是覆盖这 6 个 Study 的库内复现，不要求对新 Study 的泛化能力。

---

## 4 统一 Shell Spec Schema（要点）

所有 Template 产出同一种 JSON。完整 Schema 在阶段 2 写成 `schemas/Shell_Spec.schema.json`，此处只定骨架。

```jsonc
{
  "schema_version": "3.0",
  "output_id": "14.1.2.1",            // 保持 content list 原编号
  "output_type": "table",
  "template_id": "TBL_DESC_SUMMARY",
  "template_version": "1.0.0",
  "preset_ids": ["demographics"],
  "title":      { "value": "...", "source": "content_list", "status": "resolved" },
  "population": { "value": "...", "source": "content_list", "status": "resolved" },
  "columns":    [ /* 列组定义，每个带 source/status */ ],
  "row_blocks": [ /* 行块，每个带 source/status */ ],
  "statistics": [ /* 每个行块的统计量与精度 */ ],
  "footnotes":  [ /* 有序，带 marker、引用位置、source */ ],
  "programming_notes": [ /* 给程序员的展示说明，见 §9 */ ],
  "figure":     null,                  // figure 专用：axes/units/groups/legend/panels
  "listing":    null,                  // listing 专用：fields/sort/grouping
  "page":       { "orientation": "landscape", "source": "template_default" },
  "issues":     [ /* 该输出的待解决问题，指向 clarification log */ ]
}
```

### 4.1 每个 Slot 必须带的两个字段

| 字段 | 取值 | 含义 |
|---|---|---|
| `source` | `content_list` | 来自该 content list 条目的明文（编号、标题、人群、访视、注释） |
| | `study_setting` | 来自用户确认的 study settings（组别、访视表、人群定义、编码字典版本） |
| | `template_default` | 来自 Template / Preset / Style Guide 的批准默认 |
| | `unresolved` | 以上均无法提供 |
| `status` | `resolved` / `needs_review` / `unresolved` / `conflict` | `unresolved` 必须在 DOCX 中可见（见 §9） |

优先级：`content_list` > `study_setting` > `template_default`。高优先级与低优先级冲突时，采用高优先级并记录；两个同级来源冲突时 → `conflict`，不自动裁定。

### 4.2 Schema 原则

- 一种 Schema 覆盖 Table / Listing / Figure，类型专属字段放在 `figure` / `listing` 子对象。
- Schema 只描述**展示结构**，不描述数据推导算法。
- 不同 Template 不允许各自定义顶层字段名；Template 的差异体现在"填哪些 slot、默认值是什么"。

---

## 5 Template 定义文件必须包含的字段

对应项目要求的 *intended use / required fields / permitted defaults / editable elements*：

| 字段 | 说明 |
|---|---|
| `template_id`, `version`, `output_type` | 稳定 ID 与语义化版本 |
| `structural_signature` | §2.1 的 S1–S6 |
| `intended_use` | 一两句话：适用于什么 |
| `not_for` | 明确不适用的情况（帮助 Agent 排除）|
| `keywords` | 受控关键词（来自受控词表，见 §5.1），进入 Keyword Index |
| `aliases` | 同义写法与缩写（如 "TEAE" / "treatment-emergent adverse event"），只取 6 个 Study 来源标题/注释中实际出现过的说法 |
| `match_cues` | 匹配线索：标题关键词、人群/终点类型、注释中的触发词；供检索与解释匹配理由 |
| `required_fields` | 必须由 content_list 或 study_setting 提供，否则 `unresolved` |
| `permitted_defaults` | 可由模板/Preset/Style Guide 提供的默认（列出值） |
| `editable_elements` | 审阅者可修改且重新生成时保留的元素 |
| `config_options` | §2.2 中的有限枚举参数 |
| `presets` | 可用主题预设列表 |
| `skeleton` | 一个最小的 Shell Spec 片段（带占位） |
| `evidence` | 支持该 Template 的来源 ID 列表（指向 Library template_id）及各自归入理由 |
| `evidence_level` | `multi_study` / `single_source` |

| `figure_plot`（仅 figure） | 绘图契约，见 §8 Figure |

**一个 Template 一个 JSON 文件**，不再为每个家族配套独立的 Config Schema、Python 脚本、README、QA 目录。Preset 同样一文件一个，也带自己的 `keywords` / `aliases`。

### 5.1 总索引（给 Agent 读取）

单个 Template JSON 是**唯一可编辑的真值**；总索引全部由脚本 `tools/build_index.py` 从这些文件**自动生成**，不手改，避免两份内容不一致。

| 文件 | 内容 | Agent 用途 |
|---|---|---|
| `Template_Index.json` | 每个 Template 一条摘要：`template_id`、`output_type`、`intended_use`、`not_for`、`keywords`、`aliases`、`required_fields` 名称、`presets`（id + 关键词）、`evidence` 数量、文件路径、版本与 SHA-256 | 第一步读取：候选筛选与解释匹配理由 |
| `Keyword_Index.json` | 倒排索引：关键词/别名（规范化小写）→ `[{template_id, preset_id, field}]` | 用 content list 标题/主题快速召回候选 |
| `Library_Bundle.json` | 全部 Template + Preset + Style Guide 的完整内容合并为一个文件 | 需要一次性加载全库时使用（例如上下文足够时） |

规则：
- 关键词来自一张受控词表 `vocab/Keywords.json`（主题、终点类型、统计类型、图形类型等分组），新增词必须先进词表，避免同义词各写各的。
- 每次修改 Template 后重新生成三份索引；生成脚本同时做校验：每个 Template 都在索引中、路径存在、哈希一致、关键词都在词表中。
- 典型 Agent 流程：读 `Template_Index.json` + `Keyword_Index.json` → 召回候选 → 只加载选中的 Template JSON（或直接用 Bundle）→ 填 Shell Spec。

---

## 6 House Style Guide 约定（草案值）

6 个 Study 的惯例并不统一（例：WTX/CPX 多用 `XX.X`，P-VCNA/SP/OMO 多用 `xx.x`；日期有 `DDMMMYYYY` 与 `YYYY-MM-DD`）。通用库统一为一种 house style，不追随任何单一来源。

| 项 | 建议值 | 状态 |
|---|---|---|
| 编号 | 保持 content list 原编号与顺序，不重排 | 确定 |
| 数值占位符 | 小写 `x`，位数表示宽度：`xx`、`xx.x`、`xx (xx.x)` | 已确定 |
| 日期占位符 | `DDMMMYYYY` | 已确定 |
| 文字占位符 | `[方括号描述]`，如 `[Treatment A]` | 已确定 |
| 未解决元素 | `<<UNRESOLVED: 简述 | Q-ID>>`，黄色高亮 | 已确定 |
| 小数位 | 原始值精度为 d：均值/中位数 d+1、SD d+2、min/max d；百分比 1 位；p 值 3 位，`<0.001` | 已确定 |
| 百分比 | `n (xx.x)`，0 计数不显示百分比 | 已确定 |
| CI | `(xx.x, xx.x)`，置信水平写在列头或脚注 | 建议 |
| 组列头 | `[Group label]` 换行 `(N=xx)` | 建议 |
| 缩写 | 全库一张缩写表；脚注中首次出现时展开 | 建议 |
| 脚注顺序 | 先 marker 脚注（a, b, c 按出现顺序），后通用说明（人群定义、分母、缩写），最后程序路径/日期行 | 已确定 |
| 页面 | Table/Listing 横向 Letter，字体 Courier New 9pt | 已确定 |
| 页眉页脚 | Study ID、Page x of y、Program 路径、运行日期占位 | 建议 |

Style Guide 是全库唯一默认来源之一，写成 `style/House_Style_Guide.json`（机器读）+ 一页 md（人读）。

---

## 7 临床语义边界

项目明确：*不得编造分析方法、人群、不确定性度量或缺失数据规则*。因此：

| 元素 | 模板可否默认 | 处理 |
|---|---|---|
| 分析人群 | 否 | 来自 content_list 或 study_setting；否则 `unresolved` |
| 治疗组/队列标签与数量 | 否 | study_setting |
| 访视列表 | 否 | study_setting |
| 统计方法（模型、检验、CI 方法） | 否 | content_list 注释或 study_setting；否则 `unresolved` |
| 分母规则、缺失处理 | 否 | 同上 |
| 编码字典及版本（MedDRA/WHODrug/CTCAE） | 否 | study_setting |
| 描述统计行的组合（n, Mean (SD), Median, Min, Max） | **可以** | template_default |
| 分类行的 n (%) 格式、排序约定（如 SOC/PT 按频数降序） | **可以**，但需在 Template 中写明 | template_default，且 status=`needs_review` |
| Preset 中的参数列表（如 Vital Signs 参数） | **可以作为候选** | template_default + `needs_review`，审阅者确认 |
| 标准脚注措辞（如 "Percentages are based on N"） | 可以提供措辞模板，但分母主体必须来自 setting | 模板措辞 + 引用槽位 |

原则：**模板管"长什么样"，不管"怎么算"**。"怎么算"一律是需要外部提供的 slot。

---

## 8 类型专属约定

### Table
- 行块类型固定为有限集合（连续变量块、分类块、层级块、交叉块、模型项块），Renderer 按块类型生成行。
- 组列可重复；Total 列为配置项。组数超过每页上限时自动分面，分面规则属 Style Guide。

### Listing
- Listing 的通用性主要在**字段配置**，不在结构。主题（AE、CM、Lab……）全部是 Preset。
- 必须字段：受试者标识、组别；排序与分组键为配置项。
- 宽表超页宽：按字段组分面板，受试者标识在每个面板重复。

### Figure
- 按项目要求：figure shell 包含**带标签的空白绘图框**，标出 x/y 轴标题与单位、分组/图例、面板布局、风险表（KM）等，不画任何模拟曲线。
- Figure 专属 slot：`x_axis`、`y_axis`（标题、单位、刻度说明）、`groups`、`legend`、`panels`、`reference_lines`、`annotations`、`risk_table`。

#### Figure 的 Python 绘图接入（为后续可视化预留）

Figure 的轴、分组、图例、面板已经是 Shell Spec 中的结构化字段，所以绘图代码可以直接读同一份 Spec，后续加入不需要改模板结构。约定如下：

- 每个 Figure Template 带 `figure_plot` 字段：
  ```jsonc
  "figure_plot": {
    "plot_type": "km",                         // 对应 S6
    "plotter": "renderer/figure/plot_km.py:plot",
    "data_contract": {                          // 将来接入真实数据时的输入列
      "required_columns": {"time": "float", "event": "int(0/1)", "group": "str"},
      "optional_columns": {"panel": "str"}
    },
    "implementation_status": "shell_only"       // shell_only → data_ready
  }
  ```
- 每种图形一个 Python 函数，统一签名 `plot(spec: dict, data: DataFrame | None) -> matplotlib.Figure`：
  - `data=None`：画**带标签的空白绘图框**（轴标题、单位、图例占位、面板、KM 风险表行名），即 Shell 本身。
  - 有 `data`：按同一 Spec 画真实图，轴/图例/分组文字完全来自 Spec，保证 Shell 和最终图一致。
- 用 matplotlib 统一画空白框和真实图，一条代码路径（已确定）。DOCX 中 Figure 区域嵌入该图（PNG），标题、脚注、Programming Notes 仍为可编辑 Word 文本。
- 按项目要求，Shell 中不出现模拟曲线；用合成数据测试绘图函数只在 `qa/` 中进行，不进入 Shell 交付物。
- 先做 `shell_only`；可视化开发时逐个图形类型把状态升到 `data_ready`，并为其提供数据契约校验。

---

## 9 Renderer 与 DOCX 约定

- 每种 output_type 一个通用 Renderer，输入只有 Shell Spec，不依赖 Template 专属代码。
- Table/Listing 用原生 Word 表格；Figure 用 Word 中的空白框（表格或形状）加轴标签文字。
- **DOCX 正文 = 真实 Shell 会有的内容**。区分两类"说明性文字"：

  | 类别 | 例子 | 进不进正文 |
  |---|---|---|
  | **Programming Notes**（来源 Shell 本来就有的给程序员的说明） | "Repeat for each visit"、"Sort by SOC descending frequency"、"Same layout as Table 14.x for SAF" | **进**。431 份来源中约 275 份含此类说明，是真实 Shell 的组成部分 |
  | **生成器自身的元信息** | "Generalization draft"、"DEMONSTRATION CONFIGURATION"、"Grouping: treatment. SD: sample"、"Stable identity"、配置参数回显 | **不进**，只写在 Shell Spec JSON / Output Inventory 里 |

- Programming Notes 在 Shell Spec 中是独立元素 `programming_notes[]`，与 `footnotes[]` 分开：
  - 每条带 `source`（同 §4.1）和 `status`；Template 可提供通用措辞（`template_default`，如"Repeat block for each parameter"），study 特有的说明来自 content list / study setting。
  - 渲染位置：放在脚注之后，统一前缀 `Programming Note:`，用不同样式（建议斜体 + 灰色或蓝色）与给读者看的脚注区分。（已确认）
  - 模板里写进去的 Programming Note 只描述**展示规则**（重复、排序、分页、同布局引用），不描述统计算法——算法仍按 §7 是 slot。
  - 提供一个渲染开关 `include_programming_notes`（默认开），需要"干净版"时可关掉。
- 判定口诀：**"一个真实项目的 Shell 里会不会出现这句话？"** 会 → 进正文；只是我们的工具在解释自己 → 不进。
- `unresolved` 元素在正文中以 §6 的可见标记出现，并对应 Clarification Log 的问题 ID。
- 每个输出保留一个 Word bookmark（`output_id` 规范化后的名称），供重新生成时定位；不再要求逐 occurrence 的 bookmark。（已确定）
- 同时输出：`Output_Inventory`（content list 条目 ↔ 生成输出 ↔ template_id）和 `Clarification_Log`。

---

## 10 构建流程与阶段门

| 阶段 | 内容 | 产物 | 门 |
|---|---|---|---|
| 0 | 定稿本约定 + Style Guide 值 | 本文件 v1.0 | 你确认 |
| 1 | 对全部 431 份来源逐份提取结构签名（只读 Library 的 Structured_Shell/Metadata） | `inventory/Signatures.csv`（一行一来源） | 抽查通过 |
| 2 | 按签名聚类，提出 Template 清单与每份来源的归属 | `inventory/Template_Clustering.csv`（一张可审阅的表） | **你审阅归类** |
| 3 | 写统一 Shell Spec Schema + 3 个差异最大的试点 Template（建议：描述性汇总、SOC/PT 层级计数、KM 图）+ 通用 Renderer | Schema、3 个 Template、Renderer | 端到端试点：用 content list 条目跑通"选模板→填 spec→出 Word" |
| 4 | 铺开其余 Template 与 Preset | 全部 Template | 每个 Template 至少用 2 条 content list 条目实测 |
| 5 | 冻结 v1.0，用 6 个 Study 的 content list 做全量生成评估 | 评估报告 | — |

阶段 2 的聚类表是整个流程最重要的人工决策点；之后的工作都建立在它上面。

---

## 11 QA 最小集

QA 只保留能直接回答"能不能用"的检查，避免旧方案的文档膨胀：

1. Schema 校验：所有 Template、Shell Spec 通过 JSON Schema。
2. 覆盖：每份来源都有归属（某 Template / Nonstandard），且理由一行可读。
3. 渲染：每个 Template 至少一份示例 DOCX，实际渲染并目视检查（截断、分页、标签可读）。
4. 无残留：示例 DOCX 中无来源 Study 的专有标签、无生成器元信息（Programming Notes 除外，见 §9）。
5. 端到端：每个 Template ≥2 条 content list 条目实测，记录 Agent 选择是否正确、slot 来源标注是否正确。

每阶段一份简短 `qa/Stage_N_Report.md`，不另建逐家族 QA 目录。

---

## 12 目录结构

```
Generic_Template_Build/
  00_CONVENTIONS_v1.0.md
  vocab/Keywords.json              # 受控关键词表
  style/
    House_Style_Guide.json
    House_Style_Guide.md
  schemas/
    Shell_Spec.schema.json
    Template.schema.json
    Study_Settings.schema.json
  inventory/
    Signatures.csv
    Template_Clustering.csv
    Nonstandard_Sources.json
  templates/
    table/<TEMPLATE_ID>.json
    listing/<TEMPLATE_ID>.json
    figure/<TEMPLATE_ID>.json
  presets/<TEMPLATE_ID>/<preset_id>.json
  renderer/
    render_table.py  render_listing.py  render_figure.py  common.py
    figure/plot_<plot_type>.py      # 每种图形一个 plot(spec, data=None)
  tools/build_index.py              # 生成并校验下面三份索引
  examples/<TEMPLATE_ID>/           # 示例 spec + DOCX
  qa/Stage_N_Report.md
  Template_Index.json               # 自动生成：Agent 检索入口
  Keyword_Index.json                # 自动生成：关键词倒排索引
  Library_Bundle.json               # 自动生成：全库合并版
```

---

## 13 决策记录（全部已确定）

| # | 决策 | 建议 |
|---|---|---|
| D1 | 来源范围（§3） | 已确认：全部 6 个 Study，不设留出集，不要求新 Study 泛化 |
| D2 | Template 证据门槛（§2.3） | 已确定：≥2 个 Study；常见类型可 single_source 收录 |
| D3 | 数值占位符大小写（§6） | 已确定：小写 `xx.x` |
| D4 | 日期占位符（§6） | 已确定：`DDMMMYYYY` |
| D5 | 小数位规则（§6） | 已确定：d+1 / d+2 / d / 百分比 1 位 / p 值 3 位 |
| D6 | 未解决元素的显示方式（§6、§9） | 已确定：`<<UNRESOLVED: … | Q-ID>>` + 黄色高亮 |
| D7 | 页面与字体（§6） | 已确定：横向 Letter，Courier New 9pt |
| D8 | 是否仍保留 bookmark（§9） | 已确定：每个输出 1 个 |
| D9 | 试点的 3 个 Template（§10） | 已确定：描述性汇总、SOC/PT 层级计数、KM 图 |
| D10 | 旧 Template_Generalization 的去留 | 已确定：保留不动，仅作参考 |
| D11 | Programming Notes 进正文（§9） | 已确认：进正文，斜体 + 灰色，前缀 `Programming Note:`，可开关 |
| D12 | 总索引（§5.1） | 已确认需要：Template_Index + Keyword_Index + Library_Bundle，均由脚本从单文件生成 |
| D13 | Figure 绘图（§8） | 已确认需要 Python 可视化；建议 matplotlib 同时画空白框与真实图，先 shell_only |
