"""Interactive, password-in-memory SSH session for explicit remote scripts/files."""
import argparse
import base64
import getpass
import hashlib
import json
import pathlib
import shlex
import sys

import paramiko

parser = argparse.ArgumentParser()
parser.add_argument("host")
parser.add_argument("--user", default="root")
args = parser.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]
known = root / "private" / "ssh_known_hosts"
known.parent.mkdir(parents=True, exist_ok=True)
client = paramiko.SSHClient()
if known.exists():
    client.load_host_keys(str(known))


class FirstUse(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, ssh, hostname, key):
        digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        print("FIRST_USE_HOST_KEY SHA256:" + digest, flush=True)
        ssh.get_host_keys().add(hostname, key.get_name(), key)
        ssh.save_host_keys(str(known))


client.set_missing_host_key_policy(FirstUse())
password = getpass.getpass("SSH password (memory only): ")
try:
    client.connect(args.host, username=args.user, password=password,
                   look_for_keys=False, allow_agent=False, timeout=15,
                   auth_timeout=15, banner_timeout=15)
finally:
    del password
print("READY", flush=True)
try:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request["action"] == "quit":
                break
            if request["action"] in ("python", "shell"):
                script = pathlib.Path(request["path"]).read_text(encoding="utf-8-sig")
                command = ("python3 -c " if request["action"] == "python" else "bash -c ") + shlex.quote(script)
                _, stdout, stderr = client.exec_command(command, timeout=request.get("timeout", 90))
                out, err = stdout.read().decode(), stderr.read().decode()
                code = stdout.channel.recv_exit_status()
                if request.get("save"):
                    pathlib.Path(request["save"]).write_text(out, encoding="utf-8")
                print(json.dumps({"rc": code, "out": out[:request.get("limit", 6000)], "stderr": err[:1500]}), flush=True)
            elif request["action"] in ("get", "put"):
                with client.open_sftp() as sftp:
                    if request["action"] == "get":
                        sftp.get(request["remote"], request["local"])
                    else:
                        sftp.put(request["local"], request["remote"])
                        sftp.chmod(request["remote"], request.get("mode", 0o600))
                print("TRANSFER_OK", flush=True)
        except Exception as error:
            print(json.dumps({"error": type(error).__name__, "detail": str(error)}), flush=True)
finally:
    client.close()
