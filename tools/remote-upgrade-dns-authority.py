import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path('/opt/vpnn-transports')
cfg=Path('/etc/vpnn-transports/masterdns.json')
stage=Path('/root/vpnn-transport-stage')
manifest=json.loads((stage/'sha256.json').read_text())
data=(stage/'masterdns-server').read_bytes()
if hashlib.sha256(data).hexdigest()!=manifest['masterdns-server']:
    raise SystemExit('checksum mismatch')
binary=root/'masterdns-server'
backup=root/'masterdns-server.before-authority'
config_backup=cfg.with_suffix('.before-authority.json')
if backup.exists() or config_backup.exists():
    raise SystemExit('authority upgrade already attempted; inspect backups')
shutil.copy2(binary,backup)
shutil.copy2(cfg,config_backup)
config=json.loads(cfg.read_text())
config['AUTHORITATIVE_NS']='ns.chichy.space'
new_config=cfg.with_suffix('.tmp')
new_config.write_text(json.dumps(config,indent=2))
new_config.chmod(0o640)
os.chown(new_config,cfg.stat().st_uid,cfg.stat().st_gid)
replacement=root/'masterdns-server.new'
replacement.write_bytes(data)
replacement.chmod(0o755)
os.replace(replacement,binary)
os.replace(new_config,cfg)
p=subprocess.run(['systemctl','restart','vpnn-dns.service'],capture_output=True,text=True,timeout=30)
if p.returncode:
    shutil.copy2(backup,binary)
    shutil.copy2(config_backup,cfg)
    subprocess.run(['systemctl','restart','vpnn-dns.service'],timeout=30)
    raise SystemExit('DNS upgrade rejected and original restored')
print('DNS authority metadata enabled; only vpnn-dns restarted.')
print(subprocess.run(['systemctl','is-active','vpnn-dns','vpnn-vk','vpnn-egress','x-ui','vps-vk'],capture_output=True,text=True).stdout)
