"""Provider settings and metadata checks. Never log or return credential values."""
import re
import httpx
from .core import config, save_config, audit
from .key_store import KEY_LOCK, load_key, save_key, key_status

def public_settings():
    c=config()
    return {'enabled':c['summary_mode']=='anthropic','summary_mode':c['summary_mode'],
      'model':c['summary_model'] if c['summary_mode']=='anthropic' else '',
      'workspace_id':c.get('anthropic_workspace_id',''), 'cloud_allowed':bool(c.get('cloud_allowed')),
      'key_status':key_status(),'has_key':key_status()!='missing'}

def input_settings(data):
    raw=data.get('api_key','');workspace=data.get('workspace_id','');model=data.get('model','')
    if not isinstance(raw,str) or len(raw)>1024 or any(c.isspace() for c in raw):raise ValueError('รูปแบบ API key ไม่ถูกต้อง')
    if not isinstance(workspace,str) or len(workspace)>180 or not re.fullmatch(r'[A-Za-z0-9_-]*',workspace):raise ValueError('Workspace ID ไม่ถูกต้อง')
    if not isinstance(model,str) or len(model)>180 or not re.fullmatch(r'[A-Za-z0-9_.:-]*',model):raise ValueError('Model ID ไม่ถูกต้อง')
    key=raw or load_key()
    if not key:raise ValueError('กรุณาใส่ API key จาก Claude Console')
    return key,workspace,model

def check_models(data):
    key,workspace,_=input_settings(data)
    headers={'x-api-key':key,'anthropic-version':'2023-06-01'}
    if workspace:headers['anthropic-workspace-id']=workspace
    try:
        with httpx.Client(timeout=httpx.Timeout(25,connect=10),follow_redirects=False,trust_env=False) as client:
            r=client.get('https://api.anthropic.com/v1/models',headers=headers,params={'limit':1000})
            if r.status_code==401:raise ValueError('API key ไม่ถูกต้องหรือหมดอายุ กรุณาตรวจใน Claude Console')
            if r.status_code==403:raise ValueError('บัญชีหรือ Workspace ไม่มีสิทธิ์อ่านโมเดล กรุณาตรวจสิทธิ์ API')
            if r.status_code==429:raise ValueError('ผู้ให้บริการจำกัดคำขอ กรุณารอสักครู่แล้วลองใหม่')
            if not r.is_success:raise ValueError('Claude API ตอบข้อผิดพลาด กรุณาตรวจบัญชี Workspace และสถานะบริการ')
            obj=r.json()
    except (httpx.HTTPError,ValueError) as exc:
        if isinstance(exc,ValueError) and not isinstance(exc,httpx.HTTPError):raise
        raise ValueError('เชื่อมต่อ Claude API ไม่สำเร็จ กรุณาตรวจเครือข่ายของเซิร์ฟเวอร์') from None
    if not isinstance(obj,dict) or not isinstance(obj.get('data'),list):raise ValueError('Claude API ตอบรายการโมเดลไม่ถูกต้อง')
    models=[{'id':m['id'],'name':m.get('display_name') or m['id']} for m in obj['data']
      if isinstance(m,dict) and isinstance(m.get('id'),str) and m.get('lifecycle')!='retired']
    return {'models':models,'has_more':bool(obj.get('has_more')),
     'message':'เชื่อมต่อและอ่านรายการโมเดลได้ ยังไม่ได้ทดสอบการสรุปหรือยืนยันว่าวงเงินเพียงพอ'}

def save_settings(data,username):
    with KEY_LOCK:
        if data.get('enabled') is False:
            c=config()
            if c['summary_mode']=='anthropic':c.update(summary_mode='disabled',cloud_allowed=False,summary_revision=int(c.get('summary_revision',0))+1);save_config(c)
            audit(username,'claude_api_disabled')
            return public_settings()
        if data.get('enabled') is not True:raise ValueError('กรุณาระบุว่าจะเปิดใช้ Claude API หรือไม่')
        if data.get('policy_ack') is not True:raise ValueError('ต้องยืนยันนโยบายส่งข้อความออกก่อนเปิดใช้ API')
        key,workspace,model=input_settings(data)
        if not model:raise ValueError('กรุณาเลือกหรือระบุ Model ID')
        # Metadata only: do not submit any meeting or create billable inference here.
        result=check_models(data)
        if model not in {m['id'] for m in result['models']}:
            raise ValueError('โมเดลนี้ไม่อยู่ในรายการที่บัญชีนี้อ่านได้ กรุณาเลือกรหัสจากรายการที่โหลด')
        save_key(key)
        c=config();c.update(summary_mode='anthropic',summary_model=model,anthropic_workspace_id=workspace,cloud_allowed=True,summary_revision=int(c.get('summary_revision',0))+1)
        save_config(c);audit(username,'claude_api_settings_saved')
        return public_settings()
