<cursor_untrusted_data_1337 source="CallDynamicTool">

package cn.qtou.api.modules.agent.service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;

import cn.qtou.modules.agentrisk.Actor;
import cn.qtou.modules.agentrisk.DraftInput;
import cn.qtou.modules.agentrisk.RiskException;
import cn.qtou.modules.agentrisk.RiskUtil;
import cn.qtou.modules.agentrisk.service.RiskConfigService;
import cn.qtou.modules.agentrisk.service.RiskDraftService;
import cn.qtou.modules.agentrisk.service.RiskRunService;
import cn.qtou.modules.agentrisk.service.RiskTycNewsService;

/** 场景③ 新增 MCP 工具（全部标注 bot）；channel 记 bot。由 AgentRiskMcpPostProcessor 挂到 agentMcpService.handle。 */
@Service
public class AgentRiskMcpTools {
	public static final List<String> NAMES = Arrays.asList("create_risk_draft", "list_risk_drafts", "dismiss_risk_draft",
			"risk_drafts_summary", "risk_run_record", "risk_tyc_news", "risk_config_get", "risk_config_update");

	@Autowired
	RiskDraftService drafts;
	@Autowired
	RiskRunService runs;
	@Autowired
	RiskConfigService config;
	@Autowired
	RiskTycNewsService tyc;

	/** 这条调用归我们处理吗（新工具，或带 draftId 的 agent_risk_alerts_create）。 */
	public static boolean owns(String name, JSONObject args) {
		return NAMES.contains(name) || ("agent_risk_alerts_create".equals(name) && args != null && args.get("draftId") != null);
	}

	static Map<String, Object> p(String type, String desc) {
		Map<String, Object> m = new LinkedHashMap<String, Object>();
		m.put("type", type);
		m.put("description", desc);
		return m;
	}

	static Map<String, Object> tool(String name, String desc, Object[][] props, String... required) {
		Map<String, Object> props2 = new LinkedHashMap<String, Object>();
		for (Object[] pr : props) {
			Map<String, Object> d = p((String) pr[1], (String) pr[2]);
			if (pr.length > 3) {
				d.put("items", pr[3]);
			}
			props2.put((String) pr[0], d);
		}
		Map<String, Object> schema = new LinkedHashMap<String, Object>();
		schema.put("type", "object");
		schema.put("properties", props2);
		if (required.length > 0) {
			schema.put("required", Arrays.asList(required));
		}
		Map<String, Object> t = new LinkedHashMap<String, Object>();
		t.put("name", name);
		t.put("description", desc);
		t.put("inputSchema", schema);
		return t;
	}

