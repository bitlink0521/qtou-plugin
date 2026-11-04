"""Durable per-tenant project health and changed-only summary claims.
No messages are sent here. Caller acknowledges notification only after delivery.
"""
import hashlib
import json
import sqlite3
from datetime import date, timedelta


class PatrolState:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS project_health '
            '(tenant TEXT, project TEXT, last_success TEXT, failed_day TEXT, '
            'failed_days INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tenant,project))')
        self.db.execute('CREATE TABLE IF NOT EXISTS summary_ack '
            '(tenant TEXT PRIMARY KEY, digest TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS failure_alert_ack (tenant TEXT, project TEXT, day TEXT, delivered_at TEXT NOT NULL, delivery_reference TEXT NOT NULL, PRIMARY KEY(tenant,project,day))')
        self.db.commit()

    def record(self, tenant, project, now, success):
        if not tenant or not project or now.tzinfo is None:
            raise ValueError('租户、项目及带时区时间必填')
        day = now.date().isoformat()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO project_health VALUES (?,?,NULL,NULL,0)', (tenant, project))
            prior = self.db.execute('SELECT failed_day,failed_days FROM project_health WHERE tenant=? AND project=?', (tenant, project)).fetchone()
            if success:
                self.db.execute('UPDATE project_health SET last_success=?,failed_day=NULL,failed_days=0 WHERE tenant=? AND project=?',
                    (now.isoformat(), tenant, project))
            else:
                yesterday = (now.date()-timedelta(days=1)).isoformat()
                count = prior[1] if prior[0] == day else (prior[1]+1 if prior[0] == yesterday else 1)
                self.db.execute('UPDATE project_health SET failed_day=?,failed_days=? WHERE tenant=? AND project=?',
                    (day, count, tenant, project))
        return self.get(tenant, project)

    def get(self, tenant, project):
        row = self.db.execute('SELECT last_success,failed_day,failed_days FROM project_health WHERE tenant=? AND project=?', (tenant, project)).fetchone()
        if not row:
            return None
        ack = self.db.execute('SELECT delivered_at FROM failure_alert_ack WHERE tenant=? AND project=? AND day=?', (tenant, project, row[1])).fetchone()
        return {'lastSuccessAt':row[0], 'lastFailedDay':row[1], 'consecutiveFailedDays':row[2],
                'failDays':row[2], 'alertDay':row[1], 'alerted':bool(ack) and row[2]>=3,
                'alertedAt':ack[0] if ack and row[2]>=3 else None}

    def retry_projects(self, tenant, today):
        date.fromisoformat(today)
        return [r[0] for r in self.db.execute('SELECT project FROM project_health WHERE tenant=? AND failed_days>0 AND failed_day<? ORDER BY project', (tenant, today))]

    def alerts(self, tenant):
        rows = self.db.execute('SELECT project FROM project_health WHERE tenant=? AND failed_days>=3 ORDER BY project', (tenant,)).fetchall()
        return [dict(projectId=r[0], **self.get(tenant,r[0]),
                     status='alerted' if self.get(tenant,r[0])['alerted'] else 'needs_attention') for r in rows]

    def acknowledge_failure_alert(self, tenant, project, day, delivered_at, delivery_reference):
        """Call only after actual delivery; no implicit acknowledgement on detection."""
        date.fromisoformat(day)
        health = self.get(tenant,project)
        if (not health or health['consecutiveFailedDays']<3 or health['lastFailedDay']!=day
                or delivered_at.tzinfo is None or not isinstance(delivery_reference,str)
                or not delivery_reference.strip()):
            raise ValueError('须提供当前失败日和真实送达引用')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO failure_alert_ack VALUES (?,?,?,?,?)',
                            (tenant,project,day,delivered_at.isoformat(),delivery_reference))
        return self.get(tenant,project)

    def summary_changed(self, tenant, summary):
        digest = hashlib.sha256(json.dumps(summary, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        row = self.db.execute('SELECT digest FROM summary_ack WHERE tenant=?', (tenant,)).fetchone()
        return {'changed': not row or row[0] != digest, 'digest': digest}

    def acknowledge_summary(self, tenant, digest):
        if not tenant or len(digest) != 64:
            raise ValueError('无效摘要确认')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO summary_ack VALUES (?,?)', (tenant, digest))


def summary_payload(summary):
    """Stable business snapshot for changed-only delivery; excludes generated/run times."""
    value = {key: summary.get(key) for key in ('todayNew', 'todayHandled', 'pending', 'expired', 'failed')}
    value['pendingItems'] = sorted(
        [{'draftId': x.get('draftId'), 'grade': x.get('grade'), 'status': x.get('status', 'pending'),
          'result': x.get('result')} for x in summary.get('pendingItems', [])],
        key=lambda x: x['draftId'] or '')
    value['failedItems'] = sorted(
        [{'queueId': x.get('queueId'), 'status': x.get('status'), 'attempts': x.get('attempts')}
         for x in summary.get('failedItems', [])], key=lambda x: x['queueId'] or '')
    value['noRecipientTotal'] = summary.get('noRecipientTotal', 0)
    value['noRecipientItems'] = sorted(
        [{'draftId': x.get('draftId'), 'projectId': x.get('projectId'),
          'status': x.get('status'), 'reason': x.get('reason')}
         for x in summary.get('noRecipientItems', [])],
        key=lambda x: (x['draftId'] or '', x['projectId'] or ''))
    return value
