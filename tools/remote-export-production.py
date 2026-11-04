import json
from pathlib import Path
import tarfile

paths=['/etc/vpnn-control','/var/lib/vpnn-control','/etc/vpnn-transports','/etc/letsencrypt','/etc/nginx/vpnn-stream-map.conf','/etc/nginx/vpnn-control-proxy.conf','/etc/nginx/conf.d/vpnn-control.conf','/etc/nginx/kit-stream.conf','/etc/systemd/system/vpnn-control.service','/etc/systemd/system/vpnn-dns.service','/etc/systemd/system/vpnn-vk.service','/etc/systemd/system/vpnn-egress.service']
paths += ['/etc/vpnn-node', '/etc/systemd/system/vpnn-dns@.service',
          '/etc/systemd/system/vpnn-node-sync.service', '/opt/vpnn-control/node_sync.py']
output=Path('/root/vpnn-control-stage/recovery.tar.gz')
with tarfile.open(output,'w:gz',dereference=True) as archive:
    for value in paths:
        path=Path(value)
        if path.exists():
            archive.add(path,arcname=value.lstrip('/'))
output.chmod(0o600)
print(json.dumps({'snapshotCreated':True,'bytes':output.stat().st_size}))
