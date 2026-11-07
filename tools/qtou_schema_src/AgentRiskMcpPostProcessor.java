<cursor_untrusted_data_1337 source="CallDynamicTool">

package cn.qtou.api.modules.agent.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.aopalliance.intercept.MethodInterceptor;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.NameMatchMethodPointcutAdvisor;
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.stereotype.Component;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;

/**
 * 给 agentMcpService.handle 外面加一层（原类不改）：tools/list 追加场景③ 新工具；
 * tools/call 新工具、或带 draftId 的 agent_risk_alerts_create 由 AgentRiskMcpTools 处理；其余原样放行。
 */
@Component
public class AgentRiskMcpPostProcessor implements BeanPostProcessor, BeanFactoryAware {
	static final String BEAN = "agentMcpService";
	private BeanFactory bf;

	public void setBeanFactory(BeanFactory beanFactory) {
		this.bf = beanFactory;
	}

	public Object postProcessBeforeInitialization(Object bean, String name) throws BeansException {
		return bean;
	}

	public Object postProcessAfterInitialization(Object bean, String name) throws BeansException {
		if (!BEAN.equals(name)) {
			return bean;
		}
		NameMatchMethodPointcutAdvisor adv = new NameMatchMethodPointcutAdvisor(new Hook(this));
		adv.setMappedName("handle");
		if (bean instanceof Advised && !((Advised) bean).isFrozen()) {
			((Advised) bean).addAdvisor(0, adv);
			return bean;
		}
		ProxyFactory pf = new ProxyFactory(bean);
		pf.setProxyTargetClass(true);
		pf.addAdvisor(adv);
		return pf.getProxy();
	}

	AgentRiskMcpTools tools() {
		return bf.getBean(AgentRiskMcpTools.class);
	}

	@SuppressWarnings("unchecked")
	Object around(Map<String, Object> agent, String body, MethodInvocation mi) throws Throwable {
		JSONObject req;
		try {
			req = JSON.parseObject(body);
		} catch (RuntimeException e) {
			return mi.proceed();
		}
		if (req == null) {
			return mi.proceed();
		}
		String method = req.getString("method");
		if ("tools/list".equals(method)) {
			Object r = mi.proceed();
			if (r instanceof Map && ((Map<String, Object>) r).get("result") instanceof Map) {
				Map<String, Object> res = (Map<String, Object>) ((Map<String, Object>) r).get("result");
				List<Object> all = new ArrayList<Object>();
				if (res.get("tools") instanceof List) {
					all.addAll((List<Object>) res.get("tools"));
				}
				addStrictParam(all);
				patchCreateFieldDesc(all); // r16：只补 agent_risk_alerts_create 的 sources/field 说明
				all.addAll(AgentRiskMcpTools.defs());
				res.put("tools", all);
			}
			return r;
		}
		if (!"tools/call".equals(method)) {
			return mi.proceed();
		}
		Object pr = req.get("params");
		if (!(pr instanceof JSONObject)) {
			return mi.proceed();
		}
		JSONObject params = (JSONObject) pr;
		String name = params.getString("name");
		Object rawArgs = params.get("arguments");
		JSONObject args = rawArgs instanceof JSONObject ? (JSONObject) rawArgs : null;
		if (PORTFOLIO.equals(name) && args != null && args.containsKey(STRICT)) {
			return strictPortfolio(req, params, args, mi);
		}
		if (!AgentRiskMcpTools.owns(name, args == null ? new JSONObject() : args)) {
			if (CREATE.equals(name)) {
				return appendFieldHint(mi.proceed()); // r16/r17：只在「不是轻投财务字段」或「首尾含空格」报错末尾追加格式提示，其余不动；处理出错原样返回
			}
			return mi.proceed();
		}
		Map<String, Object> rpc = new LinkedHashMap<String, Object>();
		rpc.put("jsonrpc", "2.0");
		rpc.put("id", req.get("id"));
		try {
			if (rawArgs != null && args == null) {
				throw new IllegalArgumentException("参数 arguments 格式不对，应为对象");
			}
			rpc.put("result", AgentRiskMcpTools.ok(tools().call(agent, name, args == null ? new JSONObject() : args)));
		} catch (Exception e) {
			rpc.put("result", AgentRiskMcpTools.err(name, e));
		}
		return rpc;
	}

