"""Every `stayfixed` a test or a script starts runs with the password database's home chosen.

Off a terminal stayfixed takes the machine owner's home from the password database and never
from `HOME` (`stayfixed.config.machine.owner_home`), so a scratch `HOME` no longer keeps a child
away from the developer's own `~/.config/stayfixed`. A child that forgets the seam does not fail:
it reads, or with `memory trust` writes, the developer's real files. So the seam is held here, by
reading the source rather than by running it, the way `tests/test_outbound.py` holds launches.

**What is read as a launch**, in every file under `tests/` and `scripts/`:

- a list or tuple display whose head is not a string literal and that starts stayfixed: the
  interpreter (`sys.executable`, or a name holding one) with the launcher (a path ending
  `scripts/stayfixed`, or `LAUNCHER`) among its next three elements, or with `-m stayfixed` at any
  position (`-I -m stayfixed` included); a head that names the hook wrapper (`run-hook.sh`, a name
  containing `wrapper`); a head built from the word `stayfixed` itself (the launcher run
  directly, `shutil.which("stayfixed")`); or `*stayfixed_argv(...)`, which is the seam itself;
- the first argument of a `subprocess` call, `os.system` or `os.popen`: a display with a literal
  head that is `stayfixed` or ends `/stayfixed` (the console script), `uv run stayfixed` or `uvx
  stayfixed`, `-m stayfixed`, or a wrapper path; and a string, as `shell=True` and those two take,
  that runs `stayfixed`, `-m stayfixed` or `run-hook.sh` as a word.

A display with a literal head anywhere else is data (a TOML key, a list of file names), and is
not read; nor is one whose head is a tuple, a dict or a list. A `*NAME` spread of a module-level
list or tuple is written out in its place (`[sys.executable, *M]`).

**What cannot be held from the source**, and why: an argv held in a local variable or a parameter,
which the walk would have to follow across calls (an argv a helper is handed, one `shlex.split`
builds), and a program name computed at run time. `INDIRECT` names the two such launches there
are, each held to exist and to sit under a seam; a new one has to be added there by hand.

**What counts as going through the seam**, launch by launch:

- the argv starts `*stayfixed_argv(...)`;
- or a name in its head is bound, in the function holding the launch, from a call to a seam
  (`SEAMS`) or to a function of the same file whose body calls one — `plugin = _plugin_root(walk)`;
- or the launch is in a function of a script `DERIVED` names, whose `main` derives the plugin root
  every such function is handed through `with_owner_home` (checked).

Anything else is a finding unless `EXEMPT` names the launch itself — its file, its function and
its argv as written — with the reason it reads no home. Both tables are held both ways: an entry
that excuses nothing is a finding too, since it is ready to excuse the next launch that matches.
"""

from __future__ import annotations

import ast
import itertools
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAMS = frozenset(
    {"stayfixed_argv", "plugin_root_with_owner_home", "checkout_with_owner_home", "with_owner_home"}
)
# This file, and the one that defines the seam for tests: what they spell is the seam.
OUT_OF_SCOPE = frozenset({"tests/test_owner_home_seam.py", "tests/ownerhome.py"})
LAUNCHING_CALLS = frozenset(
    {
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "os.system",
        "os.popen",
    }
)
# `stayfixed` as a word of a shell command: the console script, a path ending in it, `-m stayfixed`.
_SHELL_WORD = re.compile(r"(?:^|[\s/'\"])stayfixed(?=$|[\s'\"])|run-hook\.sh")

# `(file, function)` of a script whose `main` builds the plugin root these functions are handed.
DERIVED: dict[tuple[str, str], str] = {
    ("scripts/smoke_hooks.py", "trust_the_store"): "handed the root `main` derives",
    ("scripts/smoke_exfiltration.py", "plant"): "handed the root `main` derives",
    ("scripts/smoke_exfiltration.py", "stayfixed"): "handed the root `main` derives",
    ("scripts/smoke_exfiltration.py", "through_wrapper"): "handed the wrapper of the root `main` "
    "derives",
}

