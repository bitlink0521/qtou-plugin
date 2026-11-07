<cursor_untrusted_data_1337 source="CallDynamicTool">

package cn.qtou.api.modules.agent.service;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import cn.qtou.common.utils.StringUtils;
import cn.qtou.console.sys.entity.Area;
import cn.qtou.console.sys.entity.Dict;
import cn.qtou.console.sys.utils.AreaUtils;
import cn.qtou.console.sys.utils.DictUtils;
import cn.qtou.modules.projectpool.entity.SrvProjectPool;

public final class AgentEntryFields {
    static final Map<String, String> LABELS = new LinkedHashMap<String, String>();
    static {
        LABELS.put("projectLinkManName", "项目联系人|联系人姓名|联系人");
        LABELS.put("projectLinkManJob", "联系人职务|项目联系人职务");
        LABELS.put("projectLinkManContactWay", "联系人联系方式");
        LABELS.put("referenceManName", "推荐人|推荐人姓名|介绍人");
        LABELS.put("referenceManContactWay", "推荐人联系方式|介绍人联系方式");
        LABELS.put("expectFinancing", "预期融资金额|预期融资|融资需求金额");
        LABELS.put("communicateForm", "沟通形式|沟通方式");
        LABELS.put("productionAddress", "生产地址");
        LABELS.put("province", "所在省份|省份");
        LABELS.put("cityValue", "所在城市|城市");
        LABELS.put("primaryBusiness", "主营业务");
        LABELS.put("yewu", "一句话描述|业务描述");
        LABELS.put("hangye", "外部行业");
        LABELS.put("hangyeValue", "行业类型|所属行业|行业");
        LABELS.put("currency", "拟投资币种|融资币种|币种");
    }

    private AgentEntryFields() { }

    static List<Dict> dictionary(String key) {
        if ("hangyeValue".equals(key) && cn.qtou.console.customize.util.SwitchUtil.isOpened("projectPool:new:industry")) {
            List<Dict> options = new ArrayList<Dict>();
            for (cn.qtou.modules.sys.entity.Industry industry : cn.qtou.modules.sys.utils.IndustryUtils.getIndustryList()) {
                Dict option = new Dict();
                option.setLabel(industry.getName());
                option.setValue(industry.getCode());
                options.add(option);
            }
            return options;
        }
        return DictUtils.getDictList("hangyeValue".equals(key) ? "industryType" : "currency".equals(key) ? "currency_type" : "communicate_form");
    }

    static String dictionaryValue(String value, List<Dict> options) {
        String found = uniqueMatch(value, options, false);
        if (found == null) found = uniqueMatch(value, options, true);
        if (found == null) found = tokenMatch(value, options);
        if (found == null) throw new IllegalArgumentException("未匹配网页字典标签");
        return found;
    }

    /**
     * 网页行业字典是「生产|加工|制造」这种粗粒度大类：按「|」拆词，BP 写的值包含某个词（或反过来）即命中；
     * 只命中一个选项才算数，命中多个仍按不唯一处理。
     */
    static String tokenMatch(String value, List<Dict> options) {
        String wanted = normalize(value);
        if (wanted.length() < 2) return null;
        String found = null;
        for (Dict option : options) {
            boolean hit = false;
            for (String token : String.valueOf(option.getLabel()).split("\\|")) {
                token = normalize(token);
                if (token.length() >= 2 && (wanted.contains(token) || token.contains(wanted))) { hit = true; break; }
            }
            if (!hit) continue;
            if (found != null && !found.equals(option.getValue())) throw new IllegalArgumentException("字典标签不唯一");
            found = option.getValue();
        }
        return found;
    }

    static boolean dictionaryHasValue(String type, String value) {
        for (Dict option : DictUtils.getDictList(type)) if (value.equals(option.getValue())) return true;
        return false;
    }

    static String areaValue(String value, List<Area> options) {
        String found = uniqueMatch(value, options, false);
        // BP 常写「上海」「广东」，地区表是「上海市」「广东省」：精确匹配不上时去掉行政区后缀再比，仍须唯一
        if (found == null) found = uniqueMatch(value, options, true);
        if (found == null) found = compoundArea(value, options);
        if (found == null) throw new IllegalArgumentException("未匹配地区，请提供完整地区名称");
        return found;
    }

    /** 用户常连写「北京市海淀区」「江苏省苏州市」：取名称是结尾的那一级，且前缀里要出现它的上级，仍须唯一。 */
    static String compoundArea(String value, List<Area> options) {
        Map<String, Area> byId = new HashMap<String, Area>();
        for (Area area : options) if (area.getId() != null) byId.put(area.getId(), area);
        String found = null;
        for (Area area : options) {
            String name = area.getName();
            if (name == null || name.length() < 2 || value.equals(name) || !value.endsWith(name)) continue;
            String prefix = normalize(value.substring(0, value.length() - name.length()));
            boolean ancestorNamed = false;
            Area parent = area.getParent() == null ? null : byId.get(area.getParent().getId());
            for (int depth = 0; parent != null && depth < 5 && !ancestorNamed; depth++) {
                String parentName = normalize(parent.getName());
                ancestorNamed = !parentName.isEmpty() && prefix.contains(parentName);
                parent = parent.getParent() == null ? null : byId.get(parent.getParent().getId());
            }
            if (!ancestorNamed) continue;
            if (found != null && !found.equals(area.getId())) throw new IllegalArgumentException("地区名称不唯一");
            found = area.getId();
        }
        return found;
    }

