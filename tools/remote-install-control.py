import subprocess
result=subprocess.run(['python3','/root/vpnn-control-stage/install.py','--domain','vpn.chichy.space','--stage','/root/vpnn-control-stage','--prepare-only'],capture_output=True,text=True,timeout=120)
print(result.stdout)
if result.returncode:
    print(result.stderr[-2500:])
raise SystemExit(result.returncode)
