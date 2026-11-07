package cn.qtou.api.modules.agent.service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;

import cn.qtou.common.utils.StringUtils;

/**
 * Agent MCP 门面（Streamable HTTP JSON-RPC，挂在 POST /v1/agent/mcp）。
 * 只转调本模块 Agent*Service，禁止直连业务库 JDBC。
 * 最小工具集覆盖三场景各至少 1 个只读/待确认入口。
 */
@Service
public class AgentMcpService {

	public static final String PROTOCOL_VERSION = "2024-11-05";
	public static final String SERVER_NAME = "qtou-agent-mcp";
	public static final String SERVER_VERSION = "0.2.0";

	@Autowired
	private AgentProjectService agentProjectService;
	@Autowired
	private AgentDocumentService agentDocumentService;
	@Autowired
	private AgentPortfolioService agentPortfolioService;
	@Autowired
	private DictMapService dictMapService;

	/**
	 * @param agentRow resolve() 得到的 agent_api_key 行
	 * @param bodyJson 请求 JSON 文本
	 * @return JSON-RPC 响应对象；notification 返回 null（HTTP 202/空体由控制器处理）
	 */
	public Object handle(Map<String, Object> agentRow, String bodyJson) {
		try {
			return handleRequest(agentRow, bodyJson);
		} catch (com.alibaba.fastjson.JSONException | ClassCastException ex) {
			// s2b：请求体本身不是合法 JSON-RPC（坏 JSON / params 不是对象）——不透出原始异常
			LOG.warn("agent mcp bad request: " + ex.getClass().getName() + ": " + ex.getMessage());
			return rpcError(null, -32600, "请求格式不对：应为 JSON-RPC 2.0 对象，params 应为对象");
		} catch (RuntimeException ex) {
			String ref = newRef();
			LOG.error("agent mcp request failed ref=" + ref, ex);
			return rpcError(null, -32603, "服务内部错误，已记录日志（ref=" + ref + "）");
		}
	}

	private Object handleRequest(Map<String, Object> agentRow, String bodyJson) {
		JSONObject req = JSON.parseObject(bodyJson);
		if (req == null) {
			return rpcError(null, -32700, "Parse error");
		}
		String method = req.getString("method");
		Object id = req.get("id");
		boolean isNotification = !req.containsKey("id");
		JSONObject params = req.getJSONObject("params");
		if (params == null) {
			params = new JSONObject();
		}

		if ("initialize".equals(method)) {
			Map<String, Object> result = new LinkedHashMap<String, Object>();
			result.put("protocolVersion", PROTOCOL_VERSION);
			Map<String, Object> caps = new LinkedHashMap<String, Object>();
			caps.put("tools", new LinkedHashMap<String, Object>());
			result.put("capabilities", caps);
			Map<String, Object> serverInfo = new LinkedHashMap<String, Object>();
			serverInfo.put("name", SERVER_NAME);
			serverInfo.put("version", SERVER_VERSION);
			result.put("serverInfo", serverInfo);
			return rpcResult(id, result);
		}
		if ("notifications/initialized".equals(method) || "initialized".equals(method)) {
			return null;
		}
		if ("ping".equals(method)) {
			return rpcResult(id, new LinkedHashMap<String, Object>());
		}
		if ("tools/list".equals(method)) {
			Map<String, Object> result = new LinkedHashMap<String, Object>();
			result.put("tools", toolDefs());
			return rpcResult(id, result);
		}
		if ("tools/call".equals(method)) {
			String name = params.getString("name");
			Object rawArgs = params.get("arguments");
			if (rawArgs != null && !(rawArgs instanceof Map)) {
				return rpcResult(id, toolError(name, new IllegalArgumentException("参数 arguments 格式不对，应为对象")));
			}
			JSONObject args = params.getJSONObject("arguments");
			if (args == null) {
				args = new JSONObject();
			}
			try {
				checkArgTypes(name, args);
				checkKnownArgs(name, args);
				Object data = callTool(agentRow, name, args);
				// s2-debt D3：search/list 类工具统一 {items:[...]}（HTTP 与 stdio 同形；structuredContent 须为对象）
				if (data instanceof List) {
					Map<String, Object> wrapped = new LinkedHashMap<String, Object>();
					wrapped.put("items", data);
					data = wrapped;
				}
				if (AgentPaging.PAGED_TOOLS.contains(name) && data instanceof Map && ((Map) data).get("items") instanceof List) {
					Map<String, Object> paged = new LinkedHashMap<String, Object>((Map<String, Object>) data);
					paged.putAll(AgentPaging.page((List<?>) paged.get("items"), args.getInteger("page"), args.getInteger("pageSize")));
					data = paged;
				}
                List<Map<String,Object>> imageContent=new ArrayList<Map<String,Object>>();
                if(data instanceof Map){Object rows=((Map)data).get("items");if(rows instanceof List)for(Object raw:(List)rows){Map row=(Map)raw;Object encoded=row.remove("imageBase64");if(encoded!=null){Map<String,Object> image=new LinkedHashMap<String,Object>();image.put("type","image");image.put("mimeType","image/png");image.put("data",encoded);imageContent.add(image);}}}
				Map<String, Object> contentItem = new LinkedHashMap<String, Object>();
				contentItem.put("type", "text");
				contentItem.put("text", JSON.toJSONString(data));
				Map<String, Object> result = new LinkedHashMap<String, Object>();
				List<Map<String,Object>> allContent=new ArrayList<Map<String,Object>>();allContent.add(contentItem);allContent.addAll(imageContent);result.put("content",allContent);
				result.put("isError", Boolean.FALSE);
				result.put("structuredContent", data);
				return rpcResult(id, result);
			} catch (Exception ex) {
				// s2-debt D2：工具执行期任何异常都回结构化 isError，不再抛 JSON-RPC -32603 打断调用
				return rpcResult(id, toolError(name, ex));
			}
		}
		if (isNotification) {
			return null;
		}
		return rpcError(id, -32601, "Method not found: " + method);
	}

	private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger(AgentMcpService.class);

