from pathlib import Path


TARGET = Path("mathematical-concept-agent/agent.py")


def replace_between(text, start, end, replacement):
    if text.count(start) != 1:
        raise RuntimeError("expected exactly one start marker: {!r}".format(start))
    if text.count(end) != 1:
        raise RuntimeError("expected exactly one end marker: {!r}".format(end))
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[:start_index] + replacement.rstrip() + "\n\n" + text[end_index:]


text = TARGET.read_text(encoding="utf-8")

state_helpers = r'''def update_state(run_id, **changes):
    path = state_path_for(run_id)
    state = read_json(path, {})
    state.update(changes)
    state["updated_at"] = utc_now()
    atomic_write_json(path, state)
    return state


def _checkpoint_from_state(state):
    """Return the last accepted research checkpoint, including legacy state."""
    checkpoint = state.get("checkpoint")
    if isinstance(checkpoint, dict):
        turn = int(checkpoint.get("turn", 0))
        status = checkpoint.get("status", "initialized")
        if status not in {"initialized", "continue", "complete", "blocked"}:
            status = "continue" if turn > 0 else "initialized"
        skills = checkpoint.get("skills_used", [])
        if not isinstance(skills, list):
            skills = []
        return {
            "turn": turn,
            "status": status,
            "summary": str(checkpoint.get("summary", "")),
            "next_step": str(checkpoint.get("next_step", "")),
            "skills_used": [item for item in skills if isinstance(item, str)],
            "committed_at": checkpoint.get("committed_at")
            or state.get("updated_at")
            or state.get("created_at")
            or utc_now(),
        }

    raw_turn = int(state.get("turn", 0))
    # Legacy active states persisted the in-flight turn before it was accepted.
    # Recover the previous committed turn when upgrading such a state.
    if state.get("status") in ACTIVE_STATUSES and not state.get("attempt") and raw_turn > 0:
        turn = raw_turn - 1
    else:
        turn = raw_turn

    raw_status = state.get("status", "initialized")
    if raw_status in {"initialized", "continue", "complete", "blocked"}:
        status = raw_status
    elif raw_status == "paused":
        status = "continue"
    else:
        status = "continue" if turn > 0 else "initialized"
    skills = state.get("skills_used", [])
    if not isinstance(skills, list):
        skills = []
    return {
        "turn": turn,
        "status": status,
        "summary": str(state.get("summary", "")),
        "next_step": str(state.get("next_step", "")),
        "skills_used": [item for item in skills if isinstance(item, str)],
        "committed_at": state.get("updated_at") or state.get("created_at") or utc_now(),
    }


def _checkpoint_fields(checkpoint):
    """Mirror one committed checkpoint onto the public state fields."""
    return {
        "turn": int(checkpoint["turn"]),
        "summary": checkpoint.get("summary", ""),
        "next_step": checkpoint.get("next_step", ""),
        "skills_used": list(checkpoint.get("skills_used", [])),
        "checkpoint": checkpoint,
    }


def _finish_attempt(attempt, status, error=None):
    value = dict(attempt or {})
    value["status"] = status
    value["runner_pid"] = None
    value["codex_pid"] = None
    value["finished_at"] = utc_now()
    if error is not None:
        value["error"] = str(error)
    return value
'''

text = replace_between(
    text,
    "def update_state(run_id, **changes):",
    "def ensure_initialized(run_id):",
    state_helpers,
)

initialize_run = r'''def initialize_run(run_id, problem=None, prompt=None):
    run_id = validate_run_id(run_id)
    source = None
    problem_text = None
    if problem is not None:
        source = Path(problem).expanduser().resolve()
        if not source.is_file():
            raise RuntimeError("Problem file does not exist: {}".format(source))
    else:
        problem_text = prompt.strip()
        if not problem_text:
            raise RuntimeError("Inline problem prompt must not be empty")
    run_dir = run_dir_for(run_id)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise RuntimeError("Run directory already exists and is not empty: {}".format(run_dir))
    run_dir.mkdir(parents=True, exist_ok=True)
    if source is not None:
        shutil.copy2(str(source), str(run_dir / "problem.md"))
        source_problem = str(source)
    else:
        atomic_write_text(run_dir / "problem.md", problem_text)
        source_problem = "<inline prompt>"
    created_at = utc_now()
    checkpoint = {
        "turn": 0,
        "status": "initialized",
        "summary": "",
        "next_step": "",
        "skills_used": [],
        "committed_at": created_at,
    }
    atomic_write_json(
        state_path_for(run_id),
        {
            "run_id": run_id,
            "status": "initialized",
            "turn": 0,
            "session_id": None,
            "runner_pid": None,
            "codex_pid": None,
            "source_problem": source_problem,
            "summary": "",
            "next_step": "",
            "skills_used": [],
            "checkpoint": checkpoint,
            "attempt": None,
            "created_at": created_at,
            "updated_at": created_at,
        },
    )
    print("Initialized run '{}' at {}".format(run_id, run_dir))
'''

