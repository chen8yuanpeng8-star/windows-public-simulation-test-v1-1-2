import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from simtest.identity import EvidenceLevel, build_identity_field, authority_eligible
from simtest.lease import Lease, LeaseState, evaluate_lease
from simtest.rollback import restore_snapshot, snapshot_files
from simtest.workers import DrainCoordinator
from simtest.eod import Checkpoint, close_day
from simtest.failure_log import run_with_failure_log
from simtest.hash_safety import freeze_and_hash, serialized_hash


class LeaseTests(unittest.TestCase):
    def test_unexpired_lease_suppresses_restart(self):
        lease = Lease("lease-1", "sim-service", 100, 200, "local-test")
        self.assertEqual(evaluate_lease(lease, now=150), LeaseState.MAINTENANCE_ACTIVE)

    def test_expired_lease_does_not_suppress_recovery(self):
        lease = Lease("lease-2", "sim-service", 100, 200, "local-test")
        self.assertEqual(evaluate_lease(lease, now=201), LeaseState.MAINTENANCE_EXPIRED)


class IdentityTests(unittest.TestCase):
    def test_historical_and_mock_never_become_live_authority(self):
        for provider in ("historical", "mock", "demo"):
            field = build_identity_field(provider, "test fixture", EvidenceLevel.RUNTIME_VERIFIED)
            self.assertFalse(authority_eligible(provider, field))

    def test_unproven_runtime_identity_fails_closed(self):
        field = build_identity_field(None, None, EvidenceLevel.UNKNOWN)
        self.assertEqual(field.evidence_level, EvidenceLevel.UNKNOWN)
        self.assertFalse(authority_eligible("live", field))


class DrainTests(unittest.IsolatedAsyncioTestCase):
    async def test_drain_stops_accepting_then_waits_for_worker(self):
        coordinator = DrainCoordinator()
        finished = asyncio.Event()
        coordinator.register("worker-1", finished.wait)
        coordinator.start_accepting()
        result_task = asyncio.create_task(coordinator.drain(timeout=1.0))
        await asyncio.sleep(0)
        self.assertFalse(coordinator.accepting)
        finished.set()
        result = await result_task
        self.assertEqual(result.exited, ("worker-1",))
        self.assertEqual(result.timed_out, ())

    async def test_drain_reports_timeout_without_claiming_success(self):
        coordinator = DrainCoordinator()
        never = asyncio.Event()
        coordinator.register("stuck-worker", never.wait)
        result = await coordinator.drain(timeout=0.01)
        self.assertEqual(result.timed_out, ("stuck-worker",))


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_fastapi_lifespan_drains_workers(self):
        try:
            from simtest.lifecycle import create_app
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("FastAPI dependency is installed by the locked Windows workflow")
            raise
        coordinator = DrainCoordinator()
        app = create_app(coordinator)
        async with app.router.lifespan_context(app):
            self.assertTrue(coordinator.accepting)
        self.assertFalse(coordinator.accepting)


class StorageAndRollbackTests(unittest.TestCase):
    def test_temporary_sqlite_transaction_commit_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "isolated.sqlite3"
            conn = sqlite3.connect(db)
            try:
                conn.execute("CREATE TABLE sample (value TEXT)")
                conn.execute("INSERT INTO sample VALUES ('committed')")
                conn.commit()
            finally:
                conn.close()
            conn = sqlite3.connect(db)
            try:
                conn.execute("INSERT INTO sample VALUES ('rolled back')")
                conn.rollback()
            finally:
                conn.close()
            conn = sqlite3.connect(db)
            try:
                values = [row[0] for row in conn.execute("SELECT value FROM sample")]
            finally:
                conn.close()
            self.assertEqual(values, ["committed"])

    def test_file_snapshot_restores_exact_bytes_and_removes_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".simulation-only").write_text("yes", encoding="utf-8")
            target = root / "state.txt"
            target.write_bytes(b"before\x00bytes")
            snapshot = snapshot_files(root, ["state.txt"])
            target.write_bytes(b"changed")
            (root / "new.txt").write_text("new", encoding="utf-8")
            restore_snapshot(root, snapshot)
            self.assertEqual(target.read_bytes(), b"before\x00bytes")
            self.assertFalse((root / "new.txt").exists())

    def test_frozen_payload_hash_matches_persisted_snapshot_after_mutation(self):
        payload = {"nested": {"value": 1}}
        frozen, digest = freeze_and_hash(payload)
        payload["nested"]["value"] = 2
        self.assertEqual(serialized_hash(frozen), digest)
        self.assertNotEqual(serialized_hash(payload), digest)


class FailureAndEodTests(unittest.TestCase):
    def test_exception_exit_code_and_log_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "failure.log"

            def fail():
                raise RuntimeError("synthetic failure")

            result = run_with_failure_log(fail, log)
            self.assertEqual(result["exit_code"], 1)
            self.assertIn("synthetic failure", log.read_text(encoding="utf-8"))

    def test_eod_success_and_fail_closed_summary(self):
        completed = close_day([Checkpoint("a", "PASS"), Checkpoint("b", "PASS")], 0)
        failed = close_day([Checkpoint("a", "PASS"), Checkpoint("b", "MISSED")], 0)
        empty = close_day([], 0)
        self.assertEqual(completed["status"], "COMPLETE")
        self.assertEqual(failed["status"], "FAILED_INCOMPLETE")
        self.assertEqual(failed["missing_checkpoints"], ("b",))
        self.assertEqual(empty["status"], "FAILED_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
