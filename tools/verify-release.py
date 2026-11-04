"""Verify candidate files and archive integrity without launching a VPN or changing networking."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import tarfile
import zipfile
import argparse
root=Path(__file__).resolve().parents[1]
artifacts=(root/'artifacts').resolve()
parser=argparse.ArgumentParser()
parser.add_argument('--manifest',default='LATEST.json',help='manifest inside artifacts; defaults to the active release')
args=parser.parse_args()
manifest_path=(artifacts/args.manifest).resolve()
if not manifest_path.is_relative_to(artifacts): raise ValueError('manifest must stay inside artifacts')
manifest=json.loads(manifest_path.read_text())
windows=artifacts/manifest['windowsDirectory']
if not windows.resolve().is_relative_to(artifacts): raise ValueError('unsafe Windows directory')
core_hash=hashlib.sha256((windows/'FlClashCore.exe').read_bytes()).hexdigest()
if json.loads((windows/'manifest.json').read_text())['coreSha256']!=core_hash:
    raise ValueError('helper and Core integrity manifest differ')
for name,expected in manifest['files'].items():
    relative=PurePosixPath(name)
    path=(artifacts/Path(*relative.parts)).resolve()
    if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(artifacts):
        raise ValueError('unsafe manifest path')
    if path.stat().st_size!=expected['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']:
        raise ValueError('artifact checksum mismatch: '+name)
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None: raise ValueError('corrupt ZIP: '+name)
            for member in archive.namelist():
                parts=PurePosixPath(member).parts
                if PurePosixPath(member).is_absolute() or '..' in parts or (parts and parts[0]=='private') or member.endswith(('admin.secret','state.json.signing','recovery.key','.p12','.jks')):
                    raise ValueError('private or unsafe ZIP member')
    if name.endswith('.tar.gz'):
        with tarfile.open(path,'r:gz') as archive:
            for member in archive.getmembers():
                if not member.isfile() or PurePosixPath(member.name).is_absolute() or '..' in PurePosixPath(member.name).parts:
                    raise ValueError('unsafe recovery tools archive')
print(json.dumps({'version':manifest['version'],'verifiedFiles':len(manifest['files']),'checksumsAndArchiveIntegrity':True,'vpnStarted':False}))
