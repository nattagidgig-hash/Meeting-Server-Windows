from pathlib import Path
from app.core import DATA, init, config

def lock():
    handle=(DATA/'server.lock').open('a+b')
    handle.seek(0);handle.write(b'1');handle.flush();handle.seek(0)
    import os
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    return handle

if __name__=='__main__':
    init();cfg=config()
    if cfg['host'] not in {'127.0.0.1','::1','localhost'} and not (cfg['tls_cert'] and cfg['tls_key']):
        raise SystemExit('LAN requires an organization-trusted TLS certificate and key. Use Enable-LAN.ps1.')
    if bool(cfg['tls_cert'])!=bool(cfg['tls_key']):raise SystemExit('TLS certificate/key must be configured together')
    try:held_lock=lock()
    except OSError:raise SystemExit('Another Meeting Server process is already running.')
    import uvicorn
    uvicorn.run('app.server:app',host=cfg['host'],port=int(cfg['port']),workers=1,access_log=False,
       ssl_certfile=cfg['tls_cert'] or None,ssl_keyfile=cfg['tls_key'] or None,log_level='warning')