_FAKE = "the plugin root's launcher is `_plugin_root`'s fake, which runs no stayfixed"
# `(file, function, argv as written)`: launches that reach stayfixed and read no home, with why.
EXEMPT: dict[tuple[str, str, str], str] = {
    (
        "tests/hooks/test_wrapper.py",
        "_run",
        "[str(plugin_root / 'hooks' / WRAPPER.name), *argv]",
    ): "runs the wrapper of the plugin root its case passes: `_plugin_root`'s fake launcher, "
    "`plugin_root_with_owner_home`'s, or this checkout's for `--version`, which reads no home",
    (
        "tests/hooks/test_wrapper.py",
        "test_an_interpreter_the_environment_names_is_ignored_off_a_terminal",
        "[str(root / 'hooks' / WRAPPER.name), 'closed', 'hook', 'PreToolUse']",
    ): _FAKE,
    (
        "tests/hooks/test_wrapper.py",
        "test_the_project_root_is_never_taken_from_an_inherited_git_environment",
        "[str(root / 'hooks' / WRAPPER.name), 'open', 'hook', 'PreToolUse']",
    ): _FAKE,
    (
        "tests/hooks/test_wrapper.py",
        "test_the_wrapper_hands_its_git_the_database_home_and_never_an_inherited_one",
        "[str(root / 'hooks' / WRAPPER.name), 'open', 'hook', 'PreToolUse']",
    ): _FAKE,
    (
        "tests/hooks/test_wrapper.py",
        "test_the_wrapper_takes_id_from_any_absolute_candidate_and_never_a_name_the_environment_holds",
        "[str(root / 'hooks' / WRAPPER.name), 'open', 'hook', 'PreToolUse']",
    ): _FAKE,
    (
        "tests/hooks/test_wrapper.py",
        "test_a_project_root_that_cannot_be_entered_says_so",
        "[str(root / 'hooks' / WRAPPER.name), policy, 'hook', 'PreToolUse']",
    ): _FAKE,
    (
        "tests/hooks/test_wrapper.py",
        "test_stayfixed_runs_from_the_project_root",
        "[str(root / 'hooks' / WRAPPER.name), 'open', 'memory', 'session-context', '--bundle', "
        "'standing-rules']",
    ): "the plugin root's launcher is `_plugin_root`'s fake, which prints its directory",
    (
        "tests/test_cli.py",
        "test_module_entry_point_runs_without_the_console_script",
        "[sys.executable, '-m', 'stayfixed', '--version']",
    ): "`python -m stayfixed --version` is the case, and `--version` reads no home",
    (
        "tests/test_launcher.py",
        "test_the_launcher_runs_from_the_plugin_root",
        "[sys.executable, '-S', str(LAUNCHER), '--version']",
    ): "the launcher itself under `-S`, for `--version`, which reads no home",
    (
        "tests/test_launcher.py",
        "test_an_old_interpreter_is_refused_with_a_reason",
        "[old, str(LAUNCHER), '--version']",
    ): "the launcher's own interpreter floor, which refuses before stayfixed is imported",
}

# Launches whose argv is not a display the walk reads, by `(file, function)`.
INDIRECT: dict[tuple[str, str], str] = {
    ("scripts/smoke_hooks.py", "check_entry"): "each `hooks.json` command with the plugin root "
    "substituted, under the root `main` derives",
    (
        "tests/test_check_workflow.py",
        "_judge",
    ): "the workflow's own step script, under the checkout `checkout_with_owner_home` builds",
}


@dataclass(frozen=True)
class Launch:
    file: str
    function: str
    argv: str
    line: int
    seamed: bool


def _files() -> list[Path]:
    found = [*ROOT.glob("tests/**/*.py"), *ROOT.glob("scripts/*.py")]
    return sorted(f for f in found if str(f.relative_to(ROOT)) not in OUT_OF_SCOPE)


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
    }


def _called(node: ast.AST) -> set[str]:
    """The names of what `node` calls, by the called expression's last part."""
    called = set()
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            func = call.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name is not None:
                called.add(name)
    return called


def _names_the_launcher(node: ast.expr) -> bool:
    text = ast.unparse(node)
    return "'scripts' / 'stayfixed'" in text or "scripts/stayfixed" in text or "LAUNCHER" in text