	public static List<Map<String, Object>> defs() {
		Map<String, Object> obj = new LinkedHashMap<String, Object>();
		obj.put("type", "object");
		Map<String, Object> str = new LinkedHashMap<String, Object>();
		str.put("type", "string");
		List<Map<String, Object>> l = new ArrayList<Map<String, Object>>();
		l.add(tool("create_risk_draft", "场景③ 巡检：生成一条待确认风险草稿（不写正式预警表）。低风险返回 skipped；同出处去重；同事件更高等级标「升级」。",
				new Object[][] { { "projectId", "string", "项目 id" }, { "riskType", "string", "风险类型（同 agent_risk_alerts_create）" },
						{ "grade", "string", "high/medium；low 直接 skipped" }, { "title", "string", "标题 ≤100 字" },
						{ "eventDate", "string", "事件日期 yyyy-MM-dd" }, { "conclusion", "string", "正文 ≤300 字，不含网址和等级词" },
						{ "sources", "array", "出处，至少 1 条 {url,title,date} 或季度财务出处", obj },
						{ "source", "string", "bot_search/tianyancha，默认 bot_search" }, { "eventKey", "string", "同一事件的键（升级判断）" },
						{ "stage", "integer", "事件阶段" }, { "runId", "string", "运行记录 id" } },
				"projectId", "riskType", "grade", "title", "eventDate", "conclusion", "sources"));
		l.add(tool("list_risk_drafts", "场景③：列风险草稿（含失败行）。", new Object[][] { { "status", "string", "all/pending/confirmed/dismissed/expired/superseded/failed；all 不含 superseded" },
				{ "projectId", "string", "项目 id" }, { "day", "string", "生成日 yyyy-MM-dd" }, { "page", "integer", "页码" },
				{ "pageSize", "integer", "每页 ≤100" } }));
		l.add(tool("dismiss_risk_draft", "场景③：忽略一条草稿（理由 ≤200 字）。", new Object[][] { { "draftId", "string", "草稿 id" },
				{ "reason", "string", "理由 ≤200 字" } }, "draftId", "reason"));
		l.add(tool("risk_drafts_summary", "场景③：某日草稿汇总（每日汇总用）：todayNew、todayHandled{confirmed,dismissed,expired}、pendingItems(≤50，带 pendingTotal/pendingTruncated)、noRecipientItems；changed 只看当天增量。",
				new Object[][] { { "date", "string", "yyyy-MM-dd，默认今天" }, { "day", "string", "同 date（旧名）" }, { "sinceDay", "string", "旧累计字段的起始日 yyyy-MM-dd" } }));
		l.add(tool("risk_run_record", "场景③：巡检写/续写运行记录。", new Object[][] { { "runType", "string", "patrol/tyc_news" },
				{ "startedAt", "string", "yyyy-MM-dd HH:mm:ss" }, { "endedAt", "string", "yyyy-MM-dd HH:mm:ss" },
				{ "scanned", "integer", "扫描家数" }, { "hits", "integer", "命中条数" }, { "draftsCreated", "integer", "生成草稿数" },
				{ "errors", "integer", "错误数" }, { "details", "array", "[{projectId,query,source,hits,status,error}]", obj },
				{ "runId", "string", "续写时传" } }, "runType"));
		l.add(tool("risk_tyc_news", "场景③（本批不启用）：天眼查新闻源未开通，调用只在运行记录写「新闻源未开通」、命中 0，返回 status=unavailable，不算失败。新闻信号请外网检索后用 create_risk_draft 提交（source=bot_search，每条带出处链接）。",
				new Object[][] { { "projectIds", "array", "项目 id，默认全部投后项目（is_after_invest=1）", str }, { "limit", "integer", "单家条数 ≤20" },
						{ "batch", "integer", "每批家数 ≤20，默认 10" }, { "runId", "string", "运行记录 id" } }));
		l.add(tool("risk_config_get", "场景③：读预警阈值配置。", new Object[][] {}));
		l.add(tool("risk_config_update", "场景③：改预警阈值配置（仅管理员；只传要改的字段，下次触发生效）。",
				new Object[][] { { "changes", "object", "要改的字段，如 {incomeMedium:35}（默认 30/50）" } }, "changes"));
		return l;
	}

	public Object call(Map<String, Object> agent, String name, JSONObject args) {
		String cid = RiskUtil.s(agent.get("customer_id"));
		String uid = RiskUtil.s(agent.get("user_id"));
		if (cid == null) {
			throw new RiskException(RiskException.UNAUTHORIZED, "调用方租户未知");
		}
		Actor a = drafts.actor(cid, uid, config.userName(uid));
		if ("agent_risk_alerts_create".equals(name)) {
			String draftId = args.getString("draftId");
			String ng = args.getString("newGrade");
			String gr = args.getString("gradeReason") != null ? args.getString("gradeReason") : args.getString("reason");
			if (ng != null || gr != null) {
				return drafts.confirmWithGrade(cid, draftId, ng, gr, a, "bot");
			}
			return drafts.confirm(cid, draftId, a, "bot");
		}
		if ("create_risk_draft".equals(name)) {
			DraftInput in = new DraftInput();
			in.customerId = cid;
			in.projectId = args.getString("projectId");
			in.riskTypeIn = args.getString("riskType");
			in.grade = args.getString("grade");
			in.title = args.getString("title");
			in.eventDate = args.getString("eventDate");
			in.conclusion = args.getString("conclusion");
			in.sources = sources(args.get("sources"));
			String src = args.getString("source");
			if (src != null && !"bot_search".equals(src) && !"tianyancha".equals(src)) {
				throw RiskException.bad("source 只能是 bot_search 或 tianyancha");
			}
			in.channel = src == null ? "bot_search" : src;
			in.trigger = "patrol";
			in.eventKey = args.getString("eventKey");
			in.stage = args.getInteger("stage");
			in.runId = args.getString("runId");
			in.createdBy = uid;
			return drafts.createDraft(in);
		}
		if ("list_risk_drafts".equals(name)) {
			Map<String, String> q = new HashMap<String, String>();
			put(q, "status", args.getString("status"));
			put(q, "projectId", args.getString("projectId"));
			put(q, "day", args.getString("day"));
			put(q, "pageNo", args.getString("page"));
			put(q, "pageSize", args.getString("pageSize"));
			Map<String, Object> r = drafts.listDrafts(cid, q, a);
			Map<String, Object> out = new LinkedHashMap<String, Object>();
			out.put("items", r.get("list"));
			out.put("count", r.get("count"));
			return out;
		}
		if ("dismiss_risk_draft".equals(name)) {
			return drafts.dismiss(cid, args.getString("draftId"), args.getString("reason"), a, "bot");
		}
		if ("risk_drafts_summary".equals(name)) {
			String date = args.getString("date") != null ? args.getString("date") : args.getString("day");
			return drafts.summary(cid, date, args.getString("sinceDay"));
		}
		if ("risk_run_record".equals(name)) {
			Map<String, Object> out = new LinkedHashMap<String, Object>();
			out.put("runId", runs.record(cid, uid, args));
			return out;
		}
		if ("risk_tyc_news".equals(name)) {
			List<String> ids = new ArrayList<String>();
			Object raw = args.get("projectIds");
			if (raw != null && !(raw instanceof List)) {
				throw RiskException.bad("projectIds 应为数组");
			}
			if (raw != null) {
				for (Object o : (List<?>) raw) {
					if (o != null) {
						ids.add(String.valueOf(o));
					}
				}
			}
			Integer limit = args.getInteger("limit"), batch = args.getInteger("batch");
			return tyc.fetch(cid, uid, ids, limit == null ? 10 : limit, batch == null ? 10 : batch, args.getString("runId"));
		}
		if ("risk_config_get".equals(name)) {
			return config.view(cid);
		}
		if ("risk_config_update".equals(name)) {
			Object ch = args.get("changes");
			if (!(ch instanceof Map)) {
				throw RiskException.bad("changes 应为对象");
			}
			Map<String, String> m = new LinkedHashMap<String, String>();
			for (Map.Entry<?, ?> e : ((Map<?, ?>) ch).entrySet()) {
				m.put(snake(String.valueOf(e.getKey())), e.getValue() == null ? null : String.valueOf(e.getValue()));
			}
			return config.update(cid, m, a, "bot");
		}
		throw RiskException.bad("未知工具");
	}

