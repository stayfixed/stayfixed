from __future__ import annotations

from pathlib import Path

from stayfixed import REPOSITORY_URL
from stayfixed.release.api import Pin, Resolution, is_released, released, resolve_pin
from stayfixed.release.pins import NO_MATCH
from stayfixed.runner import NOT_FOUND
from tests.runners import LsRemote

LIGHT, TAG_OBJECT, COMMIT, ALIAS = "1" * 40, "2" * 40, "3" * 40, "9" * 40
# The per-plugin tag `claude plugin tag` writes beside every release (`RELEASING.md` step 6). It
# is in the fixture because the real listing has one, and it is asserted rather than merely
# present: `PLUGIN_TAG_SHA` must reach neither the pin dictionary nor `is_released`.
PLUGIN_TAG_SHA = "4" * 40
LISTING = (
    f"{LIGHT}\trefs/tags/v0.1.0\n"
    f"{TAG_OBJECT}\trefs/tags/v1.0.0\n"
    f"{COMMIT}\trefs/tags/v1.0.0^{{}}\n"
    f"{ALIAS}\trefs/tags/v1\n"
    f"{PLUGIN_TAG_SHA}\trefs/tags/stayfixed--v1.0.0\n"
)


def test_an_annotated_tag_resolves_to_its_commit_not_its_tag_object(tmp_path: Path) -> None:
    # Mutation (oracle): `{**peeled, **plain}` -> the annotated case answers the tag object,
    # which a workflow pin could not check out.
    stub = LsRemote(stdout=LISTING)
    assert resolve_pin("1.0.0", stub, cwd=tmp_path) == Resolution(Pin("v1.0.0", COMMIT), True)
    assert resolve_pin("0.1.0", stub, cwd=tmp_path) == Resolution(Pin("v0.1.0", LIGHT), True)
    assert len(stub.calls) == 2
    assert stub.calls[0] == ["git", "ls-remote", "--exit-code", REPOSITORY_URL, "refs/tags/v*"]


def test_the_answer_that_stays_apart_is_the_failed_ask(tmp_path: Path) -> None:
    # `released` distinguishes three states; its callers distinguish two. "No such tag" and "no
    # tags at all" are one `Resolution(None, True)` here, one `NO_TAG` sentence in
    # `project.templates._ci` and one red row in `doctor` — and the first two assertions below are
    # what say so. `Resolution.asked` is what keeps the failed ask apart from both, which is the
    # distinction every caller does depend on: running again can help only that one.
    assert resolve_pin("9.9.9", LsRemote(stdout=LISTING), cwd=tmp_path) == Resolution(None, True)
    assert resolve_pin("0.1.0", LsRemote(code=NO_MATCH), cwd=tmp_path) == Resolution(None, True)
    assert resolve_pin("0.1.0", LsRemote(code=NOT_FOUND), cwd=tmp_path) == Resolution(None, False)
    assert released(LsRemote(code=128), cwd=tmp_path) is None


def test_is_released_judges_semver_tags_and_never_the_alias(tmp_path: Path) -> None:
    assert is_released(LIGHT, LsRemote(stdout=LISTING), cwd=tmp_path) is True
    assert is_released(COMMIT, LsRemote(stdout=LISTING), cwd=tmp_path) is True
    assert is_released(ALIAS, LsRemote(stdout=LISTING), cwd=tmp_path) is False
    assert is_released("5" * 40, LsRemote(code=NO_MATCH), cwd=tmp_path) is False
    assert is_released(LIGHT, LsRemote(code=NOT_FOUND), cwd=tmp_path) is None
    pins = released(LsRemote(stdout=LISTING), cwd=tmp_path)
    assert pins is not None
    assert "v1" in pins
    # And the per-plugin tag is not a tag this module answers about. `_LINE` is what drops it — the
    # pattern requires `refs/tags/v`, so `stayfixed--v1.0.0` never reaches the dictionary at all —
    # and `_SEMVER` would drop it a second time downstream. Asserted on both sides, because the
    # fixture line was inert until now: a `uses:` pin resolved to this sha would check out a ref
    # the reusable workflow's own gate never ran on.
    assert "stayfixed--v1.0.0" not in pins
    assert is_released(PLUGIN_TAG_SHA, LsRemote(stdout=LISTING), cwd=tmp_path) is False
