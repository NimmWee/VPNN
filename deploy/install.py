#!/usr/bin/env python3
"""Install VPNN control on the existing KIT node, preserving its VPN services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import urllib.request

MARKER = '# Managed by VPNN control installer\n'
STREAM_INCLUDE = 'include /etc/nginx/vpnn-stream-map.conf;'

def validate_domain(domain):
    if len(domain) > 253 or not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
        raise ValueError('a plain lowercase public hostname is required')

def add_stream_include(text):
    if STREAM_INCLUDE in text:
        return text
    pattern=r'(map\s+\$ssl_preread_server_name\s+\$kit_upstream\s*\{)'
    if len(re.findall(pattern,text)) != 1:
        raise ValueError('unrecognized KIT stream map; refusing to replace existing routing')
    return re.sub(pattern,lambda m:m[0]+'\n        '+STREAM_INCLUDE,text,count=1)

def run(*args,timeout=60):
    result=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError(args[0]+' failed: '+result.stderr[-1800:])
    return result.stdout

def write(path,data,mode=0o644):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.vpnn-new')
    temporary.write_bytes(data.encode() if isinstance(data,str) else data)
    temporary.chmod(mode)
    os.replace(temporary,path)

def nginx_transaction(files,backup):
    previous={Path(p):Path(p).read_bytes() if Path(p).exists() else None for p in files}
    for path,data in previous.items():
        if data is not None:
            write(backup/(str(path).lstrip('/').replace('/','_')),data,0o600)
    try:
        for path,data in files.items():
            write(path,data)
        run('nginx','-t')
        run('systemctl','reload','nginx')
    except Exception:
        for path,data in previous.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                write(path,data)
        run('nginx','-t')
        run('systemctl','reload','nginx')
        raise

def install(args):
    import pwd
    validate_domain(args.domain)
    if os.geteuid()!=0:
        raise ValueError('run as root')
    stage=Path(args.stage).resolve()
    binary=stage/'vpnn-control'
    manifest=json.loads((stage/'sha256.json').read_text())
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=manifest.get('vpnn-control'):
        raise ValueError('control binary checksum mismatch')
    stream=Path('/etc/nginx/kit-stream.conf')
    original_stream=stream.read_text()
    updated_stream=add_stream_include(original_stream)
    run('nginx','-t')
    http_path=Path('/etc/nginx/conf.d/vpnn-control.conf')
    if http_path.exists() and not http_path.read_text().startswith(MARKER):
        raise ValueError('unmanaged nginx config exists')
    try:
        account=pwd.getpwnam('vpnncontrol')
    except KeyError:
        run('useradd','--system','--no-create-home','--shell','/usr/sbin/nologin','vpnncontrol')
        account=pwd.getpwnam('vpnncontrol')
    if not Path('/etc/systemd/system/vpnn-control.service').exists():
        for host,port in [('127.0.0.1',8098),('127.0.0.1',10448),('0.0.0.0',80)]:
            with socket.socket() as probe:
                probe.bind((host,port))
    backup=Path('/var/backups/vpnn-control')/time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True,mode=0o700)
    backup.parent.chmod(0o700)
    data=Path('/var/lib/vpnn-control')
    data.mkdir(mode=0o700,exist_ok=True)
    data.chmod(0o700)
    os.chown(data,account.pw_uid,account.pw_gid)
    for name in ['state.json','state.json.signing']:
        destination=data/name
        if not destination.exists():
            if not (stage/name).is_file():
                raise ValueError('initial installation requires private '+name)
            write(destination,(stage/name).read_bytes(),0o600)
            os.chown(destination,account.pw_uid,account.pw_gid)
    config=Path('/etc/vpnn-control')
    config.mkdir(mode=0o750,exist_ok=True)
    os.chown(config,0,account.pw_gid)
    if not (config/'admin.secret').exists():
        secret=(stage/'admin.secret').read_bytes().strip()
        if len(secret)<24:
            raise ValueError('invalid administrator secret')
        write(config/'admin.secret',secret,0o640)
        os.chown(config/'admin.secret',0,account.pw_gid)
    target=Path('/opt/vpnn-control/vpnn-control')
    if target.exists():
        write(backup/'vpnn-control',target.read_bytes(),0o700)
    write(target,binary.read_bytes(),0o755)
    unit=f'''[Unit]
Description=VPNN signed configuration and administration
After=network-online.target
Wants=network-online.target

[Service]
User=vpnncontrol
Group=vpnncontrol
ExecStart=/opt/vpnn-control/vpnn-control -listen 127.0.0.1:8098 -state /var/lib/vpnn-control/state.json -admin-secret-file /etc/vpnn-control/admin.secret -node-status-file /run/vpnn-node/status.json -max-active-devices 8 -public-url https://{args.domain}
Restart=on-failure
RestartSec=5
Environment=GOMAXPROCS=2
Environment=GOMEMLIMIT=64MiB
StateDirectory=vpnn-control
StateDirectoryMode=0700
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet=
UMask=0077
MemoryMax=128M
TasksMax=64
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
'''
    write('/etc/systemd/system/vpnn-control.service',unit)
    run('systemctl','daemon-reload')
    run('systemctl','enable','vpnn-control')
    run('systemctl','restart','vpnn-control')
    for attempt in range(20):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8098/health',timeout=2) as response:
                if response.status==200:
                    break
        except OSError:
            time.sleep(.5)
    else:
        raise RuntimeError('control health check failed')
    webroot=Path('/var/www/vpnn-acme')
    webroot.mkdir(parents=True,exist_ok=True,mode=0o755)
    http=MARKER+f'''server {{
    listen 80;
    listen [::]:80;
    server_name {args.domain};
    server_tokens off;
    access_log off;
    location ^~ /.well-known/acme-challenge/ {{ root {webroot}; }}
    location / {{ return 301 https://{args.domain}$request_uri; }}
}}
'''
    if not Path('/etc/letsencrypt/live',args.domain,'fullchain.pem').exists():
        nginx_transaction({http_path:http},backup)
    if shutil.which('ufw'):
        run('ufw','allow','80/tcp','comment','VPNN HTTPS certificate renewal')
    if args.prepare_only:
        print(json.dumps({'prepared':True,'publicHTTPS':False,'httpListener':'127.0.0.1:8098'}))
        return
    if not shutil.which('certbot'):
        run('apt-get','update',timeout=300)
        run('apt-get','install','-y','certbot',timeout=600)
    run('certbot','certonly','--webroot','-w',str(webroot),'-d',args.domain,'--non-interactive','--agree-tos','--register-unsafely-without-email','--keep-until-expiring',timeout=180)
    https=f'''
limit_req_zone $binary_remote_addr zone=vpnn_api:1m rate=20r/s;
limit_req_zone $binary_remote_addr zone=vpnn_login:1m rate=5r/m;
server {{
    listen 127.0.0.1:10448 ssl proxy_protocol;
    server_name {args.domain};
    ssl_certificate /etc/letsencrypt/live/{args.domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{args.domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    set_real_ip_from 127.0.0.1;
    real_ip_header proxy_protocol;
    server_tokens off;
    access_log off;
    client_max_body_size 1m;
    add_header Strict-Transport-Security "max-age=86400" always;
    location /api/node/ {{ return 403; }}
    location = /api/admin/login {{
        limit_req zone=vpnn_login burst=5 nodelay;
        include /etc/nginx/vpnn-control-proxy.conf;
    }}
    location / {{
        limit_req zone=vpnn_api burst=40 nodelay;
        include /etc/nginx/vpnn-control-proxy.conf;
    }}
}}
'''
    proxy='''proxy_pass http://127.0.0.1:8098;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_connect_timeout 5s;
proxy_read_timeout 20s;
proxy_send_timeout 20s;
'''
    nginx_transaction({stream:updated_stream,http_path:http+https,Path('/etc/nginx/vpnn-stream-map.conf'):MARKER+f'{args.domain} 127.0.0.1:10448;\n',Path('/etc/nginx/vpnn-control-proxy.conf'):MARKER+proxy},backup)
    hook=Path('/etc/letsencrypt/renewal-hooks/deploy/vpnn-nginx')
    write(hook,'#!/bin/sh\nset -eu\n/usr/sbin/nginx -t\n/bin/systemctl reload nginx\n',0o755)
    run('systemctl','enable','--now','certbot.timer')
    print(json.dumps({'installed':True,'url':'https://'+args.domain,'httpListener':'127.0.0.1:8098','backup':str(backup),'signingKeyPreserved':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain',required=True)
    parser.add_argument('--stage',required=True)
    parser.add_argument('--prepare-only',action='store_true')
    install(parser.parse_args())
