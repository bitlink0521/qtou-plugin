# 公开信息补全与天眼查兜底（主流程第 8 步、第 4 步）

## 检索工具顺序

1. 有已连接的 Tavily（插件 / 应用）：用它 search，再 extract 取正文，记 `source=tavily_plugin`。
2. 没有 Tavily 插件但本机有 Tavily key（`TAVILY_API_KEY` 或 `~/.qtou/tavily-key`）：脚本自动检索。
3. 都没有：用你自带的联网搜索找网址，再逐个**打开网页**取正文，记 `source=agent_search`。计划要求只搜官方域名（`include_domains`）而你的搜索不支持时，在查询词里加 `site:`，receipt 里的 query 和 include_domains 照抄计划。

搜索结果摘要不能当正文；打不开的页面记失败，不用摘要顶替。检索失败不等于没有信息。

## 入池后补全工商与档案字段（第 8 步）

脚本在插件根目录 `tools/project-enrichment/`（本技能目录的 `../../tools/`），只用 Python 标准库。按返回的 `status` 循环执行，直到结束：

```bash
python3 <插件根目录>/tools/project-enrichment/workflow.py --pending-id <pendingId> --output-dir <本轮证据目录>
```

| 返回 status | 你要做的 |
|---|---|
| `research_required` | 按输出目录里的 `research-plan.json` 逐条检索并取正文，把真实查询（`queryId`、`query`、`include_domains`、`round`、`source`、带时区的 `searchedAt`、`status`、`hits`、`urls`）和正文（`url`、`title`、`content`、`retrievedAt`、`publishedDate`）存成 sources 文件，再加 `--sources-file <文件>` 重跑。第一轮至少覆盖工商（含官方域）、官网联系方式、正式披露三组；还缺字段时脚本会给第二轮定向计划，照做，最多两轮。 |
| `proposal_required` | 读 `verify-task.json`，**只依据其中的 publicSources** 按 instructions 和 schema 逐字段核实，存成 JSON，再加 `--proposal-file <文件>` 重跑。检索和核实都由你完成，不需要模型名。 |
| `review_required` | 逐项读 `evidence.json`：主体是否是本公司、引文是否是连续原文（20–200 字）、值和日期单位是否对。改动另存 `evidence-reviewed.json` 并写明理由，然后加 `--evidence-file <文件> --apply` 写入（确认入池即授权，不再问用户）。 |
| `complete` / `partial` / `already_complete` | 结束。`partial` 时把 `unresolved` 里每个字段和原因列进汇报。 |
| `failed` / `research_failed` | 把 code 和 message 如实写进汇报，不换路径重试。 |

核实规则：
- 同名公司、子公司、母公司、关联公司的信息不能写到本公司；拿不准就留空。
- 法人、注册资本、成立日期、股东只采工商公示或正式公告；注册资本带单位（元 / 万元）。
- 员工数核对时点和范围，参保人数、「公司及控股子公司」人数不是本公司员工数；资质核对有效期。
- 新三板挂牌不等于 A 股上市；地区、币种、状态、工商类型按字典映射，不猜 ID。
- 页面上 AI 生成的分析段不算披露事实。

## 天眼查查不到时的兜底建档（第 4 步）

`agent_projects_confirm` 返回「天眼查未取得有效公司」时，待确认记录保留，不要重新建 pending：

1. 按检索工具顺序找公司官网、工商公开页、正式披露，取正文，存成 sources 文件：`{"companyName", "queries": [{"query", "searchedAt"}], "sources": [{"url", "title", "content", "retrievedAt", "publishedDate"}]}`。
2. 运行 `python3 <插件根目录>/tools/project-enrichment/enrich.py --company '<公司全称>' --sources-file <文件> --output <draft.json>`，返回 `proposal_required` 后按 `verify-task.json` 核实，加 `--proposal-file` 重跑得到 `draft.json`。主营业务（business）的值必须是引文里逐字出现的原话（至少 10 字）。
3. 用户原来的确认仍有效：`agent_projects_confirm({ pendingId, companyFallback: <draft.json 的内容> })` 重试同一个 pendingId。`confirmToken` 不是该工具的入参。法人、注册资本等工商字段留空，不从模型猜。
4. 证据被拒时如实报原因，记录保持待确认，不用空壳公司兜底。数据库或权限错误不要说成天眼查查不到。

Grok API 只给无人值守脚本用（`--verifier grok`，凭据在 `~/.qtou/grok-credentials`）；你在对话里执行时不用。Tavily / Grok 密钥不进聊天、不写进文件或日志。
