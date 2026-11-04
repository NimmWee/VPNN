"""Disposable-device DNS data-plane revocation check; never changes host routes."""
import base64
import json
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

root=Path(__file__).resolve().parents[1]
directory=root/'private/revocation-test'
directory.mkdir(exist_ok=True)
base='https://vpn.chichy.space'
admin=(root/'private/control/admin.secret').read_text().strip()

def api(method,path,body=None,token=admin):
    data=json.dumps(body).encode() if body is not None else None
    request=Request(base+path,method=method,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=20) as response: return response.status,json.load(response)
    except HTTPError as error:
        return error.code,{}

def wait_applied(version,count):
    for attempt in range(45):
        code,state=api('GET','/api/admin/state')
        status=state.get('networkStatus') or {}
        if code==200 and status.get('healthy') and status.get('appliedVersion',0)>=version and status.get('dnsDevices')==count:
            return state
        time.sleep(1)
    raise RuntimeError('node did not confirm the expected active-device state')

def raw(text): return base64.urlsafe_b64decode(text+'='*(-len(text)%4))

def probe(config,timeout,tag):
    file=directory/(tag+'.json')
    file.write_text(json.dumps(config))
    result=subprocess.run([str(root/'artifacts/vpnn-transport-check.exe'),'-config',str(file),'-state-dir',str(directory/tag),'-status-file',str(directory/(tag+'-status.json')),'-timeout',timeout],capture_output=True,text=True,timeout=90)
    (directory/(tag+'-output.txt')).write_text(result.stdout+result.stderr)
    return result.returncode==0 and 'HTTPS_OK' in result.stdout

code,state=api('GET','/api/admin/state')
assert code==200
initial=sum(device['enabled'] for device in state['devices'])
group=next(group['id'] for group in state['groups'] if 'dns' in group['profiles'] and 'vk' in group['profiles'])
code,invite=api('POST','/api/admin/devices',{'name':'Disposable production revocation test','group':group})
assert code==201
(directory/'invite.json').write_text(json.dumps(invite))
revoked=False
try:
    code,envelope=api('GET','/api/device/config',token=invite['token'])
    assert code==200
    payload=raw(envelope['payload'])
    Ed25519PublicKey.from_public_bytes(raw(invite['publicKey'])).verify(raw(envelope['signature']),payload)
    profiles=json.loads(payload)
    wait_applied(profiles['version'],initial+1)
    profile=json.loads(next(item['config'] for item in profiles['profiles'] if item['id']=='dns'))
    config=next(item['x-vpnn'] for item in profile['proxies'] if 'x-vpnn' in item)
    config['listen']='127.0.0.1:19382'
    if not probe(config,'60s','before-revoke'):
        raise RuntimeError('disposable DNS access did not carry HTTPS before revocation')
    code,_=api('POST','/api/admin/devices/'+invite['deviceId']+'/revoke',{})
    assert code==200
    revoked=True
    _,current=api('GET','/api/admin/state')
    wait_applied(current['version'],initial)
    assert api('GET','/api/device/config',token=invite['token'])[0]==403
    name='revocation-'+secrets.token_hex(4)+'.'+config['dns']['domains'][0]
    question=b''.join(bytes([len(label)])+label.encode() for label in name.split('.'))+b'\x00'
    identifier=secrets.randbelow(65536)
    message=struct.pack('!HHHHHH',identifier,0x0100,1,0,0,0)+question+struct.pack('!HH',16,1)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as connection:
        connection.settimeout(5)
        connection.sendto(message,('89.125.120.163',53))
        response,_=connection.recvfrom(4096)
    assert struct.unpack('!H',response[:2])[0]==identifier
    assert response[3]&15==5
    if probe(config,'8s','after-revoke'):
        raise RuntimeError('revoked device still carried HTTPS')
    report={'beforeRevokeHTTPS':True,'afterRevokeSettingsHTTP':403,'gatewayAfterRevoke':'REFUSED','afterRevokeHTTPS':False,'remainingActiveDevices':initial}
    (root/'logs/production-revocation-check.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
finally:
    if not revoked:
        api('POST','/api/admin/devices/'+invite['deviceId']+'/revoke',{})
