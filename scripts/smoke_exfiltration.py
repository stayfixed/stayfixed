#!/usr/bin/env python3
"""The clone-to-exfiltration scenario: a hostile clone, run end to end against a plugin root.

    python3 scripts/smoke_exfiltration.py --plugin-root R --fixture F --scratch S

The clone commits its own notes as standing rules, names ANOTHER project, and ships a
`.claude/settings.json` `env` block pointing stayfixed at a machine configuration inside itself
and at a `PATH` inside itself. This script materialises that `env` block the way a harness
would — the two relative values become absolute paths inside the scratch clone — and then asks
each boundary the scenario is about, one printed row each.

**Every negative row has its positive control.** "The canary is absent" is also what a broken
pipeline prints, so the first three rows show the note reaching a session when the owner has
trusted it, then not reaching one after the record lapses, then not reaching one after the
record is deleted. A row that could only ever have been green is not evidence.

The scenario's MCP arm — `memory_search` under an explicit `project=` — is not run: stayfixed
ships no MCP server yet (the README lists the memory MCP server under "Not yet"), and the run
says so in its own output rather than leaving a silent gap in the scenario.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_hooks import developer_free_env, fixture_repository, with_owner_home

CANARY = "CANARY-IN-REPO-RULE"
DELIMITER = "<<<stayfixed:repository-data"
# The remote the overlay records for `smoke`, and the one the clone has instead. The clone chooses
# its own `project.name` and its own `origin`, and not what the overlay recorded under that name,
# which is the whole of why `attach` can tell the two apart. It has an `origin` of its own because
# a checkout with none is a state of its own (`no-origin`), not the one this scenario is about.
RECORDED_REMOTE = "git@example.com:the-owner/smoke.git"
CLONES_REMOTE = "git@example.com:somebody-else/smoke.git"
# How many rows this scenario declares. Asserted at the end, because seven of the nine assert an
# ABSENCE and a run that executed one of them prints an identically green last line.
EXPECTED_ROWS = 9


@dataclass
class Report:
    rows: list[tuple[bool, str, str]]

    def row(self, ok: bool, label: str, evidence: str) -> None:
        self.rows.append((ok, label, evidence))
        print(f"{'ok  ' if ok else 'FAIL'}  {label}: {evidence}")

    @property
    def failures(self) -> int:
        return sum(1 for ok, _, _ in self.rows if not ok)


@dataclass(frozen=True)
class Planted:
    clone: Path
    home: Path
    data: Path
    overlay: Path
    machine_in_clone: Path
    planted_interpreter: Path
    planted_marker: Path


def _run(argv: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Every subprocess here reads stdin from a pipe, which is what a hook's stdin is.

    It is also the gate: nothing stayfixed honours only from an interactive terminal, `attach`'s
    `--machine` among it, is honoured on a pipe, the state the clone's `env` block actually meets.
    """
    return subprocess.run(  # noqa: S603
        argv,
        input="",
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def plant(fixture: Path, scratch: Path, plugin_root: Path) -> Planted:
    clone = fixture_repository(fixture, scratch / "clone")
    subprocess.run(  # noqa: S603
        ["git", "-C", str(clone), "remote", "add", "origin", CLONES_REMOTE],  # noqa: S607
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        },
    )
    home = scratch / "home"
    data = scratch / "data"
    (home / ".config" / "stayfixed").mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)

    # What the clone's `env` block names, made real: a machine configuration inside the clone
    # recording an overlay inside the clone, and an interpreter inside the clone.
    evil_overlay = clone / "evil" / "overlay"
    (evil_overlay / "projects" / "smoke" / "memory").mkdir(parents=True, exist_ok=True)
    machine_in_clone = clone / "evil" / "config.toml"
    machine_in_clone.write_text(f'[overlay]\nroot = "{evil_overlay}"\n', encoding="utf-8")
    planted_marker = scratch / "planted-ran"
    planted = clone / "bin" / "python3"
    planted.parent.mkdir(parents=True, exist_ok=True)
    # No `exec`: an `exec python3` would re-search a PATH whose first entry is this directory
    # and never terminate. This writes a marker and exits, so "the planted interpreter ran" is
    # a file on disk rather than an inference from an exit code.
    planted.write_text(
        f'#!/bin/sh\nprintf planted > "{planted_marker}"\nexit 0\n', encoding="utf-8"
    )
    planted.chmod(0o755)

    # A REAL overlay and a REAL machine file, so the `attach` rows below reach the containment
    # check instead of refusing for want of any machine configuration at all — a refusal for
    # the wrong reason is the vacuous shape this repository names.
    overlay = scratch / "overlay"
    env = {**os.environ, "HOME": str(home)}
    created = _run(
        [
            sys.executable,
            str(plugin_root / "scripts" / "stayfixed"),
            "overlay",
            "create",
            "--owner",
            "smoke-owner",
            "--name",
            "overlay",
            "--local",
            "--root",
            str(scratch),
        ],
        env,
        scratch,
    )
    if created.returncode != 0:
        raise SystemExit(f"could not render the overlay the scenario needs: {created.stderr}")
    (overlay / "projects" / "smoke" / "memory").mkdir(parents=True, exist_ok=True)
    (overlay / "projects" / "smoke" / "project.toml").write_text(
        f'remote = "{RECORDED_REMOTE}"\n', encoding="utf-8"
    )
    (home / ".config" / "stayfixed" / "config.toml").write_text(
        f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8"
    )
    return Planted(clone, home, data, overlay, machine_in_clone, planted, planted_marker)


