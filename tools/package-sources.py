"""Archive corresponding project sources, excluding local credentials, caches and builds."""
import hashlib
import argparse
import re
import json
import os
from pathlib import Path
import subprocess
import zipfile
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--version',default='0.1.2')
args=parser.parse_args()
if not re.fullmatch(r'\d+\.\d+\.\d+',args.version): raise ValueError('invalid release version')
files=set()
def repository(directory):
    if not (directory/'.git').exists():
        # The pinned ANet module is a source copy from the module cache.
        for path in directory.rglob('*'):
            if path.is_file() and (path.suffix in ['.go','.mod','.sum','.md','.yaml','.yml','.json'] or path.name in ['LICENSE','NOTICE']): files.add(path)
        return
    result=subprocess.run(['git','-C',str(directory),'ls-files','-z','--cached','--others','--exclude-standard'],capture_output=True,check=True)
    for value in result.stdout.decode('utf-8').split('\0'):
        if not value: continue
        path=directory/value
        if path.is_dir() and (path/'.git').exists(): repository(path)
        elif path.is_file(): files.add(path)
for name in ['client','transports/freeturn','transports/masterdns','transports/xray','transports/anet']:
    repository(root/name)
for name in ['engine','control','deploy','docs','tools']:
    for path in (root/name).rglob('*'):
        relative=path.relative_to(root/name)
        if any(part in ['.git','__pycache__','.pytest_cache','vendor','node_modules','build'] for part in relative.parts): continue
        if path.is_file() and path.suffix.lower() in ['.go','.mod','.sum','.py','.ps1','.sh','.md','.json','.html','.js','.css','.yaml','.yml','.toml','.txt']:
            files.add(path)
for pattern in ['*.lock.json','README.md','NOTICES.md','Start-*.cmd']:
    files.update(path for path in root.glob(pattern) if path.is_file())
for path in list(files):
    relative=path.relative_to(root)
    if path.is_symlink() or any(part in ['private','logs','downloads','.toolchains','.cache','.dart_tool','.gradle','.codegraph'] for part in relative.parts) or path.suffix.lower() in ['.exe','.dll','.apk','.p12','.jks','.keystore','.db','.sqlite','.pyc'] or path.name in ['local.properties','key.properties']:
        files.remove(path)
        continue
    if path.stat().st_size>20*1024*1024: raise RuntimeError('unexpected large source: '+str(relative))
    if path.suffix in ['.py','.ps1','.md','.json','.txt']:
        data=path.read_bytes()
        terms=[value.encode() for value in os.environ.get('VPNN_SOURCE_SCAN_TERMS','').split('|') if value]
        if any(secret in data for secret in terms):
            raise RuntimeError('credential found in source candidate: '+str(relative))
output=root/f'artifacts/VPNN-Sources-{args.version}.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for path in sorted(files): archive.write(path,str(path.relative_to(root)).replace('\\','/'))
print(json.dumps({'sourceArchive':str(output),'files':len(files),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))
