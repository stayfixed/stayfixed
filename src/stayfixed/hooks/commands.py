"""`stayfixed hook <event>`: stdin in, JSON out, the exit code owned here and event-aware."""

from __future__ import annotations

import argparse
import json
import os
import sys

from stayfixed import fsops
from stayfixed.areas import SubParsers
from stayfixed.config.loader import CONFIG_FILE, ConfigError, MachineConfigError, load
from stayfixed.config.paths import PathEscape, PathUnasked
from stayfixed.config.schema import Config
from stayfixed.harnesses import detect
from stayfixed.hooks.dispatch import dispatch, read_event
from stayfixed.hooks.policy import refuses_on_internal_error
from stayfixed.hooks.registry import discover
from stayfixed.hooks.sink import sink_for
from stayfixed.presets import load_preset

# Fixed text, never the link's target: what a link in the project's root points at is the
# repository's choice. Asked of the name itself (`is_symlink`) and before any `is_file`, which
# follows the link, so the answer does not depend on the target: followed, a link to a regular
# file would reach the loader's refusal as an internal error, and one to `/dev/zero` would read
# as no file at all.
LINKED = (
    "stayfixed: stayfixed.toml is a symbolic link, and no stayfixed command reads stayfixed.toml "
    "through one; replace the link with the file itself"
)


def _linked(event_name: str) -> int:
    """A symlinked `stayfixed.toml`: refused where an internal error refuses, open elsewhere.

    The same verdict per event as a `stayfixed.toml` that does not load, in words that name the
    rule rather than an exception; no handler runs on any event.
    """
    if refuses_on_internal_error(event_name):
        sys.stderr.write(f"{LINKED}; refused\n")
        return 2
    sys.stderr.write(f"{LINKED}; continuing open\n")
    return 0


# The verdict for a `stayfixed.toml` that is a real file and does not load: `ConfigError` for a
# value the loader refuses, `PathEscape` for a `[paths]` value that leaves the project or passes
# through a symlink — a symlinked `AGENTS.md` is one, since `agents_md` is a `[paths]` key. Both
# reached the generic handler and printed `internal error: <class>`, which reads as a stayfixed
# bug when the fault is the repository's configuration.
#
# **stayfixed's own words for the class of cause, and never the loader's message.** That message
# carries the repository's text — a `[paths]` value, a key, a value the loader refused — and a
# refused `PreToolUse` hands this stream to the model, where repository text belongs only inside
# `trust.wrap` after `stayfixed memory trust`. So the line names which kind of fault it is and the
# command that prints the detail: `stayfixed docs check` loads the same file and prints the
# loader's refusal whole, in a terminal the owner reads (`stayfixed doctor` names the file as not
# loading and points there too).
UNLOADABLE = (
    "stayfixed: stayfixed.toml does not load ({cause}); {verdict} — run `stayfixed docs check` "
    "for the detail"
)
# `ConfigError` is the loader's one class for a file it cannot read, a file that is not TOML and a
# value it refuses, so the words are true of all three.
REFUSED_VALUE = "a file or value the loader refuses"
ESCAPING_PATH = "a path that leaves the project or passes through a symlink"
UNASKED_PATH = "a path on which a directory cannot be checked for a symlink"


def _unloadable(event_name: str, cause: str) -> int:
    """The same verdict per event an internal error gets, in words that name the cause: refused
    where an internal error refuses, because an unloadable configuration is never permission."""
    refused = refuses_on_internal_error(event_name)
    verdict = "refused" if refused else "continuing open"
    sys.stderr.write(UNLOADABLE.format(cause=cause, verdict=verdict) + "\n")
    return 2 if refused else 0


def _output_cap(config: Config | None) -> int:
    """The platform cap is a shipped constant; a repository without a config still gets it."""
    if config is not None:
        return config.native_caps.hook_output_chars
    return int(load_preset("recommended")["native_caps"]["hook_output_chars"])


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
        config = None
        root = event.project_root
        document = None if root is None else root / CONFIG_FILE
        if document is not None and fsops.is_symlink(document):
            return _linked(event_name)
        if root is not None and document is not None and fsops.is_file(document):
            # `interactive=False`, said rather than sniffed. A hook's stdin is a pipe, so
            # the terminal check happens to answer the same thing — but the gate on
            # `STAYFIXED_CONFIG` and `XDG_CONFIG_HOME` is the one that decides which
            # overlay root and which `trust.json` this process reads, and it should not
            # rest on a property of how the harness happens to invoke us.
            try:
                config = load(root, interactive=False)
            except MachineConfigError:
                # The machine file's fault, not `stayfixed.toml`'s: this line would name the
                # wrong file, so it keeps the generic verdict below.
                raise
            except PathUnasked:
                return _unloadable(event_name, UNASKED_PATH)
            except PathEscape:
                return _unloadable(event_name, ESCAPING_PATH)
            except ConfigError:
                return _unloadable(event_name, REFUSED_VALUE)
        cap = _output_cap(config)
        # Keyed on the session the payload named, so `once_key` means "once per context"
        # rather than "every invocation", and a handler's failure reaches `doctor` instead of
        # being discarded. `sink_for` answers `NullSink()` whenever there is no writable data
        # directory — outside a harness, or on a read-only one — because a hook runs on every
        # tool call and a sink failure must cost a marker, never the call.
        outcome = dispatch(
            event,
            discover(),
            config,
            harness=harness,
            sink=sink_for(event.session_id, os.environ),
            cap=cap,
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
