# 项目公开信息补全

默认采用 Tavily search → extract 正文 → 调用插件的Agent用自己的模型结构化核实（`--verifier grok`可改用Grok API）→ 带出处草稿，再交原轻投BP解析及人工确认。标准库实现；不改Java、数据库、原工商服务或原确认逻辑。enrich.py不创建pending、不确认、不更新项目；workflow.py在已授权且证据审阅后可经MCP补空值，不直连数据库。

## 运行

```sh
# 1. 生成核实任务 /absolute/verify-task.json（status=proposal_required）
python3 tools/project-enrichment/enrich.py \
  --company '法定公司全称' --sources-file /absolute/sources.json \
  --bp-text-file /absolute/bp.txt --output /absolute/draft.json
# 2. Agent 按任务核实、存为 proposal.json 后，带上结果和实际模型名重跑
python3 tools/project-enrichment/enrich.py \
  --company '法定公司全称' --sources-file /absolute/sources.json \
  --bp-text-file /absolute/bp.txt --output /absolute/draft.json \
  --proposal-file /absolute/proposal.json --model '实际模型名'
```

无人值守脚本可加`--verifier grok`改由Grok API核实。Grok支持 `GROK_API_KEY` / `XAI_API_KEY`、`GROK_BASE_URL` / `XAI_BASE_URL`、`GROK_MODEL`（默认grok-4.7）。凭据文件可含一行密钥赋值及一行HTTPS API基础地址，也可只含密钥；默认地址为https://api.x.ai/v1。兼容网关通过相同配置使用，实际服务方由部署者选择。文件路径可用`--grok-credentials-file`显式传入；都没配时读本机`~/.qtou/grok-credentials`。密钥不写代码、草稿或日志；不要在shell命令里直接传密钥。现有Grok CLI登录不能代替API凭据。

有`TAVILY_API_KEY`或本机`~/.qtou/tavily-key`可省略sources-file，脚本自动执行两次公开搜索并提取正文。无key时，Bot用已连接Tavily插件search、extract并提供下述文件，不索取聊天明文密钥，不把search摘要冒充正文：

```json
{"companyName":"法定公司全称","queries":[{"query":"实际查询词","searchedAt":"2026-10-29T12:00:00+08:00"}],"sources":[{"url":"https://example.com/about","title":"实际页面标题","content":"实际提取的页面正文","retrievedAt":"2026-10-29T12:00:00+08:00","publishedDate":null}]}
```

示例不是可用证据。检索优先官网、官方公告和权威工商来源；歧义先消歧。sources最多取12条，每条正文最多20000字；截断后核验只针对保留片段，不表示通读全文。Tavily提取失败的页不作为成功来源。没有正文或API失败会阻断本次补全，原业务可按原流程继续，但不能宣称已补全。

`--existing-file`接收原字段JSON；`--bp-text-file`接收原BP，并调用本地原`agent_bp_parse`读取已有字段。也可用`--parsed-bp-file`传入原解析结果（必须与BP对应）。来源与已有资料的companyName须与目标公司一致。交给核实模型的只有公司名和公开来源，不发送原BP及已有私有字段。

## 输出与边界

输出权限0600，含来源、查询记录、字段核验状态、missingOnlyPatch及requiresConfirmation=true。公司主体不一致、引文无法定位、冲突或无证据不进入补丁；引文须为20–200字的原文片段，允许空白规范化后比对。法人/资本/成立日/股东还要求权威政府或正式证券公告来源，且值出现在权威引文中；复杂值因此可能留空，不能为填满而放松证据。模型建议仍须人工审阅，引用存在不等于已完成人工事实核验。

已有非空字段（含0/false）不覆盖。`enrich.py`产出入池前建议；`profile.py`产出入池后的30项字段候选，实际写入走新增MCP工具，不直接写数据库。只有公司主体、正文引文、字段值和内部字典均核对通过的空值可写；资质、人数范围、历史融资须额外核实，内部管理和财务字段不推断。

