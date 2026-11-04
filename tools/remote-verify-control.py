import json
import subprocess

def run(*args):
    result=subprocess.run(args,text=True,capture_output=True,timeout=20)
    return {'rc':result.returncode,'out':result.stdout[:1600],'err':result.stderr[:300]}

print(json.dumps({'services':run('systemctl','is-active','vpnn-control','vpnn-dns','vpnn-vk','vpnn-egress','nginx','x-ui','vps-vk','fail2ban'),'nginx':run('nginx','-t'),'control':run('systemctl','show','vpnn-control','-p','MemoryCurrent','-p','NRestarts','-p','User'),'listeners':run('ss','-lntp','( sport = :8098 or sport = :10448 )'),'renewal':run('systemctl','is-enabled','certbot.timer')}))
