"""`stayfixed hook <event>`: stdin in, JSON out, the exit code owned here and event-aware."""

from __future__ import annotations

import argparse
import json
import os
import sys

from stayfixed.areas import SubParsers
from stayfixed.config.schema import Config
from stayfixed.config.session import session_config
from stayfixed.harnesses import detect
from stayfixed.hooks.api import Sink
from stayfixed.hooks.dispatch import NOTICE_EVENT, dispatch, read_event
from stayfixed.hooks.policy import refuses_on_internal_error
from stayfixed.hooks.registry import discover
from stayfixed.hooks.sink import sink_for
from stayfixed.presets import DEFAULT_PRESET, load_preset

# What the sink records, once per session, for a session whose configuration did not load whole,
# on an event that does not show the notice: the marker key and the record's `error`. Fixed text
# and never a warning's words, which `doctor` would not quote anyway (`checks._diagnostics`).
CONFIG_FALLBACK = "config-fallback"


def _output_cap(config: Config | None) -> int:
    """The platform cap is a shipped constant; a repository without a config still gets it."""
    if config is not None:
        return config.native_caps.hook_output_chars
    return int(load_preset(DEFAULT_PRESET)["native_caps"]["hook_output_chars"])


def _log_fallback(event_name: str, sink: Sink) -> None:
    """Record, once per session, that this session runs without some of its configuration: the
    notice is shown on `SessionStart` alone, and a tool call says nothing of it, so the sink is
    where `doctor` finds that it happened."""
    if sink.seen(CONFIG_FALLBACK):
        return
    sink.diagnostic({"event": event_name, "handler": "*", "error": CONFIG_FALLBACK})
    sink.mark(CONFIG_FALLBACK)


def run_hook(args: argparse.Namespace) -> int:
    event_name = str(args.event)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        # argv is authoritative: the wrapper controls it, while stdin is the untrusted side.
        payload["hook_event_name"] = event_name
        harness = detect(os.environ, payload)
        event = read_event(payload, os.environ)
        # Never raises for what the repository or the machine file holds (`config.session`), so a
        # configuration that does not load is never why a call is refused: the guards run on the
        # preset and the owner's layer, and the session hears why once, on `SessionStart`. The
        # machine file is the one no variable moves (`config.machine`), so which overlay root and
        # which `trust.json` this process reads rests on no property of how the harness happens
        # to invoke us.
        session = session_config(event.project_root)
        # Keyed on the session the payload named, so `once_key` means "once per context"
        # rather than "every invocation", and a handler's failure reaches `doctor` instead of
        # being discarded. `sink_for` answers `NullSink()` whenever there is no writable data
        # directory — outside a harness, or on a read-only one — because a hook runs on every
        # tool call and a sink failure must cost a marker, never the call.
        sink = sink_for(event.session_id, os.environ)
        if session.warnings and event_name != NOTICE_EVENT:
            _log_fallback(event_name, sink)
        outcome = dispatch(
            event,
            discover(),
            session,
            harness=harness,
            sink=sink,
            cap=_output_cap(session.config),
        )
    except BaseException as exc:  # an internal error must never read as permission
        reason = f"stayfixed: internal error: {type(exc).__name__}: {exc}"
        if refuses_on_internal_error(event_name):
            sys.stderr.write(f"{reason}; refused\n")
            return 2
        sys.stderr.write(f"{reason}; continuing open\n")
        return 0
    if outcome.stdout:
        sys.stdout.write(outcome.stdout)
    if outcome.stderr:
        sys.stderr.write(outcome.stderr)
    return outcome.exit_code


def register(groups: SubParsers) -> None:
    group = groups.add_parser("hook", help="dispatch one harness hook event (internal)")
    group.add_argument("event", help="hook event name, e.g. SessionStart")
    group.set_defaults(func=run_hook)
