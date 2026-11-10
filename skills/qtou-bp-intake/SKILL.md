---
name: qtou-bp-intake
description: >-
  轻投 BP 入池：读 BP → 建待确认项目 → 确认卡 → 入池 → 补齐附件、字段、团队、图片和工商档案 → 回读核对 → 一次性汇报。
  用户丢 BP、说入池/入库/建项目/补全项目信息时用。
---
# 轻投：BP 入池

先按 `qtou-connect` 技能连上轻投。业务操作只走 qtou MCP 工具，参数传 JSON 对象（数组传数组、`confirmed` 传布尔），每个写入工具对同一项目一次传对、只调一次。返回 `isError` 时：
- `INVALID_ARGUMENT`：message 说明哪里不对，按它改好参数后重调同一个工具，不要因此停下整个流程。
- `FAILED_PRECONDITION` 且 message 说了下一步（如「请先确认入池」「先上传」「带 companyFallback 重试」「用这个 pendingId 续办」）：照做后接着走流程，这是顺序没走对，不是故障。例如还没确认入池就调了补全工具，就回到第 4 步出确认卡。
- `BACKEND_DB_ERROR`、`INTERNAL_ERROR`、`UPSTREAM_*`、权限错误：把 code、message 和 `ref=…` 如实转告并停下，不换路径绕过。

**已入池项目接着补**（用户说「把某某项目的工商信息 / Logo / 团队补全」「继续某某的入库」）：先 `agent_projects_find({ q: "<项目名或公司名>" })` 找回 `pendingId`，`status=confirmed` 的从第 5 步起做缺的部分；`status=pending`（上次没确认完）的调 `agent_projects_get({ pendingId })` 拿新的 `confirmToken`，从第 4 步确认卡接着走，不要新建；不要让用户去找编号。只在 `poolOnly` 里出现的不是经 Agent 入池的，补全工具用不了，如实告诉用户到网页维护。找到多条时列给用户选。续办时原 BP 还没上传（`bp_get` 里没有附件）而对话里没有文件路径：用 `agent_projects_bp_source` 里的文件名在本机找（`mdfind -name '<文件名>'`，或在下载、桌面、当前目录里找），找到就接着上传、看图；找不到再请用户把 BP 发过来。

**入池成功不是终点。** 用户哪怕只说一句「入库」「入池轻投」，也要按下面 10 步全部做完，第 10 步的完成标准全部满足才算完成，不能挑几步做完就交差。工具返回的 `todo` 列出的都是还没做完的事，逐条处理掉。参考文件到哪一步再读，一次只读一个，不要一次性打印多份文件或整份字段目录（会被截断）。

## 执行清单

1. **读 BP**：逐页提取原文，记下页码；扫描页、图片页先记下，等第 7 步看图。
   - BP 是 PPT / PPTX / DOC / DOCX 时，轻投只收 PDF 附件，由服务端转换，不用本机 Office：`shasum -a 256 <文件>` 算出 sha256，调 `agent_files_convert_url({ fileName, sha256, size })`，按返回的 `uploadUrl` 和请求头 `curl -sS -X PUT -H '<头>: <值>' --data-binary @<文件> '<uploadUrl>'`，响应里的 `pdfUrl` 用 `curl -sSL -o <本轮目录>/<名字>.pdf '<pdfUrl>'` 下载，之后全程把这份 PDF 当 BP 用（读正文、上传附件、看图）。Keynote（.key）先请用户导出 PDF。
2. **提取证据**：读 [FIELDS.md](FIELDS.md)，按字段表、证据格式和「值怎么写」生成 `bpEvidence`，包括 `fields`、**核心团队 `team`（BP 里有几个人就写几个人；团队页常是图片，要看图提取）**、历史融资 `financing`。`team` 为空会被拒，BP 确实没有团队信息才传 `teamAbsentReason` 说明。字典字段只查对应字段的选项。
3. **建待确认**：`agent_projects_create_pending({ projectName, companyName, text, bpEvidence })`，`companyName` 用法定全称。BP 只写了品牌或简称时自己查出全称，不要先问用户：至少搜三次（品牌 + 创始人姓名、官网域名 + 公司、品牌 + 主营产品），看官网页脚 / ICP 备案、天眼查 / 企查查 / 爱企查、招聘站和创投媒体；有两处以上独立来源给出同一全称、且创始人或产品对得上，就用它，并在汇报里写明依据。查完仍有多个候选或一个都没有，才把候选和依据列给用户选。`text` 只写几行简短标签，如「项目名称：…」「公司名称：…」「轮次：…」「行业：…」「来源：BP 文件名」，每行的值几个词即可（来源、轮次、城市限 64 字），详细内容都放进 `bpEvidence`。记下 `pendingId`、`evidenceId`、`confirmToken`。返回 `bpEvidenceDropped` 里列出的条目是引文对不上、被服务端摘掉的，其余已存下：记下这几条，第 5 步照 `reason` 改好后补。**不要因为报错把 `bpEvidence` 整个去掉重提**，那样确认后字段和团队都不会补。
4. **确认入池**：
   - `companyMatch.choiceRequired: true`（已有同名公司）：给用户两个选项「关联已有公司」「取消后改名」，用户选定后调 `agent_projects_company_choose({ pendingId, choice, companyId, confirmed: true })`。
   - **确认卡**：在对话里列出项目名、公司全称、轮次、行业、团队人数和主要缺口，问用户「确认入池吗？」，用户明确回复「确认入池」（或同义的明确同意）后才调 `agent_projects_confirm({ pendingId, confirmToken })`；用户没回复、说再看看或要改，就不调。客户端若再弹「是否允许」或接受 / 拒绝框，让用户照常点；返回 `USER_DECLINED` 视为取消，不重试。
   - `askUser` 里的字段（联系人、推荐人等）列为「可选补充」，不阻塞入池；用户回答后用其原话调 `agent_projects_user_fields`（先 `confirmed: false` 预览，再 `true`）。
   - 返回「天眼查未取得有效公司」：多半是 BP 上写的是旧名或少了字（如「有限公司」实为「有限责任公司」、迁址后换了地名）。先联网查工商现用全称，查到同字号的现名就 `agent_projects_confirm({ pendingId, confirmToken, companyName: "<现名>" })` 重试，用户原来的确认仍有效，汇报里写明 BP 名和现名；确实查不到再按 [ENRICHMENT.md](ENRICHMENT.md)「天眼查查不到时的兜底建档」带 `companyFallback` 重试。都用同一个 pendingId，不新建。
   - 用户确认入池即授权补空值：第 5–8 步直接做，不逐项问用户。

   以下各步都先 `confirmed: false` 预览自检（主体、值、出处、字典），通过再 `confirmed: true` 写入；自检不过的项不写，记入缺口。
