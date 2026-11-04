import json
import socket
import subprocess

try:
    addresses={item[4][0] for item in socket.getaddrinfo('vpn.chichy.space',443,type=socket.SOCK_STREAM)}
except OSError:
    print(json.dumps({'blocked':'DNS record vpn.chichy.space is not published yet'}))
    raise SystemExit(2)
if '89.125.120.163' not in addresses:
    raise SystemExit('hostname does not point to the authorized VPS')
result=subprocess.run(['python3','/root/vpnn-control-stage/install.py','--domain','vpn.chichy.space','--stage','/root/vpnn-control-stage'],capture_output=True,text=True,timeout=900)
print(result.stdout)
if result.returncode:
    print(result.stderr[-2500:])
raise SystemExit(result.returncode)
