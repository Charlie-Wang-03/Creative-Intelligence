"""Regression coverage for immutable local-material provenance.

This module reuses the offline import harness from ``test_run_archive_offline``
so the contract remains deterministic and requires no Moonshine runtime, API
credentials, network access, or model calls.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import test_run_archive_offline as harness


class MaterialProvenanceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner, cls._module_patcher = harness._load_runner_module()

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(harness.RUNNER_MODULE_NAME, None)
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

    def test_state_rejects_material_content_mutation_after_run_started(self):
        inputs = self.temp_root / "inputs"
        inputs.mkdir()
        material = inputs / "notes.md"
        material.write_text("original source material\n", encoding="utf-8")
        queue_path = inputs / "queue.json"
        queue_path.write_text(
            json.dumps(
                {
                    "format": self.runner.FORMAT_ID,
                    "language": "en",
                    "objects": [
                        {
                            "name": "Bochner formula",
                            "materials": ["notes.md"],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        first_job = self.runner.load_job(queue_path)
        state = self.runner.load_or_create_state(first_job)
        self.assertEqual(state["status"], "pending")
        self.assertTrue(first_job.state_path.exists())

        material.write_text("mutated source material\n", encoding="utf-8")
        resumed_job = self.runner.load_job(queue_path)

        with self.assertRaisesRegex(
            self.runner.RunnerError,
            "material content changed after this run started",
        ):
            self.runner.load_or_create_state(resumed_job)


if __name__ == "__main__":
    unittest.main()