	/** s2-debt D2：异常 → {isError:true, content:[{text: {"error":{code,message,tool}}}], structuredContent}。
	 *  s2b：message 只给人话；原始异常（类名、堆栈、服务器路径、SQL）只写服务端日志，用 ref 关联。 */
	static Map<String, Object> toolError(String tool, Throwable ex) {
		String code = errorCode(ex);
		String raw = ex.getMessage();
		String ref = newRef();
		String msg;
		boolean hidden;
		if ("INTERNAL_ERROR".equals(code)) {
			msg = "服务内部错误，已记录日志（ref=" + ref + "）";
			hidden = true;
		} else if ("BACKEND_DB_ERROR".equals(code)) {
			msg = "数据库访问失败，请稍后重试；详情已记录日志（ref=" + ref + "）";
			hidden = true;
		} else if (ex instanceof ClassCastException || ex instanceof com.alibaba.fastjson.JSONException
				|| ex instanceof NumberFormatException) {
			msg = "参数格式不对，请按工具 inputSchema 检查各参数类型（ref=" + ref + "）";
			hidden = true;
		} else if ("NOT_FOUND".equals(code)) {
			// s2c N4：NOT_FOUND 只说什么不存在，不回显调用方传入的原始 id/输入
			msg = safeMessage(notFoundHead(raw), code, ref);
			hidden = false;
		} else {
			msg = safeMessage(raw, code, ref);
			hidden = !msg.equals(raw);
		}
		if ("agent_projects_user_fields".equals(tool)) {
			LOG.info("agent mcp user fields failed: " + code + " ref=" + ref);
		} else if (hidden) {
			LOG.error("agent mcp tool " + tool + " failed: " + code + " ref=" + ref, ex);
		} else if (ex.getCause() != null) {
			LOG.warn("agent mcp tool " + tool + " failed: " + code + " ref=" + ref, ex);
		} else {
			LOG.info("agent mcp tool " + tool + " failed: " + code + " ref=" + ref + " msg=" + redactForCaller(raw, 800));
		}
		Map<String, Object> err = new LinkedHashMap<String, Object>();
		err.put("code", code);
		err.put("message", msg);
		err.put("tool", tool);
		Map<String, Object> body = new LinkedHashMap<String, Object>();
		body.put("error", err);
		Map<String, Object> contentItem = new LinkedHashMap<String, Object>();
		contentItem.put("type", "text");
		contentItem.put("text", JSON.toJSONString(body));
		Map<String, Object> result = new LinkedHashMap<String, Object>();
		result.put("content", Arrays.asList(contentItem));
		result.put("isError", Boolean.TRUE);
		result.put("structuredContent", body);
		return result;
	}

	/** 含 Java 类名 / 异常名 / 堆栈行 的片段。 */
	static final java.util.regex.Pattern JAVA_TOKEN = java.util.regex.Pattern.compile(
			"\\b(?:java|javax|sun|com|org|cn|io|net)\\.[A-Za-z_$][\\w$]*\\.|\\b\\w*(?:Exception|Throwable)\\b|\\bat [\\w$.]+\\(|\\.java:\\d+");
	/** 服务器绝对路径（/a/b、~/a、C:\\a）；URL 里的 //host/... 不算。 */
	static final java.util.regex.Pattern ABS_PATH = java.util.regex.Pattern.compile(
			"(?:^|(?<=[\\s=:：(（\"'《<,，]))~?(?:/[^/\\s<>\"'）)，,;；]+(?: [^/\\s<>\"'）)，,;；]+)*(?=/))*/[^/\\s<>\"'）)，,;；]+/?"
			+ "|\\b[A-Za-z]:\\\\[^\\s<>\"'）)，,;；]+");

	/** 业务消息原样保留；混入原始异常的截掉尾巴；绝对路径只留文件名。 */
	static String safeMessage(String raw, String code, String ref) {
		if (StringUtils.isBlank(raw)) {
			return genericMessage(code, ref);
		}
		String msg = raw;
		if (JAVA_TOKEN.matcher(msg).find()) {
			int cut = -1;
			for (String sep : new String[] { ": ", "：" }) {
				int i = msg.indexOf(sep);
				if (i > 0 && (cut < 0 || i < cut)) {
					cut = i;
				}
			}
			String head = cut > 0 ? msg.substring(0, cut) : "";
			if (head.length() > 0 && !JAVA_TOKEN.matcher(head).find()) {
				// s2e：只脱敏截断 head，ref 在后面追加，保证不被截掉
				return redactForCaller(stripPaths(head), CALLER_MSG_MAX) + "（详情已记录日志，ref=" + ref + "）";
			} else {
				return genericMessage(code, ref);
			}
		}
		return redactForCaller(stripPaths(msg), CALLER_MSG_MAX);
	}

	static String stripPaths(String msg) {
		java.util.regex.Matcher m = ABS_PATH.matcher(msg);
		StringBuffer sb = new StringBuffer();
		while (m.find()) {
			String path = m.group().replace('\\', '/');
			while (path.endsWith("/")) {
				path = path.substring(0, path.length() - 1);
			}
			String base = path.substring(path.lastIndexOf('/') + 1);
			m.appendReplacement(sb, java.util.regex.Matcher.quoteReplacement(base));
		}
		m.appendTail(sb);
		return sb.toString();
	}

	/** s2e：回给调用方的 message 上限，与 s2d 桥坏请求行一致。 */
	public static final int CALLER_MSG_MAX = 300;
	private static final String SECRET_KEY = "[\\w.-]*(?:token|password|passwd|pwd|secret|api[_-]?key|authorization|cookie|agent[_-]?key|credential)[\\w.-]*";
	private static final java.util.regex.Pattern RE_QTPAT = java.util.regex.Pattern.compile("qtpat_[A-Za-z0-9_\\-.]*");
	private static final java.util.regex.Pattern RE_BEARER = java.util.regex.Pattern.compile("\\b(Bearer|Basic)\\s+[^\\s\"',;}\\]]+",
			java.util.regex.Pattern.CASE_INSENSITIVE);
	private static final java.util.regex.Pattern RE_JSON_KV = java.util.regex.Pattern.compile(
			"(\"" + SECRET_KEY + "\"\\s*:\\s*)(\"(?:[^\"\\\\]|\\\\.)*\"?|[^,}\\]\\s]+)", java.util.regex.Pattern.CASE_INSENSITIVE);
	private static final java.util.regex.Pattern RE_PLAIN_KV = java.util.regex.Pattern.compile(
			"(\\b" + SECRET_KEY + "\\s*[=:]\\s*)(\"[^\"]*\"?|'[^']*'?|[^\\s&,;}\\]\"']+)", java.util.regex.Pattern.CASE_INSENSITIVE);

