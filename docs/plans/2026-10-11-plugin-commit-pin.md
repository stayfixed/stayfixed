# The plugin pinned by commit: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **The wave is the dispatch unit, not the task.** Waves are lettered (`A`–`G`) and own a run of
> the continuously numbered tasks. One implementer, one review round and one reviewer per
> **dispatched** wave; inside a wave every task keeps its own failing test, verification and
> commit. Do not dispatch one subagent per task.
>
> **The controller runs two things itself:** the pre-flight measurements (Execution contract,
> section 6) before Wave A, and Task 8 after Wave F. Both run the real `claude` CLI or a read-only
> `gh` against GitHub, and each such `gh` call waits for the owner's yes in that session.
>
> **One pull request** (`wp/plugin-commit-pin`, into `dev`), waves in order on one branch, rebased
> on `dev` before every push. Every dispatched seat runs on Opus.
>
> **Review rounds stop at Minors.** Only a Critical or Important finding opens another fix round;
> a Minor goes to Findings' "Follow-ups" and is filed when the pull request closes.

**Goal:** lift `RELEASING.md`'s release blocker so `0.3.0` can be cut: the marketplace entry pins
the plugin repository's commit by `sha` beside its `ref`, that commit is a pure function of the
release commit, `scripts/release.py check --tag` verifies the pin offline, and
`scripts/publish_plugin.py` builds the commit with the tag's own code and says by its exit code
whether the owner rejects the `pypi` approval (`1`) or fixes something and runs it again (`2`).

**Architecture:** `scripts/plugin_tree.py` gains the plugin commit: `plugin_commit` writes the
members' blobs (`git fast-import`, from memory) and trees (`mktree`) into a SHA-1 bare repository,
and a hand-written commit object — fixed author, committer and date, a message naming the version,
and as its parent the `sha` the marketplace pinned at the source commit's first parent — so every
reader computes the same id; the `commit` CLI prints it beside the `sha` the source commit itself
pins, and `--require-pin` makes a difference exit `1`. `scripts/release.py` gains `pin`, which
writes that id into the marketplace entry after checking the plugin repository's `main` is its
parent, and `check --tag` refuses a pin that is not the id. `scripts/publish_plugin.py` reads
`scripts/plugin_tree.py` and `src/stayfixed` out of the tag's objects and runs that copy, verifies
the attestation with an exact certificate identity, decides the remote's state from GitHub's API on
the default remote, compares commit ids instead of manifests, moves `main` only by fast-forward,
and raises `Rejected` (exit `1`) or `Refusal` (exit `2`). `release.yml` attests the packages and
the manifest in an `attest` job that runs no suite, and refuses the gated jobs until the plugin
repository's tag names the pinned commit; the smoke installs by `ref` and `sha` from a commit
`plugin_tree.py commit` built. No script imports another.

**Tech Stack:** Python ≥ 3.11.0 standard library; `uv`, pytest (`-n auto`), ruff, mypy, the
mutation oracle (`scripts/mutation_oracle.py`), towncrier fragments; git plumbing (`fast-import`,
`mktree`, `hash-object -t commit`, `ls-tree`, `cat-file`); GitHub Actions; `gh` 2.101 on the
owner's machine; the `claude` CLI 2.1.261 in CI.

**Spec:** the agent-harness extraction design, in a private repository this one cannot link to —
§5.9 (the release, amended 2026-10-10 with the plugin's own repository) and §15.7 (wave 8's
outcome). Both still describe a plugin "pinned to the tag" and a digest check, and lack the
decisions below; Task 8 Step 4 amends them after the merge. The decisions this plan implements
are the owner's of 2026-10-11, recorded in `docs/plans/2026-10-10-plugin-repository.md`, Findings,
"External review and the owner's decisions (2026-10-11)": pin the commit (`sha` beside `ref`; a
deterministic plugin commit — fixed author and date, a message without the source sha, the previous
release's `sha` as its parent — that the release commit can name and `release.py check --tag` can
verify offline; "already published" a comparison of commit ids); keep the subprocess boundary and
run the tag's own renderer (`scripts/plugin_tree.py` and `src/stayfixed` from the tag); type the
publisher's outcomes by exit code, `1` reject and `2` fix and run again, held by tests. The same
record lists this plan's remaining scope, each item restated where a task takes it. A review of
this plan (Findings, "Plan review") changed it before dispatch.

**Scope:** a change belongs here iff it (a) computes, writes, pins, checks or publishes the plugin
commit; (b) types the publisher's outcomes or hardens what it trusts; (c) builds, installs, attests
or gates on the plugin commit in a workflow; (d) is a simplification or test-scaffolding item that
record lists for `scripts/plugin_tree.py`, `scripts/publish_plugin.py`, `scripts/release.py` or
their tests; or (e) restates the documents those changes falsify, including how a release returns
to `dev`. Out: the `0.3.0` release itself; creating `stayfixed/stayfixed-plugin` or its rulesets
(section 3 gains a third one here, the owner runs it); anything under `src/stayfixed/`, `hooks/`,
`skills/`, `agents/`; publishing an older version line (refused, Task 4); Codex's install path;
`README.md`'s install paragraph, which names `0.2.0` until the release edits it.

**Premise:** measured on 2026-10-11 at `dev` = `9968c4b`. A task that finds one no longer holds
stops and reports the mismatch instead of guessing.

- **`scripts/plugin_tree.py`** (298 lines): `PLUGIN_PATHS` (nine), `FORMAT = "stayfixed-plugin-tree
  1"`, `REGULAR_MODES`, `GIT_OPTIONS = ("--no-replace-objects", "-c", "safe.bareRepository=all")`,
  `Member(path, mode, content)`, `commit(root, rev) -> str` (no length check), `members(root, rev,
  *, exact=False)` (calls `commit` itself; sorted), `manifest(entries)` (sorts again; pinned by
  `test_the_manifest_is_one_line_per_member_in_order` with unsorted input), `render(entries, out)`,
  `_under(path, entry)`, `_control(path)` (refuses `< 0x20` and `0x7F` only). The module docstring's
  paragraph "The order needs no mutation" is bookkeeping. CLI `manifest` (`--manifest-file`
  optional) and `render` (required); `run_manifest`/`run_render` call `commit()` and then
  `members()`, which resolves again.
- **`scripts/publish_plugin.py`** (536 lines) renders with the checkout's `plugin_tree.py`;
  `_tag_commit` peels with `--no-replace-objects` and checks `len(sha) != 40`; `_verify` uses
  `--signer-workflow` (a prefix match in gh 2.101); `_manifest_rows`, `MANIFEST_FORMAT`,
  `FILE_MODES` re-read what `plugin_tree.py` wrote; `_already` compares the remote tag's manifest;
  `_build`/`_mktree` write with `hash-object -w --no-filters` and `mktree -z` and the commit with
  `commit-tree`, which stamps the time; `main` is always the parent and always pushed; `_network`
  runs `ls-remote`/`fetch`/`push` with `NO_HOOKS = ("-c", "core.hooksPath=/dev/null")`;
  `_remote_refs` selects exact ref names because `ls-remote` matches patterns by their tail;
  `Published` carries `pushed` and `already`; every refusal exits `2`. 36 tests in
  `tests/scripts/test_publish_plugin.py`, 33 `mutations/tooling.toml` entries citing them.
- **`scripts/release.py`**: `marketplace_problems` refuses a `sha`; `plugin_tree_count` runs
  `manifest --json` and reads `files` (`_files_counted`, one `_said`); `PLUGIN_URL =
  "https://github.com/stayfixed/stayfixed-plugin.git"`; lines 74–78 and 302, and
  `mutations/tooling.toml` near line 1564, say "pinned to the release's tag". The tag tests
  (`tests/scripts/test_release.py` around lines 692–836) expect `[]` or exact lists; the entry's
  shape is a param `id="a-sha"` of `test_an_entry_naming_another_repository_or_no_ref_is_refused`.
  `tests/test_manifests.py` lines 45–49 assert the entry's `source` equals a dict with no `sha`.
  `.claude-plugin/marketplace.json` writes `source` on one line, `"ref": "v0.2.0"`.
- **The frame.** `stayfixed.cli.run` exits `2` on `Refusal`, `1` on `Failure`, `2` on any other
  exception; under `--json` the `Result`'s data is printed at the object's top level beside
  `summary`.
- **Two ways git meets the owner's configuration.** `gitenv.git_run` hands git `PATH`, `HOME`,
  `LANG`, `LC_ALL`, `SYSTEMROOT` only, so it reads `HOME`'s `.gitconfig` (global
  `init.defaultObjectFormat`, `core.autocrlf`, `core.hooksPath`, `url.*.insteadOf`) and never
  `GIT_CONFIG_*`. `Runner.launch(argv, cwd)` takes no environment and passes `os.environ` minus
  git's location variables, so `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n` reach a network git and
  redirect `ls-remote` (measured by the plan review). `src/stayfixed/runner.py` is runtime and is
  not changed here.
- **Measured 2026-10-11 on git 2.54.0:**
  - `git init --bare --template=` under `HOME` holding `init.defaultObjectFormat = sha256` makes a
    sha256 repository; `--object-format=sha1` overrides it.
  - `git --git-dir=<an empty directory> hash-object -w --stdin` fails: "not a git repository", exit 128.
  - `git hash-object -t commit -w --stdin` writes a commit naming a parent the repository lacks,
    the same id twice; it refuses a malformed parent (39 or 64 characters, `1`) as `badParentSha1`
    but accepts 40 uppercase hex characters; it refuses a zero-padded date, a missing committer or a
    bad timezone itself, so `fsck --strict` adds nothing over it without `--literally`.
  - `git archive` applies `export-ignore` from the archived tree and `core.autocrlf=true` (`x\n`
    becomes `x\r\n`): it is not a read of the commit's bytes.
  - `hash-object --stdin-paths` in a bare repository converts `a\r\n` under `core.autocrlf =
    input`; `--no-filters` keeps it. `git fast-import` keeps `a\r\n` (plan review).
  - A `refs/replace/` entry on an annotated tag object moves what `^{commit}` peels to.
