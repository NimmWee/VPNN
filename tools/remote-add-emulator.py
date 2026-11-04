import json
import os
from pathlib import Path
import re

entry=json.loads(Path('/root/vpnn-transport-stage/client-allow.json').read_text())['id']
if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}',entry):
    raise SystemExit('invalid test Client ID')
path=Path('/etc/vpnn-transports/clients.json')
data=json.loads(path.read_text())
data['clients'][entry]={'comment':'VPNN Android emulator test'}
temp=path.with_suffix('.tmp')
temp.write_text(json.dumps(data))
temp.chmod(0o640)
os.chown(temp,path.stat().st_uid,path.stat().st_gid)
os.replace(temp,path)
print('Emulator Client ID added to isolated relay allowlist.')
