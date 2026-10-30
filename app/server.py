from __future__ import annotations
import asyncio, hashlib, json, secrets, shutil, threading, time, uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from .core import DATA, ROOT, init, db, config, password_ok, update_job, recover, audit
from .worker import loop
from .report import plain, docx_bytes, doc_bytes
from .claude_settings import public_settings, check_models, save_settings

LIMITS=defaultdict(list)
stop=threading.Event()
upload_lock=asyncio.Lock()

@asynccontextmanager
async def lifespan(app):
    init();recover();stop.clear()
    thread=threading.Thread(target=loop,args=(stop,),daemon=True);thread.start()
    yield
    stop.set()

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def headers(request,call_next):
    if request.headers.get('sec-fetch-site')=='cross-site' and request.method not in ('GET','HEAD'):
        return JSONResponse({'detail':'ไม่อนุญาตคำขอจากเว็บไซต์อื่น'},status_code=403)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
    return response

def session(request,write=False):
    token=request.cookies.get('meeting_session','')
    with db() as c:
        row=c.execute('SELECT s.*,u.admin FROM sessions s JOIN users u ON u.name=s.username WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    if not row:raise HTTPException(401,'กรุณาเข้าสู่ระบบ')
    if write and not secrets.compare_digest(request.headers.get('x-csrf-token',''),row['csrf']):raise HTTPException(403,'คำขอหมดอายุ กรุณาโหลดหน้าใหม่')
    return dict(row)

def authorized_job(request,jid,write=False):
    user=session(request,write)
    with db() as c:row=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
    if not row or (row['owner']!=user['username'] and not user['admin']):raise HTTPException(404,'ไม่พบงานหรือไม่มีสิทธิ์')
    return user,dict(row)

def administrator(request,write=False):
    s=session(request,write)
    if not s['admin']:raise HTTPException(403,'เฉพาะผู้ดูแลระบบเท่านั้น')
    return s

def secret_transport(request):
    # Loopback HTTP is allowed only when both the server bind and peer are local.
    # Trust no forwarded headers. Remote configuration requires actual TLS.
    local={'127.0.0.1','::1','localhost'}
    if request.url.scheme!='https' and not (request.client and request.client.host in local and config()['host'] in local):
        raise HTTPException(403,'การตั้งค่า Key ต้องใช้ HTTPS หรือเปิดจาก 127.0.0.1 บนเครื่องเซิร์ฟเวอร์')

async def small_json(request,limit=1000000):
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>limit:raise HTTPException(413,'ข้อมูลยาวเกินขอบเขต')
    try:
        obj=json.loads(body)
        if not isinstance(obj,dict):raise ValueError()
        return obj
    except (ValueError,UnicodeDecodeError):raise HTTPException(400,'รูปแบบ JSON ไม่ถูกต้อง')

@app.get('/')
def index():return FileResponse(ROOT/'web'/'index.html')

@app.get('/client.js')
def js():return FileResponse(ROOT/'web'/'client.js',media_type='text/javascript')

@app.get('/style.css')
def css():return FileResponse(ROOT/'web'/'style.css',media_type='text/css')

@app.get('/health')
def health():return {'status':'ok'}

@app.post('/api/login')
async def login(request:Request):
    data=await small_json(request,4000);ip=request.client.host
    now=time.time();LIMITS[ip]=[t for t in LIMITS[ip] if t>now-300]
    if len(LIMITS[ip])>=10:raise HTTPException(429,'ลองรหัสผ่านหลายครั้ง กรุณารอ 5 นาที')
    name=data.get('username','');password=data.get('password','')
    if not isinstance(name,str) or not isinstance(password,str):raise HTTPException(400,'ข้อมูลไม่ถูกต้อง')
    LIMITS[ip].append(now)
    with db() as c:row=c.execute('SELECT * FROM users WHERE name=?',(name,)).fetchone()
    # Same PBKDF work for unknown users to avoid a fast username oracle.
    dummy='0'*32+'$'+'0'*64
    valid=password_ok(password,row['password'] if row else dummy)
    if not row or not valid:raise HTTPException(401,'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
    LIMITS.pop(ip,None)
    token=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32)
    with db() as c:c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),name,csrf,now+8*3600))
    response=JSONResponse({'ok':True});response.set_cookie('meeting_session',token,httponly=True,secure=bool(config()['tls_cert']),samesite='lax',max_age=8*3600)
    audit(name,'login');return response

