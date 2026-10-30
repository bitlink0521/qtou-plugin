# BP图文完整提取（默认流程）

收到BP必须覆盖文字和图片，不能以抽出正文为完成。
1. 调 agent_projects_bp_schema，读取92字段、团队与融资子模块、附件和 visualMedia；列字段映射及缺口。
2. 新项目按原create_pending→用户确认→confirm；已入池项目（用户确认入池或要求补全）补空。实际上传PDF并回读文件SHA；不得用本地路径假装上传。
3. 调 agent_projects_bp_pages({pendingId,fileId,pages:[1,2]})逐页检查全BP。每次最多2页；MCP image内容是真实渲染页面，text仅辅助。扫描页、客户Logo、表格、资质、联系方式必须检查图像，不得仅依赖OCR文本。
4. 建每页review清单：页码、内容、对应字段/子表/图片目标、提取结果或不提取原因。没有对应字段的有用图表/证书/客户证据用document.image保存到项目文档，不塞错字段。
5. 调 agent_projects_bp_assets 传assets数组：{target,page,bbox:[left,top,right,bottom],reviewed:true,reason,memberId?,name?}。坐标0..1按页面左上角。target为project.logo、team.photo或document.image。照片须从姓名/职务及版面核实归属，不做人脸身份猜测；不得把客户Logo作为公司Logo。头像须真实团队memberId和姓名。document.image须简短标题name。
6. 先confirmed=false内部预览自检裁图，无误直接confirmed=true（确认入池即授权，不逐项问）。只替换空图或原姓名生成占位图，真实已上传图片保留。文件来自服务器原PDF裁图，不能生成图片冒充。
7. 图片内文字也映射业务字段：客户/案例→serviceObject/otherSituations，产品/专利→techRemarks，资质→honour，团队学历履历→对应团队子表，规划和预测→带时点历史描述，不写成当前实际值。未核实字段保持缺口，不能只存图片就忽略其中可读信息。
8. agent_projects_bp_fill默认补空；已填的描述字段仍有遗漏时，可显式mode=append_evidence追加有出处的新段落，原文保留并去重。只允许受限描述字段，身份/工商/金额/状态不可追加或覆盖。禁止把已有字段非空当作信息完整。
9. agent_projects_bp_get回读logo、团队photo、字段、附件、media；再次执行验证幂等；实际网页确认图片已加载而非错误占位图。完整提取账本记录：已映射、缺证据、冲突、无适用字段。历史BP不代表当前状态。

MCP新增：agent_projects_bp_pages、agent_projects_bp_assets。stdio代理动态透传tools/list与image内容；客户端缓存旧工具表时重连刷新，不得静默跳过图片。仅本机已部署，服务器需同版本API/网页图片接口及共享存储配置。
