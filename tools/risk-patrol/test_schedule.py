import unittest
from datetime import datetime, timezone
from schedule import parse_times, latest_slot, SlotStore

class ScheduleTests(unittest.TestCase):
    def test_config_validation(self):
        self.assertEqual(parse_times('16:30,08:30'),['08:30','16:30'])
        for value in ('','8:30','08:30,08:30','23:30,00:00','08:00,08:30'):
            with self.assertRaises(ValueError): parse_times(value)
    def test_beijing(self):
        self.assertEqual(latest_slot('08:30,16:30',datetime(2026,10,29,1,tzinfo=timezone.utc)),
                         '2026-10-29T08:30:00+08:00')
    def test_retry_and_duplicate(self):
        store=SlotStore(':memory:'); self.addCleanup(store.db.close)
        self.assertTrue(store.claim('a','slot',100))
        self.assertFalse(store.claim('a','slot',101))
        store.finish('a','slot',False)
        self.assertTrue(store.claim('a','slot',102))
        store.finish('a','slot',True)
        self.assertFalse(store.claim('a','slot',10000))
        self.assertTrue(store.claim('b','slot',10000))

    def test_expired_worker_cannot_finish_reclaimed_lease(self):
        import tempfile
        with tempfile.NamedTemporaryFile() as f:
            old=SlotStore(f.name); new=SlotStore(f.name)
            self.addCleanup(old.db.close); self.addCleanup(new.db.close)
            self.assertTrue(old.claim('a','s',100,10))
            self.assertTrue(new.claim('a','s',111,10))
            old.finish('a','s',True)
            self.assertEqual(new.db.execute('SELECT state,lease_until FROM patrol_slots').fetchone(),('running',121))
            new.finish('a','s',False)
            self.assertTrue(old.claim('a','s',112,10))
