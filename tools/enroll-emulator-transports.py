"""Use the local control API to create one isolated emulator test invitation."""
import base64
import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--windows',action='store_true')
args=parser.parse_args()
target='windows' if args.windows else 'emulator'
private=root/'private'/'transport-test'
base='http://127.0.0.1:8098'
token=(root/'private'/'control'/'admin.secret').read_text().strip()

def request(method,path,body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(base+path,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as res:
        return json.load(res)

state=request('GET','/api/admin/state')
group=json.loads((private/'group.json').read_text())
if args.windows:
    group['id']='owner-transports-windows'
    group['name']='DNS / VK · Windows owner test'
groups=[g for g in state['groups'] if g['id']!=group['id']]+[group]
request('PUT','/api/admin/groups',groups)
inviteFile=private/(target+'-invite.json')
if inviteFile.exists():
    invite=json.loads(inviteFile.read_text())
else:
    invite=request('POST','/api/admin/devices',{'name':target+' · transports','group':group['id']})
    inviteFile.write_text(json.dumps(invite))
endpoint='http://127.0.0.1:8098' if args.windows else 'http://10.0.2.2:8098'
query=urllib.parse.urlencode({'url':endpoint,'token':invite['token'],'key':invite['publicKey'],'device':invite['deviceId']})
(private/(target+'-invitation.txt')).write_text('vpnn://enroll?'+query)
provision=request('GET','/api/admin/provision')
device=next(d for d in provision['devices'] if d['id']==invite['deviceId'])
(private/(target+'-provision.json')).write_text(json.dumps(device))
print(target+' invitation and server Client ID written to private files.')
