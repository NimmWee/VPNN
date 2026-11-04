import json
import subprocess

def run(command):
    p = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=20)
    return {"rc": p.returncode, "out": p.stdout[:14000], "err": p.stderr[:1000]}

checks = {
    "os": "cat /etc/os-release; uname -m; uptime",
    "resources": "free -m; df -h / /opt",
    "listeners": "ss -lntup",
    "units": "systemctl list-units --type=service --state=running --no-pager --no-legend",
    "firewall": "ufw status numbered 2>/dev/null; nft list ruleset 2>/dev/null | head -100",
    "paths": "ls -ld /opt/vpnn* /etc/vpnn* /opt/free-turn* /opt/masterdns* 2>/dev/null; command -v python3 systemctl openssl",
}
print(json.dumps({name: run(command) for name, command in checks.items()}))