    /** 沟通方式字典只有「会面/电话/BP」，用户说法五花八门：先归到字典标签再匹配。 */
    static String communicateSynonym(String value) {
        if (value.matches(".*(会面|见面|面谈|面聊|线下|拜访|会议|现场|路演).*")) return "会面";
        if (value.matches(".*(电话|通话|电联|语音).*")) return "电话";
        if (value.matches("(?i).*(BP|商业计划书|计划书).*")) return "BP";
        return value;
    }

    private static final String AREA_SUFFIX = "(特别行政区|维吾尔自治区|壮族自治区|回族自治区|自治区|自治州|省|市|县|区|行业)$";

    static String normalize(String name) {
        return name == null ? "" : name.trim().replaceAll(AREA_SUFFIX, "");
    }

    private static String uniqueMatch(String value, List<?> options, boolean loose) {
        String wanted = loose ? normalize(value) : value;
        if (wanted.isEmpty()) return null;
        String found = null;
        for (Object option : options) {
            String label = option instanceof Area ? ((Area) option).getName() : ((Dict) option).getLabel();
            String id = option instanceof Area ? ((Area) option).getId() : ((Dict) option).getValue();
            if (!wanted.equals(loose ? normalize(label) : label)) continue;
            if (found != null && !found.equals(id)) throw new IllegalArgumentException(option instanceof Area ? "地区名称不唯一" : "字典标签不唯一");
            found = id;
        }
        return found;
    }

    static Map<String, Object> extract(Map<String, String> fields) {
        Map<String, Object> values = new LinkedHashMap<String, Object>();
        for (Map.Entry<String, String> spec : LABELS.entrySet()) {
            for (String label : (spec.getValue() + "|" + spec.getKey()).split("\\|")) {
                String value = fields.get(label.toLowerCase(java.util.Locale.ROOT));
                if (StringUtils.isNotBlank(value)) {
                    values.put(spec.getKey(), value);
                    break;
                }
            }
        }
        return values;
    }

    static String productionAreas(String value, List<Area> options) {
        java.util.Set<String> ids = new java.util.LinkedHashSet<String>();
        for (String name : value.split("[,，、]")) ids.add(areaValue(name.trim(), options));
        return String.join(",", ids);
    }

    static Object convert(String key, String value) {
        if (StringUtils.isBlank(value) || value.matches("(?s).*<[/!]?[A-Za-z].*"))
            throw new IllegalArgumentException("值为空或包含HTML");
        if ("expectFinancing".equals(key)) {
            java.util.regex.Matcher amount = java.util.regex.Pattern.compile("^([0-9]+(?:\\.[0-9]+)?)(万元|亿元|元)$").matcher(value);
            if (!amount.matches()) throw new IllegalArgumentException("金额须明确元、万元或亿元，不接受区间或推测");
            BigDecimal number = new BigDecimal(amount.group(1));
            if ("亿元".equals(amount.group(2))) number = number.multiply(new BigDecimal("10000"));
            if ("元".equals(amount.group(2))) number = number.divide(new BigDecimal("10000"));
            if (number.precision() > 15) throw new IllegalArgumentException("金额超出范围");
            return number;
        }
        if ("communicateForm".equals(key)) value = communicateSynonym(value);
        String dictionary = "currency".equals(key) ? "currency_type" : "communicateForm".equals(key) ? "communicate_form" : "hangyeValue".equals(key) ? "industryType" : null;
        if (dictionary != null) {
            return dictionaryValue(value, dictionary(key));
        }
        if ("province".equals(key) || "cityValue".equals(key)) {
            return areaValue(value, "province".equals(key) ? AreaUtils.getAllProvinceList() : AreaUtils.getAreaList());
        }
        if ("productionAddress".equals(key)) return productionAreas(value, AreaUtils.getAreaList());
        int limit = "yewu".equals(key) ? 30 : "primaryBusiness".equals(key) ? 1000 : 255;
        if (value.length() > limit) throw new IllegalArgumentException("字段超过长度限制" + limit);
        return value;
    }

    static Map<String, Object> apply(SrvProjectPool pool, Map<?, ?> proposed) {
        BeanWrapper bean = new BeanWrapperImpl(pool);
        Map<String, Object> issues = new LinkedHashMap<String, Object>();
        for (String key : LABELS.keySet()) {
            Object value = proposed.get(key);
            if (value == null || StringUtils.isBlank(String.valueOf(value)) || !empty(bean.getPropertyValue(key))) continue;
            try {
                bean.setPropertyValue(key, convert(key, String.valueOf(value).trim()));
            } catch (IllegalArgumentException invalid) {
                issues.put(key, invalid.getMessage());
            }
        }
        return issues;
    }

    static boolean empty(Object value) {
        return value == null || StringUtils.isBlank(String.valueOf(value));
    }

    static Map<String, Object> summary(SrvProjectPool pool) {
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        Map<String, Object> values = new LinkedHashMap<String, Object>();
        List<String> missing = new ArrayList<String>();
        BeanWrapper bean = new BeanWrapperImpl(pool);
        for (String key : LABELS.keySet()) {
            Object value = bean.getPropertyValue(key);
            values.put(key, value);
            if (empty(value)) missing.add(key);
        }
        for (String key : new String[] {"logo", "isAutoGenerate", "outsiteProjectId", "outsiteProduct"}) {
            Object value = bean.getPropertyValue(key);
            values.put(key, value);
            if (empty(value)) missing.add(key);
        }
        result.put("fields", values);
        result.put("missingFields", missing);
        result.put("logoStatus", empty(pool.getLogo()) ? "not_filled" : "0".equals(pool.getIsAutoGenerate()) ? "placeholder" : "real");
        return result;
    }
}


</cursor_untrusted_data_1337>