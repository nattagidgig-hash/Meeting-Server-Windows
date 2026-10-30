from __future__ import annotations
import hashlib, hmac, json, os, secrets, sqlite3, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('MEETING_DATA', ROOT / 'data')).resolve()
DEFAULT = {'host':'127.0.0.1','port':8765,'tls_cert':'','tls_key':'',
 'whisper_path':str(DATA/'models'/'whisper'),'language':'th','max_upload_mb':500,
 'max_pending_jobs':20,'min_free_gb':2,'summary_mode':'disabled','summary_model':'','whisper_threads':0,
 'cloud_allowed':False,'anthropic_workspace_id':'','summary_revision':0,'max_summary_chars':10000,
 'max_summary_chunks':30,'font':'Tahoma'}

def config():
    p=DATA/'config.json'
    return DEFAULT | (json.loads(p.read_text(encoding='utf-8')) if p.exists() else {})

def save_config(c):
    DATA.mkdir(parents=True,exist_ok=True)
    p=DATA/'config.json'; temp=p.with_suffix('.tmp')
    temp.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(p)

def db():
    con=sqlite3.connect(DATA/'meeting.db',timeout=30)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON'); con.execute('PRAGMA journal_mode=WAL')
    return con

def init():
    for p in [DATA,DATA/'uploads',DATA/'models',DATA/'backups']:p.mkdir(parents=True,exist_ok=True)
    if not (DATA/'config.json').exists():save_config(DEFAULT)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY,password TEXT NOT NULL,admin INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,username TEXT NOT NULL REFERENCES users(name),csrf TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(name),title TEXT NOT NULL,filename TEXT NOT NULL,path TEXT NOT NULL,state TEXT NOT NULL,progress TEXT NOT NULL DEFAULT '',transcript TEXT NOT NULL DEFAULT '',edited TEXT,report TEXT,report_text TEXT,summary_mode TEXT,summary_model TEXT,revision INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',created REAL NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at REAL NOT NULL,username TEXT NOT NULL,event TEXT NOT NULL,job TEXT NOT NULL DEFAULT '');
        ''')
        columns={row[1] for row in c.execute('PRAGMA table_info(jobs)')}
        if 'summary_revision' not in columns:
            c.execute('ALTER TABLE jobs ADD COLUMN summary_revision INTEGER NOT NULL DEFAULT 0')

MIN_PASSWORD_LENGTH=8
DEFAULT_ADMIN_USER='Admin'
DEFAULT_ADMIN_PASSWORD='11111111'

def password_hash(value):
    if len(value)<MIN_PASSWORD_LENGTH:raise ValueError(f'ใช้รหัสผ่านอย่างน้อย {MIN_PASSWORD_LENGTH} ตัวอักษร')
    salt=secrets.token_hex(16); digest=hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),600000).hex()
    return f'{salt}${digest}'

def password_ok(value,stored):
    try:
        salt,digest=stored.split('$',1)
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),600000).hex(),digest)
    except (ValueError,AttributeError):return False

def add_user(name,password,admin=False):
    if not name or len(name)>80 or any(x in name for x in '\r\n'):raise ValueError('ชื่อผู้ใช้ไม่ถูกต้อง')
    with db() as c:c.execute('INSERT INTO users VALUES(?,?,?)',(name,password_hash(password),int(admin)))

def audit(username,event,job=''):
    with db() as c:c.execute('INSERT INTO audit(at,username,event,job) VALUES(?,?,?,?)',(time.time(),username,event,job))

def update_job(jid,**fields):
    allowed={'state','progress','transcript','edited','report','report_text','summary_mode','summary_model','error','revision'}
    if not fields or not set(fields)<=allowed:raise ValueError('Invalid job update')
    fields['updated']=time.time()
    with db() as c:c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),jid))

def recover():
    with db() as c:
        c.execute("UPDATE jobs SET state='queued',progress='กู้คืนคิวถอดเสียงหลังเริ่มระบบ',updated=? WHERE state='transcribing'",(time.time(),))
        c.execute("UPDATE jobs SET state='transcribed',progress='งานสรุปถูกหยุด กรุณาตรวจข้อความและกดสรุปใหม่',updated=? WHERE state IN ('summarizing','queued_summary')",(time.time(),))
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))

def claim_job():
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT * FROM jobs WHERE state IN ('queued','queued_summary') ORDER BY updated LIMIT 1").fetchone()
        if not row:return None
        state='transcribing' if row['state']=='queued' else 'summarizing'
        c.execute('UPDATE jobs SET state=?,updated=? WHERE id=?',(state,time.time(),row['id']))
        return dict(row)|{'state':state}
