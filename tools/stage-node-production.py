import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
files={'vpnn-control':root/'artifacts/vpnn-control-linux-amd64','vpnn-dns-gateway':root/'artifacts/vpnn-dns-gateway-linux-amd64','node_sync.py':root/'deploy/node_sync.py'}
manifest={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
(root/'private/production-control-stage/sha256.json').write_text(json.dumps(manifest))
print('Node/control checksums prepared; no credentials printed')
