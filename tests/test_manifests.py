from __future__ import annotations

import json
import re
import shutil
import tomllib
from collections.abc import Iterable
from pathlib import Path

import pytest

from stayfixed import __version__
from stayfixed.release.api import HASHED_FILES, RECORD
from tests.release_script import release

ROOT = Path(__file__).resolve().parents[1]


def test_claude_manifest_names_the_plugin_its_version_and_titled_user_config() -> None:
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "stayfixed"
    assert manifest["version"] == __version__
    # The keys, before anything is asserted about their entries. `"x"` satisfies both
    # assertions in the loop and `{}` satisfies the loop itself: measured, the three entries
    # moved to an unread key and `userConfig` left empty, this module was 9 passed — a test
    # named "…and titled user config" green on a plugin that offers none.
    #
    # Mutation: none of its own. The manifest is data and the oracle mutates source; the
    # measurement above is by hand, like the fixture mutations in `tests/test_fixtures.py`.
    assert set(manifest["userConfig"]) == {"reply_language", "artifact_language", "preset"}
    for key, entry in manifest["userConfig"].items():
        assert entry["title"], key
        assert entry["description"], key


def test_marketplace_has_a_description_and_an_unversioned_entry() -> None:
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert marketplace["name"] == "stayfixed-marketplace"
    assert marketplace["description"]
    (entry,) = marketplace["plugins"]
    assert entry["name"] == "stayfixed"
    assert entry["source"] == "./"
    assert "version" not in entry


def test_codex_manifest_carries_no_hooks_or_skills_key() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "stayfixed"
    assert "hooks" not in manifest
    # `claude plugin validate` refuses "../skills/" as a path traversal attempt and reports
    # "./skills/" as not found, because the value resolves relative to .codex-plugin/ itself: no
    # string reaches the root-level skills/ directory from there. `skills/` now holds skills, but
    # the key is the release's to add — this assertion is what encodes its absence today, and the
    # change that adds it rewrites this test and its name, once Codex's own manifest reading has
    # actually been measured.
    assert "skills" not in manifest


def test_the_repository_passes_release_check(capsys: pytest.CaptureFixture[str]) -> None:
    # Through the script's own `main`, as CI runs it: the version sources agree, and the record
    # of the shipped files is current.
    assert release().main(["check", "--root", str(ROOT)]) == 0, capsys.readouterr().out


def test_the_repository_itself_carries_a_current_release_record() -> None:
    # The release record is kept true on every commit and not only at a tag, which is what makes it
    # a record anyone has watched fail. A change to the wrapper, to `hooks/hooks.json` or to
    # `scripts/stayfixed` that forgot `scripts/release.py hashes` reddens here and in the gate.
    assert release().drift(ROOT) == []


def test_a_drifted_record_fails_the_hashes_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The test above holds the committed record clean; this one holds that the same check can
    # say otherwise about it. A copy of the repository's shipped files and its record, with one
    # recorded digest changed, exits 1 naming that file and no other.
    #
    # Mutation (declared): `hashes --check` exits clean on a drifted record -> exit 0, and this
    # reddens.
    for relative in (*HASHED_FILES, RECORD):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    record = json.loads((tmp_path / RECORD).read_text(encoding="utf-8"))
    record["files"]["hooks/hooks.json"] = "0" * 64
    (tmp_path / RECORD).write_text(json.dumps(record), encoding="utf-8")
    assert release().main(["hashes", "--check", "--root", str(tmp_path), "--json"]) == 1
    problems = json.loads(capsys.readouterr().out)["problems"]
    assert problems == [
        f"{RECORD} does not match hooks/hooks.json; run `{release().COMMAND} hashes`"
    ]


def test_no_top_level_bin_directory() -> None:
    assert not (ROOT / "bin").exists()


