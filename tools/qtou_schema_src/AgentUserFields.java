<cursor_untrusted_data_1337 source="CallDynamicTool">

package cn.qtou.api.modules.agent.service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.BeanWrapperImpl;
import cn.qtou.modules.projectpool.entity.SrvProjectPool;

final class AgentUserFields {
    static final List<String> KEYS = java.util.Collections.unmodifiableList(Arrays.asList(
            "projectLinkManName", "projectLinkManJob", "projectLinkManContactWay",
            "referenceManName", "referenceManContactWay", "communicateForm",
            "productionAddress", "expectFinancing", "currency"));

    private AgentUserFields() { }

    static String normalize(String value) {
        return value == null ? "" : value.replaceAll("[\\s\\p{Z}]+", " ").trim();
    }

    static List<Map<String, Object>> ask(Map<?, ?> values) {
        List<Map<String, Object>> result = new ArrayList<Map<String, Object>>();
        for (String key : KEYS) if (AgentEntryFields.empty(values.get(key))) {
            Map<String, Object> item = new LinkedHashMap<String, Object>();
            item.put("property", key);
            item.put("label", AgentEntryFields.LABELS.get(key).split("\\|")[0]);
            item.put("why", "BP与公开资料一般没有，需要你告知");
            result.add(item);
        }
        return result;
    }

    static Map<String, Object> values(SrvProjectPool pool) {
        Map<String, Object> values = new LinkedHashMap<String, Object>();
        org.springframework.beans.BeanWrapper bean = new BeanWrapperImpl(pool);
        for (String key : KEYS) values.put(key, bean.getPropertyValue(key));
        return values;
    }

    static Map<String, Object> map(String statement, Map<?, ?> fields, boolean overwrite,
            Map<?, ?> existing, Map<String, Object> issues) {
        if (statement == null || statement.length() < 2 || statement.length() > 2000 || normalize(statement).length() < 2)
            throw new IllegalArgumentException("statement须为用户原话，长度2至2000字符");
        if (fields == null || fields.isEmpty()) throw new IllegalArgumentException("fields须为非空对象");
        if (overwrite && !java.util.regex.Pattern.compile("(?:^|[，。；,;！!\\n])\\s*(?:我)?(?:明确)?(?:请|同意|允许|确认)(?:覆盖|替换|修改|更新)(?:已有|现有|原有)?(?:字段|值|信息|内容)").matcher(statement).find())
            throw new IllegalArgumentException("覆盖须由用户原话明确授权，例如：同意覆盖已有字段");
        Map<String, Object> mapped = new LinkedHashMap<String, Object>();
        for (Map.Entry<?, ?> entry : fields.entrySet()) {
            String key = String.valueOf(entry.getKey());
            if (!KEYS.contains(key)) { issues.put(key, "不在用户字段白名单"); continue; }
            if (!(entry.getValue() instanceof String) && !(entry.getValue() instanceof Number)) {
                issues.put(key, "值须为文字或数字"); continue;
            }
            String value = normalize(String.valueOf(entry.getValue()));
            if (value.isEmpty() || !normalize(statement).contains(value)) {
                issues.put(key, "值未逐字出现在用户原话中"); continue;
            }
            try {
                Object converted = AgentEntryFields.convert(key, value);
                if (overwrite || AgentEntryFields.empty(existing.get(key))) mapped.put(key, converted);
            } catch (IllegalArgumentException invalid) { issues.put(key, invalid.getMessage()); }
        }
        return mapped;
    }
}


</cursor_untrusted_data_1337>