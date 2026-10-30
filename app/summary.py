from __future__ import annotations
import json
from pathlib import Path
import httpx
from .core import ROOT, DATA, audit, config
from .key_store import load_key, KEY_LOCK

def split_text(text,limit):
    # Preserve every character and the original timestamp locators across chunks.
    chunks=[]; remaining=text
    while len(remaining)>limit:
        cut=remaining.rfind('\n',0,limit)
        if cut<limit//2:cut=limit
        else:cut+=1
        chunks.append(remaining[:cut]);remaining=remaining[cut:]
    if remaining:chunks.append(remaining)
    return chunks

def system_prompt():
    root=ROOT/'skills'/'summarize-org-transcripts'
    return '\n\n'.join((root/p).read_text(encoding='utf-8') for p in ['SKILL.md','references/output-templates.md','references/app-output.md'])

def call_model(cfg,system,user):
    model=cfg['summary_model'].strip()
    if not model:raise ValueError('ยังไม่ได้กำหนดชื่อโมเดลสรุป')
    mode=cfg['summary_mode']
    with httpx.Client(timeout=httpx.Timeout(1200,connect=20),follow_redirects=False,trust_env=False) as client:
        if mode=='ollama':
            context=32768
            metadata=client.post('http://127.0.0.1:11434/api/show',json={'model':model})
            metadata.raise_for_status()
            info=metadata.json().get('model_info',{})
            capacities=[v for k,v in info.items() if k.endswith('.context_length') and isinstance(v,(int,float))]
            if not capacities or max(capacities)<context:
                raise ValueError('ยังยืนยันไม่ได้ว่าโมเดลในเครื่องรองรับ context 32768 กรุณาให้ผู้ดูแลเลือกโมเดลที่รองรับก่อน')
            # Conservative UTF-8 byte bound: fail closed rather than silently
            # relying on Ollama to truncate an overlong prompt.
            if len((system+user).encode('utf-8'))+6400>context:
                raise ValueError('ข้อความหรือบันทึกรวมยาวเกินขอบเขตโมเดลในเครื่อง กรุณาแบ่งเป็นงานย่อย ไม่ได้ส่งข้อความที่ถูกตัดไปสรุป')
            r=client.post('http://127.0.0.1:11434/api/chat',json={'model':model,'stream':False,'keep_alive':0,
              'messages':[{'role':'system','content':system},{'role':'user','content':user}],
              'options':{'temperature':0,'num_ctx':context,'num_predict':6000}})
            r.raise_for_status();obj=r.json()
            if obj.get('done_reason')=='length':raise ValueError('โมเดลสรุปตอบไม่ครบ ต้องลดขนาดช่วงหรือปรับโมเดล')
            return obj['message']['content']
        if mode=='anthropic':
            if not cfg.get('cloud_allowed'):raise ValueError('องค์กรยังไม่อนุญาตส่งข้อความออก')
            with KEY_LOCK:
                latest=config()
                if int(latest.get('summary_revision',0))!=int(cfg.get('summary_revision',0)) or latest['summary_mode']!='anthropic' or not latest['cloud_allowed']:
                    raise ValueError('การตั้งค่า API เปลี่ยนหรือถูกปิด กรุณาตรวจแล้วกดสรุปใหม่')
                key=load_key()
            if not key:raise ValueError('ยังไม่ได้ตั้งค่า API key บนเครื่องเซิร์ฟเวอร์')
            headers={'x-api-key':key,'anthropic-version':'2023-06-01'}
            if cfg.get('anthropic_workspace_id'):headers['anthropic-workspace-id']=cfg['anthropic_workspace_id']
            r=client.post('https://api.anthropic.com/v1/messages',headers=headers,json={'model':model,'max_tokens':6000,
             'system':system,'messages':[{'role':'user','content':user}]})
            r.raise_for_status();obj=r.json()
            if obj.get('stop_reason')=='max_tokens':raise ValueError('AI ตอบถูกตัด ยังไม่สามารถใช้เป็นรายงานครบถ้วน')
            return '\n'.join(x.get('text','') for x in obj.get('content',[]) if x.get('type')=='text')
    raise ValueError('ยังไม่ได้เปิดใช้ส่วนสรุป')

