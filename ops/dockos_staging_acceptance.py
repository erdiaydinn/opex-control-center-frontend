from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('DOCKOS_STAGING_URL','').rstrip('/')
TOKEN = os.environ.get('DOCKOS_STAGING_BEARER','')
SECRET = os.environ.get('DOCKOS_STAGING_GATEWAY_SECRET','')
PREVIOUS_SECRET = os.environ.get('DOCKOS_STAGING_PREVIOUS_GATEWAY_SECRET','')
EMAIL = os.environ.get('DOCKOS_STAGING_USER_EMAIL','').strip().lower()
ROLE = os.environ.get('DOCKOS_STAGING_USER_ROLE','dockos_admin').strip().lower()
REQUIRE_READY = os.environ.get('DOCKOS_REQUIRE_READY','true').lower() == 'true'


def fail(message):
    raise SystemExit(message)


def require_inputs():
    missing=[]
    for name,value in [('DOCKOS_STAGING_URL',BASE),('DOCKOS_STAGING_BEARER',TOKEN),('DOCKOS_STAGING_GATEWAY_SECRET',SECRET),('DOCKOS_STAGING_USER_EMAIL',EMAIL)]:
        if not value: missing.append(name)
    if missing: fail('Missing staging acceptance inputs: '+', '.join(missing))
    if len(SECRET)<32: fail('DOCKOS_STAGING_GATEWAY_SECRET must be >=32 characters')


def signed_headers(path, method='GET', signing_secret=None, nonce=None, timestamp=None):
    signing_secret = signing_secret or SECRET
    nonce = nonce or secrets.token_hex(16)
    timestamp = timestamp or str(int(time.time()))
    authorization = f'Bearer {TOKEN}'
    auth_hash = hashlib.sha256(authorization.encode('utf-8')).hexdigest()
    canonical = f'{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{auth_hash}'.encode('utf-8')
    signature = hmac.new(signing_secret.encode('utf-8'),canonical,hashlib.sha256).hexdigest()
    return {
        'Authorization':authorization,
        'X-OPEX-User':EMAIL,
        'X-OPEX-Role':ROLE,
        'X-DockOS-Gateway':SECRET,
        'X-DockOS-Gateway-Timestamp':timestamp,
        'X-DockOS-Gateway-Nonce':nonce,
        'X-DockOS-Gateway-Signature':signature,
    }


def call(path, headers=None):
    request=urllib.request.Request(BASE+path,method='GET',headers=headers or {})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            return response.status,response.read().decode('utf-8')
    except urllib.error.HTTPError as error:
        return error.code,error.read().decode('utf-8')


def main():
    require_inputs()

    path='/api/dockos/live-purchase-orders'
    headers=signed_headers(path)
    status,body=call(path,headers)
    if status!=200: fail(f'CORPORATE_OIDC_GATEWAY=FAIL status={status} body={body[:500]}')
    payload=json.loads(body)
    if payload.get('source')!='BIGQUERY': fail(f'BIGQUERY_ONLY_PO=FAIL source={payload.get("source")}')
    print(f'CORPORATE_OIDC_GATEWAY=PASS user={EMAIL} role={ROLE}')
    print(f'BIGQUERY_ONLY_PO=PASS count={payload.get("count")} synced_at={payload.get("synced_at")}')

    replay_status,replay_body=call(path,headers)
    if replay_status!=401: fail(f'GATEWAY_REPLAY=FAIL status={replay_status} body={replay_body[:300]}')
    print('GATEWAY_REPLAY=PASS exact signed replay rejected')

    if PREVIOUS_SECRET:
        rotation_path='/api/dockos/ops/metrics'
        status,body=call(rotation_path,signed_headers(rotation_path,signing_secret=PREVIOUS_SECRET))
        if status!=200: fail(f'GATEWAY_ROTATION=FAIL status={status} body={body[:300]}')
        print('GATEWAY_ROTATION=PASS previous secret accepted during rotation window')
    else:
        print('GATEWAY_ROTATION=NOT_RUN no previous-secret acceptance input')

    metrics_path='/api/dockos/ops/metrics'
    status,body=call(metrics_path,signed_headers(metrics_path))
    if status!=200: fail(f'OBSERVABILITY=FAIL status={status}')
    required=[
        'dockos_reservation_latency_p95_ms','dockos_lock_wait_p95_ms','dockos_failed_bookings_total',
        'dockos_outbox_oldest_age_seconds','dockos_notification_retry_total','dockos_notification_dead_total',
        'dockos_bigquery_sync_lag_seconds','dockos_db_pool_saturation_ratio','dockos_db_pool_requests_waiting'
    ]
    missing=[metric for metric in required if metric not in body]
    if missing: fail('OBSERVABILITY=FAIL missing='+','.join(missing))
    print('OBSERVABILITY=PASS metrics=' + ','.join(required))

    readiness_status,readiness_body=call('/api/dockos/readiness')
    readiness=json.loads(readiness_body)
    failed=[item['key'] for item in readiness.get('checks',[]) if not item.get('ok')]
    print(f'PRODUCTION_READINESS status={readiness_status} ready={readiness.get("ready")} failed={failed}')
    if REQUIRE_READY and (readiness_status!=200 or not readiness.get('ready')):
        fail('PRODUCTION_READINESS=FAIL remaining='+','.join(failed))
    if readiness.get('ready'):
        print('PRODUCTION_READINESS=PASS')


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(f'STAGING_ACCEPTANCE_EXCEPTION={type(error).__name__}: {error}',file=sys.stderr)
        raise
