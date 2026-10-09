from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import pytest

from stayfixed import jsonobject
from stayfixed.errors import Failure, Refusal
from stayfixed.overlay.api import create, init_instance
from stayfixed.overlay.create import RETRY_WAIT_SECONDS, _is_template
from stayfixed.runner import Completed
from tests.parserlimits import LONG_NUMBER, NESTED
from tests.runners import Recorder

# What `gh repo view <slug> --json isTemplate` really prints, measured against gh 2.101.0: a
# template answers `{"isTemplate":true}` with exit 0; a repository that is not one answers
# `{"isTemplate":false}`; a repository that does not exist (or that this token cannot see) exits 1
# with GraphQL's "Could not resolve to a Repository" on stderr; a bad token exits 1 with an HTTP
# 401 line. Exit 1 alone therefore cannot tell "not found" from "not authenticated", and the
# stderr is the only thing that can.
A_TEMPLATE = Completed(0, '{"isTemplate":true}\n', "")
NOT_A_TEMPLATE = Completed(0, '{"isTemplate":false}\n', "")
NO_SUCH_REPOSITORY = Completed(
    1,
    "",
    "GraphQL: Could not resolve to a Repository with the name 'octo/stayfixed-overlay-template'."
    " (repository)\n",
)
# A repository of the owner's own, published or not: the probe `create` asks before it chooses.
THE_OWNERS_PROBE = "gh repo view octo/stayfixed-overlay-template"


def _populate(argv: list[str], cwd: Path) -> None:
    """Stand in for a successful template generation: write the probe `create` looks for."""
    if argv[:3] != ["gh", "repo", "create"]:
        return
    target = cwd / argv[3].split("/")[-1] / ".claude-plugin"
    target.mkdir(parents=True, exist_ok=True)
    (target / "plugin.json").write_text(json.dumps({"name": "stayfixed-overlay"}), encoding="utf-8")


def _the_create_call(runner: Recorder) -> list[str]:
    """The one `gh repo create` argv a run made; more or fewer is a finding in its own right."""
    made = [argv for argv in runner.calls if argv[:3] == ["gh", "repo", "create"]]
    assert len(made) == 1, runner.calls
    return made[0]


def _template_named(runner: Recorder) -> str:
    argv = _the_create_call(runner)
    return argv[argv.index("--template") + 1]


def test_creating_from_the_template_asks_github_for_a_private_repository(tmp_path: Path) -> None:
    # A template rather than a fork, because a fork's visibility is bound to the
    # upstream network and cannot be made private. The `--private` flag is that decision.
    runner = Recorder(answers={THE_OWNERS_PROBE: A_TEMPLATE}, on_call=_populate)
    create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    creating = _the_create_call(runner)
    assert "--private" in creating
    assert "--template" in creating


def test_a_clone_that_raced_generation_is_retried_once_before_failing(tmp_path: Path) -> None:
    # The race did not reproduce in the one measured trial of template generation, and one
    # clean run cannot rule out an asynchronous generation step that sometimes outlasts the
    # clone. The retry is therefore carried on the strength of reasoning, not of a measurement
    # — so it is asserted here rather than left to be discovered by whoever hits it.
    empty = Recorder(answers={THE_OWNERS_PROBE: A_TEMPLATE})
    with pytest.raises(Failure):
        create("octo", "stayfixed-private", source="template", root=tmp_path, runner=empty)
    # The repository's own name, not the template's: the probe is also a `gh repo view`.
    verbs = [argv[:4] for argv in empty.calls]
    assert ["gh", "repo", "view", "octo/stayfixed-private"] in verbs, (
        "must distinguish 'not created' from 'raced'"
    )
    assert ["git", "clone", "--", "git@github.com:octo/stayfixed-private.git"] in verbs


def test_an_existing_populated_clone_is_left_alone(tmp_path: Path) -> None:
    # `create` is idempotent because `gh` may give up on the clone with the repository already
    # created — so the second run finds a tree and must not re-create.
    (tmp_path / "stayfixed-private" / ".claude-plugin").mkdir(parents=True)
    (tmp_path / "stayfixed-private" / ".claude-plugin" / "plugin.json").write_text(
        "{}", encoding="utf-8"
    )
    runner = Recorder()
    created = create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    assert runner.calls == []
    assert "exists" in " ".join(created.notes)


