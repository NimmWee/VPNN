"""Read-only production prerequisites; never prints server credentials."""
import json
from pathlib import Path
import re
import shutil
import subprocess

def run(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=20)
    return {"rc": result.returncode, "out": result.stdout[:2500], "err": result.stderr[:200]}

hosts=[]
for path in Path('/etc/nginx/sites-enabled').glob('*'):
    text=path.read_text()
    hosts.append({'file':str(path),'listen':re.findall(r'^\s*listen\s+([^;]+);',text,re.M),'names':re.findall(r'^\s*server_name\s+([^;]+);',text,re.M)})
nginx=subprocess.run(['nginx','-T'],text=True,capture_output=True,timeout=20)
selected=[line for line in nginx.stdout.splitlines() if re.search(r'configuration file|^\s*(stream|http|map|server|listen|include|proxy_pass|ssl_preread|ssl_certificate)\b',line)]
print(json.dumps({'nginx':hosts,'nginxStructure':selected,'listeners':run('ss','-lntp','( sport = :80 or sport = :443 or sport = :8098 )'),'units':run('systemctl','is-active','nginx','vpnn-dns','vpnn-vk','vpnn-egress','fail2ban'),'tools':{x:shutil.which(x) for x in ['nginx','certbot','openssl','curl']},'resources':run('free','-m')}))
