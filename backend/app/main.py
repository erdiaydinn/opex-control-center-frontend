import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.modules.dockos.identity import authenticate_request, verify_gateway
from app.modules.dockos.persistence import persistence_mode, refresh_state
from app.modules.dockos.router import router as dockos_router

PROD=os.getenv('DOCKOS_ENV','development').lower()=='production'
if PROD:
    os.environ['DOCKOS_TRUST_ROLE_HEADER']='true'

def _cors_origins():
    raw=os.getenv('OPEX_CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080')
    return [x.strip() for x in raw.split(',') if x.strip()]

app=FastAPI(title='EAY Platform API',version='8.0.0-production-candidate',docs_url=None if PROD else '/api/docs',redoc_url=None,openapi_url=None if PROD else '/api/openapi.json')
app.add_middleware(CORSMiddleware,allow_origins=_cors_origins(),allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],allow_headers=['Accept','Content-Type','Authorization','X-OPEX-User','X-OPEX-Role','X-DockOS-Gateway','X-DockOS-Gateway-Timestamp','X-DockOS-Gateway-Signature'])

@app.middleware('http')
async def production_identity(request:Request,call_next):
    protected=request.url.path.startswith('/api/dockos') and not request.url.path.endswith('/health') and not request.url.path.endswith('/readiness')
    try:
        if PROD and protected:
            verify_gateway(request)
            identity=authenticate_request(request)
            header_email=(request.headers.get('X-OPEX-User') or '').strip().lower()
            header_role=(request.headers.get('X-OPEX-Role') or '').strip().lower()
            if header_email!=identity.email or header_role!=identity.role:
                raise HTTPException(401,'Gateway identity ile OIDC identity eşleşmiyor.')
            refresh_state()
        elif persistence_mode()=='postgres' and request.url.path.startswith('/api/dockos'):
            refresh_state()
        return await call_next(request)
    except HTTPException as error:
        return JSONResponse({'detail':error.detail},status_code=error.status_code)
    except RuntimeError as error:
        return JSONResponse({'detail':str(error)},status_code=503)

app.include_router(dockos_router,prefix='/api')

@app.get('/health',include_in_schema=False)
def root_health():
    return {'status':'ok','service':'eay-platform-backend','release':'RC8','persistence':persistence_mode()}
