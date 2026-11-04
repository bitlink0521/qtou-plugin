import unittest,tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from patrol_state import PatrolState
from runner import execute_due
from schedule import SlotStore

class FailureAlertTest(unittest.TestCase):
 def test_days_delivery_ack_and_success_reset(self):
  s=PatrolState(':memory:');self.addCleanup(s.db.close)
  now=datetime(2026,10,27,9,tzinfo=ZoneInfo('Asia/Shanghai'))
  for day in range(3):
   t=now+timedelta(days=day)
   s.record('t','qa',t,False);s.record('t','qa',t,False)
   self.assertEqual(s.get('t','qa')['failDays'],day+1)
  self.assertFalse(s.alerts('t')[0]['alerted'])
  with self.assertRaises(ValueError):s.acknowledge_failure_alert('t','qa','2026-10-29',t,'')
  s.acknowledge_failure_alert('t','qa','2026-10-29',t,'unittest delivery receipt only')
  self.assertTrue(s.alerts('t')[0]['alerted'])
  s.record('t','qa',t+timedelta(days=1),False)
  self.assertFalse(s.alerts('t')[0]['alerted'])
  s.record('t','qa',t+timedelta(days=1),True)
  self.assertEqual(s.get('t','qa')['failDays'],0);self.assertFalse(s.get('t','qa')['alerted']);self.assertEqual(s.alerts('t'),[])

 def test_health_is_present_before_server_finish(self):
  class Client:
   def __init__(self):self.finishes=[]
   def call(self,name,args=None):
    if name=='agent_health':return {'customerId':'t'}
    if name=='risk_config_get':return {'patrolTimes':'08:30,16:30'}
    if name=='agent_portfolio_list':return [{'id':'qa','project_name':'QA模拟故障','is_after_invest':1}]
    if name=='risk_run_record':
     if args.get('runId'):self.finishes.append(args)
     return {'runId':'run'}
  with tempfile.TemporaryDirectory() as d:
   store=SlotStore(str(Path(d)/'state.sqlite'));self.addCleanup(store.db.close);c=Client()
   def fail(q):raise RuntimeError('simulated only')
   for day in (27,28,29):execute_due(c,fail,store,datetime(2026,10,day,9,tzinfo=ZoneInfo('Asia/Shanghai')),events=[])
   detail=c.finishes[-1]['details'][-1]
   self.assertEqual(detail['failDays'],3);self.assertEqual(detail['consecutiveFailedDays'],3)
   self.assertFalse(detail['alerted']);self.assertIsNone(detail['lastSuccessAt'])
