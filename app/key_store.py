"""Windows DPAPI machine-bound secret storage; folder ACLs remain required."""
import base64
import json
import os
import threading
from .core import DATA

KEY_LOCK=threading.RLock()
PROTECTED=DATA/'claude-key.dpapi.json'
LEGACY=DATA/'secrets.json'

def _crypt(value,protect):
    if os.name!='nt':
        raise ValueError('การบันทึก API key จากหน้าเว็บต้องรันบน Windows เพื่อใช้ DPAPI')
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(value)
    source=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    output=Blob()
    crypt32=ctypes.WinDLL('Crypt32.dll',use_last_error=True)
    kernel32=ctypes.WinDLL('Kernel32.dll',use_last_error=True)
    kernel32.LocalFree.argtypes=[ctypes.c_void_p];kernel32.LocalFree.restype=ctypes.c_void_p
    if protect:
        fn=crypt32.CryptProtectData
        fn.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        args=(ctypes.byref(source),'Meeting Server Claude API',None,None,None,5,ctypes.byref(output))
    else:
        fn=crypt32.CryptUnprotectData
        fn.argtypes=[ctypes.POINTER(Blob),ctypes.POINTER(wintypes.LPWSTR),ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        args=(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output))
    fn.restype=wintypes.BOOL
    if not fn(*args):
        raise ValueError('Windows DPAPI ไม่สามารถบันทึก/อ่าน Key ได้ ตรวจสิทธิ์และเครื่องที่ใช้')
    try:return ctypes.string_at(output.pbData,output.cbData)
    finally:kernel32.LocalFree(ctypes.cast(output.pbData,ctypes.c_void_p))

def key_status():
    return 'dpapi' if PROTECTED.exists() else 'legacy' if LEGACY.exists() else 'missing'

def load_key():
    with KEY_LOCK:
        if PROTECTED.exists():
            data=json.loads(PROTECTED.read_text(encoding='utf-8'))
            return _crypt(base64.b64decode(data['ciphertext'],validate=True),False).decode('utf-8')
        if LEGACY.exists():return json.loads(LEGACY.read_text(encoding='utf-8')).get('anthropic_api_key','')
    return ''

def save_key(key):
    if not isinstance(key,str) or not key.strip() or len(key)>1024 or any(c.isspace() for c in key):
        raise ValueError('รูปแบบ API key ไม่ถูกต้อง')
    with KEY_LOCK:
        protected=_crypt(key.strip().encode('utf-8'),True)
        DATA.mkdir(parents=True,exist_ok=True)
        temp=PROTECTED.with_suffix('.tmp')
        temp.write_text(json.dumps({'version':1,'scope':'windows-local-machine','ciphertext':base64.b64encode(protected).decode('ascii')}),encoding='utf-8')
        os.replace(temp,PROTECTED)
        # The previous CLI file must not retain a readable duplicate of the key.
        if LEGACY.exists():
            data=json.loads(LEGACY.read_text(encoding='utf-8'))
            data.pop('anthropic_api_key',None)
            tmp=LEGACY.with_suffix('.tmp');tmp.write_text(json.dumps(data),encoding='utf-8');os.replace(tmp,LEGACY)
