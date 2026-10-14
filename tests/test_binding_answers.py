"""One binding question, one answer, on every surface that asks it.

`memory` commands, `attach`, `attach --check` and `doctor` each say whether the overlay's record
binds this checkout's `origin`. They used to answer it twice, in `memory.store` and in
`attach.binding`, and the two had drifted: a checkout with no `origin`, in a project the overlay
records, was told by the memory commands to add the `origin`, and by `attach`, `attach --check`
and `doctor` that the overlay records a different remote URL and to pass `--trust-remote`, which
then refused because there is no `origin`. The classifier is `memory.store`'s now, and each
surface says the one cause with the one way out.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from stayfixed.attach.check import check
from stayfixed.attach.write import attach
from stayfixed.config.loader import load
from stayfixed.doctor.api import run_checks
from stayfixed.errors import Refusal
from stayfixed.memory.store import NO_ORIGIN_CAUSE, NO_ORIGIN_WAY_OUT, resolved
from tests.attach.test_write import RULE, _attachable
from tests.gitfixture import git
from tests.runners import Recorder

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _attached_then_origin_removed(tmp_path: Path) -> tuple[Path, Path, Path]:
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    git(root, "remote", "remove", "origin")
    return root, store, machine


def test_a_checkout_with_no_origin_hears_one_cause_and_one_way_out_everywhere(
    tmp_path: Path,
) -> None:
    # Mutation: `mutations/`'s "the binding classifier reads a missing origin as a
    # different remote".
    root, store, machine = _attached_then_origin_removed(tmp_path)
    home = tmp_path / "home"

    _, why = resolved(root, load(root, machine=machine), machine=machine)
    assert why is not None
    memory = why.said

    # With and without `--trust-remote`, which is the way out the old answer offered.
    refusals = []
    for trust_remote in (False, True):
        with pytest.raises(Refusal) as refused:
            attach(
                root,
                store=store,
                machine=machine,
                confirmed=True,
                trust_remote=trust_remote,
                runner=Recorder(),
                home=home,
            )
        refusals.append(str(refused.value))

    checked = check(root, store=store, machine=machine, home=home)

    doctor = next(
        row
        for row in run_checks(
            root, home=home, machine=machine, runner=Recorder(), env={"HOME": str(home)}
        )
        if row.name == "attached"
    )

    for surface, said in (
        ("memory", memory),
        ("attach", refusals[0]),
        ("attach --trust-remote", refusals[1]),
        ("attach --check", checked.summary),
        ("doctor", f"{doctor.detail} {doctor.remedy}"),
    ):
        assert NO_ORIGIN_CAUSE in said and NO_ORIGIN_WAY_OUT in said, surface
        assert "--trust-remote" not in said, surface
        assert "different remote" not in said, surface
    assert checked.exit_code != 0
