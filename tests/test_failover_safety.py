"""Guard against touching a paused or replaced node and overwriting user state."""
import importlib.util
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


class FailoverSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        script = self.root / 'scripts/run-failover.py'
        shutil.copy(Path(__file__).resolve().parents[1] / 'scripts/run-failover.py', script)
        shutil.copy(Path(__file__).resolve().parents[1] / 'scripts/calibrate-capacity.py', self.root / 'scripts/calibrate-capacity.py')
        self.previous = Path.cwd()
        spec = importlib.util.spec_from_file_location('failover_test_subject', script)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        import os
        os.chdir(self.previous)
        self.temp.cleanup()

    def test_existing_pause_is_not_unpaused(self):
        with patch.object(self.module, 'owned', return_value=('id', True, True)), \
             patch.object(self.module, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'unpaused'):
                self.module.pause()
            self.module.unpause()
            command.assert_not_called()

    def test_identity_mismatch_refuses_operation(self):
        path = self.root / '.runtime/kind-owned/dc-primary.id'
        path.parent.mkdir(parents=True)
        path.write_text('old-id\n')
        with patch.object(self.module, 'docker_state', return_value=('different-id', True, True)):
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                self.module.owned()

    def test_restore_does_not_overwrite_external_replica_change(self):
        self.module.state.update({'scaled_by_run': True, 'original_replicas': 12})
        def fake_obj(args):
            if 'federatedhpa' in args:
                return None
            return {'spec': {'replicas': 9}}
        with patch.object(self.module, 'obj', side_effect=fake_obj), \
             patch.object(self.module, 'run') as command, contextlib.redirect_stderr(io.StringIO()):
            failures = self.module.cleanup()
            self.assertTrue(any('refusing overwrite' in error for error in failures))
            command.assert_not_called()

    def test_feature_gate_preserves_other_values(self):
        actual = self.module.flags(['controller', '--feature-gates=Other=true,Failover=false'],
                                   {'enable-no-execute-taint-eviction': 'true'}, 'Failover')
        self.assertIn('--feature-gates=Other=true,Failover=true', actual)
        self.assertIn('--enable-no-execute-taint-eviction=true', actual)

    def test_cpu_summary_quantities_and_unknown_values(self):
        self.assertEqual(self.module.cpu_millicores('12'), 12000)
        self.assertEqual(self.module.cpu_millicores('11850m'), 11850)
        with self.assertRaises(RuntimeError):
            self.module.cpu_millicores('not-a-quantity')

    def test_strategy_restoration_refuses_external_change(self):
        self.module.state['strategies']['karmada-webhook'] = {'type': 'RollingUpdate'}
        with patch.object(self.module, 'dep', return_value={'spec': {'strategy': {'type': 'External'}}}), \
             patch.object(self.module, 'change_strategy') as change, contextlib.redirect_stderr(io.StringIO()):
            failures = self.module.cleanup()
            self.assertTrue(any('strategy changed externally' in error for error in failures))
            change.assert_not_called()

    def test_capacity_waits_until_karmada_matches_member_requests(self):
        node = {'metadata': {'name': 'secondary-node'}, 'status': {'allocatable': {'cpu': '12'}}}
        pod = {'spec': {'nodeName': 'secondary-node', 'containers': [{'resources': {'requests': {'cpu': '11850m'}}}]},
               'status': {'phase': 'Running'}}
        def fake_obj(args):
            return {'items': [node if 'nodes' in args else pod]}
        def summary(cpu):
            return {'status': {'resourceSummary': {'allocatable': {'cpu': '12'}, 'allocated': {'cpu': cpu}}}}
        with patch.object(self.module, 'obj', side_effect=fake_obj), \
             patch.object(self.module, 'cluster', side_effect=[summary('11600m'), summary('11850m')]) as check, \
             patch.object(self.module.time, 'sleep'):
            result = self.module.secondary_capacity(6)
            self.assertEqual(check.call_count, 2)
            self.assertEqual(result['secondary_total_cpu_slots'], 6)

    def test_cloud_hold_waits_and_checks_each_sample(self):
        now = [0]
        def advance(seconds):
            now[0] += seconds
        with patch.object(self.module.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(self.module.time, 'sleep', side_effect=advance), \
             patch.object(self.module, 'owned', return_value=('id', True, True)), \
             patch.object(self.module, 'state_snapshot', return_value={'cloud': 'ready'}) as snapshot, \
             patch.object(self.module, 'marker'), patch.object(self.module, 'event'):
            self.module.hold_failover(lambda row: row['cloud'] == 'ready', 10)
            self.assertEqual(now[0], 10)
            self.assertEqual(snapshot.call_count, 2)

    def test_healthy_rejects_pending_eviction_and_test_taint(self):
        row = {'ready': 'True', 'desired': 8, 'assigned': {'dc-primary': 3, 'dc-secondary': 5, 'cloud-azure': 0},
               'members': {'dc-primary': {'desired': 3, 'available': 3},
                           'dc-secondary': {'desired': 5, 'available': 5},
                           'cloud-azure': {'desired': 0, 'available': 0}}, 'taints': [], 'eviction_tasks': []}
        self.assertTrue(self.module.healthy(row, 8))
        row['eviction_tasks'] = [{'fromCluster': 'dc-primary'}]
        self.assertFalse(self.module.healthy(row, 8))
        row['eviction_tasks'] = []
        row['taints'] = [{'key': self.module.TAINT}]
        self.assertFalse(self.module.healthy(row, 8))


if __name__ == '__main__':
    unittest.main()