	/** s2e：与 s2d 桥 redact() 同规则——令牌串/Bearer/敏感键值遮掉，控制字符与 U+2028/2029 转义，超长截断并注明「…(+N chars)」。 */
	public static String redactForCaller(String input, int max) {
		if (input == null) {
			return null;
		}
		// s2f：长度一律按 Unicode 码点计，不切开 emoji / 代理对
		int full = input.codePointCount(0, input.length());
		String s = full > 4096 ? input.substring(0, input.offsetByCodePoints(0, 4096)) : input;
		s = RE_QTPAT.matcher(s).replaceAll("***令牌***");
		s = RE_BEARER.matcher(s).replaceAll("$1 ***");
		s = RE_JSON_KV.matcher(s).replaceAll("$1\"***\"");
		s = RE_PLAIN_KV.matcher(s).replaceAll("$1***");
		StringBuilder b = new StringBuilder(s.length() + 16);
		for (int i = 0; i < s.length(); i++) {
			char c = s.charAt(i);
			if (c == '\n') {
				b.append("\\n");
			} else if (c == '\r') {
				b.append("\\r");
			} else if (c == '\t') {
				b.append("\\t");
			} else if (c < 0x20 || c == 0x7f || c == '\u2028' || c == '\u2029') {
				b.append(String.format("\\u%04x", (int) c));
			} else {
				b.append(c);
			}
		}
		s = b.toString();
		if (s.codePointCount(0, s.length()) > max) {
			return s.substring(0, s.offsetByCodePoints(0, max)) + "…(+" + Math.max(1, full - max) + " chars)";
		}
		if (full > 4096) {
			return s + "…(+" + (full - 4096) + " chars)";
		}
		return s;
	}

	/** s2c N4：「项目不存在或不属于当前租户: xxx」→「项目不存在或不属于当前租户」。 */
	static String notFoundHead(String raw) {
		if (StringUtils.isBlank(raw)) {
			return raw;
		}
		int cut = -1;
		for (String sep : new String[] { ":", "：" }) {
			int i = raw.indexOf(sep);
			if (i > 0 && (cut < 0 || i < cut)) {
				cut = i;
			}
		}
		return cut > 0 ? raw.substring(0, cut).trim() : raw;
	}

	static String genericMessage(String code, String ref) {
		if ("NOT_FOUND".equals(code)) {
			return "对象不存在（ref=" + ref + "）";
		}
		if ("INVALID_ARGUMENT".equals(code)) {
			return "参数不对，请按工具 inputSchema 检查（ref=" + ref + "）";
		}
		if ("FAILED_PRECONDITION".equals(code)) {
			return "当前状态不允许该操作；详情已记录日志（ref=" + ref + "）";
		}
		return "服务内部错误，已记录日志（ref=" + ref + "）";
	}

	static String newRef() {
		return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
	}

	private static final Map<String, String> TYPE_CN = new HashMap<String, String>();
	static {
		TYPE_CN.put("object", "对象");
		TYPE_CN.put("array", "数组");
		TYPE_CN.put("string", "字符串");
		TYPE_CN.put("integer", "整数");
		TYPE_CN.put("number", "数字");
		TYPE_CN.put("boolean", "true/false");
	}

	/** s2b：按 tools/list 声明的 inputSchema 校验参数类型，给人话错误，而不是让 fastjson 抛 ClassCastException。
	 *  string 宽松（数字/布尔也接受，与 fastjson getString 行为一致）。 */
	@SuppressWarnings("unchecked")
	private void checkArgTypes(String tool, JSONObject args) {
		Map<String, Object> schema = null;
		for (Map<String, Object> t : toolDefs()) {
			if (t.get("name") != null && t.get("name").equals(tool)) {
				schema = (Map<String, Object>) t.get("inputSchema");
				break;
			}
		}
		if (schema == null || !(schema.get("properties") instanceof Map)) {
			return;
		}
		Map<String, Object> props = (Map<String, Object>) schema.get("properties");
		for (Map.Entry<String, Object> e : props.entrySet()) {
			Object v = args.get(e.getKey());
			if (v == null || !(e.getValue() instanceof Map)) {
				continue;
			}
			Map<String, Object> ps = (Map<String, Object>) e.getValue();
			String type = String.valueOf(ps.get("type"));
			if (("array".equals(type) || "object".equals(type)) && v instanceof String) {
				// 兼容把数组/对象序列化成字符串传进来的客户端（fastjson 原本也会解析）
				try {
					Object parsed = JSON.parse((String) v);
					if (typeOk(type, parsed)) {
						args.put(e.getKey(), parsed);
						v = parsed;
					}
				} catch (RuntimeException ignore) {
					// 解析失败 → 下面按类型不对报人话
				}
			}
			if (!typeOk(type, v)) {
				throw new IllegalArgumentException("参数 " + e.getKey() + " 格式不对，应为" + typeCn(type));
			}
			if ("array".equals(type) && ps.get("items") instanceof Map) {
				String it = String.valueOf(((Map<String, Object>) ps.get("items")).get("type"));
				List<Object> list = (List<Object>) v;
				for (int i = 0; i < list.size(); i++) {
					if (list.get(i) != null && !typeOk(it, list.get(i))) {
						throw new IllegalArgumentException("参数 " + e.getKey() + " 第 " + (i + 1) + " 项格式不对，应为" + typeCn(it));
					}
				}
			}
		}
	}

	/** s2d P2：search/list 类工具的未知参数名直接报 INVALID_ARGUMENT，不再静默忽略后返回全库列表。 */
	public static final String MISSING_Q_MSG = "缺少 q：请传关键词 q（项目名或文档名）；要列出某个项目的全部文档请传 projectId";
	private static final Map<String, String[]> ARG_ALIASES = new HashMap<String, String[]>();
	static {
		ARG_ALIASES.put("agent_documents_search", new String[] { "project" });
		ARG_ALIASES.put("agent_portfolio_list", new String[0]);
		ARG_ALIASES.put("agent_projects_user_fields", new String[0]);
		ARG_ALIASES.put("agent_risk_alerts_list", new String[] { "project" });
	}
	private static final java.util.regex.Pattern SAFE_KEY = java.util.regex.Pattern.compile("[A-Za-z_][A-Za-z0-9_]{0,40}");

