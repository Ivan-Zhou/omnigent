"""DATABRICKS-PATCH(smart-routing)

The user-level config entry behind the Web UI's Smart Routing switch: whether a
native harness is eligible, and the command that saves Smart Routing feedback.

A launcher outside Omnigent writes ``harness.<harness>.smart_routing`` into the
user-level ``config.yaml`` and removes it when the user is not eligible. The
host reads the entry on every request, so a rewritten file needs no restart.
A project's ``.omnigent/config.yaml`` can neither make a user eligible nor set
the command.

Managed-only; not meant to be upstreamed.
"""

from __future__ import annotations

import logging

from omnigent.config import load_global_config

_logger = logging.getLogger(__name__)


def is_smart_routing_eligible(harness: str) -> bool:
    """Return whether ``harness.<harness>.smart_routing.eligible`` is literally ``true``.

    ``harness`` is a canonical id such as ``"claude-native"``. Never raises: a
    missing or unreadable config, or any other entry shape, counts as not eligible.
    """
    return _smart_routing_entry(harness).get("eligible") is True


def smart_routing_feedback_command(harness: str) -> list[str] | None:
    """Return ``harness.<harness>.smart_routing.feedback_command``, the argv that saves feedback.

    Never raises: a missing or unreadable config, or anything but a non-empty
    list of strings, counts as no command.
    """
    command = _smart_routing_entry(harness).get("feedback_command")
    if isinstance(command, list) and command and all(isinstance(arg, str) for arg in command):
        return command
    return None


def _smart_routing_entry(harness: str) -> dict[str, object]:
    try:
        config = load_global_config()
    except Exception as exc:  # noqa: BLE001 - the type only: a YAML error message quotes config lines.
        _logger.warning("Could not read the user config for Smart Routing: %s", type(exc).__name__)
        return {}
    harnesses = config.get("harness") if isinstance(config, dict) else None
    entry = harnesses.get(harness) if isinstance(harnesses, dict) else None
    smart_routing = entry.get("smart_routing") if isinstance(entry, dict) else None
    return smart_routing if isinstance(smart_routing, dict) else {}
