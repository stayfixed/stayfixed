"""The owner's walkthrough, offline, in a temporary directory.

Every package is tested on its own against stubs. This is the one test that runs them in the
order a person does, and it exists because the four packages' seams — the machine file, the
overlay root, the project record, the link tree, the ignore region — are each written by one
package and read by another, and a stub on both sides of a seam agrees with itself.

**Every step runs the real launcher.** Each one used to call a library function, so the
argv wiring of eight commands — the flag names, the `--yes` gate reached through argparse, the
`--machine` refusal from a pipe, the JSON `doctor` prints — was exercised by nothing that ran
them in order. `_cli` below runs `scripts/stayfixed` in a subprocess, which is how a person and
how a skill reach these commands.

Nothing here touches the network, the real `~`, or any harness binary. `HOME` is a scratch
directory and every harness variable is dropped, and the binaries the CLI resolves through
`PATH` on purpose — `gh`, `claude`, `codex` and `pre-commit`, the owner's own — are answered by
a scratch `bin/` placed first on the subprocess's `PATH`. `pre-commit` there writes the commit
hook `doctor` later asks about, rather than only recording that it was called. `git` is real,
because a repository with no `origin` is not the thing being tested.

**`--machine` is driven through a pseudo-terminal on `attach`/`detach`.** Those two commands
honour it only from an interactive shell and refuse otherwise; `_cli(..., tty=True)` hands the
child a pty as stdin, and one test below proves both halves of that gate through argv.
"""

from __future__ import annotations

import json
import os
import pty
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