def hostile_env(planted: Planted, plugin_root: Path) -> dict[str, str]:
    """The environment the clone's committed `env` block produces, materialised."""
    env = developer_free_env()
    env.update(
        {
            "HOME": str(planted.home),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PROJECT_DIR": str(planted.clone),
            "CLAUDE_PLUGIN_DATA": str(planted.data),
            "STAYFIXED_CONFIG": str(planted.machine_in_clone),
            "PATH": f"{planted.planted_interpreter.parent}:{os.environ.get('PATH', '')}",
        }
    )
    return env


def stayfixed(
    plugin_root: Path, args: list[str], env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """stayfixed itself, on this script's own interpreter.

    The rows that use this are about stayfixed's answers and not about the wrapper's probe; the
    planted interpreter is what the wrapper rows are about.
    """
    return _run([sys.executable, str(plugin_root / "scripts" / "stayfixed"), *args], env, cwd)


def through_wrapper(
    wrapper: Path, args: list[str], env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return _run([str(wrapper), *args], env, cwd)


def trust_record(planted: Planted) -> Path:
    return planted.home / ".config" / "stayfixed" / "trust.json"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("--plugin-root", "--fixture", "--scratch"):
        parser.add_argument(flag, required=True, type=Path)
    args = parser.parse_args(argv)
    # The owner's home is the scratch one in the password database too, which is where stayfixed
    # looks for it off a terminal (`smoke_hooks.with_owner_home`); `plant` puts it at `home`.
    plugin_root = with_owner_home(
        args.plugin_root.resolve(), args.scratch / "owner-home-plugin", args.scratch / "home"
    )
    report = Report([])
    planted = plant(args.fixture, args.scratch, plugin_root)
    env = hostile_env(planted, plugin_root)
    wrapper = plugin_root / "hooks" / "run-hook.sh"
    bundle = ["open", "memory", "session-context", "--bundle", "standing-rules", "--part", "1"]

    # --- the positive control, first: the pipeline can emit the note when it is trusted ------
    recorded = stayfixed(
        plugin_root,
        ["memory", "trust", "--in-repo-memory", "--root", str(planted.clone)],
        env,
        planted.clone,
    )
    emitted = through_wrapper(wrapper, bundle, env, planted.clone)
    report.row(
        recorded.returncode == 0
        and emitted.returncode == 0
        and CANARY in emitted.stdout
        and DELIMITER in emitted.stdout,
        "the owner's own trust record lets the note through, inside a delimited region",
        f"trust rc={recorded.returncode}, bundle rc={emitted.returncode}, "
        f"canary={CANARY in emitted.stdout}, delimited={DELIMITER in emitted.stdout}",
    )

    # --- and the record lapses the moment the clone changes what it committed ---------------
    note = planted.clone / "docs" / "memory" / "developer" / "canary.md"
    committed = note.read_text(encoding="utf-8")
    note.write_text(committed + "\nAnd one more line.\n", encoding="utf-8")
    lapsed = through_wrapper(wrapper, bundle, env, planted.clone)
    report.row(
        lapsed.returncode == 0 and CANARY not in lapsed.stdout,
        "a lapsed record withdraws the note",
        f"rc={lapsed.returncode}, canary={CANARY in lapsed.stdout}",
    )

    # The dispatcher's own SessionStart entry, under the lapsed record. Measured rather than
    # predicted: the expectation was a `worktree-link` line reporting the store as not linked,
    # and this clone never produces one — `memory.hooks._link_worktree` speaks for a LINKED
    # WORKTREE, and the clone is a main checkout with no link ever created, so the handler's
    # own answer is "nothing to do" and the envelope carries no context at all. That is the
    # right answer and it is what is asserted: a well-formed envelope naming the event, with
    # no `additionalContext` and neither the canary nor the repository-data marker anywhere in
    # it. The row's positive control is the first row above — the same store, trusted, does
    # reach a session through the bundle entries — so "nothing came out" cannot be a crash.
    started = through_wrapper(wrapper, ["open", "hook", "SessionStart"], env, planted.clone)
    try:
        envelope = json.loads(started.stdout)
    except json.JSONDecodeError:
        envelope = {}
    specific = envelope.get("hookSpecificOutput", {})
    report.row(
        started.returncode == 0
        and specific.get("hookEventName") == "SessionStart"
        and "additionalContext" not in specific
        and CANARY not in started.stdout
        and DELIMITER not in started.stdout,
        "the session-start hook answers its envelope and injects nothing from the clone",
        f"rc={started.returncode}, event={specific.get('hookEventName')!r}, "
        f"context={'additionalContext' in specific}, canary={CANARY in started.stdout}",
    )

    # --- and with no record at all --------------------------------------------------------
    # **The note is put back and the owner trusts it again first, and that is the whole of this
    # row.** Row 2 changed `canary.md` and never restored it, so by this line the record had
    # already lapsed and the unlink below could not change anything the next bundle would
    # notice: the row printed the same absence row 2 had just printed, for row 2's reason.
    # Measured: pointing `trust_record()` at a path that does not exist made the unlink a no-op
    # and left `trust.json` 240 bytes on disk — and the row still reported ok. So the record is
    # made real again, its presence is asserted before the unlink and its absence after, and
    # the re-trusted store is shown to emit — this row's own positive control, because "the
    # canary did not arrive" is also what a store that was never re-trusted prints.
    note.write_text(committed, encoding="utf-8")
    again = stayfixed(
        plugin_root,
        ["memory", "trust", "--in-repo-memory", "--root", str(planted.clone)],
        env,
        planted.clone,
    )
    restored = through_wrapper(wrapper, bundle, env, planted.clone)
    had_record = trust_record(planted).exists()
    trust_record(planted).unlink(missing_ok=True)
    without = through_wrapper(wrapper, bundle, env, planted.clone)
    report.row(
        again.returncode == 0
        and had_record
        and not trust_record(planted).exists()
        and CANARY in restored.stdout
        and without.returncode == 0
        and CANARY not in without.stdout,
        "with no record at all the note is never injected",
        f"re-trusted rc={again.returncode}, record before={had_record}, "
        f"after={trust_record(planted).exists()}, canary while recorded="
        f"{CANARY in restored.stdout}, rc={without.returncode}, "
        f"canary={CANARY in without.stdout}",
    )

    # --- a home the clone names ------------------------------------------------------------
    # Claude Code applies no `HOME` from the clone's `env` block, but direnv, mise or a
    # devcontainer can set one from a file the clone commits, and the wrapper enters the clone
    # before Python starts, so `HOME=fakehome` is a directory the clone ships. It ships the
    # owner's own record there, moved out of the owner's home: the digest is one a clone computes
    # from its own content. Relative and absolute, the note stays out; moved back, the same record
    # lets it through under the same `HOME`, so the absence is the home's doing.
    retrusted = stayfixed(
        plugin_root,
        ["memory", "trust", "--in-repo-memory", "--root", str(planted.clone)],
        env,
        planted.clone,
    )
    planted_record = planted.clone / "fakehome" / ".config" / "stayfixed" / "trust.json"
    planted_record.parent.mkdir(parents=True, exist_ok=True)
    trust_record(planted).replace(planted_record)
    spelled = {
        "relative": through_wrapper(wrapper, bundle, {**env, "HOME": "fakehome"}, planted.clone),
        "absolute": through_wrapper(
            wrapper, bundle, {**env, "HOME": str(planted.clone / "fakehome")}, planted.clone
        ),
    }
    planted_record.replace(trust_record(planted))
    owners = through_wrapper(wrapper, bundle, {**env, "HOME": "fakehome"}, planted.clone)
    report.row(
        retrusted.returncode == 0
        and all(done.returncode == 0 and CANARY not in done.stdout for done in spelled.values())
        and CANARY in owners.stdout,
        "a trust record under a HOME the clone names is never read",
        ", ".join(f"{name} canary={CANARY in done.stdout}" for name, done in spelled.items())
        + f", the owner's record under the same HOME canary={CANARY in owners.stdout}",
    )

    # --- the wrapper's containment, made reachable ------------------------------------------
    # The four absolute candidates are not masked by a `PATH` entry, so on a runner that has
    # one of them the fall-through is never reached and the assertion would be on a token that
    # cannot be produced. The candidate list is the one thing a test may rewrite, for the
    # reason `tests/hooks/test_wrapper.py::_plugin_root` gives: it is deliberately not
    # environment-settable, so there is no other seam. Every guard around it is the shipped one.
    contained_root = args.scratch / "wrapper"
    (contained_root / "hooks").mkdir(parents=True, exist_ok=True)
    (contained_root / "scripts").mkdir(parents=True, exist_ok=True)
    copied = contained_root / "hooks" / "run-hook.sh"
    lines = wrapper.read_text(encoding="utf-8").splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if line.startswith("candidates="))
    lines[first] = "candidates='python3'\n"
    copied.write_text("".join(lines), encoding="utf-8")
    copied.chmod(0o755)
    (contained_root / "scripts" / "stayfixed").write_text(
        (plugin_root / "scripts" / "stayfixed").read_text(encoding="utf-8"), encoding="utf-8"
    )
    contained_env = {
        **env,
        "PATH": f"{planted.planted_interpreter.parent}:/usr/bin:/bin",
        "CLAUDE_PLUGIN_ROOT": str(contained_root),
    }
    contained_env.pop("STAYFIXED_PYTHON_CANDIDATES", None)
    # Both policies, and the exit codes are NOT the same — asserting "the wrapper refused, so it
    # exited non-zero" would have been wrong about `open`, which is the whole of the two failure
    # policies: a fault the wrapper can see prints its token and then degrades to 0 under `open` and
    # refuses with 2 under `closed`. What both rows share is the token, the reason inside it, and
    # that the planted interpreter never ran.
    degraded = through_wrapper(
        copied, ["open", "hook", "SessionStart"], contained_env, planted.clone
    )
    refused = through_wrapper(
        copied, ["closed", "hook", "PreToolUse"], contained_env, planted.clone
    )
    named = all(
        "SF_NO_PY" in done.stderr and "inside the project root" in done.stderr
        for done in (degraded, refused)
    )
    report.row(
        named
        and degraded.returncode == 0
        and refused.returncode == 2
        and not planted.planted_marker.exists(),
        "the interpreter inside the clone is refused by name, not merely not reached",
        f"open rc={degraded.returncode}, closed rc={refused.returncode}, named={named}, "
        f"planted-ran={planted.planted_marker.exists()}",
    )

    # --- what the clone's machine configuration bought it: a warning row and nothing else ----
    reported = stayfixed(
        plugin_root,
        ["doctor", "--json", "--root", str(planted.clone), "--home", str(planted.home)],
        env,
        planted.clone,
    )
    rows = {row["name"]: row for row in json.loads(reported.stdout or "{}").get("checks", [])}
    ignored = rows.get("ignored-env", {})

    # --- and what `attach` does with a store the machine does not record --------------------
    # Run here rather than below because the row above needs its refusal: `doctor`'s
    # `ignored-env` row is emitted because the variable is SET and never checks that the value
    # was ignored, so the sentence it prints stays true under the mutation it exists to catch.
    # Measured while `config/machine.py` still honoured those variables at a terminal: deleting
    # that tty gate, which the module's docstring then called its whole security record, left
    # that row reporting ok while the clone's configuration was being honoured. `attach` resolves
    # the overlay through `machine_config_path`, and its refusal names the overlay it resolved, so
    # which of the two files was read is a fact this scenario can read rather than assert.
    inside = planted.clone / "evil" / "overlay" / "projects" / "smoke" / "memory"
    attached = stayfixed(
        plugin_root,
        ["attach", "--store", str(inside), "--root", str(planted.clone), "--yes"],
        env,
        planted.clone,
    )
    # The refusal names the overlay it resolved — "… the overlay this machine records --
    # <root>/projects/…" — so the anchor is that clause and not the path anywhere in the line:
    # the `--store` argument the refusal quotes back is itself a path inside the clone, and a
    # bare substring test would find the clone's overlay in every run.
    owners_overlay = f"records -- {planted.overlay}/" in attached.stderr
    clones_overlay = f"records -- {planted.clone / 'evil' / 'overlay'}/" in attached.stderr
    report.row(
        ignored.get("status") == "warn"
        and "STAYFIXED_CONFIG" in ignored.get("detail", "")
        and owners_overlay
        and not clones_overlay,
        "the clone's machine configuration is named as ignored, and was ignored",
        f"status={ignored.get('status')!r}, the owner's overlay is the one in use="
        f"{owners_overlay}, the clone's is={clones_overlay}",
    )

    report.row(
        attached.returncode == 2
        and "--store must name this project's own directory" in attached.stderr,
        "attach refuses a store the machine does not record, for that reason",
        f"rc={attached.returncode}, stderr={attached.stderr.strip()[:120]!r}",
    )

    real = planted.overlay / "projects" / "smoke" / "memory"
    checked = stayfixed(
        plugin_root,
        ["attach", "--store", str(real), "--root", str(planted.clone), "--check", "--json"],
        env,
        planted.clone,
    )
    state = json.loads(checked.stdout or "{}").get("state")
    report.row(
        state == "mismatch",
        "a clone claiming another project's name is not that project",
        f"state={state!r}",
    )

    print("skip  memory_search under an explicit project= — stayfixed does not depend on mcp")
    # The floor this script had none of. Seven of its nine rows assert an ABSENCE, and a run
    # that executed one row prints the same green last line as a run that executed all nine —
    # measured, with `report.rows[:1]` immediately before this print and the whole suite still
    # green. The sibling script states its own count for the same reason.
    ran = len(report.rows)
    if ran != EXPECTED_ROWS:
        report.row(
            False,
            "the scenario ran the rows it declares",
            f"{ran} row(s), expected {EXPECTED_ROWS}",
        )
    print(f"{ran} row(s), {report.failures} failure(s)")
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
