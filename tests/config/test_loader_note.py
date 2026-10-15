"""The NOTE loader: an unknown name is ignored, an invalid value resets only its key.

A session cannot refuse the way a command does: a `stayfixed.toml` from a newer release, or one
with one bad value in it, would otherwise cost every setting the project made. `loads_noting`
reads what it can and says what it could not (`src/stayfixed/config/loader.py`); `loads` and
`load` still refuse, and every case below is held on both sides.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stayfixed.config import loader
from stayfixed.config.classes import REFUSED_LAYER_NOTE
from stayfixed.config.loader import (
    RESET_NOTE,
    UNKNOWN_NOTE,
    ConfigError,
    loads,
    loads_noting,
)
from stayfixed.config.owner import resolve_owner
from stayfixed.config.paths import PathEscape
from stayfixed.errors import Failure, Refusal
from stayfixed.presets import load_preset
from stayfixed.printed import clipped
from tests.crafted import assert_never_raw

HEAD = '[stayfixed]\nversion = "0.1.0"\npreset = "recommended"\n'
MINIMAL = HEAD + '\n[project]\nname = "sample"\n'
OWNER = resolve_owner(None)


def preset_defaults(section: str) -> dict[str, object]:
    defaults: dict[str, object] = load_preset("recommended")["defaults"][section]
    return defaults


def refusal(text: str, root: Path) -> Exception:
    """What `loads` refuses `text` with: the reason a reset note gives."""
    with pytest.raises((Failure, Refusal)) as raised:
        loads(text, root, machine=root / "none.toml")
    return raised.value


def reset(key: str, text: str, root: Path) -> str:
    return RESET_NOTE.format(key=clipped(key), reason=refusal(text, root))


UNKNOWN_NAMES = [
    ("[newer]\nx = 1\n", "newer"),  # a section, in loads
    ("[memory]\nfuture = 1\n", "memory.future"),  # a key, in _build
    ("[budgets]\nfuture = 1\n", "budgets.future"),  # a key, in _budgets
    ('[gates.custom.g]\nrun = ["x"]\nfuture = 1\n', "gates.custom.g.future"),  # a key, in _gates
]


@pytest.mark.parametrize(("extra", "named"), UNKNOWN_NAMES, ids=[n for _, n in UNKNOWN_NAMES])
def test_an_unknown_name_is_ignored_with_a_note(tmp_path: Path, extra: str, named: str) -> None:
    got = loads_noting(MINIMAL + extra, tmp_path, owner=OWNER)
    assert got.notes == (UNKNOWN_NOTE.format(name=named),)
    assert_never_raw(*got.notes)


def test_an_unknown_name_is_never_printed_raw(tmp_path: Path) -> None:
    # A TOML key is any quoted text; the note prints it through `printed.clipped`.
    # Mutation (`mutations/`'s "an unknown name's note prints it raw"): the escape byte reaches
    # the note.
    text = MINIMAL + '[memory]\n"\\u001b[2J\\n::error::IGNORE" = 1\n'
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert len(got.notes) == 1
    assert_never_raw(*got.notes)


def test_the_rest_of_a_newer_file_survives(tmp_path: Path) -> None:
    # Review focus: an unknown section, an unknown key and an unknown enum value together, and
    # the project's other settings — a lowered budget, a `[paths]` value — still stand.
    text = (
        MINIMAL
        + '[newer]\nx = 1\n[memory]\nmode = "harness"\nfuture = 1\n'
        + '[budgets]\nagents_md_lines = 250\n[paths]\nspecs = "design/specs"\n'
    )
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert got.config.memory.mode == preset_defaults("memory")["mode"]
    assert got.config.budgets.effective("agents_md_lines") == 250
    assert got.config.paths.specs == "design/specs"
    assert len(got.notes) == 3


def test_an_invalid_value_resets_only_its_key(tmp_path: Path) -> None:
    # Mutation (`mutations/`'s "the NOTE path drops the whole document on a keyed refusal"): the
    # budget the document also set is lost with the bad mode.
    text = MINIMAL + '[memory]\nmode = "harness"\n[budgets]\nagents_md_lines = 900\n'
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert got.config.memory.mode == preset_defaults("memory")["mode"]
    assert got.config.budgets.configured["agents_md_lines"] == 900
    assert got.notes == (reset("memory.mode", text, tmp_path),)


def test_an_escaping_path_resets_only_that_path(tmp_path: Path) -> None:
    # Mutation (`mutations/`'s "the NOTE path catches ConfigError but not PathEscape"): the
    # refusal of `../x` propagates and the session would lose the whole file.
    text = MINIMAL + '[paths]\nbugs = "../x"\nspecs = "design/specs"\n'
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert got.config.paths.bugs == preset_defaults("paths")["bugs"]
    assert got.config.paths.specs == "design/specs"
    assert got.notes == (reset("paths.bugs", text, tmp_path),)


def test_a_path_through_a_symlink_resets_only_that_path(tmp_path: Path) -> None:
    # The second way `validate_paths` refuses: the grammar admits the value and `contained()`
    # finds the symlink on the way. Mutation (`mutations/`'s "validate_paths stops naming the key
    # of a contained() refusal"): the refusal carries no key and the whole file is refused.
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside, root / "elsewhere")
    text = MINIMAL + '[paths]\nbugs = "elsewhere/bugs"\nspecs = "design/specs"\n'
    got = loads_noting(text, root, owner=OWNER)
    assert got.config.paths.bugs == preset_defaults("paths")["bugs"]
    assert got.config.paths.specs == "design/specs"
    assert got.notes == (reset("paths.bugs", text, root),)


def test_an_unknown_preset_resets_to_recommended(tmp_path: Path) -> None:
    # Mutation (`mutations/`'s "the preset name is read before its membership check"): the preset
    # loader's own refusal, which carries no key, propagates.
    text = MINIMAL.replace('preset = "recommended"', 'preset = "future"')
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert got.config.stayfixed.preset == "recommended"
    assert got.notes == (reset("stayfixed.preset", text, tmp_path),)


def test_a_custom_gate_that_cannot_run_is_dropped(tmp_path: Path) -> None:
    # A custom gate has no preset value to fall back to: the gate is left out, and the gates the
    # project's other tables name still run.
    text = MINIMAL + '[gates.custom.bad]\nrun = []\n[gates.custom.good]\nrun = ["true"]\n'
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert sorted(got.config.gates.custom) == ["good"]
    assert got.notes == (reset("gates.custom.bad", text, tmp_path),)


def test_a_repository_guards_section_is_refused_by_resolve(tmp_path: Path) -> None:
    # The repository never sets a machine-only key: `classes.resolve` refuses the layer and the
    # owner's values stand. Mutation (`mutations/`'s "the NOTE path removes a repository's
    # machine-only table without a note"): the two notes go missing.
    machine = tmp_path / "m.toml"
    machine.write_text('[personal]\nreply_language = "ru"\n', encoding="utf-8")
    owner = resolve_owner(machine)
    text = MINIMAL + '[guards]\nbg_cleanup = false\n[personal]\nreply_language = "xx"\n'
    got = loads_noting(text, tmp_path, owner=owner)
    assert got.config.personal == owner.personal
    assert got.config.personal.reply_language == "ru"
    assert got.notes == (
        REFUSED_LAYER_NOTE.format(key="guards.bg_cleanup", layer="repository"),
        REFUSED_LAYER_NOTE.format(key="personal.reply_language", layer="repository"),
    )


def test_the_owners_session_budgets_win_over_the_repositorys(tmp_path: Path) -> None:
    machine = tmp_path / "m.toml"
    machine.write_text("[budgets]\nstartup_rules_words = 900\n", encoding="utf-8")
    # The owner's layer is folded in by both loaders. Mutation (`mutations/`'s "the document's
    # budget wins over the owner's session budget"): 1000 comes back.
    owner = resolve_owner(machine)
    text = MINIMAL + "[budgets]\nstartup_rules_words = 1000\nagents_md_lines = 250\n"
    for config in (
        loads_noting(text, tmp_path, owner=owner).config,
        loads(text, tmp_path, owner=owner),
    ):
        assert config.budgets.configured == {"startup_rules_words": 900, "agents_md_lines": 250}
        assert config.personal == owner.personal


REFUSED = [
    pytest.param("[newer]\nx = 1\n", r"unknown section\(s\): newer", id="section"),
    pytest.param("[memory]\nfuture = 1\n", r"\[memory\] has unknown key\(s\): future", id="key"),
    pytest.param(
        "[budgets]\nfuture = 1\n", r"\[budgets\] has unknown key\(s\): future", id="budget"
    ),
    pytest.param(
        '[gates.custom.g]\nrun = ["x"]\nfuture = 1\n',
        r"\[gates\.custom\.g\] has unknown key\(s\): future",
        id="gate-key",
    ),
    pytest.param('[memory]\nmode = "harness"\n', r"memory\.mode must be one of", id="enum"),
    pytest.param(
        '[paths]\nbugs = "../x"\n', r"paths\.bugs is not a plain relative path", id="path"
    ),
    pytest.param("[guards]\nbg_cleanup = false\n", r"unknown section\(s\): guards", id="guards"),
]


@pytest.mark.parametrize(("extra", "message"), REFUSED)
def test_refuse_still_refuses_each_of_them(tmp_path: Path, extra: str, message: str) -> None:
    # Mutation (`mutations/`'s "_build drops an unknown key under REFUSE"): the `key` case loads.
    with pytest.raises((ConfigError, PathEscape), match=message):
        loads(MINIMAL + extra, tmp_path, machine=tmp_path / "none.toml")


def test_refuse_still_refuses_an_unknown_preset(tmp_path: Path) -> None:
    text = MINIMAL.replace('preset = "recommended"', 'preset = "future"')
    with pytest.raises(ConfigError, match=r"^\[stayfixed\] preset names a preset this version"):
        loads(text, tmp_path, machine=tmp_path / "none.toml")


@pytest.mark.parametrize(
    "text",
    [pytest.param("[[[", id="not-toml"), pytest.param('[project]\nname = "x"\n', id="no-version")],
)
def test_a_document_level_refusal_propagates(tmp_path: Path, text: str) -> None:
    # A refusal with no key is about the whole document: there is nothing to reset.
    with pytest.raises(ConfigError) as raised:
        loads_noting(text, tmp_path, owner=OWNER)
    assert raised.value.key is None


def test_a_key_the_document_does_not_hold_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The retry removes a key the document holds; a validator naming any other cannot loop.
    def refuses(config: object) -> object:
        raise ConfigError("held", key="paths.nowhere")

    monkeypatch.setattr(loader, "_enforcement", refuses)
    with pytest.raises(ConfigError, match=r"^held$"):
        loads_noting(MINIMAL, tmp_path, owner=OWNER)


def test_a_validator_that_keeps_refusing_spends_the_document_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Each retry removes the one key it was handed; once that key is gone the next refusal of
    # it propagates, so the attempts are the keys removed plus one, never a loop. Mutation
    # (`mutations/`'s "the NOTE retry takes a key the document does not hold for removed"): the
    # validator is asked a fourth time and the test reddens.
    handed = ["stayfixed.preset", "paths.specs", "paths.specs"]
    calls: list[str] = []

    def refuses(config: object) -> object:
        calls.append(handed[len(calls)])
        raise ConfigError("held", key=calls[-1])

    monkeypatch.setattr(loader, "_enforcement", refuses)
    with pytest.raises(ConfigError, match=r"^held$"):
        loads_noting(MINIMAL + '[paths]\nspecs = "design/specs"\n', tmp_path, owner=OWNER)
    assert calls == handed


def test_a_custom_gate_whose_name_holds_a_dot_is_dropped_by_its_whole_name(tmp_path: Path) -> None:
    # A custom gate's name may hold a dot, so `gates.custom.a.b` names the gate `a.b`, not a key
    # `b` of a gate `a`. Mutation (`mutations/`'s "the NOTE retry cannot remove a key whose name
    # holds a dot"): the gate is never found, and the whole file is refused.
    text = MINIMAL + '[gates.custom."a.b"]\nrun = []\n'
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert got.config.gates.custom == {}
    assert got.notes == (reset("gates.custom.a.b", text, tmp_path),)


def test_a_section_that_is_not_a_table_is_the_presets(tmp_path: Path) -> None:
    text = "memory = 1\n" + MINIMAL  # before any header, so a top-level key
    got = loads_noting(text, tmp_path, owner=OWNER)
    assert got.config.memory.mode == preset_defaults("memory")["mode"]
    assert got.notes == (reset("memory", text, tmp_path),)


def test_a_repository_guards_value_that_is_not_a_table_is_refused_too(tmp_path: Path) -> None:
    got = loads_noting("guards = false\n" + MINIMAL, tmp_path, owner=OWNER)
    assert got.notes == (REFUSED_LAYER_NOTE.format(key="guards", layer="repository"),)
