from __future__ import annotations

import argparse
from pathlib import Path

from stayfixed.cli import build_parser, discover_registrars
from stayfixed.command import (
    ATTACH_CHECK_HELP,
    CHECK_HELP,
    DRY_RUN_HELP,
    HOME_HELP,
    INSTANCE_DIR_HELP,
    MACHINE_HELP,
    OVERLAY_ROOT_HELP,
    ROOT_HELP,
    SETUP_MACHINE_HELP,
    SETUP_ROOT_HELP,
    STORE_HELP,
    common_flags,
    root_and_config,
)
from tests.cli import subparsers

SHARED = {
    "--root": ROOT_HELP,
    "--machine": MACHINE_HELP,
    "--store": STORE_HELP,
    "--dry-run": DRY_RUN_HELP,
    "--home": HOME_HELP,
    "--check": CHECK_HELP,
}
# The commands that mean something else by a shared name, each with the sentence it uses. A new
# entry here is a decision, not a convenience: it says the flag means something else.
# The exceptional sentences are constants in `command.py` too (`OVERLAY_ROOT_HELP`,
# `INSTANCE_DIR_HELP`, `SETUP_ROOT_HELP`, `SETUP_MACHINE_HELP`, `ATTACH_CHECK_HELP`), so each
# is spelled once in its parser and named here — never spelled a second time by hand in a test.
EXCEPTIONS = {
    ("overlay", "create", "--root"): INSTANCE_DIR_HELP,
    ("overlay", "init", "--root"): OVERLAY_ROOT_HELP,
    ("overlay", "upgrade", "--root"): OVERLAY_ROOT_HELP,
    ("setup", None, "--root"): SETUP_ROOT_HELP,
    ("setup", None, "--machine"): SETUP_MACHINE_HELP,
    # `attach --check` reports the same way `bugs index`, `docs trail` and `memory index` do,
    # and exits differently on purpose: its 1 is a binding mismatch and not a non-empty diff.
    # `command.ATTACH_CHECK_HELP` carries the argument.
    ("attach", None, "--check"): ATTACH_CHECK_HELP,
}

CONFIG = """
[stayfixed]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""


def test_common_flags_are_root_and_machine_and_store_only_on_request() -> None:
    plain = common_flags(argparse.ArgumentParser())
    assert vars(plain.parse_args([])) == {"root": ".", "machine": None}
    with_store = common_flags(argparse.ArgumentParser(), store=True)
    assert vars(with_store.parse_args(["--store", "s"])) == {
        "root": ".",
        "machine": None,
        "store": "s",
    }


def test_root_and_config_resolves_the_root_and_loads_under_the_named_machine_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "widget"
    root.mkdir()
    (root / "stayfixed.toml").write_text(CONFIG, encoding="utf-8")
    args = common_flags(argparse.ArgumentParser()).parse_args(
        ["--root", str(root), "--machine", str(tmp_path / "m.toml")]
    )
    resolved, config = root_and_config(args)
    assert resolved == root.resolve() and config.project.name == "widget"


def _flags() -> list[tuple[str, str | None, str, str | None]]:
    """`(group, command, flag, help)` for every shared flag the real parser registers."""
    parser = build_parser(discover_registrars())
    found: list[tuple[str, str | None, str, str | None]] = []
    groups = subparsers(parser)
    assert groups is not None
    for group, sub in groups.choices.items():
        nested = subparsers(sub)
        targets: list[tuple[str | None, argparse.ArgumentParser]] = [(None, sub)] + [
            (name, inner) for name, inner in (nested.choices if nested is not None else {}).items()
        ]
        for command, target in targets:
            for flag_action in target._actions:
                for flag in flag_action.option_strings:
                    if flag in SHARED:
                        found.append((group, command, flag, flag_action.help))
    return found


def test_every_shared_flag_carries_the_one_help_string_or_a_named_exception() -> None:
    # One sentence per shared flag. `--root` and `--machine` were spelled by hand in three parsers
    # and drifted from `common_flags`' sentence, and `--home` had two sentences in two areas, one
    # saying "read" and the other "write". `--dry-run` and `--store` were each spelled once and are
    # here for the property rather than for a defect: this walk is what stops the second spelling
    # from ever being written. One constant per flag in `command.py`, and this holds every
    # occurrence to it.
    #
    # The floor is the walk's own non-emptiness, asserted before anything is filtered out of it:
    # a `_flags()` that found nothing would make the comparison below vacuously true. Measured
    # on this tree the walk finds 55 occurrences; the floor is deliberately well under that, so
    # that a command registered later does not have to edit an unrelated number.
    #
    # Mutation (declared): `common_flags`' `help=MACHINE_HELP` -> `help="machine file"` ->
    # every `--machine` diverges and this reddens listing them.
    flags = _flags()
    assert len(flags) >= 30, flags
    wrong = [
        (group, command, flag, text)
        for group, command, flag, text in flags
        if text != EXCEPTIONS.get((group, command, flag), SHARED[flag])
    ]
    assert wrong == [], wrong
