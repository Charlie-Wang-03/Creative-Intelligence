import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "agent.py"
SPEC = importlib.util.spec_from_file_location("math_concept_agent", str(MODULE_PATH))
AGENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGENT)


class AgentFrameworkTests(unittest.TestCase):
    def test_config_is_framework_local_and_invocation_only(self):
        self.assertEqual(AGENT.CONFIG_PATH, MODULE_PATH.parent / "config.toml")
        config_text = AGENT.CONFIG_PATH.read_text(encoding="utf-8")
        self.assertIn('model = "gpt-5.6-sol"', config_text)
        self.assertIn('model_reasoning_effort = "max"', config_text)

        args = AGENT.temporary_config_args(
            {"model": "test-model", "agents": {"enabled": True}}
        )
        self.assertIn('model="test-model"', args)
        self.assertIn("agents.enabled=true", args)

    def test_command_applies_temporary_config(self):
        command = AGENT.build_codex_command(
            None,
            "do work",
            {"model": "test-model", "model_reasoning_effort": "high"},
        )
        self.assertIn('model="test-model"', command)
        self.assertIn('model_reasoning_effort="high"', command)
        self.assertNotIn("--output-schema", command)
        self.assertNotIn("--ephemeral", command)
        self.assertIn("--json", command)
        self.assertIn("--strict-config", command)

    def test_resume_command_uses_saved_session(self):
        command = AGENT.build_codex_command("session-123", "continue", {})
        self.assertIn("resume", command)
        self.assertIn("session-123", command)

    def test_only_state_is_persistent_controller_file_at_run_root(self):
        run_dir = AGENT.run_dir_for("sample")
        self.assertEqual(AGENT.state_path_for("sample"), run_dir / "state.json")
        self.assertEqual(AGENT.runtime_dir_for("sample"), run_dir / ".runtime")

    def test_run_id_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            AGENT.validate_run_id("../outside")

    def test_prepare_run_initializes_once_and_then_resumes(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "ROOT", Path(directory)
        ):
            new_run = SimpleNamespace(
                run_id="sample", problem=None, prompt="Study this structure."
            )
            self.assertEqual(AGENT.prepare_run(new_run), "sample")
            self.assertEqual(
                (Path(directory) / "runs" / "sample" / "problem.md").read_text(
                    encoding="utf-8"
                ).strip(),
                "Study this structure.",
            )

            resume = SimpleNamespace(run_id="sample", problem=None, prompt=None)
            self.assertEqual(AGENT.prepare_run(resume), "sample")

            continuation = SimpleNamespace(
                run_id="sample", problem=None, prompt="Continue with a counterexample."
            )
            self.assertEqual(AGENT.prepare_run(continuation), "sample")
            self.assertEqual(
                continuation._continuation_prompt,
                "Continue with a counterexample.",
            )
            self.assertEqual(
                (Path(directory) / "runs" / "sample" / "problem.md").read_text(
                    encoding="utf-8"
                ).strip(),
                "Study this structure.",
            )

            with self.assertRaises(RuntimeError):
                AGENT.prepare_run(
                    SimpleNamespace(run_id="sample", problem="other.md", prompt=None)
                )

    def test_continuation_prompt_is_added_without_replacing_problem(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "ROOT", Path(directory)
        ):
            AGENT.initialize_run("sample", prompt="Original research problem.")
            args = SimpleNamespace(
                run_id="sample", problem=None, prompt="Use five parallel subagents."
            )
            AGENT.prepare_run(args)

            rendered = AGENT.render_prompt(
                "sample", continuation_prompt=args._continuation_prompt
            )
            self.assertIn("Use five parallel subagents.", rendered)
            self.assertIn("CONTINUATION INSTRUCTION BEGIN", rendered)
            self.assertIn("Current research run: `sample`", rendered)
            self.assertNotIn("research-status JSON", rendered)
            agents_text = AGENT.AGENTS_PATH.read_text(encoding="utf-8")
            self.assertIn("asks to advance the research", agents_text)
            self.assertIn('"status":"continue|complete|blocked"', agents_text)
            self.assertEqual(
                (Path(directory) / "runs" / "sample" / "problem.md").read_text(
                    encoding="utf-8"
                ).strip(),
                "Original research problem.",
            )

    def test_run_and_start_accept_problem_source_for_new_run(self):
        parser = AGENT.build_parser()
        inline = parser.parse_args(["run", "sample", "--prompt", "Study this structure."])
        self.assertEqual(inline.prompt, "Study this structure.")
        self.assertIsNone(inline.problem)

        file_input = parser.parse_args(["start", "sample", "--problem", "problem.md"])
        self.assertEqual(file_input.problem, "problem.md")
        self.assertIsNone(file_input.prompt)

        resume = parser.parse_args(["run", "sample"])
        self.assertIsNone(resume.problem)
        self.assertIsNone(resume.prompt)

        with self.assertRaises(SystemExit):
            parser.parse_args(
                ["run", "sample", "--problem", "problem.md", "--prompt", "text"]
            )

        with self.assertRaises(SystemExit):
            parser.parse_args(["init", "sample", "--prompt", "text"])

    def test_steering_command_is_not_exposed(self):
        with self.assertRaises(SystemExit):
            AGENT.build_parser().parse_args(
                ["steer", "sample", "--prompt", "change direction"]
            )

    def test_parse_turn_result(self):
        result = AGENT.parse_turn_result(
            json.dumps(
                {
                    "status": "continue",
                    "summary": "Saved a useful lemma.",
                    "skills_used": ["construct-mathematical-concept"],
                    "next_step": "Test the lemma on boundary cases.",
                }
            )
        )
        self.assertEqual(result["status"], "continue")

        self.assertIsNone(AGENT.parse_optional_turn_result("ordinary response"))
        self.assertIsNone(
            AGENT.parse_optional_turn_result(json.dumps({"answer": "ordinary JSON"}))
        )

    def test_parse_session_and_final_message_events(self):
        session_id, final_text = AGENT.parse_codex_event(
            '{"type":"thread.started","thread_id":"session-123"}'
        )
        self.assertEqual(session_id, "session-123")
        self.assertIsNone(final_text)

        session_id, final_text = AGENT.parse_codex_event(
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"{\\"status\\":\\"complete\\"}"}}'
        )
        self.assertIsNone(session_id)
        self.assertEqual(final_text, '{"status":"complete"}')

    def test_formats_live_progress_events(self):
        command = AGENT.codex_progress_message(
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": "rg --files",
                    "status": "in_progress",
                },
            }
        )
        self.assertEqual(command, "TOOL | STARTED | PowerShell | List files")
        self.assertNotIn("rg --files", command)

        read_file = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "Get-Content -Raw -LiteralPath 'secret/report.md'",
                },
            }
        )
        self.assertEqual(
            read_file, "TOOL | COMPLETED | PowerShell | Read file | secret/report.md"
        )

        positional_read = AGENT.codex_progress_message(
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": "Get-Content -Encoding utf8 runs\\sample\\state.json | Select-Object -Last 5",
                },
            }
        )
        self.assertEqual(
            positional_read,
            "TOOL | STARTED | PowerShell | Read file | runs\\sample\\state.json",
        )

        variable_read = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "$p = 'runs\\sample\\research\\construction-progress.md'; Get-Content -Raw -LiteralPath $p",
                },
            }
        )
        self.assertEqual(
            variable_read,
            "TOOL | COMPLETED | PowerShell | Read file | runs\\sample\\research\\construction-progress.md",
        )

        unresolved_variable = AGENT.codex_progress_message(
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": "Get-Content -LiteralPath $p",
                },
            }
        )
        self.assertEqual(
            unresolved_variable,
            "TOOL | STARTED | PowerShell | Read file",
        )

        stray_quote = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": 'Get-Content -LiteralPath "',
                },
            }
        )
        self.assertEqual(stray_quote, "TOOL | COMPLETED | PowerShell | Read file")

        argv_read = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": [
                        "pwsh.exe",
                        "-Command",
                        "$c=Get-Content -LiteralPath 'runs\\sample\\research\\candidate.md' -Encoding utf8",
                    ],
                },
            }
        )
        self.assertEqual(
            argv_read,
            "TOOL | COMPLETED | PowerShell | Read file | runs\\sample\\research\\candidate.md",
        )

        list_path = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "Get-ChildItem -LiteralPath 'runs\\sample\\research' -File",
                },
            }
        )
        self.assertEqual(
            list_path,
            "TOOL | COMPLETED | PowerShell | List files | runs\\sample\\research",
        )

        write_path = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "Set-Content -LiteralPath 'runs\\sample\\note.md' -Value $text",
                },
            }
        )
        self.assertEqual(
            write_path,
            "TOOL | COMPLETED | PowerShell | Modify files | runs\\sample\\note.md",
        )

        subagent = AGENT.codex_progress_message(
            {
                "type": "item.started",
                "item": {
                    "type": "collab_agent_tool_call",
                    "tool": "spawn_agent",
                    "task_name": "direction_1",
                },
            }
        )
        self.assertEqual(subagent, "TOOL | STARTED | Agent tool | spawn_agent")
        self.assertNotIn("direction_1", subagent)

        self.assertIsNone(
            AGENT.codex_progress_message({"type": "token_count", "usage": {}})
        )

    def test_agent_message_progress_is_not_truncated(self):
        full_text = "visible progress " + "x" * 500
        message = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": full_text},
            }
        )
        self.assertIn(full_text, message)
        self.assertTrue(message.startswith("MESSAGE | COMPLETED\n"))
        self.assertGreater(len(message), 500)

    def test_structured_turn_result_is_not_printed_twice(self):
        full_text = json.dumps(
            {
                "status": "continue",
                "summary": "Saved a useful lemma.",
                "skills_used": ["construct-mathematical-concept"],
                "next_step": "Verify boundary cases.",
            }
        )
        message = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": full_text},
            }
        )
        self.assertIsNone(message)
        self.assertEqual(
            AGENT.TURN_STATUS_LABELS["continue"],
            "RESEARCH CONTINUES",
        )

    def test_reasoning_summary_is_shown_in_full(self):
        full_summary = (
            "First line\nSecond line\n"
            + "x" * 500
        )
        message = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {"type": "reasoning", "summary": full_summary},
            }
        )
        self.assertEqual(message, "REASONING | COMPLETED\n" + full_summary)

    def test_formats_other_event_types_clearly(self):
        file_change = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "file_change",
                    "status": "completed",
                    "changes": [
                        {"path": "research/progress.md", "kind": "update"},
                        {"path": "research/candidate.md", "kind": "create"},
                    ],
                },
            }
        )
        self.assertEqual(
            file_change,
            "TOOL | COMPLETED | File change | research/progress.md, research/candidate.md",
        )

        failed_command = AGENT.codex_progress_message(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "pytest",
                    "status": "failed",
                },
            }
        )
        self.assertEqual(
            failed_command, "TOOL | COMPLETED | PowerShell | Run tests | FAILED"
        )

        web_search = AGENT.codex_progress_message(
            {
                "type": "item.started",
                "item": {"type": "web_search", "query": "Gale duality"},
            }
        )
        self.assertEqual(
            web_search, "TOOL | STARTED | Web search | Gale duality"
        )

        usage = AGENT.codex_progress_message(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 80,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 10,
                },
            }
        )
        self.assertEqual(
            usage,
            "REQUEST | COMPLETED | input 100, cached 80, output 20, reasoning 10",
        )

        self.assertEqual(
            AGENT.codex_progress_message({"type": "future.event"}),
            "EVENT | future.event",
        )

    def test_progress_renderer_coalesces_tools_and_preserves_text(self):
        now = [10.0]
        renderer = AGENT.ProgressRenderer(
            long_tool_seconds=2.0, clock=lambda: now[0]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            renderer.handle(
                {
                    "type": "item.started",
                    "item": {
                        "id": "short",
                        "type": "command_execution",
                        "command": "Get-Content runs\\sample\\problem.md",
                    },
                }
            )
            now[0] = 10.4
            renderer.handle(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "short",
                        "type": "command_execution",
                        "command": "Get-Content runs\\sample\\problem.md",
                        "status": "completed",
                    },
                }
            )
            renderer.handle(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "reasoning",
                        "text": "line one\nline two",
                    },
                }
            )
            renderer.handle(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": "complete\nmodel message",
                    },
                }
            )

        rendered = output.getvalue()
        self.assertEqual(rendered.count("Read file"), 1)
        self.assertIn("problem.md | 0.4s", rendered)
        self.assertIn("REASONING | COMPLETED\nline one\nline two", rendered)
        self.assertIn("MESSAGE | COMPLETED\ncomplete\nmodel message", rendered)

    def test_progress_renderer_reports_long_and_interrupted_tools(self):
        now = [20.0]
        renderer = AGENT.ProgressRenderer(
            long_tool_seconds=2.0, clock=lambda: now[0]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            renderer.handle(
                {
                    "type": "item.started",
                    "item": {
                        "id": "long",
                        "type": "command_execution",
                        "command": "pytest",
                    },
                }
            )
            now[0] = 22.1
            renderer.flush_long_running()
            now[0] = 23.0
            renderer.handle(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "long",
                        "type": "command_execution",
                        "command": "pytest",
                        "status": "completed",
                    },
                }
            )
            renderer.handle(
                {
                    "type": "item.started",
                    "item": {
                        "id": "stuck",
                        "type": "web_search",
                        "query": "open problem",
                    },
                }
            )
            now[0] = 24.0
            renderer.finish()

        rendered = output.getvalue()
        self.assertIn("TOOL | RUNNING | PowerShell | Run tests", rendered)
        self.assertIn("TOOL | COMPLETED | PowerShell | Run tests | 3.0s", rendered)
        self.assertIn(
            "TOOL | INTERRUPTED | Web search | open problem | 1.0s", rendered
        )

    def test_execute_turn_separates_stderr_from_progress(self):
        event = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "visible message"},
            }
        )
        script = (
            "import sys; "
            "print({!r}); "
            "print('hidden diagnostic', file=sys.stderr)"
        ).format(event)
        with tempfile.TemporaryDirectory() as directory:
            stop_path = Path(directory) / ".runtime" / "STOP"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                return_code, stop_reason, _, final_text = AGENT.execute_turn(
                    [sys.executable, "-c", script], stop_path
                )

            self.assertEqual(return_code, 0)
            self.assertIsNone(stop_reason)
            self.assertEqual(final_text, "visible message")
            self.assertIn("MESSAGE | COMPLETED\nvisible message", output.getvalue())
            self.assertNotIn("hidden diagnostic", output.getvalue())
            self.assertIn(
                "hidden diagnostic",
                (stop_path.parent / "codex-stderr.log").read_text(encoding="utf-8"),
            )

    def test_plain_response_preserves_research_progress(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "ROOT", Path(directory)
        ):
            run_dir = AGENT.run_dir_for("sample")
            run_dir.mkdir(parents=True)
            (run_dir / "problem.md").write_text("Research problem", encoding="utf-8")
            AGENT.atomic_write_json(
                AGENT.state_path_for("sample"),
                {
                    "run_id": "sample",
                    "status": "paused",
                    "turn": 7,
                    "session_id": "session-old",
                    "runner_pid": None,
                    "codex_pid": None,
                    "summary": "Established result",
                    "next_step": "Prove the main theorem",
                    "skills_used": ["construct-mathematical-concept"],
                },
            )
            args = SimpleNamespace(
                run_id="sample",
                problem=None,
                prompt="Explain the result without continuing research.",
                keep_stop=False,
                once=False,
            )
            with mock.patch.object(
                AGENT, "build_codex_command", return_value=["codex"]
            ), mock.patch.object(
                AGENT,
                "execute_turn",
                return_value=(0, None, "session-old", "Ordinary explanation"),
            ):
                result = AGENT.command_run(args)

            self.assertEqual(result, 0)
            state = AGENT.read_json(AGENT.state_path_for("sample"), {})
            self.assertEqual(state["status"], "paused")
            self.assertEqual(state["turn"], 7)
            self.assertEqual(state["summary"], "Established result")
            self.assertEqual(state["next_step"], "Prove the main theorem")
            self.assertEqual(
                state["skills_used"], ["construct-mathematical-concept"]
            )
            self.assertIsNone(state["runner_pid"])
            self.assertIsNone(state["codex_pid"])

    def test_stale_running_state_is_reconciled(self):
        stale = {"status": "running", "runner_pid": 999999}
        repaired = {**stale, "status": "error", "runner_pid": None}
        with mock.patch.object(AGENT, "update_state", return_value=repaired) as update:
            result = AGENT.reconcile_state("sample", stale, None, False)
        self.assertEqual(result["status"], "error")
        update.assert_called_once()

    def test_background_start_waits_until_runner_and_codex_are_running(self):
        class FakeProcess:
            pid = 4321

            @staticmethod
            def poll():
                return None

        args = SimpleNamespace(
            run_id="sample", _continuation_prompt="Use five parallel subagents."
        )
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            AGENT, "prepare_run", return_value="sample"
        ), mock.patch.object(
            AGENT, "runtime_dir_for", return_value=Path(directory)
        ), mock.patch.object(
            AGENT, "read_lock_pid", side_effect=[None, 4321, 4321]
        ), mock.patch.object(
            AGENT, "pid_alive", return_value=False
        ), mock.patch.object(
            AGENT,
            "read_json",
            side_effect=[
                {"status": "starting", "runner_pid": 4321},
                {"status": "running", "runner_pid": 4321},
            ],
        ) as read_state, mock.patch.object(
            AGENT.subprocess, "Popen", return_value=FakeProcess()
        ) as popen, mock.patch.object(
            AGENT.time, "sleep"
        ):
            result = AGENT.command_start(args)
        self.assertEqual(result, 0)
        self.assertEqual(read_state.call_count, 2)
        child_command = popen.call_args.args[0]
        self.assertEqual(
            child_command[-2:], ["--prompt", "Use five parallel subagents."]
        )


if __name__ == "__main__":
    unittest.main()
