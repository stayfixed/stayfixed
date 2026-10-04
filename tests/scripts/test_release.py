"""`scripts/release.py`: this repository's own release discipline, driven through `main(argv)`.

The three commands used to be the installed CLI's `release` group, and they only ever checked
the stayfixed repository itself; the exit codes and the `--json` shapes are the ones that group
had, and these tests are what holds them. The half of the release record that shipped code reads
— `HASHED_FILES`, `digests`, `read_record` and what it raises — stays in `stayfixed.release`,
and `tests/release/test_hashes.py` holds it, its happy path included: what `digests` computes,
and that no record reads as `None` and a record as the digests it names. What is here is the
writer and the drift check. towncrier is a development dependency and is *invoked*, never
imported; the argv is the contract, and a stub records it.

Every message that tells the reader which command to run again is asserted against the command
written out, `uv run python scripts/release.py …`, and never through the script's own
`COMMAND`: read from the script, the expectation was the script's text compared with itself,
and a script telling its reader to run a command that no longer exists stayed green.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

from stayfixed.errors import Failure, Refusal
from stayfixed.release.api import HASHED_FILES, RECORD, digests, read_record
from stayfixed.runner import NOT_FOUND
from tests.release.test_hashes import hashed_plugin
from tests.runners import Recorder
from tests.script import release as _script

release = _script()
ROOT = Path(__file__).resolve().parents[2]

# The fragment predicate reads the types towncrier itself is configured with, so a fixture
# repository has to declare them exactly as the real one does.
PYPROJECT = """[project]
name = "stayfixed"
version = "{v}"

[[tool.towncrier.type]]
directory = "feature"

[[tool.towncrier.type]]
directory = "fix"

