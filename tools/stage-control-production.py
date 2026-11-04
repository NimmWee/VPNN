"""Prepare private control migration and HTTPS invitations, without printing credentials."""
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

root=Path(__file__).resolve().parents[1]
stage=root/'private'/'production-control-stage'
stage.mkdir(exist_ok=True)
shutil.copyfile(root/'artifacts'/'vpnn-control-linux-amd64',stage/'vpnn-control')
for name in ['state.json','state.json.signing','admin.secret']:
    shutil.copyfile(root/'private'/'control'/name,stage/name)
(stage/'sha256.json').write_text(json.dumps({'vpnn-control':hashlib.sha256((stage/'vpnn-control').read_bytes()).hexdigest()}))
for device in ['windows','emulator']:
    text=(root/'private'/'transport-test'/(device+'-invitation.txt')).read_text().strip()
    url=urlsplit(text)
    pairs=[(key,'https://vpn.chichy.space' if key=='url' else value) for key,value in parse_qsl(url.query)]
    (root/'private'/'transport-test'/(device+'-production-invitation.txt')).write_text(urlunsplit(url._replace(query=urlencode(pairs))))
result={'stage':str(stage),'stateDevices':len(json.loads((stage/'state.json').read_text())['devices'])}
print(json.dumps(result))
