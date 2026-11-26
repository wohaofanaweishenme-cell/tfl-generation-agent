# House Style Guide v1.0

机器可读版本：`House_Style_Guide.json`（以它为准）。依据：约定 v1.0 §6 与决策 D3–D8、D11。

| 项 | 规则 |
|---|---|
| 编号 | 保持 content list 原编号和顺序，不重排 |
| 数值占位符 | 小写 `x`：`xx`、`xx.x`、`xx (xx.x)` |
| 统计量 | n `xx`；Mean (SD) `xx.x (xx.xx)`；Median `xx.x`；Min, Max `xx, xx`；n (%) `xx (xx.x)` |
| 小数位 | 原始精度 d：均值/中位数 d+1，SD/SE d+2，最小/最大 d；百分比 1 位；p 值 3 位，`<0.001` |
| 百分比 | `n (xx.x)`；计数为 0 时只显示 0 |
| CI | `(xx.x, xx.x)`，置信水平写在列头或脚注 |
| 日期 | `DDMMMYYYY` |
| 文字占位 | `[描述]`，如 `[Treatment A]` |
| 组列头 | 组名换行 `(N=xx)` |
| 未解决元素 | `<<UNRESOLVED: 简述 \| Q-ID>>`，黄色高亮 |
| 脚注顺序 | 带标记脚注（[a]、[b]…按首次出现）→ 通用说明（人群、分母、字典、缩写）→ 程序路径/日期 |
| Programming Notes | 脚注之后；前缀 `Programming Note: `；斜体灰色；可开关；只写展示规则 |
| 页面 | 横向 Letter，页边距 1 英寸，Courier New 9pt |
| 页眉 / 页脚 | 左上 `[Sponsor / Study ID]`，右上 `Page x of y`；左下 `Program: [program path]`，右下 `Run date: DDMMMYYYY` |
| 表格线 | 列头上下各一条线，表格底部一条线，无竖线 |
| 每页组数 | 最多 6 组，超过时分面板 |
| Figure | 带标签的空白绘图框，不画任何曲线、柱或数据点；KM 风险表标题 "Number at risk" |
| Bookmark | 每个输出 1 个：`OUT_` + 编号（非字母数字替换为 `_`） |

## v1.1 增补（阶段 4）

| 项 | 规则 |
|---|---|
| 终点类统计量 | 率 + CI `xx.x (xx.x, xx.x)`；中位数 + CI `xx.x (xx.x, xx.x)`；LS Mean (SE) `xx.x (xx.xx)`；p 值 `x.xxx` |
| Listing 占位 | 受试者号 `xxxxxx`；日期 `DDMMMYYYY`；日期时间 `DDMMMYYYY:HH:MM`；数值 `xx.x`；文字 `[xxxxxxxx]`；是否 `Y/N` |
| Listing 版式 | 示例 3 行；每个面板最多 10 个字段，超过则分面板，每个面板重复受试者号和组别；多字段同格用 " / " 分隔 |
