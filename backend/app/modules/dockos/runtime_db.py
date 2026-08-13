import os
from psycopg_pool import ConnectionPool

_POOL = None

def enabled():
    return os.getenv('DOCKOS_PERSISTENCE','json').lower() == 'postgres'

def pool():
    global _POOL
    if _POOL is None:
        url = os.getenv('DATABASE_URL','').strip()
        if not url:
            raise RuntimeError('DATABASE_URL required')
        _POOL = ConnectionPool(url, min_size=1, max_size=20, open=True)
    return _POOL