	static final String PORTFOLIO = "agent_portfolio_list";
	static final String STRICT = "strictAfterInvest";

	/** tools/list：给原 agent_portfolio_list 的入参说明补上 strictAfterInvest（可选，默认 false）。 */
	@SuppressWarnings("unchecked")
	static void addStrictParam(List<Object> all) {
		for (Object t : all) {
			if (!(t instanceof Map) || !PORTFOLIO.equals(((Map<String, Object>) t).get("name"))) {
				continue;
			}
			Object sc = ((Map<String, Object>) t).get("inputSchema");
			if (sc instanceof Map && ((Map<String, Object>) sc).get("properties") instanceof Map) {
				Map<String, Object> d = new LinkedHashMap<String, Object>();
				d.put("type", "boolean");
				d.put("description", "可选，默认 false。true 时只留 is_after_invest=1 且未删的项目（场景③巡检用）");
				((Map<String, Object>) ((Map<String, Object>) sc).get("properties")).put(STRICT, d);
			}
		}
	}

	/**
	 * v3 strictAfterInvest：原工具不认这个参数（未知参数会报错），先摘掉再放行；true 时强制 afterInvestOnly=true，
	 * 出来后再外层过滤 is_after_invest='1'（原 SQL 已排除删除行）。false/缺省与原工具完全一致。
	 */
	@SuppressWarnings("unchecked")
	Object strictPortfolio(JSONObject req, JSONObject params, JSONObject args, MethodInvocation mi) throws Throwable {
		Object sv = args.remove(STRICT);
		boolean strict = Boolean.TRUE.equals(sv) || "true".equals(String.valueOf(sv));
		if (sv != null && !(sv instanceof Boolean) && !"true".equals(String.valueOf(sv)) && !"false".equals(String.valueOf(sv))) {
			Map<String, Object> rpc = new LinkedHashMap<String, Object>();
			rpc.put("jsonrpc", "2.0");
			rpc.put("id", req.get("id"));
			rpc.put("result", AgentMcpService.toolError(PORTFOLIO, new IllegalArgumentException("参数 strictAfterInvest 应为布尔值")));
			return rpc;
		}
		if (strict) {
			args.put("afterInvestOnly", Boolean.TRUE);
		}
		params.put("arguments", args);
		mi.getArguments()[1] = req.toJSONString();
		Object r = mi.proceed();
		if (!strict || !(r instanceof Map) || !(((Map<String, Object>) r).get("result") instanceof Map)) {
			return r;
		}
		Map<String, Object> res = (Map<String, Object>) ((Map<String, Object>) r).get("result");
		Object sc = res.get("structuredContent");
		if (Boolean.TRUE.equals(res.get("isError")) || !(sc instanceof Map) || !(((Map<String, Object>) sc).get("items") instanceof List)) {
			return r;
		}
		List<Object> kept = new ArrayList<Object>();
		int dropped = 0;
		for (Object it : (List<Object>) ((Map<String, Object>) sc).get("items")) {
			Object v = it instanceof Map ? ((Map<String, Object>) it).get("is_after_invest") : null;
			if (v != null && "1".equals(String.valueOf(v).trim())) {
				kept.add(it);
			} else {
				dropped++;
			}
		}
		Map<String, Object> data = new LinkedHashMap<String, Object>((Map<String, Object>) sc);
		data.put("items", kept);
		data.put("strictAfterInvest", Boolean.TRUE);
		data.put("droppedNotAfterInvest", dropped);
		Map<String, Object> contentItem = new LinkedHashMap<String, Object>();
		contentItem.put("type", "text");
		contentItem.put("text", JSON.toJSONString(data));
		res.put("content", java.util.Arrays.asList(contentItem));
		res.put("structuredContent", data);
		return r;
	}

