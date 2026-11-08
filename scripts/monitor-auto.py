#!/usr/bin/env python3
"""Record and verify a real FederatedHPA burst or subsequent scale-in."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

phase = sys.argv[1]
if phase not in ('burst', 'cooldown'):
    raise SystemExit('Expected burst or cooldown')
clusters = ('dc-primary', 'dc-secondary', 'cloud-azure')
kcfg = os.environ['KARMADA_CONFIG']
log = Path(os.environ['AUTO_SNAPSHOT_LOG'])
timeout = int(os.getenv('AUTO_PHASE_TIMEOUT', '600'))
max_cpu = float(os.getenv('AUTO_CPU_MAX_PERCENT', '90'))
min_memory = int(os.getenv('AUTO_MIN_AVAILABLE_MIB', '1536'))


def command(*args):
    p = subprocess.run(['kubectl', *args], text=True, capture_output=True, check=True)
    return json.loads(p.stdout) if p.stdout.strip() else None


def host_cpu():
    with open('/proc/stat', encoding='utf-8') as f:
        values = [int(x) for x in f.readline().split()[1:]]
    return sum(values), values[3] + values[4]


def available_mib():
    with open('/proc/meminfo', encoding='utf-8') as f:
        return next(int(line.split()[1]) // 1024 for line in f if line.startswith('MemAvailable:'))


def snapshot():
    hpa = command('--kubeconfig', kcfg, '-n', 'demo', 'get', 'fhpa', 'placement-demo', '-o', 'json')
    deployment = command('--kubeconfig', kcfg, '-n', 'demo', 'get', 'deployment', 'placement-demo', '-o', 'json')
    bindings = command('--kubeconfig', kcfg, '-n', 'demo', 'get', 'resourcebindings', '-o', 'json')['items']
    assigned = {c: 0 for c in clusters}
    for b in bindings:
        ref = b.get('spec', {}).get('resource', {})
        if ref.get('kind') == 'Deployment' and ref.get('name') == 'placement-demo':
            for target in b['spec'].get('clusters', []):
                if target['name'] in assigned:
                    assigned[target['name']] += int(target.get('replicas') or 0)
    members = {}
    for c in clusters:
        item = command('--context', 'kind-' + c, '-n', 'demo', 'get', 'deployment', 'placement-demo',
                       '--ignore-not-found', '-o', 'json')
        members[c] = {'desired': int((item or {}).get('spec', {}).get('replicas') or 0),
                      'ready': int((item or {}).get('status', {}).get('availableReplicas') or 0)}
    status = hpa.get('status') or {}
    metrics = status.get('currentMetrics') or []
    cpu = next((m.get('resource', {}).get('current', {}).get('averageUtilization') for m in metrics
                if m.get('type') == 'Resource' and m.get('resource', {}).get('name') == 'cpu'), None)
    raw = command('--kubeconfig', kcfg, 'get', '--raw', '/apis/metrics.k8s.io/v1beta1/namespaces/demo/pods')
    metric_clusters = sorted({x.get('metadata', {}).get('annotations', {}).get('resource.karmada.io/query-from-cluster')
                              for x in raw.get('items', []) if x.get('metadata', {}).get('labels', {}).get('app') == 'placement-demo'} - {None})
    return {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phase': phase,
            'hpa_current': status.get('currentReplicas'), 'hpa_desired': status.get('desiredReplicas'),
            'hpa_cpu_percent': cpu, 'deployment_desired': deployment.get('spec', {}).get('replicas'),
            'assigned': assigned, 'members': members, 'pod_metric_clusters': metric_clusters,
            'host_available_mib': available_mib()}


start = time.monotonic()
last_total, last_idle = host_cpu()
high_cpu_count = 0
ramped = False
while time.monotonic() - start < timeout:
    row = snapshot()
    total, idle = host_cpu()
    delta = total - last_total
    usage = 100 * (1 - (idle - last_idle) / delta) if delta else 0
    last_total, last_idle = total, idle
    row['wsl_cpu_percent'] = round(usage, 1)
    with log.open('a', encoding='utf-8') as out:
        out.write(json.dumps(row, sort_keys=True) + '\n')
    print(json.dumps(row, sort_keys=True), flush=True)
    if row['host_available_mib'] < min_memory:
        raise SystemExit(f'WSL available memory below safety threshold: {row["host_available_mib"]}Mi')
    high_cpu_count = high_cpu_count + 1 if usage > max_cpu else 0
    if high_cpu_count >= 3:
        raise SystemExit(f'WSL CPU exceeded {max_cpu}% for three observations')
    ready = sum(x['ready'] for x in row['members'].values())
    if phase == 'burst' and row['hpa_cpu_percent'] is not None and row['hpa_cpu_percent'] > 50 \
            and (row['hpa_desired'] or 0) > 10 and row['assigned']['cloud-azure'] > 0 \
            and row['members']['cloud-azure']['ready'] > 0 and 'cloud-azure' in row['pod_metric_clusters']:
        print('FederatedHPA CPU-driven cloud overflow observed', flush=True)
        sys.exit(0)
    if phase == 'cooldown' and row['hpa_desired'] == 4 and row['deployment_desired'] == 4 \
            and sum(row['assigned'].values()) == 4 and ready == 4:
        print('FederatedHPA returned to four Ready replicas', flush=True)
        sys.exit(0)
    if phase == 'burst' and not ramped and time.monotonic() - start >= 90:
        print('Increasing local generators to four bounded workers each', flush=True)
        for c in clusters:
            subprocess.run(['kubectl', '--context', 'kind-' + c, '-n', 'demo', 'set', 'env',
                            'deployment/cloud-burst-loadgen', 'LOAD_WORKERS=4'], check=True)
        marker_env = os.environ.copy()
        marker_env.update({'SCENARIO': 'auto', 'MARKER_REQUIRED': '1'})
        subprocess.run(['python3', 'scripts/emit-marker.py', 'Automatic burst: generators increased to four workers'],
                       env=marker_env, check=True)
        ramped = True
    time.sleep(10)
raise SystemExit(f'{phase} did not meet its acceptance checks within {timeout}s; see {log}')