@app.get('/api/session')
def who(request:Request):
    s=session(request);cfg=config()
    return {'username':s['username'],'admin':bool(s['admin']),'csrf':s['csrf'],'summary_mode':cfg['summary_mode'],'summary_model':cfg['summary_model'],'max_upload_mb':cfg['max_upload_mb']}

@app.post('/api/logout')
def logout(request:Request):
    s=session(request,True)
    with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(s['token'],))
    r=JSONResponse({'ok':True});r.delete_cookie('meeting_session');return r

@app.get('/api/admin/claude')
def claude_config(request:Request):
    administrator(request);secret_transport(request)
    return public_settings()

STATUS_CACHE={'at':0.0,'payload':None}

@app.get('/api/admin/claude/status')
async def claude_status(request:Request,refresh:int=0):
    # Live connectivity check for the admin UI. Metadata endpoint only: no meeting
    # text is sent, and the key itself is never returned or logged.
    administrator(request);secret_transport(request)
    cfg=config();now=time.time()
    if not refresh and STATUS_CACHE['payload'] and now-STATUS_CACHE['at']<30:
        return STATUS_CACHE['payload']
    payload={'connected':False,'state':'disabled','model':cfg.get('summary_model',''),
             'checked_at':now,'latency_ms':None,'model_count':None,
             'message':'ปิดส่วนสรุปอยู่ ยังไม่ได้เชื่อมต่อ Claude API'}
    if cfg['summary_mode']=='anthropic':
        started=time.time()
        try:
            result=await asyncio.to_thread(check_models,{'api_key':'','workspace_id':cfg.get('anthropic_workspace_id',''),'model':cfg['summary_model']})
        except ValueError as exc:
            payload.update(state='failed',message=str(exc)[:300])
        except OSError:
            payload.update(state='failed',message='เชื่อมต่อผู้ให้บริการไม่ได้ ตรวจเครือข่ายของเซิร์ฟเวอร์')
        else:
            ids={m['id'] for m in result['models']}
            payload['model_count']=len(ids);payload['latency_ms']=int((time.time()-started)*1000)
            if cfg.get('summary_model') in ids:
                payload.update(connected=True,state='ready',message='เชื่อมต่อ Claude API ได้ และโมเดลที่ตั้งไว้มีในบัญชี')
            else:
                payload.update(state='model_missing',message='เชื่อมต่อได้ แต่ไม่พบโมเดลที่ตั้งไว้ในบัญชีนี้')
    payload['checked_at']=time.time()
    STATUS_CACHE.update(at=payload['checked_at'],payload=payload)
    return payload

@app.post('/api/admin/claude/test')
async def claude_test(request:Request):
    s=administrator(request,True);secret_transport(request)
    data=await small_json(request,8000)
    try:result=await asyncio.to_thread(check_models,data)
    except (ValueError,OSError):
        # No provider error body, request header, or key is reflected to callers.
        raise HTTPException(400,'ตรวจการเชื่อมต่อไม่ผ่าน กรุณาตรวจ Key, Workspace, สิทธิ์บัญชี และเครือข่ายเซิร์ฟเวอร์') from None
    audit(s['username'],'claude_api_metadata_test')
    return result

@app.post('/api/admin/claude')
async def claude_save(request:Request):
    s=administrator(request,True);secret_transport(request)
    data=await small_json(request,8000)
    try:return await asyncio.to_thread(save_settings,data,s['username'])
    except (ValueError,OSError):
        raise HTTPException(400,'บันทึกไม่สำเร็จ กรุณาตรวจ Key, โมเดล, นโยบายข้อมูล และสิทธิ์ Windows DPAPI บนเซิร์ฟเวอร์') from None

@app.get('/api/jobs')
def jobs(request:Request):
    s=session(request)
    with db() as c:
        rows=c.execute('SELECT id,title,owner,state,progress,error,created,updated FROM jobs '+('' if s['admin'] else 'WHERE owner=? ')+'ORDER BY created DESC LIMIT 200',() if s['admin'] else (s['username'],)).fetchall()
    return [dict(x) for x in rows]

