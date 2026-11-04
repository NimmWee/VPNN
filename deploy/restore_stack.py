#!/usr/bin/env python3
"""Restore the owned VPNN stack on a clean Ubuntu amd64 machine; dry-run by default."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time

import recovery
import node_sync

UNITS = ['vpnn-control', 'vpnn-dns', 'vpnn-dns@', 'vpnn-vk', 'vpnn-egress', 'vpnn-node-sync']
BINARIES = {'vpnn-control':'/opt/vpnn-control/vpnn-control',
            'vpnn-dns-gateway':'/opt/vpnn-control/vpnn-dns-gateway',
            'freeturn-server':'/opt/vpnn-transports/freeturn-server',
            'masterdns-server':'/opt/vpnn-transports/masterdns-server',
            'xray':'/opt/vpnn-transports/xray'}

def domain(value):
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}', value):
        raise ValueError('a lowercase public hostname is required')
    return value

def readdress(value, previous, current):
    if isinstance(value, dict):
        return {key:readdress(item,previous,current) for key,item in value.items()}
    if isinstance(value, list):
        return [readdress(item,previous,current) for item in value]
    if isinstance(value, str):
        # Replace only a complete IPv4 literal or host:port, never arbitrary text/secrets.
        if value == previous: return current
        if re.fullmatch(re.escape(previous)+r':\d+', value): return current+value[len(previous):]
    return value

def plan(snapshot, bundle, address, hostname):
    address=str(ipaddress.IPv4Address(address))
    if not ipaddress.ip_address(address).is_global: raise ValueError('public IPv4 required')
    domain(hostname)
    manifest=json.loads((bundle/'sha256.json').read_text())
    for name in [*BINARIES, 'node_sync.py']:
        if hashlib.sha256((bundle/name).read_bytes()).hexdigest()!=manifest.get(name):
            raise ValueError('recovery bundle checksum mismatch: '+name)
    state_path=snapshot/'var/lib/vpnn-control/state.json'
    state=json.loads(state_path.read_text())
    desired=node_sync.desired(state,'v.chichy.space',8)
    seed=snapshot/'var/lib/vpnn-control/state.json.signing'
    if seed.stat().st_size!=32: raise ValueError('invalid signing seed')
    if len((snapshot/'etc/vpnn-control/admin.secret').read_bytes().strip())<24:
        raise ValueError('invalid administrator key')
    for name in ['xray.json','clients.json']:
        if not isinstance(json.loads((snapshot/'etc/vpnn-transports'/name).read_text()),dict):
            raise ValueError('invalid transport configuration')
    environment=(snapshot/'etc/vpnn-transports/freeturn.env').read_text().strip()
    if not environment.startswith('VPNN_OBF_KEY=') or len(environment)<=20 or '\x00' in environment:
        raise ValueError('missing relay access key')
    units={}
    for name in UNITS:
        text=(snapshot/f'etc/systemd/system/{name}.service').read_text()
        if 'ExecStart=' not in text or '/opt/vpnn-' not in text:
            raise ValueError('unexpected recovery service')
        text=text.replace('89.125.120.163:53',address+':53')
        if name=='vpnn-control':
            text=re.sub(r'-public-url https://[^\s]+','-public-url https://'+hostname,text)
        units[name]=text
    cert=snapshot/f'etc/letsencrypt/live/{hostname}'
    if not (cert/'fullchain.pem').is_file() or not (cert/'privkey.pem').is_file():
        raise ValueError('backup has no certificate for this hostname')
    state=readdress(state,'89.125.120.163',address)
    state['version']=max(state['version']+1,int(time.time()*1000))
    return {'address':address,'hostname':hostname,'state':state,'units':units,
            'dnsDevices':len(desired['dns']),'vkDevices':len(desired['vk'])}

def run(*args,timeout=90):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if result.returncode: raise RuntimeError('restore command failed: '+args[0])
    return result.stdout

def write(path,data,mode=0o600,owner=None):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data,str) else data)
    path.chmod(mode)
    if owner: shutil.chown(path,user=owner,group=owner)

def assert_clean(address='89.125.120.163'):
    if any(Path(value).exists() for value in ['/var/lib/vpnn-control','/etc/vpnn-transports',
           '/etc/systemd/system/vpnn-control.service','/etc/nginx/kit-stream.conf']):
        raise ValueError('apply is only for a clean OS; existing VPNN/KIT must use the update installer')
    # systemd-resolved may legitimately own 127.0.0.53:53 on a fresh Ubuntu.
    for kind,host,port in [(socket.SOCK_DGRAM,address,53),(socket.SOCK_DGRAM,'0.0.0.0',56010),
                            *[(socket.SOCK_STREAM,'0.0.0.0',p) for p in [80,443,8098,24430,24431]]]:
        with socket.socket(socket.AF_INET,kind) as probe: probe.bind((host,port))

def wait_for_node():
    for _ in range(60):
        try:
            status=json.loads(Path('/run/vpnn-node/status.json').read_text())
            state=json.loads(Path('/var/lib/vpnn-control/state.json').read_text())
            age=int(time.time())-status.get('appliedAt',0)
            if status.get('healthy') and -30<=age<=45 and status.get('appliedVersion',0)>=state['version']:
                return
        except (OSError,ValueError,KeyError): pass
        time.sleep(1)
    raise RuntimeError('restored node did not confirm the current state')

def apply(snapshot,bundle,wanted):
    import grp
    import pwd
    if os.geteuid()!=0: raise ValueError('root required')
    if os.uname().machine!='x86_64': raise ValueError('amd64 server required')
    os_release=Path('/etc/os-release').read_text()
    if 'ID=ubuntu' not in os_release: raise ValueError('Ubuntu required')
    marker=Path('/var/lib/vpnn-restore/restore.json')
    identity=hashlib.sha256((snapshot/'var/lib/vpnn-control/state.json.signing').read_bytes()+
        (bundle/'sha256.json').read_bytes()+wanted['address'].encode()+wanted['hostname'].encode()).hexdigest()
    previous=json.loads(marker.read_text()) if marker.exists() else None
    if previous is not None and previous.get('identity')!=identity:
        raise ValueError('a different restoration owns this machine')
    if previous is not None and previous.get('complete'):
        for service in ['vpnn-control','vpnn-egress','vpnn-vk','vpnn-node-sync','vpnn-dns']:
            run('systemctl','is-active',service)
        wait_for_node()
        return
    if previous is None:
        assert_clean(wanted['address'])
        write(marker,json.dumps({'identity':identity,'complete':False}))
    run('apt-get','update',timeout=300)
    run('apt-get','install','-y','nginx','certbot','fail2ban','ufw',timeout=600)
    for account in ['vpnncontrol','vpnntransport']:
        try: pwd.getpwnam(account)
        except KeyError: run('useradd','--system','--no-create-home','--shell','/usr/sbin/nologin',account)
    for name,target in BINARIES.items(): write(target,(bundle/name).read_bytes(),0o755)
    write('/opt/vpnn-control/node_sync.py',(bundle/'node_sync.py').read_bytes(),0o755)
    # A retry resumes the same restore without rolling back updates already accepted by control.
    for relative,data in [('state.json',json.dumps(wanted['state']).encode()),
                          ('state.json.signing',(snapshot/'var/lib/vpnn-control/state.json.signing').read_bytes())]:
        destination=Path('/var/lib/vpnn-control')/relative
        if relative=='state.json.signing' and destination.exists() and destination.read_bytes()!=data:
            raise ValueError('existing signing identity differs from recovery snapshot')
        if not destination.exists(): write(destination,data,owner='vpnncontrol')
    shutil.chown('/var/lib/vpnn-control',user='vpnncontrol',group='vpnncontrol')
    Path('/var/lib/vpnn-control').chmod(0o700)
    if not Path('/etc/vpnn-control/admin.secret').exists():
        write('/etc/vpnn-control/admin.secret',(snapshot/'etc/vpnn-control/admin.secret').read_bytes(),0o640)
    shutil.chown('/etc/vpnn-control',group='vpnncontrol')
    Path('/etc/vpnn-control').chmod(0o750)
    shutil.chown('/etc/vpnn-control/admin.secret',group='vpnncontrol')
    for name in ['xray.json','clients.json']:
        source=snapshot/'etc/vpnn-transports'/name
        value=readdress(json.loads(source.read_text()),'89.125.120.163',wanted['address'])
        write('/etc/vpnn-transports/'+name,json.dumps(value),0o640)
        shutil.chown('/etc/vpnn-transports/'+name,group='vpnntransport')
    write('/etc/vpnn-transports/freeturn.env',(snapshot/'etc/vpnn-transports/freeturn.env').read_bytes(),0o640)
    shutil.chown('/etc/vpnn-transports/freeturn.env',group='vpnntransport')
    Path('/etc/vpnn-transports').chmod(0o750)
    shutil.chown('/etc/vpnn-transports',group='vpnntransport')
    for directory in ['/etc/vpnn-node','/etc/vpnn-node/devices']:
        Path(directory).mkdir(parents=True,exist_ok=True,mode=0o750)
        shutil.chown(directory,group='vpnntransport')
    write('/etc/vpnn-node/targets.json','{}',0o640)
    shutil.chown('/etc/vpnn-node/targets.json',group='vpnntransport')
    # Copy only the control hostname's certificate lineage; private client signing stays staged.
    host=wanted['hostname']
    for relative in [f'live/{host}/fullchain.pem', f'live/{host}/privkey.pem',f'live/{host}/cert.pem', f'live/{host}/chain.pem']:
        source=snapshot/'etc/letsencrypt'/relative
        if source.exists(): write('/etc/vpnn-tls/'+relative,source.read_bytes())
    proxy='''proxy_pass http://127.0.0.1:8098;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-Proto https;
proxy_read_timeout 20s;
'''
    write('/etc/nginx/vpnn-control-proxy.conf',proxy,0o644)
    configuration=f'''server {{
listen 80;
server_name {host};
location ^~ /.well-known/acme-challenge/ {{ root /var/www/vpnn-acme; }}
location / {{ return 301 https://{host}$request_uri; }}
}}
server {{
listen 443 ssl;
server_name {host};
ssl_certificate /etc/vpnn-tls/live/{host}/fullchain.pem;
ssl_certificate_key /etc/vpnn-tls/live/{host}/privkey.pem;
ssl_protocols TLSv1.2 TLSv1.3;
server_tokens off;
access_log off;
client_max_body_size 1m;
add_header Strict-Transport-Security "max-age=86400" always;
location /api/node/ {{ return 403; }}
location / {{ include /etc/nginx/vpnn-control-proxy.conf; }}
}}
'''
    write('/etc/nginx/conf.d/vpnn-control.conf',configuration,0o644)
    Path('/var/www/vpnn-acme').mkdir(parents=True,exist_ok=True)
    for name,text in wanted['units'].items(): write('/etc/systemd/system/'+name+'.service',text,0o644)
    run('nginx','-t')
    run('systemctl','daemon-reload')
    for name in ['vpnn-control','vpnn-egress','vpnn-vk','vpnn-node-sync','vpnn-dns']:
        run('systemctl','enable','--now',name)
    run('systemctl','reload','nginx')
    for port in ['22/tcp','80/tcp','443/tcp','53/udp','56010/udp']: run('ufw','allow',port)
    # Do not enable UFW automatically: provider console/SSH policy belongs to the operator.
    write('/etc/fail2ban/jail.d/vpnn-sshd.local','[sshd]\nenabled = true\nbackend = systemd\nmaxretry = 3\nfindtime = 600\nbantime = 30d\n',0o644)
    run('systemctl','enable','--now','fail2ban')
    run('systemctl','restart','fail2ban')
    run('certbot','certonly','--webroot','-w','/var/www/vpnn-acme','-d',host,'--non-interactive','--agree-tos','--register-unsafely-without-email','--keep-until-expiring',timeout=180)
    write('/etc/nginx/conf.d/vpnn-control.conf',configuration.replace('/etc/vpnn-tls/live/','/etc/letsencrypt/live/'),0o644)
    run('nginx','-t')
    run('systemctl','reload','nginx')
    write('/etc/letsencrypt/renewal-hooks/deploy/vpnn-nginx','#!/bin/sh\nset -eu\n/usr/sbin/nginx -t\n/bin/systemctl reload nginx\n',0o755)
    run('systemctl','enable','--now','certbot.timer')
    wait_for_node()
    write(marker,json.dumps({'identity':identity,'complete':True}))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',required=True)
    parser.add_argument('--key-file',required=True)
    parser.add_argument('--address',required=True)
    parser.add_argument('--domain',default='vpn.chichy.space')
    parser.add_argument('--bundle',default=str(Path(__file__).resolve().parent))
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='vpnn-restore-') as directory:
        snapshot=Path(directory)/'snapshot'
        recovery.unpack(recovery.open_snapshot(Path(args.backup).read_bytes(),Path(args.key_file).read_bytes()),snapshot)
        wanted=plan(snapshot,Path(args.bundle),args.address,args.domain)
        if args.apply: apply(snapshot,Path(args.bundle),wanted)
        print(json.dumps({'validated':True,'applied':args.apply,'dnsDevices':wanted['dnsDevices'],'vkDevices':wanted['vkDevices'],'address':wanted['address']}))

if __name__=='__main__': main()