def parse_report(text):
    text=text.strip()
    if text.startswith('```'):
        text=text.split('\n',1)[1]
        if text.rstrip().endswith('```'):text=text.rstrip()[:-3]
    obj=json.loads(text)
    required=['summary','topics','decisions','proposals','actions','open_questions','review_notes']
    if not isinstance(obj,dict) or any(not isinstance(obj.get(k),list) for k in required):raise ValueError('AI ตอบไม่ตรงโครงสร้างรายงาน')
    if not isinstance(obj.get('metadata'),dict) or not isinstance(obj.get('coverage'),dict):raise ValueError('AI ตอบ metadata หรือ coverage ไม่ครบ')
    if not isinstance(obj.get('next_meeting'),dict):raise ValueError('AI ตอบข้อมูลนัดหมายไม่ตรงรูปแบบ')
    def refs(x):
        return isinstance(x.get('source_refs'),list) and all(isinstance(r,str) for r in x['source_refs'])
    for key in ['summary','decisions','proposals','open_questions','review_notes']:
        for item in obj[key]:
            if not isinstance(item,dict) or not isinstance(item.get('text'),str) or not refs(item):raise ValueError('รายการรายงานหรือแหล่งอ้างอิงไม่ตรงโครงสร้าง')
    for topic in obj['topics']:
        if not isinstance(topic,dict) or not isinstance(topic.get('title'),str) or not isinstance(topic.get('details'),list):raise ValueError('หัวข้อรายงานไม่ตรงโครงสร้าง')
        for d in topic['details']:
            if not isinstance(d,dict) or not isinstance(d.get('text'),str) or not refs(d):raise ValueError('รายละเอียดหัวข้อไม่ตรงโครงสร้าง')
    for action in obj['actions']:
        if not isinstance(action,dict) or not isinstance(action.get('task'),str) or not refs(action) or action.get('assignment_type') not in ['assigned','requested','committed']:raise ValueError('รายการงานที่ต้องทำไม่ตรงโครงสร้าง')
        for key in ['owner','due_text','due_date','status_text','conditions']:
            if action.get(key) is not None and not isinstance(action[key],str):raise ValueError('รายละเอียดงานที่ต้องทำไม่ตรงโครงสร้าง')
    # Never allow model output to act as human approval.
    obj['report_status']='draft'
    if obj.get('schema_version')!='1.0':raise ValueError('รูปแบบรายงานไม่ตรง schema 1.0')
    if len(json.dumps(obj,ensure_ascii=False))>800000:raise ValueError('รายงานใหญ่เกินขอบเขต')
    return obj

def summarize(cfg,title,transcript,owner,jid,progress):
    parts=split_text(transcript,min(4000,int(cfg['max_summary_chars'])) if cfg['summary_mode']=='ollama' else int(cfg['max_summary_chars']))
    if not parts:raise ValueError('ไม่มีข้อความสำหรับสรุป')
    if len(parts)>int(cfg['max_summary_chunks']):raise ValueError('ข้อความยาวเกินขอบเขตที่ตั้งไว้ กรุณาแบ่งงานก่อนสรุป')
    system=(ROOT/'skills'/'runtime-local.txt').read_text(encoding='utf-8') if cfg['summary_mode']=='ollama' else system_prompt()
    prefix='ชื่อเรื่องจากผู้ใช้: '+title+'\nวันประชุม: ไม่ระบุ เว้นแต่พบในต้นฉบับ\noutput_format=json\ndetail_level=detailed\nส่ง JSON ตามสัญญา app-output.md เท่านั้น\nห้ามอ้างอิงเวลาของเทปหรือเลขช่วงข้อความในรายงาน: source_refs ต้องเป็น [] เสมอ\n'
    partials=[]
    for i,part in enumerate(parts):
        progress(f'กำลังสรุปช่วง {i+1}/{len(parts)}')
        if cfg['summary_mode']=='anthropic':audit(owner,'cloud_summary_request',jid)
        instruction=prefix+f'\nช่วง {i+1}/{len(parts)}; '+('ข้อมูลทั้งหมดตามที่ได้รับ' if len(parts)==1 else 'เป็นเพียงบางส่วน ห้ามอ้างว่าครบทั้งงาน')+'\n<transcript>\n'+part+'\n</transcript>'
        partials.append(parse_report(call_model(cfg,system,instruction)))
    if len(partials)==1:return partials[0]
    evidence=json.dumps(partials,ensure_ascii=False)
    # Avoid silent truncation or pretending that only the first chunks were read.
    if len(evidence)>int(cfg['max_summary_chars'])*3:
        raise ValueError('บันทึกสรุปย่อยยาวเกินขอบเขตรวม กรุณาแบ่งการประชุมเป็นงานย่อย ไม่มีรายงานรวมที่สมบูรณ์')
    progress('กำลังรวมทุกช่วงและตรวจมติที่เปลี่ยนภายหลัง')
    if cfg['summary_mode']=='anthropic':audit(owner,'cloud_merge_request',jid)
    merged=parse_report(call_model(cfg,system,prefix+'\nรวมบันทึกหลักฐานจากทุกช่วงต่อไปนี้ ไม่เติมข้อมูล รักษา source_refs และข้อขัดแย้ง ลบรายการซ้ำ ใช้ข้อมูลแก้ไขล่าสุดเฉพาะเมื่อมีหลักฐานชัดเจน ระบุ review_notes ว่าเป็นรายงานรวมจากการแบ่งช่วง\n<chunk_reports>\n'+evidence+'\n</chunk_reports>'))
    merged['review_notes'].append({'text':f'รวมจากข้อความ {len(parts)} ช่วง ต้องตรวจความครบถ้วนและลำดับการเปลี่ยนมติกับต้นฉบับ','source_refs':[]})
    return merged
