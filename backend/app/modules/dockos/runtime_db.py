import os
from psycopg_pool import ConnectionPool

_POOL=None
_OWNER_PID=None

def enabled(): return os.getenv('DOCKOS_PERSISTENCE','json').lower()=='postgres'

def pool():
    global _POOL,_OWNER_PID
    pid=os.getpid()
    if _OWNER_PID not in (None,pid):
        _POOL=None
    if _POOL is None:
        url=os.getenv('DATABASE_URL','').strip()
        if not url: raise RuntimeError('DATABASE_URL required')
        _POOL=ConnectionPool(url,min_size=1,max_size=20,open=True)
        _OWNER_PID=pid
    return _POOL
