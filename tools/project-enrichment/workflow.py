#!/usr/bin/env python3
"""Local MCP profile enrichment with bounded research, explicit review and readback."""
import argparse,json,subprocess,sys
from pathlib import Path
import enrich,research
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'risk-patrol'))
from mcp_client import LocalMcpClient,McpError


def verify(before,applied,after):
 if before['projectId']!=after['projectId'] or before['companyId']!=after['companyId']:
  raise enrich.EnrichmentError('READBACK_MISMATCH','回读项目或公司不一致')
 if before['confirmedFields']!=after['confirmedFields']:
  raise enrich.EnrichmentError('READBACK_MISMATCH','原BP字段发生变化')
 index={r['field']:r for r in after['fields']}
 for row in before['fields']:
  value=row.get('value')
  if value is not None and (not isinstance(value,str) or value.strip()):
   if index[row['field']].get('value')!=value:raise enrich.EnrichmentError('READBACK_MISMATCH','已有字段发生变化')
 for row in applied['fields']:
  if row['status']!='filled':continue
  got=index[row['field']].get('value');expected=row.get('mappedValue')
  if row['field']=='foundingTime':
   # Local MCP serializes java.sql.Date as epoch milliseconds on readback.
   from datetime import datetime
   if isinstance(got,(int,float)):got=datetime.fromtimestamp(got/1000).strftime('%Y-%m-%d')
  if got!=expected:raise enrich.EnrichmentError('READBACK_MISMATCH','补写字段未回读一致：'+row['field'])
 return True


def run(args,client=None):
 client=client or LocalMcpClient();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
 def save(name,value):enrich.save(out/(name+'.json'),value)
 snap=client.call('agent_projects_profile_get',{'pendingId':args.pending_id});save('before',snap)
 planned=research.plan(snap);save('research-plan',planned)
 if not planned['missingFields']:return {'status':'already_complete','businessWrites':0}
 bundle=json.loads(args.sources_file.read_text()) if args.sources_file else None
 previous_bundle=None
 for number in (1,2):
  save('research-plan',planned)
  if bundle is None or (number==2 and not args.sources_file):
   try:bundle=research.collect(planned,bundle)
   except enrich.EnrichmentError as e:
    if e.code=='TAVILY_PLUGIN_REQUIRED':return {'status':'research_required','round':number,'reason':str(e),'plan':str(out/'research-plan.json'),'businessWrites':0}
    raise
  save('sources',bundle)
  gaps=research.coverage(planned,bundle)
  if gaps:return {'status':'research_required','round':number,'errors':gaps,'plan':str(out/'research-plan.json'),'businessWrites':0}
  sources=enrich.validate_sources(snap['companyName'],bundle)
  if not sources:return {'status':'research_failed','reason':'未获得可核实正文','businessWrites':0}
  bundle_key=json.dumps(bundle,sort_keys=True,ensure_ascii=False)
  if previous_bundle!=bundle_key:
   if args.evidence_file:
    evidence=json.loads(args.evidence_file.read_text())
    # A reviewed model artifact must use precisely the current collected source material.
    if evidence.get('sources')!=sources or evidence.get('searchReceipts')!=bundle['queries']:
     raise enrich.EnrichmentError('EVIDENCE_MISMATCH','审核证据与本轮来源/查询不一致')
   else:
    command=[sys.executable,str(Path(__file__).with_name('profile.py')),'--company',snap['companyName'],'--sources-file',str(out/'sources.json'),'--output',str(out/'evidence.json')]
    command+=['--verifier',args.verifier,'--task-output',str(out/'verify-task.json')]
    for flag,value in (('--proposal-file',args.proposal_file),('--model',args.model),('--grok-credentials-file',args.grok_credentials_file)):
     if value:command+=[flag,str(value)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=150)
    if result.returncode:raise enrich.EnrichmentError('VERIFY_FAILED','模型核实失败，未写入；详见独立CLI脱敏输出')
    status=json.loads(result.stdout.strip().splitlines()[-1])
    if status.get('status')=='proposal_required':return {**status,'round':number}
    evidence=json.loads((out/'evidence.json').read_text())
   save('evidence',evidence)
   preview=client.call('agent_projects_profile_fill',{'pendingId':args.pending_id,'evidence':evidence,'confirmed':False});save('preview',preview)
   previous_bundle=bundle_key
  next_snapshot={**snap,'fields':[{**r,'value':r.get('mappedValue') if r['status']=='ready' else r.get('value')} for r in preview['fields']]}
  planned=research.plan(snap,2) if research.missing(next_snapshot) else research.plan(next_snapshot,2)
  if number==1 and planned['queries']:continue
  break
 if not args.apply or not args.evidence_file:
  return {'status':'review_required','readyCount':preview.get('readyCount',0),'researchRounds':number,'sourceFailures':[r for r in bundle.get('extractions',[]) if r.get('status')=='failed'],'unresolved':[{'field':r['field'],'reason':r.get('reason','未找到可核实正文')} for r in preview['fields'] if r['status'] in ('unknown','needs_verification')],'businessWrites':0}
 # --apply attests the Bot has reviewed facts and has actual user authorization to fill missing values.
 applied=client.call('agent_projects_profile_fill',{'pendingId':args.pending_id,'evidence':evidence,'confirmed':True});save('applied',applied)
 after=client.call('agent_projects_profile_get',{'pendingId':args.pending_id});save('after',after)
 verify(snap,applied,after)
 unresolved=[{'field':r['field'],'reason':r.get('reason','未找到可核实正文')} for r in applied['fields'] if r['status'] in ('unknown','needs_verification')]
 return {'status':'partial' if unresolved or any(r.get('status')=='failed' for r in bundle.get('extractions',[])) else 'complete','sourceFailures':[r for r in bundle.get('extractions',[]) if r.get('status')=='failed'],'filledCount':applied.get('filledCount',0),'readbackVerified':True,'unresolved':unresolved,'researchRounds':number,'browserVerificationRequired':True,'projectId':after['projectId']}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pending-id',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--sources-file',type=Path);p.add_argument('--evidence-file',type=Path);enrich.add_verifier_arguments(p);p.add_argument('--apply',action='store_true',help='仅在已审阅证据且用户已授权补空值时使用；不确认入池')
 args=p.parse_args()
 try:r=run(args)
 except (enrich.EnrichmentError,McpError) as e:r={'status':'failed','code':e.code,'message':str(e),'completionVerified':False}
 except Exception:r={'status':'failed','code':'WORKFLOW_FAILED','completionVerified':False}
 args.output_dir.mkdir(parents=True,exist_ok=True);enrich.save(args.output_dir/'result.json',r);print(json.dumps(r,ensure_ascii=False));return 1 if r['status']=='failed' else 0
if __name__=='__main__':raise SystemExit(main())