	@SuppressWarnings("unchecked")
	private void checkKnownArgs(String tool, JSONObject args) {
		String[] aliases = ARG_ALIASES.get(tool);
		if (aliases == null || args == null || args.isEmpty()) {
			return;
		}
		java.util.Set<String> allowed = new java.util.LinkedHashSet<String>();
		for (Map<String, Object> t : toolDefs()) {
			if (tool.equals(t.get("name")) && t.get("inputSchema") instanceof Map) {
				Object props = ((Map<String, Object>) t.get("inputSchema")).get("properties");
				if (props instanceof Map) {
					allowed.addAll(((Map<String, Object>) props).keySet());
				}
			}
		}
		String shown = joinCn(allowed);
		allowed.addAll(Arrays.asList(aliases));
		for (String k : args.keySet()) {
			if (!allowed.contains(k)) {
				throw new IllegalArgumentException(unknownArgMessage(k, shown));
			}
		}
	}

	public static String unknownArgMessage(String key, String shown) {
		String who = key != null && SAFE_KEY.matcher(key).matches() ? "参数 " + key + " 不认识" : "有不认识的参数名";
		return who + "，可用参数：" + shown;
	}

	static String joinCn(java.util.Collection<String> c) {
		StringBuilder sb = new StringBuilder();
		for (String x : c) {
			if (sb.length() > 0) {
				sb.append("、");
			}
			sb.append(x);
		}
		return sb.toString();
	}

	private static String typeCn(String type) {
		String cn = TYPE_CN.get(type);
		return cn == null ? type : cn;
	}

	private static boolean typeOk(String type, Object v) {
		if ("object".equals(type)) {
			return v instanceof Map;
		}
		if ("array".equals(type)) {
			return v instanceof List;
		}
		if ("integer".equals(type)) {
			if (v instanceof Integer || v instanceof Long || v instanceof Short || v instanceof Byte
					|| v instanceof java.math.BigInteger) {
				return true;
			}
			if (v instanceof Number) {
				double d = ((Number) v).doubleValue();
				return d == Math.rint(d) && Math.abs(d) < Integer.MAX_VALUE;
			}
			return v instanceof String && ((String) v).trim().matches("-?\\d{1,9}");
		}
		if ("number".equals(type)) {
			return v instanceof Number || (v instanceof String && ((String) v).trim().matches("-?\\d+(\\.\\d+)?"));
		}
		if ("boolean".equals(type)) {
			return v instanceof Boolean || "true".equals(v) || "false".equals(v);
		}
		if ("string".equals(type)) {
			return v instanceof String || v instanceof Number || v instanceof Boolean;
		}
		return true;
	}

	static String errorCode(Throwable ex) {
		if (ex instanceof IllegalArgumentException) {
			String m = ex.getMessage();
			return m != null && m.contains("不存在") ? "NOT_FOUND" : "INVALID_ARGUMENT";
		}
		if (ex instanceof com.alibaba.fastjson.JSONException || ex instanceof ClassCastException) {
			return "INVALID_ARGUMENT";
		}
		if (ex instanceof IllegalStateException) {
			return "FAILED_PRECONDITION";
		}
		if (ex instanceof org.springframework.dao.DataAccessException) {
			return "BACKEND_DB_ERROR";
		}
		return "INTERNAL_ERROR";
	}

	public String newSessionId() {
		return UUID.randomUUID().toString();
	}

