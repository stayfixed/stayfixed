"""The delivery rule: the core never reaches the private layer — `attach`, `memory` and `overlay`
— by an import statement, by what loads when a core module is imported, by a module named in a
string, or through the import machinery, but for the crossings pinned here with their reasons."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest

import stayfixed.areas
from tests.boundaries import astscan

ROOT = Path(__file__).resolve().parents[2]


# Every import by which a core module reaches a delivery area today, one row per import statement:
# the importing file relative to `src/stayfixed/`, the module the statement names cut to three
# dotted parts, and the names it takes out of that module. Held as a multiset and by equality in
# both directions, so a new crossing reddens the test, and so do a row whose import has gone, a
# second statement beside a pinned one, and a pinned statement that takes one more name: the pardon
# covers exactly the statements and names written here, and cutting a crossing is deleting its rows
# in the same commit.
#
# One crossing is left, and it is meant to stay. `stayfixed setup --overlay` creates or records the
# private overlay as the last step of machine setup, so `setup/run.py` calls into the overlay area
# by design, and its rows stay until that step leaves `setup`: one statement in
# `_requested_overlay`, which refuses before the first write, and one in `_apply_overlay`, which
# creates and records. Both sit inside the functions, so importing `setup` — which `doctor` does —
# loads none of it (`test_in_isolation_no_core_module_loads_a_delivery_area`).
CORE_TO_DELIVERY = (
    (
        "setup/run.py",
        "stayfixed.overlay.api",
        frozenset({"require_overlay", "target_root"}),
    ),
    (
        "setup/run.py",
        "stayfixed.overlay.api",
        frozenset({"create", "init_instance", "overlay_fault", "require_overlay"}),
    ),
)

DeliveryRow = tuple[str, str, frozenset[str]]


def _delivery_offences(where: str, text: str, areas: frozenset[str]) -> list[DeliveryRow]:
    """The delivery rule, for one file: every import statement by which a core module reaches a
    delivery area, as `(where, module, names)` with the module cut to three dotted parts.

    One row per import statement, keyed on the module the statement names and never on its
    aliases: `astscan.imported_modules` also yields `stayfixed.overlay.api.create` for every name a
    `from` imports, which would turn one import of four names into four rows. The names are the
    row's third part instead, as written, so a pardon is for one statement and what it takes; a
    statement that imports a module itself (`import stayfixed.overlay.api`) takes no names. The
    one spelling whose aliases are the modules is `from stayfixed import memory`, and it is read
    as such: a row per area, importing the area itself. A module is core when the first part of
    its path is not a delivery area, so `cli.py`, `config/` and every other subpackage that is not
    an area are core too. Delivery importing core, or delivery importing delivery, is not this
    rule's business.
    """
    parts = Path(where).parts
    core = parts[0] not in areas
    rows: list[DeliveryRow] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            taken = [(alias.name, frozenset[str]()) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # `astscan.imported_modules` yields the statement's own module first, resolved when
            # the import is relative, and then one name per alias.
            module = astscan.imported_modules(node, ("stayfixed", *parts[:-1]))[0][1]
            taken = [(module, frozenset(alias.name for alias in node.names))]
            if module == "stayfixed":
                taken = [(f"{module}.{alias.name}", frozenset[str]()) for alias in node.names]
        else:
            continue
        for module, names in taken:
            bits = module.split(".")
            delivery = bits[0] == "stayfixed" and len(bits) > 1 and bits[1] in areas
            if core and delivery:
                rows.append((where, ".".join(bits[:3]), names))
    return rows


def test_core_never_imports_delivery() -> None:
    # CONTRIBUTING, "Areas": the delivery areas may import the core, and the core may not import
    # them, through `api.py` or not, at module level or inside a function, but for the statements
    # `CORE_TO_DELIVERY` pins. The walk is the whole package, so the equality below also fails on
    # a walk that stopped walking: it would find no rows, and the pinned rows are never empty.
    #
    # Mutation (declared): `mutations/`'s "setup imports one more name from the overlay area in a
    # statement of its own", which a comparison of `(file, module)` sets let through.
    source = ROOT / "src" / "stayfixed"
    rows: list[DeliveryRow] = []
    for path in sorted(source.rglob("*.py")):
        rows += _delivery_offences(
            path.relative_to(source).as_posix(),
            path.read_text(encoding="utf-8"),
            stayfixed.areas.DELIVERY_AREAS,
        )
    assert len(CORE_TO_DELIVERY) == 2
    found, pinned = Counter(rows), Counter(CORE_TO_DELIVERY)
    assert found == pinned, {"unpinned": found - pinned, "gone": pinned - found}


# Imports every module it is handed, then prints every `stayfixed` module the interpreter loaded.
IMPORT_EACH = (
    "import importlib, sys\n"
    "for name in sys.argv[1:]:\n"
    "    importlib.import_module(name)\n"
    "print(' '.join(sorted(m for m in sys.modules if m.startswith('stayfixed'))))\n"
)


def core_files(source: Path) -> list[tuple[str, Path]]:
    """Every core file under `source`, relative to it: each module outside the delivery areas,
    `cli.py` and the subpackages that are not areas included."""
    return [
        (path.relative_to(source).as_posix(), path)
        for path in sorted(source.rglob("*.py"))
        if path.relative_to(source).parts[0] not in stayfixed.areas.DELIVERY_AREAS
    ]


def test_in_isolation_no_core_module_loads_a_delivery_area() -> None:
    # The source rule above reads statements, and a statement inside a function is pardoned there
    # because it is the pinned crossing. What it cannot see is when that statement runs: the
    # crossing stood at module level in `setup/run.py`, `setup/api.py` re-exports from that
    # module, and `doctor/entries.py` imported `setup.api` for `USER_SETTINGS` — so importing
    # `doctor`'s report loaded `overlay.api`, `overlay.create`, `memory.store` and the rest of the
    # private layer, with every rule green. So every core module is imported in one clean
    # interpreter, which loads the union of their import closures, and no delivery module may be
    # among what it loaded: the private layer is loaded by the core only when a command asks for
    # it, here `setup --overlay`.
    #
    # Mutation (declared): `mutations/`'s "setup loads the overlay area at import again".
    source = ROOT / "src" / "stayfixed"
    # Every core module, dotted. `__main__` is left out because importing it runs the CLI: its
    # whole body is `main()`.
    modules = [
        ".".join(("stayfixed", *Path(where).with_suffix("").parts)).removesuffix(".__init__")
        for where, _ in core_files(source)
        if Path(where).name != "__main__.py"
    ]
    # The walk names the modules the crossing reached, so a list that stopped holding them
    # cannot keep this green.
    assert {
        "stayfixed.cli",
        "stayfixed.doctor.api",
        "stayfixed.doctor.checks",
        "stayfixed.setup.api",
        "stayfixed.setup.run",
    } <= set(modules), modules
    completed = subprocess.run(
        [sys.executable, "-c", IMPORT_EACH, *modules],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(source.parent)},
    )
    assert completed.returncode == 0, completed.stderr
    loaded = completed.stdout.split()
    assert "stayfixed.doctor.checks" in loaded, "the probe imported nothing"
    delivery = [
        name
        for name in loaded
        if name.split(".")[1:2] and name.split(".")[1] in stayfixed.areas.DELIVERY_AREAS
    ]
    assert delivery == []


def test_the_delivery_areas_are_attach_memory_and_overlay() -> None:
    # The three areas CONTRIBUTING's "Areas" names as delivery, pinned as a literal rather than
    # read back: the crossing meant to stay exercises only `overlay`, so a change that dropped
    # `memory` or `attach` from the constant beside a new crossing into it would otherwise keep
    # `test_core_never_imports_delivery` green.
    #
    # Mutation (declared): `mutations/`'s "memory stops being a delivery area".
    declared = stayfixed.areas.DELIVERY_AREAS
    assert declared == frozenset({"attach", "memory", "overlay"})


def test_the_delivery_rule_judges_the_importer_and_the_imported() -> None:
    # The walk above can only show the rule holding for the imports the tree happens to make, so
    # the rule is put in front of spellings the tree does not carry. A core module reaching a
    # delivery area relatively and from inside a function is an offence, named exactly; a
    # delivery module reaching another delivery area is not, because only the core is held.
    #
    # Mutations (declared): `mutations/`'s "the delivery rule stops recognising a delivery
    # module", which reddens the first arm, and "the delivery rule holds a delivery module to the
    # core's rule", which reddens the second.
    delivery = frozenset({"attach", "memory", "overlay"})
    assert _delivery_offences(
        "docs/commands.py", "def check():\n    from ..memory import api\n", delivery
    ) == [("docs/commands.py", "stayfixed.memory", frozenset({"api"}))]
    assert _delivery_offences("memory/x.py", "import stayfixed.overlay.api\n", delivery) == []

    # The one spelling whose module is the package itself, so the area is in an alias: read by
    # alias, and only for that spelling. Mutation (declared): `mutations/`'s "the delivery rule
    # reads `from stayfixed import memory` as importing nothing".
    assert _delivery_offences("cli.py", "from stayfixed import ledger, memory\n", delivery) == [
        ("cli.py", "stayfixed.memory", frozenset())
    ]

    # Two statements naming one module are two rows, each with the names it takes, so a pardon
    # for one statement is never a pardon for a second one beside it. Mutation (declared):
    # `mutations/`'s "the delivery rule forgets which names a statement takes".
    two = "from stayfixed.overlay.api import create\nfrom stayfixed.overlay.api import create\n"
    assert _delivery_offences("setup/run.py", two, delivery) == [
        ("setup/run.py", "stayfixed.overlay.api", frozenset({"create"})),
        ("setup/run.py", "stayfixed.overlay.api", frozenset({"create"})),
    ]
    assert _delivery_offences(
        "setup/run.py", "from stayfixed.overlay.api import create, target_root\n", delivery
    ) == [("setup/run.py", "stayfixed.overlay.api", frozenset({"create", "target_root"}))]


# The names through which a module is loaded without an import statement of its own, which the
# delivery rule above reads no more than discovery's caller does: `import_module` and `__import__`
# import by a string, a module's own `__spec__` and `__loader__` and the finders on `sys`'s
# `meta_path`, `path_hooks` and `path_importer_cache` load a module by its file with no import at
# all, and `sys.breakpointhook` and `sys.__breakpointhook__` import whatever `PYTHONBREAKPOINT`
# names. Each is read as an attribute of anything, as a bare name, and inside a string constant
# that is not a docstring: a message that names one is a row, to pin or to reword.
DYNAMIC_IMPORTS = frozenset(
    {
        "__breakpointhook__",
        "__import__",
        "__loader__",
        "__spec__",
        "breakpointhook",
        "import_module",
        "meta_path",
        "path_hooks",
        "path_importer_cache",
    }
)
# The builtins that run code built from text, and the module that holds every builtin, which hands
# `__import__` over by a computed name. Read as a bare name unless, by Python's scoping, it resolves
# to a function's own binding, a comprehension's variable or an import from any module but
# `builtins`, in that scope or one around it; as a binding made in a module or a class body, which
# Python looks up at run time, so that the binding may not have run, may have been deleted, or may
# be the builtin itself (`exec = exec`), and which therefore hides nothing and is a row to pin or
# rename; under any alias `from builtins import` gives one; and as a whole string constant (a
# choice spelled `"eval"` is a row too, to pin or to reword). Not as an attribute: `compile` is
# `re.compile` there, and `builtins.exec` needs `builtins`, which the machinery rule below holds.
# `__builtins__` is the exception: every module carries it, so it is read as an attribute of
# anything (`json.__builtins__`), and a `from` of it from any module is a row, under any alias.
TEXT_RUNNERS = frozenset({"__builtins__", "breakpoint", "compile", "eval", "exec"})

# The one core module whose job is importing modules by name: discovery, which imports
# `stayfixed.<area>.<submodule>` for the submodules `area_modules` is called with (held below), and
# is how every area, delivery included, plugs into the core.
DISCOVERY_MODULE = "areas.py"
# What discovery itself reads of the names below, by function: its two imports by name.
DISCOVERY_READS = (("area_modules", "import_module"), ("area_imports", "import_module"))

# Every other place a core module imports by a string, one row per reference: the file relative to
# `src/stayfixed/`, the innermost function, and the name it reaches. Held as a multiset and by
# equality in both directions, as `CORE_TO_DELIVERY` is.
#
# One row, meant to stay. `profiles/hints.py`'s `_hint` imports `stayfixed.profiles.<name>.hygiene`
# for a `name` that `hint_modules` listed from this package's own shipped profiles through
# `importlib.resources` — profile discovery, which CONTRIBUTING's "Areas" describes beside area
# discovery. It names no area and no repository path, so it is pinned here rather than moved into
# `areas.py`, which knows nothing of profiles.
DYNAMIC_IMPORTERS = (("profiles/hints.py", "_hint", "import_module"),)


def _dynamic_imports(tree: ast.Module) -> list[tuple[str, str]]:
    """Every reference in `tree` to a `DYNAMIC_IMPORTS` or `TEXT_RUNNERS` name, as `(function,
    name)`, `function` being the innermost enclosing `def` or `<module>`.

    Read as: a `DYNAMIC_IMPORTS` name as an attribute of anything (`importlib.import_module`,
    `builtins.__import__`, `sys.meta_path`, `module.__spec__`), by its bare name, by any name a
    `from … import` binds it to, and anywhere inside a string constant that is not a docstring,
    which covers `getattr(importlib, "import_module")` and a string annotation that
    `typing.get_type_hints` would evaluate; a `TEXT_RUNNERS` name by its bare name unless it
    resolves, by Python's scoping (`astscan.shadowed`), to a binding that hides it
    (`astscan.scope_bindings`: a function's local or parameter, a comprehension's variable, or an
    import from any module but `builtins`), by any name `from builtins import` binds it to (`from`
    any module, for `__builtins__`, which is also read as an attribute of anything), as a whole
    string constant, which is how `getattr(builtins, "exec")` spells it, and as a binding that
    lands in a module or a class body (`exec = exec`, `del exec`, `def breakpoint`, a walrus in a
    module-level comprehension), which Python looks up at run time. The `from` statement itself is
    a row: of any module for a `DYNAMIC_IMPORTS` name or `__builtins__`, of `builtins` for another
    `TEXT_RUNNERS` one, and `from importlib import *`. A docstring, or any string standing alone as
    a statement, is prose and is not read (`astscan.walk`).
    """

    def binds(node: ast.ImportFrom, names: frozenset[str]) -> list[ast.alias]:
        if names is TEXT_RUNNERS and node.module != "builtins":
            return [alias for alias in node.names if alias.name == "__builtins__"]
        return [alias for alias in node.names if alias.name in names]

    bound = set(DYNAMIC_IMPORTS) | {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for names in (DYNAMIC_IMPORTS, TEXT_RUNNERS)
        for alias in binds(node, names)
    }
    walrus = {id(node.target) for node in ast.walk(tree) if isinstance(node, ast.NamedExpr)}
    found: list[tuple[str, str]] = []

    for child, function, chain in astscan.walk(tree):
        if isinstance(child, ast.Attribute) and (
            child.attr in DYNAMIC_IMPORTS or child.attr == "__builtins__"
        ):
            found.append((function, child.attr))
        elif isinstance(child, ast.Name) and (
            child.id in bound
            or (
                child.id in TEXT_RUNNERS
                and type(child.ctx) is ast.Load
                and not astscan.shadowed(child.id, chain)
            )
        ):
            found.append((function, child.id))
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            if child.value in TEXT_RUNNERS:
                found.append((function, child.value))
            found.extend(
                (function, name) for name in sorted(DYNAMIC_IMPORTS) if name in child.value
            )
        elif isinstance(child, ast.ImportFrom) and (
            binds(child, DYNAMIC_IMPORTS)
            or binds(child, TEXT_RUNNERS)
            or (child.module == "importlib" and any(a.name == "*" for a in child.names))
        ):
            found.append((function, f"from {child.module} import"))
        elif (
            (binding := astscan.bound_name(child)) is not None
            and binding in TEXT_RUNNERS
            and astscan.binds_at_run_time(binding, chain, walrus=id(child) in walrus)
        ):
            found.append((function, binding))
    return found


def test_no_core_module_imports_by_a_string_but_discovery() -> None:
    # The delivery rule reads import statements, so a function-level
    # `importlib.import_module("stayfixed.memory.store")` or `__import__(...)` in a core file
    # crossed into the private layer with every boundary test green. A string import in the core
    # is discovery's alone, and the one other one — profile discovery — is pinned with its reason.
    # So were a module's own loader (`type(__spec__.loader)(name, path).exec_module(module)`), a
    # finder on `sys.meta_path`, and `exec` of a string that imports. This reads those names; the
    # standard library's other ways to import by a string are held where they must be imported
    # from, by `test_no_core_module_reaches_the_import_machinery_…`.
    #
    # Mutations (declared): `mutations/`'s "a core function imports the note store through
    # importlib", "a core function imports the note store through __import__", "a core function
    # imports the note store through an alias of import_module", "a core function loads the note
    # store through its own module's loader", "a core function loads the note store through a
    # finder on sys.meta_path", "a core function imports the note store by running text", "a core
    # function reaches __import__ through __builtins__" and "a core function's string annotation
    # imports the note store".
    source = ROOT / "src" / "stayfixed"
    rows: list[tuple[str, str, str]] = []
    discovery: list[tuple[str, str]] = []
    for where, path in core_files(source):
        found = _dynamic_imports(ast.parse(path.read_text(encoding="utf-8")))
        if where == DISCOVERY_MODULE:
            discovery += found
        else:
            rows += [(where, function, name) for function, name in found]
    # Discovery's exemption is its two `importlib.import_module` calls and nothing else, so an
    # `exec` or a `sys.meta_path` read in `areas.py` is caught like one anywhere else, and a reader
    # that stopped seeing the spelling the pardon is written in cannot pass by finding nothing.
    assert Counter(discovery) == Counter(DISCOVERY_READS), discovery
    found_rows, pinned = Counter(rows), Counter(DYNAMIC_IMPORTERS)
    assert found_rows == pinned, {"unpinned": found_rows - pinned, "gone": pinned - found_rows}


def test_the_string_import_rules_read_every_spelling() -> None:
    # The walk above can only show the rule holding for the spellings the tree carries, so it is
    # put in front of the ones it does not. Measured by hand: reading `from importlib import`
    # aliases no more reddens the first assertion, and dropping the string-constant arm the
    # second. In `texts`, dropping the attribute arm of `_dynamic_imports`, any one of its names,
    # the bare reading of `TEXT_RUNNERS`, their whole constant arm, the substring arm, reading
    # `from` statements of `importlib` alone, or reading `__builtins__` as no attribute or in a
    # `from` of `builtins` alone each reddens it. In `quiet`, reading docstrings, reading a
    # `TEXT_RUNNERS` `from` of any module, or reading a name the file binds itself (a local, a
    # parameter, an import) each reddens it. In `scoped`, hiding a builtin wherever the file binds
    # its name, letting a class body be seen by its methods, not following `global`, letting a
    # `global` alone hide the builtin, giving a comprehension no scope, binding no parameter,
    # reading a store as a use, or reading a function's annotations in its own scope each reddens
    # it. In `generic`, on 3.12 and later, leaving a function's or a class's type parameters
    # unread reddens it. The scoping is `tests/boundaries/astscan.py`'s, whose own cases hold it
    # too. Mutations (declared): `mutations/`'s "the name rule hides a builtin across the whole
    # file again", "a module or a class body hides a builtin by any binding again", "a binding of a
    # text runner in a module or a class body is no row", "a function's store of a text runner
    # under global is no row", "a walrus in a comprehension binds in the comprehension", "a walrus
    # target is taken to land in its comprehension", "import builtins under a text runner's name
    # hides the builtin", "a function's type parameters are not read", "a class's type parameters
    # are not read", "__builtins__ read off another module is no row" and "a from of __builtins__
    # out of another module is no row".
    aliased = "from importlib import import_module as load\ndef f():\n    load('x')\n"
    assert _dynamic_imports(ast.parse(aliased)) == [
        ("<module>", "from importlib import"),
        ("f", "load"),
    ]
    reflected = "import importlib\ndef f():\n    getattr(importlib, 'import_module')('x')\n"
    assert _dynamic_imports(ast.parse(reflected)) == [("f", "import_module")]
    texts = (
        "def f(x: \"__import__('stayfixed.memory.store')\"):\n    type(__spec__.loader)\n"
        "    sys.meta_path\n    m.__loader__\n    getattr(importlib, 'import_module')\n"
        "exec(text)\ngetattr(builtins, 'eval')\nfrom builtins import compile as c\nbreakpoint()\n"
        "__builtins__\nre.compile('x')\nfrom sys import path_hooks\nsys.path_importer_cache\n"
        "sys.breakpointhook(None, None)\nsys.__breakpointhook__\n"
        "json.__builtins__\nfrom re import __builtins__ as b\nb\n"
    )
    assert sorted(_dynamic_imports(ast.parse(texts))) == [
        ("<module>", "__breakpointhook__"),
        ("<module>", "__builtins__"),
        ("<module>", "__builtins__"),
        ("<module>", "__import__"),
        ("<module>", "b"),
        ("<module>", "breakpoint"),
        ("<module>", "breakpointhook"),
        ("<module>", "eval"),
        ("<module>", "exec"),
        ("<module>", "from builtins import"),
        ("<module>", "from re import"),
        ("<module>", "from sys import"),
        ("<module>", "path_importer_cache"),
        ("f", "__loader__"),
        ("f", "__spec__"),
        ("f", "import_module"),
        ("f", "meta_path"),
    ]
    # Prose and a name of the file's own are not the builtin: a docstring naming a finder, a
    # `compile` imported from another module under its name or an alias, and a parameter or a
    # local named after a builtin that runs text.
    quiet = (
        '"""Names no finder on sys.meta_path."""\n'
        "from re import compile as _c\n_R = _c('x')\nfrom re import compile\ncompile('y')\n"
        "def f(eval):\n    exec = 1\n    return eval, exec\n"
    )
    assert _dynamic_imports(ast.parse(quiet)) == []
    # A function's binding hides a builtin in that function and the scopes it encloses, never
    # beyond: the builtin read in another function, beside a comprehension's variable, in a method
    # beside a class attribute, or after another function's `global` names it, is still the
    # builtin, while a nested function reading its enclosing function's parameter, and a function
    # reading what a walrus in its comprehension bound, read the file's own. A binding that lands
    # in a module or a class body is a row of its own and hides nothing, since Python looks it up
    # at run time: a class attribute, a store under `global`, `__builtins__ = {}`, `exec = exec`
    # and a walrus in a module-level comprehension. `import builtins` under the name hides nothing.
    scoped = (
        "def g(exec):\n    return exec\nexec('x')\n"
        "_ = [0 for eval in ()]\ndef h():\n    return eval('x')\n"
        "class K:\n    compile = len\n    def m(self):\n        return compile('x')\n"
        "def r():\n    global breakpoint\n    breakpoint = print\ndef s():\n    breakpoint()\n"
        "def outer(compile):\n    def inner():\n        return compile\n    return inner\n"
        "__builtins__ = {}\ndef t():\n    return __builtins__\n"
        "def u(exec):\n    def v():\n        global exec\n        return exec('x')\n    return v\n"
        "exec = exec\n_ = [(eval := e) for e in ()]\n"
        "def w():\n    _ = [(compile := c) for c in ()]\n    return compile('x')\n"
        "import builtins as breakpoint\nbreakpoint.exec('x')\n"
    )
    assert sorted(_dynamic_imports(ast.parse(scoped))) == [
        ("<module>", "__builtins__"),
        ("<module>", "breakpoint"),
        ("<module>", "compile"),
        ("<module>", "eval"),
        ("<module>", "exec"),
        ("<module>", "exec"),
        ("<module>", "exec"),
        ("h", "eval"),
        ("m", "compile"),
        ("r", "breakpoint"),
        ("s", "breakpoint"),
        ("t", "__builtins__"),
        ("v", "exec"),
    ]
    # Type parameters are evaluated around the `def` or `class` they belong to. The syntax is
    # 3.12's, so this case is parsed from text there and has nothing to read on 3.11.
    if sys.version_info >= (3, 12):
        generic = "def f[T: exec('x')]():\n    pass\nclass C[T: __import__('x')]:\n    pass\n"
        assert _dynamic_imports(ast.parse(generic)) == [
            ("<module>", "exec"),
            ("<module>", "__import__"),
        ]


# The standard library modules a core module may import with no row, by name or as a package whose
# submodules are all allowed: the 34 the core imports today, each one whose public functions import
# no module named by a string and run no code built from text but through a name the rule above
# reads (`sys.breakpointhook`, `typing.get_type_hints` of a string spelling `__import__`). Every
# other module is the machinery: a core import of one is a row of `MACHINERY_IMPORTERS` below, with
# what the file reaches in it.
# Read the other way round, a deny-list of the modules that can import by a string stayed open to
# every one nobody had measured yet (`timeit`, `xml.dom.pulldom`'s `xml.sax`, `inspect`'s
# `importlib`, `builtins`). `importlib` and `pkgutil` are not on the list: discovery imports through
# them, and their rows say what each file reaches. `urllib` is listed as `urllib.parse`: an import
# of any other submodule of it is a row, while a read off the `urllib` that `import urllib.parse`
# binds is not judged, since no read off an allowed import is (an attribute chain, below).
#
# This rule and the name rule above are a tripwire, not a proof: they read import statements and a
# list of names, so they catch a crossing written the ordinary way and prove nothing about one
# written to hide. What they cannot read: an attribute chain through an allowed module
# (`dataclasses.inspect.importlib`, `typing.sys.modules`), a module already in `sys.modules`, a
# loader or a finder reached by a computed name (`getattr(sys, "meta" + "_path")`), an import in a
# module or a class body that fails and is caught, which hides a builtin the name rule then takes
# for the file's own, code built from text at run time, and a string an allowed module evaluates
# (`typing.get_type_hints` of an annotation built at run time).
# `test_in_isolation_no_core_module_loads_a_delivery_area` sees what loads at import time and
# nothing a function does later.
STANDARD_IMPORTS = frozenset(
    {
        "__future__",
        "argparse",
        "collections",
        "configparser",
        "contextlib",
        "copy",
        "dataclasses",
        "datetime",
        "enum",
        "errno",
        "functools",
        "hashlib",
        "io",
        "itertools",
        "json",
        "os",
        "pathlib",
        "posixpath",
        "pwd",
        "re",
        "shlex",
        "shutil",
        "signal",
        "stat",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tempfile",
        "time",
        "tomllib",
        "types",
        "typing",
        "urllib.parse",
    }
)
# `importlib.resources` reads package data, and imports a module only as the anchor `files` is
# handed: given a module's name, it imports that module. So it is outside the rule for exactly two
# reads, which import nothing that is not already loaded. One is `files` called on the package
# itself, `__package__` (a core module's own package) or the literal `"stayfixed"`, in a module
# that never binds `__package__` itself. The other is `importlib.resources.abc`, which holds types.
# Every other read of it, the same function given any other argument, the module handed on and the
# functions that take an anchor of their own (`read_text`, `open_binary` …), is the machinery.
RESOURCES = "importlib.resources"

# Every core import of a module off `STANDARD_IMPORTS`, one row per statement: the file relative
# to `src/stayfixed/`, the module the statement names, and what the file reaches through it -- the
# names a `from` statement takes, or each attribute path read off the name an `import` binds
# (`<value>` when the name itself is handed on, where anything could be read off it). Held as a
# multiset and by equality in both directions, as `DYNAMIC_IMPORTERS` is.
MACHINERY_IMPORTERS = (
    # Discovery: imports `stayfixed.<area>.<submodule>` by name, and lists the areas.
    ("areas.py", "importlib", frozenset({"import_module"})),
    ("areas.py", "pkgutil", frozenset({"iter_modules"})),
    # Profile discovery: imports `stayfixed.profiles.<name>.hygiene`, pinned in `DYNAMIC_IMPORTERS`.
    ("profiles/hints.py", "importlib", frozenset({"import_module"})),
    # Reads the running interpreter's bytecode magic, the first four bytes of every `.pyc` it would
    # open; it imports nothing.
    ("profiles/python/hygiene.py", "importlib.util", frozenset({"util.MAGIC_NUMBER"})),
)


def _attribute_path(node: ast.AST, parents: dict[int, ast.AST]) -> tuple[str, ast.AST]:
    """The dotted attributes read off the name `node`, outermost last (`util.MAGIC_NUMBER` for
    `importlib.util.MAGIC_NUMBER`), or `<value>` when the name is used as anything but the root
    of an attribute read; and the outermost node of that read, which a call would be made on."""
    path: list[str] = []
    while isinstance(parent := parents.get(id(node)), ast.Attribute) and parent.value is node:
        path.append(parent.attr)
        node = parent
    return ".".join(path) or "<value>", node


def _within(module: str, listed: Iterable[str]) -> bool:
    return any(module == entry or module.startswith(f"{entry}.") for entry in listed)


def _reads_data(dotted: str, node: ast.AST, parents: dict[int, ast.AST], rebound: bool) -> bool:
    """Whether reading `dotted` at `node` is one of the two reads of `RESOURCES` that import
    nothing: anything in its `abc`, or a call of its `files` with one positional argument, the
    literal `"stayfixed"` or `__package__` in a module that never binds it (`rebound`)."""
    if _within(dotted, {f"{RESOURCES}.abc"}):
        return True
    call = parents.get(id(node))
    if dotted != f"{RESOURCES}.files" or not isinstance(call, ast.Call) or call.func is not node:
        return False
    if call.keywords or len(call.args) != 1:
        return False
    (anchor,) = call.args
    if isinstance(anchor, ast.Name):
        return anchor.id == "__package__" and not rebound
    return isinstance(anchor, ast.Constant) and anchor.value == "stayfixed"


def _machinery_imports(tree: ast.AST) -> list[tuple[str, frozenset[str]]]:
    """Every statement in `tree` that imports a module neither `stayfixed`'s own nor on
    `STANDARD_IMPORTS`, as `(module, reach)`: for `from m import a, b` the names taken that are not
    allowed modules themselves (`from urllib import parse` takes none), for `import m.n [as x]`
    every attribute path read off the name it binds, anywhere in the file. A `RESOURCES` name,
    and an `import` of it, counts only for its reads `_reads_data` does not pass, and is no row
    when that leaves none."""
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    # A module that binds `__package__` itself can point it at any module at all.
    rebound = any(
        (isinstance(node, ast.Name) and node.id == "__package__" and type(node.ctx) is not ast.Load)
        or (isinstance(node, ast.arg) and node.arg == "__package__")
        for node in ast.walk(tree)
    )

    def reached(bound: str, dotted: str) -> set[str]:
        """The reads off the name `bound`, which stands for `dotted`, past what imports nothing."""
        paths: set[str] = set()
        for name in ast.walk(tree):
            if isinstance(name, ast.Name) and name.id == bound:
                path, outer = _attribute_path(name, parents)
                full = dotted if path == "<value>" else f"{dotted}.{path}"
                if not _reads_data(full, outer, parents, rebound):
                    paths.add(path)
        return paths

    def allowed(module: str) -> bool:
        return module.split(".")[0] == "stayfixed" or _within(module, STANDARD_IMPORTS)

    found: list[tuple[str, frozenset[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names: set[str] = set()
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}"
                if allowed(node.module) or allowed(dotted):
                    continue
                data = alias.name != "*" and _within(dotted, {RESOURCES})
                if data and not reached(alias.asname or alias.name, dotted):
                    continue
                names.add(alias.name)
            if names:
                found.append((node.module, frozenset(names)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # An allowed import is no row, and nothing read off the name it binds is judged:
                # `import urllib.parse` binds `urllib`, and `urllib.request` read off it passes.
                if allowed(alias.name):
                    continue
                bound = alias.asname or alias.name.split(".")[0]
                dotted = alias.name if alias.asname else bound
                reach = reached(bound, dotted)
                if reach or not _within(alias.name, {RESOURCES}):
                    found.append((alias.name, frozenset(reach)))
    return found


def test_no_core_module_reaches_the_import_machinery_but_where_pinned() -> None:
    # The rule above reads a list of names, and `pkgutil.resolve_name("stayfixed.memory.store")`,
    # `importlib.util.find_spec` and a loader's `exec_module`, `importlib.resources.files` handed
    # the store's name, `pydoc.locate`, `pickle.loads`, `logging.config`'s resolver, `timeit` and
    # `xml.sax.make_parser` each crossed into the private layer from a core function with every
    # boundary test green. So the core imports the standard library from `STANDARD_IMPORTS` alone,
    # and any other import is pinned with what it reaches: a new importer is a new row, and a
    # pinned importer reaching one more name changes its row. `importlib.resources` is no row while
    # it only reads the package's own data. What this cannot see is in the comment over
    # `STANDARD_IMPORTS`: it is a tripwire, not a proof.
    #
    # Mutations (declared): `mutations/`'s "a core function imports the note store through
    # pkgutil.resolve_name", "profile discovery reaches importlib.util as well", "a core function
    # opens the note store's resources by its module name", "a core function opens the note
    # store's resources through files imported by name", "a core function imports the note store
    # through pydoc.locate", "a core function unpickles a reference to the note store", "a core
    # function loads code through marshal", "a core function resolves the note store through
    # logging.config", "a core function runs an import through timeit", "a core function reaches
    # xml.sax through a sibling submodule's import" and "a core function takes __import__ from
    # builtins by a computed name".
    source = ROOT / "src" / "stayfixed"
    rows = [
        (where, module, reach)
        for where, path in core_files(source)
        for module, reach in _machinery_imports(ast.parse(path.read_text(encoding="utf-8")))
    ]
    found_rows, pinned = Counter(rows), Counter(MACHINERY_IMPORTERS)
    assert found_rows == pinned, {"unpinned": found_rows - pinned, "gone": pinned - found_rows}
    # Every module is held to the standard library (`tests/boundaries/test_layering.py`), and the
    # core to the part of it listed here, so the list may name nothing outside it: a listed module
    # the runtime may not import would admit here what the layer below refuses. Mutation
    # (declared): `mutations/`'s "the core's import list admits a module outside the standard
    # library" -> this reddens.
    outside = {
        name for name in STANDARD_IMPORTS if name.split(".")[0] not in sys.stdlib_module_names
    }
    assert outside == set(), outside


def test_the_machinery_rule_reads_every_spelling() -> None:
    # The walk above can show the rule holding only for the spellings the tree carries, so it is
    # put in front of the ones it does not: a `from` import of a submodule, an aliased `import`,
    # the name handed on as a value, and `importlib.resources` read for the package's own data in
    # each spelling left alone, though not what is read off the `importlib` its `import` binds.
    # Measured by hand: dropping the `RESOURCES` check of the `from` arm of `_machinery_imports`,
    # the `<value>` fallback, or `_reads_data`'s `files` arm each reddens it.
    spellings = (
        "from importlib import resources\nfrom importlib.resources.abc import Traversable\n"
        "import importlib.resources\nimportlib.resources.files(__package__)\n"
        "importlib.import_module('x')\nfrom importlib import resources, util\n"
        "from importlib.util import find_spec\nimport pkgutil as p\np.resolve_name('x')\n"
        "import runpy\nf(runpy)\nrunpy.run_module('x')\n"
    )
    assert sorted(_machinery_imports(ast.parse(spellings)), key=str) == sorted(
        [
            ("importlib.resources", frozenset({"import_module"})),
            ("importlib", frozenset({"util"})),
            ("importlib.util", frozenset({"find_spec"})),
            ("pkgutil", frozenset({"resolve_name"})),
            ("runpy", frozenset({"<value>", "run_module"})),
        ],
        key=str,
    )


@pytest.mark.parametrize(
    ("source", "rows"),
    [
        pytest.param(
            "from importlib import resources\nresources.files(__package__).joinpath('x')\n"
            "resources.files('stayfixed')\n",
            [],
            id="files-on-the-package",
        ),
        pytest.param(
            "import importlib.resources\nimport importlib.resources as r\n"
            "importlib.resources.files(__package__)\nr.files('stayfixed')\n",
            [],
            id="files-on-the-package-through-import",
        ),
        pytest.param(
            "from importlib.resources.abc import Traversable\nx: Traversable\n", [], id="abc"
        ),
        pytest.param(
            "from importlib import resources\nresources.files('stayfixed.memory.store')\n",
            [("importlib", frozenset({"resources"}))],
            id="files-on-a-module-name",
        ),
        pytest.param(
            "import importlib.resources\nimportlib.resources.files(name)\n",
            [("importlib.resources", frozenset({"resources.files"}))],
            id="files-on-a-computed-name",
        ),
        pytest.param(
            "import importlib.resources as r\nr.files(anchor=__package__)\n",
            [("importlib.resources", frozenset({"files"}))],
            id="files-by-keyword",
        ),
        pytest.param(
            "from importlib.resources import files\nfiles('stayfixed.memory.store')\n",
            [("importlib.resources", frozenset({"files"}))],
            id="files-imported-by-name",
        ),
        pytest.param(
            "from importlib import resources\nresources.read_text(__package__, 'x')\n",
            [("importlib", frozenset({"resources"}))],
            id="an-anchor-of-its-own",
        ),
        pytest.param(
            "from importlib import resources\nload(resources)\n",
            [("importlib", frozenset({"resources"}))],
            id="handed-on",
        ),
        pytest.param(
            "from importlib import resources\n__package__ = 'stayfixed.memory.store'\n"
            "resources.files(__package__)\n",
            [("importlib", frozenset({"resources"}))],
            id="package-rebound",
        ),
        pytest.param(
            "from importlib import resources\ndef f(__package__):\n"
            "    return resources.files(__package__)\n",
            [("importlib", frozenset({"resources"}))],
            id="package-a-parameter",
        ),
        pytest.param(
            "import pydoc\npydoc.locate('x')\n", [("pydoc", frozenset({"locate"}))], id="pydoc"
        ),
        pytest.param(
            "from pickle import loads as load\n", [("pickle", frozenset({"loads"}))], id="pickle"
        ),
        pytest.param(
            "import marshal as m\nm.loads(data)\n",
            [("marshal", frozenset({"loads"}))],
            id="marshal",
        ),
        pytest.param(
            "import logging.config\nlogging.config.dictConfig({})\n",
            [("logging.config", frozenset({"config.dictConfig"}))],
            id="logging-config",
        ),
        pytest.param(
            "from logging import config, getLogger\n",
            [("logging", frozenset({"config", "getLogger"}))],
            id="logging-off-the-list",
        ),
        pytest.param(
            "from multiprocessing.reduction import ForkingPickler\n",
            [("multiprocessing.reduction", frozenset({"ForkingPickler"}))],
            id="a-submodule-off-the-list",
        ),
        pytest.param(
            "import xml.dom.pulldom\nxml.sax.make_parser(['x'])\n",
            [("xml.dom.pulldom", frozenset({"sax.make_parser"}))],
            id="a-sibling-read-off-the-package-an-import-binds",
        ),
        pytest.param(
            "from xml.dom import pulldom\n", [("xml.dom", frozenset({"pulldom"}))], id="xml-dom"
        ),
        pytest.param(
            "import timeit\ntimeit.timeit('x')\n", [("timeit", frozenset({"timeit"}))], id="timeit"
        ),
        pytest.param(
            "import builtins\ngetattr(builtins, name)\n",
            [("builtins", frozenset({"<value>"}))],
            id="builtins",
        ),
        pytest.param(
            "import inspect\ninspect.importlib\n",
            [("inspect", frozenset({"importlib"}))],
            id="inspect",
        ),
        pytest.param(
            "import os.path\nfrom collections.abc import Mapping\nimport urllib.parse\n"
            "from urllib import parse\nfrom os import path\nimport stayfixed.areas\n"
            "from . import sibling\n",
            [],
            id="on-the-list-or-our-own",
        ),
        pytest.param(
            "from urllib import parse, request\nimport urllib.request\n",
            [("urllib", frozenset({"request"})), ("urllib.request", frozenset())],
            id="a-package-allowed-in-part",
        ),
    ],
)
def test_the_machinery_rule_reads_resources_by_its_anchor_and_every_other_module(
    source: str, rows: list[tuple[str, frozenset[str]]]
) -> None:
    # `importlib.resources.files` imports the anchor it is handed when that names a module, so
    # it is data only on the package itself, and every other read of `importlib.resources` is a
    # row. Every module off `STANDARD_IMPORTS` is a row, a submodule of an allowed package
    # included, and nothing on it is. Measured by hand: dropping the `rebound` check, the keyword
    # check, the `abc` arm, the `RESOURCES` check of the `import` arm, the `allowed` check of
    # either statement, the dotted name's own check in the `from` arm, the `stayfixed` exemption,
    # or reading the list by top-level name each reddens a case.
    assert _machinery_imports(ast.parse(source)) == rows