def test_the_local_source_touches_no_network(tmp_path: Path) -> None:
    # The documented fallback when the template repository is unreachable, and the only mode a
    # test may exercise end to end.
    runner = Recorder()
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=runner)
    # "Touches no network" is a claim about `gh`: the one local call is `git init`, asserted on
    # its own below. It used to read `runner.calls == []`, which was that claim while `--local`
    # ran nothing at all.
    assert [argv for argv in runner.calls if argv[0] == "gh"] == []
    assert (created.root / ".claude-plugin" / "plugin.json").is_file()
    assert (created.root / "hooks" / "hooks.json").is_file()


@pytest.mark.parametrize("name", ["../escape", "a/b", "", "-flag"])
def test_a_name_that_is_not_one_path_segment_is_refused(tmp_path: Path, name: str) -> None:
    # A name is one path segment, because it becomes a directory name, a remote path and later
    # a marketplace selector. `-flag` is in the list because a configured value shaped like an
    # option never reaches a subprocess in an option's position.
    with pytest.raises(Refusal):
        create("octo", name, source="local", root=tmp_path, runner=Recorder())


def test_init_renames_the_plugin_and_marketplace_for_the_owner(tmp_path: Path) -> None:
    # The owner's suffix is what keeps two overlays installed into one harness from colliding.
    # A measured trial added and installed an owner-suffixed pair, pushed to a private SSH
    # remote, without error under a scratch CLAUDE_CONFIG_DIR.
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    init_instance(created.root, "OctoCat", runner=Recorder())
    plugin = json.loads((created.root / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((created.root / ".claude-plugin" / "marketplace.json").read_text())
    assert plugin["name"] == "stayfixed-overlay-octocat"
    assert market["name"] == "stayfixed-overlay-marketplace-octocat"


def test_init_installs_pre_commit_and_says_so_when_it_cannot(tmp_path: Path) -> None:
    # gitleaks runs twice over the overlay, and one of the two is this hook. A missing
    # `pre-commit` is a reported finding, never a traceback — the binary is optional.
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    missing = Recorder(answers={"pre-commit": Completed(127, "", "not found")})
    result = init_instance(created.root, "octo", runner=missing)
    # "did not run" and not merely "pre-commit": the success note names the tool too, so the
    # weaker match held on either outcome and this half asserted nothing.
    assert any("`pre-commit install` did not run" in note for note in result.notes)
    assert not any("installed the commit-time" in note for note in result.notes)


def test_init_refuses_a_directory_that_is_not_an_overlay_before_touching_it(
    tmp_path: Path,
) -> None:
    # `--root` defaults to `.`, and `init` asked nothing of it: run inside the stayfixed checkout
    # itself, it renamed all three plugin manifests and installed a commit hook there. `upgrade`
    # had the guard and `setup` uses it twice; this is the caller `identity.py` was written for
    # that it did not list. Mutation: the `require_overlay` line removed → the manifest below is
    # renamed and the runner is called.
    project = tmp_path / "project"
    (project / ".claude-plugin").mkdir(parents=True)
    manifest = project / ".claude-plugin" / "plugin.json"
    manifest.write_text(json.dumps({"name": "somebody-elses-plugin"}), encoding="utf-8")
    runner = Recorder()
    with pytest.raises(Refusal) as refused:
        init_instance(project, "octo", runner=runner)
    assert "overlay init" in str(refused.value)
    assert json.loads(manifest.read_text())["name"] == "somebody-elses-plugin"
    assert runner.calls == []


def test_init_is_idempotent(tmp_path: Path) -> None:
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    first = init_instance(created.root, "octo", runner=Recorder())
    second = init_instance(created.root, "octo", runner=Recorder())
    assert first.renamed != () and second.renamed == ()


def test_the_cli_never_picks_the_github_source_for_you() -> None:
    # A rule with no other witness: `--template` is never the default, and an invocation with
    # neither flag refuses and names both. A repository is created on an account only after
    # explicit confirmation, and a non-interactive caller — the usual one in this harness — can
    # express confirmation only by naming the source. Mutation:
    # `source="template"` in that parser's `set_defaults` and this reddens; it is declared as
    # `mutations/`'s "overlay create picks the GitHub source when nobody asked for it", because the
    # failure creates a repository nobody asked for.
    from stayfixed.cli import build_parser, discover_registrars
    from stayfixed.overlay.commands import run_overlay_create

    args = build_parser(discover_registrars()).parse_args(["overlay", "create", "--owner", "octo"])
    with pytest.raises(Refusal) as refused:
        run_overlay_create(args)
    assert "--template" in str(refused.value)
    assert "--local" in str(refused.value)


def test_the_wait_before_the_retry_is_spent_only_on_the_race(tmp_path: Path) -> None:
    # "on the second, wait and retry once": the pause exists for an asynchronous generation step
    # that may still be running, so it is spent only when `gh repo view` names the repository
    # back. Spending it when nothing was created is ten seconds bought with nothing, and it is
    # the branch the retry test above never reaches. Mutation: make the wait unconditional and
    # the second half reddens; drop it entirely and the first half does.
    named: list[float] = []
    answering = Recorder(
        answers={
            "gh": Completed(0, "stayfixed-private\n", ""),
            THE_OWNERS_PROBE: A_TEMPLATE,
        }
    )
    with pytest.raises(Failure):
        create(
            "octo",
            "stayfixed-private",
            source="template",
            root=tmp_path,
            runner=answering,
            wait=named.append,
        )
    assert named == [RETRY_WAIT_SECONDS]

    silent: list[float] = []
    with pytest.raises(Failure):
        create(
            "octo",
            "stayfixed-private",
            source="template",
            root=tmp_path,
            runner=Recorder(answers={THE_OWNERS_PROBE: A_TEMPLATE}),
            wait=silent.append,
        )
    assert silent == []


def test_a_render_that_cannot_start_leaves_no_probe_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The directory `--local` has to create first is `<name>/.claude-plugin`, which is exactly
    # the probe `--template` reads as "this was already created". So a `--local` that refused
    # after creating it would leave the owner in the one state where the honest recovery —
    # `overlay create --template` — reports "already exists and was left alone" and never
    # creates the repository at all. Everything that can refuse therefore runs first. Mutation:
    # move the `plan(...)` call back below `mkdirs_within` and this reddens on the second
    # assertion, with a directory on disk and no repository anywhere.
    def _unavailable() -> NoReturn:
        raise Failure("this stayfixed was installed without the template tree")

    monkeypatch.setattr("stayfixed.overlay.create.templates", _unavailable)
    with pytest.raises(Failure):
        create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    assert not (tmp_path / "stayfixed-private").exists()


def test_a_mixed_case_owner_gets_one_answer_from_both_commands(tmp_path: Path) -> None:
    # `SEGMENT` has a lowercase leading class and a mixed-case GitHub login is ordinary, so the
    # two commands have to fold alike. `create` validated the raw value while `init_instance`
    # folded first, which refused `--owner OctoCat` from `overlay create` and accepted it from
    # the other — one owner string, two answers, and a refusal saying "is not one path segment"
    # about a value that is one. Mutation: validate `owner` rather than `account` in `create`
    # and the first half reddens with a `Refusal`.
    remote = tmp_path / "remote"
    remote.mkdir()
    runner = Recorder(
        answers={"gh repo view octocat/stayfixed-overlay-template": A_TEMPLATE}, on_call=_populate
    )
    create("OctoCat", "stayfixed-private", source="template", root=remote, runner=runner)
    # And the fold reaches the argv, not just the validator: GitHub is case-insensitive about a
    # login, but the value is also a directory name and a manifest suffix, and those are not.
    assert "octocat/stayfixed-private" in _the_create_call(runner)
    assert runner.calls[0][3] == "octocat/stayfixed-overlay-template", "the probe folds too"

    local = tmp_path / "local"
    local.mkdir()
    created = create("OctoCat", "stayfixed-private", source="local", root=local, runner=Recorder())
    init_instance(created.root, "OctoCat", runner=Recorder())
    plugin = json.loads((created.root / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "stayfixed-overlay-octocat"


def test_a_gh_that_cannot_be_run_at_creation_is_named_as_the_cause_and_costs_no_more_calls(
    tmp_path: Path,
) -> None:
    # `Completed` has carried `code` and `stderr` since this seam was written and `overlay.create`
    # threw both away: with `gh` absent from `PATH`, the command launched three subprocesses and
    # then exited 1 saying "GitHub did not confirm the repository exists; check `gh auth status`" —
    # a cause that was not the cause, about a binary that was not there. A missing optional binary
    # is a reported finding, and never a misattributed one.
    #
    # The probe is answered here and `gh repo create` is what cannot run (a `gh` that hung, or was
    # removed between the two calls), because the probe has its own arm and its own test below;
    # this is the one that reaches the creation arm.
    #
    # Mutation (`mutations/`'s "overlay create --template asks GitHub about a `gh` that
    # could not run"): the `NOT_FOUND`/`TIMED_OUT` arm becomes `if False:` → two more
    # subprocesses run and the message names `gh auth status` instead of the launch failure.
    absent = Recorder(
        answers={
            THE_OWNERS_PROBE: A_TEMPLATE,
            "gh repo create": Completed(127, "", "gh could not be run: [Errno 2] gh"),
        }
    )
    waited: list[float] = []
    with pytest.raises(Failure) as failed:
        create(
            "octo",
            "stayfixed-private",
            source="template",
            root=tmp_path,
            runner=absent,
            wait=waited.append,
        )
    message = str(failed.value)
    assert "gh could not be run" in message, "the real cause is in Completed.stderr"
    assert "gh auth status" not in message, "a binary that never ran cannot have a bad token"
    assert "--local" in message, "the source that works today has to be named"
    # The sentence only this arm produces. `Runner`'s own docstring keeps "not installed" and
    # "hung for five minutes" apart because their remedies differ, and without this assertion
    # the mutation below survives: the next arm — `gh` ran and declined — quotes the same
    # stderr and stops after the same one call, so every other assertion here holds under it.
    assert "Install `gh` and authenticate it" in message
    assert [argv[:3] for argv in absent.calls] == [
        ["gh", "repo", "view"],
        ["gh", "repo", "create"],
    ]
    assert waited == [], "nothing was waiting to finish generating"


def test_a_gh_that_ran_and_declined_quotes_its_own_answer(tmp_path: Path) -> None:
    # The other arm of the same defect, and the one `docs/cli.md` names as the likeliest
    # reason `--template` fails: neither template repository exists yet. `gh`'s own stderr says
    # so, and is quoted rather than replaced by a guess about authentication.
    declined = Recorder(
        answers={
            THE_OWNERS_PROBE: A_TEMPLATE,
            "gh repo create": Completed(1, "", "GraphQL: Could not resolve to a Repository"),
        }
    )
    with pytest.raises(Failure) as failed:
        create("octo", "stayfixed-private", source="template", root=tmp_path, runner=declined)
    message = str(failed.value)
    assert "Could not resolve to a Repository" in message
    assert "stayfixed overlay publish-template" in message
    assert "exited 1" in message, "a binary that ran has an exit code, not a launch failure"
    assert [argv[:3] for argv in declined.calls] == [
        ["gh", "repo", "view"],
        ["gh", "repo", "create"],
    ]


# --- which template `--template` generates from ------------------------------------------------


def test_the_owners_own_template_is_used_when_they_have_published_one(tmp_path: Path) -> None:
    # A person who publishes their own template gets their own copy, so an overlay they generate
    # is exactly the tree their `publish-template` put there. Mutation (`mutations/`'s
    # "overlay create never asks whose template to use"): the probe is dropped and the publisher's
    # template is always named → this reddens on the argv.
    runner = Recorder(answers={THE_OWNERS_PROBE: A_TEMPLATE}, on_call=_populate)
    created = create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    assert runner.calls[0] == [
        "gh",
        "repo",
        "view",
        "octo/stayfixed-overlay-template",
        "--json",
        "isTemplate",
    ]
    assert _template_named(runner) == "octo/stayfixed-overlay-template"
    assert "octo/stayfixed-overlay-template" in " ".join(created.notes)
    assert len([argv for argv in runner.calls if argv[:3] == ["gh", "repo", "view"]]) == 1


def test_the_publishers_template_is_used_when_the_owner_has_none(tmp_path: Path) -> None:
    # A personal account with no copy of the template could not create an overlay at all: the
    # documented contract asked for a repository nobody had told them to publish. The answer to
    # "does <owner>/stayfixed-overlay-template exist" is `gh`'s real not-found shape (see
    # `NO_SUCH_REPOSITORY`), and it falls back to the publisher's own public template.
    # Mutation (`mutations/`'s "overlay create has no template to fall back on"): the
    # fallback is dropped and the owner's template is always named → this reddens.
    #
    # Named with its host. `gh` resolves an unqualified `OWNER/REPO` on `GH_HOST`, which the runner
    # keeps, so on a GitHub Enterprise host the fallback named whoever owns `stayfixed` there, and
    # the owner's private overlay -- whose hooks run in every session -- was generated from it.
    # `github.com/OWNER/REPO` is looked up on github.com whatever `GH_HOST` says (measured against
    # gh 2.101.0 with `GH_HOST` set to another host). The owner's own probe above stays
    # host-relative: that repository is on the owner's own host. Mutation (`mutations/`'s "the
    # publisher's template is named on whatever host gh defaults to") → this reddens on the argv.
    runner = Recorder(answers={THE_OWNERS_PROBE: NO_SUCH_REPOSITORY}, on_call=_populate)
    created = create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    assert _template_named(runner) == "github.com/stayfixed/stayfixed-overlay-template"
    assert "github.com/stayfixed/stayfixed-overlay-template" in " ".join(created.notes)


def test_a_repository_that_is_not_a_template_is_not_generated_from(tmp_path: Path) -> None:
    # `gh repo create --template` on an ordinary repository fails; an owner whose repository of
    # that name is not marked as a template has not published one, and gets the publisher's.
    runner = Recorder(answers={THE_OWNERS_PROBE: NOT_A_TEMPLATE}, on_call=_populate)
    create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    assert _template_named(runner) == "github.com/stayfixed/stayfixed-overlay-template"


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        pytest.param(
            Completed(
                1, "", "HTTP 401: Bad credentials (https://api.github.com/graphql)\nTry `gh auth`"
            ),
            "Bad credentials",
            id="authentication",
        ),
        pytest.param(
            Completed(
                1,
                "",
                "error connecting to api.github.com: Could not resolve host: api.github.com",
            ),
            "Could not resolve host",
            id="network-that-also-says-could-not-resolve",
        ),
        pytest.param(
            Completed(127, "", "gh could not be run: [Errno 2] gh"),
            "gh could not be run",
            id="gh-absent",
        ),
        pytest.param(Completed(124, "", "gh did not answer in 300s"), "300s", id="gh-hung"),
        pytest.param(Completed(0, "not json at all\n", ""), "not json at all", id="not-json"),
        pytest.param(Completed(0, '{"isTemplate": "yes"}\n', ""), "yes", id="not-a-boolean"),
    ],
)
def test_a_probe_that_failed_for_another_reason_never_switches_the_template(
    tmp_path: Path, answer: Completed, said: str
) -> None:
    # The hazard the discrimination exists for: `gh` exits 1 both for a repository that is not
    # there and for a token that is not valid, so "exit 1" cannot be read as "not found". A
    # transient failure that fell back to the publisher's template would silently generate the
    # overlay of a person who HAS their own template from somebody else's, and they would not
    # know. Only the not-found shape (`NO_SUCH_REPOSITORY`) falls back; everything else refuses
    # with gh's own words and `gh repo create` never runs.
    # Mutation: treat every non-zero exit of the probe as not-found → the first two cases redden.
    runner = Recorder(answers={THE_OWNERS_PROBE: answer}, on_call=_populate)
    with pytest.raises(Failure) as failed:
        create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    assert said in str(failed.value)
    assert not [argv for argv in runner.calls if argv[:3] == ["gh", "repo", "create"]]
    assert not (tmp_path / "stayfixed-private").exists()


def test_a_probe_failure_is_printed_without_letting_it_drive_a_terminal(tmp_path: Path) -> None:
    # `gh`'s stderr can carry whatever a proxy or a wrapper put in it, and this message reaches a
    # terminal and a CI log: a line break followed by `::error::` is a workflow command there.
    hostile = Completed(1, "", "HTTP 401\n::error::forged\x1b[2J")
    runner = Recorder(answers={THE_OWNERS_PROBE: hostile})
    with pytest.raises(Failure) as failed:
        create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    message = str(failed.value)
    assert "\n::error::" not in message
    assert "\x1b" not in message


HOSTILE = Completed(1, "", "HTTP 500\n::error::forged\x1b[2J")


@pytest.mark.parametrize(
    "answers",
    [
        pytest.param({THE_OWNERS_PROBE: A_TEMPLATE, "gh repo create": HOSTILE}, id="repo-create"),
        pytest.param(
            {THE_OWNERS_PROBE: A_TEMPLATE, "gh repo view octo/stayfixed-private": HOSTILE},
            id="clone-and-view",
        ),
    ],
)
def test_what_gh_and_git_print_cannot_drive_a_terminal(
    tmp_path: Path, answers: dict[str, Completed]
) -> None:
    # The probe's answer was clipped and quoted, and every other subprocess answer this command
    # quotes, `gh repo create`'s, `gh repo view`'s and `git clone`'s, was printed raw: a line break
    # followed by `::error::` is a workflow command in a CI log, and an escape drives a terminal.
    # They are all clipped in the one place that reads them, `_detail`.
    #
    # Mutation: `mutations/`'s "a subprocess's answer is quoted raw".
    runner = Recorder(answers={**answers, "git clone": HOSTILE})
    with pytest.raises(Failure) as failed:
        create("octo", "stayfixed-private", source="template", root=tmp_path, runner=runner)
    message = str(failed.value)
    assert "forged" in message
    assert "\n::error::" not in message
    assert "\x1b" not in message


def test_what_git_init_prints_cannot_drive_a_terminal(tmp_path: Path) -> None:
    # The same for the `--local` branch's `git init`, whose failure is a note.
    runner = Recorder(answers={"git init": HOSTILE})
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=runner)
    message = " ".join(created.notes)
    assert "forged" in message
    assert "\n::error::" not in message
    assert "\x1b" not in message


def test_a_gh_that_is_not_installed_costs_one_subprocess_at_the_probe(tmp_path: Path) -> None:
    # Absent at the very first question: one launch, the launch failure named, no
    # `gh repo create`, no clone, no wait.
    absent = Recorder(answers={"gh": Completed(127, "", "gh could not be run: [Errno 2] gh")})
    waited: list[float] = []
    with pytest.raises(Failure) as failed:
        create(
            "octo",
            "stayfixed-private",
            source="template",
            root=tmp_path,
            runner=absent,
            wait=waited.append,
        )
    message = str(failed.value)
    assert "gh could not be run" in message
    assert "gh auth status" not in message
    assert "--local" in message
    assert [argv[:3] for argv in absent.calls] == [["gh", "repo", "view"]]
    assert waited == []


# --- `--local` leaves a repository -------------------------------------------------------------


def test_a_local_overlay_is_a_git_repository_on_main_with_no_remote(tmp_path: Path) -> None:
    # `create --local` used to leave a bare directory, so the owner's next step (commit it, push
    # it to a private repository) began with a `git init` nobody had told them about. The init
    # is `create`'s `--local` branch and not `_render_locally`, which `publish-template` also
    # uses for its scratch render. Mutation (`mutations/`'s "overlay create --local leaves no
    # git repository"): the `git init` call is deleted → this reddens.
    runner = Recorder()
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=runner)
    assert runner.calls == [["git", "init"], ["git", "symbolic-ref", "HEAD", "refs/heads/main"]]
    assert runner.cwds == [created.root, created.root]
    assert not any(argv[0] == "gh" for argv in runner.calls), "`--local` touches no GitHub"
    message = " ".join(created.notes)
    assert "git remote add origin git@github.com:octo/stayfixed-private.git" in message
    assert "git push -u origin main" in message


