#!/usr/bin/env python3
"""Install the same-VPS DNS/VK reconciler; keep KIT and the iPhone stack separate."""
import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import Request,urlopen

def run(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=45)
    if result.returncode:
        raise RuntimeError('installation command failed: '+args[0])
    return result.stdout

def write(path,data,mode=0o644,group=None):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.new')
    temporary.write_bytes(data.encode() if isinstance(data,str) else data)
    temporary.chmod(mode)
    if group is not None: os.chown(temporary,0,group)
    os.replace(temporary,path)

def install(stage):
    if os.geteuid()!=0: raise ValueError('root required')
    stage=Path(stage)
    manifest=json.loads((stage/'sha256.json').read_text())
    for name in ['vpnn-dns-gateway','node_sync.py']:
        if hashlib.sha256((stage/name).read_bytes()).hexdigest()!=manifest[name]:
            raise ValueError('node checksum mismatch')
    run('systemctl','is-active','vpnn-control','vpnn-egress','vpnn-vk')
    backup=Path('/var/backups/vpnn-control')/('node-'+time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700,parents=True)
    for path in ['/etc/systemd/system/vpnn-dns.service','/etc/vpnn-transports/xray.json','/etc/vpnn-transports/clients.json','/var/lib/vpnn-control/state.json']:
        write(backup/Path(path).name,Path(path).read_bytes(),0o600)
    write('/opt/vpnn-control/vpnn-dns-gateway',(stage/'vpnn-dns-gateway').read_bytes(),0o755)
    write('/opt/vpnn-control/node_sync.py',(stage/'node_sync.py').read_bytes(),0o755)
    gid=grp.getgrnam('vpnntransport').gr_gid
    for value in ['/etc/vpnn-node','/etc/vpnn-node/devices']:
        path=Path(value)
        path.mkdir(exist_ok=True,mode=0o750)
        path.chmod(0o750)
        os.chown(path,0,gid)
    if not Path('/etc/vpnn-node/targets.json').exists():
        write('/etc/vpnn-node/targets.json','{}\n',0o640,gid)
    common='''User=vpnntransport
Group=vpnntransport
Restart=on-failure
RestartSec=5
Environment=GOMAXPROCS=1
Environment=GOMEMLIMIT=24MiB
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
UMask=0077
MemoryMax=64M
TasksMax=64
LimitNOFILE=4096
'''
    gateway='[Unit]\nDescription=VPNN authoritative individual DNS gateway\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\n'+common+'''AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
ExecStart=/opt/vpnn-control/vpnn-dns-gateway -listen 89.125.120.163:53 -zone v.chichy.space -nameserver ns.chichy.space -targets /etc/vpnn-node/targets.json -workers 16

[Install]
WantedBy=multi-user.target
'''
    backend='[Unit]\nDescription=VPNN individual DNS backend %i\nAfter=vpnn-egress.service\nWants=vpnn-egress.service\n\n[Service]\n'+common+'''ExecStart=/opt/vpnn-transports/masterdns-server -config /etc/vpnn-node/devices/%i.json -nowait

[Install]
WantedBy=multi-user.target
'''
    sync='''[Unit]
Description=VPNN co-located individual access reconciliation
After=vpnn-control.service network-online.target
Wants=vpnn-control.service

[Service]
ExecStart=/usr/bin/python3 /opt/vpnn-control/node_sync.py --zone v.chichy.space --nameserver ns.chichy.space --max-devices 8
Restart=on-failure
RestartSec=5
RuntimeDirectory=vpnn-node
RuntimeDirectoryMode=0755
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_FOWNER
ReadWritePaths=/etc/vpnn-node /etc/vpnn-transports /run/vpnn-node
UMask=0077
MemoryMax=64M
TasksMax=64

[Install]
WantedBy=multi-user.target
'''
    secret=Path('/etc/vpnn-control/admin.secret').read_text().strip()
    def api(method,path,body=None):
        data=json.dumps(body).encode() if body is not None else None
        request=Request('http://127.0.0.1:8098/api/admin/'+path,data=data,method=method,headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
        with urlopen(request,timeout=15) as response: return json.load(response)
    current=api('GET','state')
    groups=current['groups']
    for group in groups:
        for mode,profile in group['profiles'].items():
            for proxy in profile.get('proxies',[]):
                meta=proxy.get('x-vpnn',{})
                if mode=='vk' and meta.get('mode')=='vk':
                    if proxy.get('type')!='vless': raise ValueError('unexpected VK inner protocol')
                    proxy['uuid']='${device.uuid}'
                if mode=='dns' and meta.get('mode')=='dns':
                    meta['dns']['domains']=['${device.dns_label}.v.chichy.space']
                    meta['dns']['key']='${device.dns_key}'
    api('PUT','groups',groups)
    run('systemctl','stop','vpnn-dns')
    write('/etc/systemd/system/vpnn-dns.service',gateway)
    write('/etc/systemd/system/vpnn-dns@.service',backend)
    write('/etc/systemd/system/vpnn-node-sync.service',sync)
    run('systemctl','daemon-reload')
    run('systemctl','enable','--now','vpnn-node-sync')
    for attempt in range(60):
        try:
            status=json.loads(Path('/run/vpnn-node/status.json').read_text())
            if status.get('healthy'):
                print(json.dumps({'nodeReady':True,'appliedVersion':status['appliedVersion'],'dnsDevices':status['dnsDevices'],'vkDevices':status['vkDevices'],'backup':str(backup)}))
                return
        except (OSError,ValueError): pass
        time.sleep(1)
    raise RuntimeError('node did not report a healthy applied state')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True)
    install(parser.parse_args().stage)
