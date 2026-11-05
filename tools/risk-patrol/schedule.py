"""Beijing schedule and durable slot claims, independent of host timezone."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sqlite3
import re
import uuid

BEIJING = ZoneInfo('Asia/Shanghai')


def parse_times(value):
    times = value.split(',') if isinstance(value, str) else []
    if not 1 <= len(times) <= 4:
        raise ValueError('每天巡检须为1–4次')
    if any(not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', t) for t in times):
        raise ValueError('巡检时间格式须为HH:mm')
    minutes = sorted(int(t[:2]) * 60 + int(t[3:]) for t in times)
    gaps = [b-a for a,b in zip(minutes,minutes[1:])]
    if len(minutes) > 1:
        gaps.append(1440-minutes[-1]+minutes[0])
    if any(g < 60 for g in gaps):
        raise ValueError('巡检间隔不得少于1小时')
    return ['%02d:%02d' % divmod(m,60) for m in minutes]


def latest_slot(times, now):
    if now.tzinfo is None:
        raise ValueError('必须提供带时区时间')
    now = now.astimezone(BEIJING)
    parsed = parse_times(times)
    slots = [datetime.combine((now-timedelta(days=delta)).date(),
                datetime.strptime(t,'%H:%M').time(),BEIJING)
             for delta in (0,1) for t in parsed]
    return max(s for s in slots if s <= now).isoformat()


class SlotStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS patrol_slots '
                        '(tenant TEXT, slot TEXT, state TEXT, lease_until REAL, '
                        'PRIMARY KEY(tenant,slot))')
        if 'owner' not in {r[1] for r in self.db.execute('PRAGMA table_info(patrol_slots)')}:
            self.db.execute('ALTER TABLE patrol_slots ADD COLUMN owner TEXT')
        self.db.commit()
        self._claims = {}

    def claim(self, tenant, slot, now, lease_seconds=1800):
        if not tenant or not slot:
            raise ValueError('租户和时段不可为空')
        owner = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO patrol_slots (tenant,slot,state,lease_until) VALUES (?,?,?,?)',
                            (tenant,slot,'pending',0))
            changed = self.db.execute('UPDATE patrol_slots SET state=?,lease_until=?,owner=? '
                'WHERE tenant=? AND slot=? AND state<>? AND lease_until<=?',
                ('running',now+lease_seconds,owner,tenant,slot,'done',now)).rowcount
        if changed == 1:
            self._claims[(tenant,slot)] = owner
        return changed == 1

    def finish(self, tenant, slot, success):
        owner = self._claims.pop((tenant,slot), None)
        if owner is None:
            return
        with self.db:
            self.db.execute('UPDATE patrol_slots SET state=?,lease_until=0,owner=NULL '
                            'WHERE tenant=? AND slot=? AND state=? AND owner=?',
                            ('done' if success else 'pending',tenant,slot,'running',owner))
