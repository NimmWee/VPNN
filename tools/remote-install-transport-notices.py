from pathlib import Path
import shutil

stage=Path('/root/vpnn-transport-stage')
root=Path('/opt/vpnn-transports')
for name in ('LICENSE-FreeTurn.txt','LICENSE-MasterDnsVPN.txt','LICENSE-Xray.txt'):
    shutil.copyfile(stage/name,root/name)
    (root/name).chmod(0o644)
print('Upstream license notices installed with the isolated server binaries.')
