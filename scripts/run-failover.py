#!/usr/bin/env python3
"""Run the lab-only cluster failover experiment with guarded restoration."""
import datetime
from decimal import Decimal, InvalidOperation
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
KCFG = os.environ.get('KARMADA_CONFIG', str(ROOT / '.runtime/karmada/karmada-apiserver.config'))
K = ['kubectl', '--kubeconfig', KCFG, '--request-timeout=8s']
HOST = ['kubectl', '--context', 'kind-karmada-mgmt', '--request-timeout=8s', '-n', 'karmada-system']
MEMBERS = ('dc-primary', 'dc-secondary', 'cloud-azure')
TARGET = 'dc-primary-control-plane'
TAINT = 'lab.karmada.io/failover'
POLICY = 'lab-failover-dc-primary'
TIMEOUT = int(os.environ.get('FAILOVER_PHASE_TIMEOUT', '480'))
INTERVAL = int(os.environ.get('FAILOVER_POLL_SECONDS', '5'))
run_dir = ROOT / '.runtime/failover' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
os.chmod(run_dir, 0o700)
log_path = run_dir / 'snapshots.jsonl'
state_path = run_dir / 'restore.json'
state = {'paused_by_run': False, 'changed': {}, 'strategies': {}, 'policy_created': False, 'test_policy_changed': False,
         'scaled_by_run': False, 'container_id': None, 'original_replicas': None}


def run(args, *, input=None, timeout=40):
    p = subprocess.run(args, input=input, text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args[0]} command failed ({p.returncode}): {p.stderr.strip() or p.stdout.strip()}')
    return p.stdout


def obj(args):
    value = run(args + ['-o', 'json'])
    return json.loads(value) if value.strip() else None


def save():
    temp = state_path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2) + '\n')
    os.chmod(temp, 0o600)
    temp.replace(state_path)


def event(stage, **details):
    row = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'stage': stage, **details}
    with log_path.open('a') as out:
        os.chmod(log_path, 0o600)
        out.write(json.dumps(row, sort_keys=True) + '\n')
    print(json.dumps(row, sort_keys=True), flush=True)


def marker(message):
    env = dict(os.environ, SCENARIO='failover', MARKER_REQUIRED='1')
    p = subprocess.run(['python3', 'scripts/emit-marker.py', message], env=env, text=True, capture_output=True, timeout=10)
    if p.returncode:
        raise RuntimeError('Cannot write required Loki marker: ' + p.stderr.strip())


def cluster(name):
    return obj(K + ['get', 'cluster', name])


def condition(item):
    return next((c.get('status') for c in item.get('status', {}).get('conditions', []) if c.get('type') == 'Ready'), None)


def docker_state():
    data = json.loads(run(['docker', 'inspect', TARGET], timeout=12))[0]
    return data['Id'], data['State']['Running'], data['State']['Paused']


def owned():
    current, running, paused = docker_state()
    recorded = (ROOT / '.runtime/kind-owned/dc-primary.id').read_text().strip()
    if current != recorded or (state['container_id'] and current != state['container_id']):
        raise RuntimeError('dc-primary ownership or container identity changed; refusing container operation')
    return current, running, paused


def dep(name):
    return obj(HOST + ['get', 'deployment', name])


def command_of(name):
    data = dep(name)
    containers = data['spec']['template']['spec']['containers']
    if len(containers) != 1 or containers[0]['name'] != name or 'command' not in containers[0] or containers[0].get('args'):
        raise RuntimeError(f'Unexpected container layout for {name}; refusing patch')
    return containers[0]['command']


def change_command(name, before, after):
    path = '/spec/template/spec/containers/0/command'
    patch = [{'op': 'test', 'path': path, 'value': before}, {'op': 'replace', 'path': path, 'value': after}]
    run(HOST + ['patch', 'deployment', name, '--type=json', '-p', json.dumps(patch)])
    run(['kubectl', '--context', 'kind-karmada-mgmt', '-n', 'karmada-system',
         'rollout', 'status', 'deployment/' + name, '--timeout=180s'], timeout=195)


