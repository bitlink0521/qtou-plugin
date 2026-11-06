"""Field-directed public research contract, shared by HTTP and plugin execution."""
from datetime import datetime
import enrich
import qtou_shared

GROUPS = {
 'registry': ('工商登记', ('juridicalPerson','foundingTime','registeredCapital','registeredCurrency','currency','state','type','registrationAuthority','sociaCreditCode','registeredAddress','province','cityValue')),
 'official': ('官网 联系我们 公司介绍 英文名称', ('companyWebsite','officeAddress','contactNumber','companyMailbox','companyProfile','englishName','abbreviation','officialAccounts','projectShorthand')),
 'disclosure': ('公告 年报 主营业务 商业模式 员工人数 高新技术企业 上市 荣誉', ('primaryBusiness','businessModel','staffNumber','nature','isMinorEnterprises','isHighNewEnterprises','isListing','honour','yewu')),
}
OFFICIAL = ['gsxt.gov.cn','cninfo.com.cn','neeq.com.cn','sse.com.cn','szse.cn']
# Tavily (plugin or HTTP key), else whatever web search the calling agent has; bodies come from opened pages.
SEARCH_SOURCES = ('tavily_plugin','tavily_http','agent_search')

def missing(snapshot):
 return [r['field'] for r in snapshot['fields'] if r.get('value') is None or (isinstance(r.get('value'),str) and not r['value'].strip())]

def plan(snapshot, round_number=1):
 company=snapshot['companyName']; absent=set(missing(snapshot)); queries=[]
 for group,(words,fields) in GROUPS.items():
  targets=[f for f in fields if f in absent]
  if not targets: continue
  labels={r['field']:r['label'] for r in snapshot['fields']}
  suffix=words if round_number==1 else ' '.join(labels[f] for f in targets)
  queries.append({'queryId':f'{round_number}:{group}', 'group':group,'round':round_number,
   'query':f'"{company}" {suffix}', 'include_domains':[], 'fields':targets})
  if group=='registry':
   queries.append({'queryId':f'{round_number}:registry_official','group':'registry_official','round':round_number,
    'query':f'"{company}" 工商 登记 注册资本 法定代表人 公告', 'include_domains':OFFICIAL,'fields':targets})
 return {'companyName':company,'round':round_number,'missingFields':sorted(absent),'queries':queries}

def coverage(plan_value,bundle):
 errors=[]; receipts=bundle.get('queries',[])
 if bundle.get('companyName')!=plan_value['companyName']: errors.append('company_mismatch')
 for q in plan_value['queries']:
  found=[]
  for r in receipts:
   if r.get('queryId')!=q['queryId'] or r.get('query')!=q['query'] or r.get('include_domains',[])!=q['include_domains']:continue
   try:
    t=datetime.fromisoformat(r.get('searchedAt',''))
    valid=t.tzinfo is not None and -300 <= (datetime.now().astimezone()-t).total_seconds() <= 86400
   except (ValueError,TypeError):valid=False
   if valid and r.get('status')=='success' and type(r.get('hits')) is int and r['hits']>=0 and isinstance(r.get('urls'),list) and r.get('source') in SEARCH_SOURCES:found.append(r)
  if not found: errors.append('query_missing_or_failed:'+q['queryId'])
 return errors

def collect(plan_value, previous=None, request=enrich.request_json):
 key=qtou_shared.tavily_key()
 if not key:raise enrich.EnrichmentError('SEARCH_REQUIRED','用已连接的Tavily或你自带的联网搜索完成research-plan.json后提供sources-file；无需聊天密钥')
 bundle=previous or {'companyName':plan_value['companyName'],'queries':[],'sources':[],'extractions':[]}
 seen={r['url'] for r in bundle['sources']}
 call=lambda url,payload:request(url,payload,key,'TAVILY')
 for q in plan_value['queries']:
  stamp=enrich.now()
  try:
   try:rows,hits=qtou_shared.tavily_search(call,q['query'],q['include_domains'])
   except ValueError:raise enrich.EnrichmentError('TAVILY_RESPONSE','搜索响应缺少results') from None
   urls=list(dict.fromkeys(r['url'] for r in rows))
   bundle['queries'].append({**q,'searchedAt':stamp,'source':'tavily_http','status':'success','hits':hits,'urls':urls})
   for url in urls:
    if url in seen:continue
    try:
     extracted=qtou_shared.tavily_extract(call,[url])
     if url not in extracted:raise enrich.EnrichmentError('EXTRACT_FAILED','正文提取失败')
     row=extracted[url];bundle['sources'].append({'url':url,'title':row.get('title') or next((r['title'] for r in rows if r['url']==url and r['title']),'') or url,'content':row['raw_content'],'retrievedAt':enrich.now(),'publishedDate':row.get('published_date')})
     bundle.setdefault('extractions',[]).append({'url':url,'status':'success','retrievedAt':enrich.now()});seen.add(url)
    except enrich.EnrichmentError as e:bundle.setdefault('extractions',[]).append({'url':url,'status':'failed','code':e.code})
  except enrich.EnrichmentError as e:bundle['queries'].append({**q,'searchedAt':stamp,'source':'tavily_http','status':'failed','code':e.code})
 return bundle
