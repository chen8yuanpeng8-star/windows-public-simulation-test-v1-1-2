import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from simtest.test_gate import GateResult, evaluate_python_counts, evaluate_powershell_counts


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class ReleaseScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "bundle"
        manifest = json.loads((SOURCE_ROOT / "TEST_MANIFEST.json").read_text(encoding="utf-8"))
        names = [item["path"] for item in manifest["files"]] + manifest["metadata_files"]
        for name in names:
            source = SOURCE_ROOT / name
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, relative_path):
        return subprocess.run(
            [sys.executable, "-B", str(self.root / relative_path)],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_root_git_metadata_is_excluded_by_both_scanners(self):
        git_dir = self.root / ".git"
        (git_dir / "objects").mkdir(parents=True)
        (git_dir / "config").write_text("isolated test git metadata", encoding="utf-8")
        (git_dir / "objects" / "fixture").write_text("not package content", encoding="utf-8")
        manifest = self.run_script("scripts/verify_manifest.py")
        security = self.run_script("scripts/security_scan.py")
        self.assertEqual(manifest.returncode, 0, manifest.stdout + manifest.stderr)
        self.assertEqual(security.returncode, 0, security.stdout + security.stderr)

    def test_release_metadata_uses_canonical_lf_bytes(self):
        for name in ("PUBLIC_RELEASE_AUDIT.json", "SHA256SUMS.txt", "TEST_MANIFEST.json"):
            content = (self.root / name).read_bytes()
            self.assertNotIn(b"\r\n", content, name)

    def test_unlisted_github_workflow_is_not_ignored(self):
        extra = self.root / ".github" / "workflows" / "unlisted.yml"
        extra.write_text("name: unlisted", encoding="utf-8")
        self.assertNotEqual(self.run_script("scripts/verify_manifest.py").returncode, 0)
        self.assertNotEqual(self.run_script("scripts/security_scan.py").returncode, 0)

    def test_unlisted_hidden_directory_is_not_ignored(self):
        extra = self.root / ".hidden" / "unlisted.txt"
        extra.parent.mkdir()
        extra.write_text("unlisted", encoding="utf-8")
        self.assertNotEqual(self.run_script("scripts/verify_manifest.py").returncode, 0)
        self.assertNotEqual(self.run_script("scripts/security_scan.py").returncode, 0)

    def test_nested_git_metadata_is_not_excluded(self):
        extra = self.root / "nested" / ".git" / "config"
        extra.parent.mkdir(parents=True)
        extra.write_text("not root metadata", encoding="utf-8")
        self.assertNotEqual(self.run_script("scripts/verify_manifest.py").returncode, 0)
        self.assertNotEqual(self.run_script("scripts/security_scan.py").returncode, 0)

    def test_modified_reviewed_file_fails_manifest_hash_check(self):
        readme = self.root / "README_WINDOWS_TEST.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        result = self.run_script("scripts/verify_manifest.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hash", (result.stdout + result.stderr).casefold())

    def test_modified_workflow_fails_manifest_hash_check(self):
        workflow = self.root / ".github" / "workflows" / "windows-simulation.yml"
        workflow.write_text(workflow.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        result = self.run_script("scripts/verify_manifest.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workflow", (result.stdout + result.stderr).casefold())

    def test_line_ending_conversion_fails_raw_hash_check(self):
        workflow = self.root / ".github" / "workflows" / "windows-simulation.yml"
        original = workflow.read_bytes()
        self.assertIn(b"\n", original)
        self.assertNotIn(b"\r\n", original)
        workflow.write_bytes(original.replace(b"\n", b"\r\n"))
        result = self.run_script("scripts/verify_manifest.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hash", (result.stdout + result.stderr).casefold())

    def test_sensitive_filename_is_rejected(self):
        (self.root / "unexpected.sqlite3").write_bytes(b"not a database")
        result = self.run_script("scripts/security_scan.py")
        self.assertNotEqual(result.returncode, 0)

    def test_sensitive_windows_path_in_allowed_file_is_rejected(self):
        readme = self.root / "README_WINDOWS_TEST.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nC:\\Users\\placeholder\\secret.txt\n", encoding="utf-8")
        result = self.run_script("scripts/security_scan.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sensitive-pattern", (result.stdout + result.stderr).casefold())

    def test_symlink_is_rejected_by_both_scanners(self):
        external = Path(self.temp.name) / "external"
        external.mkdir()
        (external / "unlisted.txt").write_text("outside bundle", encoding="utf-8")
        link = self.root / "linked-directory"
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(external)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(self.run_script("scripts/verify_manifest.py").returncode, 0)
        self.assertNotEqual(self.run_script("scripts/security_scan.py").returncode, 0)

    def test_manifest_path_traversal_is_rejected(self):
        path = self.root / "TEST_MANIFEST.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["files"][0]["path"] = "../outside.txt"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = self.run_script("scripts/verify_manifest.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe", (result.stdout + result.stderr).casefold())


class TestCountGateTests(unittest.TestCase):
    def test_zero_python_tests_is_failure(self):
        result = evaluate_python_counts(run=0, failures=0, errors=0, skipped=0, minimum=17)
        self.assertFalse(result.full_pass)
        self.assertIn("below minimum", result.reasons[0])

    def test_skipped_python_test_blocks_full_pass(self):
        result = evaluate_python_counts(run=17, failures=0, errors=0, skipped=1, minimum=17)
        self.assertFalse(result.full_pass)
        self.assertEqual(result.passed, 16)
        self.assertEqual(result.skipped, 1)

    def test_complete_python_suite_passes_with_exact_counts(self):
        result = evaluate_python_counts(run=17, failures=0, errors=0, skipped=0, minimum=17)
        self.assertEqual(result, GateResult(True, 17, 0, 0, ()))

    def test_zero_powershell_assertions_is_failure(self):
        result = evaluate_powershell_counts(passed=0, failed=0, minimum=5)
        self.assertFalse(result.full_pass)
        self.assertIn("below minimum", result.reasons[0])

    def test_powershell_failure_and_minimum_are_independent(self):
        result = evaluate_powershell_counts(passed=5, failed=1, minimum=5)
        self.assertFalse(result.full_pass)
        self.assertEqual(result.passed, 5)
        self.assertEqual(result.failed, 1)


if __name__ == "__main__":
    unittest.main()