5. **补字段和团队**：确认入池时服务端已用存下的证据自动补字段和团队，结果在确认返回的 `bpFill` 里。`bpFill.status` 为 `skipped`、团队人数少于 BP，或第 3 步有被摘掉的条目时，调 `agent_projects_bp_fill({ pendingId, evidence, confirmed })` 补齐（只传要补的条目）。看返回里每项的 `filled / preserved / needs_verification`。
6. **上传 BP 原文件**：转成 PDF（≤20MB，超限去掉内嵌视频或压缩图片），算 SHA256，调 `agent_projects_bp_upload_url({ pendingId, fileName, sha256, sizeBytes })`，按返回的地址 PUT 文件，请求头带返回 `headers` 里的 `X-Qtou-Upload-Sig`；再调 `agent_projects_bp_attach({ pendingId, uploadId, confirmed })`，记下 `fileId`。不能用本地路径代替上传。
7. **图片和扫描页**：读 [VISUALS.md](VISUALS.md)，逐页看图、补图里的文字、裁 Logo / 团队头像 / 证据图。`bp_fill` 和确认返回里的 `todo` 列出还缺的项（团队为空、Logo 占位、哪些成员是占位头像），全部处理完才算这一步完成。
8. **工商和档案字段**：读 [ENRICHMENT.md](ENRICHMENT.md)，联网检索、核实，用 `agent_projects_profile_fill` 补写工商与公司档案空字段（先预览再写入，最后读回）。
   **历史融资**：看 `agent_projects_bp_get` 返回的 `financingTab`（融资页签现有记录，企名片同步的也在这里；`collections.financing` 只是 BP 证据，不是页签）。页签里没有、或缺了公开报道里的轮次时，联网搜「品牌 / 公司全称 + 融资」（36氪、投资界、动脉网、IT桔子、公司官网新闻、正式公告），打开报道取原文，每轮调 `agent_projects_financing_add({ pendingId, rounds: [{ round, date, money, investors, sourceTitle, sourceUrl, quote }] })` 先预览、再 `confirmed: true` 写入。`quote` 是报道里含公司名或品牌、轮次或金额的原句；只到年份、对不上主体的不写。
9. **回读**：`agent_projects_bp_get({ pendingId })` 和 `agent_projects_profile_get({ pendingId })`。
10. **完成标准（全部满足才结束）**：
    - 团队人数 = BP 里的核心成员人数，每人有职务和履历；BP 有照片的成员，头像是从 BP 裁的真照片（`isAutoGenerate` 为 `"0"` 的是姓名占位图，不算）。
    - BP 里有内容的字段都已写入，或列在缺口里并写明原因。
    - BP 附件有 `fileId`。
    - 工商与档案字段已走完第 8 步，剩余空字段都有原因。
    - 融资页签有公开可查的历史融资；查过没有的，写明查了哪些来源。
    - 有一项不满足，就回到对应步骤补做；确实做不了的写进汇报的「未完成」。

## 底线（不满足的值不写）

- 每个值有出处，引文逐字核对，不编数字；BP 没写披露日期照常入池（见 FIELDS.md）。
- 法律主体一致：母公司、子公司、关联公司、同名公司的信息不写到本公司名下。
- 已有值不覆盖（包括 0 和 false）；要替换先问用户。
- 返回 `duplicate` 就说「重复，已经有了」并附已有记录，不重试、不另建。
- 私有 BP 不发给外部模型；联网核实只用公开网页。
- 不静默入池；不引导用户去网页确认（网页没有待确认菜单）；不用 HTTP 直调 confirm / reject。

## 汇报（一次性）

写了哪些字段和团队成员（各自来源页）、附件和图片结果、工商补全结果；仍空着的字段及原因（无可靠来源 / 主体对不上 / 冲突 / 字典不匹配 / 提取失败）；第 10 步没满足的项。
