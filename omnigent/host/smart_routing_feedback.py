"""DATABRICKS-PATCH(smart-routing)

Saves the Web UI's Smart Routing feedback with the command in the user-level config.

The host runs exactly ``harness.<harness>.smart_routing.feedback_command``, so
the server never chooses what runs here. The request goes to the command as
JSON on stdin, which keeps the user's text out of process listings, and the
command answers with one JSON line once the feedback is saved. Only that
answer, or a fixed error code, goes back to the server.

Managed-only; not meant to be upstreamed.
"""

from __future__ import annotations

import asyncio
import json
import logging

from omnigent.host.frames import (
    HostSmartRoutingFeedbackFrame,
    HostSmartRoutingFeedbackResultFrame,
    SmartRoutingFeedbackSession,
)
from omnigent.host.smart_routing_entry import smart_routing_feedback_command
from omnigent.inner._proc import spawn_kwargs
from omnigent.inner._subprocess_lifecycle import terminate_subprocess

_logger = logging.getLogger(__name__)

# Saving takes about a second; the cap only bounds a stuck command.
FEEDBACK_COMMAND_TIMEOUT_S = 30.0
_STDERR_LOG_CHARS = 300


async def run_smart_routing_feedback(
    frame: HostSmartRoutingFeedbackFrame,
) -> HostSmartRoutingFeedbackResultFrame:
    """Run the configured feedback command for *frame* and relay its answer.

    Never raises: a missing command, a failed or timed-out run, and an answer
    that doesn't match the request each come back as an ``error``.
    """
    command = smart_routing_feedback_command(frame.harness)
    if command is None:
        return _error_result(frame, "no_command")
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **spawn_kwargs(),
        )
    except OSError as exc:
        _logger.warning(
            "Could not start the Smart Routing feedback command: %s", type(exc).__name__
        )
        return _error_result(frame, "failed")
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(_command_stdin(frame)), timeout=FEEDBACK_COMMAND_TIMEOUT_S
        )
    except TimeoutError:
        _logger.warning(
            "The Smart Routing feedback command ran past %.0f s", FEEDBACK_COMMAND_TIMEOUT_S
        )
        return _error_result(frame, "timeout")
    finally:
        await terminate_subprocess(
            process,
            label="Smart Routing feedback command",
            terminate_timeout=1.0,
            kill_timeout=1.0,
        )
    if process.returncode != 0:
        _logger.warning(
            "The Smart Routing feedback command exited with %s: %s",
            process.returncode,
            _last_line(stderr)[:_STDERR_LOG_CHARS],
        )
        return _error_result(frame, "failed")
    return _result_from_answer(frame, _last_line(stdout))


def _command_stdin(frame: HostSmartRoutingFeedbackFrame) -> bytes:
    request = {
        "feedback_id": frame.feedback_id,
        "message": frame.message,
        "harness": frame.harness,
        "trigger": frame.trigger,
        "session": _command_session(frame.session) if frame.session is not None else None,
    }
    return json.dumps(request).encode()


def _command_session(session: SmartRoutingFeedbackSession) -> dict[str, str | None]:
    """The session as the command reads it; a Codex session adds its private CODEX_HOME."""
    fields = {
        "native_session_id": session.native_session_id,
        "smart_routing_state": session.smart_routing_state,
    }
    if session.codex_bridge_id is not None:
        # Imported here because the server imports this module and doesn't need the Codex bridge.
        from omnigent.harnesses.codex_native.bridge import (
            bridge_dir_for_bridge_id,
            codex_home_for_bridge_dir,
        )

        bridge_dir = bridge_dir_for_bridge_id(session.codex_bridge_id)
        fields["codex_home"] = str(codex_home_for_bridge_dir(bridge_dir))
    return fields


def _result_from_answer(
    frame: HostSmartRoutingFeedbackFrame, answer_line: str
) -> HostSmartRoutingFeedbackResultFrame:
    """Accept ``saved`` with this request's feedback ID, or ``feedback_off`` with none."""
    try:
        answer = json.loads(answer_line)
    except ValueError:
        answer = None
    if isinstance(answer, dict):
        feedback_id, status = answer.get("feedback_id"), answer.get("status")
        saved = status == "saved" and feedback_id == frame.feedback_id
        feedback_off = status == "feedback_off" and feedback_id is None
        if saved or feedback_off:
            return HostSmartRoutingFeedbackResultFrame(
                frame.request_id, feedback_id=feedback_id, status=status
            )
    _logger.warning("The Smart Routing feedback command's answer does not match the request")
    return _error_result(frame, "bad_reply")


def _error_result(
    frame: HostSmartRoutingFeedbackFrame, error: str
) -> HostSmartRoutingFeedbackResultFrame:
    return HostSmartRoutingFeedbackResultFrame(frame.request_id, error=error)


def _last_line(output: bytes) -> str:
    lines = output.decode(errors="replace").strip().splitlines()
    return lines[-1] if lines else ""
