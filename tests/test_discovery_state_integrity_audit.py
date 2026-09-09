"""Audit-only negative controls for branch-discovery state integrity.

These tests intentionally encode fail-closed contracts that current runner v2
does not yet satisfy.  The branch is for scouting/reproduction only; no
production fix is included here.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_run_archive_offline import _load_runner_module, _stub_write_json


class DiscoveryStateIntegrityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner, cls._module_patcher = _load_runner_module()

    @classmethod
    def tearDownClass(cls):
        cls._module_patcher.stop()

    def setUp(self):
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.temp_root = Path(self._temporary_directory.name)
        self.task_dir = self.temp_root / "Creative-Intelligence"
        self.task_dir.mkdir()
        self._original_task_dir = self.runner.TASK_DIR
        self.runner.TASK_DIR = self.task_dir
        self.addCleanup(setattr, self.runner, "TASK_DIR", self._original_task_dir)

    def _job(self, target_archives=2):
        return self.runner.build_discovery_job(
            ["Category Theory"],
            target_archives=target_archives,
            run_name="discovery-integrity-audit",
        )

    def _row(self, job, index, name, status="verified"):
        return {
            "index": index,
            "name": name,
            "branch": "Category Theory",
            "source_urls": [],
            "status": status,
            "project_slug": self.runner._discovery_project_slug(job, index),
            "session_id": "session-%s" % index,
            "archive": str(
                self.task_dir
                / "archives"
                / job.key
                / ("%03d-%s.md" % (index, self.runner._safe_filename(name, "object")))
            ),
            "archive_sha256": self.runner._sha256_text("fixture-%s" % index),
            "verification_submissions": 1,
            "failure_stage": "",
            "last_verification": {},
            "last_error": "",
        }

    def test_discovery_state_rejects_unknown_row_status(self):
        job = self._job(target_archives=1)
        state = self.runner.load_or_create_state(job)
        state["objects"] = [self._row(job, 1, "Yoneda lemma", status="corrupted")]
        _stub_write_json(job.state_path, state)

        with self.assertRaisesRegex(self.runner.RunnerError, "unknown.*status|invalid.*status"):
            self.runner.load_or_create_state(job)

    def test_discovery_state_rejects_case_insensitive_duplicate_object_names(self):
        job = self._job(target_archives=2)
        state = self.runner.load_or_create_state(job)
        state["objects"] = [
            self._row(job, 1, "Yoneda lemma", status="failed"),
            self._row(job, 2, "yoneda LEMMA", status="verified"),
        ]
        _stub_write_json(job.state_path, state)

        with self.assertRaisesRegex(self.runner.RunnerError, "duplicate.*object|duplicate.*name"):
            self.runner.load_or_create_state(job)

    def test_discovery_state_rejects_missing_verified_archive(self):
        job = self._job(target_archives=1)
        state = self.runner.load_or_create_state(job)
        state["objects"] = [self._row(job, 1, "Yoneda lemma", status="verified")]
        _stub_write_json(job.state_path, state)

        with self.assertRaisesRegex(self.runner.RunnerError, "verified.*archive|archive.*missing"):
            self.runner.load_or_create_state(job)


if __name__ == "__main__":
    unittest.main()
