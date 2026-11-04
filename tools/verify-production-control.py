"""Verify HTTPS, authentication and pinned signatures without printing credentials."""
import base64
import json
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

root=Path(__file__).resolve().parents[1]
endpoint='https://vpn.chichy.space'

def request(path,token=None,body=None):
    headers={}
    if token:
        headers['Authorization']='Bearer '+token
    if body is not None:
        headers['Content-Type']='application/json'
        body=json.dumps(body).encode()
    try:
        with urlopen(Request(endpoint+path,headers=headers,data=body),timeout=25) as response:
            return response.status,response.headers,json.load(response)
    except HTTPError as error:
        return error.code,error.headers,{}

def raw(value):
    return base64.urlsafe_b64decode(value+'='*(-len(value)%4))

status,_,health=request('/health')
assert status==200 and health['status']=='ok'
assert request('/api/admin/state')[0]==401
assert request('/api/node/provision')[0]==403
admin=(root/'private/control/admin.secret').read_text().strip()
status,headers,_=request('/api/admin/login',body={'token':admin})
assert status==200
cookie=headers.get('Set-Cookie','')
assert all(flag in cookie for flag in ['Secure','HttpOnly','SameSite=Strict'])
status,_,state=request('/api/admin/state',admin)
assert status==200
checks=[]
for device in ['windows','emulator']:
    invitation=(root/'private/transport-test'/(device+'-production-invitation.txt')).read_text().strip()
    fields={key:value[0] for key,value in parse_qs(urlsplit(invitation).query).items()}
    status,_,envelope=request('/api/device/config',fields['token'])
    assert status==200
    payload=raw(envelope['payload'])
    Ed25519PublicKey.from_public_bytes(raw(fields['key'])).verify(raw(envelope['signature']),payload)
    config=json.loads(payload)
    assert config['deviceId']==fields['device']
    assert set(profile['id'] for profile in config['profiles'])=={'vk','dns'}
    checks.append({'device':device,'signature':'valid','modes':['vk','dns']})
report={'https':'valid certificate','unauthorizedAdmin':401,'publicNodeAPI':403,'adminCookie':'Secure; HttpOnly; SameSite=Strict','groups':len(state['groups']),'devices':checks}
(root/'logs/production-https-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