## 已入池项目基本情况补全

1. `agent_projects_profile_get(pendingId)` 回读当前租户、原入池用户拥有的已确认项目及字段库存。
2. Tavily搜索并提取公开正文，保留真实query、searchedAt、retrievedAt、URL和正文。`python3 tools/project-enrichment/profile.py --help`查看核实参数：默认先返回proposal_required和verify-task.json，Agent核实后带`--proposal-file`、`--model`重跑。
3. `agent_projects_profile_fill(pendingId,evidence)` 默认仅预览，逐字段返回ready/preserved/unknown/needs_verification。
4. 用户明确授权补空值后使用同一工具并传`confirmed:true`，事务保存公司、扩展和项目字段及来源审计。权限不扩大，旧入池/天眼查接口保留。
5. 再次get并核验网页；重复相同补写应filledCount=0。荣誉对应项目页字段。原有字段不覆盖；未知字典不猜ID。该接口不上传PDF附件。

原confirm仍先走原工商服务；天眼查失败时可提交经审核的`companyFallback`公开证据，通过新增校验器形成有主体信息的公司记录。Bot须加载更新后的`skill/qtou/PROJECT-ENRICHMENT.md`，用户确认入池与授权补空值各按会话真实授权执行。

服务器需部署本目录、原MCP客户端及更新skill，配置该服务器的API凭据或可用Tavily插件；Mac路径不会自动在服务器生效。未配置时明确报失败，不回退编造。撤销本功能可移除新增目录并恢复skill新增段落，无业务数据迁移。

## 验证

```sh
python3 -m unittest discover -s tools/project-enrichment -p 'test_*.py' -v
```

结构化调用依据：[xAI Structured Outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs)。兼容网关是否支持该协议以真实请求为准，不自动降级为非Grok服务。


## 默认自动补全编排

Bot入池后使用`workflow.py --pending-id ID --output-dir 本轮目录`。本机运行包同等入口`runtime/project-enrichment/qtou-profile`自动加载原运行配置，不打印凭据。服务器需部署更新后的tools和skill，并按服务器实际MCP客户端/地址配置接入；LocalMcpClient 连接 `QTOU_MCP_URL`（默认 `http://113.250.189.74:18081/api/v1/agent/mcp`），凭据读环境变量 `QTOU_CONNECTOR_TOKEN`。

脚本盘点30字段，首轮安排工商公开+官方域、官网、正式披露查询；还有缺口则安排第二轮定向查询。运行时Tavily key存在时自动调用HTTP，没有时返回research_required，Bot须使用已连接插件执行research-plan.json，附实际查询凭证与正文，再用`--sources-file`继续。不要把research_required当成完成，不复制查询时间或用摘要冒充正文。

插件queries每项在原query/searchedAt外须含queryId、round、group、include_domains、source=tavily_plugin、status=success、hits和urls（直接采用计划参数，命中数和URL按实际响应记录）。失败写status=failed及脱敏code；失败查询不算覆盖。最多两轮检索；未查实、来源冲突、字典不匹配明确报告，不能称已穷尽公开资料。

默认由Agent核实（先返回proposal_required）并做MCP只读预览。Bot逐项审核主体、出处连续原文、值、日期及单位后，保留模型原产物和修订理由，传`--evidence-file 审核后文件 --apply`写入已授权的空字段；不传已审核证据文件时，即使加apply也只返回review_required。审核文件的sources和searchReceipts必须与当前来源完全一致。脚本检查读回项目/公司ID、实际写入值、原BP及所有非空值；失败明确报错。unknown或needs_verification存在则partial，不表示全部字段完成。网页验证仍由Bot执行，脚本result的browserVerificationRequired不是网页验证成功。

输出本轮before、research-plan、sources、evidence、preview、applied、after、result JSON；重复运行只针对当前缺失项。此流程由插件在BP入池/明确补全请求时触发，不是后台自动定时刷新。Java工商原流程保持不变。
