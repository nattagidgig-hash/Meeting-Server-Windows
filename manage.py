from __future__ import annotations
import argparse, getpass, json, os, shutil, sqlite3, sys, time
from pathlib import Path
from app.core import DATA, ROOT, DEFAULT, init, config, save_config, db, add_user, password_hash, audit, DEFAULT_ADMIN_USER, DEFAULT_ADMIN_PASSWORD

def confirmed_password():
    password=getpass.getpass('Password (12+ characters, hidden): ')
    if password!=getpass.getpass('Repeat password: '):raise ValueError('Passwords do not match')
    return password

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['init','add-user','reset-password','download-model','summary','check','lan','backup','purge-job'])
    parser.add_argument('--cert');parser.add_argument('--key');parser.add_argument('--job');parser.add_argument('--confirm',action='store_true')
    args=parser.parse_args();init();cfg=config()
    if args.command=='init':
        with db() as c:count=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if not count:
            # Default account so a fresh install can log in immediately.
            name=os.environ.get('MEETING_ADMIN_USER',DEFAULT_ADMIN_USER).strip() or DEFAULT_ADMIN_USER
            add_user(name,os.environ.get('MEETING_ADMIN_PASSWORD',DEFAULT_ADMIN_PASSWORD),True)
            print('Default administrator created:',name)
            print('Initial password is printed in START-HERE-TH.md only, never in the web app.')
            print('Change it now with: manage.py reset-password')
        else:print('Existing configuration and accounts preserved.')
    elif args.command=='add-user':
        name=input('New username: ').strip();admin=input('Administrator can view all jobs. Make admin? [y/N]: ').strip().lower()=='y';add_user(name,confirmed_password(),admin);print('User created.')
    elif args.command=='reset-password':
        name=input('Username to reset: ').strip();hashed=password_hash(confirmed_password())
        with db() as c:
            result=c.execute('UPDATE users SET password=? WHERE name=?',(hashed,name))
            if not result.rowcount:raise ValueError('User not found')
            c.execute('DELETE FROM sessions WHERE username=?',(name,))
        print('Password changed; existing sessions revoked.')
    elif args.command=='download-model':
        from huggingface_hub import snapshot_download
        print('Downloading Whisper small multilingual from Systran/faster-whisper-small. Internet required for this step.')
        snapshot_download('Systran/faster-whisper-small',local_dir=cfg['whisper_path'])
        from faster_whisper import WhisperModel
        m=WhisperModel(cfg['whisper_path'],device='cpu',compute_type='int8',local_files_only=True);del m
        print('Model downloaded and CPU INT8 load verified.')
    elif args.command=='summary':
        print('1 = Disabled (transcription only)\n3 = Claude API (Anthropic) — recommended for this project')
        choice=input('Mode [1]: ').strip() or '1'
        mode={'1':'disabled','3':'anthropic'}.get(choice)
        if mode is None:raise ValueError('Invalid choice')
        cfg['summary_mode']=mode;cfg['cloud_allowed']=False
        if mode!='disabled':
            model=input('Exact approved/installed model name: ').strip()
            if not model:raise ValueError('Model name required; no unverified default is chosen')
            cfg['summary_model']=model
        if mode=='anthropic':
            print('Transcript text WILL leave the organization. Verify commercial account, model, retention, and organization approval first.')
            if input('Type ALLOW-CLOUD to confirm organization authorization: ').strip()!='ALLOW-CLOUD':raise ValueError('Cloud authorization not confirmed; configuration unchanged')
            key=getpass.getpass('Anthropic API key (hidden): ').strip()
            if not key:raise ValueError('API key required')
            from app.key_store import save_key
            save_key(key)
            cfg['cloud_allowed']=True;cfg['anthropic_workspace_id']=input('Workspace ID if required (blank if not): ').strip()
        cfg['summary_revision']=int(cfg.get('summary_revision',0))+1
        save_config(cfg);audit('local-operator','summary_configuration_changed');print('Summary settings saved. Log out/in or refresh browser to update the displayed mode.')
    elif args.command=='lan':
        if not args.cert or not args.key:raise ValueError('Provide organization-trusted PEM certificate and private-key paths')
        cert=Path(args.cert).resolve();key=Path(args.key).resolve()
        if not cert.is_file() or not key.is_file():raise ValueError('Certificate or key not found')
        import ssl
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(str(cert),str(key))
        cfg.update(host='0.0.0.0',tls_cert=str(cert),tls_key=str(key));save_config(cfg)
        print('HTTPS LAN configuration saved. Restart server. Certificate hostname/IP must match what clients open.')
    elif args.command=='check':
        print('Python:',sys.version.split()[0]);print('Data directory:',DATA);print('Bind:',cfg['host'],cfg['port']);print('TLS:',bool(cfg['tls_cert']));print('Summary:',cfg['summary_mode']);print('Free disk GB:',round(shutil.disk_usage(DATA).free/1024**3,1))
        print('Whisper model prepared:',(Path(cfg['whisper_path'])/'model.bin').exists())
        for name in ['fastapi','uvicorn','httpx','docx','faster_whisper']:
            import importlib.util
            print(name+':',bool(importlib.util.find_spec(name)))
        with db() as c:print('User accounts:',c.execute('SELECT COUNT(*) FROM users').fetchone()[0])
        print('No API key, password, transcript, or network request is printed by this check.')
    elif args.command=='backup':
        if not args.confirm:raise ValueError('Backups contain meeting data. Use --confirm after choosing an authorized storage destination.')
        folder=DATA/'backups'/time.strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True)
        with db() as source,sqlite3.connect(folder/'meeting.db') as target:source.backup(target)
        shutil.copytree(DATA/'uploads',folder/'uploads');shutil.copy(DATA/'config.json',folder/'config.json')
        print('Backup created at',folder,'; secrets and model files are not included. Restrict access and copy to approved separate storage.')
    elif args.command=='purge-job':
        if not args.confirm or not args.job:raise ValueError('This permanently deletes one meeting. Require --job ID --confirm after policy/backup review.')
        with db() as c:
            job=c.execute('SELECT * FROM jobs WHERE id=?',(args.job,)).fetchone()
            if not job:raise ValueError('Job not found')
            if job['state'] in {'queued','transcribing','queued_summary','summarizing'}:raise ValueError('Cannot delete an active job')
            c.execute('DELETE FROM jobs WHERE id=?',(args.job,))
        path=Path(job['path']).resolve()
        if path.parent==(DATA/'uploads').resolve():path.unlink(missing_ok=True)
        audit('local-operator','purged_job',args.job);print('Meeting and audio removed from the live database; existing backups are separate.')

if __name__=='__main__':
    try:main()
    except (ValueError,sqlite3.Error,FileNotFoundError) as exc:raise SystemExit(str(exc))
