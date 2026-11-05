---
name: qtou
description: >-
  连接并使用轻投：MCP 地址与鉴权、弹表单收账密代签 agent_key（前缀 qtpat_）、三场景（入池/尽调/预警）、AC MC3
  确认卡（确认入池后自动补全、应写尽写）、场景②文档检索→读正文→先学系统里已有报告或用户模板再写尽调报告、场景③投后名单→季度财务→外网三类信号→分级带出处预警→确认后回写。用户说连轻投、装轻投
  MCP、入池、查文档、写尽调报告、投后巡检、风险预警时用。
---
# 轻投

同事 bot / Agent 安装本插件后，用户说「连轻投 / 装轻投 MCP / BP 入池 / 查文档尽调 / 写尽调报告 / 投后预警」即按下列执行。

## 默认项目补全入口

收到BP还必须执行[BP图文完整提取](BP-VISUALS.md)：逐页检查页面图像、Logo、团队照片、表格及图片文字，按字段/子表/附件补齐并回读与网页验收；不得只提文字或把姓名生成头像当已提取照片。

用户提供BP时，必须先用agent_projects_bp_schema完整盘点字段及子表，按PROJECT-ENRICHMENT.md的完整BP流程提取、确认、入库和回读；不能只填工商或简介。用户提供项目名称、公司名称或BP并要入池时，默认先执行[项目基本信息补全](PROJECT-ENRICHMENT.md)：Tavily检索/提取与Grok有出处整理，已有字段不覆盖，确认卡上带补全建议和缺口。入池仍须用户点卡确认，不替代原工商逻辑。用户确认入池后按「入池后自动补全」直接补写（bp_attach → bp_assets → profile_fill），不逐项问，经原文审核后写入并回读核验。具体执行入口和停止条件见PROJECT-ENRICHMENT.md，不能只建公司关联就结束。

## MCP

