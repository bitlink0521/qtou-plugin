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
| URL（开发占位） | `http://127.0.0.1:8081/api/v1/agent/mcp` |
| 传输 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <agent_key>` |
| 连接器名 | `轻投` |
| 插件变量 | `QTOU_CONNECTOR_TOKEN` |

只认 Bearer `agent_key`（由 `POST /v1/agent/auth/login` 签发），不读 cookie。无效/吊销 → 401（或业务码 `10007`）。

签发：弹表单收账密（不收 PAT）→ 代调 `POST /api/v1/agent/auth/login`（与 MCP 同主机）→ 得窄 scope `agentKey` → 写入 `QTOU_CONNECTOR_TOKEN`。审计不写密码明文；key 永不进聊天。兼容别名 `POST /v1/agent/tokens`。

装连接器：优先团队市场 / Marketplace 插件 qtou。Grok Bot 上若 `轻投` 报 Network error，改用 stdio 等价连接器（`轻投stdio` / `轻投本地`）。禁止手填 URL、禁止手抄 PAT。

旧 `qtou-mcp:8787` 不是成品。

## 接入（强制）

1. 已连且冒烟通则结束。
2. 未装或 401：弹表单收轻投账密。
3. 代签 → 写入变量 → 冒烟只读工具。

## 工具最小集（13 个）

`agent_health` · `agent_bp_parse` · `agent_projects_create_pending` · `agent_projects_get` · `agent_projects_confirm` · `agent_projects_reject` · `agent_documents_search` · `agent_documents_content` · `agent_portfolio_list` · `agent_portfolio_quarterly` · `agent_risk_alerts_list` · `agent_risk_alerts_create` · `agent_dicts`

入池补全另用：`agent_projects_bp_schema` · `agent_projects_bp_get` · `agent_projects_bp_fill` · `agent_projects_bp_attach` · `agent_projects_bp_pages` · `agent_projects_bp_assets` · `agent_projects_bp_source` · `agent_projects_profile_get` · `agent_projects_profile_fill`（见 PROJECT-ENRICHMENT.md、BP-VISUALS.md）。

若连接器工具列表里没有 `agent_documents_content`，是客户端缓存了旧列表：先重连 / 重启该 MCP 再查；仍没有则报「服务端未部署 content」，不得改用别的路径读文件。
`agent_portfolio_quarterly` / `agent_risk_alerts_create` 缺失同理：重连后仍缺报「服务端未部署场景③工具」，不得改用 HTTP 或直连库。

写操作一律待确认，禁止静默入池。例外：用户已点「确认入池」的项目，其补空值类写入（bp_attach / bp_assets / bp_fill / profile_fill）按下节自动执行，不再逐项确认。

**返回形状与错误（2026-10-28 起，HTTP 与 stdio 一致）**：检索/列表类工具（`agent_documents_search` / `agent_portfolio_list` / `agent_risk_alerts_list` / `agent_dicts`）一律返回 `{ items: [...] }`，从 `items` 取。工具失败返回 `isError=true`，正文是 `{"error":{"code","message","tool"}}`。code 包括 `INVALID_ARGUMENT`、`NOT_FOUND`、`FAILED_PRECONDITION`、`BACKEND_DB_ERROR`、`INTERNAL_ERROR`，桥侧还有 `UPSTREAM_UNAVAILABLE` / `UPSTREAM_HTTP_*` / `UPSTREAM_RPC_*`。拿到这类返回时，把 code 和 message 如实告诉用户，不得重试成别的路径（HTTP、直连库、读本地文件），也不得写成「没找到」。message 已是给人看的中文说明，不含服务器路径和 Java 异常；带 `ref=…` 的表示详情只在服务端日志，转告用户时把 ref 一并给出，方便管理员查日志。（2026-10-28 s2c 起）`UPSTREAM_HTTP_*` / `UPSTREAM_BAD_RESPONSE` 等桥侧错误的 message 也带 `ref=…`，与桥 stderr 同一个；`NOT_FOUND` 只说什么不存在（如「项目不存在或不属于当前租户」「文件不存在」），不再回显传入的 id，需要时自己对照刚传的参数告诉用户。stdio 上 `arguments` 不是对象时返回 isError `INVALID_ARGUMENT`「参数 arguments 格式不对，应为对象」（与 HTTP 相同）；发出的行不是合法 JSON 会立刻收到 JSON-RPC `-32700`（id=null），不是 JSON-RPC 对象或 params 不是对象收到 `-32600`，桥不会断，修正后重发即可。（2026-10-28 s2d 起）桥 stderr 只记脱敏、截断后的摘要：令牌、Bearer、token/password/secret/cookie/agent_key 等字段值一律显示为 `***`，单行坏请求不超过 300 字符，上游原文不超过 800 字符。排障时用 ref 对照，不要指望在 stderr 里看到原始请求。

## 入池后自动补全（强制，应写尽写，不逐项问）

入池本身不变：仍按下方 AC MC3，`agent_projects_create_pending` 后必须弹卡，用户点「确认入池」才 confirm。用户确认入池（或要求补全某个已入池项目）即视为本项目补空值授权，之后补全写入不再逐项问，按顺序做完：

1. **BP 附件** `agent_projects_bp_attach`：原 BP 转 PDF，≤20MB（超限可去掉内嵌视频、压图），回读 fileId / SHA256。
2. **BP 素材** `agent_projects_bp_assets`：logo、团队头像、证据图，按 [BP-VISUALS.md](BP-VISUALS.md)。
3. **档案字段** `agent_projects_bp_fill` / `agent_projects_profile_fill`：BP 字段与子表、工商及公司档案补空。

每项先 `confirmed=false` 内部预览自检（主体、值、出处、字典映射），通过就直接 `confirmed=true` 写入并回读；预览不发给用户等批准。自检不过的项不写，记入缺口。

主动上网补齐入池所需的全部信息：工商字段、官网、主营业务、简介、荣誉、融资、地址、联系方式等，按 [PROJECT-ENRICHMENT.md](PROJECT-ENRICHMENT.md) 两轮 Tavily 检索并提取正文。天眼查查不到时，confirm 带 `companyFallback`（Tavily + Grok，schemaVersion=1）。

底线（任一不满足，该项不写）：

- 每个值都有出处，引文逐字核对；不编数字。
- 法律主体一致：母公司、子公司、关联公司、同名公司的数据不得写到本公司名下。
- 已有值不覆盖（含 0/false）；要替换须另行问用户。
- 返回 `duplicate` 时直说「重复，已经有了」，附已有记录（id、名称），不重试、不另建。
- 私有 BP 不发给外部模型；交 Grok 的只有公开网页资料。

做完一次性汇报：写了哪些字段及各自来源；仍空着的字段及原因（无可靠公开来源 / 主体对不上 / 冲突 / 字典不匹配 / 提取失败）。

## AC MC3：入池确认卡（强制）

轻投网页没有 Agent「待确认」菜单。入池不得引导「去网页确认」。

流程：

1. `agent_bp_parse`（可选）→ 展示草稿字段。
2. `agent_projects_create_pending` → 得到 `pendingId`（此时仍非正式池）。可直接传 `companyName`（法定全称）。
3. 必须弹聊天确认卡（widget），选项至少：
   - 「确认入池」→ 再调 `agent_projects_confirm({ pendingId })`（MCP 有该工具时）；stdio 暂缺时可用已鉴权 HTTP `POST /api/v1/agent/projects/{pendingId}/confirm`，且仅在用户点确认后。
   - 「取消/驳回」→ 调 `agent_projects_reject`（或 HTTP reject），或什么都不调；不得 confirm。
4. 禁止：未弹卡就 confirm；禁止用户未点同意就入池。

确认卡文案：展示项目名、`pendingId`、置信度/轮次行业缺口；问「确认把该项目入正式池？」

## Demo：BP 入池

- 用户丢 BP /「入库」
- Bot：parse → create_pending → 弹确认卡 → 用户确认后 confirm → 自动补全（附件、素材、档案）→ 一次性汇报；取消则 reject/不调。

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
   - 工作底稿另存来源记录（事实/数字 → 文档名、fileId、原文逐字摘录、自算数的算式），供自检和备查，不放进交给用户的报告正文。
5. **交付前自检（强制）**：按 DD-REPORT-WRITING.md 第 12 节；对照工作底稿逐条核对每个数字能在材料原文找到或由其算出，任何一条不过就改到过为止，不交半成品。交付消息（不写进报告）里说明：参照了哪份范本（文档名 + fileId / 用户模板 / 插件兜底规范）；这是初稿、待投资经理复核；未读文档及原因；「待补」清单；材料为模拟或测试数据时一并说明。

## 场景③：投后风险预警（强制步骤）

触发：用户要「投后巡检 / 风险预警 / 看看投后项目有没有风险」。默认只读；回写必须逐条确认。

1. **取名单**：`agent_portfolio_list({ afterInvestOnly: true })`（可加 `q` 过滤）。记下每家的 projectId、项目名、公司全称、法人、成立日期、行业、投资日期，后面外网查询用全称消歧。同名项目（项目名相同、公司全称/法人不同）分开处理，不得合并。
2. **取季度数据算财务异常**：每家调 `agent_portfolio_quarterly({ projectId })`（可带 `from`/`to`，格式 YYYYQn）。
   - `finance` 每季两行：`type=current` 是本期，`type=samePeriod` 是去年同期，`reportCycleOf` 是所属季度。同比 = current ÷ samePeriod − 1。
   - 只认读回的数，自己算的数写明算式。财务类须 ≥2 季数据（`financeQuarterCount`），不足标「数据不足」，不定级；外网两类照查。
   - 返回「项目不存在或不属于当前租户」= 拒绝，如实报，不换路径。
3. **外网查舆情与公告**：每家都查，用公司全称 + 法人/成立日期消歧。
   - 舆情（近 90 天）：财经/主流媒体；同一事件 ≥2 家独立媒体才算确认。
   - 公告（近 12 个月）：巨潮资讯/交易所/全国股转；国家企业信用信息公示系统；中国执行信息公开网、裁判文书网。
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
   - 财务类写入时，出处要带同一字段两期的轻投记录 id（本期 + 基期）：服务端按 recordId 回读数据库复算档位，`grade` 低于复算档位会返回 INVALID_ARGUMENT「等级低于财务核算档位…不得因无档位降级，本次未写库」，按提示改等级重试；写入成功时响应 `gradeCheck` 带定级核算（如 C1 净资产 … 降 xx.xx%，落 30%–50% 档→中(medium)）；E7 v2 起不再自动写进意见结论，员工要看就自己精简写进正文 `conclusion`。
   - （2026-10-28 s3 R3 起）财务出处只覆盖 1 期（每个字段只有 1 个报告期）时照样可写：服务端仍按 recordId 核对属于本项目、原值与库一致（不一致 INVALID_ARGUMENT 不写库），但算不了环比，返回 `gradeCheck:{status:"skipped",reason:"仅 1 期，无法算环比"}`，（E7 v2 起不写进意见结论）。报告与确认卡照实写「仅 1 期，未核算档位」。≥2 期照旧复算。
   - 同一事件多源只算 1 条，出处并列。
   - （2026-10-28 s3c5 起）只要 sources 里带本项目财务 recordId（净资产/总资产/净利润），**不论 riskType**（财务/指标/业务/其他）服务端都复算档位；等级低于档位返回 INVALID_ARGUMENT，不写库。
   - 财务出处 `{recordId, field, value, formula}`：field 用 func_project_quarterly_finance 列名（net_assets、total_assets、net_profit…；中文名也认，会统一成列名）。value 照 `agent_portfolio_quarterly` 返回的原值抄；服务端按 recordId+field 读库核对，容格式差（1e8 = 100000000.00 = 100,000,000，差 ≤0.005 算一致），不一致返回 INVALID_ARGUMENT「出处原值与轻投记录不符…」，不写库。**value、formula 都必填**，缺任一返回 INVALID_ARGUMENT，不写库，服务端不回填。出处索引里显示的是库值写法（「[i] 轻投记录 id 列名=库值」）。
   - recordId 不属于本项目，或用非财务字段名配财务 recordId，都会被拒。
   - **落库映射（Song He 2026-10-28 定，不加字典）**：入参 `grade` 仍只传 high|medium|low；服务端映射到网页字典 `risk_grade`：high→`significant_risk`「重大」；medium、low→`controllable_risk`「警告」；`no_risk`「正常」永不写入。报告与确认卡写「初判 高/中/低 → 网页显示 重大/警告」，两边说法一致，不得自造其他等级名。
5. **出处（硬门）**：每条预警都要能核对。
   - 外网：来源标题 + **可打开的 URL**（本轮亲自打开过）+ 发布日期 + ≤200 字**原文摘录**（逐字）。
   - 财务：轻投记录 id（finance 行 `id`）+ 字段原值 + 计算式，如 `(14400000 / 32000000 − 1) × 100% = −55%（2026Q3 vs 2025Q3）`。
   - 一条假链接或摘录对不上 = 整包作废。禁止编造事件、链接、数字。
6. **查询失败标「查询失败」**：某源超时/报错/打不开，就在该源写「查询失败」及原因，**不得**写成「未发现」或「无风险」；其余源照常。全部没信号就明说「未发现风险信号」并附查询范围，不硬凑。
7. **出报告**：①总览（企业数、高/中/低条数、查询失败数）②按企业分节：基本信息 → 季度要点 → 预警列表（等级/类型/事件/日期/出处）→ 未发现项 ③查询范围与失败清单。稿首标「Grok 预警初判，需投后经理复核」；模拟数据加醒目标注。
8. **员工确认后才写入**：默认不回写。逐条弹确认卡（同 MC3：展示项目名、等级、事件、出处；选项「确认写入」/「不写」）。
   - 仅点「确认写入」的条目调 `agent_risk_alerts_create({ projectId, theme, riskType: "舆情|公告|财务", grade: "high|medium|low", conclusion: "<意见结论正文，≤300 字>", rule?: "<命中条款，只回显>", matters, sources: [...], eventDate?: "YYYY-MM-DD", confirmed: true })`。`sources` 同第 5 步格式；外网 `{title,url,date,excerpt}`，财务 `{recordId,field,value,formula}`。
   - **风险发生日期 = 事件日期（2026-10-28 s3 E6 起）**，不是写入当天：外网出处的 `date` **必填**，写 `YYYY-MM-DD` 发布日期（「近日」、缺日期、2026-02-30 这类返回 INVALID_ARGUMENT 不写库）；财务出处取该 recordId 的报告期末（2026Q3→2026-09-30）。不传 `eventDate` 时：全是外网→取最早发布日；全是财务→取本期报告期末；外网+财务混合→**必须**传 `eventDate`，否则拒。传了 `eventDate` 必须等于某条出处的日期，且不能晚于今天。返回 `riskDate`、`riskDateSource` 说明取自哪条出处；网页「风险发生日期」列显示的就是它。
   - **意见结论 = 固定头 + 正文 + 出处索引（2026-10-28 s3 E7 v2 起，MCP 写入专用；网页手填不限）**：Agent 只传正文 `conclusion`（旧名 `evidence` 也认），只写结论摘要；服务端存成「Grok 预警初判，需投后经理复核」+ 换行 + 正文 + 换行「出处：[1] URL；[2] URL」（财务为「[i] 轻投记录 id 列名=库值」）。**只有正文计数，≤300 字**（Unicode 码点）；固定头和出处索引都不计，URL 原样完整保留，4 条长 URL 也不影响。等级、类型、发生日、命中条款、定级核算不再拼进意见结论（网页有等级/类型/日期列，响应有 `riskDate`、`gradeCheck`、`rule`），需要的话自己精简写进正文。以下返回 INVALID_ARGUMENT、不写库：正文为空；超过 300 字（「正文上限 300 字，本次 N 字」→ 精简后重试，明细留在 sources 和预警报告里）；正文带网址（`http(s)://`、`www.`）；正文带「[1]」这类索引或自带「出处：」段；`sources[].url` 不是 ASCII 无空格的完整链接（中文要百分号编码，不能借 url 塞正文）；财务出处 recordId 不是记录 id。返回 `bodyChars`（正文字数）、`bodyMax`=300、`indexChars`（「出处：…」整行字数）、`opinionChars`（落库总字数）。事件描述 `matters` 照旧 ≤255 字，不要把明细挪进去。
   - 未确认不得传 `confirmed: true`；员工拒绝的条目什么都不调。
   - 返回 `duplicate: true` = 该项目同事件（或同出处 URL）已有 **Agent 写入的**（意见结论以「Grok 预警初判」开头）、**尚未关闭**（状态未设置/告警/跟进，不含解除、忽略）的预警；员工网页手建的同主题、同 URL 预警不算重复（2026-10-28 s3c 起）。告诉员工「已存在（existingAlertId）」，不再重试。
   - 写入后 `risk_state` 默认**留空（NULL）**，与网页员工新建一致（2026-10-28 s3c-3 起；返回里 `state`/`riskStateLabel` 为 null 或不出现，网页不显示状态文字；之前写成 `alarm` 的 Agent 前缀行已回填为 NULL）。员工明确要求时才传 `state`，只能是网页字典 `risk_state` 的值（`relieve` 解除、`ignore` 忽略、`follow_up` 跟进、`alarm` 告警，区分大小写），字典外（含 `open`、`未设置`、`ALARM`）返回 `INVALID_ARGUMENT`、不写库。`agent_risk_alerts_list` 的 `state` 传 `unset` 查未设置的行，旧别名 `open` 视同 `unset`。网页详情页没有「状态」下拉，状态只在库和 MCP 里可见，不要告诉员工去网页看状态。正文 `conclusion` 原样落库（E7 v2 起不再按句去重）。可用 `agent_risk_alerts_list({ projectId })` 读回核对，并告诉员工在轻投网页「投后详情 → 风险监控」可见：「风险等级」列显示 `riskGradeLabel`（重大/警告，与 MCP 返回、`agent_risk_alerts_list` 的 `risk_grade_label` 一致），「意见结论」第一行是「Grok 预警初判，需投后经理复核」，接着是正文，最后一行「出处：[1] …」（E7 v2 起；E7 v1 的行是「Grok 预警初判，需投后经理复核｜重大(高)｜…」，更早是「等级：重大｜初判：高(high)」）。返回里 `agentGrade` 是原 high/medium/low。
   - `riskType` 由服务端映射到网页字典 risk_type：财务→财务风险(1)；公告/法律/合规/政策(policy)/监管→法律合规风险(2)；舆情/突发→突发事项(contingencies)；业务→业务风险(0)；指标→指标预警；重大变动→重大变动；其他→其他风险。状态、等级、类型三个字段只会以字典值落库；表外的值返回 `INVALID_ARGUMENT`、不写库，把 message 转告员工，换成表内的值再确认，不要猜。
   - 等级、状态、类型的可选值用 `agent_dicts({ type: "risk_grade" | "risk_state" | "risk_type" })` 取，与网页下拉同源（sys_dict）同序；不要自己编值。

## 不做

不手抄 PAT；不直连业务库；不与工场抢名；不引导去网页确认待确认（无菜单）；不静默入池；尽调报告不写材料里没有的事实（缺的写「待补」）；预警不写无出处/打不开链接的条目，不把「查询失败」写成「无风险」，未经员工逐条确认不回写。
