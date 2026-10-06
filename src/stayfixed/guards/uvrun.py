"""How `uv run` is read through to the program it launches, for `bashscan.command_words`.

uv is one stack's launcher, and this module is where the shared scanner keeps it, so the scanner
itself names no stack: the background guard and every profile's red-run hint read commands through
the same unwrap (`tests/test_language_neutral.py` pardons this file for that reason). What it reads
is uv's own option grammar, measured against uv; it never runs uv.
"""

from __future__ import annotations

# `uv run --locked pytest`, the shape the README and the `attribute-failure` skill recommend:
# `uv`, uv's global options, the word `run`, `run`'s options, then the program. The five tables
# are uv's own, read off `uv --help` and `uv run --help` (uv 0.12.19, measured): the global
# options are accepted before `run` and after it, `run`'s own only after it (`uv --locked run`
# exits 2). An option in no table stops the unwrap rather than being guessed a flag, since a
# guessed flag that takes a value reads that value as the program (`uv run --with pytest echo`
# would become a pytest run); `-h` is in no table because it prints help and runs nothing. The
# tables move with uv, and an option uv adds is under-reported until it is added here.
_UV = "uv"
_UV_RUN = "run"
_UV_GLOBAL_FLAGS = frozenset(
    {
        "-q",
        "--quiet",
        "-v",
        "--verbose",
        "-n",
        "--no-cache",
        "--managed-python",
        "--no-managed-python",
        "--no-python-downloads",
        "--system-certs",
        "--offline",
        "--no-progress",
        "--no-config",
    }
)
_UV_GLOBAL_VALUED = frozenset(
    {
        "--cache-dir",
        "--color",
        "--allow-insecure-host",
        "--directory",
        "--project",
        "--config-file",
    }
)
_UV_RUN_FLAGS = _UV_GLOBAL_FLAGS | frozenset(
    {
        "--all-extras",
        "--no-dev",
        "--only-dev",
        "--no-default-groups",
        "--all-groups",
        "--no-editable",
        "--exact",
        "--no-env-file",
        "--isolated",
        "--active",
        "--no-sync",
        "--locked",
        "--frozen",
        "--all-packages",
        "--no-project",
        "--no-index",
        "-U",
        "--upgrade",
        "--no-sources",
        "--reinstall",
        "--compile-bytecode",
        "--no-build-isolation",
        "--no-build",
        "--no-binary",
        "--refresh",
    }
)
# `-m pytest` runs the pytest module and `--script x` the file `x`: flags, whose next word is a
# module or a script uv hands to Python rather than a program on the path. So by default such
# a command stays whole, and the background guard never refuses `uv run -m sleep 30` as a
# `sleep`; a caller asking which test runner ran passes `command_words` its
# `modules_as_programs`, and reads `uv run -m pytest` as a pytest run.
_UV_RUN_TARGETS = frozenset({"-m", "--module", "-s", "--script", "--gui-script"})
_UV_RUN_VALUED = _UV_GLOBAL_VALUED | frozenset(
    {
        "--extra",
        "--no-extra",
        "--group",
        "--no-group",
        "--only-group",
        "--no-editable-package",
        "--env-file",
        "-w",
        "--with",
        "--with-editable",
        "--with-requirements",
        "--package",
        "--python-platform",
        "--index",
        "--default-index",
        "-i",
        "--index-url",
        "--extra-index-url",
        "-f",
        "--find-links",
        "--index-strategy",
        "--keyring-provider",
        "-P",
        "--upgrade-package",
        "--upgrade-group",
        "--resolution",
        "--prerelease",
        "--prerelease-package",
        "--fork-strategy",
        "--exclude-newer",
        "--exclude-newer-package",
        "--no-sources-package",
        "--reinstall-package",
        "--link-mode",
        "-C",
        "--config-setting",
        "--config-settings-package",
        "--no-build-isolation-package",
        "--no-build-package",
        "--no-binary-package",
        "--refresh-package",
        "-p",
        "--python",
    }
)


def is_launcher(name: str) -> bool:
    """Whether a command's program, by its bare name, is uv."""
    return name == _UV


def past_run(segment: list[str], index: int, *, modules_as_programs: bool) -> int | None:
    """Where the program `uv run` launches starts in `segment`, read from `index`, just past
    the word `uv` (`is_launcher`); `None` when these words are not a `uv run` the tables can
    read whole. `modules_as_programs` reads the word after `-m` or `--script` as that program.

    Before `run` only uv's global options are skipped; after it `run`'s too, `--` ends them,
    and the first word that is not an option is the program.
    """
    flags, valued = _UV_GLOBAL_FLAGS, _UV_GLOBAL_VALUED
    running = False
    while index < len(segment):
        word = segment[index]
        if not running and word == _UV_RUN:
            flags = _UV_RUN_FLAGS | _UV_RUN_TARGETS if modules_as_programs else _UV_RUN_FLAGS
            valued = _UV_RUN_VALUED
            running = True
            index += 1
            continue
        if running and word == "--":
            return index + 1
        if not word.startswith("-") or word == "-":
            return index if running else None
        width = _uv_option_width(word, flags, valued)
        if width is None:
            return None
        index += width
    return min(index, len(segment)) if running else None


def _uv_option_width(token: str, flags: frozenset[str], valued: frozenset[str]) -> int | None:
    """How many words the uv option `token` spans -- one, or two when its value is the next
    word -- or `None` for an option in neither table.

    `--name=value` is one word. A short cluster is read the way uv reads it: `-qq` and `-nq`
    are flags, and the first value-taking letter takes the rest of the word as its value
    (`-p3.12`, `-np3.12`) or, at the word's end, the next word (`-p 3.12`).
    """
    if token.startswith("--"):
        name, equals, _ = token.partition("=")
        if name in valued:
            return 1 if equals else 2
        if name in flags and not equals:
            return 1
        return None
    for position in range(1, len(token)):
        short = "-" + token[position]
        if short in valued:
            return 1 if position + 1 < len(token) else 2
        if short not in flags:
            return None
    return 1
