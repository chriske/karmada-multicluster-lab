#!/usr/bin/env python3
"""Wait for a manual stage and write actual desired, assigned and Ready values."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

clusters = ('dc-primary', 'dc-secondary', 'cloud-azure')
kcfg = os.environ['KARMADA_CONFIG']
desired, stage = int(sys.argv[1]), int(sys.argv[2])
timeout = int(os.getenv('STAGE_TIMEOUT', '240'))
log = Path(os.environ['MANUAL_SNAPSHOT_LOG'])


def read(*args):
    result = subprocess.run(['kubectl', *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def snapshot():
    deployment = read('--kubeconfig', kcfg, '-n', 'demo', 'get', 'deployment', 'placement-demo', '-o', 'json')
    bindings = read('--kubeconfig', kcfg, '-n', 'demo', 'get', 'resourcebindings', '-o', 'json')['items']
    assignments = {name: 0 for name in clusters}
    matching = [b for b in bindings if b.get('spec', {}).get('resource', {}).get('name') == 'placement-demo'
                and b.get('spec', {}).get('resource', {}).get('kind') == 'Deployment']
    for binding in matching:
        for target in binding.get('spec', {}).get('clusters', []):
            if target['name'] in assignments:
                assignments[target['name']] += int(target.get('replicas') or 0)
    members = {}
    for name in clusters:
        member = read('--context', 'kind-' + name, '-n', 'demo', 'get', 'deployment', 'placement-demo',
                      '--ignore-not-found', '-o', 'json')
        members[name] = {'desired': int((member or {}).get('spec', {}).get('replicas') or 0),
                         'ready': int((member or {}).get('status', {}).get('availableReplicas') or 0)}
    return {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'stage': stage, 'desired': int(deployment.get('spec', {}).get('replicas') or 0),
            'binding_count': len(matching), 'assigned': assignments, 'members': members}


deadline = time.monotonic() + timeout
last = None
while time.monotonic() < deadline:
    last = snapshot()
    converged = (last['desired'] == desired and last['binding_count'] == 1
                 and sum(last['assigned'].values()) == desired
                 and all(last['members'][c]['desired'] == last['assigned'][c]
                         and last['members'][c]['ready'] == last['assigned'][c] for c in clusters))
    if converged:
        # The first three scale-up points should fit on-prem; cloud overflow is
        # required at 16 and 22. Scale-in placement is observed, not assumed.
        error = None
        if stage <= 3 and last['assigned']['cloud-azure'] != 0:
            error = 'Unexpected cloud assignment before nominal on-prem capacity is full'
        if stage in (4, 5) and last['assigned']['cloud-azure'] == 0:
            error = 'Expected cloud overflow was not observed'
        last['status'] = 'FAIL' if error else 'PASS'
        with log.open('a', encoding='utf-8') as out:
            out.write(json.dumps(last, sort_keys=True) + '\n')
        print(json.dumps(last, sort_keys=True), flush=True)
        if error:
            sys.exit(error)
        sys.exit(0)
    time.sleep(3)
if last is not None:
    last['status'] = 'TIMEOUT'
    with log.open('a', encoding='utf-8') as out:
        out.write(json.dumps(last, sort_keys=True) + '\n')
sys.exit(f'Stage {stage} did not converge within {timeout}s; last snapshot: {json.dumps(last)}')
