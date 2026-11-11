# GitHub + Colab 中期汇报使用说明

仓库：`git@github.com:wohaofanaweishenme-cell/tfl-generation-agent.git`  
网页版：<https://github.com/wohaofanaweishenme-cell/tfl-generation-agent>  
Demo notebook：`notebooks/02_Midterm_Demo_GitHub_Colab.ipynb`

## 一次性的 GitHub 上传（不覆盖仓库原有内容）

**推荐方式：GitHub Desktop**

1. 安装 [GitHub Desktop](https://desktop.github.com/) 并登录新建的 GitHub 账号。
2. `File → Clone repository`，选择 `wohaofanaweishenme-cell/tfl-generation-agent`，克隆到本机。
3. 解压收到的 `tfl-generation-agent-github-ready.zip`，将其中 `tfl-generation-agent-repo/` **里面的文件和文件夹**复制到刚克隆的仓库根目录（不要把 ZIP 当成唯一文件上传）。
4. GitHub Desktop 的 `Changes` 中确认能看到 `README.md`, `pyproject.toml`, `src/`, `notebooks/` 等；填写 summary，例如 `Initial TFL agent MVP and Colab demo`。
5. 点击 `Commit to main`，再点击 `Push origin`。

**也可使用 Git Bash/终端：**（先确保 Git 能使用你的 SSH key，或使用 HTTPS 登录）

```bash
git clone git@github.com:wohaofanaweishenme-cell/tfl-generation-agent.git
cd tfl-generation-agent
# 将解压后的 tfl-generation-agent-repo/ 内所有内容复制到这里
git add .
git commit -m "Add TFL agent MVP and midterm Colab demo"
git push origin HEAD
```

> 如果你在 GitHub 建仓库时已经勾选了初始化 README，这种“先 clone 再复制”方式仍然适用，而且不会强制覆盖远端历史。

## Google Colab 演示

1. 提交 GitHub 后，打开 [Midterm Demo Notebook](https://colab.research.google.com/github/wohaofanaweishenme-cell/tfl-generation-agent/blob/main/notebooks/02_Midterm_Demo_GitHub_Colab.ipynb)。
2. 从头运行每一个 cell。第一个代码 cell 使用 `git clone` / `git pull`，然后执行 `pip install -e`。
3. 默认 `MODE="fixture"`，使用合成 PDF、合成模板库、预写的模拟 LLM 响应；**不会调用真实 LLM**。
4. 展示五步输出：SAP blocks → structured specification/source evidence → template matches → editable DOCX → validation report。
5. 最后下载 `.docx` 文件。现场请提前保存结果 Word 和每步截图作为故障备份。

**真实模型模式：** `MODE="api"` 时在 Colab 的 Secrets 中设置 `OPENAI_API_KEY`，不要把 key 写在 notebook/repo 里。即便使用 API，默认输入依然是合成 SAP；要测试真实研究效果，还需替换为正式 SAP 和经审核的 Template Library。

**私有仓库提醒：** 如果仓库是 Private，Colab 的 `git clone` 不一定有权限。可以先在 GitHub 登录后打开 Notebook，但后续运行时克隆仍需要认证；推荐按学校的数据管理要求选择公开/私有方案，切勿把访问 token 写进提交代码。公开仓库只适合上传本包中可公开的合成示例。

## 台上讲解时的限制说明

- 目前只演示一个 Table 的五步工程流水线；Figure、Listing、整份 SAP 全自动 TFL 识别还未完成。
- Fixture 的成功运行是集成测试，不是模型抽取准确率。
- 验证报告主要检查证据字符串、Schema 和 DOCX 结构，不等于医学统计正确性保证。
- 展示一个实际失败案例（可以是后续真实 API 试验中记录的结果），不要把假设失败案例说成实测结果。

## 常见问题

- `ModuleNotFoundError: tfl_agent`：先跑 Notebook 的 GitHub 初始化 cell；若 Python 包刚更新，需要重启 runtime 后重新运行。
- `Repository not found`：核对仓库是否 Private、账号是否授权、URL 是否正确；GitHub SSH 地址不能直接替换成 Notebook 中的 HTTPS URL 而无需配置 SSH。
- `git pull` 失败：如果本机 clone 的仓库有未提交修改，先保存这些修改；新的 Colab runtime 可重新克隆。
- `No DOCX generated`：查看 `modification_plan` 和 `validation_report`，可能是 placeholder、检索或证据校验未通过。