@app.post('/api/jobs')
async def upload(request:Request):
    async with upload_lock:
        return await upload_file(request)

async def upload_file(request:Request):
    s=session(request,True);cfg=config();limit=int(cfg['max_upload_mb'])*1024*1024
    try:size=int(request.headers.get('content-length','-1'))
    except ValueError:raise HTTPException(400,'ขนาดไฟล์ไม่ถูกต้อง')
    if size<1 or size>limit:raise HTTPException(413,f'จำกัดไฟล์ {cfg["max_upload_mb"]} MB')
    from urllib.parse import unquote
    name=unquote(request.headers.get('x-filename','audio.mp3'))[:180]
    ext=Path(name).suffix.lower()
    if ext not in {'.mp3','.wav','.m4a','.mp4','.aac','.ogg','.flac','.webm','.wma'}:raise HTTPException(400,'ชนิดไฟล์ไม่รองรับ')
    with db() as c:count=c.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','transcribing','queued_summary','summarizing')").fetchone()[0]
    if count>=int(cfg['max_pending_jobs']):raise HTTPException(429,'คิวเต็ม กรุณารองานก่อน')
    if shutil.disk_usage(DATA).free<size+int(cfg['min_free_gb'])*1024**3:raise HTTPException(507,'พื้นที่ว่างไม่พอ กรุณาให้ผู้ดูแลตรวจสอบ')
    jid=uuid.uuid4().hex;path=DATA/'uploads'/(jid+ext);total=0
    try:
        with path.open('xb') as f:
            async for chunk in request.stream():
                total+=len(chunk)
                if total>limit:raise HTTPException(413,'ไฟล์ใหญ่เกินขอบเขต')
                f.write(chunk)
        if total!=size:raise HTTPException(400,'อัปโหลดไม่ครบ กรุณาลองใหม่')
        title=unquote(request.headers.get('x-title','')).strip()[:180] or Path(name).stem
        now=time.time()
        with db() as c:c.execute('INSERT INTO jobs(id,owner,title,filename,path,state,created,updated) VALUES(?,?,?,?,?,?,?,?)',(jid,s['username'],title,name,str(path),'queued',now,now))
    except BaseException:
        path.unlink(missing_ok=True);raise
    audit(s['username'],'upload',jid);return {'id':jid}

@app.get('/api/jobs/{jid}')
def detail(request:Request,jid:str):
    _,j=authorized_job(request,jid)
    j.pop('path');j['report_display']=plain(j)
    j['report']=json.loads(j['report']) if j['report'] else None
    return j

@app.post('/api/jobs/{jid}/summarize')
async def queue_summary(request:Request,jid:str):
    s,j=authorized_job(request,jid,True);cfg=config();data=await small_json(request)
    if j['state'] not in {'transcribed','draft','approved'}:raise HTTPException(409,'งานยังไม่พร้อมสรุป')
    if cfg['summary_mode']=='disabled':raise HTTPException(409,'ยังไม่เปิดโมเดลสรุป ให้ผู้ดูแลตั้งค่าบนเซิร์ฟเวอร์ก่อน')
    if cfg['summary_mode']=='anthropic' and (not cfg.get('cloud_allowed') or data.get('cloud_consent') is not True):raise HTTPException(403,'ต้องได้รับอนุญาตจากองค์กรและยืนยันส่งข้อความนี้ก่อนใช้ API')
    transcript=data.get('transcript',j['transcript'])
    if not isinstance(transcript,str) or not transcript.strip():raise HTTPException(400,'ไม่มีข้อความสำหรับสรุป')
    with db() as c:
        result=c.execute("UPDATE jobs SET edited=?,summary_mode=?,summary_model=?,summary_revision=?,state='queued_summary',report=NULL,report_text=NULL,revision=revision+1,error='',progress='รอคิวสรุป',updated=? WHERE id=? AND state IN ('transcribed','draft','approved')",(transcript,cfg['summary_mode'],cfg['summary_model'],int(cfg.get('summary_revision',0)),time.time(),jid))
        if not result.rowcount:raise HTTPException(409,'สถานะงานเปลี่ยนแล้ว กรุณาโหลดใหม่')
    audit(s['username'],'queue_summary_'+cfg['summary_mode'],jid);return {'ok':True}

