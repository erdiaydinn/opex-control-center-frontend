import hashlib
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from .retry_policy import next_retry_seconds, terminal


def _reservation_start(reservation):
    if reservation.get('shipment_mode') != 'SEVKIYAT' or not reservation.get('slot_date'):
        return None
    start_text = str(reservation.get('selected_slot') or '').split('-')[0].strip()
    try:
        return datetime.fromisoformat(f"{reservation['slot_date']}T{start_text}:00")
    except ValueError:
        return None


def _recipients(reservation):
    values = [reservation.get('contact_email')]
    values.extend(item.strip() for item in os.getenv('DOCKOS_DC_EMAILS','').split(','))
    return sorted({value for value in values if value and '@' in value})


def _event_copy(event):
    return {
        'CREATED': ('Rezervasyonunuz oluşturuldu','Rezervasyon kaydınız başarıyla oluşturuldu.'),
        'REMINDER_48': ('Rezervasyona 48 saat kaldı','Planlanan geliş saatinize 48 saat kaldı. Araç ve sevkiyat bilgilerinizi kontrol edin.'),
        'FINAL_24': ('Rezervasyon için son hatırlatma','Rezervasyona 24 saat kaldı. Tedarikçi iptal/değişiklik süresi sona ermiştir; bundan sonraki değişiklikleri merkez depo yönetir.'),
        'EDITED': ('Rezervasyonunuz merkez depo tarafından güncellendi','Rezervasyon bilgileriniz merkez depo operasyonu tarafından değiştirildi.'),
        'CANCELLED': ('Rezervasyonunuz iptal edildi','Rezervasyon kaydınız merkez depo operasyonu tarafından iptal edildi.'),
    }[event]


def render_mail(event,reservation,reason=''):
    title,intro=_event_copy(event)
    detail_rows=[
        ('Rezervasyon No',reservation.get('reservation_no','-')),
        ('Tedarikçi',reservation.get('supplier_name','-')),
        ('Merkez Depo',reservation.get('warehouse_name','-')),
        ('Tarih',reservation.get('slot_date','-')),
        ('Saat',reservation.get('selected_slot','-')),
        ('Palet / SKU',f"{reservation.get('pallet_count',0)} palet / {reservation.get('sku_count',0)} SKU"),
        ('Araç / Plaka',f"{reservation.get('vehicle_type') or '-'} / {reservation.get('vehicle_plate') or '-'}"),
        ('PO',reservation.get('po_number') or '-'),
    ]
    if reason:
        detail_rows.append(('Açıklama',reason))
    rows=''.join(f"<tr><td style='padding:9px 12px;color:#667085;border-bottom:1px solid #eaecf0'>{label}</td><td style='padding:9px 12px;font-weight:700;border-bottom:1px solid #eaecf0'>{value}</td></tr>" for label,value in detail_rows)
    html=f"""<div style="font-family:Arial,sans-serif;background:#f5f6f8;padding:28px;color:#101828"><div style="max-width:680px;margin:auto;background:white;border-radius:18px;overflow:hidden;border:1px solid #eaecf0"><div style="padding:22px 26px;background:#101828;color:white"><div style="font-size:12px;color:#fda4c0;font-weight:700">EAY PLATFORM · DOCKOS</div><h1 style="margin:7px 0 0;font-size:24px">{title}</h1></div><div style="padding:24px 26px"><p style="margin-top:0;line-height:1.6">{intro}</p><table style="width:100%;border-collapse:collapse;margin-top:18px">{rows}</table><div style="margin-top:20px;padding:14px;border-radius:12px;background:#fff1f6;color:#9f1239"><strong>Önemli:</strong> Bu e-posta DockOS tarafından otomatik oluşturulmuştur. Rezervasyon numaranızı işlemlerde kullanın.</div></div></div></div>"""
    return f"DockOS | {title} | {reservation.get('reservation_no','')}",html


