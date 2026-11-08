"""The teardown must validate all ownership records before deleting anything."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class DownSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'bin').mkdir()
        (self.root / '.runtime/kind-owned').mkdir(parents=True)
        shutil.copy(Path(__file__).resolve().parents[1] / 'scripts/down.sh', self.root / 'scripts/down.sh')
        self.make_command('kind', '''#!/bin/sh
if [ "$1" = get ]; then
  printf '%s\\n' karmada-mgmt dc-primary
else
  printf '%s\\n' "$*" >> "$TEST_LOG"
fi
''')
        self.make_command('docker', '''#!/bin/sh
case "$4" in
  karmada-mgmt-control-plane) echo mgmt-id ;;
  dc-primary-control-plane) echo primary-id ;;
esac
''')
        self.env = os.environ.copy()
        self.env['PATH'] = str(self.root / 'bin') + ':' + self.env['PATH']
        self.env['TEST_LOG'] = str(self.root / 'deleted.log')
        self.ids = self.root / '.runtime/kind-owned'
        (self.ids / 'karmada-mgmt.id').write_text('mgmt-id\n')

    def tearDown(self):
        self.temp.cleanup()

    def make_command(self, name, source):
        path = self.root / 'bin' / name
        path.write_text(source)
        path.chmod(0o755)

    def run_down(self):
        return subprocess.run(['bash', str(self.root / 'scripts/down.sh')], env=self.env,
                              text=True, capture_output=True)

    def test_missing_or_mismatched_record_prevents_any_deletion(self):
        result = self.run_down()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dc-primary', result.stderr)
        self.assertFalse((self.root / 'deleted.log').exists())
        (self.ids / 'dc-primary.id').write_text('wrong-id\n')
        result = self.run_down()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dc-primary', result.stderr)
        self.assertFalse((self.root / 'deleted.log').exists())

    def test_only_matching_owned_clusters_are_deleted(self):
        (self.ids / 'dc-primary.id').write_text('primary-id\n')
        result = self.run_down()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'deleted.log').read_text().splitlines(),
                         ['delete cluster --name karmada-mgmt', 'delete cluster --name dc-primary'])


if __name__ == '__main__':
    unittest.main()
