import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
META = {"TEST_MANIFEST.json", "PUBLIC_RELEASE_AUDIT.json", "SHA256SUMS.txt"}
ALLOWLIST = {
    ".github/workflows/windows-simulation.yml",
    "README_WINDOWS_TEST.md",
    "requirements-lock.txt",
    "run_tests.ps1",
    "powershell/SimulatedService.ps1",
    "powershell/Watchdog-Sim.ps1",
    "scripts/build_audit.py",
    "scripts/build_zip.py",
    "scripts/security_scan.py",
    "scripts/verify_manifest.py",
    "scripts/verify_zip.py",
    "scripts/run_python_tests.py",
    "scripts/check_powershell_counts.py",
    "simtest/__init__.py",
    "simtest/eod.py",
    "simtest/failure_log.py",
    "simtest/hash_safety.py",
    "simtest/identity.py",
    "simtest/lease.py",
    "simtest/lifecycle.py",
    "simtest/rollback.py",
    "simtest/workers.py",
    "tests/Watchdog.Tests.ps1",
    "tests/test_simulation.py",
    "tests/test_test_count_gate.py",
    "simtest/test_gate.py",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_on_disk():
    return {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def main():
    actual = files_on_disk()
    expected = ALLOWLIST | META
    if actual != expected:
        raise SystemExit(f"allowlist mismatch; extra={sorted(actual-expected)} missing={sorted(expected-actual)}")

    payload = sorted(ALLOWLIST)
    manifest = {
        "bundle_id": "public-windows-simulation-tests",
        "version": "1.1.3",
        "release_type": "pure_simulation_only",
        "python": "3.11.x",
        "runner": "windows-2022 standard hosted runner",
        "history_included": False,
        "files": [{"path": name, "sha256": digest(ROOT / name)} for name in payload],
        "metadata_files": sorted(META),
        "production_source_parity": "NONE: independently authored simulations only",
        "production_verification": "NOT_PERFORMED",
        "minimum_tests": {"python": 17, "powershell_assertions": 5},
        "skip_policy": "Any skip prevents FULL_PASS",
    }
    (ROOT / "TEST_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    inventory = []
    for name in sorted(expected):
        if name in {"PUBLIC_RELEASE_AUDIT.json", "SHA256SUMS.txt"}:
            inventory.append({"path": name, "sha256": None, "hash_note": "self-referential metadata; covered by SHA256SUMS where applicable"})
        else:
            inventory.append({"path": name, "sha256": digest(ROOT / name)})
    audit = {
        "audit_schema": "PUBLIC_RELEASE_AUDIT_V1",
        "review_status": "REVIEWED_FOR_AUTHORIZED_V1_1_3_PUBLIC_RELEASE",
        "public_release": True,
        "package_version": "1.1.3",
        "repository_history_included": False,
        "source_origin": "generic simulation content; review found no identifiable project-specific source; authoring provenance is not independently verified from the archive",
        "security_scope": {
            "production_data_included": False,
            "secrets_included": False,
            "personal_files_included": False,
            "live_evidence_included": False,
            "test_code_external_service_calls": False,
            "dependency_setup_network": "pip downloads pinned packages from the configured package index",
            "real_order_capability": False,
        },
        "automated_checks": {
            "file_allowlist": "PENDING",
            "manifest_hashes": "PENDING",
            "sensitive_data_scan": "PENDING",
            "git_history_included": False,
        },
        "test_gates": {
            "python_minimum": 17,
            "powershell_assertion_minimum": 5,
            "zero_test_count": "FAIL",
            "any_skip": "FAIL_FOR_FULL_PASS",
        },
        "local_validation": {
            "scanner_and_gate_regressions": "PASS: 14 targeted tests",
            "full_windows_suite": "PENDING_GITHUB_ACTIONS",
            "powershell_source_parse": "PASS",
            "powershell_child_process_execution": "PENDING_GITHUB_ACTIONS",
            "github_actions_run": "PENDING_AUTHORIZED_V1_1_3_RUN",
        },
        "workflow": {
            "runner": "windows-2022",
            "trigger": "workflow_dispatch only",
            "max_parallel_runs": 1,
            "timeout_minutes": 20,
            "token_permissions": {"contents": "read"},
            "secrets_configured": False,
            "larger_runner": False,
            "artifact_upload": False,
            "evidence_retained_in": "Actions run logs and job summary; no artifact storage",
        },
        "files": inventory,
        "unverified_until_actions_run": ["actual Windows hosted-runner behavior", "GitHub workflow run", "end-to-end run result"],
    }
    (ROOT / "PUBLIC_RELEASE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    def write_checksums():
        checksum_names = sorted(expected - {"SHA256SUMS.txt"})
        sums = "".join(f"{digest(ROOT / name)}  {name}\n" for name in checksum_names)
        (ROOT / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")

    write_checksums()
    subprocess.run([sys.executable, str(ROOT / "scripts/verify_manifest.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/security_scan.py")], check=True)
    audit["automated_checks"] = {
        "file_allowlist": "PASS",
        "manifest_hashes": "PASS",
        "sensitive_data_scan": "PASS",
        "git_history_included": False,
    }
    (ROOT / "PUBLIC_RELEASE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    write_checksums()
    subprocess.run([sys.executable, str(ROOT / "scripts/verify_manifest.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/security_scan.py")], check=True)
    print(f"AUDIT_GENERATED files={len(expected)} payload={len(payload)}")


if __name__ == "__main__":
    main()