	private List<Map<String, Object>> toolDefs() {
		List<Map<String, Object>> tools = new ArrayList<Map<String, Object>>();
		tools.add(tool("agent_health", "健康检查（确认 Bearer 有效）", schema()));
		// 场景① 入池：只读解析 + 待确认创建
		tools.add(tool("agent_bp_parse", "场景①：解析 BP 文本为结构化草稿（不入库）。仅按「项目名称：/公司名称：」等标签抽取，无标签时项目名取首个正文行（跳过页码标记）；projectName/companyName 为空时返回 hint，创建待确认项目时请显式传 projectName/companyName",
				schema("text", "string", "BP 文本内容", true)));
		tools.add(tool("agent_projects_create_pending", "场景①：创建待确认项目（不直接入池）。BP 无「项目名称：/公司名称：」标签时，务必传 projectName（项目名）与 companyName（公司全称）；未传时依次取 bpEvidence.fields 的 project.projectName / company.name；带 bpEvidence 而公司全称仍缺失会被拒绝",
				schema("text", "string", "BP 文本或项目描述", false, "projectName", "string", "项目名称；优先于 BP 文本解析，未传取 bpEvidence 的 project.projectName（无 text 时必填其一）", false, "companyName", "string", "公司全称（工商主体，如「XX科技有限公司」）；优先于 BP 文本解析，未传取 bpEvidence 的 company.name；须能在 bpEvidence.document.pages 原文中找到", false,"bpEvidence","object","完整BP结构化证据，按bp_schema；随用户确认一并入对应模块",false)));
		tools.add(tool("agent_projects_get", "场景①：查询待确认项目",
				schema("pendingId", "string", "待确认 id", true)));
		tools.add(tool("agent_projects_confirm", "场景①：确认入正式池；补全明确BP字段和同名外部数据，真实Logo优先、缺失则沿用网页占位图；返回entryCompleteness及missingFields，不猜测未知字段",
				schema("pendingId", "string", "待确认 id", true, "companyFallback", "object", "天眼查失败时使用联网检索正文与当前模型核实结果组成的补全CLI schemaVersion=1完整证据；未知工商字段留空", false)));
        tools.add(tool("agent_projects_bp_schema","完整BP字段目录：项目/公司/团队/融资/附件；类型、字典、写入边界及页码原文契约",schema()));
        tools.add(tool("agent_projects_bp_source","读取本项目原始逐页BP与已审核结构化证据（租户和原入池用户隔离）",schema("pendingId","string","原待确认id",true)));
        tools.add(tool("agent_projects_bp_get","读取项目池完整BP字段、核心团队、融资及附件；租户及原用户隔离",schema("pendingId","string","原待确认id",true)));
        tools.add(tool("agent_projects_bp_fill","BP逐字段原文校验后预览/补空；真实创建团队及历史融资；不覆盖已有值",schema("pendingId","string","原待确认id",true,"evidence","object","先调用agent_projects_bp_schema获取完整结构；含document.pages及逐项sources/nature/asOf/reviewed",true,"confirmed","boolean","用户授权后true，否则零业务写入预览",false)));
        tools.add(tool("agent_projects_bp_pages","读取本项目BP的真实页面图像及文字，每次1至2页；图片以MCP image内容返回",schema("pendingId","string","原待确认id",true,"fileId","string","本项目已上传BP附件id",true,"pages","array","实际1起始页码，每次1至2页",true)));
        tools.add(tool("agent_projects_bp_assets","从真实BP按页裁图：Logo、核心成员头像、其他证据图片；默认预览，确认后补写空值或姓名占位图",schema("pendingId","string","原待确认id",true,"fileId","string","本项目已上传BP附件id",true,"assets","array","先读bp_schema.visualMedia；逐图视觉核验目标身份及归属",true,"confirmed","boolean","用户已授权补全时true",false)));
        tools.add(tool("agent_projects_bp_attach","真实上传PDF并关联商业计划书，按文件SHA256幂等；默认只预览",schema("pendingId","string","原待确认id",true,"file","object","{fileName,contentBase64,sha256?} PDF不超过20MB；不接受本地路径假附件",true,"confirmed","boolean","用户授权上传后true",false)));
		tools.add(tool("agent_projects_user_fields", "用户原话补全联系人、推荐人、沟通形式、生产地址、预期融资及币种；默认补空，先预览再确认", schema("pendingId", "string", "原待确认id，支持待确认及已入池项目", true, "statement", "string", "用户原话，2至2000字符，每个值须逐字出现", true, "fields", "object", "属性到值：projectLinkManName/projectLinkManJob/projectLinkManContactWay/referenceManName/referenceManContactWay/communicateForm/productionAddress/expectFinancing/currency", true, "confirmed", "boolean", "false预览，true事务写入并回读", false, "overwrite", "boolean", "仅用户原话明确同意覆盖已有字段时允许true", false)));
		tools.add(tool("agent_projects_profile_get", "读取已入池项目基本情况字段清单（不修改）", schema("pendingId", "string", "原待确认id", true)));
		tools.add(tool("agent_projects_profile_fill", "有出处地补全已入池项目/公司空字段；默认预览，不覆盖已有值", schema("pendingId", "string", "原待确认id", true, "evidence", "object", "联网检索正文及当前模型核实的profile.py凭证", true, "confirmed", "boolean", "用户授权补全时true，缺省仅预览", false)));
		tools.add(tool("agent_projects_reject", "场景①：驳回待确认项目",
				schema("pendingId", "string", "待确认 id", true, "reason", "string", "驳回原因", false)));
		// 场景② 尽调：文档检索
		tools.add(tool("agent_documents_search", "场景②：模糊查文档（只读）",
				schema("q", "string", "关键词（项目名/文档名/正文，支持部分词；文件名 0 命中且正文也 0 命中时自动 2-gram 容错）", false, "projectId", "string", "项目 id", false,
						"page", "integer", "页码，从 1 开始，默认 1", false, "pageSize", "integer", "每页条数 1–50，默认 20", false)));
		tools.add(tool("agent_documents_content", "场景②：按 fileId 读文档正文（只读，限本租户）",
				schema("fileId", "string", "文档 fileId（来自 agent_documents_search）", true, "maxChars", "integer", "最多返回字符数，默认 20000", false)));
		tools.add(tool("agent_documents_pages", "场景②：按 fileId 取文档页面图片（PDF 或图片，只读，限本租户），每次1至2页；扫描件没有文字层时用它看图读取",
				schema("fileId", "string", "文档 fileId（来自 agent_documents_search）", true, "pages", "array", "实际1起始页码，每次1至2页", true)));
		// 场景③ 投后/预警：列表只读
		tools.add(tool("agent_portfolio_list",
				"场景③：投后/项目名单（只读，限本租户）。afterInvestOnly=true 只列投后项目；每条含 projectId、项目名、公司全称、法人、成立日期、行业、投资日期，用于外网查询消歧",
				schema("afterInvestOnly", "boolean", "只列投后项目（is_after_invest=1 或 after_invest_status 非空），场景③应传 true", false,
						"q", "string", "可选：按项目名/公司全称模糊过滤", false,
						"page", "integer", "页码，从 1 开始，默认 1；返回 hasMore=true 时取下一页", false,
						"pageSize", "integer", "每页条数 1–50，默认 20", false)));
		tools.add(tool("agent_portfolio_quarterly",
				"场景③：读项目季报（年/季、经营情况、重大事项、风险及化解、最新估值）+ 季度财务（营收、净利、总资产、总负债、净资产；current=本期，samePeriod=去年同期）（只读，限本租户）",
				schema("projectId", "string", "项目 id（来自 agent_portfolio_list）", true,
						"from", "string", "起始季度 YYYYQn，如 2025Q4（可选）", false,
						"to", "string", "截止季度 YYYYQn（可选）", false)));
		tools.add(tool("agent_risk_alerts_list", "场景③：风险预警列表（只读，限本租户；传别家 projectId 会被拒）",
				schema("projectId", "string", "项目 id", false, "state", "string", "状态过滤：网页字典 risk_state 值（relieve|ignore|follow_up|alarm）；unset=未设置（Agent 新写入与网页新建默认都是空）；旧值 open 视同 unset", false,
						"page", "integer", "页码，从 1 开始，默认 1；返回 hasMore=true 时取下一页", false,
						"pageSize", "integer", "每页条数 1–50，默认 20", false)));
		tools.add(tool("agent_risk_alerts_create", "场景③：员工逐条确认后写入一条风险预警。risk_state 默认留空（与网页新建一致，riskStateLabel=null）；可选传 state=网页字典 risk_state 值，字典外返回 INVALID_ARGUMENT。未确认禁止调用；同项目同事件已有 Agent 写入、尚未关闭（未设置/告警/跟进）的预警时不重复写（员工网页手建的不算），返回 duplicate=true。意见结论 = 固定头「AI 预警初判，需投后经理复核」+ 调用方只传的正文 conclusion（≤300 字，按字计；不得带网址或 [n] 索引，超限/违规返回 INVALID_ARGUMENT、不写库）+ 服务端按 sources 生成的「出处：[1] URL；[2] URL」（URL 原样完整；固定头和出处索引不计 300）；响应带 bodyChars、indexChars。明细放 sources，事件描述 matters 最多 255 字",
				createAlertSchema()));
		tools.add(tool("agent_dicts", "字典列表 invest_round|industry_type|risk_grade|risk_state|risk_type（与网页下拉同源同序）",
				schema("type", "string", "字典类型", true)));
        for (Map<String,Object> definition : tools) if ("agent_projects_user_fields".equals(definition.get("name"))) {
            Map properties = (Map) ((Map) definition.get("inputSchema")).get("properties");
            Map statement = (Map) properties.get("statement");
            statement.put("minLength", 2); statement.put("maxLength", 2000);
            Map fields = (Map) properties.get("fields");
            Map<String,Object> allowed = new LinkedHashMap<String,Object>();
            for (String key : AgentUserFields.KEYS) allowed.put(key, schemaString(AgentEntryFields.LABELS.get(key)));
            fields.put("properties", allowed); fields.put("additionalProperties", false); fields.put("minProperties", 1);
        }
        for(Map<String,Object> tool:tools){String tn=String.valueOf(tool.get("name"));Map ps=(Map)((Map)tool.get("inputSchema")).get("properties");if("agent_projects_bp_assets".equals(tn))ps.put("assets",AgentBpMediaService.assetSchema());if("agent_projects_bp_pages".equals(tn)||"agent_documents_pages".equals(tn)){Map pg=new LinkedHashMap();pg.put("type","array");pg.put("minItems",1);pg.put("maxItems",2);Map it=new LinkedHashMap();it.put("type","integer");it.put("minimum",1);pg.put("items",it);ps.put("pages",pg);}}
        for(Map<String,Object> tool:tools){String name=String.valueOf(tool.get("name"));Map sc=(Map)tool.get("inputSchema"),props=(Map)sc.get("properties");if("agent_projects_bp_fill".equals(name))props.put("evidence",AgentBpService.evidenceSchema());if("agent_projects_create_pending".equals(name))props.put("bpEvidence",AgentBpService.evidenceSchema());if("agent_projects_bp_attach".equals(name))props.put("file",new LinkedHashMap<String,Object>(){{put("type","object");put("properties",new LinkedHashMap<String,Object>(){{put("fileName",schemaString("PDF文件名，不含路径"));put("contentBase64",schemaString("真实PDF内容base64，不超过20MB"));put("sha256",schemaString("可选文件SHA256"));}});put("required",java.util.Arrays.asList("fileName","contentBase64"));put("additionalProperties",false);}});}
		return tools;
	}

