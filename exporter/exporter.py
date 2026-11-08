"""Export a small, deliberately low-cardinality Karmada placement view.

Run with KUBECONFIG pointing to the Karmada control-plane kubeconfig.
The exporter must NOT be mistaken for a full scheduler estimator.
"""
import logging
import os
import time
from prometheus_client import Gauge, Counter, start_http_server
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

LOG = logging.getLogger('karmada-lab-exporter')
NAMESPACE = os.getenv('LAB_NAMESPACE', 'demo')
WORKLOAD = os.getenv('LAB_WORKLOAD', 'placement-demo')
CLUSTERS = tuple(os.getenv('LAB_CLUSTERS', 'dc-primary,dc-secondary,cloud-azure').split(','))

DESIRED = Gauge('karmada_lab_desired_replicas', 'Top-level desired replicas from the Karmada resource template', ['namespace', 'workload'])
ASSIGNED = Gauge('karmada_lab_assigned_replicas', 'Replicas assigned in ResourceBinding.spec.clusters', ['namespace', 'workload', 'member_cluster'])
POLL_OK = Gauge('karmada_lab_exporter_poll_success', 'Whether last polling cycle succeeded')
WORKLOAD_PRESENT = Gauge('karmada_lab_workload_present', 'Whether the observed Karmada Deployment exists')
POLL_TIME = Gauge('karmada_lab_exporter_last_poll_timestamp_seconds', 'Last successful poll Unix timestamp')
HPA_ACTIVE = Gauge('karmada_lab_hpa_active', 'Whether FederatedHPA is configured for demo workload')
HPA_CURRENT = Gauge('karmada_lab_hpa_current_replicas', 'FederatedHPA current replicas')
HPA_DESIRED = Gauge('karmada_lab_hpa_desired_replicas', 'FederatedHPA desired replicas')
HPA_CPU = Gauge('karmada_lab_hpa_cpu_utilization_percent', 'FederatedHPA observed CPU utilization percentage')
HPA_TARGET = Gauge('karmada_lab_hpa_cpu_target_percent', 'FederatedHPA target CPU utilization percentage')
DECISIONS = Counter('karmada_lab_binding_changes_total', 'Observed changes in ResourceBinding replica assignments (since exporter start)', ['namespace', 'workload'])


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    config.load_kube_config(config_file=os.path.expanduser(os.getenv('KUBECONFIG', '~/.kube/karmada.config')),
                            context=os.getenv('KARMADA_CONTEXT', 'karmada-apiserver'))
    apps = client.AppsV1Api()
    customs = client.CustomObjectsApi()
    start_http_server(int(os.getenv('EXPORTER_PORT', '9400')))
    last_assignments = None
    interval = float(os.getenv('POLL_SECONDS', '3'))
    while True:
        try:
            try:
                d = apps.read_namespaced_deployment(WORKLOAD, NAMESPACE)
            except ApiException as exc:
                if exc.status != 404:
                    raise
                # No observed Deployment is different from a desired zero.
                DESIRED.clear()
                ASSIGNED.clear()
                WORKLOAD_PRESENT.set(0)
                for gauge in (HPA_ACTIVE, HPA_CURRENT, HPA_DESIRED, HPA_CPU, HPA_TARGET):
                    gauge.set(float('nan'))
                last_assignments = None
                POLL_OK.set(1)
                POLL_TIME.set(time.time())
                time.sleep(interval)
                continue
            desired = int(d.spec.replicas or 0)
            bindings = customs.list_namespaced_custom_object('work.karmada.io', 'v1alpha2', NAMESPACE, 'resourcebindings')
            allocations = {cluster: 0 for cluster in CLUSTERS}
            for binding in bindings.get('items', []):
                ref = binding.get('spec', {}).get('resource', {})
                if ref.get('kind') == 'Deployment' and ref.get('name') == WORKLOAD:
                    for target in binding.get('spec', {}).get('clusters', []):
                        name = target.get('name')
                        if name in allocations:
                            allocations[name] += int(target.get('replicas') or 0)
            try:
                hpa = customs.get_namespaced_custom_object(
                    'autoscaling.karmada.io', 'v1alpha1', NAMESPACE, 'federatedhpas', WORKLOAD)
                HPA_ACTIVE.set(1)
                status = hpa.get('status') or {}
                HPA_CURRENT.set(status.get('currentReplicas') if status.get('currentReplicas') is not None else float('nan'))
                HPA_DESIRED.set(status.get('desiredReplicas') if status.get('desiredReplicas') is not None else float('nan'))
                metric = next((m for m in status.get('currentMetrics', [])
                               if m.get('type') == 'Resource'
                               and m.get('resource', {}).get('name') == 'cpu'), None)
                observed = ((metric or {}).get('resource') or {}).get('current') or {}
                utilization = observed.get('averageUtilization')
                HPA_CPU.set(utilization if utilization is not None else float('nan'))
                HPA_TARGET.set(float('nan'))
                for m in hpa.get('spec', {}).get('metrics', []):
                    if m.get('type') == 'Resource' and m.get('resource', {}).get('name') == 'cpu':
                        target = m['resource'].get('target', {}).get('averageUtilization')
                        HPA_TARGET.set(target if target is not None else float('nan'))
                        break
            except ApiException as exc:
                if exc.status != 404:
                    raise
                HPA_ACTIVE.set(0)
                # An absent HPA has no utilization, target, or replica status.
                # Zero would falsely imply an active HPA targeting 0% CPU.
                for gauge in (HPA_CURRENT, HPA_DESIRED, HPA_CPU, HPA_TARGET):
                    gauge.set(float('nan'))
            DESIRED.labels(NAMESPACE, WORKLOAD).set(desired)
            for name, count in allocations.items():
                ASSIGNED.labels(NAMESPACE, WORKLOAD, name).set(count)
            fingerprint = (desired, tuple(sorted(allocations.items())))
            if last_assignments is not None and fingerprint != last_assignments:
                DECISIONS.labels(NAMESPACE, WORKLOAD).inc()
                LOG.info('placement change: desired=%d assigned=%s', desired, allocations)
            last_assignments = fingerprint
            WORKLOAD_PRESENT.set(1)
            POLL_OK.set(1)
            POLL_TIME.set(time.time())
        except Exception:
            LOG.exception('Cannot poll Karmada API')
            POLL_OK.set(0)
            WORKLOAD_PRESENT.set(float('nan'))
            DESIRED.clear()
            ASSIGNED.clear()
            for gauge in (HPA_ACTIVE, HPA_CURRENT, HPA_DESIRED, HPA_CPU, HPA_TARGET):
                gauge.set(float('nan'))
        time.sleep(interval)


if __name__ == '__main__':
    main()
