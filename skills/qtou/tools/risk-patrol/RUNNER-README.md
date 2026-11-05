# 本地巡检执行器

从轻投 MCP（`QTOU_MCP_URL`，默认 74 服务器）读取配置和名单，额外严格过滤is_after_invest=1。只写草稿，正式风险须员工确认。

```bash
cd /Users/hesong/Documents/gihub_space/qtou/repo/tools/risk-patrol
# 插件已搜的结果用于采集，不需要本地Tavily key
python3 runner.py --collect-only --candidates-file /绝对路径/candidates.json --output /绝对路径/evidence.json
# 核实正文、事件日期、S3-C定级以后提交；不重复搜索
python3 runner.py --events /绝对路径/verified-events.json --output /绝对路径/submitted.json
# heartbeat按配置时段认领；失败和仅采集不标完成，可重试
python3 runner.py --due --state /绝对路径/patrol.sqlite --events /绝对路径/verified-events.json --candidates-file /绝对路径/candidates-v2.json
```

候选文件固定格式：
```json
{"schemaVersion":1,"projects":{"项目ID":[{"url":"https://example.com/notice","title":"公告标题","content":"候选正文","publishedDate":"2026-10-29"}]}}
```
每个已搜项目必须有键，无命中用空数组；缺键记该项目失败。候选条目不允许额外verified/grade等字段，不能据此提交草稿。输出候选证据只存本地，CLI只打印统计。

事件文件是数组。每条须有verified=true、rule（对应S3-C规则）、projectId、grade（medium/high）、eventKey（重试不变）、riskType、title、eventDate、conclusion、sources（url/title/date），可带stage。服务端仍校验出处、日期、长度与指纹。非due模式不能组合events与候选文件。due模式必须提供完整schemaVersion=2凭证，或执行真实本地搜索；单独空events不能绕过逐项目覆盖。明确逐候选核实后无符合S3-C的已确认异常才可用空数组，这不表示公司无风险。

租户来自agent_health，时间来自risk_config_get.patrolTimes，按北京时间及SQLite租约认领；失败释放为可重试。只有已核实事件提交全部成功才完成时段；只采集不会冒充完成。重试复用eventKey及出处，由服务端幂等，禁止随机改变事件键。

限制：名单接口上游最多500条且无分页；执行器没有绕过MCP直连数据库。heartbeat须先完整收集名单并核实异常，不可把缺搜索的空数组当正常。天眼查新闻不会调用，运行记录写“新闻源未开通”。

## 持久健康与摘要
`--due --state` 同一SQLite文件还保存逐项目最近成功时间及连续失败自然日。同一天重试失败不重复加天数，中断一天不算连续；成功清零。输出retryProjectIds为前一天仍失败项目（下一轮完整扫描会再次覆盖它们），failureAlerts仅连续≥3天。保留项目健康状态直到成功，不因某轮进程异常把失败认作完成。

`patrol_state.PatrolState.summary_changed(tenant, summary)` 返回changed/digest；只有实际通知成功以后调用acknowledge_summary。summary需仅含业务状态计数和待办id，不要放不断变化的时间戳，否则每轮都变。模块本身不发送外部消息、不自动确认。

应用heartbeat每30分钟执行意味着08:30/16:30后首个心跳运行，不能承诺准点。如需缩小偏差可改每5分钟检查，巡检次数仍由服务端配置决定；认领时段避免重复执行。

过期/提醒：本机8091已部署LocalScopedRiskTask包装，仅当前tenant且严格投后范围运行第3/7天提醒及7天过期，第7天先提醒后过期。原RiskTaskRegistry继续s3auto.tasks.off=true，不能与本地包装同时开启。财务队列/历史恢复使用持久固定s3auto.local.since激活边界，重启不会重新取当前时间。当前tenant每日季报逾期检查与运行记录90天清理也在该包装中；清理先备份确切待删行，备份失败不删。部署、时间边界及恢复证据见qa/codex-20261029/backend/RESULT.md。其他tenant不随本机测试启用。

## 插件完整覆盖凭证（当前版本2）

`--due --events ... --candidates-file ...`接受 `{ "schemaVersion":2, "projects":{项目ID:候选数组}, "receipts":{项目ID:凭证}}`。projects及receipts键必须精确等于当前严格投后名单，新增项目会拒绝。真实搜索凭证包含query、source=tavily_plugin、searchedAt（本slot内带时区ISO）、reviewed=true及conclusion=no_anomaly/events；逐条review另存理由和来源证据，不把摘要冒充正文。

明确QA/模拟/验收/测试项目使用空候选数组，receipt为`{"source":"test_scope","conclusion":"skip_test_project","reason":"说明明确测试身份及无外部主体"}`；不填虚构搜索时间，不称已实搜或无异常。执行器验证当前项目名称测试标识，写status=skipped。真实企业禁止skip。收集失败或范围不全不可完成时段。coverageComplete表示实搜和合法测试skip覆盖工作流，非全面风险保证。

每轮真实企业的采集工作须同时覆盖新闻/舆情与官方公告司法工商检索；后者用Tavily include_domains限定交易所/股转/巨潮/法院/信用中国/公示系统等适用官方域名。两类实际query/time/domains/hits与逐候选主体日期复核另存证据，receipt.query引用两类查询。当前runner只验证凭证覆盖与声明，不能自动证明人工已完成两类检索，因此审核必须检查原始结果；缺任何一类不可宣称完整业务验收。无检索结果不等于官方无记录。

risk_run_record是增量接口：每次调用（包括不带runId的首调）都会累加scanned/hits并追加details。采用首调全部统计0且details=[]，完成时一次提交真实累计；不要将同一累计值在start/finish重复传入。统计更正须保留前值和审计，不得冒充新搜索。

逐家health在run finish之前并入details。consecutiveFailedDays/failDays是失败日数，alerted是独立送达状态，不从日数推定。`PatrolState.alerts(tenant)`返回needs_attention/alerted；只有实际送达后调用`acknowledge_failure_alert(tenant, project, day, delivered_at, delivery_reference)`，按项目/自然日持久去重。未送达UI显示待告警。不得在测试样本/自动检测后假ack，测试ack只在独立临时SQLite中验证。

摘要统一用`summary_payload(raw_summary)`裁剪后再`summary_changed`，稳定排序待办，排除动态时间。当前持久库`/Users/hesong/Documents/gihub_space/qtou/qa/codex-20261029/s2/patrol-real/slot.sqlite`已保存用户可见daily6条QA摘要的真实送达ack；不要每次另建空库导致重复通知。
