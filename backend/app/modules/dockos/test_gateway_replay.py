import hashlib
import hmac
import os
import time

from fastapi import HTTPException
from starlette.requests import Request

os.environ['DOCKOS_ENV'] = 'production'
os.environ['DOCKOS_PERSISTENCE'] = 'postgres'
os.environ['DOCKOS_TENANT_KEY'] = 'ys_tr'
os.environ['DOCKOS_GATEWAY_TRUST_MODE'] = 'hmac'
os.environ['DOCKOS_GATEWAY_SECRET'] = 'A' * 48
os.environ['DOCKOS_GATEWAY_PREVIOUS_SECRET'] = 'B' * 48

from .identity import verify_gateway


def request_for(secret: str, nonce: str):
    timestamp = str(int(time.time()))
    token = 'Bearer staging-token-placeholder'
    path = '/api/dockos/reservations'
    auth_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    canonical = f'{timestamp}\n{nonce}\nGET\n{path}\n{auth_hash}'.encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), canonical, hashlib.sha256).hexdigest()
    headers = [
        (b'authorization', token.encode()),
        (b'x-dockos-gateway-timestamp', timestamp.encode()),
        (b'x-dockos-gateway-nonce', nonce.encode()),
        (b'x-dockos-gateway-signature', signature.encode()),
    ]
    scope = {'type':'http','method':'GET','path':path,'raw_path':path.encode(),'query_string':b'','headers':headers,'scheme':'https','server':('staging',443),'client':('127.0.0.1',12345),'root_path':''}
    return Request(scope)


def main():
    first = request_for('A' * 48, 'nonce-primary-00000001')
    verify_gateway(first)
    try:
        verify_gateway(first)
        raise AssertionError('exact replay was accepted')
    except HTTPException as error:
        assert error.status_code == 401 and 'replay' in str(error.detail).lower(), error.detail

    previous = request_for('B' * 48, 'nonce-previous-000001')
    verify_gateway(previous)
    print('GATEWAY_REPLAY_ROTATION=PASS')


if __name__ == '__main__':
    main()
