# 公开信息补全与天眼查兜底（主流程第 8 步、第 4 步）

## 检索工具顺序

1. 有已连接的 Tavily（插件 / 应用）：用它 search，再 extract 取正文，记 `source=tavily_plugin`。
2. 没有 Tavily：用你自带的联网搜索找网址，再逐个**打开网页**取正文，记 `source=agent_search`。只搜某个官方域名时在查询词里加 `site:`。

搜索结果摘要不能当正文；打不开的页面记失败，不用摘要顶替。检索失败不等于没有信息。

## 入池后补全工商与档案字段（第 8 步）

全程在对话里用 MCP 工具完成，不需要 Python，也不要跑插件里的脚本。

1. `agent_projects_profile_get({ pendingId })`：看哪些字段是空的（`value` 为空），只补这些。
2. 按上面的检索工具顺序查：工商登记（天眼查 / 企查查 / 爱企查 / 启信宝公司页、国家企业信用信息公示系统）、公司官网（简介、联系方式、地址）、正式披露（公告、年报、招股书）。至少这三组都查，缺的字段再定向查一轮。每个结果都要**打开网页取正文**。
3. 拼证据对象 `evidence`（字段名照抄）：

```json
{
  "schemaVersion": 1,
  "companyName": "<与项目公司全称一字不差>",
  "searchReceipts": [{ "query": "<实际查询词>", "searchedAt": "<date -u +%Y-%m-%dT%H:%M:%SZ 的输出>" }],
  "sources": [{ "id": "s1", "url": "https://…", "title": "<网页标题>",
                "content": "<网页正文：须含公司全称和下面的引文，可截取相关连续段落，30–20000 字>",
                "retrievedAt": "<同上，打开网页时的时间>", "publishedDate": "<有就写>" }],
  "modelProposal": {
    "companyName": "<同上>", "entityMatched": true,
    "fields": [{ "field": "juridicalPerson", "value": "张三", "status": "supported",
                 "evidence": [{ "sourceId": "s1", "quote": "<含 value 的连续原文，20–200 字>" }] }]
  }
}
```

   - 时间用命令 `date -u +%Y-%m-%dT%H:%M:%SZ` 取（UTC，结尾 Z；Windows 见 qtou-connect「Windows 命令」），不要手写、不要照抄示例，7 天内；`value` 必须逐字出现在 `quote` 里，`quote` 必须逐字出现在该来源 `content` 里。
   - 可补字段：`juridicalPerson` 法人、`foundingTime` 成立日期（YYYY-MM-DD）、`registeredCapital` 注册资本（带单位，如「1000万元」「2839.0417万人民币」）、`registeredCurrency`、`state` 经营状态、`type` 工商类型、`registrationAuthority` 登记机关、`sociaCreditCode` 统一社会信用代码、`registeredAddress` 注册地址、`englishName`、`province` 省份、`abbreviation` 简称、`companyWebsite` 网址、`officeAddress` 办公地址、`contactNumber` 电话、`companyMailbox` 邮箱、`companyProfile` 简介、`staffNumber` 员工数（纯数字）、`officialAccounts` 公众号、`primaryBusiness` 主营业务、`businessModel` 商业模式、`cityValue` 城市、`projectShorthand` 项目简称、`yewu` 一句话描述（≤30 字）、`isListing` 是否上市、`honour` 荣誉、`productionAddress` 生产地址。找不到的字段不写进 `fields`。
4. `agent_projects_profile_fill({ pendingId, evidence, confirmed: false })` 预览：`status=ready` 的会写；`needs_verification` 看 `reason`（引文没逐字匹配、单位不对、字典没匹配等），能改就改好再预览，改不了的放进汇报。
5. 逐项核对预览：主体是否本公司、引文是否连续原文、值和单位是否对。确认入池即授权补空值，不再问用户，调 `agent_projects_profile_fill({ pendingId, evidence, confirmed: true })` 写入。
6. `agent_projects_profile_get({ pendingId })` 读回，写入的字段都在才算完成；没补上的字段和原因列进汇报。

核实规则：
- 同名公司、子公司、母公司、关联公司的信息不能写到本公司；拿不准就留空。
- 法人、注册资本、成立日期、统一社会信用代码、登记机关、注册地址、股东只采工商登记信息：国家企业信用信息公示系统、正式公告，或天眼查 / 企查查 / 爱企查 / 启信宝的公司公开页（它们转载工商公示，页面须出现本公司全称）；招聘站、黄页、建设通这类聚合站不算。公示系统有验证码打不开时，就去这四家找，不要因为打不开公示系统就留空。注册资本带单位（元 / 万元）。
- 员工数核对时点和范围，参保人数、「公司及控股子公司」人数不是本公司员工数；资质核对有效期。
- 新三板挂牌不等于 A 股上市；地区、币种、状态、工商类型按字典映射，不猜 ID。
- 页面上 AI 生成的分析段不算披露事实。

## 天眼查查不到时的兜底建档（第 4 步）

`agent_projects_confirm` 返回「天眼查未取得有效公司」、且查不到同字号的工商现名（查到了就带 `companyName` 重试，见 SKILL.md 第 4 步）时，待确认记录保留，不要重新建 pending：

1. 按检索工具顺序找公司官网、工商公开页、正式披露，取正文，存成 sources 文件：`{"companyName", "queries": [{"query", "searchedAt"}], "sources": [{"url", "title", "content", "retrievedAt", "publishedDate"}]}`。
2. 核实主营业务，拼 `companyFallback`：和第 8 步的 `evidence` 一样带 `schemaVersion`、`companyName`、`searchReceipts`、`sources`（1–12 条）、`modelProposal: { companyName, entityMatched: true }`，另加
   `"fields": [{ "field": "business", "status": "supported", "suggestedValue": "<主营业务原话，至少 10 字>", "evidence": [{ "sourceId": "s1", "quote": "<含该原话的连续原文，20–200 字>" }] }]`。
3. 用户原来的确认仍有效：`agent_projects_confirm({ pendingId, confirmToken, companyFallback })` 重试同一个 pendingId。法人、注册资本等工商字段这一步先留空，不从模型猜；入池后第 8 步按上面的工商来源补齐。
4. 证据被拒时如实报原因，记录保持待确认，不用空壳公司兜底。数据库或权限错误不要说成天眼查查不到。

插件 `tools/project-enrichment/` 里的脚本只给无人值守的定时任务用，对话里不用。Tavily / Grok 密钥不进聊天、不写进文件或日志。