text = replace_between(
    text,
    "def initialize_run(run_id, problem=None, prompt=None):",
    "def prepare_run(args):",
    initialize_run,
)

command_run = r'''def command_run(args):
    run_id = prepare_run(args)
    continuation_prompt = getattr(args, "_continuation_prompt", None)
    stop_path = stop_path_for(run_id)
    if not args.keep_stop and stop_path.exists():
        stop_path.unlink()
    lock = acquire_lock(run_id)
    try:
        state = read_json(state_path_for(run_id), {})
        checkpoint = _checkpoint_from_state(state)
        session_id = state.get("session_id")
        previous_public_status = state.get("status", checkpoint["status"])

        # Upgrade legacy state lazily. Runtime status may change while the
        # checkpoint fields stay pinned to the last accepted research result.
        state = update_state(
            run_id,
            checkpoint=checkpoint,
            attempt=state.get("attempt"),
            **_checkpoint_fields(checkpoint)
        )

        while True:
            if stop_path.exists():
                update_state(
                    run_id,
                    status="stopped",
                    runner_pid=None,
                    codex_pid=None,
                    checkpoint=checkpoint,
                    **_checkpoint_fields(checkpoint)
                )
                print("Stop requested; run ended.")
                return 0

            previous_public_status = state.get("status", checkpoint["status"])
            attempt_turn = int(checkpoint["turn"]) + 1
            prompt = render_prompt(run_id, continuation_prompt=continuation_prompt)
            continuation_prompt = None
            command = build_codex_command(session_id, prompt)
            attempt = {
                "turn": attempt_turn,
                "status": "starting",
                "runner_pid": os.getpid(),
                "codex_pid": None,
                "started_at": utc_now(),
            }
            state = update_state(
                run_id,
                status="starting",
                runner_pid=os.getpid(),
                codex_pid=None,
                checkpoint=checkpoint,
                attempt=attempt,
                **_checkpoint_fields(checkpoint)
            )
            print("Starting Codex request for '{}'...".format(run_id), flush=True)

            active_session_id = session_id

            def remember_session_id(observed_session_id):
                nonlocal active_session_id, attempt
                if active_session_id and observed_session_id != active_session_id:
                    raise RuntimeError(
                        "Codex resumed an unexpected session: {}".format(observed_session_id)
                    )
                active_session_id = observed_session_id
                attempt = dict(attempt)
                attempt["session_id"] = observed_session_id
                update_state(
                    run_id,
                    session_id=observed_session_id,
                    attempt=attempt,
                )

            def remember_process(codex_pid):
                nonlocal attempt
                attempt = dict(attempt)
                attempt.update(
                    status="running",
                    runner_pid=os.getpid(),
                    codex_pid=codex_pid,
                )
                update_state(
                    run_id,
                    status="running",
                    runner_pid=os.getpid(),
                    codex_pid=codex_pid,
                    attempt=attempt,
                )

            try:
                return_code, stop_reason, observed_session_id, final_text = execute_turn(
                    command, stop_path, remember_session_id, remember_process
                )
                session_id = observed_session_id or active_session_id
                if stop_reason:
                    finished_attempt = _finish_attempt(
                        attempt, "stopped", "Stopped by {}".format(stop_reason)
                    )
                    update_state(
                        run_id,
                        status="stopped",
                        runner_pid=None,
                        codex_pid=None,
                        session_id=session_id,
                        checkpoint=checkpoint,
                        attempt=finished_attempt,
                        **_checkpoint_fields(checkpoint)
                    )
                    print("Run stopped by {}.".format(stop_reason))
                    return 0
                if return_code != 0:
                    message = "codex exec exited with code {}".format(return_code)
                    update_state(
                        run_id,
                        status="error",
                        runner_pid=None,
                        codex_pid=None,
                        session_id=session_id,
                        checkpoint=checkpoint,
                        attempt=_finish_attempt(attempt, "failed", message),
                        **_checkpoint_fields(checkpoint)
                    )
                    print(
                        "Codex failed with exit code {}. No automatic retry. "
                        "See {}.".format(
                            return_code, runtime_dir_for(run_id) / "codex-stderr.log"
                        )
                    )
                    return return_code or 1
                if not session_id:
                    raise RuntimeError("Codex did not report a session id")
                if final_text is None:
                    raise RuntimeError("Codex did not emit a final agent message")
                result = parse_optional_turn_result(final_text)
            except (RuntimeError, OSError) as exc:
                session_id = active_session_id
                update_state(
                    run_id,
                    status="error",
                    runner_pid=None,
                    codex_pid=None,
                    session_id=session_id,
                    checkpoint=checkpoint,
                    attempt=_finish_attempt(attempt, "failed", exc),
                    **_checkpoint_fields(checkpoint)
                )
                print("Codex run error: {}".format(exc), file=sys.stderr)
                return 1

            if result is None:
                state = update_state(
                    run_id,
                    status=previous_public_status,
                    runner_pid=None,
                    codex_pid=None,
                    session_id=session_id,
                    checkpoint=checkpoint,
                    attempt=None,
                    **_checkpoint_fields(checkpoint)
                )
                return 0

            checkpoint = {
                "turn": attempt_turn,
                "status": result["status"],
                "summary": result["summary"],
                "next_step": result["next_step"],
                "skills_used": list(result["skills_used"]),
                "committed_at": utc_now(),
            }
            state = update_state(
                run_id,
                status=result["status"],
                runner_pid=os.getpid() if result["status"] == "continue" else None,
                codex_pid=None,
                session_id=session_id,
                checkpoint=checkpoint,
                attempt=None,
                **_checkpoint_fields(checkpoint)
            )
            print("\n=== {} ===".format(TURN_STATUS_LABELS[result["status"]]), flush=True)
            print("Progress:", flush=True)
            print(result["summary"], flush=True)
            if result["skills_used"]:
                print("Skills: {}".format(", ".join(result["skills_used"])), flush=True)
            if result["next_step"]:
                print("Next step:", flush=True)
                print(result["next_step"], flush=True)

            if result["status"] != "continue":
                return 0
            if args.once:
                state = update_state(
                    run_id,
                    status="paused",
                    runner_pid=None,
                    codex_pid=None,
                    checkpoint=checkpoint,
                    attempt=None,
                    **_checkpoint_fields(checkpoint)
                )
                print("Paused after one turn (--once).")
                return 0
    finally:
        release_lock(lock)
'''