def _not_yet() -> list[str]:
    """What `README.md` itself declares unshipped, read off the README and never restated here.

    The README's own roadmap sentence is the authority: the day an item ships, its author
    removes it from that sentence, as `assess`'s did, and the storefront is free to advertise
    it, with no second list to remember. Restating the items here would be the drift this test
    exists to catch, one file along.

    A leading article is dropped, and that is the whole difference between a test that catches
    this and one that does not: the README writes "the adoption state machine" and every one of
    the four listings wrote "an adoption state machine", so an item kept with its article
    matched nothing and the first draft of this test went green over the very strings it was
    written for.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sentence = readme.split("**Not yet:**", 1)[1].split("—", 1)[0]
    flat = " ".join(sentence.replace(">", " ").replace("`", " ").split())
    items = [part.strip(" .,") for part in re.split(r",| and ", flat)]
    return [re.sub(r"^(?:the|an?) ", "", item) for item in items if item]


# The four storefront strings — PyPI, the Claude Code plugin, the marketplace entry and the
# Codex listing — in the order a prospective adopter meets them.
def _storefront() -> dict[str, str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    (entry,) = market["plugins"]
    return {
        "pyproject.toml": pyproject["project"]["description"],
        ".claude-plugin/plugin.json": claude["description"],
        ".claude-plugin/marketplace.json": entry["description"],
        ".codex-plugin/plugin.json": codex["description"],
        ".codex-plugin/plugin.json interface.shortDescription": codex["interface"][
            "shortDescription"
        ],
    }


def test_the_readme_still_declares_what_has_not_shipped() -> None:
    # The non-vacuity guard for the test below: a README that lost the sentence, or a sentence
    # this parser stopped finding items in, would otherwise turn that test into an assertion
    # over an empty list and leave the storefront free to advertise anything.
    items = _not_yet()
    assert len(items) >= 4, items
    assert "memory MCP server" in items
    assert "hold-the-line baseline" in items


def test_no_storefront_string_advertises_what_the_readme_says_is_not_yet() -> None:
    """The listings a stranger reads before the README may not outrun it.

    `pyproject.toml`'s description is the PyPI page; the two Claude manifests are the plugin
    card and the marketplace row; the Codex listing is the third storefront. All four
    advertised "an adoption state machine" while `stayfixed assess` did not exist and the
    README listed it under **Not yet**, and nothing in `scripts/release.py check` or
    `RELEASING.md` looked. Mutation (declared): put the memory MCP server into
    `pyproject.toml`'s description -> reddens naming the file.

    What this cannot see is a paraphrase. The Codex listing's `shortDescription` said "earned
    enforcement", which is the state machine's effect under another name and matches no item
    in the README's sentence; that one was caught by reading, and this test would not have
    caught it.
    """
    items = _not_yet()
    offending = [
        (where, item)
        for where, text in _storefront().items()
        for item in items
        if re.search(rf"\b{re.escape(item)}\b", text, re.IGNORECASE)
    ]
    assert offending == [], offending


def test_every_changelog_fragment_carries_towncriers_orphan_prefix() -> None:
    """A fragment named without the `+` prints its slug in the release notes.

    towncrier reads the part before `.<type>.md` as the fragment's issue reference and
    `issue_format = "{issue}"` renders it in parentheses at the end of the bullet, so the 26
    fragments assembled for 0.1.0 would each have published an internal slug nobody outside
    the repository can read. The `+` is towncrier's documented `orphan_prefix`; it suppresses the
    reference and leaves the slug readable in the repository, and it is per-fragment, so a
    fragment that one day names a real issue still renders its reference.

    No entry in `mutations/`: the invariant is over a set of file *names* and the oracle
    applies a textual change to a file's *contents*, so there is no line for it to mutate.
    The directory is empty right after a release, so the rule is also shown to reject a name
    without the prefix, which keeps the check from passing on nothing.
    """
    assert _unprefixed(["+a.feature.md", "b.fix.md", ".gitkeep"]) == ["b.fix.md"]
    assert _unprefixed(path.name for path in (ROOT / "changelog.d").iterdir()) == []


def _unprefixed(names: Iterable[str]) -> list[str]:
    """The fragment files among `names` that lack towncrier's orphan prefix."""
    return sorted(name for name in names if name.endswith(".md") and not name.startswith("+"))
