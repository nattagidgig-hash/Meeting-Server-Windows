'use strict';
let me=null,current=null,dirtyTranscript=false,dirtyReport=false,noticeTimer,jobRows=[],jobFilter='all',jobSearch='',jobsLoaded=false;
const $=id=>document.getElementById(id);
const statusNames={queued:'รอคิวถอดเสียง',transcribing:'กำลังถอดเสียง',transcribed:'ถอดเสียงแล้ว รอตรวจและสรุป',queued_summary:'รอคิวสรุป',summarizing:'กำลังสรุป',draft:'ฉบับร่างสำหรับตรวจทาน',approved:'ตรวจและอนุมัติแล้ว',failed:'ถอดเสียงไม่สำเร็จ'};
const stateKind={queued:'active',transcribing:'active',queued_summary:'active',summarizing:'active',transcribed:'ready',draft:'draft',approved:'done',failed:'failed'};
const filterGroups={active:['active'],review:['ready','draft'],approved:['done'],failed:['failed']};
const thMonths=['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];
const ICONS={
 'arrow-right':'<path d="M5 12h14m0 0-7-7m7 7-7 7"/>',
 'upload':'<path d="m8 16 4-4m0 0 4 4m-4-4v9m8-4.257A5.5 5.5 0 0 0 16.5 7a.62.62 0 0 1-.534-.302 7.5 7.5 0 1 0-11.78 9.096"/>',
 'file':'<path d="M14 2.27V6.4c0 .56 0 .84.109 1.054a1 1 0 0 0 .437.437c.214.11.494.11 1.054.11h4.13M14 17H8m8-4H8m12-3.012V17.2c0 1.68 0 2.52-.327 3.162a3 3 0 0 1-1.311 1.311C17.72 22 16.88 22 15.2 22H8.8c-1.68 0-2.52 0-3.162-.327a3 3 0 0 1-1.311-1.311C4 19.72 4 18.88 4 17.2V6.8c0-1.68 0-2.52.327-3.162a3 3 0 0 1 1.311-1.311C6.28 2 7.12 2 8.8 2h3.212c.733 0 1.1 0 1.446.083.306.073.598.195.867.36.303.185.562.444 1.08.963l3.19 3.188c.518.519.777.778.963 1.081a3 3 0 0 1 .36.867c.082.346.082.712.082 1.446Z"/>',
 'inbox':'<path d="M2.5 12h3.382c.685 0 1.312.387 1.618 1 .306.613.933 1 1.618 1h5.764c.685 0 1.312-.387 1.618-1 .306-.613.933-1 1.618-1H21.5M8.967 4h6.066c1.077 0 1.616 0 2.091.164a3 3 0 0 1 1.121.693c.36.352.6.833 1.082 1.796l2.166 4.333c.19.378.284.567.35.765.06.177.102.357.128.541.029.207.029.418.029.841V15.2c0 1.68 0 2.52-.327 3.162a3 3 0 0 1-1.311 1.311C19.72 20 18.88 20 17.2 20H6.8c-1.68 0-2.52 0-3.162-.327a3 3 0 0 1-1.311-1.311C2 17.72 2 16.88 2 15.2v-2.067c0-.422 0-.634.029-.84.026-.184.068-.365.128-.541.066-.199.16-.388.35-.766l2.166-4.333c.482-.963.723-1.444 1.082-1.796a3 3 0 0 1 1.12-.693C7.352 4 7.89 4 8.968 4Z"/>'};

function icon(name){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');
  svg.setAttribute('stroke-width','1.75');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');
  svg.setAttribute('aria-hidden','true');svg.setAttribute('class','i');svg.innerHTML=ICONS[name]||'';
  return svg;
}
function fmtDate(sec){const d=new Date(sec*1000);return d.getDate()+' '+thMonths[d.getMonth()]+' '+(d.getFullYear()+543);}
function fmtTime(sec){const d=new Date(sec*1000);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');}
function pct(text){const m=/(\d{1,3})\s*%/.exec(text||'');return m?Math.min(100,parseInt(m[1],10)):null;}
function autosize(el){if(!el)return;el.style.height='auto';el.style.height=Math.max(el.scrollHeight+2,0)+'px';}
function say(text){$('notice').textContent=text;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{$('notice').textContent=''},10000);}

async function api(path,options={}){
 const headers={...(options.headers||{})};if(me&&options.method&&options.method!=='GET')headers['x-csrf-token']=me.csrf;
 const r=await fetch(path,{...options,headers,credentials:'same-origin'});let obj;try{obj=await r.json()}catch{throw Error('เซิร์ฟเวอร์ตอบไม่ครบ กรุณาตรวจการเชื่อมต่อ')}
 if(!r.ok){if(r.status===401)showLogin();throw Error(typeof obj.detail==='string'?obj.detail:'คำขอไม่ถูกต้อง')};return obj;
}
function post(path,data){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}

function showLogin(){
  me=null;current=null;$('login').hidden=false;$('dashboard').hidden=true;$('detail').hidden=true;
  $('logout').hidden=true;$('api-settings').hidden=true;$('settings').hidden=true;$('claude-api-key').value='';
  window.scrollTo(0,0);
}
async function start(){
  try{
    me=await api('/api/session');$('login').hidden=true;$('logout').hidden=false;$('api-settings').hidden=!me.admin;
    $('settings').hidden=true;$('dashboard').hidden=false;$('detail').hidden=true;
    $('session-info').textContent=me.username+' • โหมดสรุป: '+({disabled:'ยังไม่เปิด',anthropic:'Claude API'}[me.summary_mode]||me.summary_mode)+' • ไฟล์ไม่เกิน '+me.max_upload_mb+' MB';
    $('api-status').hidden=!me.admin;
    if(me.admin)refreshApiStatus();
    await loadJobs();
  }catch{showLogin()}
}

/* ---------- job list ---------- */
function chipEl(state){
  const s=document.createElement('span');
  s.className='chip chip-state is-'+(stateKind[state]||'active');
  s.textContent=statusNames[state]||state;return s;
}
function jobRow(j){
  const row=document.createElement('div');row.className='job';
  const main=document.createElement('div');main.className='job-main';
  const title=document.createElement('strong');title.textContent=j.title;
  const meta=document.createElement('div');meta.className='job-meta';
  meta.append(chipEl(j.state));
  const when=document.createElement('span');when.className='meta';
  when.textContent='อัปโหลด '+fmtDate(j.created)+' • '+fmtTime(j.created);
  meta.append(when);
  if(j.state==='failed'&&j.error){const e=document.createElement('span');e.className='job-err';e.textContent=j.error;meta.append(e);}
  main.append(title,meta);
  const kind=stateKind[j.state]||'active';
  if(kind==='active'){
    const p=pct(j.progress);
    const note=document.createElement('p');note.className='meta';
    note.textContent=j.progress||statusNames[j.state];note.style.marginTop='6px';
    const bar=document.createElement('div');bar.className='progress'+(p===null?' is-indeterminate':'');
    const fill=document.createElement('span');if(p!==null)fill.style.width=p+'%';
    bar.append(fill);main.append(note,bar);
  }else if(j.progress&&j.state!=='approved'){
    const note=document.createElement('p');note.className='meta';note.textContent=j.progress;
    note.style.marginTop='6px';main.append(note);
  }
  const btn=document.createElement('button');btn.className='btn btn-outline';btn.type='button';
  btn.append(document.createTextNode('เปิดงาน'),icon('arrow-right'));
  btn.onclick=()=>openJob(j.id);
  row.append(main,btn);return row;
}
function emptyState(title,text,actionLabel,action,iconName){
  const box=document.createElement('div');box.className='empty';
  box.append(icon(iconName||'file'));
  const strong=document.createElement('strong');strong.textContent=title;
  const p=document.createElement('p');p.textContent=text;
  box.append(strong,p);
  if(actionLabel){const b=document.createElement('button');b.className='btn btn-outline';b.type='button';b.textContent=actionLabel;b.onclick=action;box.append(b);}
  return box;
}
function skeleton(){
  const host=$('jobs');host.replaceChildren();
  host.setAttribute('aria-busy','true');
  for(let i=0;i<3;i++){const r=document.createElement('div');r.className='skel';r.append(document.createElement('span'),document.createElement('span'));host.append(r);}
}
function matches(j){
  if(jobSearch&&!j.title.toLowerCase().includes(jobSearch))return false;
  if(jobFilter==='all')return true;
  return (filterGroups[jobFilter]||[]).includes(stateKind[j.state]||'active');
}
function renderJobs(){
  const host=$('jobs');host.replaceChildren();host.removeAttribute('aria-busy');
  const list=jobRows.filter(matches);
  $('jobs-summary').textContent=jobRows.length?('ทั้งหมด '+jobRows.length+' งาน • แสดง '+list.length):'';
  if(!jobRows.length){
    host.append(emptyState('ยังไม่มีงานในระบบ','อัปโหลดไฟล์เสียงหรือวิดีโอเพื่อเริ่มถอดเสียงงานแรก','เพิ่มไฟล์แรก',()=>{$('title').focus();$('title').scrollIntoView({block:'center',behavior:'smooth'})},'inbox'));
    return;
  }
  if(!list.length){
    host.append(emptyState('ไม่พบงานที่ตรงกับเงื่อนไข','ลองล้างคำค้นหรือเลือกตัวกรองอื่น','ล้างตัวกรอง',()=>{jobSearch='';jobFilter='all';$('search').value='';syncFilters();renderJobs();},'file'));
    return;
  }
  for(const j of list)host.append(jobRow(j));
}
function syncFilters(){
  for(const b of $('filters').querySelectorAll('[data-filter]')){
    const on=b.dataset.filter===jobFilter;
    b.classList.toggle('is-active',on);b.setAttribute('aria-pressed',on?'true':'false');
  }
}
async function loadJobs(){
  if(!jobsLoaded)skeleton();
  try{jobRows=await api('/api/jobs');jobsLoaded=true;renderJobs();}
  catch(err){$('jobs').removeAttribute('aria-busy');say(err.message);throw err;}
}

/* ---------- detail ---------- */
function updateSteps(state){
  const canReview=['transcribed','draft','approved'].includes(state);
  const approved=state==='approved';
  const mark=(name,cls)=>{const li=document.querySelector('[data-step="'+name+'"]');if(li)li.className=cls||'';};
  mark('transcript',canReview?'is-done':'is-active');
  mark('report',approved?'is-done':(canReview?'is-active':''));
  mark('export',approved?'is-done':'');
  if(!canReview)mark('export','');
}
async function openJob(id){current=await api('/api/jobs/'+id);dirtyReport=false;dirtyTranscript=false;renderJob();}
function renderJob(){
  const j=current;if(!j)return;
  $('dashboard').hidden=true;$('detail').hidden=false;
  $('job-title').textContent=j.title;
  const kind=stateKind[j.state]||'active';
  const st=$('job-status');st.className='chip chip-state is-'+kind;st.textContent=statusNames[j.state]||j.state;
  $('job-updated').textContent='อัปเดตล่าสุด '+fmtDate(j.updated)+' • '+fmtTime(j.updated);
  const bar=$('job-progress'),p=pct(j.progress);
  bar.hidden=kind!=='active';
  if(kind==='active'){
    bar.classList.toggle('is-indeterminate',p===null);
    bar.firstElementChild.style.width=(p===null?34:p)+'%';
    bar.setAttribute('aria-valuenow',p===null?'':String(p));
    bar.setAttribute('aria-label',j.progress||statusNames[j.state]||'ความคืบหน้า');
  }
  $('job-error').textContent=j.error||'';
  $('transcript').value=j.edited??j.transcript;
  $('report').value=j.report_display;
  $('cloud-box').hidden=me.summary_mode!=='anthropic';
  $('cloud-consent').checked=false;
  $('mode-note').textContent=me.summary_mode==='anthropic'?'จะส่งข้อความที่ตรวจแล้วให้ Claude API เมื่อคุณยืนยัน':'ส่วนสรุปยังปิดอยู่ ผู้ดูแลต้องเชื่อมต่อ Claude API ก่อน';
  $('summarize').disabled=me.summary_mode==='disabled'||!['transcribed','draft','approved'].includes(j.state);
  $('save-transcript').disabled=!['transcribed','draft','approved'].includes(j.state);
  $('retry').hidden=j.state!=='failed';
  $('report-box').hidden=!j.report;
  $('approve').disabled=j.state!=='draft';
  $('transcript').disabled=['queued','transcribing','queued_summary','summarizing'].includes(j.state);
  $('unsaved').hidden=true;
  const rs=$('report-state');
  if(j.report){rs.className='chip chip-state '+(j.state==='approved'?'is-done':'is-draft');rs.textContent=j.state==='approved'?'อนุมัติแล้ว':'ฉบับร่าง';}
  updateSteps(j.state);
  for(const [id,kindOf] of [['download-transcript','transcript'],['download-docx','docx'],['download-doc','doc'],['download-report','report'],['download-json','json']])$(id).href='/api/jobs/'+j.id+'/download/'+kindOf;
  autosize($('transcript'));autosize($('report'));
  countTranscript();
  window.scrollTo({top:0,behavior:'smooth'});
}
function countTranscript(){
  const n=$('transcript').value.length;
  $('transcript-count').textContent=n?n.toLocaleString('th-TH')+' ตัวอักษร':'';
}
function unsaved(){dirtyTranscript=true;$('unsaved').hidden=false}
$('transcript').oninput=()=>{unsaved();countTranscript();autosize($('transcript'));};
$('report').oninput=()=>{dirtyReport=true;$('unsaved').hidden=false;autosize($('report'));};
window.addEventListener('resize',()=>{autosize($('transcript'));autosize($('report'));});

/* ---------- actions ---------- */
$('login-form').onsubmit=async e=>{
  e.preventDefault();
  const err=$('login-error');err.textContent='';
  const user=$('username').value.trim(),pass=$('password').value;
  if(!user||!pass){err.textContent='กรุณากรอกชื่อผู้ใช้และรหัสผ่าน';(user?$('password'):$('username')).focus();return;}
  try{await post('/api/login',{username:user,password:pass});$('password').value='';await start()}
  catch(ex){err.textContent=ex.message;err.focus&&err.focus();$('password').select&&$('password').select();}
};
$('logout').onclick=async()=>{try{await post('/api/logout',{});showLogin()}catch(err){say(err.message)}};
$('refresh').onclick=()=>loadJobs().catch(()=>{});
$('search').oninput=()=>{jobSearch=$('search').value.trim().toLowerCase();renderJobs();};
$('filters').addEventListener('click',e=>{
  const b=e.target.closest('[data-filter]');if(!b)return;
  jobFilter=b.dataset.filter;syncFilters();renderJobs();
});
$('back').onclick=()=>{
  if((dirtyReport||dirtyTranscript)&&!confirm('มีข้อความที่ยังไม่ได้บันทึก ต้องการกลับรายการงานหรือไม่?'))return;
  current=null;dirtyReport=false;dirtyTranscript=false;$('detail').hidden=true;$('dashboard').hidden=false;
  window.scrollTo({top:0,behavior:'smooth'});loadJobs().catch(()=>{});
};
$('audio').addEventListener('change',()=>{
  const f=$('audio').files[0];
  $('file-name').textContent=f?f.name+' • '+(f.size/1048576).toFixed(1)+' MB':'';
});
const dz=$('dropzone');
for(const evt of ['dragenter','dragover'])dz.addEventListener(evt,e=>{e.preventDefault();dz.classList.add('is-over');});
for(const evt of ['dragleave','drop'])dz.addEventListener(evt,e=>{e.preventDefault();dz.classList.remove('is-over');});
dz.addEventListener('drop',e=>{
  const files=e.dataTransfer&&e.dataTransfer.files;
  if(!files||!files.length)return;
  const dt=new DataTransfer();dt.items.add(files[0]);$('audio').files=dt.files;
  $('audio').dispatchEvent(new Event('change'));
});
$('upload-form').onsubmit=async e=>{
  e.preventDefault();
  const file=$('audio').files[0];
  if(!file){say('กรุณาเลือกไฟล์เสียงหรือวิดีโอก่อนอัปโหลด');$('dropzone').focus();return;}
  if(file.size>me.max_upload_mb*1024*1024){say('ไฟล์ใหญ่เกินขนาดที่กำหนด');return;}
  $('upload-button').disabled=true;$('upload-state').textContent='กำลังอัปโหลด กรุณารอจนขึ้นว่าเข้าคิวแล้ว';
  try{
    const j=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/octet-stream','x-filename':encodeURIComponent(file.name),'x-title':encodeURIComponent($('title').value)},body:file});
    $('upload-state').textContent='อัปโหลดครบและเข้าคิวแล้ว';$('audio').value='';$('title').value='';$('file-name').textContent='';
    jobsLoaded=false;await openJob(j.id);
  }catch(err){say(err.message);$('upload-state').textContent='อัปโหลดไม่สำเร็จ'}
  finally{$('upload-button').disabled=false}
};
$('summarize').onclick=async()=>{
  if(current.report&&!confirm('การสรุปใหม่จะแทนรายงานเดิมและยกเลิกการอนุมัติ ต้องการดำเนินการหรือไม่?'))return;
  try{await post('/api/jobs/'+current.id+'/summarize',{transcript:$('transcript').value,cloud_consent:$('cloud-consent').checked});await openJob(current.id);say('บันทึกข้อความและเข้าคิวสรุปแล้ว')}
  catch(err){say(err.message)}
};
$('save-transcript').onclick=async()=>{
  if(current.report&&!confirm('การเปลี่ยนข้อความต้นทางจะยกเลิกรายงานเดิมและการอนุมัติ เพื่อให้สรุปใหม่ ต้องการบันทึกหรือไม่?'))return;
  try{await post('/api/jobs/'+current.id+'/transcript',{text:$('transcript').value,revision:current.revision});await openJob(current.id);say('บันทึกข้อความตรวจแล้ว ต้นฉบับยังคงอยู่')}
  catch(err){say(err.message)}
};
$('retry').onclick=async()=>{try{await post('/api/jobs/'+current.id+'/retry',{});await openJob(current.id)}catch(err){say(err.message)}};
$('save-report').onclick=async()=>{try{await post('/api/jobs/'+current.id+'/report',{text:$('report').value,revision:current.revision});await openJob(current.id);say('บันทึกฉบับร่างแล้ว')}catch(err){say(err.message)}};
$('approve').onclick=async()=>{
  if(dirtyReport||dirtyTranscript){say('กรุณาบันทึกการแก้รายงาน หรือส่งข้อความไปสรุปใหม่ก่อนอนุมัติ');return;}
  if(!confirm('ยืนยันว่าได้ตรวจชื่อ ตัวเลข มติ และงานที่ต้องทำกับต้นฉบับแล้ว และต้องการอนุมัติรายงานฉบับนี้?'))return;
  try{await post('/api/jobs/'+current.id+'/approve',{revision:current.revision});await openJob(current.id);say('บันทึกการอนุมัติโดยผู้ใช้แล้ว')}
  catch(err){say(err.message)}
};
$('print').onclick=()=>{
  if(dirtyReport){say('กรุณาบันทึกรายงานก่อนพิมพ์');return;}
  $('print-view').replaceChildren();
  const h=document.createElement('h1'),status=document.createElement('p'),text=document.createElement('pre');
  h.textContent=current.title;status.textContent='สถานะ: '+(statusNames[current.state]||current.state);text.textContent=current.report_display;
  $('print-view').append(h,status,text);window.print();
};
window.addEventListener('beforeunload',e=>{if(dirtyTranscript||dirtyReport){e.preventDefault();e.returnValue='';}});
setInterval(async()=>{
  if(!me)return;
  try{
    if(current){if(dirtyReport||dirtyTranscript)return;const next=await api('/api/jobs/'+current.id);if(next.updated!==current.updated){current=next;renderJob()}}
    else if(!$('dashboard').hidden)await loadJobs();
  }catch{}
},4000);

/* ---------- API connection status ---------- */
const API_TEXT={ready:'เชื่อมต่อแล้ว',disabled:'ยังไม่เปิดใช้',failed:'เชื่อมต่อไม่สำเร็จ',model_missing:'โมเดลไม่ตรง',checking:'กำลังตรวจสอบ',idle:'ยังไม่ตรวจสอบ'};
function paintApiStatus(data){
  const state=(data&&data.state)||'idle';
  const pill=$('api-status'),label=$('api-status-text'),card=$('api-card');
  if(pill){pill.hidden=!me?.admin;pill.dataset.state=state;}
  if(label)label.textContent='API: '+(API_TEXT[state]||state);
  if(!card)return;
  card.dataset.state=state;
  $('api-card-title').textContent=API_TEXT[state]||state;
  const bits=[];
  if(data&&data.message)bits.push(data.message);
  if(data&&data.model)bits.push('โมเดล '+data.model);
  if(data&&data.latency_ms!=null)bits.push(data.latency_ms+' ms');
  if(data&&data.checked_at)bits.push('ตรวจเมื่อ '+fmtTime(data.checked_at));
  $('api-card-detail').textContent=bits.join(' • ')||'กดตรวจสอบเพื่อยืนยันว่าบัญชีนี้เรียก Claude API ได้จริง';
}
async function refreshApiStatus(force){
  if(!me?.admin)return;
  paintApiStatus({state:'checking',message:'กำลังตรวจสอบกับผู้ให้บริการ'});
  try{const d=await api('/api/admin/claude/status'+(force?'?refresh=1':''));paintApiStatus(d);}
  catch(err){paintApiStatus({state:'failed',message:err.message});}
}

/* ---------- admin settings ---------- */
let settingsChanged=false;
function settingPayload(){return {api_key:$('claude-api-key').value.trim(),workspace_id:$('claude-workspace').value.trim(),model:$('claude-model').value.trim(),enabled:$('claude-enabled').checked,policy_ack:$('claude-policy').checked};}
function applySettingsView(s){
  $('claude-api-key').value='';$('claude-workspace').value=s.workspace_id||'';$('claude-model').value=s.model||'';
  $('claude-enabled').checked=s.enabled;$('claude-policy').checked=false;
  $('claude-key-state').textContent=s.key_status==='dpapi'?'มี Key ที่เข้ารหัสไว้แล้ว • เว้นช่องว่างเพื่อใช้ Key เดิม':s.key_status==='legacy'?'มี Key จากชุดเดิม • บันทึกอีกครั้งเพื่อย้ายไปการเข้ารหัส DPAPI':'ยังไม่มี Key ที่บันทึกไว้';
}
async function openSettings(){
  if(!me?.admin)return;
  if((dirtyTranscript||dirtyReport)&&!confirm('มีการแก้งานที่ยังไม่บันทึก ต้องการออกจากหน้างานหรือไม่?'))return;
  try{
    const s=await api('/api/admin/claude');current=null;dirtyTranscript=false;dirtyReport=false;settingsChanged=false;
    $('detail').hidden=true;$('dashboard').hidden=true;$('settings').hidden=false;
    applySettingsView(s);$('claude-test-result').textContent='';$('claude-model-list').replaceChildren();$('claude-save-error').textContent='';
    window.scrollTo(0,0);refreshApiStatus();
  }catch(err){say(err.message)}
}
async function closeSettings(){
  if(settingsChanged&&!confirm('มีการตั้งค่าที่ยังไม่บันทึก ต้องการยกเลิกหรือไม่?'))return;
  $('claude-api-key').value='';settingsChanged=false;$('settings').hidden=true;await start();
}
$('api-settings').onclick=openSettings;
$('api-status').onclick=()=>openSettings();
$('api-check').onclick=async()=>{
  const b=$('api-check');b.disabled=true;
  try{await refreshApiStatus(true);say('ตรวจสอบสถานะการเชื่อมต่อแล้ว');}finally{b.disabled=false;}
};
$('settings-back').onclick=()=>closeSettings().catch(e=>say(e.message));
$('claude-cancel').onclick=$('settings-back').onclick;
for(const id of ['claude-api-key','claude-workspace','claude-model','claude-enabled','claude-policy'])$(id).addEventListener('input',()=>{settingsChanged=true;});
function settingsBusy(busy){for(const id of ['claude-api-key','claude-workspace','claude-model','claude-enabled','claude-policy','claude-test','claude-save','claude-cancel','settings-back','api-settings'])$(id).disabled=busy;}
$('claude-test').onclick=async()=>{
  const data=settingPayload();settingsBusy(true);$('claude-test-result').textContent='กำลังตรวจบัญชีและอ่านรายการโมเดล...';
  try{
    const r=await post('/api/admin/claude/test',data);$('claude-model-list').replaceChildren();
    for(const m of r.models){const o=document.createElement('option');o.value=m.id;o.label=m.name;$('claude-model-list').append(o);}
    $('claude-test-result').textContent=r.message+'\nพบ '+r.models.length+' โมเดล'+(r.has_more?' (ยังมีรายการเพิ่มเติม)':'');
  }catch(e){$('claude-test-result').textContent=e.message;}finally{data.api_key='';settingsBusy(false);}
};
$('claude-settings-form').onsubmit=async e=>{
  e.preventDefault();const data=settingPayload();$('claude-save-error').textContent='';
  if(data.enabled&&!data.policy_ack){$('claude-save-error').textContent='กรุณายืนยันนโยบายข้อมูลก่อนเปิด API';$('claude-policy').focus();return;}
  settingsBusy(true);
  try{
    const s=await post('/api/admin/claude',data);applySettingsView(s);settingsChanged=false;
    me=await api('/api/session');
    $('claude-test-result').textContent=s.enabled?'บันทึกและเปิด Claude API แล้ว ยังต้องยืนยันการส่งข้อความก่อนสรุปแต่ละงาน':'ปิด Claude API แล้ว';
    say('บันทึกการตั้งค่าแล้ว');refreshApiStatus(true);
  }catch(err){$('claude-save-error').textContent=err.message;}finally{data.api_key='';$('claude-api-key').value='';settingsBusy(false);}
};
window.addEventListener('beforeunload',e=>{if(settingsChanged){e.preventDefault();e.returnValue='';}});

start();