text = replace_between(
    text,
    "def command_run(args):",
    "def command_start(args):",
    command_run,
)

reconcile_state = r'''def reconcile_state(run_id, state, lock_pid, runner_alive):
    if state.get("status") not in ACTIVE_STATUSES or runner_alive:
        return state
    previous = state.get("status")
    stale_pid = state.get("runner_pid") or lock_pid
    lock_path = lock_path_for(run_id)
    if lock_path.exists() and not pid_alive(lock_pid):
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    checkpoint = _checkpoint_from_state(state)
    message = "Controller PID {} is no longer running; reconciled stale '{}' state.".format(
        stale_pid, previous
    )
    attempt = state.get("attempt")
    if not isinstance(attempt, dict):
        attempt = {
            "turn": int(checkpoint["turn"]) + 1,
            "status": previous,
            "runner_pid": state.get("runner_pid"),
            "codex_pid": state.get("codex_pid"),
            "started_at": state.get("updated_at") or utc_now(),
        }
    attempt = _finish_attempt(attempt, "interrupted", message)
    return update_state(
        run_id,
        status="error",
        runner_pid=None,
        codex_pid=None,
        checkpoint=checkpoint,
        attempt=attempt,
        **_checkpoint_fields(checkpoint)
    )
'''

text = replace_between(
    text,
    "def reconcile_state(run_id, state, lock_pid, runner_alive):",
    "def command_status(args):",
    reconcile_state,
)

TARGET.write_text(text, encoding="utf-8", newline="\n")
