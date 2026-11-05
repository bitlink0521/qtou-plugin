import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from patrol_state import PatrolState


class StateTests(unittest.TestCase):
    def test_failure_days_retry_and_recovery(self):
        state = PatrolState(':memory:'); self.addCleanup(state.db.close)
        def at(day): return datetime(2026, 10, day, 8, 30, tzinfo=ZoneInfo('Asia/Shanghai'))
        for day in (26, 26, 27, 28): state.record('t', 'p', at(day), False)
        self.assertEqual(state.get('t', 'p')['consecutiveFailedDays'], 3)
        self.assertEqual(len(state.alerts('t')), 1)
        self.assertEqual(state.retry_projects('t', '2026-10-29'), ['p'])
        self.assertEqual(state.retry_projects('other', '2026-10-29'), [])
        state.record('t', 'p', at(29), True)
        self.assertEqual(state.alerts('t'), [])
        self.assertIsNotNone(state.get('t', 'p')['lastSuccessAt'])

    def test_gap_does_not_claim_consecutive(self):
        state = PatrolState(':memory:'); self.addCleanup(state.db.close)
        for day in (26, 28):
            state.record('t', 'p', datetime(2026, 10, day, tzinfo=ZoneInfo('Asia/Shanghai')), False)
        self.assertEqual(state.get('t', 'p')['consecutiveFailedDays'], 1)

    def test_summary_ack_only_after_delivery(self):
        state = PatrolState(':memory:'); self.addCleanup(state.db.close)
        first = state.summary_changed('t', {'pending': 1})
        self.assertTrue(first['changed'])
        self.assertTrue(state.summary_changed('t', {'pending': 1})['changed'])
        state.acknowledge_summary('t', first['digest'])
        self.assertFalse(state.summary_changed('t', {'pending': 1})['changed'])
        self.assertTrue(state.summary_changed('t', {'pending': 2})['changed'])
        self.assertTrue(state.summary_changed('other', {'pending': 1})['changed'])

class StableSummaryTest(unittest.TestCase):
 def test_timestamps_and_order_do_not_change_business_digest(self):
  from patrol_state import summary_payload
  s=PatrolState(':memory:');self.addCleanup(s.db.close)
  a={'pending':2,'expired':0,'failed':0,'todayNew':{'total':2},'pendingItems':[{'draftId':'b','grade':'high','createDate':'old'},{'draftId':'a','grade':'medium'}],'generatedAt':'first'}
  b=dict(a,generatedAt='second',pendingItems=list(reversed(a['pendingItems'])))
  x=s.summary_changed('t',summary_payload(a));s.acknowledge_summary('t',x['digest'])
  self.assertFalse(s.summary_changed('t',summary_payload(b))['changed'])
  b['pending']=1
  self.assertTrue(s.summary_changed('t',summary_payload(b))['changed'])

 def test_unroutable_draft_is_actionable_summary_change(self):
  from patrol_state import summary_payload
  s=PatrolState(':memory:');self.addCleanup(s.db.close)
  first={'pending':1,'failed':0,'noRecipientTotal':0,'noRecipientItems':[]}
  x=s.summary_changed('t',summary_payload(first));s.acknowledge_summary('t',x['digest'])
  unroutable=dict(first,noRecipientTotal=1,noRecipientItems=[{'draftId':'d1','projectId':'p1','reason':'NO_RECIPIENT'}])
  self.assertTrue(s.summary_changed('t',summary_payload(unroutable))['changed'])
  x=s.summary_changed('t',summary_payload(unroutable));s.acknowledge_summary('t',x['digest'])
  self.assertFalse(s.summary_changed('t',summary_payload(dict(unroutable,generatedAt='later')))['changed'])
  reassigned=dict(unroutable,noRecipientItems=[{'draftId':'d2','projectId':'p2','reason':'NO_RECIPIENT'}])
  self.assertTrue(s.summary_changed('t',summary_payload(reassigned))['changed'])
