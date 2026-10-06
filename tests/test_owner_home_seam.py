"""Every `stayfixed` a test or a script starts runs with the password database's home chosen.

Off a terminal stayfixed takes the machine owner's home from the password database and never
from `HOME` (`stayfixed.config.machine.owner_home`), so a scratch `HOME` no longer keeps a child
away from the developer's own `~/.config/stayfixed`. A child that forgets the seam does not fail:
it reads, or with `memory trust` writes, the developer's real files. So the seam is held here, by
reading the source rather than by running it, the way `tests/test_outbound.py` holds launches.

**What is read as a launch.** A list or tuple display, in a file under `tests/` or `scripts/`,
that is an argv starting `stayfixed`:

- its head is the interpreter (`sys.executable`, or a name holding one) followed, within the
  next three elements, by the launcher (a path ending `scripts/stayfixed`, or `LAUNCHER`) or by
  `-m stayfixed`;
- or its head names the hook wrapper (`run-hook.sh`, a name containing `wrapper`);
- or its head is `*stayfixed_argv(...)`, which is the seam itself.

A display whose head is a string literal is a list of file names, not an argv. Two launches build
their argv some other way and are named in `INDIRECT`, held to exist.

**What counts as going through the seam.** The argv starts `*stayfixed_argv(...)`; or the
top-level function holding it names a seam (`SEAMS`), or names a function of the same file that
does; or the file is a script whose `main` derives its plugin root through `with_owner_home`
before any launch (`DERIVED`). Anything else is a finding unless `EXEMPT` names its function with
the reason it reads no home. Both tables are held both ways: an entry that excuses nothing is a
finding too, since it is ready to excuse the next launch that matches it.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAMS = frozenset(
    {"stayfixed_argv", "plugin_root_with_owner_home", "checkout_with_owner_home", "with_owner_home"}
)
# This file, and the two that define the seam: what they spell is the seam, not a launch.
OUT_OF_SCOPE = frozenset({"tests/test_owner_home_seam.py", "tests/ownerhome.py"})

# Scripts whose `main` builds the plugin root every launch below it uses through `with_owner_home`.
DERIVED: dict[str, str] = {
    "scripts/smoke_hooks.py": "every row runs under the root `main` derives for the scratch home",
    "scripts/smoke_exfiltration.py": "every row runs under the root `main` derives for the "
    "scratch home",
}

# `(file, top-level function)`: launches that reach stayfixed and read no home, with why.
EXEMPT: dict[tuple[str, str], str] = {
    ("tests/hooks/test_wrapper.py", "_run"): "runs the wrapper of the plugin root its case passes: "
    "`_plugin_root`'s fake launcher, which runs no stayfixed, `plugin_root_with_owner_home`'s, or "
    "this checkout's for `--version`, which reads no home",
    (
        "tests/hooks/test_wrapper.py",
        "test_an_interpreter_the_environment_names_is_ignored_off_a_terminal",
    ): "the plugin root's launcher is `_plugin_root`'s fake, which runs no stayfixed",
    (
        "tests/hooks/test_wrapper.py",
        "test_the_project_root_is_never_taken_from_an_inherited_git_environment",
    ): "the plugin root's launcher is `_plugin_root`'s fake, which runs no stayfixed",
    ("tests/hooks/test_wrapper.py", "test_a_project_root_that_cannot_be_entered_says_so"): (
        "the plugin root's launcher is `_plugin_root`'s fake, which runs no stayfixed"
    ),
    ("tests/hooks/test_wrapper.py", "test_stayfixed_runs_from_the_project_root"): (
        "the plugin root's launcher is `_plugin_root`'s fake, which prints its directory"
    ),
    ("tests/test_cli.py", "test_module_entry_point_runs_without_the_console_script"): (
        "`python -m stayfixed --version` is the case, and `--version` reads no home"
    ),
    ("tests/test_launcher.py", "test_the_launcher_runs_from_the_plugin_root"): (
        "the launcher itself under `-S`, for `--version`, which reads no home"
    ),
    ("tests/test_launcher.py", "test_an_old_interpreter_is_refused_with_a_reason"): (
        "the launcher's own interpreter floor, which refuses before stayfixed is imported"
    ),
}

# Launches whose argv is not a display the walk reads, by `(file, top-level function)`.
INDIRECT: dict[tuple[str, str], str] = {
    ("scripts/smoke_hooks.py", "check_entry"): "each `hooks.json` command with the plugin root "
    "substituted, under the root `main` derives (`DERIVED`)",
    (
        "tests/test_check_workflow.py",
        "_judge",
    ): "the workflow's own step script, under the checkout `checkout_with_owner_home` builds",
}


def _files() -> list[Path]:
    found = [*ROOT.glob("tests/**/*.py"), *ROOT.glob("scripts/*.py")]
    return sorted(f for f in found if str(f.relative_to(ROOT)) not in OUT_OF_SCOPE)


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
    }


def _names_the_launcher(node: ast.expr) -> bool:
    text = ast.unparse(node)
    return "'scripts' / 'stayfixed'" in text or "scripts/stayfixed" in text or "LAUNCHER" in text


def is_launch(display: ast.List | ast.Tuple) -> bool:
    elements = display.elts
    if not elements:
        return False
    head = elements[0]
    if isinstance(head, ast.Constant | ast.JoinedStr):
        return False
    if isinstance(head, ast.Starred):
        call = head.value
        return isinstance(call, ast.Call) and getattr(call.func, "id", None) == "stayfixed_argv"
    text = ast.unparse(head)
    if "run-hook.sh" in text or "WRAPPER" in text or "wrapper" in text.lower():
        return True
    if not (text == "sys.executable" or isinstance(head, ast.Name)):
        return False
    rest = elements[1:4]
    if any(_names_the_launcher(element) for element in rest):
        return True
    words = [ast.unparse(element) for element in rest]
    return words[:2] == ["'-m'", "'stayfixed'"]


def _top_level(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def unseamed() -> dict[tuple[str, str], list[int]]:
    """Every launch that goes through no seam, by `(file, top-level function)`, with its lines."""
    found: dict[tuple[str, str], list[int]] = {}
    for path in _files():
        relative = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tops = _top_level(tree)
        seamed_here = {name for name, node in tops.items() if _names(node) & SEAMS}
        derived = relative in DERIVED
        for owner in tree.body:
            name = getattr(owner, "name", "<module>")
            reaches = _names(owner)
            through = bool(reaches & SEAMS) or bool(reaches & seamed_here) or derived
            for node in ast.walk(owner):
                if not isinstance(node, ast.List | ast.Tuple) or not is_launch(node):
                    continue
                head = node.elts[0]
                if isinstance(head, ast.Starred) or through:
                    continue
                found.setdefault((relative, name), []).append(node.lineno)
    return found


def test_every_stayfixed_a_test_starts_goes_through_the_owner_home_seam() -> None:
    found = unseamed()
    unexplained = {key: lines for key, lines in found.items() if key not in EXEMPT}
    assert unexplained == {}, (
        "a test or script starts stayfixed without choosing the password database's home; use "
        "tests/ownerhome.py's seam, or name the function in EXEMPT with why it reads no home"
    )
    stale = sorted(set(EXEMPT) - set(found))
    assert stale == [], "an EXEMPT entry excuses no launch"


def test_each_derived_script_derives_its_root_in_main() -> None:
    for relative in DERIVED:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        main = _top_level(tree).get("main")
        assert main is not None and "with_owner_home" in _names(main), relative


def test_each_indirect_launch_is_where_it_is_named() -> None:
    for relative, function in INDIRECT:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        owner = _top_level(tree).get(function)
        assert owner is not None, (relative, function)
        assert "run" in _names(owner) and "subprocess" in _names(owner), (relative, function)
        assert relative in DERIVED or _names(owner) & SEAMS, (relative, function)


def test_the_walk_reads_each_shape_it_claims_to() -> None:
    # The vacuity guard: each form the docstring names is a launch, and a list of file names whose
    # head is a literal is not, so an empty finding above is the seam's doing and not a blind walk.
    def launch(source: str) -> bool:
        display = ast.parse(source, mode="eval").body
        assert isinstance(display, ast.List | ast.Tuple)
        return is_launch(display)

    assert launch("[sys.executable, str(ROOT / 'scripts' / 'stayfixed'), 'hook']")
    assert launch("[sys.executable, '-S', str(LAUNCHER), '--version']")
    assert launch("[old, str(LAUNCHER), '--version']")
    assert launch("[sys.executable, '-m', 'stayfixed', 'hook', event]")
    assert launch("[str(root / 'hooks' / WRAPPER.name), 'open']")
    assert launch("[str(wrapper), *args]")
    assert launch("[*stayfixed_argv(home), 'hook']")
    assert not launch("('hooks/run-hook.sh', 'scripts/stayfixed')")
    assert not launch("[sys.executable, '-c', 'pass']")
