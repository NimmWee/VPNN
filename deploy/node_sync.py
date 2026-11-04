#!/usr/bin/env python3
"""Apply individual DNS/VK access from the co-located control's atomic state file."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

def label(device):
    return 'd-'+hashlib.sha256(device.encode()).hexdigest()[:16]

def desired(state,zone,max_devices=8):
    if not re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,63}',zone):
        raise ValueError('invalid delegated zone')
    version=state.get('version')
    if type(version) is not int or version<=0:
        raise ValueError('invalid state version')
    groups={item['id']:item['profiles'] for item in state['groups']}
    active=[item for item in state['devices'].values() if item['enabled']]
    if len(active)>max_devices:
        raise ValueError('node capacity exceeded')
    result={'version':version,'dns':[],'vk':[]}
    ports=set()
    identifiers=set()
    for item in sorted(active,key=lambda value:value['id']):
        identifier=item['id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',identifier) or identifier in identifiers:
            raise ValueError('invalid device identity')
        identifiers.add(identifier)
        profiles=groups.get(item['group'])
        if profiles is None:
            raise ValueError('unassigned device group')
        identity=str(uuid.UUID(item['uuid']))
        if identity!=item['uuid']:
            raise ValueError('noncanonical network identity')
        if 'vk' in profiles:
            result['vk'].append({'id':identifier,'uuid':identity})
        if 'dns' in profiles:
            port=item['dnsPort']
            key=item['dnsKey']
            if type(port) is not int or not 54001<=port<=64999 or port in ports or not re.fullmatch(r'[a-zA-Z0-9_-]{32}',key):
                raise ValueError('invalid individual DNS access')
            ports.add(port)
            name=label(identifier)
            result['dns'].append({'id':identifier,'label':name,'domain':name+'.'+zone,'port':port,'key':key})
    return result

def run(*args):
    result=subprocess.run(args,text=True,capture_output=True,timeout=45)
    if result.returncode:
        raise RuntimeError('node operation failed: '+args[0])
    return result.stdout

def atomic(path,value,mode=0o600,group=None):
    path=Path(path)
    data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode() if not isinstance(value,bytes) else value
    if path.exists() and path.read_bytes()==data:
        return False
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.new')
    temporary.write_bytes(data)
    temporary.chmod(mode)
    if group is not None:
        os.chown(temporary,0,group)
    os.replace(temporary,path)
    return True

def synchronize(args):
    import grp
    directory=Path('/etc/vpnn-node')
    public=Path('/run/vpnn-node/status.json')
    state=json.loads(Path(args.state).read_text())
    wanted=desired(state,args.zone,args.max_devices)
    previous={}
    cache=directory/'applied.json'
    if cache.exists():
        previous=json.loads(cache.read_text())
    transport=Path('/etc/vpnn-transports')
    gid=grp.getgrnam('vpnntransport').gr_gid
    old_labels={item['label'] for item in previous.get('dns',[])}
    new_labels={item['label'] for item in wanted['dns']}
    for name in old_labels-new_labels:
        if not re.fullmatch(r'd-[a-f0-9]{16}',name):
            raise ValueError('invalid owned service label')
        run('systemctl','disable','--now','vpnn-dns@'+name+'.service')
    for device in wanted['dns']:
        keyfile=directory/'devices'/(device['label']+'.key')
        key_changed=atomic(keyfile,device['key'].encode(),0o640,gid)
        config={'UDP_HOST':'127.0.0.1','UDP_PORT':device['port'],'DOMAIN':[device['domain']],
                'AUTHORITATIVE_NS':args.nameserver,'PROTOCOL_TYPE':'SOCKS5','DATA_ENCRYPTION_METHOD':5,
                'ENCRYPTION_KEY_FILE':str(keyfile),'USE_EXTERNAL_SOCKS5':True,'FORWARD_IP':'127.0.0.1','FORWARD_PORT':24431,
                'UDP_READERS':1,'DNS_REQUEST_WORKERS':1,'DEFERRED_SESSION_WORKERS':1,'MAX_CONCURRENT_REQUESTS':512,
                'DEFERRED_SESSION_QUEUE_LIMIT':256,'DNS_CACHE_MAX_RECORDS':1000,'SOCKET_BUFFER_SIZE':524288,'LOG_LEVEL':'ERROR'}
        changed=atomic(directory/'devices'/(device['label']+'.json'),config,0o640,gid)
        unit='vpnn-dns@'+device['label']+'.service'
        run('systemctl','enable',unit)
        if changed or key_changed:
            run('systemctl','restart',unit)
        else:
            run('systemctl','start',unit)
        run('systemctl','is-active',unit)
    xray_path=transport/'xray.json'
    xray=json.loads(xray_path.read_text())
    incoming=next(value for value in xray['inbounds'] if value.get('tag')=='vk')
    incoming['settings']['clients']=[{'id':item['uuid']} for item in wanted['vk']]
    candidate=directory/'xray-candidate.json'
    atomic(candidate,xray,0o640,gid)
    run('/opt/vpnn-transports/xray','run','-test','-config',str(candidate))
    changed_xray=atomic(xray_path,xray,0o640,gid)
    changed_clients=atomic(transport/'clients.json',{'clients':{item['id']:{'comment':'managed device'} for item in wanted['vk']}},0o640,gid)
    atomic(directory/'targets.json',{item['domain']:'127.0.0.1:'+str(item['port']) for item in wanted['dns']},0o640,gid)
    if changed_xray:
        run('systemctl','restart','vpnn-egress')
    else:
        run('systemctl','start','vpnn-egress')
    if changed_xray or changed_clients:
        run('systemctl','restart','vpnn-vk')
    else:
        run('systemctl','start','vpnn-vk')
    run('systemctl','start','vpnn-dns')
    run('systemctl','is-active','vpnn-egress','vpnn-vk','vpnn-dns')
    atomic(cache,wanted)
    atomic(public,{'healthy':True,'appliedVersion':wanted['version'],'appliedAt':int(time.time()),'devices':[item['id'] for item in wanted['dns']],'vkDevices':len(wanted['vk']),'dnsDevices':len(wanted['dns'])},0o644)

if __name__=='__main__':
    import fcntl
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',default='/var/lib/vpnn-control/state.json')
    parser.add_argument('--zone',required=True)
    parser.add_argument('--nameserver',required=True)
    parser.add_argument('--max-devices',type=int,default=8)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:
        raise SystemExit('root required for node service reconciliation')
    Path('/run/vpnn-node').mkdir(mode=0o755,exist_ok=True)
    with Path('/run/vpnn-node/sync.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            try:
                synchronize(args)
            except Exception as error:
                subprocess.run(['systemctl','stop','vpnn-vk','vpnn-egress','vpnn-dns'],capture_output=True,timeout=45)
                atomic('/run/vpnn-node/status.json',{'healthy':False,'error':'Network provisioning failed; inspect node service journal','updatedAt':int(time.time())},0o644)
                print('VPNN node reconciliation failed: '+type(error).__name__,flush=True)
                if args.once:
                    raise SystemExit(1)
            if args.once:
                break
            time.sleep(10)
