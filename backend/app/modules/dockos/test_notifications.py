import os
import unittest
from datetime import datetime
from unittest.mock import patch

from .notifications import process_due_notifications


class FakeSMTP:
    sent=[]
    def __init__(self,*args,**kwargs): pass
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def starttls(self,context=None): return None
    def login(self,*args): return None
    def send_message(self,message): self.sent.append(message)


class FailingSMTP(FakeSMTP):
    def send_message(self,message): raise OSError('temporary smtp failure')


class NotificationReliabilityTests(unittest.TestCase):
    def setUp(self):
        os.environ['DOCKOS_SMTP_HOST']='smtp.test.local'
        os.environ['DOCKOS_SMTP_FROM']='dockos@test.local'
        os.environ['DOCKOS_NOTIFICATION_MAX_ATTEMPTS']='3'
        os.environ['DOCKOS_NOTIFICATION_RETRY_BASE_SECONDS']='5'
        FakeSMTP.sent.clear()
        self.item={'key':'DKS-1|CREATED|2026-08-13T10:00:00','reservation_no':'DKS-1','event':'CREATED','due_at':'2026-08-13T10:00:00','recipients':['supplier@test.local'],'subject':'DockOS test','html':'<b>ok</b>','status':'PENDING','attempts':0,'created_at':'2026-08-13T09:00:00'}

    def test_stable_message_id_and_idempotency_header(self):
        with patch('app.modules.dockos.notifications.smtplib.SMTP',FakeSMTP):
            result=process_due_notifications([self.item],datetime.fromisoformat('2026-08-13T11:00:00'))
        self.assertEqual(result['sent'],1)
        self.assertEqual(self.item['status'],'SENT')
        self.assertEqual(len(FakeSMTP.sent),1)
        message=FakeSMTP.sent[0]
        self.assertEqual(message['X-DockOS-Idempotency-Key'],self.item['key'])
        first_id=message['Message-ID']
        self.item.update({'status':'PENDING','attempts':0,'sent_at':None})
        with patch('app.modules.dockos.notifications.smtplib.SMTP',FakeSMTP):
            process_due_notifications([self.item],datetime.fromisoformat('2026-08-13T11:00:00'))
        self.assertEqual(FakeSMTP.sent[-1]['Message-ID'],first_id)

    def test_failure_backoff_and_dead_letter(self):
        outbox=[dict(self.item)]
        with patch('app.modules.dockos.notifications.smtplib.SMTP',FailingSMTP):
            first=process_due_notifications(outbox,datetime.fromisoformat('2026-08-13T11:00:00'))
        self.assertEqual(first['failed'],1)
        self.assertEqual(outbox[0]['status'],'FAILED')
        self.assertTrue(outbox[0]['next_attempt_at'])
        outbox[0]['next_attempt_at']='2026-08-13T11:00:00'
        with patch('app.modules.dockos.notifications.smtplib.SMTP',FailingSMTP):
            process_due_notifications(outbox,datetime.fromisoformat('2026-08-13T11:01:00'))
        outbox[0]['next_attempt_at']='2026-08-13T11:01:00'
        with patch('app.modules.dockos.notifications.smtplib.SMTP',FailingSMTP):
            last=process_due_notifications(outbox,datetime.fromisoformat('2026-08-13T11:02:00'))
        self.assertEqual(outbox[0]['status'],'DEAD')
        self.assertEqual(last['dead'],1)


if __name__=='__main__': unittest.main(verbosity=2)