	private Object callTool(Map<String, Object> agent, String name, JSONObject args) {
		String customerId = str(agent.get("customer_id"));
		if ("agent_projects_user_fields".equals(name)) {
			if (!(args.get("statement") instanceof String)) {
				throw new IllegalArgumentException("statement必须是用户原话字符串");
			}
			return agentProjectService.userFields(args.getString("pendingId"), agent, args.getString("statement"),
					(Map<String,Object>) args.get("fields"), Boolean.TRUE.equals(args.get("confirmed")), Boolean.TRUE.equals(args.get("overwrite")));
		}
		if ("agent_health".equals(name)) {
			Map<String, Object> m = new LinkedHashMap<String, Object>();
			m.put("ok", true);
			m.put("service", SERVER_NAME);
			m.put("customerId", customerId);
			m.put("agentKeyId", agent.get("id"));
			return m;
		}
		if ("agent_bp_parse".equals(name)) {
			String text = args.getString("text");
			if (StringUtils.isBlank(text)) {
				throw new IllegalArgumentException("缺少 text");
			}
			return agentProjectService.parseOnly(text);
		}
		if ("agent_projects_create_pending".equals(name)) {
			String text = args.getString("text");
			Object bp=args.get("bpEvidence");
            if(bp!=null&&!(bp instanceof Map))throw new IllegalArgumentException("bpEvidence须为对象");
			// bp-company-fix：显式 projectName/companyName 优先，缺省取 bpEvidence 的 project.projectName / company.name
			Map<String, String> overrides = AgentPendingNames.resolve(args.getString("projectName"), args.getString("companyName"), (Map<?, ?>) bp);
			if (StringUtils.isBlank(text) && overrides.get("projectName") == null) {
				throw new IllegalArgumentException(AgentPendingNames.MISSING_TEXT);
			}
			if (StringUtils.isBlank(text)) {
				text = "项目名称：" + overrides.get("projectName");
			}
			if (bp != null && overrides.get("companyName") == null) {
				AgentPendingNames.requireCompany(overrides, (Map<?, ?>) bp, str(agentProjectService.parseOnly(text).get("companyName")));
			}
            return agentProjectService.createPendingWithBp(agent, text, overrides, (Map<String,Object>)bp);
		}
		if ("agent_projects_get".equals(name)) {
			String pendingId = args.getString("pendingId");
			if (StringUtils.isBlank(pendingId)) {
				throw new IllegalArgumentException("缺少 pendingId");
			}
			Map<String, Object> pending = agentProjectService.getPending(pendingId, customerId);
			if (pending == null) {
				throw new IllegalArgumentException("待确认项目不存在");
			}
			return pending;
		}
		if ("agent_projects_confirm".equals(name)) {
			String pendingId = args.getString("pendingId");
			if (StringUtils.isBlank(pendingId)) {
				throw new IllegalArgumentException("缺少 pendingId");
			}
			Object fallback = args.get("companyFallback");
			if (fallback != null && !(fallback instanceof Map)) throw new IllegalArgumentException("companyFallback须为证据对象");
			return agentProjectService.confirm(pendingId, agent, (Map<String, Object>) fallback);
		}
        if("agent_projects_bp_source".equals(name)){String id=args.getString("pendingId");if(StringUtils.isBlank(id))throw new IllegalArgumentException("缺少pendingId");return agentProjectService.bpSource(id,agent);}
        if("agent_projects_bp_schema".equals(name))return agentProjectService.bpSchema(agent);
        if("agent_projects_bp_pages".equals(name)||"agent_projects_bp_assets".equals(name)){
            boolean pages="agent_projects_bp_pages".equals(name);String pid=args.getString("pendingId"),fid=args.getString("fileId");if(StringUtils.isBlank(pid)||StringUtils.isBlank(fid))throw new IllegalArgumentException("缺少pendingId或fileId");Object rows=args.get(pages?"pages":"assets");if(!(rows instanceof List))throw new IllegalArgumentException("pages/assets须为数组");return agentProjectService.bpMedia(pid,agent,fid,pages?(List)rows:null,pages?null:(List)rows,!pages&&Boolean.TRUE.equals(args.get("confirmed")));
        }
        if("agent_projects_bp_get".equals(name)||"agent_projects_bp_fill".equals(name)||"agent_projects_bp_attach".equals(name)){
            String id=args.getString("pendingId");if(StringUtils.isBlank(id))throw new IllegalArgumentException("缺少pendingId");boolean fill="agent_projects_bp_fill".equals(name),attach="agent_projects_bp_attach".equals(name);Object evidence=args.get("evidence"),file=args.get("file");if(fill&&!(evidence instanceof Map))throw new IllegalArgumentException("缺少evidence对象");if(attach&&!(file instanceof Map))throw new IllegalArgumentException("缺少file对象");return agentProjectService.bp(id,agent,fill?(Map<String,Object>)evidence:null,(fill||attach)&&Boolean.TRUE.equals(args.get("confirmed")),attach?(Map<String,Object>)file:null);
        }
		if ("agent_projects_profile_get".equals(name) || "agent_projects_profile_fill".equals(name)) {
			String pendingId = args.getString("pendingId");
			if (StringUtils.isBlank(pendingId)) throw new IllegalArgumentException("缺少pendingId");
			boolean fill = "agent_projects_profile_fill".equals(name);
			Object evidence = args.get("evidence");
			if (fill && !(evidence instanceof Map)) throw new IllegalArgumentException("缺少evidence对象");
			return agentProjectService.profile(pendingId, agent, fill ? (Map<String,Object>)evidence : null, fill && Boolean.TRUE.equals(args.get("confirmed")));
		}
		if ("agent_projects_reject".equals(name)) {
			String pendingId = args.getString("pendingId");
			if (StringUtils.isBlank(pendingId)) {
				throw new IllegalArgumentException("缺少 pendingId");
			}
			String reason = args.getString("reason");
			return agentProjectService.reject(pendingId, agent, reason);
		}
		if ("agent_documents_search".equals(name)) {
			String q = args.getString("q");
			String projectId = first(args, "projectId", "project");
			if (StringUtils.isBlank(q) && StringUtils.isBlank(projectId)) {
				// s2d P2：不再静默走全库列表
				throw new IllegalArgumentException(MISSING_Q_MSG);
			}
			Integer page = args.getInteger("page");
			Integer pageSize = args.getInteger("pageSize");
			// s2-fix P2：返回 {items, indexing, partial, message?, indexPending?}，补抽未完成不静默
			return agentDocumentService.searchWithStatus(customerId, q, projectId, null, page == null ? 1 : page, pageSize == null ? 20 : pageSize);
		}
		if ("agent_documents_content".equals(name)) {
			String fileId = args.getString("fileId");
			if (StringUtils.isBlank(fileId)) {
				throw new IllegalArgumentException("缺少 fileId");
			}
			Integer maxChars = args.getInteger("maxChars");
			try {
				return agentDocumentService.readContent(customerId, fileId, maxChars == null ? 20000 : maxChars);
			} catch (RuntimeException e) {
				throw e;
			} catch (Exception e) {
				throw new IllegalStateException("读取文件正文失败", e);
			}
		}
		if ("agent_documents_pages".equals(name)) {
			String fileId = args.getString("fileId");
			if (StringUtils.isBlank(fileId)) {
				throw new IllegalArgumentException("缺少 fileId");
			}
			Object pages = args.get("pages");
			if (!(pages instanceof List)) {
				throw new IllegalArgumentException("pages 须为页码数组");
			}
			try {
				return agentDocumentService.readPages(customerId, fileId, (List<?>) pages);
			} catch (RuntimeException e) {
				throw e;
			} catch (Exception e) {
				throw new IllegalStateException("读取文档页面失败", e);
			}
		}
		if ("agent_portfolio_list".equals(name)) {
			return agentPortfolioService.listPortfolio(customerId, Boolean.TRUE.equals(args.getBoolean("afterInvestOnly")),
					args.getString("q"));
		}
		if ("agent_portfolio_quarterly".equals(name)) {
			return agentPortfolioService.quarterly(customerId, first(args, "projectId", "project"), args.getString("from"),
					args.getString("to"));
		}
		if ("agent_risk_alerts_create".equals(name)) {
			List<Map<String, Object>> sources = new ArrayList<Map<String, Object>>();
			JSONArray arr = args.getJSONArray("sources");
			if (arr != null) {
				for (int i = 0; i < arr.size(); i++) {
					if (arr.get(i) != null && !(arr.get(i) instanceof Map)) {
						throw new IllegalArgumentException("参数 sources 第 " + (i + 1) + " 项格式不对，应为对象");
					}
					JSONObject o = arr.getJSONObject(i);
					if (o != null) {
						sources.add(o);
					}
				}
			}
			return agentPortfolioService.createRiskAlert(customerId, str(agent.get("user_id")),
					first(args, "projectId", "project"), args.getString("theme"), args.getString("riskType"),
					first(args, "grade", "riskGrade"), first(args, "matters", "riskMatters"), args.getString("rule"),
					first(args, "conclusion", "evidence"), sources, Boolean.TRUE.equals(args.getBoolean("confirmed")),
					args.getString("state"), first(args, "eventDate", "riskDate"));
		}
		if ("agent_risk_alerts_list".equals(name)) {
			String projectId = first(args, "projectId", "project");
			String state = args.getString("state");
			return agentPortfolioService.listRiskAlerts(customerId, projectId, state);
		}
		if ("agent_dicts".equals(name)) {
			String type = args.getString("type");
			if (StringUtils.isBlank(type)) {
				throw new IllegalArgumentException("缺少 type");
			}
			return dictMapService.list(type);
		}
		throw new IllegalArgumentException("未知工具: " + name);
	}

