"""Read-only Windows client state summary; excludes profile credentials and invitations."""
import json
import argparse
import ctypes
import os
from ctypes import wintypes
from pathlib import Path
import yaml

root=Path.home()/'AppData'/'Roaming'/'com.follow'
reports=[]
parser=argparse.ArgumentParser()
parser.add_argument('--pid',nargs='*',type=int,default=[])
args=parser.parse_args()
for name in ('VPNN','clash'):
    directory=root/name
    path=directory/'config.yaml'
    if not path.exists():
        continue
    data=yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    report={
        'directory':str(directory),'configModified':path.stat().st_mtime,
        'mode':data.get('mode'),'mixedPort':data.get('mixed-port'),
        'tun':data.get('tun'),'siteDNS':data.get('dns',{}).get('nameserver'),
        'transports':[p.get('x-vpnn',{}).get('mode') for p in data.get('proxies',[])],
        'cacheExists':(directory/'vpnn-config.enc').exists(),
        'profileCount':len(list((directory/'profiles').glob('*.yaml'))),
    }
    preferences=directory/'shared_preferences.json'
    if preferences.exists():
        state=json.loads(preferences.read_text(encoding='utf-8'))
        report['preferenceKeys']=list(state)
    reports.append(report)
if args.pid:
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    security=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    security.OpenProcessToken.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE)]
    security.GetTokenInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    for pid in [os.getpid()]+args.pid:
        process=kernel.OpenProcess(0x1000,False,pid)
        token=wintypes.HANDLE()
        elevated=wintypes.DWORD()
        length=wintypes.DWORD()
        ok=bool(process and security.OpenProcessToken(process,8,ctypes.byref(token)) and security.GetTokenInformation(token,20,ctypes.byref(elevated),4,ctypes.byref(length)))
        reports.append({'pid':pid,'tokenReadable':ok,'elevated':bool(elevated.value) if ok else None})
        if token:
            kernel.CloseHandle(token)
        if process:
            kernel.CloseHandle(process)
print(json.dumps(reports,ensure_ascii=True,indent=2))
