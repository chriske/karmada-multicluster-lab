#!/usr/bin/env python3
"""Use the exact Cluster resource summary for this request-calibrated lab."""
import json
import subprocess

base = ['kubectl', '--context', 'kind-karmada-mgmt', '-n', 'karmada-system']
deployment = json.loads(subprocess.run(base + ['get', 'deployment', 'karmada-scheduler', '-o', 'json'],
                                       check=True, capture_output=True, text=True).stdout)
container = deployment['spec']['template']['spec']['containers'][0]
if container['name'] != 'karmada-scheduler':
    raise SystemExit('Unexpected scheduler container layout; refusing to change feature gates')
command = container['command']
gate = 'CustomizedClusterResourceModeling'
flag_index = next((i for i, x in enumerate(command) if x.startswith('--feature-gates=')), None)
if flag_index is None:
    command.append(f'--feature-gates={gate}=false')
else:
    prefix, value = command[flag_index].split('=', 1)
    gates = [entry for entry in value.split(',') if not entry.startswith(gate + '=')]
    gates.append(f'{gate}=false')
    command[flag_index] = prefix + '=' + ','.join(gates)
patch = [{'op': 'replace', 'path': '/spec/strategy', 'value': {'type': 'Recreate'}},
         {'op': 'replace', 'path': '/spec/template/spec/containers/0/command', 'value': command}]
subprocess.run(base + ['patch', 'deployment', 'karmada-scheduler', '--type=json', '-p', json.dumps(patch)], check=True)
subprocess.run(base + ['rollout', 'status', 'deployment/karmada-scheduler', '--timeout=180s'], check=True)
