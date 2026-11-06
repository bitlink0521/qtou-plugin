# 写入预警（主流程第 8 步）

只写员工确认的条目，每条只调一次 `agent_risk_alerts_create`，参数直接传 JSON 对象。

## 参数

```json
{
  "projectId": "...", "theme": "事件标题", "riskType": "舆情|公告|财务|业务|指标|重大变动|其他",
  "grade": "high|medium|low", "conclusion": "意见结论正文", "rule": "命中条款（可选）",
  "matters": "事件描述（≤255 字）", "eventDate": "YYYY-MM-DD（可选）",
  "sources": [ ... ], "confirmed": true
}
```

- **外网出处** `{ title, url, date, excerpt }`：`url` 是本轮亲自打开过的完整 ASCII 链接（中文要百分号编码）；`date` 必填，是 `YYYY-MM-DD` 发布日期（「近日」、缺日期、不存在的日期会被拒）；`excerpt` ≤200 字逐字摘录。
- **财务出处** `{ recordId, field, value, formula }`，四项都必填：`recordId` 是 finance 行的 `id`；`field` 只写纯列名（如 `business_income`、`net_assets`、`total_assets`、`net_profit`），不带季度、不带 `=值`；`value` 照 `agent_portfolio_quarterly` 返回的原值抄；`formula` 写本条用到的算式，如 `(32000000−14400000)÷32000000=55%`。季度只写在确认卡的「季度」栏。
- **意见结论 `conclusion`**：只写结论正文，≤300 字；不带网址、不带「[1]」索引或「出处：」段（服务端会自动加固定头「AI 预警初判，需投后经理复核」和出处索引）。等级、类型、日期不用拼进去。
- **风险发生日期**：是事件日期，不是写入日。全是外网出处取最早发布日，全是财务出处取本期报告期末（2026Q3 → 2026-09-30）；外网和财务混合时必须传 `eventDate`，且它必须等于某条出处的日期、不晚于今天。
- `riskType` 由服务端映射到网页字典；`state` 默认不传（网页显示为未设置），员工明确要求时才传 `relieve|ignore|follow_up|alarm`。可选值用 `agent_dicts({ type: "risk_grade" | "risk_state" | "risk_type" })` 查，不自己编。

## 服务端会复核，按返回改

- 带了本项目财务 recordId 的条目（不论 riskType），服务端按库里数据复算档位：`grade` 低于复算档位会被拒（「等级低于财务核算档位…」），按提示改等级再写；成功时返回 `gradeCheck`。只有 1 期数据时返回 `gradeCheck.status=skipped`，照写，报告里写「仅 1 期，未核算档位」。
- `value` 与库里不一致、recordId 不属于本项目、非财务列名配财务 recordId、正文超 300 字、正文带网址等，都会返回 `INVALID_ARGUMENT` 且不写库：按 message 改内容后再调，不要靠换参数格式试。
- 返回 `duplicate: true`：该项目同一事件（或同一出处链接）已有 Agent 写入、尚未关闭的预警。告诉员工「已存在（existingAlertId）」，不重试。

## 写完核对

`agent_risk_alerts_list({ projectId })` 读回。告诉员工在轻投网页「投后详情 → 风险监控」查看：「风险等级」列显示重大 / 警告，「意见结论」第一行是固定头，接着是正文，最后一行是出处。网页没有「状态」下拉，不要让员工去网页看状态。