def test_a_local_overlay_carries_a_real_repository_on_main(tmp_path: Path) -> None:
    # The same claim against a real `git`, because a stub records the argv and cannot say whether
    # the argv makes a repository: `symbolic-ref` is `git`'s own and `HEAD` is where it shows.
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    from stayfixed.runner import subprocess_runner

    created = create(
        "octo", "stayfixed-private", source="local", root=tmp_path, runner=subprocess_runner()
    )
    head = (created.root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    assert head == "ref: refs/heads/main"
    config = (created.root / ".git" / "config").read_text(encoding="utf-8")
    assert "[remote" not in config, "no remote: the owner adds it once the repository exists"


def test_a_git_that_cannot_init_is_a_note_and_the_tree_is_kept(tmp_path: Path) -> None:
    # The tree is already rendered when `git init` runs, so a missing `git` cannot un-render it;
    # refusing would only hide a directory that exists. The note says what to run.
    runner = Recorder(answers={"git": Completed(127, "", "git could not be run: [Errno 2] git")})
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=runner)
    assert (created.root / ".claude-plugin" / "plugin.json").is_file()
    message = " ".join(created.notes)
    assert "git could not be run" in message
    assert "could not be run" in message and "did not run" not in message
    assert "`git init` and `git symbolic-ref HEAD refs/heads/main`" in message