def change_strategy(name, before, after):
    path = '/spec/strategy'
    patch = [{'op': 'test', 'path': path, 'value': before}, {'op': 'replace', 'path': path, 'value': after}]
    run(HOST + ['patch', 'deployment', name, '--type=json', '-p', json.dumps(patch)])


def flags(command, new_flags, gate=None):
    result = command[:]
    for key, value in new_flags.items():
        matches = [a for a in result if a.startswith('--' + key + '=') or a == '--' + key]
        if len(matches) > 1 or any(a == '--' + key for a in matches):
            raise RuntimeError(f'Unexpected duplicate or split flag --{key}')
        if matches:
            result[result.index(matches[0])] = '--' + key + '=' + value
        else:
            result.append('--' + key + '=' + value)
    if gate:
        matches = [a for a in result if a.startswith('--feature-gates=')]
        if len(matches) > 1 or '--feature-gates' in result:
            raise RuntimeError('Unexpected feature-gates arguments')
        old = matches[0] if matches else None
        entries = old.split('=', 1)[1].split(',') if old else []
        entries = [a for a in entries if not a.startswith(gate + '=')]
        value = '--feature-gates=' + ','.join(entries + [gate + '=true'])
        if old: result[result.index(old)] = value
        else: result.append(value)
    return result


def state_snapshot(stage, source=True):
    c = cluster('dc-primary')
    d = obj(K + ['-n', 'demo', 'get', 'deployment', 'placement-demo'])
    binding = obj(K + ['-n', 'demo', 'get', 'resourcebinding', 'placement-demo-deployment'])
    assigned = {name: 0 for name in MEMBERS}
    for t in binding['spec'].get('clusters', []):
        if t['name'] in assigned: assigned[t['name']] = t.get('replicas', 0)
    members = {}
    for n in MEMBERS:
        if n == 'dc-primary' and not source:
            members[n] = None
            continue
        data = obj(['kubectl', '--context', 'kind-' + n, '--request-timeout=8s', '-n', 'demo',
                    'get', 'deployment', 'placement-demo', '--ignore-not-found'])
        members[n] = {'desired': (data or {}).get('spec', {}).get('replicas', 0),
                      'available': (data or {}).get('status', {}).get('availableReplicas', 0)}
    row = {'ready': condition(c), 'taints': c['spec'].get('taints', []), 'desired': d['spec'].get('replicas'),
           'assigned': assigned, 'members': members, 'eviction_tasks': binding['spec'].get('gracefulEvictionTasks', [])}
    event(stage, **row)
    return row


def wait_for(label, predicate, *, source=True, timeout=None):
    end = time.monotonic() + (timeout or TIMEOUT)
    while time.monotonic() < end:
        row = state_snapshot(label, source=source)
        if predicate(row): return row
        time.sleep(INTERVAL)
    raise RuntimeError(f'{label}: timed out after {timeout or TIMEOUT}s')


def pause():
    _, running, paused = owned()
    if not running or paused: raise RuntimeError('Target is not running and unpaused; refusing pause')
    run(['docker', 'pause', TARGET], timeout=20)
    state['paused_by_run'] = True
    save()
    event('pause', container_id=state['container_id'])


def unpause():
    if not state['paused_by_run']: return
    _, running, paused = owned()
    if not running: raise RuntimeError('Run-owned target is not running; manual recovery needed')
    if paused: run(['docker', 'unpause', TARGET], timeout=20)
    state['paused_by_run'] = False
    save()
    event('unpause')


def healthy(row, count):
    return (row['ready'] == 'True' and row['desired'] == count and sum(row['assigned'].values()) == count
            and not row['eviction_tasks'] and not any(t.get('key') == TAINT for t in row['taints'])
            and all(row['members'][n] is not None and row['members'][n]['desired'] == row['assigned'][n]
                    and row['members'][n]['available'] == row['assigned'][n] for n in MEMBERS))


