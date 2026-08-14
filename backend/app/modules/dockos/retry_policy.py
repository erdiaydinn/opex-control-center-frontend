import os

def next_retry_seconds(attempts:int)->int:
    base=max(5,int(os.getenv('DOCKOS_NOTIFICATION_RETRY_BASE_SECONDS','30')))
    return min(3600,base*(2**max(0,min(attempts,7))))

def terminal(attempts:int)->bool:
    return attempts>=max(1,int(os.getenv('DOCKOS_NOTIFICATION_MAX_ATTEMPTS','8')))
