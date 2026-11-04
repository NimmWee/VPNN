import json
import subprocess

names=['vpnn-dns','vpnn-vk','vpnn-egress','x-ui','vps-vk','nginx','fail2ban']
result={}
for name in names:
    p=subprocess.run(['systemctl','show',name,'--property=ActiveState,SubState,UnitFileState,MemoryCurrent,TasksCurrent,NRestarts'],text=True,capture_output=True,timeout=15)
    result[name]=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
p=subprocess.run(['ufw','status'],text=True,capture_output=True,timeout=15)
result['newFirewall']=[line for line in p.stdout.splitlines() if '53/udp' in line or '56010/udp' in line]
print(json.dumps(result))
