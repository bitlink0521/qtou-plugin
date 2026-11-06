---
name: qtou-bp-intake
description: >-
  轻投 BP 入池：解析 BP → 建待确认项目 → 弹入池确认卡（带 confirmToken）→ 用户确认后入池 → 自动补全附件、素材、工商与档案字段（应写尽写）→ 一次性汇报。
  用户丢 BP、说入池/入库/建项目/补全项目信息时用。
---
# 轻投：BP 入池

使用前先按 `qtou-connect` 技能连接轻投；所有业务操作只走 qtou MCP 工具，不直调 HTTP、不直连库，参数传 JSON 对象，返回 `isError` 时如实转告 code 与 message。

## 默认项目补全入口

收到BP还必须执行[BP图文完整提取](BP-VISUALS.md)：逐页检查页面图像、Logo、团队照片、表格及图片文字，按字段/子表/附件补齐并回读与网页验收；不得只提文字或把姓名生成头像当已提取照片。

用户提供BP时，必须先用agent_projects_bp_schema完整盘点字段及子表，按PROJECT-ENRICHMENT.md的完整BP流程提取、确认、入库和回读；不能只填工商或简介。用户提供项目名称、公司名称或BP并要入池时，默认先执行[项目基本信息补全](PROJECT-ENRICHMENT.md)：联网检索并取网页正文（有Tavily用Tavily，没有就用你自带的搜索并打开网页），由你自己（当前模型）核实并做有出处整理，已有字段不覆盖，确认卡上带补全建议和缺口。入池仍须用户点卡确认，不替代原工商逻辑。用户确认入池后按「入池后自动补全」直接补写（bp_attach → bp_assets → profile_fill），不逐项问，经原文审核后写入并回读核验。具体执行入口和停止条件见PROJECT-ENRICHMENT.md，不能只建公司关联就结束。

## 入池后自动补全（强制，应写尽写，不逐项问）

入池本身不变：仍按下方 AC MC3，`agent_projects_create_pending` 后必须弹卡，用户点「确认入池」才 confirm。用户确认入池（或要求补全某个已入池项目）即视为本项目补空值授权，之后补全写入不再逐项问，按顺序做完：

1. **BP 附件** `agent_projects_bp_attach`：原 BP 转 PDF，≤20MB（超限可去掉内嵌视频、压图）。先调 `agent_projects_bp_upload_url({ pendingId })` 拿 `uploadId` 和一次性上传地址（绑定该 pendingId，约 10 分钟有效，传一次即失效，不需要也不接受 agent_key），把 PDF 原样 PUT 上去，再调 `agent_projects_bp_attach({ pendingId, uploadId, confirmed })`；不要再把整份 PDF 转 base64 塞进参数。回读 fileId / SHA256。
2. **BP 素材** `agent_projects_bp_assets`：logo、团队头像、证据图，按 [BP-VISUALS.md](BP-VISUALS.md)。
3. **档案字段** `agent_projects_bp_fill` / `agent_projects_profile_fill`：BP 字段与子表、工商及公司档案补空。完整 BP 证据已在 create_pending 时存在服务端，`bp_fill` 传 `evidenceId` 取用，不再把整份 evidence 重发一遍。evidenceId 只能复用 create_pending 时存的证据；没有的（旧项目或新证据）要完整传 evidence。

每项先 `confirmed=false` 内部预览自检（主体、值、出处、字典映射），通过就直接 `confirmed=true` 写入并回读；预览不发给用户等批准。自检不过的项不写，记入缺口。

**字典字段想办法填上（行业、细分领域、轮次、币种、沟通方式等）**：材料里的说法和字典选项不完全一致时，不要直接留空——先看 `agent_projects_bp_schema` / `bp_get` 返回的该字段全部选项，选语义最接近的一项写入（如「智能制造」→「生产|加工|制造」或「高科技」），汇报里注明「按最接近归类：原文 X → 选项 Y」。只有所有选项都明显无关时才留空并写原因。币种材料没写时，服务端会按公司注册资本币种补，不用另传。

**描述字段写整理稿，不贴原文**：简介、主营业务、团队、竞品、财务等 value 按 [PROJECT-ENRICHMENT.md](PROJECT-ENRICHMENT.md)「字段value怎么写」整理成通顺、简短的描述（去页码和表格断行，数字照抄），原文只放 `sources.quote`；把整页 BP 当 value 或多个字段写同一段会被服务端拒绝。

主动上网补齐入池所需的全部信息：工商字段、官网、主营业务、简介、荣誉、融资、地址、联系方式等，按 [PROJECT-ENRICHMENT.md](PROJECT-ENRICHMENT.md) 两轮联网检索并取正文（检索工具顺序见该文件）。天眼查查不到时，confirm 带 `companyFallback`（联网检索正文 + 你自己核实，schemaVersion=1，确知模型名再用 `--model` 写上，不知道就不写），不用另配 Grok。

底线（任一不满足，该项不写）：

- 每个值都有出处，引文逐字核对；不编数字。
- 法律主体一致：母公司、子公司、关联公司、同名公司的数据不得写到本公司名下。
- 已有值不覆盖（含 0/false）；要替换须另行问用户。
- 返回 `duplicate` 时直说「重复，已经有了」，附已有记录（id、名称），不重试、不另建。
- 私有 BP 不发给外部模型；核实只依据公开网页资料。

做完一次性汇报：写了哪些字段及各自来源；仍空着的字段及原因（无可靠公开来源 / 主体对不上 / 冲突 / 字典不匹配 / 提取失败）。

## AC MC3：入池确认卡（强制）

规则速查（细节见下文及 PROJECT-ENRICHMENT.md）：
- **Codex 等支持表单的客户端（经插件启动器连接）**：展示摘要后直接调 `agent_projects_confirm`，启动器会弹出确认卡（项目名、公司、待确认编号）让用户点「接受 / 拒绝」；不要再让用户打字回复「确认入池」。返回 `USER_DECLINED` 表示用户没同意，视为取消，不重试。
- **文字确认卡**：客户端不支持卡片组件、也不支持表单时，用文字确认卡代替，用户明确回复「确认入池」才 confirm。
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

## 不做

不静默入池；不引导去网页确认待确认（无菜单）；不用 HTTP 直调 confirm / reject；入池写入每步只调一次，不靠换参数格式试。
