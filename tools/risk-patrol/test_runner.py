import unittest
from runner import execute


class Fake:
    def __init__(self):
        self.calls = []
        self.seen = set()
    def call(self, name, args=None):
        self.calls.append((name, args))
        if name == 'risk_config_get': return {'patrolTimes': '08:30,16:30'}
        if name == 'agent_portfolio_list':
            return [{'id': 'a', 'is_after_invest': 1, 'project_name': '正常'},
                    {'id': 'b', 'is_after_invest': 0, 'project_name': '排除'},
                    {'id': 'c', 'is_after_invest': 1, 'project_name': '失败'}]
        if name == 'risk_run_record': return {'runId': 'r1'}
        if name == 'create_risk_draft':
            key = args['eventKey']
            outcome = 'duplicate' if key in self.seen else 'created'
            self.seen.add(key)
            return {'result': outcome}


class RunnerTest(unittest.TestCase):
    def test_collect_isolation_no_draft(self):
        client = Fake()
        def search(q):
            if q.startswith('失败'): raise RuntimeError('secret')
            return [{'url': 'https://example.com'}]
        result = execute(client, search)
        self.assertEqual((result['scanned'], result['errors'], result['draftsCreated']), (2, 1, 0))
        self.assertFalse(any(n == 'create_risk_draft' for n, a in client.calls))
        self.assertEqual(client.calls[-1][1]['details'][0]['error'], '新闻源未开通')
        self.assertNotIn('secret', str(result))

    def test_verified_retry_duplicate_and_scope(self):
        client = Fake()
        event = {'verified': True, 'rule': 'S3-C行政处罚', 'projectId': 'a',
                 'grade': 'medium', 'sources': [{'url': 'https://example.com'}], 'eventKey': 'same'}
        first = execute(client, None, [event])
        second = execute(client, None, [event])
        self.assertEqual(first['draftsCreated'], 1)
        self.assertEqual(second['draftsCreated'], 0)
        bad = dict(event, projectId='b')
        self.assertEqual(execute(client, None, [bad])['errors'], 1)
        self.assertEqual(execute(client, None, [dict(event, verified=False)])['errors'], 1)


if __name__ == '__main__': unittest.main()

class ScheduleIntegrationTest(unittest.TestCase):
    def test_collection_does_not_complete_slot(self):
        from runner import execute_due
        from schedule import SlotStore, BEIJING
        from datetime import datetime
        store = SlotStore(':memory:'); self.addCleanup(store.db.close)
        class Client(Fake):
            def call(self, name, args=None):
                if name == 'agent_health': return {'customerId': 'tenant'}
                return super().call(name, args)
        now = datetime(2026, 10, 29, 9, 0, tzinfo=BEIJING)
        c = Client()
        execute_due(c, lambda q: [], store, now)
        self.assertTrue(store.claim('tenant', '2026-10-29T08:30:00+08:00', now.timestamp()))
        store.finish('tenant', '2026-10-29T08:30:00+08:00', False)
        execute_due(c, lambda q: [], store, now, events=[])
        self.assertEqual(execute_due(c, lambda q: [], store, now, events=[])['mode'], 'not_due')

    def test_candidate_schema_cannot_submit(self):
        from runner import validate_candidates
        with self.assertRaises(ValueError):
            validate_candidates({'schemaVersion': 1, 'projects': {'a': [{'url': 'https://x', 'title': '', 'content': '', 'verified': True}]}})
        client = Fake()
        saved = {'schemaVersion': 1, 'projects': {'a': [], 'c': []}}
        result = execute(client, None, candidates=saved)
        self.assertEqual(result['errors'], 0)
        self.assertEqual(result['draftsCreated'], 0)
        self.assertFalse(any(n == 'create_risk_draft' for n, a in client.calls))

class EmptyEventsCoverageTest(unittest.TestCase):
    def test_empty_events_missing_search_never_finishes(self):
        from runner import execute_due
        from schedule import SlotStore, BEIJING
        from datetime import datetime
        class Client(Fake):
            def call(self, name, args=None):
                if name == 'agent_health': return {'customerId': 'tenant'}
                return super().call(name,args)
        store=SlotStore(':memory:'); self.addCleanup(store.db.close); now=datetime(2026,10,29,9,tzinfo=BEIJING)
        def unavailable(q): raise RuntimeError('no search credentials')
        r=execute_due(Client(),unavailable,store,now,events=[])
        self.assertFalse(r['coverageComplete'])
        self.assertGreater(r['errors'],0)
        self.assertTrue(store.claim('tenant',r['slot'],now.timestamp()))

class PluginReceiptTest(unittest.TestCase):
 def test_full_reviewed_plugin_receipts(self):
  from runner import execute_due
  from schedule import SlotStore,BEIJING
  from datetime import datetime
  class Client(Fake):
   def call(self,name,args=None):
    if name=='agent_health':return {'customerId':'tenant'}
    return super().call(name,args)
  now=datetime(2026,10,29,9,tzinfo=BEIJING)
  evidence={'schemaVersion':2,'projects':{'a':[],'c':[]},'receipts':{pid:{'query':'公司公告检索','source':'tavily_plugin','searchedAt':'2026-10-29T08:45:00+08:00','reviewed':True,'conclusion':'no_anomaly'} for pid in ['a','c']}}
  def no_http(q):raise AssertionError('plugin must not need local key')
  store=SlotStore(':memory:'); self.addCleanup(store.db.close);r=execute_due(Client(),no_http,store,now,events=[],candidates=evidence)
  self.assertTrue(r['coverageComplete']);self.assertEqual(r['errors'],0)
  self.assertEqual(execute_due(Client(),no_http,store,now,events=[],candidates=evidence)['mode'],'not_due')
  evidence['receipts'].pop('c')
  with self.assertRaises(ValueError):execute_due(Client(),no_http,store,datetime(2026,10,30,9,tzinfo=BEIJING),events=[],candidates=evidence)