def cpu_millicores(value):
    text = str(value)
    units = {'m': Decimal('1'), 'u': Decimal('0.001'), 'n': Decimal('0.000001')}
    try:
        return Decimal(text[:-1]) * units[text[-1]] if text and text[-1] in units else Decimal(text) * 1000
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f'Invalid CPU quantity in Karmada summary: {value}') from exc


def secondary_capacity(assigned):
    """Wait until Karmada's requested CPU agrees with the live member node."""
    spec = importlib.util.spec_from_file_location('lab_capacity', ROOT / 'scripts/calibrate-capacity.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = ['kubectl', '--context', 'kind-dc-secondary', '--request-timeout=8s']
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        nodes = obj(base + ['get', 'nodes'])['items']
        if len(nodes) != 1:
            raise RuntimeError('Secondary capacity check requires exactly one node')
        node = nodes[0]
        pods = obj(base + ['get', 'pods', '-A'])['items']
        live = [p for p in pods if p.get('spec', {}).get('nodeName') == node['metadata']['name']
                and p.get('status', {}).get('phase') not in ('Succeeded', 'Failed')]
        requested = sum(module.pod_cpu_requests(p) for p in live)
        local_alloc = cpu_millicores(node['status']['allocatable']['cpu'])
        summary = cluster('dc-secondary').get('status', {}).get('resourceSummary', {})
        alloc = summary.get('allocatable', {}).get('cpu')
        used = summary.get('allocated', {}).get('cpu')
        if alloc is not None and used is not None and abs(cpu_millicores(used) - requested) <= 10 \
                and abs(cpu_millicores(alloc) - local_alloc) <= 10:
            extra = max(0, int((local_alloc - requested) // 250))
            return {'secondary_assigned': assigned, 'secondary_requested_m': requested,
                    'secondary_additional_cpu_slots': extra, 'secondary_total_cpu_slots': assigned + extra}
        time.sleep(5)
    raise RuntimeError('Secondary Karmada CPU summary did not converge with live member requests within 120s')


def hold_failover(predicate, seconds):
    if seconds < 0:
        raise RuntimeError('FAILOVER_HOLD_SECONDS must be non-negative')
    marker(f'Failover test: cloud observation begins for {seconds}s')
    event('failover-hold-start', seconds=seconds)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(min(INTERVAL, max(0, deadline - time.monotonic())))
        _, running, paused = owned()
        if not running or not paused:
            raise RuntimeError('Target did not remain paused during the cloud observation window')
        row = state_snapshot('failover-hold', source=False)
        if not predicate(row):
            raise RuntimeError('Eight healthy-member replicas or cloud availability lost during observation window')
    event('failover-hold-complete', seconds=seconds)
    marker('Failover test: cloud observation complete')


def patch_toleration(before, after, action):
    path = '/spec/placement/clusterTolerations'
    p = obj(K + ['-n', 'demo', 'get', 'propagationpolicy', 'placement-demo-burst'])
    actual = p['spec']['placement'].get('clusterTolerations')
    if actual != before: raise RuntimeError('Demo policy tolerations changed externally; refusing overwrite')
    operations = [{'op': 'test', 'path': '/metadata/resourceVersion', 'value': p['metadata']['resourceVersion']}]
    if action == 'remove': operations.append({'op': 'remove', 'path': path})
    else: operations.append({'op': 'replace' if before is not None else 'add', 'path': path, 'value': after})
    run(K + ['-n', 'demo', 'patch', 'propagationpolicy', 'placement-demo-burst', '--type=json', '-p', json.dumps(operations)])


def cleanup():
    failures = []
    def attempt(label, fn):
        try: fn()
        except Exception as e:
            failures.append(label + ': ' + str(e)); print('CLEANUP ERROR:', failures[-1], file=sys.stderr, flush=True)
    attempt('unpause', unpause)
    if state['paused_by_run']:
        return failures + ['Target still paused; remaining cleanup not attempted']
    if state['policy_created']:
        def remove_policy():
            end = time.monotonic() + 180
            while time.monotonic() < end:
                c = cluster('dc-primary')
                taints = [t for t in c['spec'].get('taints', []) if t.get('key') == TAINT and t.get('effect') == 'NoExecute']
                if condition(c) == 'True' and not taints: break
                time.sleep(3)
            else: raise RuntimeError('Ready/test taint did not recover; leave policy in place for inspection')
            data = obj(K + ['get', 'clustertaintpolicy', POLICY, '--ignore-not-found'])
            if data and data['metadata'].get('uid') != state['policy_uid']:
                raise RuntimeError('Test policy identity changed; refusing delete')
            if data: run(K + ['delete', 'clustertaintpolicy', POLICY, '--wait=true'])
            state['policy_created'] = False; save()
        attempt('test policy', remove_policy)
    if state['test_policy_changed']:
        def restore_policy():
            patch_toleration(state['test_tolerations'], state['original_tolerations'],
                             'remove' if state['original_tolerations'] is None else 'replace')
            state['test_policy_changed'] = False; save()
        attempt('demo tolerations', restore_policy)
    for name in ('karmada-controller-manager', 'karmada-webhook'):
        if name in state['changed']:
            def restore(name=name):
                before, after = state['changed'][name]
                current = command_of(name)
                if current == after: change_command(name, after, before)
                elif current != before: raise RuntimeError('Command changed externally; refusing overwrite')
                del state['changed'][name]; save()
            attempt('restore ' + name, restore)
        if name in state['strategies'] and name not in state['changed']:
            def restore_strategy(name=name):
                original = state['strategies'][name]
                current = dep(name)['spec']['strategy']
                if current == {'type': 'Recreate'}: change_strategy(name, current, original)
                elif current != original: raise RuntimeError('Deployment strategy changed externally; refusing overwrite')
                del state['strategies'][name]; save()
            attempt('restore strategy ' + name, restore_strategy)
    if state['scaled_by_run']:
        def restore_replicas():
            d = obj(K + ['-n', 'demo', 'get', 'deployment', 'placement-demo'])
            actual = d['spec'].get('replicas')
            hpa = obj(K + ['-n', 'demo', 'get', 'federatedhpa', 'placement-demo', '--ignore-not-found'])
            if hpa or actual != 8: raise RuntimeError(f'Desired replicas changed to {actual} or HPA appeared; refusing overwrite')
            run(K + ['-n', 'demo', 'scale', 'deployment/placement-demo', f"--replicas={state['original_replicas']}"])
            wait_for('restore-baseline', lambda row: healthy(row, state['original_replicas']), timeout=240)
            state['scaled_by_run'] = False; save()
        attempt('restore replica count', restore_replicas)
    return failures


def interrupt(signum, frame):
    raise KeyboardInterrupt(f'signal {signum}')


def main():
    signal.signal(signal.SIGTERM, interrupt)
    try:
        hold_seconds = int(os.environ.get('FAILOVER_HOLD_SECONDS', '60'))
    except ValueError as exc:
        raise RuntimeError('FAILOVER_HOLD_SECONDS must be a non-negative integer') from exc
    if hold_seconds < 0 or TIMEOUT <= 0 or INTERVAL <= 0:
        raise RuntimeError('Hold must be non-negative; phase timeout and polling interval must be positive')
    with open('/proc/meminfo', encoding='utf-8') as f:
        available = next(int(line.split()[1]) // 1024 for line in f if line.startswith('MemAvailable:'))
    if available < 1536:
        raise RuntimeError(f'WSL available memory below 1536 MiB: {available} MiB')
    for n in MEMBERS:
        c = cluster(n)
        if condition(c) != 'True': raise RuntimeError(f'{n} is not Ready')
        if any(t.get('effect') == 'NoExecute' for t in c['spec'].get('taints', [])):
            raise RuntimeError(f'{n} has a NoExecute taint; refusing global eviction enablement')
    if obj(K + ['get', 'clustertaintpolicies'])['items']:
        raise RuntimeError('Existing ClusterTaintPolicy found; refusing global eviction enablement')
    for kind in ('resourcebindings', 'clusterresourcebindings'):
        args = K + ['get', kind] + (['-A'] if kind == 'resourcebindings' else [])
        for item in obj(args)['items']:
            if any(c.get('name') == 'dc-primary' for c in item.get('spec', {}).get('clusters', [])):
                if (item['metadata'].get('namespace'), item['metadata']['name']) not in {
                    ('demo', 'placement-demo-deployment'), ('demo', 'placement-demo-service')}:
                    raise RuntimeError(f'Foreign binding targets dc-primary: {item["metadata"]["name"]}')
    if obj(K + ['-n', 'demo', 'get', 'federatedhpa', 'placement-demo', '--ignore-not-found']):
        raise RuntimeError('FederatedHPA active; refusing test')
    for n in MEMBERS:
        load = obj(['kubectl', '--context', 'kind-' + n, '--request-timeout=8s', '-n', 'demo',
                    'get', 'deployment', 'cloud-burst-loadgen', '--ignore-not-found'])
        if load and load['spec'].get('replicas', 1) != 0: raise RuntimeError(f'Load generator active in {n}')
    ident, running, paused = owned()
    if not running or paused: raise RuntimeError('Target was already paused or not running; refusing test')
    state['container_id'] = ident
    original = state_snapshot('preflight')
    if not healthy(original, original['desired']): raise RuntimeError('Initial demo state has not converged')
    state['original_replicas'] = original['desired']
    d = obj(K + ['-n', 'demo', 'get', 'propagationpolicy', 'placement-demo-burst'])
    old = d['spec']['placement'].get('clusterTolerations')
    if old and any(x.get('key') in ('', TAINT) for x in old): raise RuntimeError('Existing toleration conflicts with test taint')
    state['original_tolerations'] = old
    state['test_tolerations'] = (old or []) + [{'key': TAINT, 'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 120}]
    for n in ('karmada-controller-manager', 'karmada-webhook'):
        cmd = command_of(n)
        if n == 'karmada-controller-manager' and any('Failover=true' in a or a in
                ('--enable-no-execute-taint-eviction', '--enable-no-execute-taint-eviction=true') for a in cmd):
            raise RuntimeError('Failover already enabled; control experiment requires disabled baseline')
        state.setdefault('original_commands', {})[n] = cmd
    save()
    patch_toleration(old, state['test_tolerations'], 'replace')
    state['test_policy_changed'] = True; save()
    run(K + ['-n', 'demo', 'scale', 'deployment/placement-demo', '--replicas=8'])
    state['scaled_by_run'] = True; save()
    base = wait_for('baseline', lambda row: healthy(row, 8) and row['assigned']['dc-primary'] > 0, timeout=240)
    estimate = secondary_capacity(base['assigned']['dc-secondary'])
    event('capacity-estimate', **estimate)
    if estimate['secondary_total_cpu_slots'] >= 8:
        raise RuntimeError('Secondary may fit all eight by CPU estimate; cloud overflow cannot be demonstrated')
    applied = obj(K + ['-n', 'demo', 'get', 'resourcebinding', 'placement-demo-deployment'])['metadata'].get('annotations', {}).get('policy.karmada.io/applied-placement', '{}')
    if not any(x.get('key') == TAINT and x.get('tolerationSeconds') == 120 for x in json.loads(applied).get('clusterTolerations', [])):
        raise RuntimeError('120-second toleration not reflected in binding applied placement')
    marker('Failover control: pause dc-primary with failover disabled')
    pause()
    failed = wait_for('control-detection', lambda row: row['ready'] in ('False', 'Unknown'), source=False, timeout=180)
    if failed['assigned'] != base['assigned']: raise RuntimeError('Control assignment changed unexpectedly')
    marker('Failover control: cluster unavailable, restoring')
    unpause()
    wait_for('control-recovery', lambda row: healthy(row, 8), timeout=240)
    for name, changes, gate in [('karmada-webhook', {'allow-no-execute-taint-policy':'true'}, None),
                                ('karmada-controller-manager', {'enable-no-execute-taint-eviction':'true'}, 'Failover')]:
        before = state['original_commands'][name]; after = flags(before, changes, gate)
        # Required pod anti-affinity prevents RollingUpdate on the one-node kind cluster.
        original_strategy = dep(name)['spec']['strategy']
        state['strategies'][name] = original_strategy; save()
        if original_strategy != {'type': 'Recreate'}:
            change_strategy(name, original_strategy, {'type': 'Recreate'})
        # Record intended rollback before patching, including interrupted rollouts.
        state['changed'][name] = [before, after]; save()
        change_command(name, before, after)
    policy = {'apiVersion':'policy.karmada.io/v1alpha1','kind':'ClusterTaintPolicy',
              'metadata':{'name':POLICY,'labels':{'app.kubernetes.io/managed-by':'karmada-lab-failover'}},
              'spec':{'targetClusters':{'clusterNames':['dc-primary']},
                      'addOnConditions':[{'conditionType':'Ready','operator':'NotIn','statusValues':['True']}],
                      'removeOnConditions':[{'conditionType':'Ready','operator':'In','statusValues':['True']}],
                      'taints':[{'key':TAINT,'effect':'NoExecute'}]}}
    if obj(K + ['get', 'clustertaintpolicy', POLICY, '--ignore-not-found']): raise RuntimeError('Test policy already exists')
    created = json.loads(run(K + ['create', '-f', '-', '-o', 'json'], input=json.dumps(policy)))
    state['policy_uid'] = created['metadata']['uid']; state['policy_created'] = True; save()
    marker('Failover test: pause dc-primary, toleration 120s')
    pause()
    wait_for('failover-detection', lambda r: r['ready'] in ('False','Unknown') and any(
        t.get('key') == TAINT and t.get('effect') == 'NoExecute' for t in r['taints']), source=False, timeout=180)
    marker('Failover test: NoExecute detected')
    def success(row):
        survivors = ('dc-secondary', 'cloud-azure')
        return (row['desired'] == 8 and row['assigned']['dc-primary'] == 0
                and row['assigned']['cloud-azure'] > 0 and row['members']['cloud-azure']['available'] > 0
                and sum(row['assigned'][n] for n in survivors) == 8
                and all(row['members'][n]['available'] == row['assigned'][n] for n in survivors)
                and sum(row['members'][n]['available'] for n in survivors) == 8)
    recovered = wait_for('failover-reassignment', success, source=False)
    event('failover-success', cloud_overflow=recovered['assigned']['cloud-azure'] > 0)
    marker('Failover test: 8 replicas available on healthy clusters')
    hold_failover(success, hold_seconds)
    unpause()
    wait_for('member-recovery', lambda row: row['ready'] == 'True' and not any(t.get('key') == TAINT for t in row['taints']), timeout=240)
    marker('Failover test: dc-primary recovered')
    event('experiment-complete', result='PASS', cloud_overflow=recovered['assigned']['cloud-azure'] > 0)


if __name__ == '__main__':
    status = 1
    try:
        main(); status = 0
    except (Exception, KeyboardInterrupt) as e:
        event('experiment-error', error=str(e)); print('FAILOVER TEST ERROR:', str(e), file=sys.stderr, flush=True)
    finally:
        failures = cleanup()
        event('cleanup', status='FAIL' if failures else 'PASS', failures=failures)
        if failures: status = 1
        print('Failover evidence:', run_dir, flush=True)
    sys.exit(status)
