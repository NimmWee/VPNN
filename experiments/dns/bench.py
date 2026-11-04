"""Run source-built MasterDnsVPN and upstream Slipstream through the same lab."""
import argparse
import hashlib
import json
import math
import platform
import queue
import socket
import socketserver
import subprocess
import threading
import time
import traceback
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

import psutil

from resolver import FakeResolver, HOST, Profile

DOMAIN = "lab.example.test"
TARGET_NAME = b"target.example.test"
PROFILES = {
    "clean": Profile(),
    "delay": Profile(delay=.025),
    "capped": Profile(delay=.025, qps=300),
    "impaired": Profile(delay=.025, drop_every=23, hold_every=11, hold=.075),
}


def read_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        block = sock.recv(size - len(data))
        if not block:
            raise EOFError("TCP stream closed before workload completed")
        data.extend(block)
    return bytes(data)


class Target(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        sock.settimeout(45)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            self.workload(sock)
        except ConnectionResetError:
            # QUIC closes the fixed target when the local client disconnects.
            return

    def workload(self, sock):
        if self.server.socks:
            if read_exact(sock, 3) != b"\x05\x01\x00":
                raise ValueError("expected no-auth lab SOCKS greeting")
            sock.sendall(b"\x05\x00")
            expected = (b"\x05\x01\x00\x03" + bytes([len(TARGET_NAME)]) + TARGET_NAME
                        + self.server.server_address[1].to_bytes(2, "big"))
            if read_exact(sock, len(expected)) != expected:
                raise ValueError("unexpected lab SOCKS destination")
            sock.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
        payload = self.server.payload
        for command in iter(lambda: sock.recv(1), b""):
            if command == b"P":
                sock.sendall(b"P")
            elif command == b"U":
                sock.sendall(hashlib.sha256(read_exact(sock, len(payload))).digest())
            elif command == b"D":
                sock.sendall(payload)
            else:
                raise ValueError("unknown workload command")


def free_port(kind, successor=False):
    for _ in range(20):
        with socket.socket(socket.AF_INET, kind) as sock:
            sock.bind((HOST, 0))
            port = sock.getsockname()[1]
            if not successor:
                return port
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as guard:
                    guard.bind((HOST, port + 1))
                return port
            except (OSError, OverflowError):
                continue
    raise RuntimeError("could not allocate a loopback port with a free UDP successor")


def start(stack, directory, name, args, diagnostic=False):
    log = stack.enter_context((directory / (name + ".log")).open("w", encoding="utf-8"))
    child = subprocess.Popen(
        [str(arg) for arg in args], cwd=directory,
        stdin=subprocess.PIPE if diagnostic else subprocess.DEVNULL,
        stdout=subprocess.PIPE if diagnostic else log,
        stderr=log, text=True, encoding="utf-8", errors="replace",
    )

    def finish():
        if child.poll() is None:
            child.kill()
        child.wait()
        if diagnostic:
            child.stdin.close()
            reader.join()
            child.stdout.close()

    stack.callback(finish)
    if not diagnostic:
        return child, None
    messages = queue.Queue()

    def collect():
        for line in child.stdout:
            if line.startswith("LAB "):
                messages.put(json.loads(line[4:]))
            else:
                log.write(line)
                log.flush()

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()

    def snapshot():
        child.stdin.write("\n")
        child.stdin.flush()
        return messages.get(timeout=5)

    return child, snapshot


def tcp_connection(port, target, socks, children):
    deadline = time.monotonic() + 30
    while True:
        if any(child.poll() is not None for child in children):
            raise RuntimeError("tunnel process exited; see trial logs")
        try:
            sock = socket.create_connection((HOST, port), timeout=.5)
            break
        except (ConnectionRefusedError, TimeoutError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.05)
    try:
        sock.settimeout(35)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if socks:
            sock.sendall(b"\x05\x01\x00")
            if read_exact(sock, 2) != b"\x05\x00":
                raise RuntimeError("SOCKS method negotiation failed")
            sock.sendall(b"\x05\x01\x00\x03" + bytes([len(TARGET_NAME)]) + TARGET_NAME
                         + target.to_bytes(2, "big"))
            header = read_exact(sock, 4)
            if header[:2] != b"\x05\x00":
                raise RuntimeError(f"SOCKS CONNECT failed ({header.hex()})")
            read_exact(sock, {1: 4, 4: 16}[header[3]] + 2)
        return sock
    except Exception:
        sock.close()
        raise


def p95(samples):
    return sorted(samples)[math.ceil(.95 * len(samples)) - 1] if samples else None


def resources(process):
    cpu = process.cpu_times()
    return cpu.user + cpu.system, process.memory_info().rss


def phase(sock, payload, resolver, diagnostics, processes, direction):
    before_diag = diagnostics() if diagnostics else None
    before_counts, before_samples = resolver.snapshot()
    before_cpu = {name: resources(proc)[0] for name, proc in processes.items()}
    peaks = {name: resources(proc)[1] for name, proc in processes.items()}
    stop = threading.Event()

    def sample():
        while not stop.wait(.025):
            for name, proc in processes.items():
                peaks[name] = max(peaks[name], proc.memory_info().rss)

    thread = threading.Thread(target=sample)
    thread.start()
    try:
        started = time.perf_counter()
        if direction == "upload":
            sock.sendall(b"U" + payload)
            if read_exact(sock, 32) != hashlib.sha256(payload).digest():
                raise ValueError("upload SHA-256 mismatch")
        else:
            sock.sendall(b"D")
            if read_exact(sock, len(payload)) != payload:
                raise ValueError("download payload mismatch")
        seconds = time.perf_counter() - started
        counts, samples = resolver.snapshot()
        after_cpu = {name: resources(proc)[0] for name, proc in processes.items()}
    finally:
        stop.set()
        thread.join()
    after_diag = diagnostics() if diagnostics else None
    counters = {key: counts[key] - before_counts[key] for key in (
        "queries", "upstream_replies", "replies_delivered", "rate_drop", "query_drop",
        "reply_drop", "question_repeat", "reordered_replies", "unmatched_reply",
    )}
    return {
        "bytes": len(payload), "seconds": seconds,
        "goodput_mbps": len(payload) * 8 / seconds / 1e6,
        "dns_queries_per_mb": counters["queries"] * 1e6 / len(payload),
        "dns": counters,
        "dns_rtt_p95_ms": p95([sample * 1e3 for sample in samples[len(before_samples):]]),
        "master_client_resend_frames": (
            after_diag["dnsResends"] - before_diag["dnsResends"] if diagnostics else None
        ),
        "process": {name: {
            "cpu_seconds": after_cpu[name] - before_cpu[name],
            "sampled_peak_rss_mib": max(peaks[name], resources(proc)[1]) / 2**20,
        } for name, proc in processes.items()},
    }


def run(args, directory, name, profile, payload, order):
    directory.mkdir()
    result = {}
    with ExitStack() as stack:
        target = stack.enter_context(socketserver.ThreadingTCPServer((HOST, 0), Target))
        target.daemon_threads = True
        target.payload = payload
        target.socks = name == "master"
        threading.Thread(target=target.serve_forever, daemon=True).start()
        stack.callback(target.shutdown)
        target_port = target.server_address[1]
        dns_port = free_port(socket.SOCK_DGRAM)
        client_port = free_port(socket.SOCK_STREAM, successor=name == "master")
        resolver = stack.enter_context(FakeResolver(dns_port, profile))
        resolver_address = f"{HOST}:{resolver.address[1]}"
        if name == "master":
            (directory / "lab.key").write_text("0123456789abcdef" * 2, encoding="ascii")
            (directory / "server.json").write_text(json.dumps({
                "DOMAIN": [DOMAIN], "UDP_HOST": HOST, "UDP_PORT": dns_port,
                "DATA_ENCRYPTION_METHOD": 5, "ENCRYPTION_KEY_FILE": str(directory / "lab.key"),
                "PROTOCOL_TYPE": "SOCKS5", "LOG_LEVEL": "ERROR",
                "USE_EXTERNAL_SOCKS5": True, "FORWARD_IP": HOST, "FORWARD_PORT": target_port,
                "DNS_UPSTREAM_SERVERS": [resolver_address],
                "UDP_READERS": 1, "DNS_REQUEST_WORKERS": 1, "DEFERRED_SESSION_WORKERS": 1,
                "MAX_CONCURRENT_REQUESTS": 512, "DEFERRED_SESSION_QUEUE_LIMIT": 256,
                "DNS_CACHE_MAX_RECORDS": 1000, "SOCKET_BUFFER_SIZE": 524288,
            }), encoding="ascii")
            server_cmd = [args.master_server, "-json", directory / "server.json", "-nowait"]
            client_cmd = [args.master_client, "-port", client_port, "-resolver", resolver_address,
                          "-domain", DOMAIN]
        else:
            server_cmd = [args.slip_server, "--dns-listen-host", HOST, "-l", dns_port,
                          "-a", f"{HOST}:{target_port}", "-d", DOMAIN,
                          "--cert", args.cert, "--key", args.key]
            client_cmd = [args.slip_client, "--tcp-listen-host", HOST, "-l", client_port,
                          "--resolver", resolver_address, "-d", DOMAIN, "--cert", args.cert]
        server, _ = start(stack, directory, "server", server_cmd)
        # Wait for this child to own its chosen UDP socket before sending queries.
        deadline = time.monotonic() + 5
        server_proc = psutil.Process(server.pid)
        while not any(c.type == socket.SOCK_DGRAM and tuple(c.laddr) == (HOST, dns_port)
                      for c in server_proc.net_connections(kind="udp")):
            if server.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("lab server did not bind its loopback UDP port")
            time.sleep(.05)
        client, diagnostics = start(stack, directory, "client", client_cmd, name == "master")
        stack.callback(resolver.quiesce)
        processes = {"client": psutil.Process(client.pid), "server": server_proc}
        with tcp_connection(client_port, target_port, name == "master", [client, server]) as sock:
            app_rtt = []
            for _ in range(12):
                start_time = time.perf_counter()
                sock.sendall(b"P")
                if read_exact(sock, 1) != b"P":
                    raise ValueError("application ping mismatch")
                app_rtt.append((time.perf_counter() - start_time) * 1e3)
            result["app_rtt_p95_ms"] = p95(app_rtt[2:])
            if diagnostics:
                result["master_negotiated"] = {k: v for k, v in diagnostics().items()
                                               if k in ("dnsUploadMTU", "dnsDownloadMTU",
                                                        "dnsWindow", "dnsDuplication")}
            for direction in order:
                result[direction] = phase(sock, payload, resolver, diagnostics, processes, direction)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("master-client", "master-server", "slip-client", "slip-server", "cert", "key"):
        parser.add_argument("--" + option, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--output", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--profile", choices=PROFILES, action="append")
    parser.add_argument("--transport", choices=("master", "slip"), action="append")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--bytes", type=int, default=65536)
    args = parser.parse_args()
    if args.trials < 1 or not 1 <= args.bytes <= 2**20:
        parser.error("positive trial count and 1..1048576 payload bytes required")
    args.output.mkdir()
    payload = hashlib.shake_256(b"VPNN DNS lab v1").digest(args.bytes)
    results = {
        "platform": platform.platform(), "python": platform.python_version(),
        "logical_cpus": psutil.cpu_count(), "psutil": psutil.__version__,
        "binaries_sha256": {name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
                            for name in ("master_client", "master_server", "slip_client", "slip_server")},
        "domain": DOMAIN, "payload_bytes_per_direction": len(payload),
        "profiles": {name: asdict(profile) for name, profile in PROFILES.items()},
        "trials": [],
    }
    for profile_name in args.profile or PROFILES:
        for trial in range(1, args.trials + 1):
            names = args.transport or ["master", "slip"]
            order = ["upload", "download"]
            if trial % 2 == 0:
                names, order = names[::-1], order[::-1]
            for name in names:
                label = f"{profile_name}-{trial}-{name}"
                print(label, flush=True)
                row = {"profile": profile_name, "trial": trial, "transport": name, "order": order}
                try:
                    row.update(run(args, args.output / label, name, PROFILES[profile_name],
                                   payload, order))
                except Exception as error:
                    row["error"] = f"{type(error).__name__}: {error}"
                    traceback.print_exc()
                results["trials"].append(row)
                (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n",
                                                          encoding="utf-8")
    return int(any("error" in trial for trial in results["trials"]))


if __name__ == "__main__":
    raise SystemExit(main())
