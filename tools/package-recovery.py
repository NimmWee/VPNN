"""Package pinned Linux tools and the restore program; never include secrets or signing keys."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
root=Path(__file__).resolve().parents[1]
target=root/'artifacts/recovery-tools-0.1.1'
target.mkdir(exist_ok=True)
files={'vpnn-control':root/'artifacts/vpnn-control-linux-amd64',
       'vpnn-dns-gateway':root/'artifacts/vpnn-dns-gateway-linux-amd64',
       **{name:root/'artifacts/transport-node'/name for name in ['freeturn-server','masterdns-server','xray']},
       **{name:root/'deploy'/name for name in ['node_sync.py','recovery.py','restore_stack.py','restore.sh']}}
for name,source in files.items(): shutil.copy2(source,target/name)
licenses=target/'licenses'
licenses.mkdir(exist_ok=True)
for folder,label in [('client','FlClash-GPL-3.0'),('client/core/Clash.Meta','mihomo-GPL-3.0'),('transports/freeturn','FreeTurn'),('transports/masterdns','MasterDnsVPN-MIT'),('transports/anet','ANet-MIT'),('transports/xray','Xray-MPL-2.0')]:
    source=root/folder/'LICENSE'
    if source.exists(): shutil.copy2(source,licenses/(label+'.txt'))
shutil.copy2(root/'NOTICES.md',target/'NOTICES.md')
shutil.copy2(root/'deploy/README.md',target/'README.md')
manifest={name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in files}
(target/'sha256.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(root/'artifacts/VPNN-Recovery-Tools-0.1.1.tar.gz','w:gz') as archive:
    for path in sorted(target.rglob('*')):
        if not path.is_file(): continue
        info=archive.gettarinfo(str(path),arcname=str(path.relative_to(target)).replace('\\','/'))
        info.uid=info.gid=0
        info.uname=info.gname='root'
        info.mode=0o755 if path.name in ['restore.sh',*['vpnn-control','vpnn-dns-gateway','freeturn-server','masterdns-server','xray']] else 0o644
        with path.open('rb') as file: archive.addfile(info,file)
print('Recovery tools packaged with pinned checksums; credentials excluded')
