import os
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from app.modules.dockos import service as dockos_service
from app.modules.dockos import router as dockos_router_module
from app.modules.dockos.identity import authenticate_request, verify_gateway, set_identity, reset_identity
from app.modules.dockos.observability import record_reservation, render_prometheus, snapshot
from app.modules.dockos.persistence import persistence_mode, refresh_state
from app.modules.dockos.production_runtime import install_service_security, readiness_checks, sync_bigquery_purchase_orders
from app.modules.dockos.router import router as dockos_router
from app.modules.dockos.runtime_db import pool as db_pool

PROD=os.getenv('DOCKOS_ENV','development').lower()=='production'
if PROD:
    os.environ['DOCKOS_TRUST_ROLE_HEADER']='true'
    install_service_security(dockos_service)
    dockos_router_module.is_admin=dockos_service.is_admin
    def _production_live_pos(supplier_name=None, warehouse_name=None, user_email=None, user_role=None):
        if supplier_name:
            dockos_service.assert_supplier_access(user_email, supplier_name, user_role)
        return sync_bigquery_purchase_orders(dockos_service, supplier_name, warehouse_name)
    dockos_router_module.get_live_purchase_orders=_production_live_pos
    dockos_service.get_live_purchase_orders=_production_live_pos


def _cors_origins():
    raw=os.getenv('OPEX_CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080')
    return [x.strip() for x in raw.split(',') if x.strip()]


def _pool_stats():
    if persistence_mode()!='postgres':
        return {}
    try:
        return db_pool().get_stats()
    except Exception:
        return {}


app=FastAPI(title='EAY Platform API',version='8.0.0-production-candidate',docs_url=None if PROD else '/api/docs',redoc_url=None,openapi_url=None if PROD else '/api/openapi.json')
app.add_middleware(CORSMiddleware,allow_origins=_cors_origins(),allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],allow_headers=['Accept','Content-Type','Authorization','X-OPEX-User','X-OPEX-Role','X-DockOS-Gateway','X-DockOS-Gateway-Timestamp','X-DockOS-Gateway-Signature'])


@app.middleware('http')
async def production_identity(request:Request,call_next):
    path=request.url.path
    started=time.perf_counter()
    status_code=500
    identity_token=None
    if path=='/api/dockos/readiness':
        try:
            if persistence_mode()=='postgres': refresh_state()
            checks=readiness_checks(dockos_service)
            slo=snapshot(dockos_service,_pool_stats())
            status_code=200 if all(item['ok'] for item in checks) else 503
            return JSONResponse({'ready':status_code==200,'release':'RC8-production-candidate','checks':checks,'slo':slo},status_code=status_code)
        except Exception as error:
            status_code=503
            return JSONResponse({'ready':False,'release':'RC8-production-candidate','checks':[{'key':'readiness','ok':False,'detail':str(error)[:300]}]},status_code=503)
    protected=path.startswith('/api/dockos') and not path.endswith('/health')
    try:
        if PROD and protected:
            verify_gateway(request)
            identity=authenticate_request(request)
            identity_token=set_identity(identity)
            header_email=(request.headers.get('X-OPEX-User') or '').strip().lower()
            header_role=(request.headers.get('X-OPEX-Role') or '').strip().lower()
            if header_email!=identity.email or header_role!=identity.role:
                raise HTTPException(401,'Gateway identity ile OIDC identity eşleşmiyor.')
            refresh_state()
        elif persistence_mode()=='postgres' and path.startswith('/api/dockos'):
            refresh_state()
        response=await call_next(request)
        status_code=response.status_code
        if PROD:
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['Referrer-Policy']='no-referrer'
            response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        return response
    except HTTPException as error:
        status_code=error.status_code
        return JSONResponse({'detail':error.detail},status_code=error.status_code)
    except PermissionError as error:
        status_code=403
        return JSONResponse({'detail':str(error)},status_code=403)
    except ValueError as error:
        status_code=400
        return JSONResponse({'detail':str(error)},status_code=400)
    except RuntimeError as error:
        status_code=503
        return JSONResponse({'detail':str(error)},status_code=503)
    finally:
        if identity_token is not None:
            reset_identity(identity_token)
        if request.method.upper()=='POST' and path=='/api/dockos/reservations':
            record_reservation((time.perf_counter()-started)*1000.0,status_code<400)


@app.get('/api/dockos/ops/metrics',include_in_schema=False)
def dockos_metrics():
    return PlainTextResponse(render_prometheus(snapshot(dockos_service,_pool_stats())),media_type='text/plain; version=0.0.4')


app.include_router(dockos_router,prefix='/api')


@app.get('/health',include_in_schema=False)
def root_health():
    return {'status':'ok','service':'eay-platform-backend','release':'RC8','persistence':persistence_mode()}
