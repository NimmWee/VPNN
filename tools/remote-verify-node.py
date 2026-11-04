import json
from pathlib import Path
import subprocess

def run(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=20)
    return {'rc':result.returncode,'out':result.stdout[:1800],'err':result.stderr[:300]}
status=json.loads(Path('/run/vpnn-node/status.json').read_text())
print(json.dumps({'status':status,'services':run('systemctl','is-active','vpnn-node-sync','vpnn-dns','vpnn-vk','vpnn-egress','vpnn-control','x-ui','vps-vk','nginx','fail2ban'),'memory':run('free','-m'),'dnsBackends':run('systemctl','list-units','--no-legend','--no-pager','vpnn-dns@*.service'),'syncRestarts':run('systemctl','show','vpnn-node-sync','-p','NRestarts')}))