import stayfixed
from stayfixed.attach.hooks import NOT_ATTACHED, REAL_DIRECTORIES
from stayfixed.config.layout import ATTACH_LEDGER
from stayfixed.config.loader import CONFIG_FILE, load
from stayfixed.doctor.api import OK, RED, SKIP, WARN, run_checks
from stayfixed.memory.api import DELIMITER, PROJECTS, harness_memory_path, markers
from tests.floor import developer_free_environ
from tests.gitfixture import git
from tests.overlay.test_upgrade import SHIPPED_MEMORY_README
from tests.ownerhome import plugin_root_with_owner_home, stayfixed_argv
from tests.runners import Recorder
from tests.snapshot import (
    assert_snapshot_changed,
    assert_snapshot_unchanged,
    snapshot,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "hooks" / "run-hook.sh"
OWNER = "owner"
PROJECT = "widget"
ORIGIN = f"git@github.com:{OWNER}/{PROJECT}.git"
# The rule the walkthrough puts in the overlay and then asks a session for. Distinctive enough
# that finding it in the wrapper's stdout cannot be an accident.
RULE_BODY = "NEVER FORCE-PUSH A SHARED BRANCH; open a pull request instead."

# The note the walkthrough asks a session for, as one spelling. `_install_path` writes it into
# the overlay on the path a fresh project takes, and `_project(initialised=True)` writes the same
# bytes into the repository so the owner's own hand-move is what puts it in the overlay.
NOTE = (
    "---\nname: no-force-push\ndescription: never force-push a shared branch\n"
    f"metadata:\n  type: rule\n  startup: 1\n---\n\n{RULE_BODY}\n"
)

CONFIG = """[stayfixed]
version = "{version}"
state = "installed"

[project]
name = "{project}"

[memory]
mode = "{mode}"
groups = ["developer", "project-stable"]
"""


def _project(tmp_path: Path, *, mode: str, initialised: bool = False) -> Path:
    """The repository the walkthrough starts from; `initialised`, the shape the owner's has.

    **`initialised` does not run `init` here.** It builds the repository `init` is run *over*:
    notes already in `paths.memory` as real directories, `[ci] mode = "none"`, and one commit,
    so the history predates stayfixed. `stayfixed init --yes` is `_install_path`'s step 0, which
    is where the launcher environment lives. The flag keeps the name `_install_path` gives it,
    because renaming one of the pair would split them.

    `[ci] mode = "none"` because this repository wants no workflow — a `ci` mode that asked for one
    would have `init` reach for the release pin and a remote, which is a different test's subject.
    The commit matters because `init` then writes its footprint on top of a tree that was already
    committed, which is the order an adopting project meets it in, and the notes moved later are
    notes that were tracked before stayfixed arrived.
    """
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    document = CONFIG.format(version=stayfixed.__version__, project=PROJECT, mode=mode)
    if initialised:
        document += '[ci]\nmode = "none"\n'
    (root / CONFIG_FILE).write_text(document, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", ORIGIN)
    if initialised:
        note = root / "docs" / "memory" / "project-stable" / "no-force-push.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(NOTE, encoding="utf-8")
        git(root, "add", "-A")
        git(
            root,
            "-c",
            "user.email=a@b.c",
            "-c",
            "user.name=a",
            "commit",
            "-qm",
            "chore: before stayfixed",
        )
    return root


@dataclass(frozen=True)
class Walkthrough:
    """What the walkthrough's eleven steps leave behind, for each test to assert about one."""

    root: Path
    overlay: Path
    machine: Path
    home: Path
    data: Path
    store: Path
    bin: Path


def _fake_binaries(bin_dir: Path) -> None:
    """The four binaries the CLI resolves through `PATH`, as the walkthrough may see them.

    `pre-commit install` writes the hook `doctor` later asks about, so the fake writes it too —
    a stub that answered 0 and wrote nothing would make two steps disagree for no reason a
    reader could see (the in-process runner these fakes replaced said the same). `gh` must never be
    reached on the `--local` path, so its fake exits 1 and the test asserts the log never names
    it. `claude` and `codex` are here because `setup` installs the preset's plugins through
    `subprocess_runner()`, which resolves them on `PATH`: without these the walkthrough would run
    the developer's real harness CLI, which no test may ever do. Nothing later reads their effect,
    so they record and exit 0.
    """
    bin_dir.mkdir()
    log = bin_dir / "calls.log"
    # The real one needs a repository and fails outside one. A bare `mkdir -p .git/hooks` left a
    # `.git` git does not read as a repository, which `setup`'s overlay guard rightly refuses as
    # a repository git will not describe; so the fake makes the repository the real one needs.
    (bin_dir / "pre-commit").write_text(
        "#!/bin/sh\n"
        f'printf \'%s\\n\' "pre-commit $*" >> "{log}"\n'
        "git rev-parse --git-dir >/dev/null 2>&1 || git init -q . || exit 1\n"
        "mkdir -p .git/hooks && printf '#!/bin/sh\\nexit 0\\n' > .git/hooks/pre-commit\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "gh").write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "gh $*" >> "{log}"\nexit 1\n', encoding="utf-8"
    )
    for harness in ("claude", "codex"):
        (bin_dir / harness).write_text(
            f'#!/bin/sh\nprintf \'%s\\n\' "{harness} $*" >> "{log}"\nexit 0\n',
            encoding="utf-8",
        )
    for name in ("pre-commit", "gh", "claude", "codex"):
        (bin_dir / name).chmod(0o755)


def _cli(walk: Walkthrough, *argv: str, tty: bool = False) -> subprocess.CompletedProcess[str]:
    """One command, the way a person or a skill runs it: the launcher, argv, a pipe or a tty.

    `tty=True` hands the child a pseudo-terminal as stdin, which is what `attach --machine`
    and `detach --machine` require (they refuse from a pipe, and the test proves the pipe
    refusal separately). Nothing here reads the developer's own `~`: `HOME` is the scratch
    home and every harness variable is dropped.
    """
    env = developer_free_environ()
    env["HOME"] = str(walk.home)
    env["PATH"] = f"{walk.bin}{os.pathsep}{env.get('PATH', '')}"
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
    env["CLAUDE_PLUGIN_DATA"] = str(walk.data)
    # The launcher's own lines, with the password database answering the scratch home as `HOME`
    # does: off a terminal, that is where the machine owner's home is read (`tests/ownerhome.py`).
    command = [*stayfixed_argv(walk.home), *argv]
    if not tty:
        return subprocess.run(
            command,
            cwd=walk.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    parent, child = pty.openpty()
    try:
        return subprocess.run(
            command,
            cwd=walk.root,
            stdin=child,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    finally:
        os.close(child)
        os.close(parent)


def _doctor(walk: Walkthrough, *, root: Path | None = None) -> list[dict[str, str]]:
    """The sixteen rows, read back out of what `doctor --json` printed on the launcher's stdout."""
    done = _cli(
        walk,
        "doctor",
        "--json",
        "--root",
        str(walk.root if root is None else root),
        "--home",
        str(walk.home),
        "--machine",
        str(walk.machine),
    )
    assert done.stdout, done.stderr
    rows: list[dict[str, str]] = json.loads(done.stdout)["checks"]
    assert len(rows) == 16, rows
    return rows


def _install_path(
    tmp_path: Path,
    *,
    initialised: bool = False,
    attach: bool = True,
    earlier_template: bool = False,
) -> Walkthrough:
    """Steps 1-5: the overlay, the machine layer, a repository, attach, and a note in it.

    Every step is the real launcher with the real argv. Step 1's overlay is created **outside** the
    project root on purpose: `setup` refuses to record one inside it, because a path inside the
    project is exactly the shape of tree a hostile clone can ship.

    `initialised` walks the same steps over a repository that already has its notes in
    `paths.memory` and has had `stayfixed init` run over it, which is the shape the owner's own
    repository is in. Step 4 then has one more beat in the middle: `--check` finds the group
    that never moved and exits 1, the notes are moved by hand — the owner's act, which no
    command performs — and the attach is taken over a repository with nothing to link over.
    Step 5 is skipped there, because the moved note is the standing rule.

    `attach=False` stops before step 4 and answers the unattached state, which is what a
    session's first `SessionStart` sees on a project nobody has bound yet.

    `earlier_template` turns step 1's tree into what a template published at 0.1.x generates:
    no ledger, since `publish-template` leaves it out, and the `common/memory/README.md` those
    releases shipped. `gh` is out of reach offline, so the rendered tree is made that shape
    before step 2, which is where such an overlay meets this release first.

    `init` runs here rather than in `_project`, which has no launcher environment: `_cli` needs
    the scratch home, the fake `PATH` and the plugin data root, and those are built from this
    function's locals. It runs before step 1 because it is the state the repository arrives in.
    """
    home = tmp_path / "home"
    data = tmp_path / "plugin-data"
    machine = tmp_path / "config" / "stayfixed" / "config.toml"
    machine.parent.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    _fake_binaries(bin_dir)

    root = _project(tmp_path, mode="overlay", initialised=initialised)
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    # Where `overlay create --root <overlays> --name stayfixed-private` puts it, which
    # `overlay.create.target_root` computes from the arguments alone.
    overlay = overlays / "stayfixed-private"
    store = overlay / PROJECTS / PROJECT / "memory"
    walk = Walkthrough(root, overlay, machine, home, data, store, bin_dir)

    def step(*argv: str, tty: bool = False) -> subprocess.CompletedProcess[str]:
        done = _cli(walk, *argv, tty=tty)
        assert done.returncode == 0, f"`{' '.join(argv)}`: {done.stderr}"
        return done

    # 0. the project footprint, on the repository that came with notes and a history. `init`
    # adopts the `stayfixed.toml` already there without rewriting it (a `Kind.ONCE` artifact
    # whose file is present is skipped), so the document above is still the document below,
    # and the manifest is the witness that the footprint pass ran.
    if initialised:
        step("init", "--yes", "--root", str(root), "--machine", str(machine))
        assert (root / ".stayfixed" / "manifest.json").is_file(), "`init` recorded no manifest"
    # 1. the overlay, rendered from the shipped template with no network call.
    step(
        "overlay",
        "create",
        "--owner",
        OWNER,
        "--name",
        "stayfixed-private",
        "--local",
        "--root",
        str(overlays),
    )
    if earlier_template:
        shutil.rmtree(overlay / ".stayfixed")
        (overlay / "common" / "memory" / "README.md").write_text(
            SHIPPED_MEMORY_README, encoding="utf-8"
        )
    # 2. make it this owner's, and install its commit-time secret scan.
    step("overlay", "init", "--owner", OWNER, "--root", str(overlay))
    # 3. the machine layer, into a scratch machine file and a scratch home. **Two runs**, as
    # the walkthrough had before it was converted: the first writes the machine file with no
    # overlay in it, the second records one into a file that already exists. "A second `setup`
    # records an overlay the first did not" is a merge seam between two areas, and collapsing
    # the two runs into one would have left it to `tests/setup/` alone -- which is the shape of
    # gap this whole module exists to close. The assertion between them is what makes it a
    # seam rather than two commands that happened to run.
    step(
        "setup",
        "--preset",
        "recommended",
        "--home",
        str(home),
        "--machine",
        str(machine),
        "--root",
        str(root),
    )
    assert str(overlay) not in machine.read_text(encoding="utf-8"), (
        "the first `setup` named no overlay and must have recorded none"
    )
    step(
        "setup",
        "--preset",
        "recommended",
        "--home",
        str(home),
        "--machine",
        str(machine),
        "--overlay",
        str(overlay),
        "--root",
        str(root),
    )
    assert str(overlay) in machine.read_text(encoding="utf-8"), (
        "the second `setup` recorded the overlay into the file the first one wrote"
    )
    if not attach:
        return walk
    # 4. attach: the diff first, then the write. `--check` writes nothing and prints what the
    # `--yes` run is consenting to, which is the order the attach skill walks.
    if initialised:
        # The beat the initialised path adds, and the one the refusal exists for. `attach`
        # links; it never moves a note, so the group still sitting in the repository is a
        # finding `--check` reports and exits 1 on, before anything is written.
        found = _cli(
            walk,
            "attach",
            "--store",
            str(store),
            "--check",
            "--json",
            "--machine",
            str(machine),
            tty=True,
        )
        assert found.returncode == 1, found.stderr
        assert json.loads(found.stdout)["real_directories"] == 1, found.stdout
        # The owner's own act: the notes move into this project's share of the overlay. No
        # command does this, which is why the refusal says where they go and stops.
        store.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root / "docs" / "memory" / "project-stable"), str(store / "project-stable"))
    previewed = step(
        "attach", "--store", str(store), "--check", "--machine", str(machine), tty=True
    )
    assert previewed.stdout.strip(), "`attach --check` printed no diff to consent to"
    step("attach", "--store", str(store), "--yes", "--machine", str(machine), tty=True)
    if initialised:
        # Step 5 already happened, by the owner's hand: the moved note *is* the standing rule.
        return walk

    # 5. a standing rule in this project's own share of the overlay.
    #
    # `project-stable` and not `developer`: `memory.store.COMMON_GROUP` is `developer`, so that
    # name resolves to `<overlay>/common/memory`, which is shared across every project. A note
    # written under `projects/<name>/memory/developer/` is linked by nothing and arrives
    # nowhere — which is the seam this walkthrough found first.
    note = store / "project-stable" / "no-force-push.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(NOTE, encoding="utf-8")
    return walk


def _session(
    walk: Walkthrough, *argv: str, machine: bool = True
) -> subprocess.CompletedProcess[str]:
    """One `hooks.json` entry, run the way a harness runs it: through the wrapper, raw.

    `HOME` and `--machine` both point into the scratch tree, so nothing here can read the
    developer's own `~/.claude` or `~/.config/stayfixed`.

    `machine=False` for `stayfixed hook <event>`, which takes no such flag: the dispatcher hands
    every handler `machine=None` on purpose, so a handler reads `.config/stayfixed/` under the
    home the password database records, and nothing a session can name. The plugin root's
    launcher pins that home to the scratch one `HOME` names (`_plugin_root`), and a caller that
    wants the hook path to see a machine file puts one there.
    """
    env = developer_free_environ()
    plugin = _plugin_root(walk)
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
    env["CLAUDE_PROJECT_DIR"] = str(walk.root)
    env["CLAUDE_PLUGIN_DATA"] = str(walk.data)
    env["HOME"] = str(walk.home)
    flags = ["--machine", str(walk.machine)] if machine else []
    return subprocess.run(
        [str(plugin / "hooks" / WRAPPER.name), "open", *argv, *flags],
        cwd=walk.root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _plugin_root(walk: Walkthrough) -> Path:
    """This checkout as the plugin root a session's wrapper runs from, with the password
    database answering the scratch home: the hook path reads the machine owner's home from
    there and not from `HOME` (`tests/ownerhome.py`)."""
    return plugin_root_with_owner_home(walk.home.parent, walk.home)


def _bundle(walk: Walkthrough, bundle: str, part: int = 1) -> subprocess.CompletedProcess[str]:
    return _session(walk, "memory", "session-context", "--bundle", bundle, "--part", str(part))


def _doctor_env(walk: Walkthrough) -> dict[str, str]:
    """The environment a harness session has: a data root, and neither ignored variable."""
    # `HOME` is here because `doctor`'s `wrapper` check hands this environment to a real
    # subprocess: without it the wrapper's `stayfixed --version` builds the default machine path
    # out of the developer's own home directory, which is a read this suite does not make.
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(walk.home),
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PLUGIN_DATA": str(walk.data),
    }


def test_setup_then_overlay_then_attach_then_a_session_sees_memory(tmp_path: Path) -> None:
    # The whole path, in the order a person walks it, ending where it is supposed to end: the
    # rule the owner wrote in their overlay arrives in a session's context.
    #
    # RAW, with no JSON envelope, which is the invariant the bundle's cap margin turns on: `memory
    # session-context` prints the text itself, so `bundles.CAP_MARGIN` is additive rather than
    # fighting an envelope's own escaping.
    walk = _install_path(tmp_path)
    done = _bundle(walk, "standing-rules")
    assert done.returncode == 0, done.stderr
    assert RULE_BODY in done.stdout
    assert not done.stdout.lstrip().startswith("{")
    assert '"summary"' not in done.stdout
    # The fakes on `PATH` were what ran, and `gh` was not among them: `--local` renders the
    # shipped template and touches no network, so a `gh` line here would mean the walkthrough
    # took the `--template` branch and only looked as if it had not.
    calls = (walk.bin / "calls.log").read_text(encoding="utf-8").splitlines()
    assert "pre-commit install" in calls
    assert not [line for line in calls if line.startswith("gh ")], calls


def test_an_overlay_from_a_template_an_earlier_release_published_passes_the_index_check(
    tmp_path: Path,
) -> None:
    # `overlay create --template` and `setup --overlay create:` generate the overlay from a
    # template repository, which carries no ledger, and one published at 0.1.x ships
    # `common/memory/README.md`, which the note reader reads as a note with no frontmatter:
    # `memory index --check` failed right after the first attach, and only an `overlay upgrade`
    # nobody had been told to run put it right. `overlay init`, which every such overlay runs,
    # now removes it where it holds the bytes a release shipped.
    #
    # Mutation: `mutations/`'s "overlay init leaves the memory README a release shipped".
    walk = _install_path(tmp_path, earlier_template=True)
    assert not (walk.overlay / "common" / "memory" / "README.md").exists()
    # Non-vacuous: the new name is there, and the tree still has no ledger of its own.
    assert (walk.overlay / "common" / "memory" / "_README.md").is_file()
    assert not (walk.overlay / ".stayfixed").exists()
    # Step 5 writes a note after the attach, which leaves any index out of date; without it the
    # store is what the first attach rendered its index from.
    (walk.store / "project-stable" / "no-force-push.md").unlink()
    checked = _cli(walk, "memory", "index", "--check", "--machine", str(walk.machine))
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_the_machine_file_is_the_only_thing_that_says_where_the_overlay_is(
    tmp_path: Path,
) -> None:
    # The machine file is the only record of the overlay root, end to end. `setup` wrote the root
    # and `attach` read it back; nothing on a command line chose it. The vacuity guard for the
    # walkthrough above: a session that resolved a store without the machine file would pass that
    # test for the wrong reason.
    walk = _install_path(tmp_path)
    assert str(walk.overlay) in walk.machine.read_text(encoding="utf-8")
    env = developer_free_environ()
    plugin = _plugin_root(walk)
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
    env["CLAUDE_PROJECT_DIR"] = str(walk.root)
    env["HOME"] = str(walk.home)
    without = subprocess.run(
        [
            str(plugin / "hooks" / WRAPPER.name),
            "open",
            "memory",
            "session-context",
            "--bundle",
            "standing-rules",
        ],
        cwd=walk.root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert RULE_BODY not in without.stdout
    # Non-vacuous: the run has to fail for *this* reason, and not for any other. The
    # wrapper degrades open, so the exit code says nothing and stderr says everything.
    assert "no overlay root is recorded" in without.stderr


def test_the_bundle_arrives_whole_and_within_the_platform_cap(tmp_path: Path) -> None:
    # The end-to-end form of the bundle's invariant: what one `hooks.json` entry emits must fit the
    # platform's own cap, because anything above it is truncated by the harness and a truncated
    # block is a block that arrives half-said.
    #
    # `trust.wrap`'s two region markers are not asserted here. In **overlay** mode there are
    # none and there must not be: the notes are the machine owner's own, `inside_project` is
    # False by construction and `bundles.blocks` wraps nothing — so that assertion cannot hold
    # on this walkthrough, and the mode where it does hold is the test below.
    walk = _install_path(tmp_path)
    done = _bundle(walk, "standing-rules")
    config = load(walk.root, machine=walk.machine)
    assert done.stdout
    assert len(done.stdout) <= config.native_caps.hook_output_chars
    assert DELIMITER not in done.stdout


def test_a_wrapped_bundle_arrives_with_both_of_its_region_markers(tmp_path: Path) -> None:
    # `trust.wrap` puts the closing nonce at the very end, so any truncation of the emitted
    # string drops it — and a region that opens and never closes is the defeat of the one
    # delimiter this project built as its boundary. It was measured arriving that way once, and
    # this is the end-to-end assertion that it does not.
    #
    # `in-repo` mode, because that is the mode in which a store is repository data and a region
    # is what wraps it. Same wrapper, same command, same scratch machine file.
    root = _project(tmp_path, mode="in-repo")
    machine = tmp_path / "config" / "stayfixed" / "config.toml"
    machine.parent.mkdir(parents=True)
    notes = root / "docs" / "memory" / "project-stable"
    notes.mkdir(parents=True)
    (notes / "no-force-push.md").write_text(NOTE, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    _fake_binaries(bin_dir)
    walk = Walkthrough(root, root, machine, tmp_path / "home", tmp_path / "data", notes, bin_dir)
    trusted = _cli(walk, "memory", "trust", "--in-repo-memory", "--machine", str(machine))
    assert trusted.returncode == 0, trusted.stderr
    done = _bundle(walk, "standing-rules")
    assert done.returncode == 0, done.stderr
    assert RULE_BODY in done.stdout
    found = re.search(rf"{re.escape(DELIMITER)}:([0-9a-f]+)>>>", done.stdout)
    assert found is not None, done.stdout
    begin, end = markers(found.group(1))
    assert begin in done.stdout
    assert end in done.stdout
    config = load(root, machine=machine)
    assert len(done.stdout) <= config.native_caps.hook_output_chars


def test_detach_returns_the_project_to_where_it_started(tmp_path: Path) -> None:
    # The round trip over the whole path rather than over `attach`'s own ledger: snapshot every
    # file under the project root before the attach and compare after the detach. What the
    # overlay records is deliberately not on this list — `projects/<name>/project.toml` is the
    # owner's consent and outlives a detach on purpose.
    #
    # The walkthrough's own steps are repeated here rather than reused, because the snapshot has
    # to be taken between `setup` and `attach` and `_install_path` runs both.
    home = tmp_path / "home"
    machine = tmp_path / "config" / "stayfixed" / "config.toml"
    machine.parent.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    _fake_binaries(bin_dir)
    root = _project(tmp_path, mode="overlay")
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    overlay = overlays / "stayfixed-private"
    store = overlay / PROJECTS / PROJECT / "memory"
    walk = Walkthrough(root, overlay, machine, home, tmp_path / "plugin-data", store, bin_dir)

    def step(*argv: str, tty: bool = False) -> None:
        done = _cli(walk, *argv, tty=tty)
        assert done.returncode == 0, f"`{' '.join(argv)}`: {done.stderr}"

    step(
        "overlay",
        "create",
        "--owner",
        OWNER,
        "--name",
        "stayfixed-private",
        "--local",
        "--root",
        str(overlays),
    )
    step("overlay", "init", "--owner", OWNER, "--root", str(overlay))
    step(
        "setup",
        "--preset",
        "recommended",
        "--home",
        str(home),
        "--machine",
        str(machine),
        "--overlay",
        str(overlay),
        "--root",
        str(root),
    )
    before = snapshot(root)
    # The walk's own non-vacuity guard: `snapshot` is a walk, so the comparison below passes
    # vacuously the day the walk stops finding anything.
    assert before
    step("attach", "--store", str(store), "--yes", "--machine", str(machine), tty=True)
    assert_snapshot_changed(root, before)
    step("detach", "--machine", str(machine), tty=True)
    assert_snapshot_unchanged(root, before)
    # Stated rather than left to the file walk, which sees files alone: the directory the links
    # sat in is taken back too once it is empty, so a detach leaves no empty `paths.memory`.
    assert not (root / "docs" / "memory").exists()


def test_doctor_is_green_on_the_attached_fixture(tmp_path: Path) -> None:
    # Green meaning: no `red`, and the only `skip`s are the one this build cannot answer — the
    # Codex hook-trust hash nothing has measured yet — and `ci-ref`, which skips on a state this
    # fixture is in rather than on a limit of the build: it records no `[ci] ref`, because no
    # released tag matches the stayfixed running here for `init` to have pinned.
    # `files` is not among them: the release ships `hooks/hashes.json`, and this walk runs
    # against the checkout, so the row compares the three shipped files against the record
    # committed beside them and is green. A `files` back in this list means the
    # record went stale — `uv run python scripts/release.py hashes` is what refreshes it.
    walk = _install_path(tmp_path)
    rows = _doctor(walk)
    assert [row["name"] for row in rows if row["status"] == RED] == []
    assert [row["name"] for row in rows if row["status"] == SKIP] == [
        "codex-trust",
        "ci-ref",
    ]
    assert next(row for row in rows if row["name"] == "files")["status"] == OK


# What `docs/cli.md` says `stayfixed doctor` launches: six subprocesses on a green attached
# installation *besides* the `ci-ref` row, which the stub runner below answers in process rather
# than launching — so six here and seven in production on a repository that records a `[ci] ref`,
# which is what `docs/cli.md` says.
# Written as a number rather than as a set of argv lists so the failure reads as "the count
# moved", which is the claim.
#
# Five and not four since the binding's and the note store's rows moved into their own areas:
# each area resolves the note store for its own rows, once per report, and in overlay mode a
# resolution asks `git` for the checkout's `origin`. So `attached` and the store's two rows ask
# it once each, where one shared context used to ask it once for all three.
#
# Six and not five since `hook-entries` asks git's index which files below the root a nested
# `.claude/skills` holds, in place of walking the whole tree.
DOCTOR_LAUNCHES = 6


def test_doctor_launches_the_number_of_subprocesses_it_says_it_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `doctor/__init__.py` used to say "exactly two" and the true answer was four: one launch is
    # this area's own — the wrapper probe — and three more come from inside the areas its rows
    # call, where nobody counting `subprocess.run` in `doctor/` would see them. The number had
    # already moved twice during this branch's review before anyone measured it.
    #
    # This case is deliberately brittle. A row that starts asking `git` one more question moves
    # it, and that is the point: the number moving *silently* is the defect this exists for, and
    # a reader who has to update a constant has read the paragraph that states it.
    #
    # `Popen` and not `subprocess.run`: `run` is a wrapper around it, so patching the lower of
    # the two counts a caller that reached past `run` as well. `ci-ref` is not among these — it
    # goes through `stayfixed.runner.Runner`, which the stub below answers, and it is the only
    # one that would leave the machine.
    #
    # **The one test here that keeps the library seam**, and the reason is the measurement
    # itself: this counts launches through a `Popen` patched in *this* process, and a `doctor`
    # run as a subprocess launches its six in a process no patch of ours can see. Everything
    # else in this module runs the launcher; this cannot, and says so.
    walk = _install_path(tmp_path)
    launched: list[list[str]] = []
    real = subprocess.Popen

    def spy(argv, *args, **kwargs):  # type: ignore[no-untyped-def]
        launched.append([str(part) for part in argv])
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    # The one call in this module that runs `run_checks` in this process, so it needs a runner to
    # hand it; `ci-ref`, the only row that would use one, skips on this fixture. Everything else
    # here reaches the CLI's own `subprocess_runner()` through the launcher, and the fakes
    # `_fake_binaries` writes are what answer it.
    checks = run_checks(
        walk.root,
        home=walk.home,
        machine=walk.machine,
        runner=Recorder(),
        env=_doctor_env(walk),
    )
    monkeypatch.undo()
    # The report is green first, so a count taken from a run that fell over early cannot pass.
    assert [check.name for check in checks if check.status == RED] == []
    assert len(launched) == DOCTOR_LAUNCHES, launched
    # And they are the six the paragraph names, not six of something else: one wrapper probe,
    # and five `git` questions. Asserted by shape rather than by full argv, because each of the
    # five `git` calls carries the temporary checkout or overlay it asks about, and by the
    # program's name, because off a terminal `git` is run by the absolute path this machine
    # holds it at (`stayfixed.gitenv.git_program`).
    assert sum(1 for argv in launched if argv[0] == str(WRAPPER)) == 1
    assert sum(1 for argv in launched if Path(argv[0]).name == "git") == 5


def test_doctor_is_red_when_the_memory_path_is_a_real_directory(tmp_path: Path) -> None:
    # The `attached` row's real-directory arm, end to end: replace the link with a real
    # directory and assert `attached` goes red. This is the shape one existing checkout already
    # has, which is why it is named rather than left to a general "not attached".
    walk = _install_path(tmp_path)
    harness = harness_memory_path(walk.root, walk.home)
    harness.mkdir(parents=True, exist_ok=True)
    attached = next(row for row in _doctor(walk) if row["name"] == "attached")
    assert attached["status"] == RED
    assert "real directory" in attached["detail"]


def test_an_owner_whose_ledger_will_not_parse_gets_back_to_green_the_way_doctor_says(
    tmp_path: Path,
) -> None:
    # The owner `hook-entries` must not refuse once an unreadable ledger beside an entry nothing
    # grants is red: attached, with one entry the overlay grants, and the ledger corrupted. The row
    # warns, the report exits 0, and the remedy it prints, followed literally, ends green with the
    # entry accounted for — so the warning is one with a way out, not a dead end. Mutations
    # (oracle): `mutations/`'s "attach does not ask the overlay about a ledger it cannot read" ->
    # the row is red; "an unreadable ledger is never told how to rebuild it" -> the remedy is not
    # the one that ends green.
    walk = _install_path(tmp_path)
    (walk.overlay / "common" / "claude" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    def attach() -> None:
        done = _cli(
            walk,
            "attach",
            "--store",
            str(walk.store),
            "--yes",
            "--machine",
            str(walk.machine),
            tty=True,
        )
        assert done.returncode == 0, done.stderr

    def entries() -> tuple[dict[str, str], list[str]]:
        rows = _doctor(walk)
        red = [row["name"] for row in rows if row["status"] == RED]
        return next(row for row in rows if row["name"] == "hook-entries"), red

    attach()
    assert entries() == (
        {
            "name": "hook-entries",
            "status": OK,
            "detail": "1 stayfixed entr(ies), 0 foreign; all accounted for",
            "remedy": "",
        },
        [],
    )
    ledger = walk.root / ATTACH_LEDGER
    ledger.write_text("this is not json", encoding="utf-8")
    row, red = entries()
    assert (row["status"], red) == (WARN, [])
    assert row["remedy"] == (
        f"remove {ATTACH_LEDGER} and run `stayfixed attach --store "
        f"<overlay>/projects/<project>/memory` to write a new one"
    )
    ledger.unlink()
    attach()
    assert entries() == (
        {
            "name": "hook-entries",
            "status": OK,
            "detail": "1 stayfixed entr(ies), 0 foreign; all accounted for",
            "remedy": "",
        },
        [],
    )


def test_an_overlay_grant_carrying_more_than_a_command_is_accounted_for_once_attached(
    tmp_path: Path,
) -> None:
    # `hook-entries` vouches for an entry only where the whole entry is the one `attach` writes, so
    # the owner it must not refuse is one whose overlay grants an entry with a `timeout` and a
    # `statusMessage` beside its command: `attach` writes both as they are, and the row reads what
    # it wrote. Run through the real `attach`, so the comparison is with the bytes it put in the
    # settings file. Mutation (oracle): `mutations/`'s "a grant keeps the integers the walk reads
    # as text" -> red.
    walk = _install_path(tmp_path)
    granted = {
        "type": "command",
        "command": "echo hi",
        "timeout": 30,
        "statusMessage": "Checking the command…",
    }
    (walk.overlay / "common" / "claude" / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [granted]}]}}),
        encoding="utf-8",
    )
    done = _cli(
        walk,
        "attach",
        "--store",
        str(walk.store),
        "--yes",
        "--machine",
        str(walk.machine),
        tty=True,
    )
    assert done.returncode == 0, done.stderr
    written = json.loads((walk.root / ".claude" / "settings.local.json").read_text("utf-8"))
    (entry,) = written["hooks"]["PreToolUse"][0]["hooks"]
    assert (entry["timeout"], entry["statusMessage"]) == (30, granted["statusMessage"]), entry
    rows = _doctor(walk)
    assert next(row for row in rows if row["name"] == "hook-entries") == {
        "name": "hook-entries",
        "status": OK,
        "detail": "1 stayfixed entr(ies), 0 foreign; all accounted for",
        "remedy": "",
    }