def _words(elements: list[ast.expr]) -> list[str | None]:
    words: list[str | None] = []
    for element in elements:
        value = element.value if isinstance(element, ast.Constant) else None
        words.append(value if isinstance(value, str) else None)
    return words


def _runs_module(elements: list[ast.expr]) -> bool:
    return any(a == "-m" and b == "stayfixed" for a, b in itertools.pairwise(_words(elements)))


def _spread(elements: list[ast.expr], constants: dict[str, list[ast.expr]]) -> list[ast.expr]:
    """`elements` with each `*NAME` of a module-level list or tuple written out in its place."""
    spread: list[ast.expr] = []
    for element in elements:
        value = element.value if isinstance(element, ast.Starred) else None
        if isinstance(value, ast.Name) and value.id in constants:
            spread += constants[value.id]
        else:
            spread.append(element)
    return spread


def is_launch(
    display: ast.List | ast.Tuple,
    *,
    launched: bool = False,
    constants: dict[str, list[ast.expr]] | None = None,
) -> bool:
    """Whether `display` is an argv that starts stayfixed. `launched` says it is the first argument
    of a launching call, which is what lets a literal head be read as a program name."""
    elements = _spread(display.elts, constants or {})
    if not elements:
        return False
    head = elements[0]
    if isinstance(head, ast.Constant | ast.JoinedStr):
        if not (launched and isinstance(head, ast.Constant) and isinstance(head.value, str)):
            return False
        program = head.value
        words = _words(elements[1:4])
        return (
            program == "stayfixed"
            or program.endswith("/stayfixed")
            or program.endswith("run-hook.sh")
            or (program in {"uv", "uvx"} and "stayfixed" in words)
            or _runs_module(elements)
        )
    if isinstance(head, ast.Starred):
        call = head.value
        return isinstance(call, ast.Call) and getattr(call.func, "id", None) == "stayfixed_argv"
    # A program is a name, an attribute, a call or a path; a tuple, a dict or a list at the head
    # is data (a TOML key, a marketplace entry) whatever it spells.
    if not isinstance(head, ast.Name | ast.Attribute | ast.Call | ast.BinOp | ast.Subscript):
        return False
    text = ast.unparse(head)
    if "run-hook.sh" in text or "WRAPPER" in text or "wrapper" in text.lower():
        return True
    if text.rstrip(")").endswith("'stayfixed'"):
        return True
    if not (text == "sys.executable" or isinstance(head, ast.Name)):
        return False
    return any(_names_the_launcher(e) for e in elements[1:4]) or _runs_module(elements)


def _shell_launch(argument: ast.expr) -> bool:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return bool(_SHELL_WORD.search(argument.value))
    if isinstance(argument, ast.JoinedStr):
        literal = "".join(
            part.value
            for part in argument.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
        return bool(_SHELL_WORD.search(literal))
    return False


def _seamed_functions(tree: ast.Module) -> set[str]:
    """The functions of this file whose body calls a seam."""
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _called(node) & SEAMS
    }


def _bound_from_a_seam(function: ast.AST | None, head: ast.expr, seamed: set[str]) -> bool:
    """Whether a name in `head` is assigned, in `function`, from a call to a seam."""
    if function is None:
        return False
    wanted = {n.id for n in ast.walk(head) if isinstance(n, ast.Name)}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and _called(node.value) & (SEAMS | seamed):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & wanted:
                return True
    return False