	// ==== r16（技术负责人 16:35 裁 02/03 选 B）：只新增代码；不改 AgentMcpService / AgentPortfolioService；校验不放宽；REST 不经过这里 ====
	static final String CREATE = "agent_risk_alerts_create";
	static final String FIELD_DESC = "财务：纯列名（func_project_quarterly_finance 列名或其中文别名），如 business_income、net_assets、total_assets、net_profit、营业收入。"
			+ "只写列名本身：不带季度、不带空格、不带「=值」。正例：business_income。反例：「2026Q3 business_income」「business_income=123」——这两种都会返回 INVALID_ARGUMENT 不写库。"
			+ "季度看 recordId 对应的报告期，不用写进 field；value、formula 另填。";
	static final String SOURCES_DESC_ADD = "财务出处每条都须有 recordId、field（纯列名）、value、formula 四项，缺一项返回 INVALID_ARGUMENT 不写库。";
	static final String FIELD_ERR_MARK = "不是轻投财务字段";
	static final String FIELD_HINT = "（field 只收纯列名，如 business_income；不带季度、空格或「=值」，季度由 recordId 的报告期决定）";
	static final String TRIM_ERR_MARK = "首尾含空格"; // r17（技术负责人 17:29）：服务端首尾空格报错也追加 FIELD_HINT

	/** tools/list：agent_risk_alerts_create 的 sources[].field 说明换成纯列名说明（含正反例），sources 说明末尾追加四项必填一句。
	 *  sources、items、items.properties、field 四层先拷贝再改；改好的 sources 拷贝用 put 写回原 inputSchema.properties（只有 properties 这一层 Map 被就地改，原 sources 及其下层对象不动）；重复调用幂等。 */
	@SuppressWarnings("unchecked")
	static void patchCreateFieldDesc(List<Object> all) {
		for (Object t : all) {
			if (!(t instanceof Map) || !CREATE.equals(((Map<String, Object>) t).get("name"))) {
				continue;
			}
			Object sc = ((Map<String, Object>) t).get("inputSchema");
			if (!(sc instanceof Map) || !(((Map<String, Object>) sc).get("properties") instanceof Map)) {
				continue;
			}
			Map<String, Object> props = (Map<String, Object>) ((Map<String, Object>) sc).get("properties");
			if (!(props.get("sources") instanceof Map)) {
				continue;
			}
			Map<String, Object> src = new LinkedHashMap<String, Object>((Map<String, Object>) props.get("sources"));
			Object d0 = src.get("description");
			String d = d0 == null ? "" : String.valueOf(d0);
			if (!d.endsWith(SOURCES_DESC_ADD)) {
				src.put("description", d.isEmpty() ? SOURCES_DESC_ADD : d + "；" + SOURCES_DESC_ADD);
			}
			if (src.get("items") instanceof Map && ((Map<String, Object>) src.get("items")).get("properties") instanceof Map) {
				Map<String, Object> item = new LinkedHashMap<String, Object>((Map<String, Object>) src.get("items"));
				Map<String, Object> ip = new LinkedHashMap<String, Object>((Map<String, Object>) item.get("properties"));
				Map<String, Object> f = ip.get("field") instanceof Map ? new LinkedHashMap<String, Object>((Map<String, Object>) ip.get("field"))
						: new LinkedHashMap<String, Object>();
				if (!f.containsKey("type")) {
					f.put("type", "string");
				}
				f.put("description", FIELD_DESC);
				ip.put("field", f);
				item.put("properties", ip);
				src.put("items", item);
			}
			props.put("sources", src);
		}
	}

