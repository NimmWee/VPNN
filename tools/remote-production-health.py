"""Summarize owned-node readiness without credentials, device IDs or process arguments."""
import json
from pathlib import Path
import subprocess
def run(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=25)
    if result.returncode: raise RuntimeError('health command failed: '+args[0])
    return result.stdout.strip()
names=['vpnn-control','vpnn-node-sync','vpnn-dns','vpnn-vk','vpnn-egress','x-ui','vps-vk','nginx','fail2ban']
services={name:run('systemctl','is-active',name) for name in names}
status=json.loads(Path('/run/vpnn-node/status.json').read_text())
state=json.loads(Path('/var/lib/vpnn-control/state.json').read_text())
memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:','SwapFree:'))}
run('nginx','-t')
print(json.dumps({'services':services,'nodeHealthy':status.get('healthy'),
 'publishedVersion':state['version'],'appliedVersion':status.get('appliedVersion'),
 'activeDevices':sum(1 for device in state['devices'].values() if device['enabled']),
 'dnsDevices':status.get('dnsDevices'),'vkDevices':status.get('vkDevices'),
 'memoryKiB':memory,'nodeSyncRestarts':run('systemctl','show','vpnn-node-sync','-p','NRestarts','--value'),
 'certbotTimer':run('systemctl','is-enabled','certbot.timer'),
 'certificate':run('openssl','x509','-in','/etc/letsencrypt/live/vpn.chichy.space/fullchain.pem','-noout','-enddate'),
 'sshMaxRetry':run('fail2ban-client','get','sshd','maxretry'),
 'sshBanSeconds':run('fail2ban-client','get','sshd','bantime')}))
