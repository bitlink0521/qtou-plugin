<cursor_untrusted_data_1337 source="CallDynamicTool">

package cn.qtou.api.modules.agent.service;
import java.util.*;
import java.math.BigDecimal;
import java.time.*;
import java.security.MessageDigest;
import javax.annotation.PostConstruct;
import javax.sql.DataSource;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import cn.qtou.console.sys.entity.Dict;
import cn.qtou.console.sys.entity.Area;
import cn.qtou.console.sys.utils.DictUtils;
import cn.qtou.console.sys.utils.AreaUtils;
import cn.qtou.modules.company.entity.BasicCompany;
import cn.qtou.modules.company.entity.CompanyExtendInfo;
import cn.qtou.modules.company.service.BasicCompanyService;
import cn.qtou.modules.company.service.CompanyExtendInfoService;
import cn.qtou.modules.projectpool.entity.SrvProjectPool;
import cn.qtou.modules.projectpool.service.SrvProjectPoolService;

/** BP structured intake: explicit field catalog, source verification, missing-only writes. */
@Service
public class AgentBpService {
 @Autowired private DataSource dataSource;
 @Autowired private AgentEntryEnrichment entryEnrichment;
 @Autowired private SrvProjectPoolService projects;
 @Autowired private BasicCompanyService companies;
 @Autowired private CompanyExtendInfoService extensions;
 @Autowired private AgentBpCollections collections;
 @Autowired private AgentProjectLogoSentinel logoSentinel;
 private JdbcTemplate jdbc;
 @PostConstruct public void init(){jdbc=new JdbcTemplate(dataSource);jdbc.execute("CREATE TABLE IF NOT EXISTS agent_bp_audit (id varchar(32) PRIMARY KEY, customer_id varchar(64) NOT NULL, pending_id varchar(64) NOT NULL, project_id varchar(64), operation varchar(32) NOT NULL, evidence_json MEDIUMTEXT, result_json MEDIUMTEXT, create_date datetime NOT NULL, KEY idx_agent_bp_pending(customer_id,pending_id,create_date)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");}
 private static final Map<String,Map<String,Object>> FIELDS=new LinkedHashMap<String,Map<String,Object>>();
 /* 原系统把这几列挪作股票代码、清华成果转化（技术名称/院系/头衔）和访谈记录，BP里没有对应内容 */
 static final List<String> NOT_FROM_BP=Arrays.asList("project.serviceObject","project.productPositioning","project.differentiation","project.userCost","project.majorRevision");
 private static void add(String scope,String key,String label,String type,String dict){FIELDS.put(scope+"."+key,obj("field",scope+"."+key,"property",key,"scope",scope,"label",label,"type",type,"dictionary",dict,"writeMode","missing_only","uiVisibility","由租户开关决定；字段仍可发现并回读"));}
 static {
        add("project","projectName","项目名称","text","");
        add("project","projectShorthand","项目简称","text","");
        add("project","companyNameEnglish","项目英文名称","text","");
        add("project","introduction","项目简介","text","");
        add("project","introductionEnglish","英文简介","text","");
        add("project","primaryBusiness","主营业务","text","");
        add("project","yewu","一句话描述","text","");
        add("project","businessModel","商业模式","text","");
        add("project","investmentHighlight","投资亮点","text","");
        add("project","highlight","highlight","text","");
        add("project","insufficient","不足","text","");
        add("project","techRemarks","核心技术介绍","text","");
        add("project","teamBackGround","团队背景","text","");
        add("project","existingInvestors","已有投资方","text","");
        add("project","financialSituation","财务状况","text","");
        add("project","investmentLogic","投资逻辑","text","");
        add("project","serviceObject","技术名称","text","");
        add("project","productPositioning","院系","text","");
        add("project","differentiation","股票代码","text","");
        add("project","userCost","头衔","text","");
        add("project","majorRevision","访谈记录","text","");
        add("project","industrySituation","行业/竞品情况及地位","text","");
        add("project","competingProducts","竞品","text","");
        add("project","performanceIntroduce","主创职务","text","");
        add("project","mainCreationSummary","主创简介","text","");
        add("project","mainCreationRemarks","主创备注","text","");
        add("project","talent","人才","text","");
        add("project","consumerInsight","用户洞察","text","");
        add("project","model","模式","text","");
        add("project","marketIntelligence","市场信息","text","");
        add("project","honour","荣誉","text","");
        add("project","projectLinkManName","项目联系人","text","");
        add("project","projectLinkManJob","联系人职务","text","");
        add("project","projectLinkManContactWay","联系人联系方式","text","");
        add("project","referenceManName","推荐人姓名","text","");
        add("project","referenceManContactWay","推荐人联系方式","text","");
        add("project","communicateForm","沟通形式","dict","communicate_form");
        add("project","hangye","外部行业","text","");
        add("company","tags","企业标签","text","");
        add("project","productionAddress","生产所在地（完整地区名称，多个用逗号分隔）","text","");
        add("project","financingNeeds","未来融资需求","text","");
        add("project","otherSituations","其他情况","text","");
        add("project","fixedAssets","固定资产说明","text","");
        add("company","name","公司名称","text","");
        add("company","abbreviation","公司简称","text","");
        add("company","juridicalPerson","法人代表","text","");
        add("company","registrationAuthority","登记机关","text","");
        add("company","sociaCreditCode","统一社会信用代码","text","");
        add("company","registeredAddress","注册地址","text","");
        add("company","englishName","公司英文名称","text","");
        add("companyInfo","companyWebsite","公司网址","text","");
        add("companyInfo","officeAddress","办公地址","text","");
        add("companyInfo","contactNumber","联系电话","text","");
        add("companyInfo","companyMailbox","公司邮箱","text","");
        add("companyInfo","companyProfile","公司简介","text","");
        add("companyInfo","officialAccounts","公众号","text","");
        add("companyInfo","contacts","联系人","text","");
        add("companyInfo","contactJob","联系人职务","text","");
        add("companyInfo","honour","企业荣誉","text","");
        add("project","hangyeClass","行业一级分类","text","");
        add("project","projectArea","项目地区","text","");
        add("project","income","营收描述","text","");
        add("project","profit","利润描述","text","");
        add("project","stockCode","股票代码","text","");
        add("project","currentPrice","现价","text","");
        add("project","financialReportDeadline","财报截止日","text","");
        add("project","onlineTime","设立日期","date","");
        add("project","county","所在县区","region","");
        add("project","netProfit","净利润（万元）","decimal","");
        add("project","totalIncome","总营收（万元）","decimal","");
        add("project","isFirst","是否首次融资","dict","yes_no");
        add("project","isNewIndustry","是否战略新兴产业","dict","isNewIndustry");
        add("project","is522Enterprise","是否522企业","dict","yes_no");
        add("project","projectStage","项目所处阶段","dict","project_stage1");
        add("project","curInvestRound","当前轮次","dict","invest_round");
        add("project","industryType","细分领域","dict","industry_type");
        add("project","hangyeValue","行业类型","dict","industryType");
        add("project","isListing","是否上市","dict","isListing");
        add("project","isTeamHold","团队是否控股","dict","is_team_hold");
        add("project","cityValue","所在城市","region","");
        add("project","province","所在省份","province","");
        add("project","currency","拟投资币种","dict","currency_type");
        add("project","expectFinancing","预期融资金额（万元）","decimal","");
        add("project","valuation","估值（万元）","decimal","");
        add("company","registeredCapital","注册资本（万元）","capital","");
        add("company","foundingTime","成立日期","date","");
        add("company","state","经营状态","dict","registration_status");
        add("company","type","工商注册类型","dict","company_type");
        add("company","registeredCurrency","注册资本币种","dict","capital");
        add("company","currency","缺省币种","dict","capital");
        add("company","province","省份地区","province","");
        add("companyInfo","staffNumber","员工人数","integer","");
        add("companyInfo","nature","公司性质","dict","company_attribute");
        add("companyInfo","isMinorEnterprises","是否中小企业","dict","isMinorEnterprises");
        add("companyInfo","isHighNewEnterprises","是否高新企业","dict","isHighNewEnterprises");
        add("companyInfo","highNewDate","高新企业资质有效日期","date","");
        add("companyInfo","cognizanceDate","认定日期","date","");
 }
 static Map<String,Object> obj(Object... pairs){Map<String,Object> out=new LinkedHashMap<String,Object>();for(int i=0;i<pairs.length;i+=2)out.put((String)pairs[i],pairs[i+1]);return out;}
 static String s(Object x){return x==null?"":String.valueOf(x).trim();}
 static String norm(Object x){return s(x).replaceAll("\\s+","").replace('（','(').replace('）',')');}
 static Map map(Object x){if(!(x instanceof Map))throw new IllegalArgumentException("BP对象格式错误");return (Map)x;}
 static List list(Object x){if(x==null)return Collections.emptyList();if(!(x instanceof List))throw new IllegalArgumentException("BP数组格式错误");return (List)x;}
 static void check(boolean ok,String why){if(!ok)throw new IllegalArgumentException("BP信息："+why);}
 static boolean empty(Object x){return x==null||(x instanceof String&&s(x).isEmpty());}
 static String hash(String x){try{byte[] data=MessageDigest.getInstance("SHA-256").digest(x.getBytes("UTF-8"));StringBuilder b=new StringBuilder();for(byte y:data)b.append(String.format("%02x",y&255));return b.toString();}catch(Exception ex){throw new IllegalStateException("摘要计算失败");}}

