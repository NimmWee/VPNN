"""Install a separate, single-owner DNS/VK test stack; never edits existing VPN services."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import uuid

ROOT = Path('/opt/vpnn-transports')
CFG = Path('/etc/vpnn-transports')
IP = '89.125.120.163'
DOMAIN = 'v.chichy.space'

def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=45).stdout.strip()

def write(path, content, mode=0o600):
    data = content if isinstance(content, str) else json.dumps(content, indent=2)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(data + '\n')
    temporary.chmod(mode)
    os.replace(temporary, path)

if os.geteuid() != 0:
    raise SystemExit('root required')
if ROOT.exists() or CFG.exists():
    raise SystemExit('existing VPNN transport installation: inspect before updating')
ipaddress.ip_address(IP)
for host, port, kind in [(IP,53,socket.SOCK_DGRAM),('0.0.0.0',56010,socket.SOCK_DGRAM),('127.0.0.1',24430,socket.SOCK_STREAM),('127.0.0.1',24431,socket.SOCK_STREAM)]:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind((host, port))

source = Path('/root/vpnn-transport-stage')
manifest = json.loads((source/'sha256.json').read_text())
for name in ('masterdns-server', 'freeturn-server', 'xray'):
    if hashlib.sha256((source/name).read_bytes()).hexdigest() != manifest[name]:
        raise SystemExit('binary checksum mismatch: ' + name)

run('useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'vpnntransport')
ROOT.mkdir(mode=0o755)
CFG.mkdir(mode=0o750)
run('chown', 'root:vpnntransport', str(CFG))
for name in manifest:
    if name not in ('masterdns-server', 'freeturn-server', 'xray'):
        raise SystemExit('unexpected manifest file')
    (ROOT/name).write_bytes((source/name).read_bytes())
    (ROOT/name).chmod(0o755)
for name in ('LICENSE-FreeTurn.txt','LICENSE-MasterDnsVPN.txt','LICENSE-Xray.txt'):
    (ROOT/name).write_bytes((source/name).read_bytes())
    (ROOT/name).chmod(0o644)

credentials = {'version':1, 'server':IP, 'domain':DOMAIN, 'uuid':str(uuid.uuid4()),
               'clientId':secrets.token_hex(16), 'obfKey':secrets.token_hex(32),
               'dnsKey':secrets.token_urlsafe(24), 'turnPort':56010}
write(CFG/'owner.json', credentials)
write(CFG/'dns.key', credentials['dnsKey'], 0o640)
write(CFG/'clients.json', {'clients':{credentials['clientId']:{'comment':'VPNN owner test'}}}, 0o640)
write(CFG/'freeturn.env', 'VPNN_OBF_KEY=' + credentials['obfKey'], 0o600)
write(CFG/'masterdns.json', {
    'UDP_HOST':IP, 'UDP_PORT':53, 'DOMAIN':[DOMAIN], 'AUTHORITATIVE_NS':'ns.chichy.space', 'PROTOCOL_TYPE':'SOCKS5',
    'DATA_ENCRYPTION_METHOD':5, 'ENCRYPTION_KEY_FILE':str(CFG/'dns.key'),
    'USE_EXTERNAL_SOCKS5':True, 'FORWARD_IP':'127.0.0.1', 'FORWARD_PORT':24431,
    'UDP_READERS':2, 'DNS_REQUEST_WORKERS':2, 'DEFERRED_SESSION_WORKERS':2,
    'MAX_CONCURRENT_REQUESTS':1024, 'DEFERRED_SESSION_QUEUE_LIMIT':512,
    'DNS_CACHE_MAX_RECORDS':2000, 'SOCKET_BUFFER_SIZE':1048576, 'LOG_LEVEL':'ERROR'
}, 0o640)
write(CFG/'xray.json', {
    'log':{'loglevel':'warning'},
    'inbounds':[
        {'tag':'vk', 'listen':'127.0.0.1', 'port':24430, 'protocol':'vless',
         'settings':{'clients':[{'id':credentials['uuid']}], 'decryption':'none'},
         'streamSettings':{'network':'tcp','security':'none'}},
        {'tag':'dns', 'listen':'127.0.0.1', 'port':24431, 'protocol':'socks',
         'settings':{'auth':'noauth','udp':False}}
    ],
    'outbounds':[{'tag':'internet','protocol':'freedom'}, {'tag':'blocked','protocol':'blackhole'}],
    'routing':{'domainStrategy':'IPOnDemand', 'rules':[
        {'type':'field','ip':['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16',
                             '172.16.0.0/12','192.168.0.0/16','224.0.0.0/4','::/128','::1/128','fc00::/7','fe80::/10','ff00::/8'],
         'outboundTag':'blocked'}]}
}, 0o640)
for path in CFG.iterdir():
    if path.name not in ('owner.json','freeturn.env'):
        run('chown','root:vpnntransport',str(path))

run(str(ROOT/'xray'), 'run', '-test', '-config', str(CFG/'xray.json'))
common = '''[Service]
User=vpnntransport
Group=vpnntransport
Restart=on-failure
RestartSec=5
Environment=GOMAXPROCS=2
Environment=GOMEMLIMIT=64MiB
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
TasksMax=64
LimitNOFILE=4096
'''
services = {
    'vpnn-egress': ('Xray egress for VPNN transport tests', f'{ROOT}/xray run -config {CFG}/xray.json', 'MemoryMax=96M\n', ''),
    'vpnn-dns': ('VPNN MasterDnsVPN encrypted DNS tunnel', f'{ROOT}/masterdns-server -config {CFG}/masterdns.json -nowait', 'MemoryMax=192M\nAmbientCapabilities=CAP_NET_BIND_SERVICE\nCapabilityBoundingSet=CAP_NET_BIND_SERVICE\n', 'Requires=vpnn-egress.service\nAfter=vpnn-egress.service\n'),
    'vpnn-vk': ('VPNN FreeTurn relay for authenticated VLESS', f'{ROOT}/freeturn-server -listen 0.0.0.0:56010 -connect 127.0.0.1:24430 -mode tcp -obf-profile rtpopus3 -obf-key ${{VPNN_OBF_KEY}} -clients-file {CFG}/clients.json', f'MemoryMax=128M\nEnvironmentFile={CFG}/freeturn.env\n', 'Requires=vpnn-egress.service\nAfter=vpnn-egress.service\n')
}
for name,(description,command,extra,deps) in services.items():
    unit = '[Unit]\nDescription='+description+'\nAfter=network-online.target\nWants=network-online.target\n'+deps+'\n'+common+extra+'ExecStart='+command+'\n\n[Install]\nWantedBy=multi-user.target\n'
    write(Path('/etc/systemd/system')/(name+'.service'), unit, 0o644)

run('systemctl','daemon-reload')
run('systemctl','enable','--now',*[n+'.service' for n in services])
run('ufw','allow','53/udp','comment','VPNN DNS tunnel')
run('ufw','allow','56010/udp','comment','VPNN VK relay')
print(json.dumps({'installed':list(services), 'dns':IP+':53', 'vk':IP+':56010',
                  'secretsFile':str(CFG/'owner.json'), 'oldServices':run('systemctl','is-active','x-ui','vps-vk','nginx','fail2ban')}))
