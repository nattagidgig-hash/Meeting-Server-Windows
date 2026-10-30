import io, json, os, tempfile, time, unittest, zipfile
import httpx
from pathlib import Path
from unittest.mock import patch

temp=tempfile.TemporaryDirectory();os.environ['MEETING_DATA']=temp.name
from app.core import init, add_user, config, save_config, update_job, db, recover
from app.summary import split_text, parse_report
from app.server import app
from fastapi.testclient import TestClient

REPORT={'schema_version':'1.0','report_status':'approved','content_type':'meeting','detail_level':'detailed',
 'metadata':{'title':'ตัวอย่าง','date':None,'participants':[]},'coverage':{'status':'full','missing_parts':[]},'source_reference_method':'timestamps',
 'summary':[{'text':'ยังไม่อนุมัติงบประมาณ','source_refs':['00:00:00']}],'topics':[],'decisions':[],'proposals':[], 'actions':[],
 'open_questions':[],'next_meeting':{'time_text':None,'purpose':None,'source_refs':[]},'review_notes':[]}

class Integration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    init();add_user('alice','Alice-password-123');add_user('bob','Bob-password-123');add_user('admin','Admin-password-123',True)
    cls.asr=patch('app.worker.transcribe',return_value='[00:00:00–00:00:10] ยังไม่อนุมัติงบประมาณ');cls.asr.start()
    cls.model=patch('app.summary.call_model',return_value=json.dumps(REPORT,ensure_ascii=False));cls.mock_model=cls.model.start()
    cls.client=TestClient(app,base_url='https://testserver');cls.client.__enter__()
 @classmethod
 def tearDownClass(cls):cls.client.__exit__(None,None,None);cls.asr.stop();cls.model.stop()
 def login(self,name='alice'):
    self.client.cookies.clear();password={'alice':'Alice-password-123','bob':'Bob-password-123','admin':'Admin-password-123'}[name]
    self.assertEqual(self.client.post('/api/login',json={'username':name,'password':password}).status_code,200)
    return {'x-csrf-token':self.client.get('/api/session').json()['csrf']}
 def upload(self):
    headers=self.login();r=self.client.post('/api/jobs',content=b'RIFF test audio',headers=headers|{'x-filename':'sample.wav','x-title':'Test meeting','content-type':'application/octet-stream'})
    self.assertEqual(r.status_code,200);jid=r.json()['id'];self.wait(jid,'transcribed');return headers,jid
 def wait(self,jid,status):
    for _ in range(100):
        r=self.client.get('/api/jobs/'+jid).json()
        if r['state']==status:return r
        time.sleep(.04)
    self.fail('Job did not reach '+status+': '+str(r))
 def test_01_auth_csrf_and_file_validation(self):
    self.client.cookies.clear();self.assertEqual(self.client.get('/api/jobs').status_code,401)
    h=self.login();self.assertEqual(self.client.post('/api/jobs',content=b'x',headers={'x-filename':'x.wav'}).status_code,403)
    self.assertEqual(self.client.post('/api/jobs',content=b'x',headers=h|{'x-filename':'x.exe'}).status_code,400)
    self.assertEqual(self.client.post('/api/logout',headers=h|{'sec-fetch-site':'cross-site'}).status_code,403)
 def test_02_transcription_download_and_owner_isolation(self):
    _,jid=self.upload();r=self.client.get('/api/jobs/'+jid);self.assertIn('ยังไม่อนุมัติ',r.json()['transcript'])
    self.assertIn('ยังไม่อนุมัติ',self.client.get('/api/jobs/'+jid+'/download/transcript').text)
    self.login('bob');self.assertEqual(self.client.get('/api/jobs/'+jid).status_code,404);self.assertEqual(self.client.get('/api/jobs/'+jid+'/download/json').status_code,404)
    self.login('admin');self.assertEqual(self.client.get('/api/jobs/'+jid).status_code,200)
 def test_03_disabled_summary_and_explicit_cloud_gate(self):
    h,jid=self.upload();cfg=config();cfg.update(summary_mode='disabled');save_config(cfg)
    self.assertEqual(self.client.post('/api/jobs/'+jid+'/summarize',headers=h,json={}).status_code,409)
    cfg.update(summary_mode='anthropic',summary_model='test-approved-model',cloud_allowed=True);save_config(cfg)
    before=self.mock_model.call_count
    self.assertEqual(self.client.post('/api/jobs/'+jid+'/summarize',headers=h,json={'cloud_consent':False}).status_code,403)
    self.assertEqual(before,self.mock_model.call_count)
    self.assertEqual(self.client.post('/api/jobs/'+jid+'/summarize',headers=h,json={'cloud_consent':True}).status_code,200)
    job=self.wait(jid,'draft');self.assertEqual(job['report']['report_status'],'draft')
    self.assertEqual(self.client.post('/api/jobs/'+jid+'/approve',headers=h,json={'revision':-1}).status_code,409)
    self.assertEqual(self.client.post('/api/jobs/'+jid+'/approve',headers=h,json={'revision':job['revision']}).status_code,200)
    self.assertEqual(self.client.post('/api/jobs/'+jid+'/report',headers=h,json={'revision':job['revision'],'text':'ข้อความแก้ไขโดยคน'}).status_code,200)
    self.assertEqual(self.client.get('/api/jobs/'+jid).json()['state'],'draft')
    doc=self.client.get('/api/jobs/'+jid+'/download/docx')
    self.assertEqual(doc.status_code,200)
    with zipfile.ZipFile(io.BytesIO(doc.content)) as z:
        xml=z.read('word/document.xml').decode();self.assertIn('ข้อความแก้ไขโดยคน',xml);self.assertIn('Tahoma',xml);self.assertNotIn('00:00:00',xml)
    legacy=self.client.get('/api/jobs/'+jid+'/download/doc')
    self.assertEqual(legacy.status_code,200)
    self.assertEqual(legacy.headers['content-type'].split(';')[0],'application/msword')
    self.assertIn('.doc',legacy.headers['content-disposition'])
    self.assertTrue(legacy.content.startswith(b'{\\rtf1'))
    self.assertIn(b'\\u',legacy.content)
    payload=self.client.get('/api/jobs/'+jid+'/download/json').json();self.assertEqual(payload['human_status'],'draft')
    revision=self.client.get('/api/jobs/'+jid).json()['revision']
    self.assertEqual(self.client.post('/api/jobs/'+jid+'/transcript',headers=h,json={'text':'ข้อความต้นทางที่ตรวจแล้ว','revision':revision}).status_code,200)
    changed=self.client.get('/api/jobs/'+jid).json()
    self.assertEqual(changed['state'],'transcribed');self.assertIsNone(changed['report'])
    self.assertIn('ยังไม่อนุมัติ',changed['transcript']);self.assertEqual(changed['edited'],'ข้อความต้นทางที่ตรวจแล้ว')
 def test_04_chunking_and_schema_validation(self):
    text='first line\n'+'x'*35000+'\nสุดท้าย';parts=split_text(text,10000)
    self.assertEqual(''.join(parts),text);self.assertTrue(all(len(p)<=10000 for p in parts));self.assertGreater(len(parts),1)
    with self.assertRaises(ValueError):parse_report('{}')
    bad=dict(REPORT,actions=['not a valid action'])
    with self.assertRaises(ValueError):parse_report(json.dumps(bad))
 def test_05_restart_keeps_work_and_does_not_resend_cloud(self):
    _,jid=self.upload();update_job(jid,state='summarizing');recover()
    j=self.client.get('/api/jobs/'+jid).json();self.assertEqual(j['state'],'transcribed');self.assertTrue(j['transcript'])
 def test_06_lan_without_tls_is_rejected_before_starting_listener(self):
    import runpy
    cfg=config();original=dict(cfg);cfg.update(host='0.0.0.0',tls_cert='',tls_key='');save_config(cfg)
    try:
        with self.assertRaises(SystemExit) as caught:runpy.run_path(str(Path(__file__).resolve().parents[1]/'run.py'),run_name='__main__')
        self.assertIn('LAN requires',str(caught.exception))
    finally:save_config(original)
 def test_07_admin_settings_secret_storage_and_transport(self):
    from app import key_store
    from app.claude_settings import public_settings
    key='unit-test-key-not-a-real-credential'
    catalog={'models':[{'id':'test-model','name':'Test model'}],'has_more':False,'message':'metadata only'}
    user_headers=self.login('alice')
    self.assertEqual(self.client.get('/api/admin/claude').status_code,403)
    self.assertEqual(self.client.post('/api/admin/claude/test',headers=user_headers,json={'api_key':key}).status_code,403)
    headers=self.login('admin')
    self.assertEqual(self.client.post('/api/admin/claude/test',json={'api_key':key}).status_code,403)
    self.assertEqual(self.client.get('http://testserver/api/admin/claude').status_code,403)
    payload={'api_key':key,'workspace_id':'wrkspc_test','model':'test-model','enabled':True,'policy_ack':False}
    with patch('app.claude_settings.check_models',return_value=catalog) as checked:
        self.assertEqual(self.client.post('/api/admin/claude',headers=headers,json=payload).status_code,400)
        self.assertEqual(checked.call_count,0)
        payload['policy_ack']=True
        # Emulate native encryption on Linux; DPAPI itself must be tested on Windows.
        with patch('app.key_store._crypt',side_effect=lambda value,protect:value[::-1]):
            key_store.LEGACY.write_text(json.dumps({'anthropic_api_key':key}),encoding='utf-8')
            result=self.client.post('/api/admin/claude',headers=headers,json=payload)
            self.assertEqual(result.status_code,200);self.assertNotIn(key,result.text)
            self.assertEqual(result.json()['key_status'],'dpapi')
            self.assertEqual(key_store.load_key(),key)
            self.assertNotIn(key,key_store.PROTECTED.read_text())
            self.assertNotIn(key,key_store.LEGACY.read_text())
            self.assertNotIn(key,self.client.get('/api/admin/claude').text)
            old_revision=config()['summary_revision']
            payload['api_key']=''
            self.assertEqual(self.client.post('/api/admin/claude',headers=headers,json=payload).status_code,200)
            self.assertGreater(config()['summary_revision'],old_revision)
    # Disabling does not require a credential/network call and does not reveal it.
    result=self.client.post('/api/admin/claude',headers=headers,json={'enabled':False})
    self.assertEqual(result.status_code,200);self.assertFalse(result.json()['enabled']);self.assertNotIn(key,result.text)
    with db() as c:
        audit_text=str([tuple(x) for x in c.execute('SELECT * FROM audit')])
        self.assertNotIn(key,audit_text)
 def test_08_metadata_check_sends_no_meeting_and_returns_no_key(self):
    from app.claude_settings import check_models
    key='unit-test-key-not-a-real-credential';seen=[]
    def responder(request):
        seen.append(request)
        return httpx.Response(200,json={'data':[{'id':'test-model','display_name':'Test'},{'id':'old-model','lifecycle':'retired'}],'has_more':False})
    fake=httpx.Client(transport=httpx.MockTransport(responder))
    with patch('app.claude_settings.httpx.Client',return_value=fake):
        result=check_models({'api_key':key,'workspace_id':'wrkspc_test'})
    self.assertEqual(len(seen),1);self.assertEqual(seen[0].method,'GET');self.assertEqual(seen[0].url.host,'api.anthropic.com')
    self.assertEqual(seen[0].content,b'');self.assertEqual(seen[0].headers['x-api-key'],key)
    self.assertEqual(result['models'],[{'id':'test-model','name':'Test'}]);self.assertNotIn(key,json.dumps(result))
 def test_09_provider_error_does_not_echo_credentials(self):
    headers=self.login('admin');key='unit-test-key-not-a-real-credential'
    with patch('app.server.check_models',side_effect=ValueError('provider message '+key)):
        result=self.client.post('/api/admin/claude/test',headers=headers,json={'api_key':key})
    self.assertEqual(result.status_code,400);self.assertNotIn(key,result.text)

 def test_10_api_status_endpoint(self):
    self.client.cookies.clear();self.assertEqual(self.client.get('/api/admin/claude/status').status_code,401)
    headers=self.login('alice');self.assertEqual(self.client.get('/api/admin/claude/status',headers=headers).status_code,403)
    self.login('admin');r=self.client.get('/api/admin/claude/status');self.assertEqual(r.status_code,200);body=r.json()
    self.assertIn(body['state'],{'disabled','ready','failed','model_missing'})
    self.assertIn('connected',body);self.assertIn('checked_at',body)
    self.assertNotIn('unit-test-key',r.text)
    self.assertFalse(body['connected'] and body['state']=='disabled')

if __name__=='__main__':unittest.main(verbosity=2)
