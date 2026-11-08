#!/usr/bin/env python3
"""Request-only CPU reservations, calculated per kind node.

This is a transparent lab capacity model, NOT a production quota mechanism.
Memory/pod slots are still separate constraints. Assumes one node per cluster.
"""
import json
import subprocess
import sys

TARGETS = {'dc-primary': 4, 'dc-secondary': 6, 'cloud-azure': 12}
APP_REQUEST_M = 250
EXTRA_BUFFER_M = 150  # other lab workloads, scheduling estimates, low overhead


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


def main():
    for cluster,target in TARGETS.items():
        # apply generated namespace; don't assume it exists
        kubectl(cluster,'apply','-f','-', stdin='apiVersion: v1\nkind: Namespace\nmetadata:\n  name: karmada-lab-system\n')
        kubectl(cluster,'-n','karmada-lab-system','delete','pod','capacity-reservation','--ignore-not-found','--wait=true')
        nodes=json.loads(kubectl(cluster,'get','nodes','-o','json'))['items']
        if len(nodes)!=1:raise RuntimeError(f'{cluster}: calibrator supports exactly one node, found {len(nodes)}')
        node=nodes[0]; node_name=node['metadata']['name']
        alloc=cpu_m(node['status']['allocatable']['cpu'])
        pods=json.loads(kubectl(cluster,'get','pods','-A','-o','json'))['items']
        requested=sum(pod_cpu_requests(p) for p in pods if p.get('spec',{}).get('nodeName')==node_name
                      and p.get('status',{}).get('phase') not in ('Succeeded','Failed'))
        desired_free=target*APP_REQUEST_M+EXTRA_BUFFER_M
        reservation=alloc-requested-desired_free
        if reservation<100:
            raise RuntimeError(f'{cluster}: too little CPU headroom for reservation: alloc={alloc}m, '
                               f'existing={requested}m, target={desired_free}m')
        pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':'capacity-reservation',
             'namespace':'karmada-lab-system','labels':{'app':'capacity-reservation'}},
             'spec':{'nodeSelector':{'kubernetes.io/hostname':node_name},
             'containers':[{'name':'pause','image':'busybox:1.36',
             'command':['sh','-c','sleep 86400'],
             'resources':{'requests':{'cpu':f'{reservation}m','memory':'32Mi'}}}]}}
        print(f'{cluster}: allocatable={alloc}m already_requested={requested}m '
              f'reserve={reservation}m target_slots={target} (+{EXTRA_BUFFER_M}m buffer)',flush=True)
        kubectl(cluster,'apply','-f','-',stdin=json.dumps(pod))
        kubectl(cluster,'-n','karmada-lab-system','wait','pod/capacity-reservation',
                '--for=condition=Ready','--timeout=120s')
    print('Reservation Pods Ready. Verify Karmada Cluster resourceSummary converges before scale test.')

if __name__=='__main__':
    try:main()
    except (subprocess.CalledProcessError,RuntimeError) as e:
        print(f'Calibration failed: {e}',file=sys.stderr)
        sys.exit(1)