def walk(relative: str, tree: ast.Module) -> list[Launch]:
    """Every launch in one file, each with its innermost function and whether it is seamed."""
    found: list[Launch] = []
    seamed_here = _seamed_functions(tree)
    constants = {
        target.id: list(node.value.elts)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List | ast.Tuple)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    # A launching call's first argument is read as such, with its literal head, and never again
    # as a display found on its own.
    firsts = {
        id(call.args[0])
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and ast.unparse(call.func) in LAUNCHING_CALLS and call.args
    }

    def record(display: ast.List | ast.Tuple, function: ast.AST | None, name: str) -> None:
        head = display.elts[0]
        seamed = (
            isinstance(head, ast.Starred)
            or _bound_from_a_seam(function, head, seamed_here)
            or (relative, name) in DERIVED
        )
        found.append(Launch(relative, name, ast.unparse(display), display.lineno, seamed))

    def visit(node: ast.AST, function: ast.AST | None, name: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                visit(child, child, child.name)
                continue
            if isinstance(child, ast.Call) and ast.unparse(child.func) in LAUNCHING_CALLS:
                first = child.args[0] if child.args else None
                if isinstance(first, ast.List | ast.Tuple):
                    if is_launch(first, launched=True, constants=constants):
                        record(first, function, name)
                elif first is not None and _shell_launch(first):
                    found.append(Launch(relative, name, ast.unparse(first), first.lineno, False))
            elif isinstance(child, ast.List | ast.Tuple) and id(child) not in firsts:
                if is_launch(child, constants=constants):
                    record(child, function, name)
            visit(child, function, name)

    visit(tree, None, "<module>")
    return found


def launches() -> list[Launch]:
    found: list[Launch] = []
    for path in _files():
        found += walk(str(path.relative_to(ROOT)), ast.parse(path.read_text(encoding="utf-8")))
    return found


def test_every_stayfixed_a_test_starts_goes_through_the_owner_home_seam() -> None:
    found = [launch for launch in launches() if not launch.seamed]
    keys = {(launch.file, launch.function, launch.argv) for launch in found}
    unexplained = sorted(
        (launch.file, launch.line, launch.argv)
        for launch in found
        if (launch.file, launch.function, launch.argv) not in EXEMPT
    )
    assert unexplained == [], (
        "a test or script starts stayfixed without choosing the password database's home; use "
        "tests/ownerhome.py's seam, or name the launch in EXEMPT with why it reads no home"
    )
    assert sorted(set(EXEMPT) - keys) == [], "an EXEMPT entry excuses no launch"


def test_each_derived_function_is_one_its_script_hands_the_derived_root() -> None:
    used = {(launch.file, launch.function) for launch in launches()}
    for relative, function in DERIVED:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        tops = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        assert "main" in tops and "with_owner_home" in _called(tops["main"]), relative
        assert (relative, function) in used, (relative, function)


def test_each_indirect_launch_is_where_it_is_named() -> None:
    for relative, function in INDIRECT:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        owner = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}.get(function)
        assert owner is not None, (relative, function)
        assert "run" in _names(owner) and "subprocess" in _names(owner), (relative, function)
        tops = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        derived = "main" in tops and "with_owner_home" in _called(tops["main"])
        assert derived or _names(owner) & SEAMS, (relative, function)


def _probe(source: str) -> list[tuple[str, bool]]:
    """What the walk makes of `source` as a test file of its own: each launch, and if seamed."""
    return [(launch.argv, launch.seamed) for launch in walk("tests/probe.py", ast.parse(source))]


def test_the_walk_reads_each_shape_it_claims_to() -> None:
    # The vacuity guard: each shape the docstring names is read as a launch, unseamed, while
    # data that only looks like one (a TOML key, a list of file names) is not, so an empty
    # finding above is the seam's doing and not a blind walk.
    unseamed = [
        "[sys.executable, str(ROOT / 'scripts' / 'stayfixed'), 'hook']",
        "[sys.executable, '-S', str(LAUNCHER), '--version']",
        "[old, str(LAUNCHER), '--version']",
        "[sys.executable, '-m', 'stayfixed', 'hook']",
        "[sys.executable, '-I', '-m', 'stayfixed', 'hook']",
        "[str(root / 'hooks' / WRAPPER.name), 'open']",
        "[str(wrapper), 'open']",
        "[str(ROOT / 'scripts' / 'stayfixed'), 'hook']",
        "[shutil.which('stayfixed'), 'hook']",
    ]
    for argv in unseamed:
        assert _probe(f"def f():\n    x = {argv}\n") == [(argv, False)], argv
    for argv in (
        "['stayfixed', 'hook']",
        "['uv', 'run', 'stayfixed', 'hook']",
        "['/x/bin/stayfixed']",
    ):
        assert _probe(f"def f():\n    subprocess.run({argv})\n") == [(argv, False)], argv
    spread = "M = ['-m', 'stayfixed']\ndef f():\n    subprocess.run([sys.executable, *M])\n"
    assert _probe(spread) == [("[sys.executable, *M]", False)]
    shell = "'stayfixed memory trust'"
    assert _probe(f"def f():\n    subprocess.run({shell}, shell=True)\n") == [(shell, False)]
    assert _probe("def f():\n    subprocess.run(['echo', 'stayfixed.toml'])\n") == []
    assert _probe("def f():\n    x = ('stayfixed', 'state')\n") == []
    assert _probe("def f():\n    x = ('hooks/run-hook.sh', 'scripts/stayfixed')\n") == []
    assert _probe("def f():\n    x = [sys.executable, '-c', 'pass']\n") == []