def test_attach_refuses_machine_from_a_pipe_and_honours_it_from_a_terminal(tmp_path: Path) -> None:
    # The interactive-shell gate on `--machine`, reached through argv rather than through the
    # `interactive=` seam: a pipe is refused with exit 2 and the sentence, a pseudo-terminal
    # is honoured. The library-level tests prove the seam; this proves the launcher hands
    # the command a stdin the gate can ask. No mutation of its own — the gate's own entry,
    # `mutations/`'s "attach honours --machine from a session nobody is sitting in front of",
    # reddens the library test and, through this, the pipe half here; run it and say so.
    walk = _install_path(tmp_path)
    store = str(walk.overlay / PROJECTS / PROJECT / "memory")
    piped = _cli(walk, "attach", "--store", store, "--check", "--machine", str(walk.machine))
    assert piped.returncode == 2 and "interactive shell" in piped.stderr
    tty = _cli(
        walk, "attach", "--store", store, "--check", "--machine", str(walk.machine), tty=True
    )
    assert tty.returncode == 0, tty.stderr


def test_init_then_the_walkthrough_ends_with_the_rule_in_a_session(tmp_path: Path) -> None:
    # The whole slice, in the order the owner walks it and on the repository shape they
    # actually have: a project with notes already in it, `stayfixed init` run over it, the
    # attach refused because those notes never moved, the notes moved by hand, the attach
    # taken, and a session reading the moved note back through the wrapper.
    #
    # What would break it: remove the refusal and step 4's `--check` exits 0 with
    # `real_directories: 0`; remove the link tree and `RULE_BODY` never reaches the bundle;
    # remove `init`'s footprint and the manifest assertion fails; let any row go red — the
    # sixteenth, `overlay-requires`, is the one this branch added and it is answered here
    # against a real overlay rather than a stub.
    walk = _install_path(tmp_path, initialised=True)
    done = _bundle(walk, "standing-rules")
    assert done.returncode == 0, done.stderr
    assert RULE_BODY in done.stdout
    rows = _doctor(walk)
    assert not [row for row in rows if row["status"] == RED]
    assert (walk.root / ".stayfixed" / "manifest.json").is_file()


