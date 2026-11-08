#!/usr/bin/env python3
"""Request-only CPU reservations, calculated per kind node.

This is a transparent lab capacity model, NOT a production quota mechanism.
Memory/pod slots are still separate constraints. Assumes one node per cluster.
"""
import json
import os
import subprocess
import sys
import time

TARGETS = {'dc-primary': 4, 'dc-secondary': 6, 'cloud-azure': 12}
APP_REQUEST_M = 250
EXTRA_BUFFER_M = 150  # other lab workloads, scheduling estimates, low overhead
APP_MEMORY_BYTES = 128 * 1024 * 1024
MEMORY_BUFFER_BYTES = 512 * 1024 * 1024
RESERVATION_MEMORY_BYTES = 32 * 1024 * 1024
POD_BUFFER = 5
KARMADA_CONFIG = os.environ.get('KARMADA_CONFIG', os.path.abspath('.runtime/karmada/karmada-apiserver.config'))


def kubectl(cluster, *args, stdin=None):
    proc = subprocess.run(['kubectl', '--context', 'kind-' + cluster, *args],
                          input=stdin, text=True, check=True, capture_output=True)
    return proc.stdout


def cpu_m(q):
    if not q: return 0
    q=str(q)
    if q.endswith('m'):return int(float(q[:-1]))
    if q.endswith('u'):return round(float(q[:-1])/1000)
    if q.endswith('n'):return round(float(q[:-1])/1000000)
    return round(float(q)*1000)


def pod_cpu_requests(pod):
    spec=pod['spec']
    app=sum(cpu_m(c.get('resources',{}).get('requests',{}).get('cpu')) for c in spec.get('containers',[]))
    init=max((cpu_m(c.get('resources',{}).get('requests',{}).get('cpu')) for c in spec.get('initContainers',[])), default=0)
    overhead=cpu_m(spec.get('overhead',{}).get('cpu'))
    return max(app,init)+overhead


def quantity_bytes(value):
    value = str(value or '0')
    units = {'Ki': 1024, 'Mi': 1024**2, 'Gi': 1024**3,
             'K': 1000, 'M': 1000**2, 'G': 1000**3}
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            return int(float(value[:-len(suffix)]) * multiplier)
    return int(value)


def pod_memory_requests(pod):
    spec = pod['spec']
    request = lambda c: quantity_bytes(c.get('resources', {}).get('requests', {}).get('memory'))
    app = sum(request(c) for c in spec.get('containers', []))
    init = max((request(c) for c in spec.get('initContainers', [])), default=0)
    return max(app, init) + quantity_bytes(spec.get('overhead', {}).get('memory'))


def plan(cluster, target):
    nodes = json.loads(kubectl(cluster, 'get', 'nodes', '-o', 'json'))['items']
    if len(nodes) != 1:
        raise RuntimeError(f'{cluster}: calibrator requires one node, found {len(nodes)}')
    node = nodes[0]
    node_name = node['metadata']['name']
    all_active = [p for p in json.loads(kubectl(cluster, 'get', 'pods', '-A', '-o', 'json'))['items']
                  if p.get('status', {}).get('phase') not in ('Succeeded', 'Failed')]
    existing = [p for p in all_active if p['metadata']['namespace'] == 'karmada-lab-system'
                and p['metadata']['name'] == 'capacity-reservation']
    if existing and existing[0]['metadata'].get('labels', {}).get('app') != 'capacity-reservation':
        raise RuntimeError(f'{cluster}: existing reservation name is not owned by this lab')
    if any(p['metadata']['namespace'] == 'demo' and p['metadata'].get('labels', {}).get('app') == 'placement-demo'
           for p in all_active):
        raise RuntimeError(f'{cluster}: remove demo workload before recalibrating')
    if any(p['metadata']['namespace'] == 'demo' and p['metadata'].get('labels', {}).get('app') == 'cloud-burst-loadgen'
           for p in all_active):
        raise RuntimeError(f'{cluster}: stop load generator before recalibrating')
    active = [p for p in all_active if p.get('spec', {}).get('nodeName') == node_name]
    active = [p for p in active if p not in existing]
    alloc = node['status']['allocatable']
    cpu = cpu_m(alloc['cpu'])
    requested = sum(pod_cpu_requests(p) for p in active)
    memory = sum(pod_memory_requests(p) for p in active)
    reservation = cpu - requested - target * APP_REQUEST_M - EXTRA_BUFFER_M
    if reservation < 100:
        raise RuntimeError(f'{cluster}: insufficient CPU for target {target}: alloc={cpu}m existing={requested}m')
    if quantity_bytes(alloc['memory']) - memory < target * APP_MEMORY_BYTES + MEMORY_BUFFER_BYTES + RESERVATION_MEMORY_BYTES:
        raise RuntimeError(f'{cluster}: insufficient requested-memory headroom for {target} pods and buffer')
    if int(alloc['pods']) - len(active) < target + POD_BUFFER + 1:
        raise RuntimeError(f'{cluster}: insufficient pod slots for {target} pods and buffer')
    return node_name, cpu, requested, reservation