def test_a_seam_counts_for_the_launch_it_reaches_and_no_other() -> None:
    # Per launch, not per function: a seam beside an unseamed launch excuses nothing, and a head
    # bound from a seam, or from a function of the file that calls one, is seamed.
    beside = (
        "def f(home):\n"
        "    subprocess.run([*stayfixed_argv(home), 'hook'])\n"
        "    subprocess.run([sys.executable, '-m', 'stayfixed', 'memory', 'trust'])\n"
    )
    assert [seamed for _, seamed in _probe(beside)] == [True, False]
    bound = (
        "def helper(base, home):\n"
        "    return plugin_root_with_owner_home(base, home)\n"
        "def f(base, home):\n"
        "    plugin = helper(base, home)\n"
        "    subprocess.run([str(plugin / 'hooks' / WRAPPER.name), 'open'])\n"
        "    other = base\n"
        "    subprocess.run([str(other / 'hooks' / WRAPPER.name), 'open'])\n"
    )
    assert [seamed for _, seamed in _probe(bound)] == [True, False]


# The roots a `_run` in the wrapper tests may run under: a fake launcher that runs no stayfixed,
# or a root whose launcher pins the database's home.
_WRAPPER_TESTS = "tests/hooks/test_wrapper.py"
_FAKE_OR_SEAMED = frozenset({"_plugin_root", "plugin_root_with_owner_home"})


def _wrapper_runs() -> list[tuple[int, str, bool]]:
    """Every `_run(...)` call in the wrapper tests: its line, its `plugin_root=`, and whether that
    root reads no home — a fake or seamed root, or this checkout's for `--version` alone. A name
    counts as such a root where the function holding the call, or one enclosing it, binds it so."""
    tree = ast.parse((ROOT / _WRAPPER_TESTS).read_text(encoding="utf-8"))
    found: list[tuple[int, str, bool]] = []

    def binds(function: ast.AST) -> set[str]:
        return {
            target.id
            for node in ast.walk(function)
            if isinstance(node, ast.Assign) and _called(node.value) & _FAKE_OR_SEAMED
            for target in node.targets
            if isinstance(target, ast.Name)
        }

    def judge(call: ast.Call, bound: set[str]) -> None:
        root = next((k.value for k in call.keywords if k.arg == "plugin_root"), None)
        if root is None:
            found.append((call.lineno, "<none>", False))
            return
        words = {a.value for a in call.args if isinstance(a, ast.Constant)}
        only_version = all(isinstance(a, ast.Constant) for a in call.args) and words - {
            "open",
            "closed",
        } == {"--version"}
        safe = (
            bool(_called(root) & _FAKE_OR_SEAMED)
            or (isinstance(root, ast.Name) and root.id in bound)
            or (isinstance(root, ast.Name) and root.id == "ROOT" and only_version)
        )
        found.append((call.lineno, ast.unparse(root), safe))

    def visit(node: ast.AST, bound: set[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef):
                visit(child, bound | binds(child))
                continue
            if isinstance(child, ast.Call) and getattr(child.func, "id", None) == "_run":
                judge(child, bound)
            visit(child, bound)

    visit(tree, set())
    return found


def test_every_wrapper_run_uses_a_root_that_reads_no_home() -> None:
    # `EXEMPT` excuses `_run` for every caller, so what it excuses is held here instead: each
    # call's plugin root is `_plugin_root`'s fake, a seamed root, or this checkout's with
    # `--version` and nothing else. A new real launch through `_run` is a finding, not an excuse.
    runs = _wrapper_runs()
    assert len(runs) > 20, runs
    assert [(line, root) for line, root, safe in runs if not safe] == []
