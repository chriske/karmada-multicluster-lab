#!/usr/bin/env python3
"""Verify fresh events from all clusters, a marker, and Grafana provisioning."""
import base64
import datetime
import json
import os
import select
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

clusters = ('karmada-mgmt', 'dc-primary', 'dc-secondary', 'cloud-azure')
marker = 'lab-verify-' + uuid.uuid4().hex[:12]
now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
for cluster in clusters:
    base = ['kubectl', '--context', 'kind-' + cluster]
    account = json.loads(subprocess.run(base + ['-n', 'monitoring', 'get', 'serviceaccount', 'default', '-o', 'json'],
                                   check=True, text=True, capture_output=True).stdout)
    event = {'apiVersion': 'v1', 'kind': 'Event',
             'metadata': {'generateName': 'lab-verify-', 'namespace': 'monitoring'},
             'involvedObject': {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'name': 'default',
                                'namespace': 'monitoring', 'uid': account['metadata']['uid']},
             'reason': 'LabVerification', 'message': marker, 'type': 'Normal',
             'firstTimestamp': now, 'lastTimestamp': now, 'count': 1,
             'source': {'component': 'karmada-lab-verify'}}
    subprocess.run(base + ['create', '-f', '-'], input=json.dumps(event), text=True, check=True)
env = os.environ.copy()
env.update({'SCENARIO': 'verify', 'MARKER_REQUIRED': '1'})
subprocess.run(['python3', 'scripts/emit-marker.py', marker], env=env, check=True)


def query_loki(expression):
    params = urllib.parse.urlencode({'query': expression, 'limit': '1000',
                                     'start': str(time.time_ns() - 600 * 10**9),
                                     'end': str(time.time_ns() + 10 * 10**9)})
    with urllib.request.urlopen('http://127.0.0.1:31091/loki/api/v1/query_range?' + params, timeout=10) as response:
        return json.load(response)['data']['result']


for attempt in range(24):
    events = query_loki('{source_type="k8s-event"} |= "' + marker + '"')
    seen = {stream['stream'].get('source_cluster') for stream in events}
    markers = query_loki('{source_type="scenario-marker"} |= "' + marker + '"')
    if set(clusters) <= seen and markers:
        print('Loki: fresh events from all four clusters and scenario marker received', flush=True)
        break
    time.sleep(5)
else:
    raise SystemExit(f'Loki did not receive all verification events: got {sorted(seen)}, marker={bool(markers)}')

base = ['kubectl', '--context', 'kind-karmada-mgmt', '-n', 'monitoring']
secret = json.loads(subprocess.run(base + ['get', 'secret', 'grafana', '-o', 'json'], check=True,
                                   text=True, capture_output=True).stdout)['data']
username = base64.b64decode(secret['admin-user']).decode()
password = base64.b64decode(secret['admin-password']).decode()
auth = base64.b64encode((username + ':' + password).encode()).decode()
forward = subprocess.Popen(base + ['port-forward', '--address=127.0.0.1', 'svc/grafana', ':80'],
                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
try:
    port = None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and forward.poll() is None:
        if select.select([forward.stdout], [], [], 1)[0]:
            line = forward.stdout.readline()
            if line.startswith('Forwarding from 127.0.0.1:'):
                port = int(line.split('127.0.0.1:', 1)[1].split()[0])
                break
    if port is None:
        raise RuntimeError('Grafana port-forward did not become ready')

    def grafana(path):
        req = urllib.request.Request(f'http://127.0.0.1:{port}' + path, headers={'Authorization': 'Basic ' + auth})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    for uid in ('prometheus', 'loki'):
        if grafana(f'/api/datasources/uid/{uid}/health').get('status') != 'OK':
            raise RuntimeError(f'Grafana datasource {uid} is not healthy')
    dashboards = grafana('/api/search?type=dash-db')
    expected = {'Karmada | Hybrid Cloud Overview', 'Karmada | Scheduler & Propagation',
                'Karmada | Cluster Capacity & Placement'}
    selected = [d for d in dashboards if d.get('title') in expected]
    if {d['title'] for d in selected} != expected:
        raise RuntimeError('Expected Grafana dashboards are missing')
    for entry in selected:
        dashboard = grafana('/api/dashboards/uid/' + urllib.parse.quote(entry['uid']))['dashboard']
        annotations = dashboard.get('annotations', {}).get('list', [])
        for name, selector in (('Kubernetes Warning Events', 'k8s-event'), ('Lab scenario markers', 'scenario-marker')):
            if not any(a.get('name') == name and a.get('enable') and a.get('datasource', {}).get('uid') == 'loki'
                       and selector in (a.get('expr') or a.get('target', {}).get('expr') or '') for a in annotations):
                raise RuntimeError(f'{entry["title"]}: missing enabled Loki annotation {name}')
        panels = {p.get('title'): p for p in dashboard.get('panels', [])}
        replica_titles = {'Assigned by cluster', 'Ready by cluster', 'Assigned replicas by cluster',
                          'Ready replicas by cluster'} & panels.keys()
        for title in replica_titles:
            custom = panels[title].get('fieldConfig', {}).get('defaults', {}).get('custom', {})
            if custom.get('stacking', {}).get('mode') != 'none' or custom.get('lineInterpolation') != 'stepAfter':
                raise RuntimeError(f'{entry["title"]}: {title} must show individual replica values as steps')
        if entry['title'] == 'Karmada | Hybrid Cloud Overview':
            titles = {p.get('title') for p in dashboard.get('panels', [])}
            if not {'Demo actual CPU use by member', 'Demo actual memory use by member'} <= titles:
                raise RuntimeError('Grafana has not yet loaded the actual-usage dashboard panels')
            hpa = panels.get('FederatedHPA target vs observed CPU', {})
            expressions = {t.get('expr') for t in hpa.get('targets', [])}
            if not {'karmada_lab_hpa_cpu_utilization_percent', 'karmada_lab_hpa_cpu_target_percent'} <= expressions:
                raise RuntimeError('Grafana HPA chart is missing observed or target CPU')
    print('Grafana: datasources healthy; three dashboards and default annotation definitions present', flush=True)
finally:
    forward.terminate()
    try:
        forward.wait(timeout=5)
    except subprocess.TimeoutExpired:
        forward.kill()
        forward.wait()
