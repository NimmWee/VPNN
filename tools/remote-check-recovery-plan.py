"""Validate recovery on the live server without applying or changing its services."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
stage=Path('/root/vpnn-control-stage')
with tempfile.TemporaryDirectory(prefix='vpnn-recovery-validation-') as directory:
    bundle=Path(directory)/'bundle'
    bundle.mkdir()
    with tarfile.open(stage/'recovery-tools-0.1.1.tar.gz','r:gz') as archive:
        archive.extractall(bundle,filter='data')
    sys.path.insert(0,str(bundle))
    import recovery
    import restore_stack
    snapshot=Path(directory)/'snapshot'
    recovery.unpack((stage/'recovery.tar.gz').read_bytes(),snapshot)
    wanted=restore_stack.plan(snapshot,bundle,'89.125.120.163','vpn.chichy.space')
    manifest=json.loads((bundle/'sha256.json').read_text())
    matches={name:hashlib.sha256(Path(path).read_bytes()).hexdigest()==manifest[name] for name,path in restore_stack.BINARIES.items()}
    if not all(matches.values()): raise RuntimeError('recovery binary differs from running installation')
    refused=False
    try: restore_stack.assert_clean()
    except ValueError: refused=True
    if not refused: raise RuntimeError('existing-server guard failed')
    print(json.dumps({'dryRunValidated':True,'applyRefusedExistingStack':True,'dnsDevices':wanted['dnsDevices'],'vkDevices':wanted['vkDevices'],'binaryMatchesLive':matches,'systemFilesChanged':False}))
