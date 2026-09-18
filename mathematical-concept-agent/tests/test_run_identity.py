import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "agent.py"
SPEC = importlib.util.spec_from_file_location("math_concept_agent_run_identity", str(MODULE_PATH))
AGENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGENT)


class DurableRunIntentTests(unittest.TestCase):
    @staticmethod
    def _args(*, prompt=None, once=False):
        return SimpleNamespace(
            run_id="sample",
            problem=None,
            prompt=prompt,
            keep_stop=False,
            once=once,
        )

    @staticmethod
    def _complete(summary="done"):
        return json.dumps(
            {
                "status": "complete",
                "summary": summary,
                "skills_used": ["verify-mathematical-concept"],
                "next_step": "",
            }
        )

    def test_problem_mutation_is_rejected_before_codex(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "ROOT", Path(directory)
        ), mock.patch.object(
            AGENT, "build_codex_command", return_value=["codex"]
        ), mock.patch.object(
            AGENT,
            "execute_turn",
            return_value=(0, None, "session-1", self._complete()),
        ) as execute_turn:
            AGENT.initialize_run("sample", prompt="Original research problem")
            problem_path = AGENT.run_dir_for("sample") / "problem.md"
            problem_path.write_text("Tampered research problem\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "problem.*changed|problem.*identity"):
                AGENT.command_run(self._args())

            execute_turn.assert_not_called()

    def test_failed_continuation_is_replayed_on_restart_without_reprompt(self):
        prompts = []

        def build_command(session_id, prompt, config=None):
            prompts.append((session_id, prompt))
            return ["codex"]

        def fail_turn(command, stop_path, on_session_id=None, on_started=None):
            if on_started:
                on_started(4321)
            if on_session_id:
                on_session_id("session-1")
            raise OSError("simulated controller failure")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "ROOT", Path(directory)
        ), mock.patch.object(
            AGENT, "build_codex_command", side_effect=build_command
        ):
            AGENT.initialize_run("sample", prompt="Original research problem")

            with mock.patch.object(AGENT, "execute_turn", side_effect=fail_turn):
                self.assertEqual(
                    AGENT.command_run(self._args(prompt="Inspect the boundary case")),
                    1,
                )

            with mock.patch.object(
                AGENT,
                "execute_turn",
                return_value=(0, None, "session-1", self._complete("recovered")),
            ):
                self.assertEqual(AGENT.command_run(self._args()), 0)

            self.assertEqual(len(prompts), 2)
            self.assertIn("Inspect the boundary case", prompts[0][1])
            self.assertIn("Inspect the boundary case", prompts[1][1])
            self.assertEqual(prompts[1][0], "session-1")

    def test_failed_attempt_binds_the_problem_identity(self):
        def fail_turn(command, stop_path, on_session_id=None, on_started=None):
            if on_started:
                on_started(4321)
            raise OSError("simulated controller failure")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "ROOT", Path(directory)
        ), mock.patch.object(
            AGENT, "build_codex_command", return_value=["codex"]
        ), mock.patch.object(
            AGENT, "execute_turn", side_effect=fail_turn
        ):
            AGENT.initialize_run("sample", prompt="Original research problem")
            self.assertEqual(
                AGENT.command_run(self._args(prompt="Inspect the boundary case")),
                1,
            )

            state = AGENT.read_json(AGENT.state_path_for("sample"), {})
            self.assertTrue(state.get("problem_sha256"))
            self.assertEqual(
                state["attempt"]["problem_sha256"],
                state["problem_sha256"],
            )
            self.assertEqual(
                state["attempt"]["continuation_prompt"],
                "Inspect the boundary case",
            )

    def test_explicit_new_continuation_overrides_failed_pending_intent(self):
        prompts = []

        def build_command(session_id, prompt, config=None):
            prompts.append(prompt)
            return ["codex"]

        def fail_turn(command, stop_path, on_session_id=None, on_started=None):
            raise OSError("simulated controller failure")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "ROOT", Path(directory)
        ), mock.patch.object(
            AGENT, "build_codex_command", side_effect=build_command
        ):
            AGENT.initialize_run("sample", prompt="Original research problem")
            with mock.patch.object(AGENT, "execute_turn", side_effect=fail_turn):
                self.assertEqual(
                    AGENT.command_run(self._args(prompt="Old continuation")),
                    1,
                )

            with mock.patch.object(
                AGENT,
                "execute_turn",
                return_value=(0, None, "session-1", self._complete()),
            ):
                self.assertEqual(
                    AGENT.command_run(self._args(prompt="New continuation")),
                    0,
                )

            self.assertIn("Old continuation", prompts[0])
            self.assertIn("New continuation", prompts[1])
            self.assertNotIn("Old continuation", prompts[1])


if __name__ == "__main__":
    unittest.main()