def _queue(outbox,reservation,event,due_at,reason=''):
    recipients=_recipients(reservation)
    key=f"{reservation.get('reservation_no')}|{event}|{due_at.isoformat()}"
    if any(item.get('key')==key for item in outbox):
        return
    subject,html=render_mail(event,reservation,reason)
    outbox.append({'key':key,'reservation_no':reservation.get('reservation_no'),'event':event,'due_at':due_at.isoformat(),'recipients':recipients,'subject':subject,'html':html,'status':'PENDING','attempts':0,'created_at':datetime.now().isoformat()})


def queue_reservation_flow(outbox,reservation,event,reason=''):
    now=datetime.now()
    if event in {'EDITED','CANCELLED'}:
        for item in outbox:
            if item.get('reservation_no')==reservation.get('reservation_no') and item.get('event') in {'REMINDER_48','FINAL_24'} and item.get('status') in {'PENDING','WAITING_CONFIG','FAILED'}:
                item['status']='CANCELLED'
    _queue(outbox,reservation,event,now,reason)
    if event in {'CREATED','EDITED'}:
        start=_reservation_start(reservation)
        if start:
            for reminder,hours in [('REMINDER_48',48),('FINAL_24',24)]:
                due=start-timedelta(hours=hours)
                if due>now:
                    _queue(outbox,reservation,reminder,due)


def _message_id(item):
    digest=hashlib.sha256(str(item.get('key') or '').encode('utf-8')).hexdigest()
    return f"<{digest}@dockos.eay>"


def process_due_notifications(outbox,now=None):
    now=now or datetime.now()
    host=os.getenv('DOCKOS_SMTP_HOST','').strip()
    sent=failed=waiting=dead=0
    for item in outbox:
        if item.get('status') not in {'PENDING','WAITING_CONFIG','FAILED'}:
            continue
        if datetime.fromisoformat(item['due_at'])>now:
            continue
        next_attempt=item.get('next_attempt_at')
        if next_attempt and datetime.fromisoformat(next_attempt)>now:
            continue
        attempts=int(item.get('attempts') or 0)
        if terminal(attempts):
            item['status']='DEAD'; dead+=1; continue
        if not item.get('recipients') or not host:
            item['status']='WAITING_CONFIG'; waiting+=1; continue
        try:
            message=EmailMessage()
            message['Subject']=item['subject']
            message['From']=os.getenv('DOCKOS_SMTP_FROM','dockos@localhost')
            message['To']=', '.join(item['recipients'])
            message['Message-ID']=_message_id(item)
            message['X-DockOS-Idempotency-Key']=str(item.get('key') or '')
            message.set_content('Bu bildirim HTML formatındadır.')
            message.add_alternative(item['html'],subtype='html')
            port=int(os.getenv('DOCKOS_SMTP_PORT','587'))
            with smtplib.SMTP(host,port,timeout=20) as smtp:
                if os.getenv('DOCKOS_SMTP_TLS','true').lower()=='true':
                    smtp.starttls(context=ssl.create_default_context())
                username=os.getenv('DOCKOS_SMTP_USER','')
                if username:
                    smtp.login(username,os.getenv('DOCKOS_SMTP_PASSWORD',''))
                smtp.send_message(message)
            item['status']='SENT'
            item['sent_at']=datetime.now().isoformat()
            item['last_error']=None
            item['next_attempt_at']=None
            sent+=1
        except Exception as error:
            attempts+=1
            item['status']='DEAD' if terminal(attempts) else 'FAILED'
            item['last_error']=str(error)[:500]
            item['next_attempt_at']=(now+timedelta(seconds=next_retry_seconds(attempts))).isoformat()
            if item['status']=='DEAD': dead+=1
            else: failed+=1
        item['attempts']=attempts+1 if item.get('status')=='SENT' else attempts
    return {'sent':sent,'failed':failed,'waiting_config':waiting,'dead':dead}