def test_a_git_older_than_2_28_still_leaves_a_repository_on_main(tmp_path: Path) -> None:
    # `git init -b` arrived in git 2.28, and an older `git` refuses the option: the run said
    # `git init -b main` "did not run" and told the owner to run the same failing command.
    # `git init` and then `git symbolic-ref HEAD refs/heads/main` name the branch on every
    # version.
    #
    # Mutation: `mutations/`'s "overlay create --local asks git init for its branch".
    runner = Recorder(answers={"git init -b": Completed(129, "", "error: unknown switch `b'")})
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=runner)
    assert ["git", "init", "-b", "main"] not in runner.calls
    assert "made it a git repository on main" in " ".join(created.notes)


def test_a_git_init_that_ran_and_failed_is_said_to_have_failed(tmp_path: Path) -> None:
    # A `git` that ran and exited non-zero ran: the note says how it ended, not that it did not
    # run.
    #
    # Mutation: `mutations/`'s "a git init that failed is said not to have run".
    runner = Recorder(answers={"git init": Completed(128, "", "fatal: cannot mkdir")})
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=runner)
    message = " ".join(created.notes)
    assert "`git init` exited 128" in message
    assert "did not run" not in message and "could not be run" not in message


def test_the_scratch_render_publish_template_uses_is_not_a_repository(tmp_path: Path) -> None:
    # `_render_locally` is shared with `publish-template`, whose scratch tree is cloned over and
    # then replaced: a `.git` of its own there would be pushed as a nested repository. The init
    # belongs to the `--local` branch alone.
    from stayfixed.overlay.create import _render_locally

    rendered = _render_locally(tmp_path, "scratch")
    assert not (rendered / ".git").exists()


