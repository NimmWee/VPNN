import json
import socket
import subprocess

out = {}
for name, address, port, kind in [
    ("dns", "89.125.120.163", 53, socket.SOCK_DGRAM),
    ("turn", "0.0.0.0", 56010, socket.SOCK_DGRAM),
    ("vless", "127.0.0.1", 24430, socket.SOCK_STREAM),
    ("dns-egress", "127.0.0.1", 24431, socket.SOCK_STREAM),
]:
    try:
        with socket.socket(socket.AF_INET, kind) as s:
            s.bind((address, port))
        out[name] = "free"
    except OSError as e:
        out[name] = str(e)
out["existing"] = subprocess.run("systemctl is-active x-ui vps-vk nginx fail2ban", shell=True, capture_output=True, text=True).stdout
print(json.dumps(out))
