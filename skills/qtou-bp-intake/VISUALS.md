# BP 图片与扫描页（主流程第 7 步）

前提：BP 原文件已上传并拿到 `fileId`（主流程第 6 步）。

1. **逐页看图**：`agent_projects_bp_pages({ pendingId, fileId, pages: [n, n+1] })`，每次最多 2 页，从第 1 页看到最后一页。返回的 image 是真实渲染页面，text 只作辅助。**看不到返回的图片**（Codex 只把工具结果的文字交给你）时，每页的 `imageUrl` 是 30 分钟有效的图片地址：`curl -sSL -o <本轮目录>/page-<n>.jpg '<imageUrl>'` 下载后用看图工具打开，不要因此停下或让用户重发 BP。扫描页、Logo、团队照片、表格、资质、联系方式一定要看图，不能只信 OCR 文字。
2. **记每页清单**：页码 → 内容 → 对应字段 / 团队 / 图片目标 → 结果或不提取的原因。图里能读到的文字照样映射到字段（见 [FIELDS.md](FIELDS.md)「图片里的文字也要映射」），没写进第 5 步的字段这时用 `agent_projects_bp_fill` 补（传的 `evidence.document.pages` 要包含写有公司全称的那一页，服务端靠它核对主体，否则整批拒绝）；已有值但内容不全的描述字段，可在该字段条目里加 `"mode": "append_evidence"` 追加有出处的新段落（身份、工商、金额、状态类字段不能追加）。
3. **Logo 来源顺序：天眼查 → 企名片 → 企业官网 → BP 裁图**，穷尽为止。前两步在确认入池时由服务端自动完成；`agent_projects_bp_get` 里 Logo 仍为空或 `isAutoGenerate` 为 `"0"`（占位图）时：
   - 先上企业官网找 Logo（首页页头、关于我们、媒体资料包），拿到图片的完整地址后调 `agent_projects_web_logo({ pendingId, imageUrl, pageUrl, confirmed: false })` 预览，看图确认是本公司 Logo 再 `confirmed: true` 写入。SVG、WebP 要换成 PNG/JPG 地址。
   - 官网找不到，再从 BP 裁。优先选浅色背景、接近正方形的版本（如图标加字号），不要选深色背景上又宽又扁的横版。
4. **裁图**：`agent_projects_bp_assets({ pendingId, fileId, assets, confirmed })`，`assets` 每项：
   - `target`：`project.logo`（项目 Logo）、`team.photo`（团队头像）、`document.image`（产品、资质、客户、图表等其他证据图，需带简短标题 `name`）。
   - `page`、`bbox: [left, top, right, bottom]`（0–1，以页面左上角为原点）、`reason`、`reviewed: true`。
   - `team.photo` 必须带真实的 `memberId`（从 `agent_projects_bp_get` 的团队列表取）和姓名；照片归属按版面上的姓名、职务判断，不做人脸身份猜测。服务端会核对该页有这位成员的姓名：PDF 文字层里有就行；姓名印在图片里（文字层只有职务）时，先看图把该页的姓名、职务照录进 BP 证据的逐页原文（`agent_projects_bp_fill` 的 `document.pages` 里对应页的 `text`），再绑定头像。
   - 客户或第三方 Logo 不能当项目 Logo。图片只能来自服务器上的原 PDF 裁图，不能生成图片冒充。
   - 每次最多 8 张。先 `confirmed: false` 预览自检，无误再 `confirmed: true`（确认入池即授权，不逐项问）。已有真实图片不覆盖，只替换空图或按姓名生成的占位图。
   - **怎么认占位图**：`agent_projects_bp_get` 里成员或项目的 `isAutoGenerate` 为 `"0"`，就是按姓名自动生成的占位图，不是真照片。BP 里有这个人的照片，就要裁图替换。
5. **回读**：`agent_projects_bp_get` 核对 Logo、每位成员的照片、文档图片都已写入；再执行一次同样的写入应当没有新增。