# --- the manifests the harness validates -------------------------------------------------------


def test_init_names_the_owner_and_the_author_the_harness_asks_for(tmp_path: Path) -> None:
    # A marketplace with no `owner` fails `claude plugin validate`, and a plugin manifest with no
    # `author` draws a warning on every install. The template ships a neutral placeholder for
    # both and `init` is where the account it belongs to goes in. Mutation: drop the owner/author
    # branch of `naming.renamed` → the placeholder is still there after init and this reddens.
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    init_instance(created.root, "OctoCat", runner=Recorder())
    market = json.loads((created.root / ".claude-plugin" / "marketplace.json").read_text())
    assert market["owner"] == {"name": "octocat"}
    for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        manifest = json.loads((created.root / relative).read_text(encoding="utf-8"))
        assert manifest["author"] == {"name": "octocat"}, relative


def test_init_completes_an_overlay_whose_template_predates_the_owner_and_author(
    tmp_path: Path,
) -> None:
    # The owner's own published template is used first, and one published by an earlier stayfixed
    # carries neither key. `init` is the one command that runs on every such overlay, so it adds
    # what is missing rather than leaving a marketplace the harness refuses.
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    for relative, removed in (
        (".claude-plugin/marketplace.json", "owner"),
        (".claude-plugin/plugin.json", "author"),
        (".codex-plugin/plugin.json", "author"),
    ):
        path = created.root / relative
        document = json.loads(path.read_text(encoding="utf-8"))
        del document[removed]
        path.write_text(json.dumps(document), encoding="utf-8")
    init_instance(created.root, "octo", runner=Recorder())
    market = json.loads((created.root / ".claude-plugin" / "marketplace.json").read_text())
    assert market["owner"] == {"name": "octo"}
    plugin = json.loads((created.root / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["author"] == {"name": "octo"}


def test_init_keeps_an_author_the_owner_wrote_themselves(tmp_path: Path) -> None:
    # Only the placeholder is replaced: a person who put their own name in `author` before
    # running `init`, or who runs it a second time, keeps it.
    #
    # Mutation: `mutations/`'s "overlay init replaces an author the owner wrote".
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    path = created.root / ".claude-plugin" / "plugin.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["author"] = {"name": "Jane Doe", "email": "jane@example.com"}
    path.write_text(json.dumps(document), encoding="utf-8")
    init_instance(created.root, "octo", runner=Recorder())
    assert json.loads(path.read_text(encoding="utf-8"))["author"] == {
        "name": "Jane Doe",
        "email": "jane@example.com",
    }


def test_init_names_the_codex_manifest_after_the_owner_too(tmp_path: Path) -> None:
    # `init_instance`'s own docstring gives the rationale — a harness
    # installs a plugin by the name in its manifest, so two owners' overlays under one
    # configuration directory are one plugin fighting itself — and the project ships a Codex
    # half of everything else, but `.codex-plugin/plugin.json` was left unsuffixed, so the
    # collision the suffix exists to prevent still happened on Codex.
    #
    # Mutation (`mutations/`'s "overlay init leaves the Codex manifest unsuffixed"):
    # the Codex row is dropped from `naming.NAMED` → this reddens on the third name.
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    init_instance(created.root, "OctoCat", runner=Recorder())
    names = {
        relative: json.loads((created.root / relative).read_text(encoding="utf-8"))["name"]
        for relative in (
            ".claude-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            ".codex-plugin/plugin.json",
        )
    }
    assert names == {
        ".claude-plugin/plugin.json": "stayfixed-overlay-octocat",
        ".claude-plugin/marketplace.json": "stayfixed-overlay-marketplace-octocat",
        ".codex-plugin/plugin.json": "stayfixed-overlay-octocat",
    }


def test_a_manifest_this_overlay_does_not_carry_is_a_note_not_a_failure(tmp_path: Path) -> None:
    # An overlay generated before the Codex half shipped carries two of the three manifests,
    # and refusing to name the other two over it would make `init` unusable on exactly the
    # overlays that most need running it. A manifest that *exists* and cannot be read is still
    # a failure — that is a file saying something this command cannot act on.
    created = create("octo", "stayfixed-private", source="local", root=tmp_path, runner=Recorder())
    (created.root / ".codex-plugin" / "plugin.json").unlink()
    result = init_instance(created.root, "octo", runner=Recorder())
    assert ".codex-plugin/plugin.json" not in result.renamed
    assert any(".codex-plugin/plugin.json" in note for note in result.notes)


def test_a_local_render_over_an_existing_repository_says_what_it_found(tmp_path: Path) -> None:
    # `--local` renders into `<root>/<name>` whether or not a repository is already there, and
    # `git init` over one is a no-op that changes neither its branch nor its remotes. The note
    # said "made it a git repository on main with no remote" anyway -- about a repository on
    # another branch with an `origin` -- and told the owner to add a remote it already had.
    #
    # Mutation (`mutations/`'s "overlay create --local reads an existing repository as one it
    # made"): the check for an existing repository is dropped → this reddens.
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    from stayfixed.runner import subprocess_runner
    from tests.gitfixture import git

    target = tmp_path / "stayfixed-private"
    target.mkdir()
    git(target, "init", "-q", "-b", "work")
    git(target, "remote", "add", "origin", "git@example.com:octo/stayfixed-private.git")
    created = create(
        "octo", "stayfixed-private", source="local", root=tmp_path, runner=subprocess_runner()
    )
    message = " ".join(created.notes)
    assert "already a git repository" in message
    assert "made it a git repository" not in message
    assert "git remote add origin" not in message
    head = (created.root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    assert head == "ref: refs/heads/work"
    assert '[remote "origin"]' in (created.root / ".git" / "config").read_text(encoding="utf-8")


def test_a_local_render_over_an_existing_repository_runs_no_git_init(tmp_path: Path) -> None:
    # The stub half: over an existing repository there is nothing for `git init` to do.
    (tmp_path / "stayfixed-private" / ".git").mkdir(parents=True)
    runner = Recorder()
    create("octo", "stayfixed-private", source="local", root=tmp_path, runner=runner)
    assert runner.calls == []


@pytest.mark.parametrize(
    "printed", [NESTED, f'{{"isTemplate": {LONG_NUMBER}}}'], ids=["nested", "long"]
)
def test_a_template_probe_past_the_parser_is_no_answer(printed: str) -> None:
    # Valid JSON that `json.loads` answers with `RecursionError` or a plain `ValueError`: the
    # probe caught only `JSONDecodeError`, so either ended `overlay create` in an internal error
    # where an answer that is not JSON reads as no answer. Mutation (declared): the catch narrowed
    # to `JSONDecodeError` again.
    assert _is_template(printed) is None


def test_a_template_probe_past_the_depth_bound_is_no_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The probe's answer goes through the one JSON object reader and its depth bound. Mutation
    # (declared): `mutations/`'s "the template probe parses with a bare json.loads".
    monkeypatch.setattr(jsonobject, "DEPTH_CAP", 4)
    assert _is_template('{"isTemplate": true, "a": [[[[]]]]}') is None