| 项 | 值 |
| --- | --- |
| URL | `<QTOU_MCP_URL>`（由 G02 的 qtou-login 安装时写入实际地址；正式域名部署时再定） |
| 传输 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <agent_key>` |
| 连接器名 | `qtou`（Grok 上手工添加的可能叫 `轻投`，二者等价） |
| 插件变量 | `QTOU_CONNECTOR_TOKEN` |

只认 Bearer `agent_key`（由 `POST /v1/agent/auth/login` 签发），不读 cookie。无效/吊销 → 401（或业务码 `10007`）。

签发：弹表单收账密（不收 PAT）→ 代调 `POST /api/v1/agent/auth/login`（与 MCP 同主机）→ 得窄 scope `agentKey` → 写入 `QTOU_CONNECTOR_TOKEN`。审计不写密码明文；key 永不进聊天。兼容别名 `POST /v1/agent/tokens`。

装连接器：优先团队市场 / Marketplace 插件 qtou。Grok Bot 上若 `轻投` 报 Network error，改用 stdio 等价连接器（`轻投stdio` / `轻投本地`）。禁止手填 URL、禁止手抄 PAT。

旧的独立 qtou-mcp 服务不是成品，只认插件配置的 `<QTOU_MCP_URL>`。

**禁止直调 HTTP（强制）**：除上面「签发」这一步把账密换成 key、并直接写入 `QTOU_CONNECTOR_TOKEN` 以外，模型不得自己读取 `agent_key` / `QTOU_CONNECTOR_TOKEN`（不读插件变量、配置文件、环境变量、钥匙串），不得拿它用 curl / 脚本 / fetch 直接调 `/api/v1/agent/**` 任何接口（含 confirm、reject、写入类接口）。一切业务操作只走 MCP 工具。不得用 curl、脚本等自行调用 MCP 端点或 REST 接口，只能通过已配置的连接器工具。MCP 连不上或缺工具时，如实报错并停止，不改用 HTTP、不直连库。服务端审计会把不经 MCP 的直调请求单独标出（`direct_http=true`）。唯一例外是 `agent_projects_bp_upload_url` 发回的一次性上传地址（见「入池后自动补全」），它不带也不收 key。

## 接入（强制）

1. 已连且冒烟通则结束。
2. 未装或 401：弹表单收轻投账密。
3. 代签 → 写入变量 → 冒烟只读工具。

## 工具最小集（13 个）

`agent_health` · `agent_bp_parse` · `agent_projects_create_pending` · `agent_projects_get` · `agent_projects_confirm` · `agent_projects_reject` · `agent_documents_search` · `agent_documents_content` · `agent_portfolio_list` · `agent_portfolio_quarterly` · `agent_risk_alerts_list` · `agent_risk_alerts_create` · `agent_dicts`

入池补全另用：`agent_projects_bp_schema` · `agent_projects_bp_get` · `agent_projects_bp_fill` · `agent_projects_bp_upload_url` · `agent_projects_bp_attach` · `agent_projects_bp_pages` · `agent_projects_bp_assets` · `agent_projects_bp_source` · `agent_projects_profile_get` · `agent_projects_profile_fill`（见 PROJECT-ENRICHMENT.md、BP-VISUALS.md）。

若连接器工具列表里没有 `agent_documents_content`，是客户端缓存了旧列表：先重连 / 重启该 MCP 再查；仍没有则报「服务端未部署 content」，不得改用别的路径读文件。
`agent_portfolio_quarterly` / `agent_risk_alerts_create` 缺失同理：重连后仍缺报「服务端未部署场景③工具」，不得改用 HTTP 或直连库。

写操作一律待确认，禁止静默入池。入池 confirm 必须带确认卡发出的 `confirmToken`，见 AC MC3。例外：用户已点「确认入池」的项目，其补空值类写入（bp_attach / bp_assets / bp_fill / profile_fill）按下节自动执行，不再逐项确认。

**返回形状与错误（2026-10-28 起，HTTP 与 stdio 一致）**：检索/列表类工具（`agent_documents_search` / `agent_portfolio_list` / `agent_risk_alerts_list` / `agent_dicts`）一律返回 `{ items: [...] }`，从 `items` 取。工具失败返回 `isError=true`，正文是 `{"error":{"code","message","tool"}}`。code 包括 `INVALID_ARGUMENT`、`NOT_FOUND`、`FAILED_PRECONDITION`、`BACKEND_DB_ERROR`、`INTERNAL_ERROR`，桥侧还有 `UPSTREAM_UNAVAILABLE` / `UPSTREAM_HTTP_*` / `UPSTREAM_RPC_*`。拿到这类返回时，把 code 和 message 如实告诉用户，不得重试成别的路径（HTTP、直连库、读本地文件），也不得写成「没找到」。message 已是给人看的中文说明，不含服务器路径和 Java 异常；带 `ref=…` 的表示详情只在服务端日志，转告用户时把 ref 一并给出，方便管理员查日志。（2026-10-28 s2c 起）`UPSTREAM_HTTP_*` / `UPSTREAM_BAD_RESPONSE` 等桥侧错误的 message 也带 `ref=…`，与桥 stderr 同一个；`NOT_FOUND` 只说什么不存在（如「项目不存在或不属于当前租户」「文件不存在」），不再回显传入的 id，需要时自己对照刚传的参数告诉用户。stdio 上 `arguments` 不是对象时返回 isError `INVALID_ARGUMENT`「参数 arguments 格式不对，应为对象」（与 HTTP 相同）；发出的行不是合法 JSON 会立刻收到 JSON-RPC `-32700`（id=null），不是 JSON-RPC 对象或 params 不是对象收到 `-32600`，桥不会断，修正后重发即可。（2026-10-28 s2d 起）桥 stderr 只记脱敏、截断后的摘要：令牌、Bearer、token/password/secret/cookie/agent_key 等字段值一律显示为 `***`，单行坏请求不超过 300 字符，上游原文不超过 800 字符。排障时用 ref 对照，不要指望在 stderr 里看到原始请求。

## 入池后自动补全（强制，应写尽写，不逐项问）

入池本身不变：仍按下方 AC MC3，`agent_projects_create_pending` 后必须弹卡，用户点「确认入池」才 confirm。用户确认入池（或要求补全某个已入池项目）即视为本项目补空值授权，之后补全写入不再逐项问，按顺序做完：

1. **BP 附件** `agent_projects_bp_attach`：原 BP 转 PDF，≤20MB（超限可去掉内嵌视频、压图）。先调 `agent_projects_bp_upload_url({ pendingId })` 拿 `uploadId` 和一次性上传地址（绑定该 pendingId，约 10 分钟有效，传一次即失效，不需要也不接受 agent_key），把 PDF 原样 PUT 上去，再调 `agent_projects_bp_attach({ pendingId, uploadId, confirmed })`；不要再把整份 PDF 转 base64 塞进参数。回读 fileId / SHA256。
2. **BP 素材** `agent_projects_bp_assets`：logo、团队头像、证据图，按 [BP-VISUALS.md](BP-VISUALS.md)。
3. **档案字段** `agent_projects_bp_fill` / `agent_projects_profile_fill`：BP 字段与子表、工商及公司档案补空。完整 BP 证据已在 create_pending 时存在服务端，`bp_fill` 传 `evidenceId` 取用，不再把整份 evidence 重发一遍。evidenceId 只能复用 create_pending 时存的证据；没有的（旧项目或新证据）要完整传 evidence。

每项先 `confirmed=false` 内部预览自检（主体、值、出处、字典映射），通过就直接 `confirmed=true` 写入并回读；预览不发给用户等批准。自检不过的项不写，记入缺口。

**字典字段想办法填上（行业、细分领域、轮次、币种、沟通方式等）**：材料里的说法和字典选项不完全一致时，不要直接留空——先看 `agent_projects_bp_schema` / `bp_get` 返回的该字段全部选项，选语义最接近的一项写入（如「智能制造」→「生产|加工|制造」或「高科技」），汇报里注明「按最接近归类：原文 X → 选项 Y」。只有所有选项都明显无关时才留空并写原因。币种材料没写时，服务端会按公司注册资本币种补，不用另传。

主动上网补齐入池所需的全部信息：工商字段、官网、主营业务、简介、荣誉、融资、地址、联系方式等，按 [PROJECT-ENRICHMENT.md](PROJECT-ENRICHMENT.md) 两轮 Tavily 检索并提取正文。天眼查查不到时，confirm 带 `companyFallback`（Tavily + Grok，schemaVersion=1）。

底线（任一不满足，该项不写）：

- 每个值都有出处，引文逐字核对；不编数字。
- 法律主体一致：母公司、子公司、关联公司、同名公司的数据不得写到本公司名下。
- 已有值不覆盖（含 0/false）；要替换须另行问用户。
- 返回 `duplicate` 时直说「重复，已经有了」，附已有记录（id、名称），不重试、不另建。
- 私有 BP 不发给外部模型；交 Grok 的只有公开网页资料。

做完一次性汇报：写了哪些字段及各自来源；仍空着的字段及原因（无可靠公开来源 / 主体对不上 / 冲突 / 字典不匹配 / 提取失败）。

## AC MC3：入池确认卡（强制）

规则速查（细节见下文及 PROJECT-ENRICHMENT.md）：
- **文字确认卡**：客户端不支持卡片组件时，用文字确认卡代替，用户明确回复「确认入池」才 confirm。
- **askUser 需要你补充**：create_pending / confirm / bp_get 返回的 `askUser` 字段（联系人、推荐人、沟通方式、生产地址等）在确认卡里列成可选的「需要你补充」，不阻塞入池；用户回答后用其原话调 `agent_projects_user_fields`。
- **BP 没写披露日期照常入池**：document.asOf 与各字段 asOf 留空即可，历史/计划/预测内容标「未注明日期」照常写入；只有当前事实和当前融资需求需要日期。不要用文件导出日期冒充，也不要因此停下来问用户。

轻投网页没有 Agent「待确认」菜单。入池不得引导「去网页确认」。

流程：

1. `agent_bp_parse`（可选）→ 展示草稿字段。
2. `agent_projects_create_pending` → 得到 `pendingId`（此时仍非正式池）和只给确认卡用的 `confirmToken`（服务端只存其哈希，绑定 pendingId 与当前用户，限时、confirm 成功后作废）。可直接传 `companyName`（法定全称）。
3. 必须弹聊天确认卡：客户端支持卡片组件（widget）就用组件；不支持（如 Codex CLI、Cursor 等纯文字客户端）就用一段文字确认卡代替，内容与组件卡相同（项目名、pendingId、置信度/轮次行业缺口、公司全称），末尾问「确认把该项目入正式池？」并列出两个选项，然后停下等用户回复。将 `askUser` 按标签列为可选的「需要你补充」清单，不阻塞入池；用户回答后，以其逐字原话为 `statement` 调 `agent_projects_user_fields({ pendingId, statement, fields, confirmed:false })` 预览，无问题再 `confirmed:true` 写入并回读，不猜联系人等值。用户明确回复「确认入池」即视为点了确认；回复含糊时再问一次，不得自行推断。选项至少：
   - 「确认入池」→ 用户点了之后，才调 MCP 工具 `agent_projects_confirm({ pendingId, confirmToken })`，token 取自这张卡。没带或带错 token 的 confirm，服务端一律拒绝（`FAILED_PRECONDITION`）。
   - 「取消/驳回」→ 调 MCP 工具 `agent_projects_reject`，或什么都不调；不得 confirm。
   - 连接器里没有 `agent_projects_confirm` / `reject`（例如 stdio 未更新）：先重连；仍没有就如实报「服务端/连接器缺入池确认工具」并停止，不得改用 HTTP 调 confirm。
   - **入池写入参数传 JSON 对象，每步只调一次**：建待确认、选公司、确认入池、驳回、挂 BP 这些写入调用，`arguments` 直接传对象，不要把整个参数序列化成一段字符串（会返回 INVALID_ARGUMENT「参数 arguments 格式不对，应为对象」）；`confirmed` 传布尔 `true`，对象参数传对象、数组传数组，schema 写数字的参数传数字（不写成带引号的字符串）。同一个项目每个写入工具只调 1 次，一次传对，不靠换格式试；返回成功或 `duplicate: true`，这一步就结束。只有返回内容类 INVALID_ARGUMENT（如字段值不合规）时，才按 message 改内容后再调。
4. 禁止：未弹卡（组件或文字卡）就 confirm；禁止用户未点同意就入池；禁止不经确认卡、自己拿 token 调 confirm；禁止用 HTTP 直调 confirm / reject。

确认卡文案：展示项目名、`pendingId`、置信度/轮次行业缺口；问「确认把该项目入正式池？」

## Demo：BP 入池

- 用户丢 BP /「入库」
- Bot：parse → create_pending → 弹确认卡（带 confirmToken）→ 用户确认后 MCP confirm → 自动补全（附件、素材、档案）→ 一次性汇报；取消则 reject/不调。

## 场景②：文档检索 → 尽调报告初稿（强制步骤）

触发：用户给项目名或文档名（可带错别字），要「找文档 / 写尽调报告初稿」。只读，不改库。

1. **检索**：`agent_documents_search({ q: "<项目名或文档名>" })`。
   - （2026-10-28 s2d 起）**必须给 `q`，或者给 `projectId` 列这个项目的全部文档**。两个都没给、或者 q 只有空白，返回 `INVALID_ARGUMENT`「缺少 q：…」，不再静默返回全库列表。参数名只认 `q`、`projectId`（`project` 是别名），写成 `keyword`、`query` 等返回 `INVALID_ARGUMENT`「参数 xx 不认识，可用参数：…」，改名后重发，不要改成不传参。`agent_portfolio_list`（afterInvestOnly、q）和 `agent_risk_alerts_list`（projectId/project、state）也照此检查参数名，不传参仍是合法的名单查询。
   - 先精确（LIKE），0 命中时服务端自动退到错字容错（返回 `matchMode=fuzzy`、`fuzzyScore`）。
   - 把命中列给用户：文档名、`fileId`、库表定位（table / relation / library id）、`readable`。fuzzy 结果要注明「按近似匹配找到」，同分并列时让用户确认是哪一个项目。
   - 排序是稳定的：fuzzy 按 `fuzzyScore` → `projectScore`（命中项目名的程度）→ 更新时间 → id 排，exact 按更新时间 → id 排，同一个查询每次顺序都相同。query 里带了项目名（哪怕有错字）时，目标项目排在前面。`tied=true` 表示这条和相邻条目同分并列；query 里没有项目名时（例如只搜「商业计化书」），多个项目会并列，这时**必须**让用户确认项目，或者带 `projectId` 重查。
   - 返回里的 `path` 只是「相对文件夹/文件名」（如 `qtou-stor-support-local/<fileId>.pdf`），不是服务器路径，也不含租户 id；读不到实体文件的为 null。只用于展示，不得拿它去读本地文件，读正文一律用 `fileId`。
   - 读正文返回 `isError` 且 `error.code=FAILED_PRECONDITION`（本地无实体文件）时，记为「未读：无实体文件」（交付消息里说明），其余文档照常处理。
   - 0 命中：如实说没找到，请用户换关键词；不得编造文档。
2. **读正文**：对确认属于该项目、`readable=true` 的每份文档调 `agent_documents_content({ fileId, maxChars })`。
   - 被拒（跨租户 / 无权限）或不可读：记下未读及原因（交付消息里说明），不得绕道读文件。
3. **定写法（写前三步，强制，见 [DD-REPORT-WRITING.md](DD-REPORT-WRITING.md) 第 0 节）**：
   ① 先跨项目搜系统里已有的报告：`agent_documents_search` 搜「尽调报告 / 投资建议书 / 尽职调查 / 投决报告」等（不带 `projectId`；这是找范本，`tied` 并列不必让用户确认项目），挑 1–3 份读全文，学结构、用词和排版，以它为准；
   ② 找不到就开写前问用户有没有模板或范本，给了就以它为准；
   ③ 两样都没有，才用 DD-REPORT-WRITING.md 的规范兜底。
   范本只学写法，不搬它的公司事实和数字。
4. **出报告**：事实只用第 2 步读回的本项目正文。
   - 结构、用词、排版按第 3 步定下的范本。
   - 报告正文不加引文、脚注、来源表、「编制说明」等证明或免责文字（见 DD-REPORT-WRITING.md 第 5 节）。
   - 材料里没有的写「待补」，不推算、不补外部常识或猜测。
   - 「待补」就写在缺信息的那一处（那一节、那一行），不挪进「待核实问题清单」或其他问题清单；问题清单只放材料里有、但需要向企业核实的事项。
   - 工作底稿另存来源记录（事实/数字 → 文档名、fileId、原文逐字摘录、自算数的算式），供自检和备查，不放进交给用户的报告正文。
5. **交付前自检（强制）**：按 DD-REPORT-WRITING.md 第 12 节；对照工作底稿逐条核对每个数字能在材料原文找到或由其算出，任何一条不过就改到过为止，不交半成品。交付消息（不写进报告）里说明：参照了哪份范本（文档名 + fileId / 用户模板 / 插件兜底规范）；这是初稿、待投资经理复核；未读文档及原因；「待补」清单；材料为模拟或测试数据时一并说明。
   - **报告全文直接贴在对话回复里**：交付时把整份报告正文（不是摘要）贴进回复；不得只写到本地文件、只给文件路径或链接。用户另要文件时可以另存，但对话里仍要有全文。

## 场景③：投后风险预警（强制步骤）

触发：用户要「投后巡检 / 风险预警 / 看看投后项目有没有风险」。默认只读；回写必须逐条确认。

1. **取名单**：`agent_portfolio_list({ afterInvestOnly: true })`（可加 `q` 过滤）。记下每家的 projectId、项目名、公司全称、法人、成立日期、行业、投资日期，后面外网查询用全称消歧。同名项目（项目名相同、公司全称/法人不同）分开处理，不得合并。
2. **取季度数据算财务异常**：每家调 `agent_portfolio_quarterly({ projectId })`（可带 `from`/`to`，格式 YYYYQn）。
   - `finance` 每季两行：`type=current` 是本期，`type=samePeriod` 是去年同期，`reportCycleOf` 是所属季度。同比 = current ÷ samePeriod − 1。
   - 只认读回的数，自己算的数写明算式。财务类须 ≥2 季数据（`financeQuarterCount`），不足标「数据不足」，不定级；外网两类照查。
   - 返回「项目不存在或不属于当前租户」= 拒绝，如实报，不换路径。
3. **查舆情与公告**：每家都查，用公司全称 + 法人/成立日期消歧。
   - 舆情（近 90 天）：舆情先用 `risk_tyc_news`，没结果再外网查（财经/主流媒体）；外网结果同一事件 ≥2 家独立媒体才算确认。报告、卡片里舆情和所有检索区间行一律写成「检索窗口：近N天（YYYY-MM-DD 至 运行日）」，终点写运行当天日期；正例 `- 舆情检索窗口：近90天（2026-08-04 至 2026-11-02）`；反例（缺「检索窗口：近N天」，不合格）`- 舆情：2026-08-04 至 2026-11-02`。
   - 公告（近 12 个月）：巨潮资讯/交易所/全国股转；国家企业信用信息公示系统；中国执行信息公开网、裁判文书网；检索区间行同样写「检索窗口：近365天（YYYY-MM-DD 至 运行日）」。
   - 主体对不上的结果不进预警；拿不准标「待核实」，不定级。
4. **分级**（每条写明命中哪一条）：
   - 高 high：失信被执行人/限高；破产、重整、清算；实控人被采取强制措施；净资产转负；营收同比降 ≥50%；营收以外关键财务指标（净资产/总资产/净利润）较上期或上年末降 ≥50%；严重违法失信名单；退市：交易所已作出终止上市决定、已进入退市整理期、新三板（全国股转系统）终止挂牌。
   - 中 medium：新增被执行或作被告的重大诉讼；行政处罚；经营异常名录；核心高管离职公告；≥2 家独立媒体负面报道；营收同比降 30%–50%；营收以外关键财务指标较上期或上年末降 30%–50%（含 30%，不含 50%）；连续 2 季亏损且扩大；资产负债率 >70%；季报逾期未报；退市风险：被实施退市风险警示（*ST）、收到终止上市事先告知书（尚未作出终止上市决定）。
   - 低 low：只有 1 家媒体的负面报道；轻微处罚；关键指标波动 15%–30%（不含 30%）。降幅超过 30% 按中/高档，不得因「没有对应档位」降级。
   - 退市条款按进程阶段定级（2026-10-28 产品定）：已作出终止上市决定 / 进入退市整理期 / 新三板终止挂牌 → 高（网页显示「重大」）；*ST、终止上市事先告知书 → 中（「警告」）。
     - 判断看「交易所是否已作出决定」：标题写「拟…终止上市」「终止上市事先告知书」的仍是告知阶段，算中，即使正文出现「终止上市决定」字样也不升高。
     - 同一退市进程（*ST → 事先告知书 → 终止上市决定 → 退市整理期 → 摘牌）按已到达的最高阶段只算 1 条（产品已定）；*ST 不另记中档。之前经过的各阶段必须写进这条的事件描述，各阶段公告作为出处并列，不能丢；摘牌不另立一条。
     - 只有 ST（无星号）、撤销/申请撤销退市风险警示，不命中本条；按其他条款或标「待核实」。
     - 引起退市的原因事件（如欺诈发行行政处罚）按「行政处罚」等原条款另定一条，不与退市合并。
     - 例：元道通信 2026-09-21 收到深交所终止上市决定 → 高（重大）。
   - 降幅 =（基期 − 本期）÷ 基期 × 100%，基期须 >0（基期为负或为 0 不算降幅，如亏损扩大走「连续 2 季亏损且扩大」）。边界：29.99%→低，30%→中，49.99%→中，50%→高。
   - 净资产、总资产是时点数，足 2 期（本期 + 上期或上年末）就能定级；同比缺去年同期、连续两季缺单季数据，照旧标「数据不足」，不定级。
   - **季报逾期未报怎么判（看报送状态和应报截止日，不看 `update_date`）**：截止日 = 季末 + `report_due_days` 天（四季度/年报用 `report_due_days_q4`），截止日当天不算逾期。只有运行日已过截止日、且 `agent_portfolio_quarterly` 返回的 `reports` 里没有该季度记录，才算「季报逾期未报」。有该季度记录就是已报，不论 `status`（`2` 审批通过、`1` 审批中、`0` 初始、`3` 审批不通过、`7` 撤回），不算逾期；`status=2` 的季报绝不能判逾期。`update_date` 是记录最后修改时间，不是报送时间，不得拿它和截止日比，也不得据此写「迟报」「逾期 N 天」。
     - 正例：运行日 2026-11-02，2026Q3 截止日 = 2026-09-30 + 30 天 = 2026-10-30，`reports` 里没有 2026Q3 记录 → 中「季报逾期未报」，出处写「`agent_portfolio_quarterly` 无 2026Q3 记录；截止 2026-10-30」。
     - 反例（不合格）：`reports` 里有 2026Q3 记录（`status=2`，`update_date` 2026-10-31 10:11:13），写成「2026-10-31 录入，超截止日 1 天，季报逾期」→ 该季已报，不出这条预警。
   - 财务类写入时，出处要带同一字段两期的轻投记录 id（本期 + 基期）：服务端按 recordId 回读数据库复算档位，`grade` 低于复算档位会返回 INVALID_ARGUMENT「等级低于财务核算档位…不得因无档位降级，本次未写库」，按提示改等级重试；写入成功时响应 `gradeCheck` 带定级核算（如 C1 净资产 … 降 xx.xx%，落 30%–50% 档→中(medium)）；E7 v2 起不再自动写进意见结论，员工要看就自己精简写进正文 `conclusion`。
   - （2026-10-28 s3 R3 起）财务出处只覆盖 1 期（每个字段只有 1 个报告期）时照样可写：服务端仍按 recordId 核对属于本项目、原值与库一致（不一致 INVALID_ARGUMENT 不写库），但算不了环比，返回 `gradeCheck:{status:"skipped",reason:"仅 1 期，无法算环比"}`，（E7 v2 起不写进意见结论）。报告与确认卡照实写「仅 1 期，未核算档位」。≥2 期照旧复算。
   - 同一事件多源只算 1 条，出处并列。
   - （2026-10-28 s3c5 起）只要 sources 里带本项目财务 recordId（净资产/总资产/净利润），**不论 riskType**（财务/指标/业务/其他）服务端都复算档位；等级低于档位返回 INVALID_ARGUMENT，不写库。
   - 财务出处 `{recordId, field, value, formula}`：field 用 func_project_quarterly_finance 列名（net_assets、total_assets、net_profit…；中文名也认，会统一成列名）。value 照 `agent_portfolio_quarterly` 返回的原值抄；服务端按 recordId+field 读库核对，容格式差（1e8 = 100000000.00 = 100,000,000，差 ≤0.005 算一致），不一致返回 INVALID_ARGUMENT「出处原值与轻投记录不符…」，不写库。**value、formula 都必填**，缺任一返回 INVALID_ARGUMENT，不写库，服务端不回填。出处索引里显示的是库值写法（「[i] 轻投记录 id 列名=库值」）。field 只收纯列名（正：`business_income`；反：`2026Q3 business_income`、`business_income=123`）；季度写在确认卡的「季度」栏，不拼进 field。每条财务出处都要有 formula。
   - recordId 不属于本项目，或用非财务字段名配财务 recordId，都会被拒。
   - **落库映射（Song He 2026-10-28 定，不加字典）**：入参 `grade` 仍只传 high|medium|low；服务端映射到网页字典 `risk_grade`：high→`significant_risk`「重大」；medium、low→`controllable_risk`「警告」；`no_risk`「正常」永不写入。报告与确认卡写「初判 高/中/低 → 网页显示 重大/警告」，两边说法一致，不得自造其他等级名。
5. **出处（硬门）**：每条预警都要能核对。
   - 外网：来源标题 + **可打开的 URL**（本轮亲自打开过）+ 发布日期 + ≤200 字**原文摘录**（逐字）。
   - 财务：每个出处一行，四栏分开写：recordId（finance 行 `id`）｜field（纯列名，如 `business_income`，不带季度、不带 `=值`）｜季度（如 2026Q3，只写在这一栏）｜value（库里原值）；
     每行另带本条用到的计算式（同一算式用到的两行都写上），如 `(32000000−14400000)÷32000000=55%`，即同比下降 55%（2026Q3 vs 2025Q3）。
     写入时 sources 逐行照抄：recordId←recordId，field←field，value←value，formula←该行算式；季度栏不进 field。
   - 一条假链接或摘录对不上 = 整包作废。禁止编造事件、链接、数字。
6. **查询失败标「查询失败」**：某源超时/报错/打不开，就在该源写「查询失败」及原因，**不得**写成「未发现」或「无风险」；其余源照常。全部没信号就明说「未发现风险信号」并附查询范围，不硬凑。
7. **出报告**：①总览（企业数、高/中/低条数、查询失败数）②按企业分节：基本信息 → 季度要点 → 预警列表（等级/类型/事件/日期/出处）→ 未发现项 ③查询范围与失败清单（检索区间行按第 3 步「检索窗口：近N天（YYYY-MM-DD 至 运行日）」写）。稿首标「Grok 预警初判，需投后经理复核」；模拟数据加醒目标注。
8. **员工确认后才写入**：默认不回写。逐条弹确认卡（同 MC3：展示项目名、等级、事件、出处（财务出处用表：recordId｜field｜季度｜value｜算式）；选项「确认写入」/「不写」）。
   - 仅点「确认写入」的条目调 `agent_risk_alerts_create({ projectId, theme, riskType: "舆情|公告|财务", grade: "high|medium|low", conclusion: "<意见结论正文，≤300 字>", rule?: "<命中条款，只回显>", matters, sources: [...], eventDate?: "YYYY-MM-DD", confirmed: true })`。`sources` 同第 5 步格式；外网 `{title,url,date,excerpt}`，财务 `{recordId,field,value,formula}`。
   - **参数传 JSON 对象，每条只调一次**：`arguments` 直接传对象，不要把整个参数序列化成一段字符串（会返回 INVALID_ARGUMENT「参数 arguments 格式不对，应为对象」）；`sources` 传数组、数组每项传对象，`confirmed` 传布尔 `true`，schema 写数字的参数传数字（如 `maxChars: 20000`，不写 `"20000"`）；`sources[].value` 照 `agent_portfolio_quarterly` 返回的原值抄。每条已确认条目只调 1 次 `agent_risk_alerts_create`，一次传对，不靠换格式试；返回成功或 `duplicate: true`，这一条就结束。只有返回内容类 INVALID_ARGUMENT（如等级低于核算档位、正文超 300 字）时，才按 message 改内容后再调。
   - **风险发生日期 = 事件日期（2026-10-28 s3 E6 起）**，不是写入当天：外网出处的 `date` **必填**，写 `YYYY-MM-DD` 发布日期（「近日」、缺日期、2026-02-30 这类返回 INVALID_ARGUMENT 不写库）；财务出处取该 recordId 的报告期末（2026Q3→2026-09-30）。不传 `eventDate` 时：全是外网→取最早发布日；全是财务→取本期报告期末；外网+财务混合→**必须**传 `eventDate`，否则拒。传了 `eventDate` 必须等于某条出处的日期，且不能晚于今天。返回 `riskDate`、`riskDateSource` 说明取自哪条出处；网页「风险发生日期」列显示的就是它。
   - **意见结论 = 固定头 + 正文 + 出处索引（2026-10-28 s3 E7 v2 起，MCP 写入专用；网页手填不限）**：Agent 只传正文 `conclusion`（旧名 `evidence` 也认），只写结论摘要；服务端存成「Grok 预警初判，需投后经理复核」+ 换行 + 正文 + 换行「出处：[1] URL；[2] URL」（财务为「[i] 轻投记录 id 列名=库值」）。**只有正文计数，≤300 字**（Unicode 码点）；固定头和出处索引都不计，URL 原样完整保留，4 条长 URL 也不影响。等级、类型、发生日、命中条款、定级核算不再拼进意见结论（网页有等级/类型/日期列，响应有 `riskDate`、`gradeCheck`、`rule`），需要的话自己精简写进正文。以下返回 INVALID_ARGUMENT、不写库：正文为空；超过 300 字（「正文上限 300 字，本次 N 字」→ 精简后重试，明细留在 sources 和预警报告里）；正文带网址（`http(s)://`、`www.`）；正文带「[1]」这类索引或自带「出处：」段；`sources[].url` 不是 ASCII 无空格的完整链接（中文要百分号编码，不能借 url 塞正文）；财务出处 recordId 不是记录 id。返回 `bodyChars`（正文字数）、`bodyMax`=300、`indexChars`（「出处：…」整行字数）、`opinionChars`（落库总字数）。事件描述 `matters` 照旧 ≤255 字，不要把明细挪进去。
   - 未确认不得传 `confirmed: true`；员工拒绝的条目什么都不调。
   - 返回 `duplicate: true` = 该项目同事件（或同出处 URL）已有 **Agent 写入的**（意见结论以「Grok 预警初判」开头）、**尚未关闭**（状态未设置/告警/跟进，不含解除、忽略）的预警；员工网页手建的同主题、同 URL 预警不算重复（2026-10-28 s3c 起）。告诉员工「已存在（existingAlertId）」，不再重试。
   - 写入后 `risk_state` 默认**留空（NULL）**，与网页员工新建一致（2026-10-28 s3c-3 起；返回里 `state`/`riskStateLabel` 为 null 或不出现，网页不显示状态文字；之前写成 `alarm` 的 Agent 前缀行已回填为 NULL）。员工明确要求时才传 `state`，只能是网页字典 `risk_state` 的值（`relieve` 解除、`ignore` 忽略、`follow_up` 跟进、`alarm` 告警，区分大小写），字典外（含 `open`、`未设置`、`ALARM`）返回 `INVALID_ARGUMENT`、不写库。`agent_risk_alerts_list` 的 `state` 传 `unset` 查未设置的行，旧别名 `open` 视同 `unset`。网页详情页没有「状态」下拉，状态只在库和 MCP 里可见，不要告诉员工去网页看状态。正文 `conclusion` 原样落库（E7 v2 起不再按句去重）。可用 `agent_risk_alerts_list({ projectId })` 读回核对，并告诉员工在轻投网页「投后详情 → 风险监控」可见：「风险等级」列显示 `riskGradeLabel`（重大/警告，与 MCP 返回、`agent_risk_alerts_list` 的 `risk_grade_label` 一致），「意见结论」第一行是「Grok 预警初判，需投后经理复核」，接着是正文，最后一行「出处：[1] …」（E7 v2 起；E7 v1 的行是「Grok 预警初判，需投后经理复核｜重大(高)｜…」，更早是「等级：重大｜初判：高(high)」）。返回里 `agentGrade` 是原 high/medium/low。
   - `riskType` 由服务端映射到网页字典 risk_type：财务→财务风险(1)；公告/法律/合规/政策(policy)/监管→法律合规风险(2)；舆情/突发→突发事项(contingencies)；业务→业务风险(0)；指标→指标预警；重大变动→重大变动；其他→其他风险。状态、等级、类型三个字段只会以字典值落库；表外的值返回 `INVALID_ARGUMENT`、不写库，把 message 转告员工，换成表内的值再确认，不要猜。
   - 等级、状态、类型的可选值用 `agent_dicts({ type: "risk_grade" | "risk_state" | "risk_type" })` 取，与网页下拉同源（sys_dict）同序；不要自己编值。

## 不做

不手抄 PAT；不直连业务库；不与工场抢名；不引导去网页确认待确认（无菜单）；不静默入池；尽调报告不写材料里没有的事实（缺的写「待补」）；预警不写无出处/打不开链接的条目，不把「查询失败」写成「无风险」，未经员工逐条确认不回写；季报逾期不拿 `update_date` 判，已报的季报不算逾期；调工具不把参数对象、数组、数字写成字符串，每条预警只调一次写入；尽调报告全文贴在对话里，不只给文件链接，缺的写「待补」不挪进问题清单。