class TestProjectSkipTest(unittest.TestCase):
 def test_only_test_named_projects_can_skip(self):
  from runner import plugin_coverage,execute
  from schedule import BEIJING
  from datetime import datetime
  class Client(Fake):
   def call(self,name,args=None):
    if name=='agent_portfolio_list':return [{'id':'a','is_after_invest':1,'project_name':'【模拟验收】隔离'}]
    return super().call(name,args)
  evidence={'schemaVersion':2,'projects':{'a':[]},'receipts':{'a':{'source':'test_scope','conclusion':'skip_test_project','reason':'明确测试项目无外部主体'}}}
  c=Client();v,skipped=plugin_coverage(c,evidence,[],'2026-10-29T08:30:00+08:00',datetime(2026,10,29,9,tzinfo=BEIJING))
  r=execute(c,None,candidates=v,skip_test_ids=skipped)
  self.assertEqual(r['results'][0]['status'],'skipped');self.assertEqual(r['errors'],0)
  class Real(Client):
   def call(self,name,args=None):
    if name=='agent_portfolio_list':return [{'id':'a','is_after_invest':1,'project_name':'真实企业'}]
    return super().call(name,args)
  with self.assertRaises(ValueError):plugin_coverage(Real(),evidence,[],'2026-10-29T08:30:00+08:00',datetime(2026,10,29,9,tzinfo=BEIJING))

class CoverageHealthTest(unittest.TestCase):
 def test_plugin_records_success_but_not_test_skip_and_closes(self):
  import tempfile
  from pathlib import Path
  from unittest.mock import patch
  import runner
  from patrol_state import PatrolState
  from schedule import SlotStore,BEIJING
  from datetime import datetime
  class Client(Fake):
   def call(self,name,args=None):
    if name=='agent_health':return {'customerId':'tenant'}
    if name=='agent_portfolio_list':return [{'id':'a','is_after_invest':1,'project_name':'真实公司'},{'id':'c','is_after_invest':1,'project_name':'QA样本'}]
    return super().call(name,args)
  now=datetime(2026,10,29,9,tzinfo=BEIJING)
  e={'schemaVersion':2,'projects':{'a':[],'c':[]},'receipts':{'a':{'source':'tavily_plugin','query':'真实公司公告','searchedAt':'2026-10-29T08:45:00+08:00','reviewed':True,'conclusion':'no_anomaly'},'c':{'source':'test_scope','conclusion':'skip_test_project','reason':'QA样本'}}}
  with tempfile.TemporaryDirectory() as d:
   path=str(Path(d)/'state.sqlite');store=SlotStore(path); self.addCleanup(store.db.close);captured=[]
   def state(p):
    v=PatrolState(p);captured.append(v);return v
   with patch.object(runner,'PatrolState',side_effect=state):
    result=runner.execute_due(Client(),None,store,now,events=[],candidates=e)
   import sqlite3
   with self.assertRaises(sqlite3.ProgrammingError):captured[0].db.execute('SELECT 1')
   check=PatrolState(path)
   self.assertEqual(check.get('tenant','a')['lastSuccessAt'],now.isoformat())
   self.assertIsNone(check.get('tenant','c'))
   self.assertEqual(result['coverageResults'][0]['lastSuccessAt'],now.isoformat())
   check.db.close();store.db.close()

 def test_verified_mode_failed_search_counts_days_and_next_success_clears(self):
  import tempfile
  from pathlib import Path
  from runner import execute_due
  from patrol_state import PatrolState
  from schedule import SlotStore,BEIJING
  from datetime import datetime
  class Client(Fake):
   def call(self,name,args=None):
    if name=='agent_health':return {'customerId':'tenant'}
    return super().call(name,args)
  with tempfile.TemporaryDirectory() as d:
   path=str(Path(d)/'state.sqlite');store=SlotStore(path); self.addCleanup(store.db.close)
   def failed(q):raise RuntimeError('search unavailable')
   for day in [27,28,29]:
    now=datetime(2026,10,day,9,tzinfo=BEIJING)
    result=execute_due(Client(),failed,store,now,events=[])
    self.assertFalse(result['coverageComplete'])
   self.assertEqual(result['failureAlerts'][0]['consecutiveFailedDays'],3)
   result=execute_due(Client(),lambda q:[],store,now,events=[])
   self.assertTrue(result['coverageComplete']);self.assertEqual(result['failureAlerts'],[])
   check=PatrolState(path);self.assertEqual(check.get('tenant','a')['consecutiveFailedDays'],0)
   self.assertEqual(check.get('tenant','a')['lastSuccessAt'],now.isoformat())
   check.db.close();store.db.close()