[[tool.towncrier.type]]
directory = "change"
"""
INIT = '__version__ = "{v}"\n'
LOCK = '[[package]]\nname = "stayfixed"\nversion = "{v}"\nsource = {{ editable = "." }}\n'
MARKETPLACE = {"name": "stayfixed-marketplace", "plugins": [{"name": "stayfixed", "source": "./"}]}


def repo(
    tmp_path: Path,
    *,
    pyproject: str,
    init: str,
    claude: str,
    codex: str,
    changelog: str,
    lock: str | None = None,
    fragments: int = 0,
    marketplace: dict[str, object] | None = None,
) -> Path:
    (tmp_path / "src" / "stayfixed").mkdir(parents=True)
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".codex-plugin").mkdir()
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.format(v=pyproject))
    (tmp_path / "uv.lock").write_text(LOCK.format(v=pyproject if lock is None else lock))
    (tmp_path / "src" / "stayfixed" / "__init__.py").write_text(INIT.format(v=init))
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "stayfixed", "version": claude})
    )
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(marketplace or MARKETPLACE)
    )
    (tmp_path / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "stayfixed", "version": codex})
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n<!-- towncrier release notes start -->\n\n"
        f"## {changelog} (2026-09-05)\n"
    )
    for index in range(fragments):
        (tmp_path / "changelog.d" / f"{index}.feature.md").write_text("x\n")
    return tmp_path


def test_all_equal_is_clean(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.0", codex="0.1.0", changelog="0.1.0"
    )
    assert release.check(root) == []


def test_each_mismatch_is_named(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.1", codex="0.1.0", changelog="0.1.0"
    )
    problems = release.check(root)
    assert len(problems) == 1
    assert ".claude-plugin/plugin.json" in problems[0]
    assert "0.1.1" in problems[0]


def test_pending_fragments_allow_the_changelog_to_lag(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        pyproject="0.2.0",
        init="0.2.0",
        claude="0.2.0",
        codex="0.2.0",
        changelog="0.1.0",
        fragments=1,
    )
    assert release.check(root) == []


def test_without_fragments_the_changelog_must_match(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0", changelog="0.1.0"
    )
    assert any("CHANGELOG.md" in problem for problem in release.check(root))


def test_a_versioned_marketplace_entry_is_refused(tmp_path: Path) -> None:
    versioned: dict[str, object] = {
        "name": "m",
        "plugins": [{"name": "stayfixed", "source": "./", "version": "0.1.0"}],
    }
    root = repo(
        tmp_path,
        pyproject="0.1.0",
        init="0.1.0",
        claude="0.1.0",
        codex="0.1.0",
        changelog="0.1.0",
        marketplace=versioned,
    )
    assert any("marketplace" in problem for problem in release.check(root))


def test_collect_reads_every_source_value(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        pyproject="1.0.0",
        init="1.0.1",
        claude="1.0.2",
        codex="1.0.3",
        changelog="1.0.4",
        lock="1.0.5",
    )
    assert release.collect(root) == {
        "pyproject.toml": "1.0.0",
        "uv.lock": "1.0.5",
        "src/stayfixed/__init__.py": "1.0.1",
        ".claude-plugin/plugin.json": "1.0.2",
        ".codex-plugin/plugin.json": "1.0.3",
        "CHANGELOG.md": "1.0.4",
    }


def test_a_missing_version_key_reads_as_none(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="1.0.0", init="1.0.0", claude="1.0.0", codex="1.0.0", changelog="1.0.0"
    )
    (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "stayfixed"}))
    assert release.collect(root)[".codex-plugin/plugin.json"] is None


def test_the_cli_command_exits_one_on_version_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # CI runs the success path on every build, so exit 1 — the version check's only
    # user-facing surface — is reached by nothing else.
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.2.0", claude="0.1.0", codex="0.1.0", changelog="0.1.0"
    )
    assert release.main(["check", "--root", str(root)]) == 1
    # stdout, and that is the change rather than an accident: these commands used to report a
    # finding by raising `Failure`, which the frame prints to stderr under a `stayfixed: failed:`
    # prefix and which drops `Result.data`. Every stayfixed command returns its findings.
    assert "version drift" in capsys.readouterr().out


def test_the_json_object_has_the_same_shape_whether_or_not_there_is_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The whole of why these commands stopped raising. A `Failure` becomes
    # `{"error": "failed", "summary": "failed: ..."}` and `Result.data` never reaches the
    # output — so a consumer that read `versions` on a clean run had nothing to read on the run
    # it cared about, and the machine-readable shape flipped on exactly the condition being
    # tested for. Asserted as the key sets being equal AND as the drifted run carrying the
    # data: "both objects are empty" would satisfy the first on its own.
    #
    # Mutation (declared): the drift arm returns `{}` for its data, which is what raising
    # produced -> the key sets differ and this reddens naming them.
    clean = repo(
        tmp_path / "a",
        pyproject="0.1.0",
        init="0.1.0",
        claude="0.1.0",
        codex="0.1.0",
        changelog="0.1.0",
    )
    drifted = repo(
        tmp_path / "b",
        pyproject="0.1.0",
        init="0.2.0",
        claude="0.1.0",
        codex="0.1.0",
        changelog="0.1.0",
    )
    assert release.main(["check", "--root", str(clean), "--json"]) == 0
    on_success = json.loads(capsys.readouterr().out)
    assert release.main(["check", "--root", str(drifted), "--json"]) == 1
    on_drift = json.loads(capsys.readouterr().out)

    assert set(on_success) == set(on_drift) == {"summary", "problems", "versions"}
    assert on_success["problems"] == []
    assert on_drift["problems"] == [
        "src/stayfixed/__init__.py says '0.2.0'; pyproject.toml says '0.1.0'"
    ]
    assert on_drift["versions"]["src/stayfixed/__init__.py"] == "0.2.0"


def test_the_cli_command_reports_the_agreed_version_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.0", codex="0.1.0", changelog="0.1.0"
    )
    argv = ["check", "--root", str(root), "--json"]
    assert release.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["versions"]["pyproject.toml"] == "0.1.0"


def _repo(
    tmp_path: Path,
    *,
    pyproject: str = "0.1.0",
    init: str = "0.1.0",
    claude: str = "0.1.0",
    codex: str = "0.1.0",
    changelog: str = "0.1.0",
    lock: str | None = None,
) -> Path:
    """`repo` with every version agreeing unless a test disagrees with one on purpose."""
    return repo(
        tmp_path,
        pyproject=pyproject,
        init=init,
        claude=claude,
        codex=codex,
        changelog=changelog,
        lock=lock,
    )


@pytest.mark.parametrize(
    ("entry", "pending"),
    [
        ("x.feature.md", True),
        ("0.fix.md", True),
        ("a.b.change.md", True),
        (".gitkeep", False),
        (".DS_Store", False),
        ("notes.md", False),
        ("x.bogus.md", False),
        ("feature.md", False),
        ("x.feature.rst", False),
    ],
)
def test_only_a_towncrier_fragment_lets_the_changelog_lag(
    tmp_path: Path, entry: str, pending: bool
) -> None:
    # A stray .DS_Store — which Finder writes just by opening changelog.d — used to count as a
    # pending fragment and turn a genuine drift from exit 1 into exit 0.
    root = _repo(tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0")
    (root / "changelog.d" / entry).write_text("x\n")
    assert release.pending_fragments(root) is pending
    assert (release.check(root) == []) is pending


def test_a_stray_file_beside_a_real_fragment_does_not_hide_it(tmp_path: Path) -> None:
    root = _repo(tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0")
    (root / "changelog.d" / ".DS_Store").write_text("x\n")
    (root / "changelog.d" / "foundation.feature.md").write_text("x\n")
    assert release.pending_fragments(root) is True


def test_the_fragment_types_come_from_the_configuration_not_from_code(tmp_path: Path) -> None:
    # Hardcoding "feature", "fix", "change" here would drift from the [[tool.towncrier.type]]
    # blocks towncrier itself reads.
    root = _repo(tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0")
    (root / "changelog.d" / "x.removal.md").write_text("x\n")
    assert release.pending_fragments(root) is False
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text() + '\n[[tool.towncrier.type]]\ndirectory = "removal"\n'
    )
    assert release.pending_fragments(root) is True


def test_a_disagreeing_lockfile_is_reported_by_name(tmp_path: Path) -> None:
    # `uv sync --locked` reds the install step on a stale lockfile with a dependency-shaped
    # message, ahead of the gate built to catch exactly this.
    root = _repo(tmp_path, lock="0.0.9")
    problems = release.check(root)
    assert len(problems) == 1
    assert "uv.lock says '0.0.9'" in problems[0]


def test_a_missing_lockfile_reads_as_none_and_is_reported_as_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "uv.lock").unlink()
    assert release.collect(root)["uv.lock"] is None
    assert any("uv.lock says None" in problem for problem in release.check(root))


def test_a_lockfile_that_names_no_stayfixed_package_reads_as_none(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "uv.lock").write_text('[[package]]\nname = "pytest"\nversion = "8.0.0"\n')
    assert release.collect(root)["uv.lock"] is None


def test_the_four_root_conditions_get_four_different_messages(tmp_path: Path) -> None:
    # One shared message told a user who typoed --root, or ran the command in their own
    # project (--root defaults to "."), that their pyproject.toml lacked a version key. The
    # file case then inherited the missing-path message, so `--root ./pyproject.toml` was told
    # a file it had just been handed does not exist — the gate asserting something untrue
    # about the user's tree, which is the very thing these messages exist to stop.
    missing = tmp_path / "nope"
    not_a_directory = tmp_path / "pyproject.toml"
    not_a_directory.write_text('[project]\nname = "stayfixed"\nversion = "0.1.0"\n')
    empty = tmp_path / "empty"
    empty.mkdir()
    no_version = tmp_path / "no-version"
    no_version.mkdir()
    (no_version / "pyproject.toml").write_text('[project]\nname = "stayfixed"\n')

    absent = release.check(missing)
    a_file = release.check(not_a_directory)
    unrelated = release.check(empty)
    versionless = release.check(no_version)
    assert absent == [f"{missing} does not exist; --root must name a repository root"]
    assert a_file == [f"{not_a_directory} is not a directory; --root must name a repository root"]
    assert unrelated == [f"{empty} has no pyproject.toml; --root must name a repository root"]
    assert versionless == ["pyproject.toml has no [project].version"]
    assert len({tuple(absent), tuple(a_file), tuple(unrelated), tuple(versionless)}) == 4


@pytest.mark.parametrize(
    ("name", "body", "kind"),
    [
        ("pyproject.toml", "not = = toml", "TOML"),
        ("uv.lock", "not = = toml", "TOML"),
        (".claude-plugin/plugin.json", "{not json", "JSON"),
        (".codex-plugin/plugin.json", "{not json", "JSON"),
    ],
)
def test_a_malformed_source_is_reported_with_its_filename(
    tmp_path: Path, name: str, body: str, kind: str
) -> None:
    # `_read` knows the filename and used to let the decoder's own error escape without it.
    root = _repo(tmp_path)
    (root / name).write_text(body)
    with pytest.raises(release.MalformedSource) as raised:
        release.check(root)
    assert name in str(raised.value)
    assert kind in str(raised.value)


# Past `json`'s own depth on every supported interpreter: 3.11 stops near 1000, 3.12 and 3.13
# between 5000 and 10000 (measured on 3.11.15, 3.12.13 and 3.13.0).
JSON_DEPTH = 100_000


@pytest.mark.parametrize("name", [".claude-plugin/plugin.json", ".codex-plugin/plugin.json"])
def test_a_manifest_nested_past_the_parser_is_reported_as_json(tmp_path: Path, name: str) -> None:
    # `json` answers nesting past its depth with `RecursionError`, not `JSONDecodeError`, and the
    # arm that caught it was the TOML one: a deep `plugin.json` was "not valid TOML". Mutation
    # (declared): the language chosen without the source's name -> "TOML", and this reddens.
    root = _repo(tmp_path)
    (root / name).write_text('{"version": ' + "[" * JSON_DEPTH + "]" * JSON_DEPTH + "}")
    with pytest.raises(RecursionError):
        json.loads((root / name).read_text())
    with pytest.raises(release.MalformedSource) as raised:
        release.check(root)
    assert str(raised.value).startswith(f"{name} is not valid JSON: ")


@pytest.mark.parametrize(
    "body",
    ['package = "not-a-list"\n', "package = [1, 2]\n"],
    ids=["not-a-list", "entries-not-tables"],
)
def test_a_wrongly_shaped_lockfile_is_reported_by_name(tmp_path: Path, body: str) -> None:
    # Valid TOML of the wrong shape decodes cleanly, so `_read`'s two decoder catches never see
    # it: iterating a string yields characters and `entry.get` raised AttributeError straight
    # past them, reaching the caller as an unlabelled internal error naming no file.
    root = _repo(tmp_path)
    (root / "uv.lock").write_text(body)
    with pytest.raises(release.MalformedSource) as raised:
        release.check(root)
    assert "uv.lock" in str(raised.value)


@pytest.mark.parametrize(
    ("name", "body", "shape"),
    [
        (".claude-plugin/plugin.json", "[]", "its top level is not an object"),
        (".codex-plugin/plugin.json", '"0.1.0"', "its top level is not an object"),
        ("pyproject.toml", 'project = "x"\n', "its project is not a table"),
        (".claude-plugin/marketplace.json", "[]", "its top level is not an object"),
        (".claude-plugin/marketplace.json", '{"plugins": ["version"]}', "not a list of objects"),
        (".claude-plugin/marketplace.json", '{"plugins": "x"}', "not a list of objects"),
        (".claude-plugin/marketplace.json", "{not json", "is not valid JSON"),
    ],
    ids=[
        "claude-manifest-list",
        "codex-manifest-string",
        "project-not-a-table",
        "marketplace-list",
        "marketplace-entry-string",
        "marketplace-plugins-string",
        "marketplace-not-json",
    ],
)
def test_a_version_source_of_the_wrong_shape_is_reported_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, body: str, shape: str
) -> None:
    # The lockfile's class, in every other source: valid JSON or TOML of the wrong shape decodes
    # cleanly and a `.get` on a list or a string raised AttributeError past the decoder's
    # catches, an internal error (exit 2) naming no file. A marketplace entry that is a string
    # was read with `in`, a substring test, and `{"plugins": "x"}` was a list of characters that
    # passed in silence. Mutations (oracle): "a manifest whose top level is not an object is read
    # with .get" and "the marketplace reads a plugins value that is not a list of objects".
    root = _repo(tmp_path)
    (root / name).write_text(body)
    with pytest.raises(release.MalformedSource) as raised:
        release.check(root)
    assert str(raised.value).startswith(name) and shape in str(raised.value), raised.value
    assert release.main(["check", "--root", str(root)]) == 1
    assert name in capsys.readouterr().err


def test_the_cli_command_exits_one_on_a_malformed_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `MalformedSource` derives from `Failure` on purpose: a source the gate cannot parse is a
    # finding, not a refusal. Nothing observed that through `run` — the unit tests catch the
    # class, which is base-class agnostic — so reverting it to `Refusal`, and exit 2 with it,
    # left every test green.
    root = _repo(tmp_path)
    (root / "uv.lock").write_text("not = = toml")
    assert release.main(["check", "--root", str(root)]) == 1
    assert "uv.lock is not valid TOML" in capsys.readouterr().err


def _at(tmp_path: Path, version: str) -> Path:
    """The module's `_repo` with every source at one version.

    There is no `_repository(tmp_path, version=…)` fixture in this module; `_repo` is the one
    that exists and it takes a keyword per source, so the two tests below say the version once
    through here rather than five times each.
    """
    return _repo(
        tmp_path,
        pyproject=version,
        init=version,
        claude=version,
        codex=version,
        changelog=version,
    )


def test_a_tag_that_names_another_version_is_drift(tmp_path: Path) -> None:
    # The release workflow used to compare the tag to the package in shell; the gate that
    # exists to say "one version everywhere" now takes the tag as a seventh source. Both
    # tag shapes are accepted — `vX.Y.Z` (the workflow's trigger) and the platform's
    # `stayfixed--vX.Y.Z` — because either may be the one the run was created from.
    # Mutation (declared): accept any tag -> the first assertion reddens.
    root = _at(tmp_path, "1.2.3")
    assert release.check(root, tag="v1.2.4") == [
        "tag v1.2.4 is neither v1.2.3 nor stayfixed--v1.2.3; pyproject.toml says '1.2.3'"
    ]
    assert release.check(root, tag="v1.2.3") == []
    assert release.check(root, tag="stayfixed--v1.2.3") == []


def test_the_drift_message_says_what_was_checked_rather_than_inventing_a_version(
    tmp_path: Path,
) -> None:
    # The message used to be derived with `tag.split("v", 1)[-1]` — a split on the first `v`
    # anywhere in the string, not a parse — so it named a version the tag does not carry.
    # Measured on this repository before the fix:
    #
    #   --tag 0.1.0          -> tag 0.1.0 names 0.1.0; pyproject.toml says '0.1.0'
    #   --tag stayfixed-v0.1.0 -> tag stayfixed-v0.1.0 names 0.1.0; …says '0.1.0'
    #   --tag dev-v0.1.0     -> tag dev-v0.1.0 names -v0.1.0; …says '0.1.0'
    #
    # The first asserts that two identical strings disagree, which is the failure the comment
    # above `check` was written to end. Both of the first two are the slips `RELEASING.md`
    # invites: a human types this flag by hand right after a tool prints `stayfixed--vX.Y.Z`.
    # The tags the older case exercised (`v1.2.4`, `v9.9.9`) all begin with `v` and carry no
    # earlier one, so the split happened to be right and the tests passed for that reason.
    #
    # Mutation (declared): the derived `named` comes back -> all three assertions redden.
    root = _at(tmp_path, "1.2.3")
    # A bare version, which is the tag `git tag 1.2.3` makes and the one that read as agreeing
    # with itself.
    assert release.check(root, tag="1.2.3") == [
        "tag 1.2.3 is neither v1.2.3 nor stayfixed--v1.2.3; pyproject.toml says '1.2.3'"
    ]
    # One hyphen short of the platform's own tag.
    assert release.check(root, tag="stayfixed-v1.2.3") == [
        "tag stayfixed-v1.2.3 is neither v1.2.3 nor stayfixed--v1.2.3; pyproject.toml says '1.2.3'"
    ]
    # And a prefix carrying an earlier `v`, where the split produced `-v1.2.3` — a string that
    # is not a version at all.
    assert release.check(root, tag="dev-v1.2.3") == [
        "tag dev-v1.2.3 is neither v1.2.3 nor stayfixed--v1.2.3; pyproject.toml says '1.2.3'"
    ]


def test_a_tag_with_pending_fragments_is_refused(tmp_path: Path) -> None:
    # Without `--tag`, pending fragments let CHANGELOG.md lag, because a change's fragment is
    # written before the release assembles it. AT a tag there is nothing left to assemble:
    # a fragment still pending means the changelog the users read is not the one the tag
    # claims. Mutation (declared): skip the fragment check under `tag` -> reddens.
    root = _at(tmp_path, "1.2.3")
    (root / "changelog.d" / "late.feature.md").write_text("late\n", encoding="utf-8")
    assert release.check(root) == []
    problems = release.check(root, tag="v1.2.3")
    assert problems == [
        "changelog.d still holds 1 fragment(s); run "
        "`uv run python scripts/release.py notes --version 1.2.3` before tagging"
    ]


def test_every_command_opens_its_own_help_with_what_it_does() -> None:
    # The installed CLI's frame copies each command's `help=` into its description; this script
    # has its own parser and no frame, so `hashes --help` opened with `usage:` and went straight
    # to the options. Mutation (declared): a command registered without `description=` ->
    # reddens naming it.
    top = release.parser()
    groups = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction))
    listed = {action.dest: action.help for action in groups._choices_actions}
    assert sorted(groups._name_parser_map) == ["check", "hashes", "notes"]
    for name, sub in groups._name_parser_map.items():
        assert sub.description == listed[name], name
        assert "--json" in sub.format_help(), name


def test_the_cli_passes_the_tag_through_to_the_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # That the flag exists and that its value reaches `check` is held here and nowhere else.
    # Mutation: `check(root, tag=args.tag)` -> `check(root)` -> exit 0 and this reddens.
    root = _at(tmp_path, "1.2.3")
    argv = ["check", "--root", str(root), "--tag", "v9.9.9"]
    assert release.main(argv) == 1
    assert "tag v9.9.9 is neither v1.2.3 nor" in capsys.readouterr().out


def test_the_cli_refuses_notes_under_a_version_that_is_not_the_projects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Exit 2, the refusal code, and no towncrier anywhere: the comparison is above the runner,
    # so this walks the command end to end without shelling out, which no test does —
    # CONTRIBUTING.md's Tests section routes such calls through a stub runner, and the write
    # path stays a unit test over the stub, under `notes` below.
    root = _at(tmp_path, "1.2.3")
    argv = ["notes", "--version", "1.3.0", "--root", str(root)]
    assert release.main(argv) == 2
    assert "set the version everywhere first" in capsys.readouterr().err


def test_a_project_with_its_own_hooks_directory_is_not_told_about_a_release_record(
    tmp_path: Path,
) -> None:
    # `--root` defaults to `.`, so this gate runs in other people's repositories, and plenty of
    # them have a `hooks/` directory — the first spelling of the guard asked exactly that and
    # told them a record they never had was missing. Asked of the recorded files themselves
    # now. Mutation (declared): probe `hooks/` again -> this reddens.
    root = _repo(tmp_path)
    (root / "hooks").mkdir()
    (root / "hooks" / "hooks.json").write_text("{}\n", encoding="utf-8")
    assert release.check(root) == []


def test_a_tree_that_ships_every_recorded_file_is_told_when_the_record_is_missing(
    tmp_path: Path,
) -> None:
    # The other direction, and the one the record exists for: a tree that carries the three
    # files the harness executes is a tree that owes a record of them. Without this the guard
    # above could be narrowed to `if False` and nothing would notice.
    root = _repo(tmp_path)
    for relative in HASHED_FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(f"# {relative}\n", encoding="utf-8")
    assert release.check(root) == [
        f"{RECORD} is missing; run `uv run python scripts/release.py hashes`"
    ]


def test_collect_still_reads_the_package_version_beside_the_repository_constants() -> None:
    # `stayfixed.REPOSITORY_SLUG` and `stayfixed.REPOSITORY_URL` sit in
    # `src/stayfixed/__init__.py` beside `__version__`; `_INIT`'s regex is anchored on
    # `__version__` alone, so the two new lines must not change what this reads.
    from stayfixed import __version__

    assert release.collect(ROOT)["src/stayfixed/__init__.py"] == __version__


# --- `notes`: the towncrier wrapper, driven through the runner seam ------------------------------

# What the stubbed towncrier prints for a draft, and what `build` returns for one.
NOTES = "## 1.2.3\n\n- a note\n"


def _root(tmp_path: Path, version: str = "1.2.3") -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "stayfixed"\nversion = "{version}"\n', encoding="utf-8"
    )
    return tmp_path


def test_the_argv_is_towncriers_build_with_the_version_and_yes(tmp_path: Path) -> None:
    stub = Recorder(stdout=NOTES)
    release.build(_root(tmp_path), version="1.2.3", draft=False, runner=stub)
    assert stub.calls == [["towncrier", "build", "--version", "1.2.3", "--yes"]]
    assert stub.cwds == [tmp_path]


def test_a_draft_adds_the_flag_and_returns_towncriers_stdout(tmp_path: Path) -> None:
    stub = Recorder(stdout=NOTES)
    assert release.build(_root(tmp_path), version="1.2.3", draft=True, runner=stub) == stub.stdout
    assert stub.calls[0][-1] == "--draft"


def test_a_version_that_is_not_the_projects_is_refused_before_anything_runs(tmp_path: Path) -> None:
    # `check` requires the changelog's first heading to equal pyproject's version, so
    # assembling under another number writes a changelog the gate then refuses. Refused here,
    # above the write. Mutation (declared): drop the comparison -> the stub is called and the
    # `calls == []` assertion reddens. The refusal names the command that lists the places to
    # change, spelled out for the reason the module docstring gives.
    stub = Recorder(stdout=NOTES)
    named = "set the version everywhere first — `uv run python scripts/release.py check` names"
    with pytest.raises(Refusal, match=re.escape(named)):
        release.build(_root(tmp_path, version="1.2.3"), version="1.3.0", draft=False, runner=stub)
    assert stub.calls == []


def test_a_missing_towncrier_names_the_dependency_group(tmp_path: Path) -> None:
    with pytest.raises(Failure, match="uv sync"):
        release.build(
            _root(tmp_path),
            version="1.2.3",
            draft=False,
            runner=Recorder(code=NOT_FOUND, stderr="boom"),
        )


# --- The release record: writing it, and the drift between it and the tree ----------------------


def test_a_written_record_has_no_drift_and_one_changed_byte_is_named(tmp_path: Path) -> None:
    # Mutation (declared): `drift` compares the record against itself -> the second
    # assertion reddens (no drift after the edit).
    root = hashed_plugin(tmp_path)
    release.write_record(root)
    assert release.drift(root) == []
    (root / "hooks" / "run-hook.sh").write_text("# changed\n", encoding="utf-8")
    assert release.drift(root) == [
        f"{RECORD} does not match hooks/run-hook.sh; run `uv run python scripts/release.py hashes`"
    ]


def test_the_record_is_json_with_a_format_and_one_digest_per_file(tmp_path: Path) -> None:
    # What the record holds is `digests`, which `tests/release/test_hashes.py` pins to the full
    # sha256 of each file; this holds that the writer records it, in the shape the shipped reader
    # reads back.
    root = hashed_plugin(tmp_path)
    release.write_record(root)
    document = json.loads((root / RECORD).read_text(encoding="utf-8"))
    assert document["format"] == 1
    assert set(document["files"]) == set(HASHED_FILES)
    assert document["files"] == digests(root)
    assert read_record(root) == digests(root)


def test_no_record_and_a_missing_file_are_both_drift(tmp_path: Path) -> None:
    root = hashed_plugin(tmp_path)
    assert release.drift(root) == [
        f"{RECORD} is missing; run `uv run python scripts/release.py hashes`"
    ]
    release.write_record(root)
    (root / "scripts" / "stayfixed").unlink()
    assert release.drift(root) == [f"{RECORD} names scripts/stayfixed, which is not in the tree"]


@pytest.mark.parametrize(
    "body",
    [b"{not json\n", b'{"format": 1, "files": {"hooks/hooks.json": "\xff\xfe"}}\n'],
    ids=["not-json", "not-utf8"],
)
def test_a_record_that_cannot_be_read_fails_the_drift_check_and_never_reads_clean(
    tmp_path: Path, body: bytes
) -> None:
    # `drift` has no arm of its own for this: the reader's `UnreadableRecord` passes through it,
    # and that class is a `Failure`, so the check exits 1 naming the record rather than reading
    # a corrupt one as no drift. No mutation of its own — the raise is the reader's, and the
    # entries on `read_record` that name `tests/release/test_hashes.py` pin it there.
    root = hashed_plugin(tmp_path)
    (root / RECORD).write_bytes(body)
    with pytest.raises(Failure, match=re.escape(RECORD)):
        release.drift(root)


def test_the_cli_writes_the_record_and_check_exits_one_on_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The command's argv wiring: that `--check` reaches `drift` and that the bare form writes.
    # No subprocess anywhere — this command reads and hashes files and nothing else.
    root = hashed_plugin(tmp_path)
    assert release.main(["hashes", "--check", "--root", str(root)]) == 1
    # stdout: a finding is returned, as every stayfixed command returns one.
    assert "is missing" in capsys.readouterr().out
    assert release.main(["hashes", "--root", str(root)]) == 0
    assert (root / RECORD).is_file()
    assert release.main(["hashes", "--check", "--root", str(root)]) == 0
    (root / "hooks" / "hooks.json").write_text("# moved\n", encoding="utf-8")
    assert release.main(["hashes", "--check", "--root", str(root)]) == 1
    assert "hooks/hooks.json" in capsys.readouterr().out


def test_the_check_json_object_has_the_same_shape_whether_or_not_there_is_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The same invariant `check` states above, and the reason these commands stopped raising
    # `Failure` to report a finding: the frame drops `Result.data` for a `Failure`, so the
    # machine-readable object changed shape on exactly the condition a consumer runs this to
    # detect.
    #
    # Mutation (declared): the drift arm returns `{}` for its data -> the key sets differ.
    root = hashed_plugin(tmp_path)
    assert release.main(["hashes", "--root", str(root)]) == 0
    capsys.readouterr()
    assert release.main(["hashes", "--check", "--root", str(root), "--json"]) == 0
    on_success = json.loads(capsys.readouterr().out)
    (root / "hooks" / "hooks.json").write_text("# moved\n", encoding="utf-8")
    assert release.main(["hashes", "--check", "--root", str(root), "--json"]) == 1
    on_drift = json.loads(capsys.readouterr().out)

    assert set(on_success) == set(on_drift) == {"summary", "problems", "files"}
    assert on_success["problems"] == []
    assert on_drift["problems"] == [
        f"{RECORD} does not match hooks/hooks.json; run `uv run python scripts/release.py hashes`"
    ]
    assert on_drift["files"] == sorted(HASHED_FILES)


def test_a_tree_missing_a_shipped_file_cannot_be_recorded_at_all(tmp_path: Path) -> None:
    # A record that names two of three files is a record saying "this is what the release
    # shipped" while naming less than it did, and every reader of it afterwards reports drift
    # against a claim nobody meant to make. Refused at the moment of writing, where the tree
    # can still be fixed — and nothing is written. Mutation (declared): drop the length check
    # -> a partial record lands and both assertions redden.
    root = hashed_plugin(tmp_path)
    (root / "hooks" / "hooks.json").unlink()
    with pytest.raises(Failure, match=re.escape("hooks/hooks.json")):
        release.write_record(root)
    assert not (root / RECORD).exists(), "a refusal wrote a partial record anyway"