- **Python.** `python3 -c CODE A B` sees `sys.argv == ['-c', 'A', 'B']`. The venv's
  `stayfixed.pth` is a plain path line, so a path inserted at the head of `sys.path` wins over it
  (plan review: inserted resolves the extracted copy, appended the checkout's). Python 3.11.0 has
  no `tarfile` extraction `filter=`.
- **gh 2.101.0:** `gh attestation verify --cert-identity` matches the certificate's
  SubjectAlternativeName exactly; `gh auth status --hostname H --active`, `gh api --hostname H` and
  `gh attestation verify --hostname H` exist. The SAN's form for a tag push is a pre-flight
  measurement (section 6).
- **Claude Code.** 2.1.296 and 2.1.261: a `url` source with `sha` beside `ref` installs the pinned
  commit even when the tag moved. 2.1.296: `claude plugin validate --strict` passes a marketplace
  whose entry carries `"sha": "0"*40` (measured 2026-10-11); 2.1.261's answer is pre-flight.
- **GitHub Actions.** The `v0.1.0` release run (an annotated tag, object `eb1c39a`) recorded
  `headSha` `8256ee8`, the peeled commit, so `GITHUB_SHA` on a tag push is the commit.
  `release.yml` `build` checks out one commit, runs `release.py check --tag`, the suite with
  `id-token: write`, `uv build`, and attests `dist/*` and the plugin manifest; `publish` and
  `github-release` (`environment: pypi`) need `[build, environment-gate]`, and `github-release`
  checks out with the default persisted token under `contents: write`. `smoke.yml`
  `installed-plugin` builds its plugin repository with porcelain and writes the entry without `sha`.
- **Tests.** "A repository holding the nine paths" is built in `tests/scripts/test_plugin_tree.py`,
  `tests/test_payload.py` (which imports from another test module and keeps
  `SYMLINK_MODE`/`GITLINK_MODE` branches with `test_a_symlink_is_a_finding` and
  `test_a_submodule_is_a_finding`, unreachable through `members`) and
  `tests/scripts/test_release.py`. `tests.gitfixture.git` is the sealed runner
  (`GIT_CONFIG_GLOBAL=/dev/null`, identity from the environment); `tests/conftest.py`'s per-test
  `HOME` holds no `[user]`. `tests/test_check_workflow.py`'s `_job()` takes no argument and asserts
  `check.yml`'s only job; `_steps_of` (10 call sites) and `_lines` (joins `\` continuations) sit
  beside `_steps` and `_commands` (does not join); `needs_smoke_workflow` beside three inline
  `skipif` copies. `tests/test_fixtures.py` `_RELEASE_BLOCK` pins `RELEASING.md` step 1's first
  bash block; `tests/test_documents.py` pins step 5's "set both to the new version".
- **Release history.** Releases are cut on `main` and come back to `dev` through a
  `chore/after-release-X` branch (`95682f9`); `RELEASING.md` does not say so.

## Global Constraints

- **Runtime is untouched.** Nothing under `src/stayfixed/`, `hooks/`, `scripts/stayfixed`,
  `skills/` or `agents/` changes, so `hooks/hashes.json` does not either. A task that finds it must
  stops and reports.
- **No script imports another.** `scripts/release.py` runs `plugin_tree.py` as
  `[sys.executable, str(Path(__file__).with_name("plugin_tree.py")), …]`; `scripts/publish_plugin.py`
  runs the copy it read out of the tag (Task 4). Only tests import `plugin_tree`, through
  `tests/scriptload.py`. Constants the scripts must agree on (the plugin repository's names, the
  40-hex check) are copies held equal by a test (Task 6).
- **The plugin commit's bytes are fixed by this plan** (Task 2, `commit_text`), and the plugin
  repository is SHA-1, forced (`--object-format=sha1`), never taken from the owner's configuration:
  a `sha` is 40 lowercase hex characters.
- **Read from objects, never from the disk or a filter;** every git that reads the source runs
  with `plugin_tree.GIT_OPTIONS`. No `git archive`, no rendered file is hashed.
- **Nothing here writes to a remote.** `publish_plugin.py --yes` and `release.py pin` run in tests
  and tasks only against bare repositories under `tmp_path` or the scratchpad; tests never run `gh`,
  `claude`, `codex`, `pip` or `pre-commit` and never reach the network. A test that rewrites the
  default remote with `insteadOf` sets `GIT_SSH_COMMAND=false`.
- **Test repositories are built with the sealed `tests.gitfixture.git`;** only the code under test
  reads `HOME`'s `.gitconfig`, which a test writes when it means the owner's configuration.
- **Every new assertion ships with the mutation that reddens it, or a sentence saying why none
  exists** (`CONTRIBUTING.md`, "Tests"), in the group file its path routes to (`scripts/*.py` and
  workflows → `mutations/tooling.toml`; the payload test, the marketplace →
  `mutations/repository.toml`). A named mutation is an expectation until a run watched it. An
  expectation is never read from the subject: ids, manifests and commit texts are spelled
  literally, or computed by git, in the tests that pin them.
- **A removed or renamed test takes its mutation entries and every comment citing it along in the
  same commit;** an entry whose behaviour still exists is re-pointed, not deleted. "No test reddens
  on this" bookkeeping lives in `mutations/*.toml`, not in product code.
- **Every value that reaches a workflow shell arrives through `env:`**, and workflow edits stay in
  `tests.workflow_yaml`'s subset.
- **Neutral text.** No project outside this repository, no home directory or login, no private
  repository; commit ids in text are 7 or 40 characters; no plan vocabulary in tracked files
  outside `docs/plans/` (`tests/test_public_anchors.py`). Characters such as U+2028 are written in
  tests as escapes, never literally.
- **User-visible changes carry a towncrier fragment**; conventional commit subjects; no attribution
  trailer.

## Rulings

The controller's, where the owner's decisions leave a choice; the owner may overturn any at review.
Cost if wrong in brackets.

1. **The parent is read from history, not recorded.** The plugin commit of source commit `R` has as
   its parent the `sha` the marketplace entry pins at `R^1`, or none when `R^1` pins none (the first,
   `0.3.0`). `release.py pin` refuses unless the plugin repository's `main` is that parent, before
   any tag is pushed; `RELEASING.md` says how a release returns to `dev` so the next `R^1` pins it.
   [A release commit cut on the wrong base is caught by `pin`; an edit past `pin` is caught by the
   publisher after the tags, spending the version.]
2. **Fixed identity:** author and committer `stayfixed <release@stayfixed.invalid>`, date `0 +0000`;
   message `stayfixed X.Y.Z`, a blank line, `The plugin tree of stayfixed/stayfixed at vX.Y.Z.`
   [GitHub shows the plugin repository's commits dated 1970.]
3. **The objects are written by `plugin_tree.py`,** in a section of its own, because a separate
   script would have to receive the tree through a subprocess or the disk under "no script imports
   another"; `plugin_tree.py` grows from 298 to about 500 lines. Its marketplace reader reads the
   `sha` and nothing else.
4. **Blobs are written from memory by `git fast-import`,** not hashed from a render: a render
   collides two members that differ only in case on macOS's filesystem, and a hashed path invites
   the owner's filters.
5. **`main` moves only by fast-forward.** A tag whose commit's parent is not the remote `main` is
   refused (exit `1`); a patch release of an older line is not supported.
6. **The tag's code is read out of its objects** (`ls-tree -r -z`, `cat-file --batch`, regular files
   only) and run as `python -I -c <boot>`: `git archive` applies attributes and line endings, and
   `Runner.launch` cannot set `PYTHONPATH`; `-I` also keeps the owner's `PYTHONPATH` and user site
   out. Before it runs, the local tag's commit is compared with GitHub's `stayfixed/stayfixed` tag
   through `gh api`; the tag's code then runs with the owner's environment, the same trust the old
   design gave the checkout, and `--source-digest` binds the same commit afterwards.
7. **GitHub's API decides the remote's state on the default remote.** `main` and the tag are read
   through `gh api --hostname github.com` before anything is classified; `ls-remote` disagreeing
   with it is exit `2` naming a redirect (`url.*.insteadOf`, `GIT_CONFIG_*`); after a push the tag
   is read back the same way. Another `--remote` (tests, rehearsals) is classified from `ls-remote`
   alone, and the summary says so. Scrubbing the environment was rejected: it drops the SSH agent
   the push needs.
8. **The exit classes.** `1` (reject the `pypi` approval) only for a fact of the release that no
   re-run changes: the tag's pin is not the commit its tree makes; the tag's `plugin.json` names
   another version; GitHub holds another commit under the tag; GitHub's `main` is not the commit's
   parent; an attestation of this manifest exists but does not verify against this workflow, tag
   and commit; the built commit reads back as another tree. Everything else is `2`, including no
   attestation found yet (the summary says: once `build` and `attest` are green, reject), a
   transport or Sigstore failure, and a refusal of the tag's own `plugin_tree.py`: CI ran the same
   code on the same commit green, so a local cause is the likely one. [A deterministic defect in
   the tag's code exits `2` and is found again on the next run.]
9. **One `attest` job attests both `dist/*` and the plugin manifest,** with no suite and no `uv`, so
   `build` loses `id-token: write`.
10. **`plugin_tree.py commit --require-pin`** exits `1` when the source commit's pin is not the
    commit; the publisher and the `attest` job read the exit. `check --tag` compares the printed ids
    itself, because its finding names both and the count.
11. **The gate on the plugin is the first step of each gated job,** not a gated job of its own,
    which would ask for a second approval.

## Review Focus

1. **A release commit cut on the wrong base.** After a stopped release, the next release commit is
   cut on `main` (the plugin was not pushed) or on the spent release commit (it was); a dev→main
   merge may also drop the `sha`. Cut wrong, its parent is not GitHub's `main`: `pin` refuses
   before the tags (Task 3), the publisher after them (Task 4).
2. **The owner's machine shapes the answer.** `init.defaultObjectFormat`, `core.autocrlf`, a
   global hooks path, `url.*.insteadOf`, `GIT_CONFIG_*`, a second `gh` host: none may change the id
   computed, the code run, or the exit class (Tasks 2, 4, 5).
3. **The checkout's code differs from the tag's.** The publisher builds with the tag's copy and the
   tag's copy imports the tag's `stayfixed` (Task 4).
4. **A re-run after a success, a half-done run, a moved tag.** "Already published" is GitHub's tag
   peeling to the pinned id; another commit under it is exit `1`; the push is atomic (Task 4).
5. **A shallow clone.** CI checks out one commit by default and `R^1` is not in it: the reader
   refuses naming `fetch-depth: 2` instead of reading the parent as none (Task 2; Task 6 sets it).

## Execution contract

Every seat's brief carries the section that applies to it, copied, a fix round and a post-PR
dispatch included.

**1. Final review.** Three parallel read-only seats — **correctness**; **architecture** (one
implementation of the commit, no script importing another, the tag's code and not the checkout's,
the simplifications of Tasks 1, 3 and 4 taken or ruled on); **security** (what the pin binds, the
parent rule, the exact certificate identity, the API as the remote's anchor, the exit classes,
`env:` for every workflow value, the `attest` job's permissions and credentials) — and a
**lifecycle** seat that walks section 2.

**2. Lifecycle matrix.** Checked at pre-flight like a task; a cell names the test covering it, or
"—".

| Command \ change | re-run, nothing changed | after a stopped release | a malformed or missing input | killed or failing part-way |
|---|---|---|---|---|
| `plugin_tree.py commit` (Task 2) | `test_the_plugin_commit_is_the_same_on_every_run` | `test_the_parent_is_the_sha_the_first_parent_pins` | `test_a_malformed_pinned_sha_is_refused`, `test_a_source_whose_first_parent_is_not_in_the_clone_is_refused` | `test_a_half_made_git_dir_is_refused_and_an_empty_one_is_made` |
| `release.py pin` (Task 3) | `test_pin_twice_writes_the_same_file` | `test_pin_refuses_when_the_plugin_main_is_not_the_parent` | `test_pin_refuses_an_unreachable_remote` | — (one write, after every check) |
| `release.py check --tag` (Task 3) | `test_a_tag_whose_pin_is_the_plugin_commit_passes` (run twice) | — | `test_a_tag_whose_pin_is_not_the_plugin_commit_is_a_finding` | — |
| `publish_plugin.py` (Tasks 4–5) | `test_a_second_publish_of_the_same_tag_pushes_nothing` | `test_a_main_that_is_not_the_parent_is_rejected` | `test_a_tag_without_the_plugin_tree_script_is_refused` | `test_a_rejected_push_moves_no_ref`, `test_a_main_that_moves_between_list_and_fetch_is_refused` |
| CI `attest`, gated steps, smoke (Task 6) | — | — (CI is a function of the tag's commit, and `fetch-depth: 2` holds its first parent) | `test_the_gated_step_compares_the_peeled_id` | `RELEASING.md` step 7 |

The lifecycle seat resolves every name here against the branch; a task that renames a test renames
its cell in the same commit.

**3. Parallelism map.** One worktree, waves in order. Read-only seats beside each other and the
next implementer. One mutation oracle at a time per host.

**4. Templates.** An implementer's brief carries these lines, copied:

- A mismatch between this plan and the tree beats a guess: stop, quote both, report.
- Paste the output of every verification command into the report.
- Focused tests while iterating; one full run (`uv run pytest -n auto --cov --cov-fail-under=92`)
  at the end of the wave; also `uv run -p 3.11 pytest -n auto -q tests/scripts` once.
- A mutation this plan names is an expectation: apply it, run the named test, restore by
  re-applying the original text, report what reddened and why; if it does not redden its target
  alone, design one that does and say so.
- Line numbers are as of `9968c4b`; locate by the quoted text.
- Static checks: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
- Do not spawn subagents. Do not run `git restore`, `git checkout -- <path>`, `git stash`,
  `git reset --hard` or `git clean`. Never run `gh` or `claude`; never run `publish_plugin.py
  --yes` or `release.py pin` against anything but a repository under `tmp_path` or your scratchpad.
- The oracle proves `HEAD`: commit, then `uv run python scripts/mutation_oracle.py <filter>`.

A fix brief enumerates the sibling instances of the defect class it fixes and reports the neighbour
probes it ran. A security ruling names the minimal preconditions, the anchor it trusts and where
that came from, and one legitimate user it must not refuse.

**5. Verification.** The controller re-verifies only heads it pushes, and re-derives the pull
request body from the branch before every push:

```bash
uv run pytest -n auto --cov --cov-fail-under=92
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/mutation_oracle.py
uv run python scripts/release.py check
uv run stayfixed plan check docs/plans/2026-10-11-plugin-commit-pin.md
```

**6. Pre-flight measurements** (controller, before Wave A; recorded in Findings from persisted logs).
A measurement that contradicts the plan stops dispatch until the plan is amended.

- [x] **The certificate identity.** With the owner's yes, against the `v0.2.0` Release's wheel
  (downloaded again only with the owner's yes): `gh attestation verify <wheel> --hostname
  github.com --repo stayfixed/stayfixed --cert-identity
  https://github.com/stayfixed/stayfixed/.github/workflows/release.yml@refs/tags/v0.2.0
  --source-ref refs/tags/v0.2.0 --source-digest efd4b6d6143bdcc56d58389152fa024f12991125
  --deny-self-hosted-runners` exits `0`; with the identity changed to the same URL without `@…`,
  to `…@refs/tags/v0.2`, and to `…@refs/tags/v0.1.1`, each exits `1`. Task 5 writes the identity
  in the form that passed.
- [x] **The attestation API's answers** (same yes): `gh api --hostname github.com
  repos/stayfixed/stayfixed/attestations/sha256:<the wheel's sha256>` answers `200`, and for a
  digest no release attested, `404`. Task 5 classifies on these.
- [x] **`sha` on the pinned CLI:** `npx @anthropic-ai/claude-code@2.1.261 plugin validate --strict`
  on a copy of `.claude-plugin/marketplace.json` whose entry carries `"sha": "0"*40` exits `0`.
  Task 6 validates that form in CI.

## Waves

| Wave | Tasks | Mode | Size (plan lines) |
|---|---|---|---|
| 0 | — | this file committed first on `wp/plugin-commit-pin`; pre-flight (section 6) | — |
| A | 1–2 | dispatched | ~230 |
| B | 3 | dispatched | ~90 |
| C | 4 | dispatched; most of `test_publish_plugin.py` is rewritten | ~170 |
| D | 5 | dispatched | ~50 |
| E | 6 | dispatched; verified by a push to GitHub | ~90 |
| F | 7 | dispatched | ~60 |
| G | 8 | controller-run, real `claude`, read-only `gh` | ~40 |

```text
Wave 0 ──> A ──> B ──> C ──> D ──> E ──> F ──> G ──[PR]
```

- **Task 1 → Task 2:** `plugin_commit` reads through `read()`/`peel()`; its tests build sources
  with `tests/plugintree.py`.
- **Task 2 → Task 3:** `check --tag` and `pin` run `plugin_tree.py commit --json`.
- **Task 2 → Task 4:** the publisher runs the tag's `plugin_tree.py commit --require-pin` and
  `manifest --exact`; its fixture tags a source holding this branch's `plugin_tree.py` and
  `src/stayfixed`.
- **Task 4 → Task 5:** Task 5 replaces `_verify`'s flags and classification and adds the
  post-push read-back to Task 4's flow.
- **Task 2 → Task 6:** the `attest` job and the smoke run `commit`.
- **Tasks 3–6 → Task 7:** the documents restate them. **Tasks 4–6 → Task 8.**

B, C and D import nothing from each other and are serialised because each writes
`mutations/tooling.toml`; C and D are separate waves for size: C rewrites the publisher's flow and
most of an 806-line test file, D reads the attestation contract.

## File structure

| Path | Task | Responsibility |
|---|---|---|
| `tests/plugintree.py` (create) | 1, 4 | the shared builders: a source holding the nine paths; a tagged source holding a working `plugin_tree.py` |
| `scripts/plugin_tree.py` | 1, 2 | `peel`, `read`, `is_plugin_path`, wider `_control`; `PluginCommit`, `commit_text`, `pinned_sha`, `plugin_commit`; CLI `commit` |
| `tests/scripts/test_plugin_tree.py`, `tests/test_payload.py` | 1, 2 | the reader's and the commit's behaviour; the payload walk without dead branches |
| `scripts/release.py`, `tests/scripts/test_release.py` | 3 | `sha` in the entry's shape; `check --tag` against the plugin commit; `pin` |
| `.claude-plugin/marketplace.json`, `tests/test_manifests.py` | 3 | the entry in the format `pin` writes; an optional `sha` |
| `scripts/publish_plugin.py`, `tests/scripts/test_publish_plugin.py` | 4, 5 | the tag's code, the API's state, ids, typed exits; the signer, `gh`, the read-back |
| `.github/workflows/release.yml`, `smoke.yml`, `ci.yml`, `tests/test_check_workflow.py`, `tests/test_fixtures.py` | 6 | the `attest` job, the gated step, the smoke's `sha`, consolidated helpers, one repository spelled equal |
| `RELEASING.md`, `CONTRIBUTING.md`, `scripts/mutation_oracle.py`, `tests/scripts/test_mutation_oracle.py`, `changelog.d/+plugin-repository.change.md` | 7 | the release with a pin and its return to `dev`; the open question recorded once |
| this file, Findings | 0, 8 | the measurements |

---

## Wave A — Tasks 1–2

### Task 1: One resolution, one sort, a wider control set, and one set of test builders

**Files:**
- Modify: `scripts/plugin_tree.py`
- Create: `tests/plugintree.py`
- Modify: `tests/scripts/test_plugin_tree.py`, `tests/test_payload.py`, `tests/scripts/test_release.py`
- Modify: `mutations/tooling.toml`, `mutations/repository.toml`

**Interfaces:**
- Produces (`scripts/plugin_tree.py`):

```python
OBJECT_NAME = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
def peel(root: Path, rev: str, kind: str) -> str   # kind in {"commit", "tree"}; under GIT_OPTIONS
def is_plugin_path(path: str) -> bool               # under some PLUGIN_PATHS entry (was _under)

@dataclass(frozen=True)
class Tree:
    commit: str
    members: tuple[Member, ...]    # sorted by path

def read(root: Path, rev: str, *, exact: bool = False) -> Tree   # resolves rev once
def members(root: Path, rev: str, *, exact: bool = False) -> list[Member]  # list(read(...).members)
def manifest(entries: Iterable[Member]) -> str   # writes in the order given; no second sort
```

- Produces (`tests/plugintree.py`), every git through `tests.gitfixture.git`: `PLUGIN_FILES:
  dict[str, tuple[bytes, str]]` (one file under each of the nine paths, both modes, spelled
  literally); `write(root, files)`; `commit(root, message="a commit") -> str`;
  `plugin_source(tmp_path, files=None) -> Path` (an initialised repository with `files or
  PLUGIN_FILES` committed).

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_plugin_tree.py`:
  - `test_peel_names_a_sha256_repository_s_commit`: a repository made with `git init
    --object-format=sha256` and one commit; `peel(root, "HEAD", "commit")` returns its 64-character
    id (fails today with `AttributeError`).
  - `test_peel_refuses_an_answer_that_is_not_an_object_name`: `plugin_tree.git_run` monkeypatched
    to answer `(0, "not-a-sha\n")`; `Refusal` naming the rev.
  - `test_a_replaced_annotated_tag_peels_to_its_own_commit`: two annotated tags, `git replace -f
    <tag1 object> <tag2 object>`; `peel(root, "refs/tags/v1", "commit")` is `v1`'s commit.
  - `test_read_resolves_the_rev_once`: a wrapping `git_run` spy counts calls whose argv holds
    `rev-parse` anywhere (`GIT_OPTIONS` come first); `run_manifest` and `run_render` make one each.
  - `test_a_c1_or_line_separator_in_a_path_is_refused`: parametrised over `"\x7f"`, `"\x85"`,
    `"\x9b"`, and the escapes for U+2028 and U+2029, inside a `skills/` name; `Refusal` "holds a
    control character".
  - `test_render_without_a_manifest_file_writes_only_the_tree`.
  - `test_is_plugin_path`: `hooks/x` yes, `hooksx/y` no, `README.md` yes.
  - `test_the_manifest_is_one_line_per_member_in_order` is rewritten: sorted input, the lines in
    that order (the sort now lives in `members` alone).

- [ ] **Step 2: Run them; each fails for its reason** (`uv run pytest tests/scripts/test_plugin_tree.py -q`).

- [ ] **Step 3: Implement.** `peel` is the one `rev-parse --verify --end-of-options <rev>^{<kind>}`
  site and checks `OBJECT_NAME.fullmatch`; `commit()` goes. `read` resolves once; `run_manifest` and
  `run_render` call `read` only. `_control` refuses `ord < 0x20`, `0x7F`, `0x80`–`0x9F`, `0x2028`,
  `0x2029`. `render`'s `--manifest-file` becomes optional, still refused inside `--out`. `manifest`
  drops its sort; `operator.attrgetter("path")` replaces `_by_path`. The docstring paragraph "The
  order needs no mutation" moves to a comment beside the plugin-tree entries in
  `mutations/tooling.toml`.

- [ ] **Step 4: Move the builders** into `tests/plugintree.py` from the three test files;
  `tests/test_payload.py` stops importing from another test module. In `tests/test_payload.py`,
  delete `payload_findings`' `SYMLINK_MODE`/`GITLINK_MODE` branches, the `REGULAR_MODES` skip they
  leave dead, `test_a_symlink_is_a_finding`, `test_a_submodule_is_a_finding`, and the docstring
  keeping them "for the tree's other readers"; inline `count_finding` into its one caller. Their
  mutation entries go in this commit, or are re-pointed at `members`' refusal tests where those
  carry the behaviour.

- [ ] **Step 5: Run** `uv run pytest -n auto -q tests/scripts tests/test_payload.py tests/test_manifests.py`; PASS.

- [ ] **Step 6: Mutations** (`mutations/tooling.toml`): `OBJECT_NAME` without its 64-character
  alternative (expected to redden `test_peel_names_a_sha256_repository_s_commit`); `peel` without
  the `OBJECT_NAME` check (expected: `test_peel_refuses_an_answer_that_is_not_an_object_name`);
  `run_manifest` peeling before `read` (expected: `test_read_resolves_the_rev_once`); `_control`
  without the C1 range, and without `0x2028`/`0x2029` (two entries). The new replace-ref test is
  added to the `reddens` of the existing entry "the plugin tree reads an object through a replace
  ref". Commit, run the oracle on `plugin_tree`.

- [ ] **Step 7: Commit** — `refactor(plugin-tree): resolve once, peel in one place, refuse C1 and line separators; share the test builders`.

### Task 2: The plugin commit, a pure function of the source commit

**Files:**
- Modify: `scripts/plugin_tree.py`, `tests/scripts/test_plugin_tree.py`, `mutations/tooling.toml`

**Interfaces:**
- Consumes: `read`, `peel`, `GIT_OPTIONS` (Task 1).
- Produces:

```python
SOURCE_REPOSITORY = "stayfixed/stayfixed"
MARKETPLACE = ".claude-plugin/marketplace.json"
PACKAGE = "stayfixed"
IDENTITY = "stayfixed <release@stayfixed.invalid> 0 +0000"
SHA1 = re.compile(r"[0-9a-f]{40}")
NO_HOOKS = ("-c", "core.hooksPath=/dev/null")

@dataclass(frozen=True)
class PluginCommit:
    rev: str              # the source commit
    version: str          # .claude-plugin/plugin.json's version at rev
    files: int
    tree: str
    parent: str | None    # the sha the marketplace pins at rev^1, or None
    commit: str
    pinned: str | None    # the sha the marketplace pins at rev

def pinned_sha(root: Path, rev: str) -> str | None
def commit_text(tree: str, parent: str | None, version: str) -> str
def plugin_commit(root: Path, rev: str, git_dir: Path, *, root_commit: bool = False) -> PluginCommit
```

CLI: `plugin_tree.py commit --root DIR --rev REV --git-dir DIR [--manifest-file FILE]
[--no-parent] [--require-pin]`; `Result.data` is `{"format": FORMAT, **asdict(PluginCommit)}`.
Under `--require-pin`, a `pinned` other than `commit` raises `Failure` (exit `1`) naming both,
after the objects and the manifest file are written.

`commit_text`, exactly (the parent line only when `parent` is not `None`):

```text
tree <tree>
parent <parent>
author stayfixed <release@stayfixed.invalid> 0 +0000
committer stayfixed <release@stayfixed.invalid> 0 +0000

stayfixed <version>

The plugin tree of stayfixed/stayfixed at v<version>.
```

Rules `plugin_commit` holds, in a section of the module headed for the commit (Ruling 3):
- **`pinned_sha(root, rev)`** reads `<rev>:.claude-plugin/marketplace.json` under `GIT_OPTIONS`,
  agreeing with `release.py`'s reading: no file → `None`; exactly one entry named `stayfixed`
  whose `source` is an object, else `Refusal`; no `sha` in it → `None`; a `sha` not matching `SHA1`,
  or JSON that does not parse → `Refusal` naming the rev and the marketplace.
- **The parent:** `None` under `root_commit`; else `cat-file commit <rev>`: no `parent` line →
  `None`; a first parent the repository does not hold (`cat-file -e` fails) → `Refusal` "the commit
  before <rev> is not in this clone; fetch it (fetch-depth: 2)"; else `pinned_sha(root, <first
  parent>)`.
- **The version** is `.claude-plugin/plugin.json`'s `version` among the members; absent or not a
  string → `Refusal`.
- **The git dir:** absent, or an empty directory → `git init --bare --quiet --template=
  --object-format=sha1` with `NO_HOOKS`; otherwise it must answer `rev-parse
  --is-bare-repository` `true` and `--show-object-format` `sha1`, else `Refusal`. Every git in it
  runs `git --git-dir=<git_dir> *NO_HOOKS …` through `git_run`.
- **The objects:** blobs by one `git fast-import --quiet --export-marks=<file>` fed `blob`, `mark
  :<n>`, `data <len>` records of each member's `content` (mark → id from the marks file); trees by
  `mktree -z` per directory, deepest first, `040000` for a subtree (the publisher's `_build`,
  moved); the commit by `hash-object -t commit -w --stdin` of `commit_text`. A `-1` from `git_run`
  is refused with `gitenv.NO_ANSWER`'s words, never a subset.
- **The manifest file**, when asked, is `manifest(tree.members)` as UTF-8, written last.

- [ ] **Step 1: Write the failing tests** (sources built with `tests/plugintree.py`; the owner's
  configuration, where a test means it, written into `HOME`'s `.gitconfig`):
  - `test_commit_text_is_exactly_the_documented_bytes`: `commit_text("a"*40, "b"*40, "0.3.0")` and
    `commit_text("a"*40, None, "0.3.0")` against the literal texts above.
  - `test_the_plugin_commit_is_what_git_computes`: build from `plugin_source`; `git cat-file commit
    <commit>` in `git_dir` equals the commit text spelled literally in the test with the tree id
    from `git rev-parse <commit>^{tree}`; `git ls-tree -r` lists exactly `PLUGIN_FILES` with their
    modes.
  - `test_the_plugin_commit_is_the_same_on_every_run`: two calls into two fresh git dirs from two
    clones: equal `commit` and `tree`.
  - `test_the_parent_is_the_sha_the_first_parent_pins`: commit `A` pinning `"c"*40`, then `B` on it
    pinning `"d"*40`; `parent == "c"*40`, `pinned == "d"*40`, and the commit text names `"c"*40`.
  - `test_a_first_release_has_no_parent` and `test_no_parent_ignores_the_history`.
  - `test_a_source_whose_first_parent_is_not_in_the_clone_is_refused`: `git clone --depth 1
    file://…` of `B`; `Refusal` containing `fetch-depth: 2`.
  - `test_a_malformed_pinned_sha_is_refused`: the malformed pin at `rev` itself (where
    `hash-object` cannot refuse it first), parametrised `"C"*40`, `"c"*39`, `"c"*64`, `1`, and two
    entries named `stayfixed`; the message names the marketplace.
  - `test_the_owner_s_object_format_does_not_reach_the_git_dir`: `init.defaultObjectFormat =
    sha256` in `HOME`; `commit` is 40 characters and equals the run without the setting.
  - `test_the_owner_s_line_endings_do_not_change_the_blobs`: `core.autocrlf = input` in `HOME`; a
    `skills/` member committed (sealed) holding `a\r\nb\r\n`; its blob in `git_dir` holds those bytes.
  - `test_members_differing_only_in_case_are_both_written`: two `skills/` members named `A.md` and `a.md`; both
    in `git ls-tree -r`.
  - Moved from the publisher's tests (their entries re-pointed): `test_the_owners_init_template_does_not_reach_the_git_dir`,
    `test_the_owners_hooks_do_not_run_in_the_git_dir`,
    `test_an_explicit_safe_bare_repository_does_not_refuse_the_git_dir`,
    `test_a_commit_that_gave_no_answer_is_refused_in_no_answer_s_words`.
  - `test_a_half_made_git_dir_is_refused_and_an_empty_one_is_made`: an empty directory is
    initialised; a non-empty non-repository and a sha256 bare repository are refused.
  - `test_a_second_commit_into_the_same_git_dir_succeeds`.
  - `test_require_pin_exits_1_when_the_pin_is_another_commit` and the `commit --json` object's keys.

- [ ] **Step 2: Run; they fail** (`AttributeError: … plugin_commit`).

- [ ] **Step 3: Implement** by the rules above. The module docstring gains one paragraph: the commit
  the plugin repository holds is computed here, so the release commit can name it and anyone can
  recompute it.

- [ ] **Step 4: Run** `uv run pytest -n auto -q tests/scripts/test_plugin_tree.py`; PASS.

- [ ] **Step 5: Mutations:** the date `0 +0000` → `1 +0000` (expected to redden
  `test_commit_text_is_exactly_the_documented_bytes` and `test_the_plugin_commit_is_what_git_computes`);
  the parent read from `rev` instead of `rev^1` (expected:
  `test_the_parent_is_the_sha_the_first_parent_pins`); the missing first parent read as `None`
  (expected: the shallow-clone test); `--object-format=sha1` dropped (expected:
  `test_the_owner_s_object_format_does_not_reach_the_git_dir`); the `SHA1` check in `pinned_sha`
  dropped (expected: the `"C"*40` case); `--require-pin` comparing `parent`. No mutation for the
  autocrlf and case tests: `fast-import` applies no filter and writes no file, and the tests guard
  a return to hashing a render; the entry records that. Commit, run the oracle on `plugin_tree`.

- [ ] **Step 6: Commit** — `feat(plugin-tree): compute and write the plugin repository's commit as a function of the source commit`.

## Wave B — Task 3

### Task 3: `release.py`: the pin in the entry, checked at a tag, written by `pin`

**Files:**
- Modify: `scripts/release.py`, `tests/scripts/test_release.py`, `.claude-plugin/marketplace.json`,
  `tests/test_manifests.py`, `mutations/tooling.toml`, `mutations/repository.toml`

**Interfaces:**
- Consumes: `plugin_tree.py commit --root R --rev HEAD --git-dir D --json` (Task 2).
- Produces: `PLUGIN_PIN = "plugin pin"`; `plugin_commit_problems(root) -> list[str]` (replaces
  `plugin_tree_count`); `pin(root, *, remote, runner) -> str`; CLI `release.py pin [--remote URL]`
  (default `PLUGIN_URL`, read only).

- **The entry's shape** (`marketplace_problems`): `sha` optional; present, it matches
  `[0-9a-f]{40}`, else "pins sha …, which is no commit id". The "cannot know" refusal goes;
  `marketplace_problems` reuses `_the_plugin_entry`'s count.
- **`check --tag`** runs `commit` once, into `<tempfile.TemporaryDirectory()>/plugin.git`, and
  reports: over `PLUGIN_FILES_MAX` under `TREE_COUNT`; a `commit` that exited non-zero under
  `TREE_COUNT`, quoting its `summary` ("could not be read"); under `PLUGIN_PIN`, no `sha` ("… pins
  no sha; the plugin commit of this tree is <commit>: run `release.py pin`") or another `sha` ("…
  pins <pinned>; the plugin commit of this tree is <commit>"). Plain `check` runs nothing.
- **`pin`** runs `commit` at `HEAD`; lists the remote with `git ls-remote --end-of-options <remote>
  refs/heads/main` through the `Runner` and selects the line whose ref is exactly `refs/heads/main`;
  refuses (`2`) a failed `ls-remote`, and a `main` that is not the commit's `parent` — absent with a
  parent, present without one, or another id — naming both and the likely cause: the release commit
  cut on the wrong base, or a merge into `main` that dropped the marketplace's `sha`
  (`RELEASING.md` section 5); else writes `sha` into the entry and returns it. The file is rewritten
  as `json.dumps(data, indent=2, ensure_ascii=False) + "\n"`; this task commits
  `.claude-plugin/marketplace.json` in that format, so a later `pin` adds the `sha` line and a comma.
- **Leftover text:** `scripts/release.py` lines 74–78 and 302, and the `mutations/tooling.toml`
  entry near line 1564, stop saying "pinned to the release's tag" alone.

- [ ] **Step 1: Write the failing tests** (`tests/scripts/test_release.py`; builders from
  `tests/plugintree.py` plus a marketplace member):
  - `test_a_sha_beside_the_ref_is_accepted`; `test_a_sha_that_is_not_a_commit_id_is_refused`
    (`"C"*40`, `"c"*39`, `""`, `1`). The `id="a-sha"` param of
    `test_an_entry_naming_another_repository_or_no_ref_is_refused` goes, its mutation entries
    re-pointed here.
  - `test_a_tag_whose_pin_is_not_the_plugin_commit_is_a_finding`,
    `test_a_tag_without_a_pin_is_a_finding_naming_the_commit`, `test_a_tag_whose_pin_is_the_plugin_commit_passes`
    (the expected id computed by `git hash-object -t commit` of the literal commit text over the
    tree git computes for the plugin paths, not by `plugin_commit`).
  - The existing tag tests' fixtures write the right `sha` (computed the same way), so their
    expected lists stay as they are; the one reading `kinds["plugin tree count"]` keeps that kind.
  - `test_plain_check_does_not_compute_the_commit`.
  - `test_pin_writes_the_commit_into_the_entry`: empty bare remote, first parent pinning nothing;
    the entry's `source` becomes `{source, url, ref, sha}`.
  - `test_pin_refuses_when_the_plugin_main_is_not_the_parent`: parametrised (remote `main` absent,
    parent `"c"*40`), (remote `main` some commit, parent `None`), (both set, different); the file
    unchanged byte for byte.
  - `test_pin_reads_main_by_its_exact_name`: the remote also holds `refs/heads/x/refs/heads/main`
    at another commit; `pin` passes.
  - `test_pin_refuses_an_unreachable_remote`: parent `None` (so only the failure check can refuse);
    `Refusal` quoting git.
  - `test_pin_twice_writes_the_same_file`.
  - `tests/test_manifests.py`: the entry's `source` holds `source`, `url`, `ref`, and optionally a
    40-hex `sha`, nothing else (the release commit after `pin` passes the suite `release.yml` runs).

- [ ] **Step 2: Run; they fail.** **Step 3: Implement**; `TAG_HELP` and the module docstring say
  what `--tag` checks; `plugin_tree_count`, `_files_counted` go.

- [ ] **Step 4: Rewrite `.claude-plugin/marketplace.json`** in the `pin` format (no `sha`: `dev`
  pins none before `0.3.0`); `uv run python scripts/release.py check` prints "one version
  everywhere: 0.2.0".

- [ ] **Step 5: Run** `uv run pytest -n auto -q tests/scripts/test_release.py tests/test_manifests.py`; PASS.

- [ ] **Step 6: Mutations:** `check --tag` comparing `pinned` with `parent`; `pin` skipping the
  `main` comparison; `pin` writing before it (expected: the "unchanged" assertion); `pin` selecting
  `ls-remote`'s first line (expected: `test_pin_reads_main_by_its_exact_name`); the shape check
  accepting uppercase. Commit, run the oracle on `release`.

- [ ] **Step 7: Commit** — `feat(release): pin the plugin commit by sha, check it at a tag, and write it with pin`.

## Wave C — Task 4

### Task 4: The publisher runs the tag's code, reads GitHub's state, compares ids, and exits 1 or 2

**Files:**
- Modify: `scripts/publish_plugin.py`, `tests/scripts/test_publish_plugin.py`, `tests/plugintree.py`,
  `mutations/tooling.toml`

**Interfaces:**
- Consumes: the tag's `plugin_tree.py commit … --require-pin --json` and `manifest --exact …
  --manifest-file` (Task 2's CLI, data keys and exit codes).
- Produces:

```python
class Rejected(Failure):   # exit 1: a fact of this release no re-run changes (Ruling 8)
    ...

@dataclass(frozen=True)
class Published:
    tag: str
    files: int
    tree: str
    commit: str
    outcome: Literal["would-push", "pushed", "already"]
    confirmed: bool        # the remote's state was read through GitHub's API

def publish(root: Path, tag: str, *, remote: str, yes: bool, runner: Runner, scratch: Path) -> Published
```

- `tests/plugintree.py` gains `tool_source(tmp_path, *, plugin_tree: bytes | None = None,
  extra: dict[str, tuple[bytes, str]] | None = None) -> Path`: a repository holding
  `PLUGIN_FILES`, this branch's `scripts/plugin_tree.py` (or `plugin_tree`) and the working-tree
  bytes of every path `git ls-files src/stayfixed` lists (no `__pycache__`), plus `extra`; committed
  with the sealed git; its marketplace pinning the commit its tree makes (computed by git: the
  commit text over `git write-tree` of a temporary index holding the plugin paths, then amended in);
  tagged `v1.2.3` (annotated), `plugin.json` at `1.2.3`. The default variant is built once per
  session (`tmp_path_factory`) and cloned per test; a variant with `plugin_tree` or `extra` is built
  per test.

The flow, each step refusing before the next runs (exit class per Ruling 8):

1. `_tag_commit(root, tag) -> str`: `TAG_PATTERN`; `refs/tags/<tag>^{commit}` peeled with
   `--no-replace-objects`; the answer matches `[0-9a-f]{40}`. `2`.
2. `_source_anchor(runner, tag, sha)`: `gh api --hostname github.com
   repos/stayfixed/stayfixed/git/ref/tags/<tag>` (peeled through `git/tags/<id>` when its object is a
   tag) must name `sha`; else `2` ("your local <tag> is not GitHub's").
3. `_tool(root, sha, scratch) -> Path`: `ls-tree -r -z <sha> -- scripts/plugin_tree.py src/stayfixed`
   and one `cat-file --batch`, under `--no-replace-objects`; every row `100644` or `100755` (any
   other mode refused, not skipped); written under `scratch/tool` through `fsops.mkdirs_within` and
   `fsops.open_within`. No `scripts/plugin_tree.py` or no `src/stayfixed` at the tag → `2`
   ("<tag> predates the plugin repository").
4. `_run_tool(runner, tool, root, *args) -> tuple[int, dict]`: `[sys.executable, "-I", "-c", BOOT,
   str(tool / "src"), str(tool / "scripts" / "plugin_tree.py"), *args, "--json"]` with

   ```python
   BOOT = (
       "import runpy, sys; src = sys.argv[1]; sys.argv[:] = sys.argv[2:]; "
       "sys.path.insert(0, src); runpy.run_path(sys.argv[0], run_name='__main__')"
   )
   ```

   The printed object must carry `format == FORMAT`, `commit`/`tree` matching `[0-9a-f]{40}`,
   `parent`/`pinned` that or `null`, `files` an `int`; anything else is `2`. Its `summary` is quoted
   through `stayfixed.printed`'s escaping, not truncated.
5. `built = _run_tool(… "commit", "--root", root, "--rev", sha, "--git-dir", scratch/"plugin.git",
   "--manifest-file", scratch/"plugin-tree.txt", "--require-pin")`: exit `1` → `1`; other non-zero
   → `2`. `tag_for(built["version"])[0] != tag` → `1`.
6. `_verify` (Task 5 owns its flags and classification; here a non-zero answer is `1`).
7. Read-back: `_run_tool(… "manifest", "--exact", "--root", git_dir, "--rev", commit,
   "--manifest-file", scratch/"readback.txt")`; bytes ≠ `plugin-tree.txt` → `1`, with
   `_first_difference`.
8. `_remote_state`: `ls-remote` of `refs/heads/main`, `refs/tags/<tag>`, `refs/tags/<tag>^{}`,
   exact names; the tag's commit is the `^{}` line's id when present, else the tag line's (the
   publisher pushes a lightweight tag: one line). When `remote` is the default one (`PLUGIN_REMOTE`
   or `PLUGIN_URL`, as given), also `gh api --hostname github.com
   repos/stayfixed/stayfixed-plugin/git/ref/heads/main` and `…/git/ref/tags/<tag>` (peeled as in step
   2; `404`, or `409` for an empty repository, is "absent"; any other failure `2`); a disagreement
   with `ls-remote` is `2` naming a redirect; `confirmed=True`.
9. Tag present: equal to `commit` → `outcome="already"`, nothing fetched or pushed; else `1`.
10. Tag absent: `main` must equal `built["parent"]` (both absent counts as equal); else `1`. With a
    parent: fetch `+refs/heads/main:refs/stayfixed/main` (with `NO_HOOKS`, which the publisher keeps
    for every network git); the fetched ref must name the listed id, else `2` ("main moved while
    this ran; run again").
11. `yes`: `push --atomic --end-of-options <remote> <commit>:refs/heads/main
    <commit>:refs/tags/<tag>`; failure → `2` (atomic: nothing moved).

Removed: `PLUGIN_TREE`, `MANIFEST_FORMAT`, `FILE_MODES`, `_plugin_tree`, `_manifest_rows`,
`_already`, `_root_tree`, `_parent`, `_mktree`, `_build`, `_scratch_repository`, the identity
fixture and paragraph; "No test reddens on this" comments move to `mutations/tooling.toml`. The
`would-push` summary: "would push <files> files as tree <tree>, commit <commit>, to <remote>:
main and <tag>; run again with --yes to push", plus "(not confirmed through GitHub's API)" when
`confirmed` is false.

**The existing tests** (36):

| Test | Becomes |
|---|---|
| `test_a_verified_tree_is_pushed_with_its_tag_and_reads_back_whole` | rewritten: `test_the_commit_pushed_is_the_pinned_one` |
| `test_without_yes_the_remote_is_unchanged`, `test_the_tree_is_rendered_from_the_tag_and_not_the_disk`, `test_a_branch_named_like_the_tag_does_not_stand_in_for_it`, `test_a_second_publish_of_the_same_tag_pushes_nothing`, `test_the_previous_release_is_replaced_whole`, `test_a_replace_ref_does_not_stand_in_for_the_tags_version`, `test_a_replace_ref_on_the_tag_object_does_not_move_the_tags_commit`, `test_an_unknown_tag_is_refused_before_anything_runs`, `test_a_tag_that_is_not_a_plain_version_is_refused`, `test_a_listing_that_names_no_object_is_refused`, `test_a_rejected_push_moves_no_ref`, `test_a_main_that_moved_before_the_push_is_not_overwritten`, `test_the_publisher_pushes_to_the_repository_the_marketplace_fetches_from`, `test_the_cli_refuses_a_tag_that_is_not_a_plain_version`, `test_a_relative_remote_is_the_one_beside_the_owner_and_not_the_scratch_repository`, `test_a_url_an_scp_like_remote_or_an_absent_path_is_given_as_it_is` | kept, on the new fixture |
| `test_the_tree_a_dry_run_names_is_the_one_a_later_run_pushes` | kept, now the commit too |
| `test_the_cli_says_what_a_dry_run_would_push` | kept, the new wording |
| `test_a_tag_whose_version_is_another_is_refused` | kept, exit `1` |
| `test_the_owners_hooks_do_not_run_in_the_scratch_repository`, `test_an_explicit_safe_bare_repository_does_not_refuse_the_scratch_repository` | kept for the network git (a `pre-push` hook), and a Task 2 counterpart for the git dir |
| `test_the_commit_ignores_the_owners_line_ending_and_hook_configuration`, `test_the_owners_init_template_does_not_reach_the_scratch_repository`, `test_a_commit_tree_that_gave_no_answer_is_not_blamed_on_the_identity` | moved to Task 2 |
| `test_a_main_that_moved_before_the_fetch_is_refused_as_a_race` | replaced: `test_a_main_that_moves_between_list_and_fetch_is_refused` |
| `test_a_tag_on_the_remote_with_another_tree_is_refused` | replaced: `test_another_commit_under_the_tag_is_rejected` |
| `test_a_tag_on_the_remote_whose_main_is_elsewhere_is_refused` | replaced: `test_a_published_tag_with_main_moved_on_is_already_published` |
| `test_a_rendered_file_changed_after_the_attestation_is_refused_by_the_read_back` | rewritten: `plugin-tree.txt` altered after the `commit` call (a `Composite` hook); exit `1` |
| `test_a_manifest_in_another_format_is_not_read` | rewritten: a tool printing another `format`; exit `2` |
| `test_the_attestation_is_asked_for_this_workflow_this_tag_and_this_commit`, `test_a_refused_attestation_stops_before_anything_is_fetched` | replaced in Task 5 |
| `test_a_missing_git_identity_is_refused_before_anything_is_pushed`, `test_a_manifest_that_cannot_be_read_is_refused`, `test_a_remote_commit_holding_a_path_outside_the_plugin_is_not_already_published` | deleted with their entries: no identity is needed, no manifest is parsed, ids are compared |

- [ ] **Step 1: Write the failing tests** (`gh` answered by `Composite.gh`; every other program real):
  - `test_the_tag_s_own_plugin_tree_builds_the_commit`: a per-test `tool_source` whose
    `plugin_tree.py` gains a tenth path `commands`, with `extra` a file `a.md` under `commands`, the
    checkout's `PLUGIN_PATHS` unchanged. Without `yes` it succeeds, and `plugin-tree.txt` equals
    the manifest the test computes with git (`ls-tree -r` over the ten paths, sha256 of each
    `cat-file` blob), its line for that file also spelled literally. Under the mutation "run the
    checkout's copy" this test reddens at step 5 (the checkout's copy omits `commands`, so its
    commit is not the pin: exit `1`), not at the manifest comparison.
  - `test_the_tag_s_tool_imports_the_tag_s_stayfixed`: the tag's `plugin_tree.py` gains, after its
    `from __future__ import annotations`, a line writing `stayfixed.__file__` to the path in an
    environment variable the test sets; the path written is under `scratch / "tool"`.
  - `test_a_tag_without_the_plugin_tree_script_is_refused`: exit `2`, the summary says "predates".
  - `test_a_tool_file_that_is_not_regular_is_refused`: a symlink under the tag's `src/stayfixed`.
  - `test_a_local_tag_github_does_not_hold_is_refused`: `gh api` answers another id; exit `2`,
    nothing extracted.
  - `test_a_pin_other_than_the_commit_is_rejected`: the tag pins `"c"*40`; exit `1`, no
    `attestation` call.
  - `test_another_commit_under_the_tag_is_rejected` (lightweight and annotated remote tags) and
    `test_an_annotated_tag_peeling_to_the_pin_is_already_published`.
  - `test_a_published_tag_with_main_moved_on_is_already_published`.
  - `test_a_main_that_is_not_the_parent_is_rejected`: parametrised as Task 3's `pin` test; exit `1`.
  - `test_publishing_an_older_line_never_rewinds_main`: `v1.3.0` published, then a `v1.2.4` whose
    first parent pins nothing; exit `1`, remote `main` still `v1.3.0`'s.
  - `test_a_main_that_moves_between_list_and_fetch_is_refused`: without `yes`, the remote `main`
    equal to the parent; a `Composite` hook pushes a new commit to it after `ls-remote`; exit `2`
    with "main moved while this ran".
  - `test_the_api_decides_on_the_default_remote`: `PLUGIN_REMOTE` rewritten to a bare path by an
    `insteadOf` in `HOME`'s `.gitconfig`, `GIT_SSH_COMMAND=false`; `gh api` answering as the bare
    remote → `confirmed`; `gh api` answering the tag absent while the bare remote holds it → exit `2`
    naming a redirect, not `already`.
  - `test_another_remote_is_not_confirmed`: a bare path; no `gh api` call for the plugin repository.
  - `test_a_tool_answer_that_is_not_an_object_name_is_refused`: a tag's `plugin_tree.py` patched to
    print `"commit": "+main"`; exit `2`, no `push`.
  - `test_the_commit_pushed_is_the_pinned_one`: after `yes`, the remote's `main` and tag name
    `built["commit"]`, which equals the id the fixture pinned.
  - `test_every_rejection_exits_1_and_every_refusal_exits_2`: one parametrised table of the cases
    above through `main([...])` — the classification's one home.

- [ ] **Step 2: Run; they fail.** **Step 3: Implement** the flow; the module docstring is rewritten
  around the tag's own code, GitHub's API as the remote's anchor, ids compared, and the exit
  classes, and states the parent rule once.

- [ ] **Step 4: Run** `uv run pytest -n auto -q tests/scripts/test_publish_plugin.py`; PASS.

- [ ] **Step 5: Mutations:** `_run_tool` running the checkout's `plugin_tree.py` (expected:
  `test_the_tag_s_own_plugin_tree_builds_the_commit`, at step 5); `BOOT` appending instead of
  inserting (expected: `test_the_tag_s_tool_imports_the_tag_s_stayfixed`); `Rejected` → `Refusal`
  for the pin; the tag line compared where a `^{}` line exists (expected:
  `test_an_annotated_tag_peeling_to_the_pin_is_already_published`); the fetch check dropped
  (expected: `test_a_main_that_moves_between_list_and_fetch_is_refused`); the API comparison dropped
  (expected: `test_the_api_decides_on_the_default_remote`); the 40-hex check on the tool's
  `commit` dropped. Commit, run the oracle on `publish_plugin`.

- [ ] **Step 6: Commit** — `feat(publish-plugin): build with the tag's own code, decide from GitHub's state, compare ids, exit 1 to reject or 2 to retry`.

## Wave D — Task 5

### Task 5: What the publisher trusts: an exact signer, a logged-in gh, an attestation that exists, the tag read back

**Files:**
- Modify: `scripts/publish_plugin.py`, `tests/scripts/test_publish_plugin.py`, `mutations/tooling.toml`

**Interfaces:**
- Consumes: Task 4's flow; the identity form and the API's answers pre-flight measured.
- Produces: `CERT_IDENTITY = "https://github.com/stayfixed/stayfixed/.github/workflows/release.yml@refs/tags/{tag}"`
  (as measured); `SIGNER_WORKFLOW` goes.

- **Before `_verify`:** `gh auth status --hostname github.com --active`; non-zero → `2`.
- **`_verify`:** `gh attestation verify <manifest> --hostname github.com --repo stayfixed/stayfixed
  --cert-identity <CERT_IDENTITY> --source-ref refs/tags/<tag> --source-digest <sha>
  --deny-self-hosted-runners`. On a non-zero answer, `gh api --hostname github.com
  repos/stayfixed/stayfixed/attestations/sha256:<sha256 of plugin-tree.txt>`: `200` → `1` (an
  attestation exists and does not verify against this workflow, tag and commit); `404` → `2` ("no
  attestation of this manifest yet; once `build` and `attest` are green, reject the approval"); any
  other answer → `2`.
- **After a push to the default remote:** `gh api … git/ref/tags/<tag>` (peeled) must name `commit`;
  a `404` → `2` ("GitHub does not list <tag> yet; run again"); another id → `2` ("the push went
  elsewhere: a `url.*.insteadOf` or `GIT_CONFIG_*`; fix it and run again").

- [ ] **Step 1: Write the failing tests:** `test_the_attestation_is_asked_with_an_exact_identity`
  (the `gh attestation verify` argv, whole, literal); `test_a_gh_that_is_not_logged_in_is_refused_before_verify`
  (exit `2`, no `attestation` call); `test_a_verify_failure_is_classified_by_whether_an_attestation_exists`
  (`200` → `1`, `404` → `2`, `500` → `2`; `gh auth status` answers `0`, only `attestation verify`
  answers `1`); `test_the_pushed_tag_is_read_back_on_the_default_remote` (the Task 4 `insteadOf`
  set-up: the commit → `pushed`; `404` → `2` "run again"; another id → `2` "went elsewhere").

- [ ] **Step 2: Run; they fail.** **Step 3: Implement.** **Step 4: Run the file; PASS.**

- [ ] **Step 5: Mutations:** `--cert-identity` → `--signer-workflow` with the old value; `200` and
  `404` swapped; the post-push comparison dropped; `gh auth status` without `--hostname`
  (expected: the exact-argv test). Commit, run the oracle.

- [ ] **Step 6: Commit** — `fix(publish-plugin): verify an exact signer, require a logged-in gh, tell a missing attestation from a wrong one, read the pushed tag back`.

## Wave E — Task 6

### Task 6: The workflows attest, gate on and install the plugin commit

**Files:**
- Modify: `.github/workflows/release.yml`, `.github/workflows/smoke.yml`, `.github/workflows/ci.yml`,
  `tests/test_check_workflow.py`, `tests/test_fixtures.py`, `mutations/tooling.toml`

**Interfaces:**
- Consumes: `plugin_tree.py commit` and `render` (Tasks 1–2), `release.py check --tag` (Task 3),
  `PLUGIN_URL`, `PLUGIN_REMOTE` and the API path (Tasks 3–5).

- **`build`:** `actions/checkout` with `fetch-depth: 2` (`check --tag` reads `HEAD^1`'s pin);
  `permissions: contents: read` only; it no longer attests or renders.
- **`attest`** (new): `needs: build`; `permissions: {id-token: write, attestations: write,
  contents: read}`; checkout with `fetch-depth: 2` and `persist-credentials: false`; no `uv`, no
  suite: downloads `dist`; with `env: PYTHONPATH: src`, `python3 scripts/plugin_tree.py commit
  --root . --rev "$GITHUB_SHA" --git-dir "$RUNNER_TEMP/plugin.git" --manifest-file
  "$RUNNER_TEMP/plugin-tree.txt" --require-pin --json > "$RUNNER_TEMP/plugin-commit.json"`; reads
  `commit` with `python3 -c` and checks it against `^[0-9a-f]{40}$` before `$GITHUB_OUTPUT`;
  attests `dist/*` and `plugin-tree.txt` with the pinned `attest-build-provenance`; uploads
  `plugin-tree` with `if-no-files-found: error`. Output `commit`.
- **`publish` and `github-release`:** `needs: [build, environment-gate, attest]`; their first step,
  before any checkout or download, "The plugin repository holds this release's commit": `env: TAG:
  ${{ github.ref_name }}`, `PINNED: ${{ needs.attest.outputs.commit }}`; `git ls-remote
  https://github.com/stayfixed/stayfixed-plugin.git "refs/tags/$TAG" "refs/tags/$TAG^{}"`; the lines
  selected by exact ref name; the `^{}` line's id when present, else the tag line's, must equal
  `$PINNED`, else `::error::` naming `RELEASING.md` step 7 and exit 1. No credential.
- **`smoke.yml` `installed-plugin`:** the porcelain build becomes `uv run python
  scripts/plugin_tree.py commit --root . --rev HEAD --git-dir "$RUNNER_TEMP/plugin-repo.git"
  --no-parent --json` (`--no-parent`: a scratch repository holds no earlier plugin commit, and a
  parent it lacks would break the clone once `dev` pins a `sha`), then `git --git-dir=… update-ref`
  of `refs/heads/main` and `refs/tags/v$version` to the printed `commit`; the scratch entry is
  `{source: url, url: file://…/plugin-repo.git, ref: v$version, sha: $commit}`; the install is
  still held to a `render` of `HEAD`.
- **`ci.yml` `plugin`:** `render` without `--manifest-file`; validates `--strict` a scratch copy of
  the marketplace whose entry carries `sha: "0"*40`, beside the real file.
- **`tests/test_check_workflow.py`:** `_job` becomes `_job(workflow, name)` (the `check.yml`
  assertion moves to its own test); `_steps_of`'s call sites use it; one continuation reader (the
  one that joins `\`); `needs_smoke_workflow` moves to `tests/test_fixtures.py` beside
  `needs_ci_workflow` and replaces the three inline `skipif` copies.
- **One plugin repository:** `test_one_plugin_repository_everywhere` holds `release.py`'s
  `PLUGIN_URL`, `publish_plugin.py`'s `PLUGIN_REMOTE` and API paths, and the workflows' URL to one
  `owner/name` (Task 7 adds `RELEASING.md`).

- [ ] **Step 1: Write the failing tests:** `test_build_fetches_the_first_parent` (also on
  `attest`); `test_only_the_attest_job_can_attest` (`build` holds no `id-token`, `attest` runs no
  `pytest` and no `uv`, sets `persist-credentials: false`); `test_the_gated_jobs_refuse_until_the_plugin_tag_names_the_pin`
  (first step of both, `$PINNED` from `needs.attest.outputs.commit` through `env:`);
  `test_the_gated_step_compares_the_peeled_id` (its script under `bash` with a stub `git` on
  `PATH`: tag line and `^{}` line, `PINNED` the `^{}` id → 0, the tag line's → 1; tag line only,
  `PINNED` equal → 0; a decoy `refs/tags/x/refs/tags/$TAG` line equal to `PINNED` while the real
  line is not → 1); `test_the_smoke_installs_by_ref_and_sha` (the entry carries `sha` from the
  `commit` step and the step passes `--no-parent`); `test_one_plugin_repository_everywhere`; the
  existing smoke and release tests updated (`test_the_release_attests_the_plugin_tree_it_rendered_from_the_commit`
  now reads `attest`).

- [ ] **Step 2: Run; they fail.** **Step 3: Edit the workflows and helpers.** **Step 4:**
  `uv run pytest -n auto -q tests/test_check_workflow.py tests/test_fixtures.py tests/test_documents.py`; PASS.

- [ ] **Step 5: Mutations:** `fetch-depth: 2` removed from `build` (expected:
  `test_build_fetches_the_first_parent`); the gated step comparing the tag line when a `^{}` line
  exists, and selecting by tail (expected: `test_the_gated_step_compares_the_peeled_id`); `sha`
  dropped from the smoke's entry and `--no-parent` dropped (expected:
  `test_the_smoke_installs_by_ref_and_sha`); `id-token: write` put back on `build` (expected:
  `test_only_the_attest_job_can_attest`). Commit, run the oracle on the workflow entries.

- [ ] **Step 6: Commit and push;** the controller reads `gh pr checks` for `installed-plugin` on
  both legs and `plugin` before the wave is complete.

## Wave F — Task 7

### Task 7: The release, restated with a pin

**Files:**
- Modify: `RELEASING.md`, `CONTRIBUTING.md`, `scripts/mutation_oracle.py`,
  `tests/scripts/test_mutation_oracle.py`, `changelog.d/+plugin-repository.change.md`,
  `tests/test_documents.py`, `tests/test_check_workflow.py` (`RELEASING.md` joins
  `test_one_plugin_repository_everywhere`)

- **`RELEASING.md`:**
  - The opening sequence and section 1: the entry pins `ref` and `sha`; the "no `sha`, which the
    release commit cannot know" paragraph becomes what the `sha` is (the plugin commit, computed
    from the release commit, its parent the previous release's) and that `check --tag` recomputes
    it. The sequence names `attest`.
  - Section 2: the blocker paragraph goes. Step 5 commits, runs `uv run python scripts/release.py
    pin`, then `git add .claude-plugin/marketplace.json && git commit --amend --no-edit` (the plugin
    tree does not hold the marketplace, so the amend leaves the commit `pin` computed unchanged);
    step 6's `check --tag` verifies the pin.
  - Step 7: the classification is the exit code — `0` published (or already), `2` fix and run
    again, `1` reject the `pypi` approval — with Ruling 8's list of what `1` means, and `2`'s "no
    attestation yet" sentence: wait for `build` and `attest`, run again, and reject if it says the
    same once both are green. The dry run names the commit the `--yes` run pushes; the identity
    paragraph goes. An approval given early uploads nothing: the gated jobs refuse until the plugin
    repository's tag names the pin.
  - Step 1's read-back gains `git ls-remote https://github.com/stayfixed/stayfixed-plugin.git
    refs/heads/main` against the marketplace's current `sha`, and the plugin repository's third
    ruleset line; the first bash block (`_RELEASE_BLOCK`) is unchanged.
  - Section 3: a third ruleset, `main`, target `branch`, over `refs/heads/main`, rules `deletion`
    and `non_fast_forward`, created with the same `ruleset` helper.
  - Section 5: which commit the next release is cut on after a stopped one — on `main` when the
    plugin was not pushed, on the spent release commit when it was — and that `pin` says which; how
    a release returns to `dev` (a `chore/after-release-X` branch from `main`), and that a merge
    into `main` which resolved `.claude-plugin/marketplace.json` to `dev`'s copy drops the `sha`, so
    `pin` refuses with no parent while the plugin repository's `main` exists: restore the entry
    from the last release commit. A patch of an older line is not supported.
  - Section 6: the `plugin_tree.py` and `publish_plugin.py` paragraphs shrink to one sentence each
    and their usage lines, pointing at `--help` and the module docstrings; `check`'s paragraph names
    the pin and `pin`.
- **The open question on `GROUP_OF`'s grouping** is recorded once, in `CONTRIBUTING.md`; the
  comments in `scripts/mutation_oracle.py` and `tests/scripts/test_mutation_oracle.py` point there.
- **`changelog.d/+plugin-repository.change.md`:** the entry pins the plugin repository's commit as
  well as its tag, so a tag moved there does not change what installs.

- [ ] **Step 1:** edit; **Step 2:** `uv run pytest -n auto -q tests/test_documents.py
  tests/test_fixtures.py tests/test_public_anchors.py tests/test_neutral.py
  tests/test_check_workflow.py tests/scripts/test_mutation_oracle.py`; PASS. **Step 3:** commit —
  `docs(releasing): cut a release with a pinned plugin commit, and classify the publisher by its exit code`.

## Wave G — Task 8 (controller-run)

### Task 8: Measure what the tests cannot, and amend the design

Recorded in this file's Findings, quoting only persisted logs under the scratchpad.

- [x] **Step 1: A release rehearsed end to end on scratch repositories.** A clone of the branch at
  its head; a version bump to `0.3.0`, committed; `release.py pin --remote <empty bare>`; the
  amend; `release.py check --tag v0.3.0`; a second release `0.3.1` on top, `pin` refusing while
  the bare remote's `main` is empty and passing once `0.3.0`'s plugin commit is pushed there by
  hand (scratch only). Both commits built into one bare repository with `plugin_tree.py commit`;
  `claude plugin validate --strict` on a marketplace pinning the `sha`; install by `ref` and `sha`
  with 2.1.296 and the pinned 2.1.261 (`npx`), `installed_plugins.json` naming the pinned commit.
- [x] **Step 2: The publisher on that clone,** with the owner's yes for its `gh` calls:
  `publish_plugin.py --tag v0.3.0 --remote <bare>` without `--yes` stops at step 2 (GitHub holds no
  such tag: exit `2`), and the bare remote holds no ref afterwards.
- [x] **Step 3: An empty repository's answer.** If `stayfixed/stayfixed-plugin` exists and is
  still empty when this runs, `gh api repos/stayfixed/stayfixed-plugin/git/ref/heads/main` answers
  `409` or `404`, as Task 4 step 8 reads it; otherwise a follow-up for the first release.
- [x] **Step 4: After the merge,** amend the private design's §5.9 (a URL source pinned to the tag
  and to its commit, the commit computed from the release commit) and §15.7 (the 2026-10-11
  decisions), in that repository.

## Findings

Written by the pre-flight, Task 8 and the pull request's review.

### Pre-flight measurements (2026-10-11)

Run by the controller with the owner's yes, against `v0.2.0`'s wheel downloaded from its Release
(sha256 `ad85c75…`); logs persisted in the session's scratchpad.

- **The certificate identity.** `gh attestation verify` with `--cert-identity
  https://github.com/stayfixed/stayfixed/.github/workflows/release.yml@refs/tags/v0.2.0`,
  `--source-ref refs/tags/v0.2.0`, `--source-digest efd4b6d…` and `--deny-self-hosted-runners`
  exits `0`, and the certificate's SubjectAlternativeName read from `--format json` is exactly that
  URL; the same URL without `@…`, with `@refs/tags/v0.2` and with `@refs/tags/v0.1.1` each exit `1`
  ("verifying with issuer \"sigstore.dev\""). Task 5's `CERT_IDENTITY` form stands.
- **The attestation API.** `repos/stayfixed/stayfixed/attestations/sha256:<the wheel's digest>`
  answers `200`; a digest no release attested answers `404`, `gh api` exits `1`, prints a JSON body
  with `"status":"404"` and writes `gh: Not Found (HTTP 404)` to stderr.
- **`sha` on the pinned CLI.** 2.1.261's `plugin validate --strict` passes the marketplace with
  `"sha": "0"*40` (exit `0`); the control `"sha": "not-a-sha"` fails (exit `1`, "Must be a full
  40-character lowercase git commit SHA"), so the validator reads the field.

### Plan review (2026-10-11)

A read-only review of this plan at `9968c4b` (premise, oracle and boundary lenses, an architecture
pass and a security pass) found two critical defects and ten to fix before dispatch; every one
reproduced or measured was taken into the text above. Critical: the remote's state — "already
published", "main is not the parent" — was decided from an `ls-remote` the owner's `GIT_CONFIG_*`
can redirect, while the read-back that defeats a redirect ran only after a push (now GitHub's API
decides on the default remote, Ruling 7); and the git dir took its object format from the owner's
`init.defaultObjectFormat`, so a configured machine computed sha256 ids and the publisher rejected
its own release (now `--object-format=sha1`; reproduced). Also taken: `git archive` reads
attributes and line endings, so the tag's code is read from its objects (reproduced); an empty
temporary directory is no git dir (reproduced); `python -c` leaves `-c` in `sys.argv[0]`
(reproduced); the exit classes refined (Ruling 8); the SAN form, the attestation API's answers and
2.1.261's `validate` of a `sha` moved to pre-flight; the fate of each existing publisher test
written down; test builders on the sealed git; a manifest and a commit text spelled literally; the
render replaced by `fast-import` (a case collision on macOS); the `attest` job carrying `dist/*`
too; the release's return to `dev` documented; Wave C split. Measured by the controller the same
day: `claude plugin validate --strict` 2.1.296 passes an entry with `sha`; the annotated `v0.1.0`
release run recorded the peeled commit as `headSha`. Not taken: a refusal of the tag's own
`plugin_tree.py` stays exit `2` (Ruling 8: CI ran the same code on the same commit green).

### Execution (2026-10-11)

Waves A–F ran with one task review each and the fix rounds below; Waves E and F ran in sibling
worktrees beside C and D at the owner's request (parallel wherever it costs no quality) and were
cherry-picked onto this branch. Rulings that change this plan's text:

- **Ruling 8, the attestation (amended).** The verify-classification seam broke three times:
  "200 → 1" let an old `gh` or a Sigstore failure on the owner's machine ask for a rejection; a
  weaker unconstrained verify still let a `gh` missing one strict flag, or a transient failure of
  the strict verify alone, reach `1`; and a release re-cut onto a commit with a byte-identical
  manifest would be answered `200` by the old attestation. `gh`'s exit code cannot tell a wrong
  attestation from a machine that could not verify, so a failed `gh attestation verify` is now
  never `1`: it is `2`, and GitHub's attestation listing only chooses the advice (none yet: run
  again once `build` and `attest` are green; one that does not verify here: run again with a
  working `gh` and network; reject if either says the same then). The publisher also refuses a
  `gh` older than 2.101.0, the version its flags were measured on, and a `gh` pre-release.
  `test_a_verify_failure_is_classified_by_whether_an_attestation_exists` is now
  `test_a_failed_verify_is_refused_with_the_advice_github_s_listing_chooses`.
- **`gh auth status`** runs before the publisher's first `gh` call (the source anchor), which is
  also before `_verify`.
- **A first parent whose `source` is not an object** (`origin/main` still holds the old `"./"`)
  is refused, not read as no parent; `0.3.0` is cut on top of the dev→main merge, whose entry
  pins no `sha`, so its plugin commit is parentless. `RELEASING.md` section 5 says so.
- **`release.py pin`** reads the plugin repository's `main` through `ls-remote`, which the owner's
  git configuration can redirect; it is the early check, and the publisher's read through
  GitHub's API after the tags is the authoritative one.

- **The publisher's entries have a group of their own.** The final review's fix wave took
  `mutations/tooling.toml` past the oracle's group-file cap, so it was split by its largest area,
  as `GROUP_OF`'s rule asks: `scripts/publish_plugin.py`'s entries are `mutations/publish.toml`'s,
  and the Global Constraint routing `scripts/*.py` to `tooling.toml` excepts the publisher.

Follow-ups, as they were settled after the pull request merged (2026-10-12), each by the commit
that fixed it in the follow-up pull request, "moot", the reason it was not taken, or "owner
action" for what only the owner can do on GitHub or in the private design:

- **Measurements.** GitHub's answer for the empty plugin repository's `main`: `409` ("Git
  Repository is empty."), `gh api` exiting `1`, and `git ls-remote` listing nothing with exit
  `0`, measured on 2026-10-12 right after `stayfixed/stayfixed-plugin` was created with its four
  rulesets, which read back as `RELEASING.md` step 1 expects. Amending the private design's two
  sections on the plugin's distribution (Task 8 Step 4): done in that repository the same day.
- **`scripts/publish_plugin.py`.** `_verify` and `_attested` as one `_advice`: not taken; the seam
  broke three times before Ruling 8 settled it, its entries anchor on the current lines, and a merge
  changes no outcome. Only two exact spellings of the default remote: not taken; `RELEASING.md` step
  7 says so, any other spelling is reported "not confirmed", and widening it means modelling git's
  URL forms. `--require-pin`'s exit 1 before the attestation: Ruling 8, kept, and documented in step
  7 (`da6c3d5`). `CLICOLOR_FORCE`/`GH_FORCE_TTY` unnamed: named (`09d36a5`), then prevented for
  every caller by the runner (`70c6a5c`), below. A failed post-fetch `rev-parse` reported as "main
  moved": fixed (`09d36a5`). The login refusal advising only a login: fixed (`09d36a5`). A `gh` dev
  build read as a pre-release: not taken; refusing it is right, and "install a released gh" is the
  advice for it too. Source reads without `plugin_tree.GIT_OPTIONS`: not taken; scripts do not
  import one another, and those reads run in the owner's checkout, not a bare repository, so
  `safe.bareRepository` does not apply. The exit table's two copied closures: not taken; two short
  arrangements, each row held to its own summary. `"no src/stayfixed"` without a mutation of its
  own: given one (`09d36a5`). Its docstring's gh floor, held by no test: held (`09d36a5`).
- **`scripts/plugin_tree.py`.** `peel`'s "the one place": reworded (`1169d84`); `pinned_sha`
  re-peeling resolved ids: not taken, one `rev-parse` of a full id that answers the same id.
  "exited -1" in `peel`, `_listing` and `_blobs`: `NO_ANSWER`'s words (`1169d84`), then
  structural in both scripts (`104a32e`), below.
  `commit --manifest-file` checked by its first line: held whole (`1169d84`). "from a url
  source": reworded (`1169d84`). A malformed `sha` at the tag reported twice by `check --tag`:
  reported once (`b1da2e2`); the tag's own tool refusing it with exit `2` is Ruling 8, kept.
- **`scripts/release.py`.** `_pinned`'s count and shape: said apart, zero and two entries
  tested (`b1da2e2`). `_is_sha` re-spelled: reused (`b1da2e2`). `ensure_ascii=False`: held
  (`b1da2e2`).
- **Workflows and their tests.** `attest`'s denylist: an allowlist of its steps (`04f8134`).
  `github-release`'s persisted token: `persist-credentials: false` (`04f8134`), and every checkout
  of the release held to it (`4c67a92`). Job readers not consolidated: not taken; both read through
  the one strict reader, `tests.workflow_yaml.load`, and what is left is three lines each. The
  literal `\n`: fixed (`04f8134`). The commit-id shape test's scripts half: flags compared, and an
  entry for each half (`04f8134`). `_code`'s backslash branch: held by a case (`04f8134`).
- **Tests.** `tests/test_payload.py`'s unread mode: dropped (`1099a4f`). `listed()` and the
  bare-remote builders: not taken; `listed()` calls the script, which `tests/plugintree.py` never
  does by design, and the two remote builders share only a `git init --bare`. The plugin URL
  spelled out in `tests/test_manifests.py`: the shared constant (`1099a4f`).
- **Documents.** The restore commit red under plain `check`: said, with why nothing checks it
  (`da6c3d5`). A persistent `404` explained only as "attest has not written it": explained
  (`da6c3d5`). Ragged wraps in `mutations/`: not taken; comments only, and a rewrap moves quoted
  names the citation test reads. The stale count in a `ci.yml` comment: the coverage step's
  statement count, dropped (`da6c3d5`). The unwrapped line in `CONTRIBUTING.md`: wrapped
  (`da6c3d5`).
- **From the external review.** The plugin repository's tags without a creation rule: a fourth
  ruleset documented in `RELEASING.md` section 3 (`da6c3d5`), and created with the repository on
  2026-10-12.
  `RepositoryRole` 5 from community reports: section 3 now says to confirm the bypass on the
  settings page (`da6c3d5`). Looking for it on 2026-10-12 found this repository's
  `release tag creation` had never been created, only `release tags`; it was created that day
  from section 3's body and reads back as step 1 expects. The owner confirmed on both repositories'
  settings pages the same day that the bypass list reads "Repository admin", so `RepositoryRole`
  5 is that role. `pin`'s refusal naming the pushed-plugin case: named (`b1da2e2`).
  `src/stayfixed/release/api.py`'s importers: named (`da6c3d5`). `cat_file_batch` into
  `stayfixed.gitenv`: not taken here; it changes the runtime, which no item of this list needs,
  and is the owner's to decide. The load-sensitive
  `test_doctor_launches_the_number_of_subprocesses_it_says_it_does`: not taken; it failed once
  with nothing kept, and has not been reproduced. Deleting the merged branch
  `wp/plugin-commit-pin` on the remote: the owner's, and not wanted.

The follow-up pull request's own review (2026-10-12) found two Important findings, both a class
fixed at one site while it lived in a shared seam, and four Minor ones:

- **"exited -1" left in the publisher, and brought back by the new post-fetch read.** The second
  finding at that seam, so the check was made structural rather than added at four more sites:
  each script runs every local git through one wrapper that refuses no answer in `NO_ANSWER`'s
  words, and a test holds that no other function calls `git_run` (`104a32e`). `gitenv.git_answer`
  was not used: it takes no `stdin` and no `timeout`, which `cat-file --batch` needs.
- **The coloured `gh` answer diagnosed in one caller.** `overlay create`'s `gh repo view --json`
  failed the same way, unnamed. `GH_FORCE_TTY` and `CLICOLOR_FORCE` join the runner's
  `_ENV_DROP`, which prevents it for every caller, and the publisher's diagnosis went
  (`70c6a5c`); the one runtime change of this work, with a changelog fragment.
- **`check --tag` holding the pin back on any entry problem:** kept, the comment now says so and
  what it costs, rather than a second list of what `plugin_tree.py` refuses (`4c67a92`).
- **The persisted-token test classifying jobs:** every checkout of the release is held, `build`'s
  included, which now persists none (`4c67a92`).
- **Step 1's read-back depending on creation order:** both listings sorted by name (`4c67a92`).
- **A fourth reader of the marketplace entry (`_pinned`):** not taken; sharing
  `marketplace_problems` would make `pin` refuse a bad `ref` or a stray `version`, a change of
  what `pin` refuses that nothing asked for. Left for the next change to the entry's shape.

### External review (2026-10-12)

A four-seat review of the pull request at `86ba0ed` (correctness of the commit and `pin`; the
publisher and the workflows; security; simplicity and the operator procedure) found no Critical
and one Important finding: the stopped-release procedure failed once `origin/main` had moved
(`git pull` on a diverged `main` exits 128; the pushed case's `git push origin main` was rejected
after PyPI had published). Every release, a stopped one's too, is now cut on `origin/main`, and
both stopped cases were rehearsed. Also taken: an import failure exits 2 rather than 1; the
`attest` job and the smoke print why no plugin commit was made; the smoke moves its tag to a
decoy child so an install that followed the `ref` would fail; `_version` accepts `X.Y.Z` only;
determinism held against an inherited `GIT_*` environment and a global attributes file; `FORMAT`
and `OBJECT_NAME` joined the cross-script equality test; one `ls-remote` of the tag after a push
tells GitHub's lag from a push sent elsewhere; a separate ruleset lets only the admin role create
a release tag (a bypass on the existing ruleset would have let the admin move or delete one); the
source-anchor advice investigates a tag the owner did not push before fetching it.

### Task 8 (2026-10-14, before the `0.3.0` release)

Run by the controller with the owner's yes, on a clone of `dev` at `17f2684`; logs persisted in the
session's scratchpad.

- **Step 1, a release rehearsed end to end.** The bump to `0.3.0` committed, `release.py notes`
  run, then `release.py pin --remote <empty bare>`: "pins d34a4f0…, the plugin commit of HEAD";
  amended in, `check --tag v0.3.0`: "one version everywhere: 0.3.0". A second release `0.3.1` on
  top: `pin` refused (exit `2`) while the bare remote had no `main` ("the plugin commit 0708479…
  has parent d34a4f0…, and … has no main; the plugin repository's main moves only by
  fast-forward"), and passed once `0.3.0`'s plugin commit was set there by hand, pinning `0708479`,
  whose parent is `d34a4f0`; `check --tag v0.3.1` passed. Both commits were built into one bare
  repository with `plugin_tree.py commit` (218 files each). `claude plugin validate --strict` passed
  a marketplace whose entry carries `ref` and `sha`, on 2.1.296 and on the pinned 2.1.261 (`npx`);
  installing from it in a scratch configuration directory succeeded on both, and
  `installed_plugins.json` named version `0.3.1` with `gitCommitSha` `0708479…`, the pinned commit.
- **Step 2, the publisher on that clone.** `publish_plugin.py --tag v0.3.0 --remote <empty bare>`
  without `--yes` exited `2`: "your local v0.3.0 names 0ff38a4…, and GitHub's stayfixed/stayfixed
  holds no such tag … nothing was run"; the bare remote held no ref afterwards.
- **Step 3, an empty repository's answer.**
  `gh api repos/stayfixed/stayfixed-plugin/git/ref/heads/main` answered `409` ("Git Repository is
  empty"), as Task 4 step 8 reads it.
- **The release itself (2026-10-14).** `0.3.0` was cut on `main` at `45f8266` (the merge of
  `dev`); `pin` wrote `d34a4f0`, the plugin commit the rehearsal computed, since only plans and the
  changelog differ between the two sources; `publish_plugin.py --tag v0.3.0` planned "would push
  218 files … commit d34a4f0 … main and v0.3.0" and `--yes` pushed them; GitHub's API read
  `main` and `v0.3.0` back at `d34a4f0`.
- **Step 4, the private design.** Nothing left to amend: its §5.9 already describes the URL
  source pinned by `ref` to the tag and by `sha` to the plugin commit, computed from the release
  commit, and its §15.7 records the 2026-10-11 decisions.
