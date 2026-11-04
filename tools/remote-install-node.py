import subprocess
result=subprocess.run(['python3','/root/vpnn-control-stage/install_node.py','--stage','/root/vpnn-control-stage'],capture_output=True,text=True,timeout=150)
print(result.stdout)
if result.returncode: print(result.stderr[-2000:])
raise SystemExit(result.returncode)