def test_a_session_before_the_attach_is_told_what_is_missing(tmp_path: Path) -> None:
    # The handler through the wrapper, on the one state it exists for: initialised, not yet
    # attached, notes still in the repository. It reads the machine file the hook path reads —
    # `<home>/.config/stayfixed/config.toml` — and not the walkthrough's own, so the walkthrough's
    # file is copied there for the hook alone.
    #
    # The envelope is raw JSON with `additionalContext` inside; both constants are single lines
    # with no JSON-escaped characters, so `in` over the text is enough. Imported and never
    # respelled: a session line is the one string a reader compares against what they saw.
    #
    # What would break it: drop either line from the handler, or let the binding read as bound
    # or the group count as zero, and the corresponding `in` fails.
    walk = _install_path(tmp_path, initialised=True, attach=False)
    hook_machine = walk.home / ".config" / "stayfixed" / "config.toml"
    hook_machine.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(walk.machine, hook_machine)
    done = _session(walk, "hook", "SessionStart", machine=False)
    assert done.returncode == 0, done.stderr
    assert NOT_ATTACHED in done.stdout
    assert REAL_DIRECTORIES.format(count=1) in done.stdout


def test_detach_on_an_initialised_project_leaves_the_footprint(tmp_path: Path) -> None:
    # The ignore region's ownership, end to end. `init` recorded the `stayfixed:ignore` region as
    # the footprint's, so the detach that takes back everything `attach` added leaves that block
    # where it is — and the manifest with it, because `detach` never touches the scaffold ledger.
    #
    # What would break it: withdraw the region unconditionally and `.gitignore` loses its
    # block, so the byte comparison fails.
    walk = _install_path(tmp_path, initialised=True)
    ignore_before = (walk.root / ".gitignore").read_text(encoding="utf-8")
    # Non-vacuous: the block this asserts survives has to be there before the detach.
    assert "stayfixed:ignore" in ignore_before
    done = _cli(walk, "detach", "--root", str(walk.root), "--machine", str(walk.machine), tty=True)
    assert done.returncode == 0, done.stderr
    assert (walk.root / ".gitignore").read_text(encoding="utf-8") == ignore_before
    assert (walk.root / ".stayfixed" / "manifest.json").is_file()
