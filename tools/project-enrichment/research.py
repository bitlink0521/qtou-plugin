"""Field-directed public research contract, shared by HTTP and plugin execution."""
import os
from datetime import datetime
import enrich

GROUPS = {
 'registry': ('工商登记', ('juridicalPerson','foundingTime','registeredCapital','registeredCurrency','currency','state','type','registrationAuthority','sociaCreditCode','registeredAddress','province','cityValue')),
 'official': ('官网 联系我们 公司介绍 英文名称', ('companyWebsite','officeAddress','contactNumber','companyMailbox','companyProfile','englishName','abbreviation','officialAccounts','projectShorthand')),
 'disclosure': ('公告 年报 主营业务 商业模式 员工人数 高新技术企业 上市 荣誉', ('primaryBusiness','businessModel','staffNumber','nature','isMinorEnterprises','isHighNewEnterprises','isListing','honour','yewu')),
}
OFFICIAL = ['gsxt.gov.cn','cninfo.com.cn','neeq.com.cn','sse.com.cn','szse.cn']

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
   if valid and r.get('status')=='success' and type(r.get('hits')) is int and r['hits']>=0 and isinstance(r.get('urls'),list) and r.get('source') in ('tavily_plugin','tavily_http'):found.append(r)
  if not found: errors.append('query_missing_or_failed:'+q['queryId'])
 return errors

def collect(plan_value, previous=None, request=enrich.request_json):
 key=os.environ.get('TAVILY_API_KEY')
 if not key:raise enrich.EnrichmentError('TAVILY_PLUGIN_REQUIRED','使用已连接Tavily插件完成research-plan.json后提供sources-file；无需聊天密钥')
 bundle=previous or {'companyName':plan_value['companyName'],'queries':[],'sources':[],'extractions':[]}
 seen={r['url'] for r in bundle['sources']}
 for q in plan_value['queries']:
  stamp=enrich.now()
  try:
   params={'query':q['query'],'search_depth':'advanced','max_results':5}
   if q['include_domains']:params['include_domains']=q['include_domains']
   result=request('https://api.tavily.com/search',params,key,'TAVILY')
   if not isinstance(result.get('results'),list):raise enrich.EnrichmentError('TAVILY_RESPONSE','搜索响应缺少results')
   urls=list(dict.fromkeys(r['url'] for r in result['results'] if enrich.public_url(r.get('url'))))
   bundle['queries'].append({**q,'searchedAt':stamp,'source':'tavily_http','status':'success','hits':len(result['results']),'urls':urls})
   for url in urls:
    if url in seen:continue
    try:
     extracted=request('https://api.tavily.com/extract',{'urls':[url],'extract_depth':'advanced','format':'text'},key,'TAVILY')
     rows=[r for r in extracted.get('results',[]) if r.get('url')==url and r.get('raw_content')]
     if not rows:raise enrich.EnrichmentError('EXTRACT_FAILED','正文提取失败')
     row=rows[0];bundle['sources'].append({'url':url,'title':row.get('title') or next((r.get('title') for r in result['results'] if r.get('url')==url),'') or url,'content':row['raw_content'],'retrievedAt':enrich.now(),'publishedDate':row.get('published_date')})
     bundle.setdefault('extractions',[]).append({'url':url,'status':'success','retrievedAt':enrich.now()});seen.add(url)
    except enrich.EnrichmentError as e:bundle.setdefault('extractions',[]).append({'url':url,'status':'failed','code':e.code})
  except enrich.EnrichmentError as e:bundle['queries'].append({**q,'searchedAt':stamp,'source':'tavily_http','status':'failed','code':e.code})
 return bundle