	private static Map<String, Object> createAlertSchema() {
		Map<String, Object> sc = schema("projectId", "string", "项目 id（须属本租户）", true,
				"theme", "string", "事件主题（≤100 字；同项目同主题、Agent 写入且未关闭的预警视为重复）", true,
				"riskType", "string", "风险类型，服务端映射到网页字典 risk_type：财务→财务风险；公告/法律/合规/政策(policy)/监管→法律合规风险；舆情/突发→突发事项；业务→业务风险；指标→指标预警；重大变动；其他→其他风险。不在表内返回 INVALID_ARGUMENT、不写库", true,
				"grade", "string", "high|medium|low（按场景③分级表）", true,
				"rule", "string", "可选：命中的分级条款原文，如「营收同比降 ≥50%」（只在响应里回显，不写进意见结论；要写请放进 conclusion 正文）", false,
				"matters", "string", "风险事项摘要（≤255 字）", false,
				"conclusion", "string", "意见结论正文：只写结论摘要（必填，≤300 字，按字计）。不得含网址（http(s):// 或 www.）、「[n]」索引或「出处：」段——出处索引由服务端按 sources 生成拼在后面、不计 300；违规或超限返回 INVALID_ARGUMENT（提示正文上限 300 字与实际字数）、不写库", true,
				"evidence", "string", "旧参数名，等同 conclusion（只在未传 conclusion 时使用）", false,
				"state", "string", "可选：网页字典 risk_state 值（relieve|ignore|follow_up|alarm）；不传则留空（与网页新建一致）；字典外返回 INVALID_ARGUMENT", false,
				"eventDate", "string", "可选：风险发生日期（事件日期，YYYY-MM-DD），须等于某条出处的日期（外网发布日或财务报告期末）。不传：只有外网出处取最早发布日，只有财务出处取本期报告期末；外网+财务混合必须传。不符/晚于今天返回 INVALID_ARGUMENT、不写库", false,
				"confirmed", "boolean", "员工已逐条确认才传 true；否则拒绝且不写库", true);
		Map<String, Object> item = new LinkedHashMap<String, Object>();
		item.put("type", "object");
		Map<String, Object> ip = new LinkedHashMap<String, Object>();
		for (String[] f : new String[][] { { "title", "外网：来源标题" }, { "url", "外网：可打开的完整 http(s) 链接（ASCII、无空格，中文须百分号编码；原样进出处索引，不计正文 300 字）" },
				{ "date", "外网：发布日期（必填，YYYY-MM-DD；缺或不是有效日期返回 INVALID_ARGUMENT 不写库）" }, { "excerpt", "外网：≤200 字原文摘录" }, { "recordId", "财务：轻投记录 id" },
				{ "field", "财务：字段名" }, { "value", "财务：字段原值（必填，缺则返回 INVALID_ARGUMENT 不写库）；须与轻投库值一致（容格式差），不符返回 INVALID_ARGUMENT 不写库" }, { "formula", "财务：计算式" } }) {
			Map<String, Object> p = new LinkedHashMap<String, Object>();
			p.put("type", "string");
			p.put("description", f[1]);
			ip.put(f[0], p);
		}
		item.put("properties", ip);
		Map<String, Object> src = new LinkedHashMap<String, Object>();
		src.put("type", "array");
		src.put("description", "出处（至少 1 条）：外网 {title,url,date,excerpt}；财务 {recordId,field,value,formula}；同一事件多源并列");
		src.put("items", item);
		@SuppressWarnings("unchecked")
		Map<String, Object> props = (Map<String, Object>) sc.get("properties");
		props.put("sources", src);
		@SuppressWarnings("unchecked")
		List<String> req = (List<String>) sc.get("required");
		req.add("sources");
		return sc;
	}