 // Schema nodes must not share identities: Fastjson would emit non-JSON-Schema $ref paths.
 private static Object schemaTree(Object value){
  if(value instanceof Map){Map<String,Object> copy=new LinkedHashMap<String,Object>();for(Object raw:((Map)value).entrySet()){Map.Entry e=(Map.Entry)raw;copy.put(String.valueOf(e.getKey()),schemaTree(e.getValue()));}return copy;}
  if(value instanceof List){List<Object> copy=new ArrayList<Object>();for(Object item:(List)value)copy.add(schemaTree(item));return copy;}return value;
 }
 private static Map<String,Object> object(Map<String,Object> properties,String...required){return obj("type","object","properties",properties,"required",Arrays.asList(required),"additionalProperties",false);}
 private static Map<String,Object> array(Map items){return obj("type","array","items",items);}
 public static Map<String,Object> evidenceSchema(){
  Map ref=object(obj("page",obj("type","integer","minimum",1),"quote",obj("type","string","minLength",5,"maxLength",4000)),"page","quote");Map refs=array(ref);
  Map<String,Object> temporal=obj("nature",obj("type","string","enum",Arrays.asList("historical_fact","plan","forecast","current_fact")),"asOf",obj("type","string","description","与document.asOf相同的披露时点；document.asOf为空时也留空"),"sources",refs);
  Map<String,Object> field=new LinkedHashMap<String,Object>(temporal);field.put("field",obj("type","string","enum",new ArrayList<String>(FIELDS.keySet())));field.put("value",obj("type","string","description","金额必须标明万元；字典传标签；无证据不提供"));field.put("mode",obj("type","string","enum",Arrays.asList("fill_missing","append_evidence"),"description","默认fill_missing；append_evidence只允许描述字段补充遗漏证据，保留原文并去重，须已有补全授权"));
  Map<String,Object> team=new LinkedHashMap<String,Object>(temporal);for(String k:Arrays.asList("name","jop","introduction","education","workExperience","exclusiveResources","telephone","weChat","businessJob"))team.put(k,obj("type","string"));team.put("stockRate",obj("type","number","minimum",0,"maximum",100));team.put("seatNum",obj("type","integer","minimum",0,"maximum",100));
  Map<String,Object> finance=new LinkedHashMap<String,Object>(temporal);finance.put("historyFinancing",obj("type","string","description","带历史时间及事实/计划性质，不将预测写实际财务"));
  Map<String,Object> competitor=new LinkedHashMap<String,Object>(temporal);competitor.put("name",obj("type","string"));competitor.put("description",obj("type","string"));
  Map page=object(obj("page",obj("type","integer","minimum",1),"text",obj("type","string")),"page","text");
  Map document=object(obj("name",obj("type","string"),"asOf",obj("type","string","description","BP披露日期YYYY-MM或YYYY-MM-DD；材料未注明时留空，不用文件导出日期冒充"),"pages",array(page)),"name","pages");
  return (Map<String,Object>)schemaTree(object(obj("schemaVersion",obj("type","integer","enum",Arrays.asList(1)),"reviewed",obj("type","boolean","enum",Arrays.asList(true)),"document",document,"fields",array(object(field,"field","value","nature","asOf","sources")),"team",array(object(team,"name","nature","asOf","sources")),"financing",array(object(finance,"historyFinancing","nature","asOf","sources")),"competitors",array(object(competitor,"name","nature","asOf","sources"))),"schemaVersion","reviewed","document"));
 }
 public String audit(String tenant,String pendingId,String projectId,String operation,Map evidence,Map result){String id=java.util.UUID.randomUUID().toString().replace("-","");jdbc.update("INSERT INTO agent_bp_audit(id,customer_id,pending_id,project_id,operation,evidence_json,result_json,create_date) VALUES(?,?,?,?,?,?,?,?)",id,tenant,pendingId,projectId,operation,evidence==null?null:cn.qtou.common.mapper.JsonMapper.toJsonString(evidence),result==null?null:cn.qtou.common.mapper.JsonMapper.toJsonString(result),new java.util.Date());return id;}
 public Map<String,Object> source(String tenant,String pendingId,String id){List<Map<String,Object>> rows=jdbc.queryForList("SELECT id,evidence_json FROM agent_bp_audit WHERE customer_id=? AND pending_id=? AND evidence_json IS NOT NULL AND operation<>'user_fields'"+(id==null?" ORDER BY create_date DESC,id DESC LIMIT 1":" AND id=?"),id==null?new Object[]{tenant,pendingId}:new Object[]{tenant,pendingId,id});check(!rows.isEmpty(),"BP原文证据不存在");return (Map)net.sf.json.JSONObject.fromObject(rows.get(0).get("evidence_json"));}
 public Map<String,Object> catalog(){
  List<Map<String,Object>> all=new ArrayList<Map<String,Object>>();
  for(Map<String,Object> f:FIELDS.values()){Map<String,Object> c=new LinkedHashMap<String,Object>(f);String dt=s(f.get("dictionary"));if(Arrays.asList("project.highlight","project.stockCode","project.currentPrice").contains(s(f.get("field")))){c.put("writeMode","read_only_derived");c.put("reason","原实体派生字段不在主表保存映射；BP原文和建议保留在审计；亮点请用project.investmentHighlight");}if(NOT_FROM_BP.contains(s(f.get("field")))){c.put("writeMode","not_from_bp");c.put("reason","网页上这一列是「"+f.get("label")+"」，由人工维护，不从BP推定");}if(!dt.isEmpty()){List<Map<String,Object>> opts=new ArrayList<Map<String,Object>>();for(Dict d:"project.hangyeValue".equals(s(f.get("field")))?AgentEntryFields.dictionary("hangyeValue"):DictUtils.getDictList(dt))opts.add(obj("value",d.getValue(),"label",d.getLabel()));c.put("options",opts);}all.add(c);}
  return obj("schemaVersion",1,"inputSchema",evidenceSchema(),"fields",all,"collections",collections.catalog(),"managementFields",Arrays.asList("projectNumber","projectStatus","projectType","source","specificSource","referrer","members","proposedInvestment","preliminarily","projectScore","ourDirector","ourSupervisor","isAfterInvest","permissions"),"managementWritePolicy","内部编号、工作流、我方投资判断、权限不从BP推定；现有人工流程设置", "evidenceContract",obj("document",obj("name","文件名","asOf","YYYY-MM或YYYY-MM-DD","pages","[{page:1,text:原文}]"),"fields","[{field:project.businessModel,value:文字,nature:historical_fact|plan|forecast|current_fact,asOf:YYYY-MM,sources:[{page:9,quote:连续原文}]}]","team","[{name,jop,education,workExperience,introduction,asOf,nature,sources}]","financing","[{historyFinancing,asOf,nature,sources}]","reviewed","须人工或AI完成语义审核后true；服务端另核原文", "preview","confirmed=false零业务写入；confirmed=true仅补空值"));
 }
 public void validate(Map evidence,String companyName){
  check(!norm(companyName).isEmpty(),"缺少确认的公司主体");check("1".equals(s(evidence.get("schemaVersion"))),"schemaVersion须为1");check(Boolean.TRUE.equals(evidence.get("reviewed")),"必须先完成事实/历史/预测审核");
  Map doc=map(evidence.get("document"));check(!s(doc.get("name")).isEmpty(),"缺少BP名称");String date=s(doc.get("asOf"));/* 很多BP不写披露日期，网页入库也不要求；没写就记为未注明，只有当前事实与近期融资计划须带日期 */if(!date.isEmpty()){check(date.matches("\\d{4}-\\d{2}(-\\d{2})?"),"BP日期须YYYY-MM或YYYY-MM-DD");LocalDate when=LocalDate.parse(date.length()==7?date+"-01":date);check(!when.isAfter(LocalDate.now()),"BP日期不能晚于今天");}
  Map<Integer,String> pages=new LinkedHashMap<Integer,String>();int size=0;
  for(Object raw:list(doc.get("pages"))){Map p=map(raw);int page=Integer.parseInt(s(p.get("page")));String text=s(p.get("text"));check(page>0&&!pages.containsKey(page)&&!text.isEmpty(),"页码重复、正文空或页码无效");size+=text.length();check(size<=2000000,"BP正文超过200万字");pages.put(page,text);}
  check(!pages.isEmpty(),"缺少BP逐页正文");String combined=String.join("\n",pages.values());check(norm(combined).contains(norm(companyName)),"BP正文公司主体不匹配");
  Set<String> known=new HashSet<String>();
  for(Object raw:list(evidence.get("fields"))){Map r=map(raw);String field=s(r.get("field"));check(s(r.get("mode")).isEmpty()||Arrays.asList("fill_missing","append_evidence").contains(s(r.get("mode"))),"未知字段写入mode");check(FIELDS.containsKey(field)&&known.add(field),"未知或重复字段："+field);proof(r,pages,date);String property=s(FIELDS.get(field).get("property"));if(Arrays.asList("name","abbreviation","juridicalPerson","registrationAuthority","sociaCreditCode","registeredAddress","englishName","foundingTime","contactNumber","companyMailbox","contacts","contactJob","projectLinkManName","projectLinkManJob","projectLinkManContactWay","referenceManName","referenceManContactWay","productionAddress","communicateForm","expectFinancing","currency","province","cityValue","tags","isHighNewEnterprises").contains(property)){StringBuilder quoted=new StringBuilder();for(Object ref:list(r.get("sources")))quoted.append(s(map(ref).get("quote")));check(norm(quoted).contains(norm(r.get("value"))),"主体/联系字段值未在引文中出现："+field);}}
  for(String key:Arrays.asList("team","financing","competitors"))for(Object raw:list(evidence.get(key))){Map r=map(raw);proof(r,pages,date);if("team".equals(key)){StringBuilder quoted=new StringBuilder();for(Object ref:list(r.get("sources")))quoted.append(s(map(ref).get("quote")));check(!s(r.get("name")).isEmpty()&&norm(quoted).contains(norm(r.get("name"))),"团队姓名未在引文中出现");}}
 }
 private static void proof(Map row,Map<Integer,String> pages,String date){
  String nature=s(row.get("nature"));check(Arrays.asList("historical_fact","plan","forecast","current_fact").contains(nature),"必须区分事实、计划、预测");check(date.equals(s(row.get("asOf"))),"披露时点与BP不一致");List refs=list(row.get("sources"));check(!refs.isEmpty(),"缺少逐字段页码原文");
  for(Object raw:refs){Map p=map(raw);int page=Integer.parseInt(s(p.get("page")));String quote=s(p.get("quote"));check(quote.length()>=5&&quote.length()<=4000&&pages.containsKey(page)&&norm(pages.get(page)).contains(norm(quote)),"页码或摘录与BP原文不一致");}
 }
 private Map<String,BeanWrapper> beans(SrvProjectPool pool){
  BasicCompany c=pool.getBasicCompany();check(c!=null&&!empty(c.getId()),"项目未关联公司");c=companies.get(c.getId());CompanyExtendInfo ext=c.getCompanyExtendInfo();if(ext!=null&&!empty(ext.getId()))ext=extensions.get(ext.getId());if(ext==null){ext=new CompanyExtendInfo();ext.setCompanyId(c.getId());}
  Map<String,BeanWrapper> out=new LinkedHashMap<String,BeanWrapper>();out.put("project",new BeanWrapperImpl(pool));out.put("company",new BeanWrapperImpl(c));out.put("companyInfo",new BeanWrapperImpl(ext));return out;
 }
 public Map<String,Object> get(String projectId,String tenant){SrvProjectPool pool=load(projectId,tenant,false);Map<String,BeanWrapper> b=beans(pool);List<Map<String,Object>> fields=new ArrayList<Map<String,Object>>();for(Map<String,Object> f:FIELDS.values()){BeanWrapper bean=b.get(f.get("scope"));String k=s(f.get("property"));Map<String,Object> r=new LinkedHashMap<String,Object>(f);r.put("value",bean.isReadableProperty(k)?bean.getPropertyValue(k):null);r.put("status",bean.isReadableProperty(k)?empty(bean.getPropertyValue(k))?"missing":"present":"unsupported");fields.add(r);}return obj("projectId",projectId,"companyId",pool.getBasicCompany().getId(),"logo",pool.getLogo(),"isAutoGenerate",pool.getIsAutoGenerate(),"fields",fields,"entryCompleteness",AgentEntryFields.summary(pool),"collections",collections.get(pool));}
 private SrvProjectPool load(String projectId,String tenant,boolean lock){check(!jdbc.queryForList("SELECT id FROM qsrv_project_pool WHERE id=? AND customer_id=? AND del_flag='0'"+(lock?" FOR UPDATE":""),projectId,tenant).isEmpty(),"项目不存在或不属于当前租户");SrvProjectPool p=projects.get(projectId);check(p!=null,"项目不存在");check(!jdbc.queryForList("SELECT id FROM biz_company WHERE id=? AND customer_id=? AND del_flag='0'"+(lock?" FOR UPDATE":" LOCK IN SHARE MODE"),p.getBasicCompany().getId(),tenant).isEmpty(),"公司不属于当前租户");return p;}
 public Map<String,Object> fill(String projectId,String companyName,String tenant,Map evidence,boolean apply){
  validate(evidence,companyName);Set<String> pageTexts=new HashSet<String>();for(Object p:list(map(evidence.get("document")).get("pages")))pageTexts.add(norm(map(p).get("text")));Map<String,Integer> valueUses=new HashMap<String,Integer>();for(Object raw:list(evidence.get("fields"))){String v=norm(map(raw).get("value"));if(v.length()>=30)valueUses.put(v,valueUses.containsKey(v)?valueUses.get(v)+1:1);}
  SrvProjectPool pool=load(projectId,tenant,apply);check(norm(pool.getCompanyName()).equals(norm(companyName)),"项目公司主体不一致");Map<String,BeanWrapper> beans=beans(pool);Set<String> changed=new HashSet<String>();List<Map<String,Object>> out=new ArrayList<Map<String,Object>>();
  for(Object raw:list(evidence.get("fields"))){Map r=map(raw);String key=s(r.get("field"));Map<String,Object> spec=FIELDS.get(key);String scope=s(spec.get("scope")),property=s(spec.get("property"));BeanWrapper bean=beans.get(scope);Object old=bean.getPropertyValue(property);Map<String,Object> result=obj("field",key,"label",spec.get("label"),"before",old,"sources",r.get("sources"),"nature",r.get("nature"),"asOf",r.get("asOf"));
   if(!empty(old)&&"append_evidence".equals(s(r.get("mode")))){
    Set<String> appendable=new HashSet<String>(Arrays.asList("project.techRemarks","project.teamBackGround","project.industrySituation","project.mainCreationRemarks","project.talent","project.consumerInsight","project.model","project.marketIntelligence","project.honour","project.financialSituation","project.financingNeeds","project.otherSituations","companyInfo.honour","companyInfo.companyProfile"));check(appendable.contains(key),"字段不允许追加证据："+key);copyCheck(s(r.get("value")),pageTexts,valueUses);String addition=s(convert(spec,r));String value=norm(old).contains(norm(addition))?s(old):s(old)+"\n"+addition;check(value.length()<=1000,"追加后超过字段1000字上限");result.put("value",value);boolean modified=!value.equals(s(old));result.put("status",modified?(apply?"filled":"ready"):"preserved");if(apply&&modified){bean.setPropertyValue(property,value);changed.add(scope);}
   }else if(!empty(old)){result.put("status","preserved");result.put("value",old);}else{
    try{check(!Arrays.asList("project.highlight","project.stockCode","project.currentPrice").contains(key),"原实体派生字段无保存映射；已保留BP证据，不伪称写入");check(!NOT_FROM_BP.contains(key),"网页上这一列是「"+spec.get("label")+"」，不从BP写入");copyCheck(s(r.get("value")),pageTexts,valueUses);Object value=convert(spec,r);result.put("value",value);result.put("status",apply?"filled":"ready");if(apply){bean.setPropertyValue(property,value);changed.add(scope);}}catch(IllegalArgumentException ex){result.put("status","needs_verification");result.put("reason",ex.getMessage());}
   }out.add(result);
  }
  Map<String,Object> child=collections.apply(pool,evidence,apply);
  Map<String,Object> enrichment=new LinkedHashMap<String,Object>();
  if(apply){BasicCompany linked=(BasicCompany)beans.get("company").getWrappedInstance();linked.setCompanyExtendInfo((CompanyExtendInfo)beans.get("companyInfo").getWrappedInstance());pool.setBasicCompany(linked);enrichment=entryEnrichment.fill(pool,tenant);extensions.save(linked.getCompanyExtendInfo());changed.add("project");}
  if(apply){if(changed.contains("company"))companies.saveMainInfo((BasicCompany)beans.get("company").getWrappedInstance());if(changed.contains("companyInfo"))extensions.save((CompanyExtendInfo)beans.get("companyInfo").getWrappedInstance());if(changed.contains("project"))logoSentinel.save(pool,tenant,()->projects.saveProject(pool));}
  Map<String,Object> after=get(projectId,tenant);if(apply){Map<String,Object> read=new HashMap<String,Object>();for(Object raw:list(after.get("fields"))){Map rr=map(raw);read.put(s(rr.get("field")),rr.get("value"));}for(Map r:out)if("filled".equals(r.get("status"))){Object expected=r.get("value"),actual=read.get(s(r.get("field")));check(expected instanceof BigDecimal&&actual instanceof BigDecimal?((BigDecimal)expected).compareTo((BigDecimal)actual)==0:Objects.equals(expected,actual),"字段写入后回读不一致："+s(r.get("field")));}}
  int count=0;for(Map r:out)if((apply?"filled":"ready").equals(r.get("status")))count++;
  return obj("projectId",projectId,"applied",apply,"filledCount",apply?count:0,"readyCount",apply?0:count,"fields",out,"collectionResult",child,"document",obj("name",map(evidence.get("document")).get("name"),"asOf",map(evidence.get("document")).get("asOf"),"textSha256",hash(s(map(evidence.get("document")).get("pages")))),"after",after,"externalSources",enrichment);
 }
 /* 字段值要给投资经理看：整页原文、PDF表格逐格断行、多个字段同一段，都要求Agent整理后再写 */
 static void copyCheck(String value,Set<String> pageTexts,Map<String,Integer> valueUses){
  String v=norm(value);check(v.length()<30||!pageTexts.contains(v),"不能把整页BP原文当字段值；请整理成通顺的描述，原文放sources.quote");
  Integer uses=valueUses.get(v);check(uses==null||uses<2,"多个字段写了同一段内容；请只写进最贴切的字段");
  String[] lines=value.split("\n");int fragments=0;for(String l:lines)if(l.trim().length()<=4)fragments++;check(lines.length<8||fragments*2<=lines.length,"内容是PDF表格逐格断行；请整理成「指标+数值」或分条描述");
 }
 private Object convert(Map spec,Map row){
  String value=s(row.get("value")),type=s(spec.get("type")),key=s(spec.get("property")),nature=s(row.get("nature")),asOf=s(row.get("asOf"));check(!value.isEmpty(),"值为空");check(!value.matches("(?s).*<[/!]?[A-Za-z].*"),"不接受HTML内容");
  boolean current="current_fact".equals(nature);if(current){check(!asOf.isEmpty(),"当前事实须注明BP日期，未注明的按历史披露处理");LocalDate d=LocalDate.parse(asOf.length()==7?asOf+"-01":asOf);check(!d.isBefore(LocalDate.now().minusDays(90)),"旧BP不能标为当前事实");}
  if("expectFinancing".equals(key)&&"plan".equals(nature)){check(!asOf.isEmpty(),"融资计划须注明BP日期才能当作当前融资需求");LocalDate date=LocalDate.parse(asOf.length()==7?asOf+"-01":asOf);check(!date.isBefore(LocalDate.now().minusDays(90)),"旧BP融资计划须重新核实");current=true;}
  if("hangyeValue".equals(key)&&current)return AgentEntryFields.convert(key,value);
  if("productionAddress".equals(key)){check(current,"生产所在地须为当前事实");return AgentEntryFields.convert(key,value);}
  if("currentPrice".equals(key)&&!current)throw new IllegalArgumentException("旧BP价格不是现价");
  if(!"text".equals(type)&&!Arrays.asList("province","region").contains(type)&&!current)throw new IllegalArgumentException("历史/计划/预测不能进入当前数值或字典字段；请保留在历史描述/融资披露");
  if("dict".equals(type)){for(Dict d:DictUtils.getDictList(s(spec.get("dictionary"))))if(norm(value).equals(norm(d.getLabel())))return d.getValue();throw new IllegalArgumentException("未匹配当前字典标签");}
  if("region".equals(type)||"province".equals(type)){for(Area a:"province".equals(type)?AreaUtils.getAllProvinceList():AreaUtils.getAreaList())if(norm(value).equals(norm(a.getName())))return a.getId();throw new IllegalArgumentException("地区未匹配");}
  if("date".equals(type))return java.sql.Date.valueOf(LocalDate.parse(value));
  if("integer".equals(type)){check(value.matches("[0-9]+"),"须非负整数");return Integer.valueOf(value);}
  if("decimal".equals(type)||"capital".equals(type)){check(value.matches("[0-9]+(?:\\.[0-9]+)?万元"),"金额须明确万元单位");return new BigDecimal(value.substring(0,value.length()-2));}
  if("sociaCreditCode".equals(key))check(value.matches("[0-9A-Z]{18}"),"信用代码格式无效");
  Set<String> descriptions=new HashSet<String>(Arrays.asList("introduction","introductionEnglish","primaryBusiness","businessModel","investmentHighlight","highlight","insufficient","techRemarks","teamBackGround","financialSituation","investmentLogic","industrySituation","competingProducts","performanceIntroduce","mainCreationSummary","mainCreationRemarks","talent","consumerInsight","model","marketIntelligence","honour","financingNeeds","otherSituations","fixedAssets","companyProfile","income","profit"));
  if(!current&&descriptions.contains(key))value="【BP "+(asOf.isEmpty()?"未注明日期":asOf)+"；"+("forecast".equals(nature)?"预测":"plan".equals(nature)?"计划":"历史披露")+"】"+value;
  /* 与网页表单maxlength一致，超出部分网页编辑时保存不了 */int limit="yewu".equals(key)?30:Arrays.asList("teamBackGround","techRemarks","businessModel").contains(key)?512:descriptions.contains(key)?1000:255;check(value.length()<=limit,"超过字段长度上限"+limit);
  if("companyWebsite".equals(key)){java.net.URI u=java.net.URI.create(value.matches("https?://.*")?value:"https://"+value);check(u.getHost()!=null&&u.getUserInfo()==null,"网站无效");return u.toString();}return value;
 }
}


</cursor_untrusted_data_1337>