def main():
    with open('/proc/meminfo', encoding='utf-8') as info:
        fields = {line.split(':', 1)[0]: line.split(':', 1)[1].strip().split()[0]
                  for line in info if ':' in line}
    available = int(fields['MemAvailable']) * 1024
    required = sum(TARGETS.values()) * APP_MEMORY_BYTES + MEMORY_BUFFER_BYTES + len(TARGETS) * RESERVATION_MEMORY_BYTES
    if available < required:
        message = f'WSL available memory {available // 1024**2}Mi below conservative {required // 1024**2}Mi requirement'
        if os.environ.get('LAB_ALLOW_LOW_MEMORY') != '1':
            raise RuntimeError(message + '; set LAB_ALLOW_LOW_MEMORY=1 only after reviewing the shared host')
        print('WARNING:', message, file=sys.stderr)
    proc = subprocess.run(['kubectl', '--kubeconfig', KARMADA_CONFIG, '-n', 'demo', 'get', 'deployment',
                           'placement-demo', '--ignore-not-found', '-o', 'name'], check=True, capture_output=True, text=True)
    if proc.stdout.strip():
        raise RuntimeError('Remove the Karmada demo Deployment before recalibrating')
    hpa = subprocess.run(['kubectl', '--kubeconfig', KARMADA_CONFIG, '-n', 'demo', 'get', 'federatedhpa',
                          'placement-demo', '--ignore-not-found', '-o', 'name'], check=True, capture_output=True, text=True)
    if hpa.stdout.strip():
        raise RuntimeError('Remove the FederatedHPA before recalibrating')
    plans = {cluster: plan(cluster, target) for cluster, target in TARGETS.items()}
    for cluster,target in TARGETS.items():
        # apply generated namespace; don't assume it exists
        kubectl(cluster,'apply','-f','-', stdin='apiVersion: v1\nkind: Namespace\nmetadata:\n  name: karmada-lab-system\n')
        kubectl(cluster,'-n','karmada-lab-system','delete','pod','capacity-reservation','--ignore-not-found','--wait=true')
        node_name, alloc, requested, reservation = plans[cluster]
        pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':'capacity-reservation',
             'namespace':'karmada-lab-system','labels':{'app':'capacity-reservation'}},
             'spec':{'nodeSelector':{'kubernetes.io/hostname':node_name},
             'containers':[{'name':'pause','image':'registry.k8s.io/pause:3.10.2',
             'resources':{'requests':{'cpu':f'{reservation}m','memory':'32Mi'}}}]}}
        print(f'{cluster}: allocatable={alloc}m already_requested={requested}m '
              f'reserve={reservation}m target_slots={target} (+{EXTRA_BUFFER_M}m buffer)',flush=True)
        kubectl(cluster,'apply','-f','-',stdin=json.dumps(pod))
        kubectl(cluster,'-n','karmada-lab-system','wait','pod/capacity-reservation',
                '--for=condition=Ready','--timeout=120s')
        expected = requested + reservation
        for attempt in range(60):
            info = json.loads(subprocess.run(['kubectl', '--kubeconfig', KARMADA_CONFIG, 'get', 'cluster', cluster,
                                              '-o', 'json'], check=True, capture_output=True, text=True).stdout)
            observed = cpu_m(info.get('status', {}).get('resourceSummary', {}).get('allocated', {}).get('cpu'))
            if abs(observed - expected) <= 10:
                print(f'{cluster}: Karmada allocated CPU converged at {observed}m', flush=True)
                break
            time.sleep(2)
        else:
            raise RuntimeError(f'{cluster}: Karmada resourceSummary did not converge; expected {expected}m, got {observed}m')
    print('Reservation Pods Ready. Verify Karmada Cluster resourceSummary converges before scale test.')

if __name__=='__main__':
    try:main()
    except (subprocess.CalledProcessError,RuntimeError) as e:
        print(f'Calibration failed: {e}',file=sys.stderr)
        if isinstance(e, subprocess.CalledProcessError) and e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(1)
