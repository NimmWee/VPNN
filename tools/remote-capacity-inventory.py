"""Read-only, whitelisted VPS inventory. Never reads credentials or process argv."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=12)
    return result.stdout.strip() if result.returncode == 0 else None


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def memory():
    return {line.split(':')[0]: int(line.split()[1])
            for line in Path('/proc/meminfo').read_text().splitlines()
            if line.split(':')[0] in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}}


def service(unit):
    result = command('systemctl', 'show', unit, '--property=ActiveState,SubState,MainPID,MemoryCurrent,CPUUsageNSec,CPUQuotaPerSecUSec,NRestarts,ControlGroup')
    fields = dict(line.split('=', 1) for line in (result or '').splitlines() if '=' in line)
    group = fields.pop('ControlGroup', '')
    pids = None
    if group:
        for prefix in ['/sys/fs/cgroup', '/sys/fs/cgroup/systemd', '/sys/fs/cgroup/memory']:
            pids = read(prefix + group + '/cgroup.procs')
            if pids:
                break
    pids = (pids or fields.get('MainPID', '')).split()
    pss = 0
    fd = 0
    observed = 0
    for pid in pids:
        if not pid.isdigit() or int(pid) <= 0:
            continue
        rollup = read('/proc/' + pid + '/smaps_rollup')
        if rollup:
            pss += sum(int(line.split()[1]) for line in rollup.splitlines() if line.startswith('Pss:'))
            observed += 1
        try:
            fd += len(list(Path('/proc/' + pid + '/fd').iterdir()))
        except OSError:
            pass
    fields.pop('MainPID', None)
    fields.update(pssKiB=pss if observed else None, fdCount=fd if observed else None, observedProcesses=observed)
    return fields


def snapshot():
    names = ['vpnn-control', 'vpnn-node-sync', 'vpnn-dns', 'vpnn-vk', 'vpnn-egress', 'x-ui', 'vps-vk', 'nginx', 'fail2ban']
    units = command('systemctl', 'list-units', '--all', '--plain', '--no-legend', 'vpnn-dns@*.service') or ''
    backends = [line.split()[0] for line in units.splitlines() if line.split()]
    cpu = {}
    for line in Path('/proc/cpuinfo').read_text().splitlines():
        if line.startswith(('model name', 'vendor_id')):
            key, value = line.split(':', 1)
            cpu[key.strip()] = value.strip()
    disk = shutil.disk_usage('/')
    fs = os.statvfs('/')
    binary = Path('/opt/vpnn-control/vpnn-control')
    status = json.loads(read('/run/vpnn-node/status.json') or '{}')
    return {'schema': 1, 'sourceKind': 'live-read-only', 'observedAtEpoch': int(time.time()),
            'memoryKiB': memory(), 'cpu': dict(cpu, logicalCPUs=os.cpu_count()),
            'cgroup': {'cpuMax': read('/sys/fs/cgroup/cpu.max'), 'memoryMax': read('/sys/fs/cgroup/memory.max'),
                       'cpuQuotaV1': read('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'),
                       'cpuPeriodV1': read('/sys/fs/cgroup/cpu/cpu.cfs_period_us'),
                       'memoryLimitV1': read('/sys/fs/cgroup/memory/memory.limit_in_bytes')},
            'diskBytes': {'total': disk.total, 'used': disk.used, 'free': disk.free},
            'inodes': {'total': fs.f_files, 'free': fs.f_favail},
            'loadAverage': list(os.getloadavg()), 'networkCounters': read('/proc/net/dev'),
            'conntrack': {'count': read('/proc/sys/net/netfilter/nf_conntrack_count'), 'max': read('/proc/sys/net/netfilter/nf_conntrack_max')},
            'services': {name: service(name) for name in names},
            'dnsBackends': [service(name) for name in backends],
            'node': {key: status.get(key) for key in ['healthy', 'appliedVersion', 'dnsDevices', 'vkDevices']},
            'controlBinarySha256': hashlib.sha256(binary.read_bytes()).hexdigest() if binary.exists() else None,
            'networkCapacity': None}


if __name__ == '__main__':
    print(json.dumps(snapshot()))
