import gc, json, os, threading
from pathlib import Path
from .core import config, claim_job, update_job, audit
from .summary import summarize

def stamp(t):
    t=max(0,int(t));return f'{t//3600:02}:{t//60%60:02}:{t%60:02}'

def transcribe(job,cfg):
    from faster_whisper import WhisperModel
    threads=int(cfg.get('whisper_threads') or 0) or max(1,min(8,(os.cpu_count() or 4)-2))
    model=WhisperModel(cfg['whisper_path'],device='cpu',compute_type='int8',cpu_threads=threads,local_files_only=True)
    lines=[]
    try:
        segments,info=model.transcribe(job['path'],language=cfg['language'] or None,vad_filter=True,beam_size=5)
        for i,seg in enumerate(segments):
            lines.append(f'[{stamp(seg.start)}–{stamp(seg.end)}] {seg.text.strip()}')
            if i%10==0:update_job(job['id'],progress='ถอดเสียงถึง '+stamp(seg.end))
        if not lines:raise ValueError('ไม่พบคำพูดในไฟล์ หรือเสียงไม่สามารถถอดได้')
        return '\n'.join(lines)
    finally:
        del model;gc.collect()

def loop(stop:threading.Event):
    while not stop.is_set():
        job=claim_job()
        if not job:stop.wait(1);continue
        try:
            cfg=config()
            if job['state']=='transcribing':
                update_job(job['id'],progress='เริ่มถอดเสียงด้วย Whisper CPU INT8',error='')
                transcript=transcribe(job,cfg)
                update_job(job['id'],transcript=transcript,state='transcribed',progress='ถอดเสียงเสร็จ กรุณาตรวจข้อความก่อนสรุป')
                audit(job['owner'],'transcription_completed',job['id'])
            else:
                if cfg['summary_mode']!=job['summary_mode'] or cfg['summary_model']!=job['summary_model'] or int(cfg.get('summary_revision',0))!=job.get('summary_revision',0):
                    raise ValueError('การตั้งค่าโมเดลเปลี่ยนหลังจัดคิว กรุณาตรวจและกดสรุปใหม่')
                report=summarize(cfg,job['title'],job['edited'] if job['edited'] is not None else job['transcript'],job['owner'],job['id'],lambda p:update_job(job['id'],progress=p))
                update_job(job['id'],report=json.dumps(report,ensure_ascii=False),report_text=None,state='draft',progress='ร่างสรุปพร้อมตรวจทาน',error='')
                audit(job['owner'],'summary_draft_created',job['id'])
        except Exception as exc:
            # Avoid recording provider bodies or raw transcripts/API keys in logs.
            if isinstance(exc,ValueError):message=str(exc)[:500]
            else:message='ประมวลผลไม่สำเร็จ ('+type(exc).__name__+') ตรวจไฟล์ โมเดล หรือการตั้งค่าบนเซิร์ฟเวอร์'
            update_job(job['id'],state='transcribed' if job['state']=='summarizing' else 'failed',error=message,progress='ต้องตรวจสอบก่อนลองใหม่')
            audit(job['owner'],'processing_failed',job['id'])