@app.post('/api/jobs/{jid}/report')
async def save_report(request:Request,jid:str):
    s,j=authorized_job(request,jid,True);data=await small_json(request)
    if j['state'] not in {'draft','approved'}:raise HTTPException(409,'ยังไม่มีร่างรายงาน')
    report=data.get('text');revision=data.get('revision')
    if not isinstance(report,str) or not report.strip():raise HTTPException(400,'รายงานว่าง')
    with db() as c:
        result=c.execute("UPDATE jobs SET report_text=?,revision=revision+1,state='draft',progress='แก้รายงานแล้ว ต้องตรวจอนุมัติใหม่',updated=? WHERE id=? AND revision=? AND state IN ('draft','approved')",(report,time.time(),jid,revision))
        if not result.rowcount:raise HTTPException(409,'มีผู้อื่นแก้ไขแล้ว กรุณาโหลดใหม่ก่อนบันทึก')
    audit(s['username'],'edit_report',jid);return {'ok':True}

@app.post('/api/jobs/{jid}/transcript')
async def save_transcript(request:Request,jid:str):
    s,j=authorized_job(request,jid,True);data=await small_json(request)
    text=data.get('text')
    if not isinstance(text,str) or not text.strip():raise HTTPException(400,'ข้อความถอดเสียงว่าง')
    with db() as c:
        result=c.execute("UPDATE jobs SET edited=?,report=NULL,report_text=NULL,revision=revision+1,state='transcribed',progress='บันทึกข้อความตรวจแล้ว รอสรุป',updated=? WHERE id=? AND revision=? AND state IN ('transcribed','draft','approved')",(text,time.time(),jid,data.get('revision')))
        if not result.rowcount:raise HTTPException(409,'สถานะหรือข้อความเปลี่ยน กรุณาโหลดงานใหม่')
    audit(s['username'],'edit_transcript',jid);return {'ok':True}

@app.post('/api/jobs/{jid}/approve')
async def approve(request:Request,jid:str):
    s,j=authorized_job(request,jid,True);data=await small_json(request,1000)
    with db() as c:
        result=c.execute("UPDATE jobs SET state='approved',progress='ตรวจและอนุมัติแล้ว',updated=? WHERE id=? AND revision=? AND state='draft'",(time.time(),jid,data.get('revision')))
        if not result.rowcount:raise HTTPException(409,'รายงานเปลี่ยนหรือยังไม่เป็นฉบับร่าง กรุณาตรวจใหม่')
    audit(s['username'],'human_approved',jid);return {'ok':True}

@app.post('/api/jobs/{jid}/retry')
def retry(request:Request,jid:str):
    s,j=authorized_job(request,jid,True)
    if j['state']!='failed':raise HTTPException(409,'งานไม่ได้อยู่ในสถานะล้มเหลว')
    update_job(jid,state='queued',error='',progress='รอคิวลองถอดใหม่');audit(s['username'],'retry',jid);return {'ok':True}

@app.get('/api/jobs/{jid}/download/{kind}')
def download(request:Request,jid:str,kind:str):
    s,j=authorized_job(request,jid)
    if kind=='transcript':content=j['transcript'].encode('utf-8-sig');media='text/plain';ext='txt'
    elif kind=='json':
        content=json.dumps({'job_id':jid,'title':j['title'],'human_status':j['state'],'revision':j['revision'],'ai_report':json.loads(j['report']) if j['report'] else None,'reviewed_text':plain(j)},ensure_ascii=False,indent=2).encode('utf-8');media='application/json';ext='json'
    elif kind=='docx':
        if not j['report']:raise HTTPException(409,'ยังไม่มีรายงาน')
        content=docx_bytes(j,config()['font']);media='application/vnd.openxmlformats-officedocument.wordprocessingml.document';ext='docx'
    elif kind=='doc':
        # Legacy Word file for organizations that still standardize on .doc.
        if not j['report']:raise HTTPException(409,'ยังไม่มีรายงาน')
        content=doc_bytes(j,config()['font']);media='application/msword';ext='doc'
    elif kind=='report':content=plain(j).encode('utf-8-sig');media='text/plain';ext='txt'
    else:raise HTTPException(404,'ไม่พบรูปแบบไฟล์')
    audit(s['username'],'download_'+kind,jid)
    return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="meeting-{jid[:8]}-{kind}.{ext}"'})