	/** tools/call agent_risk_alerts_create（非 draftId 路径）：仅当 isError 且 error.code=INVALID_ARGUMENT 且 message 含「不是轻投财务字段」
	 *  或「首尾含空格」（r17）、且尚未带 FIELD_HINT 时，在 message 末尾追加 FIELD_HINT（原文不删）：structuredContent 换成追加后的新 Map，
	 *  content 里文本与原 structuredContent JSON 相同的 text 项换成新文本——这两项是在原 result Map 上就地 put，返回的仍是同一个外层对象。
	 *  其余结果原样返回（同一对象）。r17：处理中出现任何 RuntimeException（如 result 是不可改 Map）→ 尽力还原已 put 的 content 后原样返回 r，不抛出。 */
	static Object appendFieldHint(Object r) {
		try {
			return appendFieldHint0(r);
		} catch (RuntimeException e) {
			return r;
		}
	}

	@SuppressWarnings("unchecked")
	static Object appendFieldHint0(Object r) {
		if (!(r instanceof Map) || !(((Map<String, Object>) r).get("result") instanceof Map)) {
			return r;
		}
		Map<String, Object> res = (Map<String, Object>) ((Map<String, Object>) r).get("result");
		if (!Boolean.TRUE.equals(res.get("isError")) || !(res.get("structuredContent") instanceof Map)) {
			return r;
		}
		Map<String, Object> body = (Map<String, Object>) res.get("structuredContent");
		if (!(body.get("error") instanceof Map)) {
			return r;
		}
		Map<String, Object> err = (Map<String, Object>) body.get("error");
		Object m0 = err.get("message");
		if (!"INVALID_ARGUMENT".equals(err.get("code")) || !(m0 instanceof String)) {
			return r;
		}
		String msg = (String) m0;
		if (!(msg.contains(FIELD_ERR_MARK) || msg.contains(TRIM_ERR_MARK)) || msg.contains(FIELD_HINT)) {
			return r;
		}
		String oldText = JSON.toJSONString(body);
		Map<String, Object> nerr = new LinkedHashMap<String, Object>(err);
		nerr.put("message", msg + FIELD_HINT);
		Map<String, Object> nbody = new LinkedHashMap<String, Object>(body);
		nbody.put("error", nerr);
		String newText = JSON.toJSONString(nbody);
		List<Object> nc = null;
		if (res.get("content") instanceof List) {
			nc = new ArrayList<Object>();
			for (Object c : (List<Object>) res.get("content")) {
				if (c instanceof Map && "text".equals(((Map<String, Object>) c).get("type")) && oldText.equals(((Map<String, Object>) c).get("text"))) {
					Map<String, Object> ci = new LinkedHashMap<String, Object>((Map<String, Object>) c);
					ci.put("text", newText);
					nc.add(ci);
				} else {
					nc.add(c);
				}
			}
		}
		Object oc = res.get("content");
		boolean cDone = false;
		try {
			if (nc != null) {
				res.put("content", nc);
				cDone = true;
			}
			res.put("structuredContent", nbody);
		} catch (RuntimeException e) {
			if (cDone) {
				try {
					res.put("content", oc);
				} catch (RuntimeException ignore) {
					// 尽力还原，失败也原样返回
				}
			}
			throw e;
		}
		return r;
	}

	static class Hook implements MethodInterceptor {
		final AgentRiskMcpPostProcessor p;

		Hook(AgentRiskMcpPostProcessor p) {
			this.p = p;
		}

		@SuppressWarnings("unchecked")
		public Object invoke(MethodInvocation mi) throws Throwable {
			Object[] a = mi.getArguments();
			if (a.length != 2 || !(a[1] instanceof String)) {
				return mi.proceed();
			}
			return p.around((Map<String, Object>) a[0], (String) a[1], mi);
		}
	}
}


</cursor_untrusted_data_1337>