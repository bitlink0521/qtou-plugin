import argparse,copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import enrich,research,workflow

SNAP={'companyName':'测试甲科技有限公司','projectId':'p','companyId':'c','confirmedFields':{'introduction':'原BP'},'fields':[{'field':'juridicalPerson','label':'法人','value':None},{'field':'companyWebsite','label':'网址','value':''},{'field':'staffNumber','label':'人数','value':0},{'field':'isListing','label':'上市','value':False}]}

class WorkflowTests(unittest.TestCase):
 def test_plan_covers_groups_keeps_false_zero_and_targets_followup(self):
  p=research.plan(SNAP);self.assertEqual(set(p['missingFields']),{'juridicalPerson','companyWebsite'})
  self.assertEqual({q['group'] for q in p['queries']},{'registry','registry_official','official'})
  self.assertTrue(next(q for q in p['queries'] if q['group']=='registry_official')['include_domains'])
  self.assertIn('法人',research.plan(SNAP,2)['queries'][0]['query'])
 def test_snippet_legacy_receipt_failure_and_domain_mismatch_do_not_cover(self):
  p=research.plan(SNAP)
  receipts=[{**q,'searchedAt':enrich.now(),'source':'tavily_plugin','hits':0,'urls':[],'status':'success'} for q in p['queries']]
  b={'companyName':SNAP['companyName'],'queries':receipts}
  self.assertEqual(research.coverage(p,b),[])
  for bad in ({'status':'failed'},{'searchedAt':'2026-01-01'},{'source':'model_memory'},{'hits':False}):
   v=copy.deepcopy(b);v['queries'][0].update(bad);self.assertTrue(research.coverage(p,v))
  v=copy.deepcopy(b);v['queries'][1]['include_domains']=[];self.assertTrue(research.coverage(p,v))
 def test_http_extract_failure_not_disguised_as_body_and_other_queries_continue(self):
  p=research.plan(SNAP);calls=[]
  def request(url,args,*unused):
   calls.append(url)
   if url.endswith('/search'):return {'results':[{'url':'https://example.com/a','title':'a','content':'摘要不能当正文'}]}
   raise enrich.EnrichmentError('EXTRACT_FAILED','失败')
  with patch.dict('os.environ',{'TAVILY_API_KEY':'test-only'}):b=research.collect(p,request=request)
  self.assertEqual(b['sources'],[]);self.assertEqual(len(b['queries']),3);self.assertTrue(b['extractions'])
 def test_plugin_missing_receipts_emits_plan_no_model_or_write(self):
  class Client:
   def call(self,tool,args):
    if tool!='agent_projects_profile_get':raise AssertionError('不得调用模型或补写')
    return SNAP
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);f=root/'input.json';f.write_text(json.dumps({'companyName':SNAP['companyName'],'queries':[],'sources':[]}))
   args=argparse.Namespace(output_dir=root,pending_id='pending',sources_file=f,evidence_file=None,apply=True,verifier='agent',proposal_file=None,model=None,grok_credentials_file=None)
   r=workflow.run(args,Client());self.assertEqual(r['status'],'research_required');self.assertEqual(r['businessWrites'],0);self.assertTrue((root/'research-plan.json').exists())
 def test_readback_detects_wrong_project_original_change_and_missing_write(self):
  after=copy.deepcopy(SNAP);after['fields'][0]['value']='张甲'
  applied={'fields':[{'field':'juridicalPerson','status':'filled','mappedValue':'张甲'}]}
  self.assertTrue(workflow.verify(SNAP,applied,after))
  for changed in ('projectId','confirmedFields'):
   wrong=copy.deepcopy(after);wrong[changed]='wrong'
   with self.assertRaises(enrich.EnrichmentError):workflow.verify(SNAP,applied,wrong)
  wrong=copy.deepcopy(after);wrong['fields'][0]['value']=None
  with self.assertRaises(enrich.EnrichmentError):workflow.verify(SNAP,applied,wrong)
  wrong=copy.deepcopy(after);wrong['fields'][2]['value']=1
  with self.assertRaises(enrich.EnrichmentError):workflow.verify(SNAP,applied,wrong)
 def test_reviewed_apply_runs_preview_write_readback_with_full_coverage(self):
  p=research.plan(SNAP)
  bundle={'companyName':SNAP['companyName'],'queries':[{**q,'searchedAt':enrich.now(),'source':'tavily_plugin','status':'success','hits':1,'urls':['https://example.com/a']} for q in p['queries']], 'sources':[{'url':'https://example.com/a','title':'测试公司官网','content':SNAP['companyName']+'公司官网公开资料。' * 10,'retrievedAt':enrich.now()}]}
  evidence={'schemaVersion':1,'companyName':SNAP['companyName'],'sources':enrich.validate_sources(SNAP['companyName'],bundle),'searchReceipts':bundle['queries']}
  preview=copy.deepcopy(SNAP);preview['readyCount']=2
  for r,v in zip(preview['fields'][:2],['张甲','https://example.com']):r.update(status='ready',mappedValue=v)
  for r in preview['fields'][2:]:r['status']='preserved'
  applied=copy.deepcopy(preview);applied['filledCount']=2
  for r in applied['fields'][:2]:r.update(status='filled',value=r['mappedValue'])
  calls=[]
  class Client:
   def call(self,tool,args):
    calls.append((tool,args))
    if tool=='agent_projects_profile_get':return applied if len(calls)>1 else SNAP
    return applied if args['confirmed'] else preview
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);f=root/'input.json';f.write_text(json.dumps(bundle));e=root/'reviewed.json';e.write_text(json.dumps(evidence))
   a=argparse.Namespace(output_dir=root/'out',pending_id='pending',sources_file=f,evidence_file=e,apply=True,verifier='agent',proposal_file=None,model=None,grok_credentials_file=None)
   r=workflow.run(a,Client());self.assertEqual(r['filledCount'],2);self.assertTrue(r['readbackVerified']);self.assertEqual(r['status'],'complete')
   self.assertEqual([x[0] for x in calls],['agent_projects_profile_get','agent_projects_profile_fill','agent_projects_profile_fill','agent_projects_profile_get'])

 def test_two_round_resume_uses_stable_inventory_and_one_model_artifact(self):
  queries=research.plan(SNAP)['queries']+research.plan(SNAP,2)['queries']
  bundle={'companyName':SNAP['companyName'],'queries':[{**q,'searchedAt':enrich.now(),'source':'tavily_plugin','status':'success','hits':0,'urls':[]} for q in queries], 'sources':[{'url':'https://example.com/a','title':'测试来源','content':SNAP['companyName']+'公开文字正文。'*10,'retrievedAt':enrich.now()}]}
  evidence={'sources':enrich.validate_sources(SNAP['companyName'],bundle),'searchReceipts':bundle['queries']}
  preview=copy.deepcopy(SNAP);preview['readyCount']=1
  for r in preview['fields']:r['status']='unknown' if r['value'] in (None,'') else 'preserved'
  preview['fields'][0].update(status='ready',mappedValue='张甲')
  calls=[]
  class Client:
   def call(self,tool,args):
    calls.append(tool)
    if tool=='agent_projects_profile_get':return SNAP
    if args['confirmed']:raise AssertionError('只读阶段不得写')
    return preview
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);f=root/'input.json';f.write_text(json.dumps(bundle));e=root/'evidence.json';e.write_text(json.dumps(evidence))
   a=argparse.Namespace(output_dir=root/'out',pending_id='pending',sources_file=f,evidence_file=e,apply=False,verifier='agent',proposal_file=None,model=None,grok_credentials_file=None)
   r=workflow.run(a,Client());self.assertEqual(r['status'],'review_required');self.assertEqual(r['researchRounds'],2);self.assertEqual(calls.count('agent_projects_profile_fill'),1)

if __name__=='__main__':unittest.main()