	private static Map<String,Object> schemaString(String description){Map<String,Object> m=new LinkedHashMap<String,Object>();m.put("type","string");m.put("description",description);return m;}
	private static Map<String, Object> tool(String name, String description, Map<String, Object> inputSchema) {
		Map<String, Object> t = new LinkedHashMap<String, Object>();
		t.put("name", name);
		t.put("description", description);
		t.put("inputSchema", inputSchema);
		return t;
	}

	/** 变长 props: name,type,desc,required, name,type,desc,required, ... */
	private static Map<String, Object> schema(Object... props) {
		Map<String, Object> schema = new LinkedHashMap<String, Object>();
		schema.put("type", "object");
		Map<String, Object> properties = new LinkedHashMap<String, Object>();
		List<String> required = new ArrayList<String>();
		for (int i = 0; i + 3 < props.length; i += 4) {
			String pname = String.valueOf(props[i]);
			String ptype = String.valueOf(props[i + 1]);
			String pdesc = String.valueOf(props[i + 2]);
			boolean preq = Boolean.TRUE.equals(props[i + 3]) || "true".equalsIgnoreCase(String.valueOf(props[i + 3]));
			Map<String, Object> p = new LinkedHashMap<String, Object>();
			p.put("type", ptype);
			p.put("description", pdesc);
			properties.put(pname, p);
			if (preq) {
				required.add(pname);
			}
		}
		schema.put("properties", properties);
		if (!required.isEmpty()) {
			schema.put("required", required);
		}
		return schema;
	}

	private static Map<String, Object> rpcResult(Object id, Object result) {
		Map<String, Object> m = new LinkedHashMap<String, Object>();
		m.put("jsonrpc", "2.0");
		m.put("id", id);
		m.put("result", result);
		return m;
	}

	private static Map<String, Object> rpcError(Object id, int code, String message) {
		Map<String, Object> err = new LinkedHashMap<String, Object>();
		err.put("code", code);
		err.put("message", message);
		Map<String, Object> m = new LinkedHashMap<String, Object>();
		m.put("jsonrpc", "2.0");
		m.put("id", id);
		m.put("error", err);
		return m;
	}

	private static String str(Object o) {
		return o == null ? null : String.valueOf(o);
	}

	private static String first(JSONObject args, String... names) {
		for (String n : names) {
			String v = args.getString(n);
			if (StringUtils.isNotBlank(v)) {
				return v;
			}
		}
		return null;
	}
}