	static String snake(String k) {
		return k.replaceAll("([a-z0-9])([A-Z])", "$1_$2").toLowerCase();
	}

	static void put(Map<String, String> m, String k, String v) {
		if (v != null) {
			m.put(k, v);
		}
	}

	static List<Map<String, Object>> sources(Object raw) {
		List<Map<String, Object>> l = new ArrayList<Map<String, Object>>();
		if (raw == null) {
			return l;
		}
		if (!(raw instanceof JSONArray)) {
			throw RiskException.bad("sources 应为数组");
		}
		JSONArray arr = (JSONArray) raw;
		for (int i = 0; i < arr.size(); i++) {
			if (!(arr.get(i) instanceof Map)) {
				throw RiskException.bad("sources 第 " + (i + 1) + " 项应为对象");
			}
			l.add(arr.getJSONObject(i));
		}
		return l;
	}

	/** 结果包装成 MCP tools/call result（与原 handle 同形）。 */
	public static Map<String, Object> ok(Object data) {
		Map<String, Object> contentItem = new LinkedHashMap<String, Object>();
		contentItem.put("type", "text");
		Object camel = RiskUtil.camel(data);
		contentItem.put("text", JSON.toJSONString(camel));
		Map<String, Object> result = new LinkedHashMap<String, Object>();
		result.put("content", Arrays.asList(contentItem));
		result.put("isError", Boolean.FALSE);
		result.put("structuredContent", camel);
		return result;
	}

	public static Map<String, Object> err(String tool, Throwable ex) {
		if (!(ex instanceof RiskException)) {
			return AgentMcpService.toolError(tool, ex);
		}
		RiskException re = (RiskException) ex;
		Map<String, Object> e = new LinkedHashMap<String, Object>();
		e.put("code", re.codeName());
		e.put("message", AgentMcpService.redactForCaller(re.getMessage(), AgentMcpService.CALLER_MSG_MAX));
		e.put("tool", tool);
		if (re.getData() != null) {
			e.put("data", RiskUtil.camel(re.getData()));
		}
		Map<String, Object> body = new LinkedHashMap<String, Object>();
		body.put("error", e);
		Map<String, Object> contentItem = new LinkedHashMap<String, Object>();
		contentItem.put("type", "text");
		contentItem.put("text", JSON.toJSONString(body));
		Map<String, Object> result = new LinkedHashMap<String, Object>();
		result.put("content", Arrays.asList(contentItem));
		result.put("isError", Boolean.TRUE);
		result.put("structuredContent", body);
		return result;
	}
}


</cursor_untrusted_data_1337>