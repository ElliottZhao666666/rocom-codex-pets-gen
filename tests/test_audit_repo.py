"""The media exception is restricted to the two explicitly approved doc previews."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class RepositoryAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = Path(__file__).resolve().parents[1]
        (self.root/'scripts').mkdir()
        (self.root/'docs/images').mkdir(parents=True)
        shutil.copy2(source/'scripts/audit_repo.py', self.root/'scripts/audit_repo.py')
        for name in ('codex-pets-preview.png', 'juhuali-colors.png'):
            shutil.copy2(source/'docs/images'/name, self.root/'docs/images'/name)

    def tearDown(self):
        self.temp.cleanup()

    def run_audit(self):
        result = subprocess.run([sys.executable, str(self.root/'scripts/audit_repo.py')],
                                capture_output=True, text=True, encoding='utf-8')
        return result.returncode, json.loads(result.stdout)

    def test_exact_approved_previews_are_allowed(self):
        code, report = self.run_audit()
        self.assertEqual(code, 0)
        self.assertEqual(len(report['approved_documentation_previews']), 2)

    def test_an_unapproved_png_is_rejected(self):
        (self.root/'docs/images/extra.png').write_bytes(b'not-approved')
        code, report = self.run_audit()
        self.assertEqual(code, 1)
        self.assertIn('docs/images/extra.png', report['private_files_found'])

    def test_renaming_other_bytes_to_an_approved_name_is_rejected(self):
        path = self.root/'docs/images/codex-pets-preview.png'
        path.write_bytes(path.read_bytes()+b'changed')
        code, report = self.run_audit()
        self.assertEqual(code, 1)
        self.assertIn('docs/images/codex-pets-preview.png', report['missing_or_changed_previews'])


if __name__ == '__main__':
    unittest.main()
