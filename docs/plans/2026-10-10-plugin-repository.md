# The plugin published from a repository of its own: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **The wave is the dispatch unit, not the task.** Waves are lettered (`A`–`E`) and own a run of
> the continuously numbered tasks. One implementer, one review round and one reviewer per
> **dispatched** wave; inside a wave every task keeps its own failing test, verification and
> commit. Do not dispatch one subagent per task.
>
> **Task 6 is not dispatched.** It runs the real `claude` CLI against scratch repositories and
> records what it measures; the controller runs it.
>
> **One pull request** (`wp/plugin-repository`), waves in order on one branch, rebased on `dev`
> before every push. Every dispatched seat runs on Opus.
>
> **Review rounds stop at Minors.** Only a Critical or Important finding opens another fix round;
> a Minor goes to Findings' "Follow-ups, to file when the pull request closes" and is filed then.

**Goal:** publish the Claude Code plugin from `stayfixed/stayfixed-plugin`, a repository whose
root is a tree generated from this one, so that `0.3.0` can be released: the directory's file
rules judge that tree, CI builds, installs and tests it on every pull request, the release workflow
attests its manifest, and the owner pushes it with one command that refuses a tree the attestation
does not vouch for.

**Architecture:** two stdlib scripts. `scripts/plugin_tree.py` (create) is a pure reader: it names
the plugin's paths once and reads them from a commit's tree, never from the disk — `members` lists
them with their modes and bytes, `manifest` is the text a release attests (one line per file: mode,
sha256, path), `render` writes the tree out — with the CLI commands `manifest` and `render`.
`scripts/publish_plugin.py` (create) is the publisher: it *runs* `plugin_tree.py` as a program,
checks the attestation against the tag's commit, builds the plugin repository's next commit with git
plumbing (no working tree, no index, no filters, no hooks), reads it back whole, and pushes `main`
and the tag atomically only with `--yes`. `scripts/release.py` also *runs* `plugin_tree.py` to
count the tree, so no script imports another; only the tests import `plugin_tree`, through
`tests/scriptload.py`. Every guard that judged "the plugin folder" now judges the generated tree:
the payload test, the release check's file count, the CI validator, the install smoke. The
marketplace entry here becomes a `url` source, `https://github.com/stayfixed/stayfixed-plugin.git`,
pinned to the tag by `ref`, and that `ref` joins the version sources `scripts/release.py check`
holds equal.

**Tech Stack:** Python ≥ 3.11 standard library; `uv`, pytest (`-n auto`), ruff, mypy, the mutation
oracle (`scripts/mutation_oracle.py`), towncrier fragments in `changelog.d/`; GitHub Actions with
`actions/attest-build-provenance` and `astral-sh/setup-uv` (both already pinned in `release.yml`);
`gh attestation verify` on the owner's machine; the `claude` CLI 2.1.261 in CI (the version `ci.yml`
and `smoke.yml` pin).

**Spec:** the agent-harness extraction design, in a private repository this one cannot link to —
§4 (the published plugin's row), §5.9 (the release, amended 2026-10-10 with the plugin's own
repository), §15.7 (wave 8's outcome: the owner's decisions of 2026-10-05 and 2026-10-07). The
owner's decisions this plan implements, quoted from the wave-8 plan's Findings ("Left for later",
item 1): "A generator produces the plugin tree. CI builds it, tests it, and attests the generated
tree's digest. The owner pushes it with one command that checks the digest against the
attestation, so CI holds no credential to a second repository (`RELEASING.md`). The marketplace
entry stays here, with a URL source pinned to the tag. The 512-file check moves to the generated
tree." Settled with the owner on 2026-10-10: the repository is `stayfixed/stayfixed-plugin`; the
owner creates it and its tag ruleset at the release (`RELEASING.md`, section 3), so nothing in this
plan creates or pushes to it. Settled with the owner on 2026-10-10, after the pre-dispatch review:
the entry is a `url` source, as the decision says, so CI's rehearsal and production share one source
type; the plugin repository carries one tag, `vX.Y.Z`, and no `stayfixed--vX.Y.Z`, which nothing
there reads; `docs/cli.md` leaves every size guard, because the directory's limits judge the files
that ship and the guard follows `PLUGIN_PATHS`; `README.md`'s links to files outside the plugin
tree become absolute links to this repository's `main`. This plan holds the 512 count on every pull
request, which is stronger than §5.9's "at a release"; the private design owes the matching
amendment (Findings, follow-ups).

**Scope:** the step that `docs/plans/2026-10-04-wave-8-core-cut.md`, Task 17 Step 3, left open, as
its own pull request. A change belongs to this plan iff it (a) generates, counts, renders or
publishes the plugin tree; (b) moves a guard that judged the repository root as the plugin folder
onto the generated tree; (c) points the marketplace entry at the plugin repository, or holds that
entry to the release's version; (d) builds, installs, tests or attests the generated tree in a
workflow; (e) restates the documents and comments those changes falsify (`RELEASING.md`,
`README.md`, `CONTRIBUTING.md`, the comments listed in Task 2, fragments), including the README links
the plugin repository cannot resolve; or (f) records Task 6's measurements and the review's outcome
in this plan's Findings. Out: the `0.3.0` release itself (version strings, `CHANGELOG.md`, tags),
which the owner cuts by `RELEASING.md` after this merges; creating `stayfixed/stayfixed-plugin` or
its ruleset; Codex's install path for a `url` source (unmeasured, recorded in Findings); the
directory submission; any command, flag or configuration key in the shipped CLI; whether
`GROUP_OF`'s coarse grouping still earns its table once the plugin tree no longer holds `mutations/`
(a follow-up).

**Premise:** measured on 2026-10-10 at `dev` = `21bdbcb`. A task that finds one no longer holds
stops and reports the mismatch instead of guessing.

- **The plugin folder is the repository root.** `.claude-plugin/marketplace.json` has one entry,
  `stayfixed`, with `"source": "./"`; `tests/test_manifests.py`
  `test_marketplace_has_a_description_and_an_unversioned_entry` and `tests/test_payload.py`
  `test_the_plugin_folder_is_the_repository_root` both pin `./`. The repository tracks 596 files.
- **The runtime reads nothing outside nine paths.** `.claude-plugin/plugin.json`,
  `.codex-plugin/plugin.json`, `hooks/` (`hashes.json`, `hooks.json`, `run-hook.sh` at `100755`),
  `scripts/stayfixed` (`100755`), `src/stayfixed/`, `skills/`, `agents/`, `README.md`, `LICENSE`:
  218 files at `21bdbcb`. `hooks/hooks.json` runs `${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh`; the
  wrapper finds `scripts/stayfixed` beside its own directory; the launcher puts `../src` on
  `sys.path`; presets, profiles and templates are package resources under `src/stayfixed/`. No
  runtime code and no skill reads `docs/`, `CHANGELOG.md`, `pyproject.toml`, `RELEASING.md` or
  `uv.lock`. `hooks/hashes.json` records `hooks/hooks.json`, `hooks/run-hook.sh` and
  `scripts/stayfixed` only, so editing `README.md` changes no hash.
- **`doctor` judges the checkout it was imported from.** `_own_root`
  (`src/stayfixed/doctor/checks.py`) is `Path(stayfixed.__file__).resolve().parents[2]` when
  `hooks/run-hook.sh` is there, and it is asked before `CLAUDE_PLUGIN_ROOT`. `smoke.yml`'s `doctor`
  step sets `PYTHONPATH: src`, so today it reports on the checkout, not on `$INSTALLED`; only
  `scripts/smoke_hooks.py` and `scripts/smoke_exfiltration.py` run the installed tree.
- **Five runtime uses of `REPOSITORY_URL`/`REPOSITORY_SLUG` mean this repository and stay:**
  `src/stayfixed/doctor/checks.py` (`cli-path` remedy), `src/stayfixed/overlay/doctor.py`,
  `src/stayfixed/setup/run.py` (`INSTALL_COMMAND`), `src/stayfixed/release/pins.py` (`git
  ls-remote` of this repository's tags, for the `check.yml` pin `init` writes),
  `src/stayfixed/project/templates.py` (the reusable workflow's `uses:`). `check.yml` stays here.
- **The release count skips a non-path source.** `scripts/release.py` `plugin_folder_counts`
  `continue`s past an entry whose `source` is not a string, and
  `tests/scripts/test_release.py::test_a_plugin_the_marketplace_fetches_from_elsewhere_is_not_counted`
  pins that. Changing the entry without changing the count makes the 512 check at a tag check
  nothing. Seven `mutations/tooling.toml` entries (from "release check stops refusing a plugin folder
  over the directory's count" to "release check reads a plugin folder git could not list as empty")
  cite the four count tests and `test_a_tag_outside_a_git_checkout_is_refused_for_want_of_a_count`.
- **`release.py`'s sources and its tests.** `_parse` sends any `.json` source to a top-level
  `version` key; the marketplace is read by `_marketplace_entries`, and the only entry rule today
  refuses an entry carrying `version` ("plugin.json is the only source"). "Six sources" is spelled in
  `TAG_HELP`, `build()`'s refusal and four `RELEASING.md` sentences. `tests/scripts/test_release.py`
  defines `MARKETPLACE = {… "source": "./"}`, which `repo()` writes (29 uses);
  `test_collect_reads_every_source_value` pins `collect()`'s exact dict; the tag tests'
  repositories (`_committed(_at(...))`) hold only the version sources.
- **The payload guard walks the whole tree.** `tests/test_payload.py` `tracked_payload` lists every
  row of `git ls-tree -r -l -z HEAD` and reads blobs through `git cat-file --batch` (`_blobs`, over
  `tests.gitfixture.git_bytes`); `test_the_tree_is_inside_the_directory_limits` drops only the
  count's finding (`findings_but_the_count`, with
  `test_the_tree_rule_excludes_the_count_and_nothing_else` and
  `test_a_count_rule_that_answers_wrongly_is_refused_rather_than_excluded`). `FILES_MAX` is read
  from `scripts/release.py` `PLUGIN_FILES_MAX` (512). `FILE_MAX_BYTES` is imported by
  `tests/scripts/test_mutation_oracle.py`. `docs/cli.md` is 261,646 bytes, 498 under
  `FILE_MAX_BYTES`. `scripts/mutation_oracle.py` (the `GROUP_OF` comment),
  `tests/scripts/test_mutation_oracle.py` (`GROUP_FILE_MAX_BYTES`' comment), `CONTRIBUTING.md`
  (the paragraph on coarse groups) and `RELEASING.md` (section 1's last paragraphs, section 6's
  `check`) justify themselves by "the plugin folder is this repository's root, so every tracked
  file counts".
- **CI installs and validates the repository root, without `uv`.** `smoke.yml` `installed-plugin`
  (`macos-latest`; checkout, setup-node, setup-python 3.13, no `uv`) runs `claude plugin marketplace
  add "$PWD"` and `claude plugin install stayfixed@stayfixed-marketplace`, then `diff -r hooks
  "$INSTALLED/hooks"`, `scripts/smoke_hooks.py`, `doctor` and `scripts/smoke_exfiltration.py`.
  `ci.yml` `plugin` (checkout, setup-node, no Python setup, no `uv`) validates
  `.claude-plugin/plugin.json --strict`, `.claude-plugin/marketplace.json --strict`,
  `.codex-plugin/plugin.json`, and runs `claude plugin tag --dry-run .` under a comment saying it
  checks "the manifest side of one version". No test pins the `plugin` job or the `marketplace
  add` line; `tests/test_check_workflow.py` pins the two smoke summary lines and reads workflows
  through `tests.workflow_yaml`, a strict subset (no flow mappings, folded scalars or anchors).
  `scripts/smoke_hooks.py` commits its scratch repository with `-c user.email=… -c user.name=…`.
- **The release attests `dist/*` only, in `build`, before any human gate.** `release.yml` `build`
  (`astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7`) runs `scripts/release.py check
  --tag "$GITHUB_REF_NAME"` (pinned by `tests/test_fixtures.py`), the suite, `uv build`, then
  `actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8` on `dist/*` with
  `id-token: write` and `attestations: write`. `environment-gate`, then `publish` and
  `github-release` behind the `pypi` environment, come after `build`.
- **The release order.** `RELEASING.md` step 6 pushes `vX.Y.Z` and `stayfixed--vX.Y.Z`; step 7
  watches the run, one `pypi` approval starts both PyPI's `publish` and `github-release`, and `main`
  moves once PyPI lists the owner. `README.md` (the package's long description) installs
  `stayfixed/stayfixed@v0.2.0`, a tag, and holds relative links to `docs/cli.md` (eight),
  `docs/methodology/`, `CONTRIBUTING.md`, `SECURITY.md` and `tests/outbound/walk.py`.
  `tests/test_fixtures.py` `_RELEASE_BLOCK` pins step 1's bash block; `tests/test_public_anchors.py`
  refuses plan vocabulary in tracked documents outside `docs/plans/`.
- **The marketplace documents `github` and `url` sources with `ref` and `sha`; `url` takes an
  `https` or `file://` git URL; validation does not fetch; a plugin whose manifest version did not
  change is not re-copied into the cache by `claude plugin update`** (code.claude.com, "Marketplace
  reference" and "Plugins reference", fetched 2026-10-10). A `ref`-only pin is the only one available
  here: the release commit names the plugin repository's tag before the owner pushes the commit it
  will name.
- **`gh attestation verify` is online and binds a ref name, not a commit, unless asked.** It
  fetches attestations from the GitHub API; unauthenticated, offline and "no attestation" are all
  non-zero exits. `--source-ref` checks the ref name; the source commit is checked only when
  `--source-digest` is passed; `--signer-workflow` is an anchored exact match (cli.github.com manual
  and `cli/cli` trunk, read 2026-10-10 by the pre-dispatch review; Task 6 Step 4 records `gh
  attestation verify --help`).
- **`overlay publish-template` is the pattern, not a library.** `src/stayfixed/overlay/publish.py`
  renders, clones with `gh repo clone`, empties the clone but `.git`, writes, `add -A`, commits and
  pushes through `Runner.launch`; without `--yes` it runs only `gh repo view`. Its helpers are
  private, `src/stayfixed/overlay/api.py` exports none of them, and
  `tests/boundaries/test_api_surface.py` refuses a script that imports past an area's `api.py`. Its
  `_replace_tree` writes UTF-8 text through a working tree under the owner's git configuration.
  Scripts may import top-level modules directly (`scripts/release.py` imports
  `stayfixed.gitenv.git_run`, `fsops`, `runner`, `errors`, `cli.run`).
- **Two ways to run git, with different environments.** `gitenv.git_run(root, *args, stdin=None)`
  returns `(code, stdout)` decoded with `surrogateescape` (`gitenv.answer_bytes` gives back the bytes
  git wrote), accepts `stdin` as text, and hands git only `PATH`, `HOME`, `LANG`, `LC_ALL` and
  `SYSTEMROOT` — no `SSH_AUTH_SOCK`, no `GIT_AUTHOR_*`. `Runner.launch(argv, cwd)` passes the
  process environment minus `GIT_DIR`, `GIT_INDEX_FILE` and the other location variables, closes
  stdin (`subprocess.DEVNULL`) and decodes output with `errors="replace"`.
- **Write primitives.** `fsops.checked_components`, `mkdirs_within`, `open_within` (yields a
  directory descriptor and the final name; the caller opens with `dir_fd`) and `fsops.utf_8_name`
  are public.
- **Test doubles.** `tests/runners.py` `Recorder` answers any program by argv prefix and records
  only the calls that reach its `launch`; `tests/scriptload.py` loads a script as a module and
  registers it in `sys.modules` first (`release()`). Tests never run `gh` or `claude`; they may run
  `git`. `tests/conftest.py` points `HOME` at a fresh directory per test whose `.gitconfig` holds
  only the maintenance keys: no git identity.
- **Routing.** `GROUP_OF` sends `scripts/*.py` and `.github/workflows/*.yml` to
  `mutations/tooling.toml`, and `tests/test_payload.py`, the marketplace file and the README to
  `mutations/repository.toml`.
- **Fragments** are `changelog.d/+<slug>.<type>.md`, types `upgrading`, `feature`, `fix`, `change`.

## Global Constraints

- **Runtime is untouched.** Nothing under `src/stayfixed/`, `hooks/`, `scripts/stayfixed`, `skills/`
  or `agents/` changes, so `hooks/hashes.json` does not change either. If a task finds it must
  touch one, it stops and reports. `README.md` and `LICENSE` are plugin members but not runtime.
- **No script imports another.** `scripts/release.py` and `scripts/publish_plugin.py` run
  `plugin_tree.py` as `[sys.executable, str(Path(__file__).with_name("plugin_tree.py")), …]`; only
  tests import it, through `tests/scriptload.py`. Scripts import only the standard library and
  top-level `stayfixed` modules (never past an area's `api.py`), and run as `uv run python
  scripts/<name>.py …`.
- **The tree is read from a commit, never from the disk.** A file edited, deleted or only staged is
  not in what the directory, the attestation or the plugin repository sees.
- **The plugin's paths are named once**, in `scripts/plugin_tree.py` `PLUGIN_PATHS`; every other
  reader runs that script, or, in a test, imports it.
- **A plugin path is UTF-8 text with no control character** (`members` refuses any other): the
  manifest is line-oriented and is the only comparison `publish` makes, so a `\n` in a file name
  could otherwise forge a line.
- **Nothing in this plan writes to a remote.** `publish` pushes only with `--yes`, and no test,
  workflow or task runs it with `--yes` against anything but a scratch repository on disk.
- **Every new assertion ships with the mutation that reddens it, or a sentence saying why none
  exists** (`CONTRIBUTING.md`, "Tests"). A mutation named here is a hypothesis until a run watched
  it fail; a load-bearing guard gets a `mutations/` entry in the group file its path routes to. **An
  expectation is never read from the subject:** the nine paths and `FORMAT` are spelled literally in
  the tests that pin them.
- **A removed or renamed test takes its mutation entries and every comment citing it along in the
  same commit** (`tests/scripts/test_mutation_oracle.py` resolves cited entry names). An entry whose
  behaviour still exists is re-pointed at the test that now carries it, not deleted.
- **Every value that reaches a workflow shell arrives through `env:`**
  (`tests/test_fixtures.py::test_no_workflow_splices_an_expression_into_a_shell`), and every
  workflow edit stays inside `tests.workflow_yaml`'s subset.
- **Tests never run `gh`, `claude`, `codex`, `pip` or `pre-commit`,** and never read the
  developer's `~/.claude`, `~/.codex` or `~/.config/stayfixed`. A test that commits through
  `gitenv.git_run` writes `user.name` and `user.email` into its `HOME`'s `.gitconfig` (environment
  identity variables do not reach `git_run`).
- **Neutral text.** Committed text names no project outside this repository, no home directory or
  login, and no private repository; commit ids in text are 7 characters or 40. Tracked documents
  outside `docs/plans/` carry no plan vocabulary (`tests/test_public_anchors.py`).
- **User-visible changes carry a towncrier fragment** written as a release note for a stranger.
- Conventional commit subjects describing intent; no attribution trailer.

## Review Focus

1. **The release window between the tag and the plugin push.** The release commit's marketplace
   names `ref: vX.Y.Z` in the plugin repository before the owner pushes it. `RELEASING.md` (Task 5)
   orders: the tags; `build` green, which is when the attestation exists; `publish_plugin.py` dry,
   then `--yes`; only then the `pypi` approval, which releases the PyPI page and the GitHub Release;
   then `main`. Nothing public points at the tag until the approval, and the approval waits for the
   plugin. A user who finds the tag in that window gets an install error, not a wrong plugin. A
   refused `publish` means rejecting the approval: the tags are spent, nothing else is. Task 2's
   check holds `ref` equal to the version.
2. **A plugin tree that differs from what CI attested** — a local edit, a different checkout, a
   line-ending conversion, a lost executable bit, an attestation of another commit under the same
   tag name. `publish` resolves the tag to one commit and passes it to the render and to `gh
   attestation verify --source-digest`; it builds the commit with plumbing, so no filter, hook or
   attribute of the owner's configuration touches the bytes; and it reads the whole new commit back
   to the same manifest before anything is pushed (Task 4).
3. **A re-run of `publish` after a push that half happened, or after a success.** "Already
   published" (exit `0`, nothing pushed) requires the remote tag's *whole* commit to hold exactly
   the manifest — no path outside the plugin paths — and `main` to name that commit; anything else
   on the remote is a refusal. The push is `--atomic`, so `main` never moves without its tag
   (Task 4).
4. **Existing `0.2.0` installs, in two populations.** A user who added `stayfixed/stayfixed@vX.Y.Z`
   sees a new release only by re-adding the marketplace at the new tag, as with every release; a
   user who added it unpinned follows `main` and meets the entry's change from `./` to a `url`
   source in place. Task 6 measures both and Task 5's fragment says what each must do.
5. **A path the runtime needs but `PLUGIN_PATHS` omits.** The install smoke runs every hook entry,
   the exfiltration scenario and `doctor` from the installed tree (Task 3: `doctor` with
   `PYTHONPATH` at the installed `src`), so an omitted runtime path fails CI rather than a user's
   session; a further step holds the installed tree to the rendered one, so the install itself drops
   nothing. `skills/`, `agents/`, `README.md` and `LICENSE` have no runtime reader in the smoke;
   Task 1's test spells all nine paths literally, so removing one is a test edit a reviewer sees.

## Execution contract

Every seat's brief carries the section of this contract that applies to it, copied rather than
referenced, a fix round and a post-PR dispatch included.

**1. Final review.** Three parallel read-only seats — **correctness**, **architecture** (one list of
plugin paths, every guard moved and none left judging the repository root, no script importing
another, the scripts' imports within the boundary rule), **security** (what `publish` trusts: the
attestation's signer workflow, source ref and source digest, the remote, the tag; what it refuses
before it writes; that its commit is built without the owner's filters and hooks; that no workflow
gains a credential to a second repository; `env:` for every value reaching a shell) — and a
**lifecycle** seat that walks section 2.

**2. Lifecycle matrix.** Checked at pre-flight like a task, walked by the lifecycle seat. A cell
names the test or step that covers it, or "—" when the change cannot reach it.

| Command \ change | re-run, nothing changed | from a `0.2.0` tree or install | a path missing or not regular | killed or failing part-way | uninstalled |
|---|---|---|---|---|---|
| `plugin_tree.py manifest` / `render` (Task 1) | Task 1 `test_render_twice_writes_the_same_tree_and_manifest` (no mutation: the functions are stateless) | Task 1 `test_members_at_an_older_commit_are_that_commits` | Task 1 `test_a_symlink_or_submodule_among_the_members_is_refused`, `test_a_missing_plugin_path_is_refused_by_name`, `test_render_refuses_a_destination_that_is_not_empty` | Task 1 `test_render_refuses_a_destination_that_is_not_empty` (a killed render leaves a non-empty directory, which the next run refuses; the manifest file is written last) | — |
| `release.py check [--tag]` (Task 2) | `tests/test_manifests.py::test_the_repository_passes_release_check` | Task 2 `test_a_path_source_is_refused_as_the_plugin_folder_it_used_to_be` | Task 2 `test_a_marketplace_without_the_plugin_entry_is_named`, `test_a_tag_whose_plugin_tree_cannot_be_read_is_a_count_finding` | — | — |
| `publish_plugin.py` (Task 4) | Task 4 `test_a_second_publish_of_the_same_tag_pushes_nothing` | — (no earlier release was published from the plugin repository) | Task 4 `test_an_unknown_tag_is_refused_before_anything_runs`, `test_a_remote_commit_holding_a_path_outside_the_plugin_is_not_already_published` | Task 4 `test_a_tag_on_the_remote_with_another_tree_is_refused`, `test_a_refused_attestation_stops_before_anything_is_fetched`, `test_a_rejected_push_moves_no_ref`, `test_without_yes_the_remote_is_unchanged` | — |
| CI `plugin`, `installed-plugin`, `build` (Task 3) | — (a workflow run is its own re-run) | Task 6 Step 3 (both upgrade populations, measured) | Task 3 `test_the_smoke_installs_the_rendered_tree_and_never_the_checkout`, `test_the_smoke_runs_doctor_from_the_installed_tree` | — | — |

The lifecycle seat resolves every test name in this matrix against the branch; a task that renames
a test renames its cell in the same commit.

**3. Parallelism map.** One worktree, waves in order. Read-only seats run beside each other and
beside the next wave's implementer. The mutation oracle runs one at a time per host.

**4. Templates.** An implementer's brief carries these lines, copied:

- A mismatch between this plan and the tree beats a guess: stop, quote both, report.
- Paste the output of every verification command into the report; "passed" without output is not
  a result.
- Focused tests while iterating; one full run (`uv run pytest -n auto --cov --cov-fail-under=92`)
  at the end of the wave.
- A mutation this plan names is a hypothesis: apply it, run the named test, restore the line by
  re-applying the original text, and report which tests reddened and why. If it does not redden,
  or reddens for another reason (a collection error, a read-back that fires first), design one that
  reddens its target alone and say so; do not weaken it.
- Line numbers in this plan are as of `21bdbcb`; locate by the quoted text.
- Static checks at CI's scope: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
- Do not spawn subagents. Do not run `git restore`, `git checkout -- <path>`, `git stash`,
  `git reset --hard` or `git clean`. Never run `gh`, and never run `publish_plugin.py` with
  `--yes` against any remote but a scratch repository under your scratchpad or the test's
  `tmp_path`.
- Write nothing outside the worktree but your scratchpad.
- The oracle proves `HEAD`: commit the task, then run `uv run python scripts/mutation_oracle.py
  <filter>`; a fix to an entry is a follow-up commit inside the same task.
- Already verified before dispatch: the Premise section's facts.

A fix brief enumerates the sibling instances of the defect class it fixes (the
`sweep-defect-class` skill) and reports the neighbour probes it ran. A security ruling names the
minimal preconditions, where the anchor it trusts came from, and one legitimate user it must not
refuse.

**5. Verification.** The controller re-verifies only the heads it pushes, and re-derives the pull
request's body from the branch before every push. The full set before every push:

```bash
uv run pytest -n auto --cov --cov-fail-under=92
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/mutation_oracle.py
uv run python scripts/release.py check
uv run stayfixed plan check docs/plans/2026-10-10-plugin-repository.md
```

`uv run stayfixed docs check` fails on `dev` already (`AGENTS.md [missing-document]`); it is not a
gate of this plan, and a new failure beyond that one is.

## Waves

| Wave | Tasks | Mode | Size (plan lines) |
|---|---|---|---|
| 0 | — | this file, committed first on `wp/plugin-repository` | — |
| A | 1–2 | dispatched | ~255; Task 2 rewrites most of `test_release.py`'s fixtures |
| B | 3 | dispatched; verified by a push to GitHub | ~90 |
| C | 4 | dispatched | ~150 |
| D | 5 | dispatched | ~70 |
| E | 6 | controller-run, real `claude` CLI | ~40 |

Launch graph, drawn last and over what each task consumes:

```text
Wave 0 ──> A ──> B ──> C ──> D ──> E ──[PR]
```

- **Task 1 → Task 2**: the payload test imports `plugin_tree`; the release count runs
  `plugin_tree.py manifest --json`.
- **Task 1 → Task 3**: every workflow runs `scripts/plugin_tree.py render`.
- **Task 1 → Task 4**: `publish_plugin.py` runs `render` and `manifest --exact`.
- **Task 2 → Task 3**: the smoke's scratch marketplace copies the entry Task 2 writes, its name
  and the marketplace's name.
- **Tasks 2–4 → Task 5**: the documents restate what those tasks made true.
- **Tasks 3–4 → Task 6**: the rehearsal runs the workflows' commands and `publish_plugin.py` by
  hand, with the real CLI.

B and C are independent in what they import, and serialised only because both write
`mutations/tooling.toml` in one worktree. They are separate waves because B is verified by a CI run
on GitHub and C is not, and C alone reads the attestation contract, the runner seam and git's
plumbing.

## File structure

| Path | Task | Responsibility |
|---|---|---|
| `scripts/plugin_tree.py` (create) | 1 | `PLUGIN_PATHS`, `Member`, `members`, `manifest`, `render`; the CLI `manifest`, `render` |
| `tests/scripts/test_plugin_tree.py` (create) | 1 | the reader's behaviour on scratch repositories |
| `tests/scriptload.py` | 1, 4 | `plugin_tree()` and `publish_plugin()`, loaded once, as `release()` is |
| `tests/test_payload.py` | 2 | walks `members(ROOT, "HEAD")`; holds the count on every pull request |
| `scripts/release.py` | 2 | the marketplace `ref` as a version source; the entry's shape; the count by running `plugin_tree.py` |
| `tests/scripts/test_release.py` | 2 | the count and the entry's checks; fixtures carrying the plugin paths |
| `.claude-plugin/marketplace.json` | 2 | the `url` source pinned to `v<version>` |
| `tests/test_manifests.py` | 2 | the entry's shape |
| `scripts/mutation_oracle.py`, `tests/scripts/test_mutation_oracle.py` | 2 | comments the change falsifies |
| `.github/workflows/ci.yml`, `smoke.yml`, `release.yml` | 3 | validate, install and attest the rendered tree |
| `tests/test_check_workflow.py` | 3 | the workflows render the tree and never install, validate or count the checkout |
| `scripts/publish_plugin.py` (create) | 4 | `publish` and its CLI |
| `tests/scripts/test_publish_plugin.py` (create) | 4 | `publish` against bare repositories, `gh` through `Recorder` |
| `RELEASING.md`, `README.md`, `CONTRIBUTING.md` | 5 | the release order, the one-time setup, where the plugin is fetched from, absolute links |
| `tests/test_documents.py` | 5 | README's links resolve in the plugin repository |
| `changelog.d/+plugin-repository.change.md` (create), maybe `+plugin-repository.upgrading.md` | 5, 6 | the release notes |
| this file, Findings | 6 | the rehearsal's measurements |

`mutations/tooling.toml` and `mutations/repository.toml` take each task's entries.

---

## Wave A — Tasks 1–2

### Task 1: Name the plugin's paths once, and read, manifest and render them from a commit

**Files:**
- Create: `scripts/plugin_tree.py`
- Create: `tests/scripts/test_plugin_tree.py`
- Modify: `tests/scriptload.py` (add `plugin_tree()` beside `release()`)
- Modify: `mutations/tooling.toml`

**Interfaces:**
- Produces:

```python
PLUGIN_PATHS: tuple[str, ...] = (
    ".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "hooks", "scripts/stayfixed",
    "src/stayfixed", "skills", "agents", "README.md", "LICENSE",
)
FORMAT = "stayfixed-plugin-tree 1"          # the manifest's first line
REGULAR_MODES = frozenset({"100644", "100755"})

@dataclass(frozen=True)
class Member:
    path: str        # POSIX, relative to the plugin root, as git lists it
    mode: str        # "100644" or "100755"
    content: bytes

def members(root: Path, rev: str, *, exact: bool = False) -> list[Member]   # sorted by path
def manifest(entries: Iterable[Member]) -> str   # FORMAT + "\n", then "<mode> <sha256> <path>\n" per member
def render(entries: Iterable[Member], out: Path) -> None
```

CLI (the `scripts/release.py` frame: `stayfixed.cli.run`, `Result`, exit `0`/`1`/`2`, `--json`):

```text
plugin_tree.py manifest --root DIR --rev REV [--exact] [--manifest-file FILE]
plugin_tree.py render   --root DIR --rev REV --out DIR --manifest-file FILE
```

Both report `{"rev": <40-char sha>, "files": N}` as `Result.data`. `--manifest-file` receives
`manifest(...)` encoded as UTF-8, byte for byte; it is the artifact a release attests and
`publish_plugin.py` compares. Printed output goes through `cli._emit`, which adds a newline, so no
reader compares stdout.

- `members` resolves `rev` once, with `rev-parse --verify --end-of-options <rev>^{commit}`, to a
  40-character sha, and reads everything at that sha. It raises `stayfixed.errors.Refusal`:
  naming the rev, for a rev git cannot resolve to a commit; naming the path, for a `PLUGIN_PATHS`
  entry absent at that commit; naming the path and its mode, for a symlink (`120000`) or submodule
  (`160000`) under one (the directory blocks both where the plugin loads them); naming the path,
  for a path that is not UTF-8 (`fsops.utf_8_name`) or that holds a control character
  (U+0000–U+001F, U+007F); and with `exact=True`, naming the path, for any path at that commit
  outside every `PLUGIN_PATHS` entry. "Under an entry" is `path == entry or
  path.startswith(entry + "/")`.
- `manifest` sorts by path. For valid UTF-8, sorting `str` by code point, sorting by UTF-8 bytes
  and git's own full-path order coincide, and `members` refuses every other path, so the module says
  so in one sentence and no mutation of the sort key exists.
- `render` writes into `out`, which must be absent or an empty directory (else `Refusal`); every
  path goes through `fsops.checked_components`, parents through `fsops.mkdirs_within`, and each file
  through `fsops.open_within` and `os.open(name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, mode,
  dir_fd=…)` followed by `os.fchmod` to exactly `0o755` for `100755` and `0o644` for `100644` (the
  umask does not decide). It writes no manifest into the tree; the CLI writes `--manifest-file`
  last, after every member, outside `--out`.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_plugin_tree.py`, each on a scratch
  repository built with `tests.gitfixture.git` (`init -q -b main`, files with their modes,
  `add -A`, `commit`):
  - `test_members_lists_every_plugin_path_with_its_mode_and_nothing_else` — the nine paths are
    spelled out literally in the test, never read from `PLUGIN_PATHS`; the repository holds a file
    under each plus look-alike neighbours (a package `stayfixed_extra` beside `src/stayfixed`,
    `scripts/release.py`, `README.md.bak`, a directory `hooksx`) and a file under `docs/` and `tests/`; the members are exactly the
    plugin paths' files, with `hooks/run-hook.sh` and `scripts/stayfixed` at `100755`. Mutations:
    drop `"agents"` from `PLUGIN_PATHS` → expected to redden; filter with `startswith(entry)`
    without the `/` → expected to redden on the neighbours.
  - `test_members_read_the_commit_and_not_the_disk` — after the commit, edit one member on disk,
    delete another, stage a new file under `skills/`; `members(root, "HEAD")` is the commit's.
    Mutation: read `content` from `root / path` → expected to redden.
  - `test_members_at_an_older_commit_are_that_commits` — two commits; `members(root, first_sha)`
    holds the first commit's bytes.
  - `test_a_symlink_or_submodule_among_the_members_is_refused` — parametrised over a symlink under
    `skills/` and a gitlink under `src/stayfixed/` planted with `update-index --cacheinfo`; the
    refusal names the path and the mode.
  - `test_a_path_with_a_control_character_is_refused` — a file named `skills/a\nb` committed; the
    refusal names it. Mutation: drop the control-character rule → expected to redden.
  - `test_exact_refuses_a_path_outside_the_plugin` — a commit holding the plugin paths plus
    `.mcp.json`; `members(..., exact=False)` lists the plugin paths, `exact=True` refuses naming
    `.mcp.json`. Mutation: ignore `exact` → expected to redden.
  - `test_a_missing_plugin_path_is_refused_by_name` — no `LICENSE` at the commit.
  - `test_an_unresolvable_rev_is_refused_by_name`.
  - `test_the_manifest_is_one_line_per_member_in_order` — the first line equals the literal
    `"stayfixed-plugin-tree 1"` (not `module.FORMAT`), the line shape, path order, a final newline.
  - `test_the_manifest_changes_with_one_byte_and_with_one_mode` — Mutations: drop the mode from the
    line → the mode case is expected to redden; hash the path instead of the content → the byte
    case is expected to redden.
  - `test_render_writes_bytes_and_the_executable_bit` — a member holding a NUL byte, CRLF and a
    non-UTF-8 byte (`\xff`) survives byte for byte; `100755` renders as exactly `0o755` and
    `100644` as exactly `0o644` by `stat.S_IMODE`, under a umask of `0o022` and of `0o077`.
    Mutations: write with `write_text(content.decode(errors="replace"))` → expected to redden on
    `\xff`; drop the `fchmod` → expected to redden under `0o077`.
  - `test_render_refuses_a_destination_that_is_not_empty`.
  - `test_render_twice_writes_the_same_tree_and_manifest` — two renders into two directories, file
    sets and bytes equal, `manifest(members(...))` equal across runs. No mutation exists: both
    functions are stateless; the test pins determinism against a later cache.
  - `test_the_cli_writes_the_manifest_file_and_renders` — `main(["render", "--root", r, "--rev",
    "HEAD", "--out", o, "--manifest-file", m])` writes the tree, and `m`'s bytes equal
    `manifest(members(r, "HEAD")).encode()`; `main(["manifest", …, "--json"])` reports the
    40-character sha and the file count; a refusal exits `2` with its sentence on stderr.

- [ ] **Step 2: Run them; expect them to fail** on the missing module:
  `uv run pytest tests/scripts/test_plugin_tree.py -q`.

- [ ] **Step 3: Implement.** Git through `stayfixed.gitenv.git_run`; the listing is
  `ls-tree -r -z --full-tree <sha> -- <PLUGIN_PATHS…>` (no pathspec when `exact`), each record
  `"<mode> <type> <oid>\t<path>"`; a missing pathspec exits `0` silently, so absence is checked
  explicitly. Blob bytes come from one `git cat-file --batch`: `git_run(root, "cat-file", "--batch",
  stdin="".join(oid + "\n" for oid in oids))`, `gitenv.answer_bytes` on the answer, then the
  `<oid> <type> <size>\n<content>\n` framing parsed by byte offsets (as `tests/test_payload.py`
  `_blobs` does over `git_bytes`). A non-zero `code` from any call is a `Refusal` naming the command.
  Module docstring: what the plugin tree is, why it is read from a commit, that the manifest file is
  the text a release attests, and why sort order needs no mutation.

- [ ] **Step 4: Run** the module, then commit, then add `mutations/tooling.toml` entries for the
  load-bearing mutations above (a `PLUGIN_PATHS` entry dropped, the prefix filter without `/`,
  content read from disk, the control-character rule dropped, `exact` ignored, the mode dropped from
  the line, the path hashed, text writes, no `fchmod`) and prove them: `uv run python
  scripts/mutation_oracle.py plugin_tree`.

- [ ] **Step 5: Commit** — `feat(release): name the plugin's paths once and read them from a commit`.

### Task 2: Judge the generated tree, not the repository root, and pin the marketplace to the plugin repository

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `scripts/release.py` (`SOURCES`/`_parse`/`collect`, `checked_by_kind`, `plugin_folder_counts`, `TAG_HELP`, `build`)
- Modify: `tests/scripts/test_release.py`
- Modify: `tests/test_payload.py`
- Modify: `tests/test_manifests.py`
- Modify: `scripts/mutation_oracle.py` (the `GROUP_OF` comment), `tests/scripts/test_mutation_oracle.py` (`GROUP_FILE_MAX_BYTES`' comment)
- Modify: `mutations/tooling.toml`, `mutations/repository.toml`

**Interfaces:**
- Consumes: `plugin_tree.py manifest --root DIR --rev HEAD --json` (Task 1), run; `plugin_tree.members`
  and `PLUGIN_PATHS`, imported by `tests/test_payload.py` only.
- Produces: in `scripts/release.py`, `PLUGIN_URL = "https://github.com/stayfixed/stayfixed-plugin.git"`;
  `MARKETPLACE` is a version source whose value is the `stayfixed` entry's `ref` with its leading `v`
  removed (so `collect(root)[MARKETPLACE] == "0.2.0"` on this branch); `plugin_folder_counts(root)`
  is replaced by `plugin_tree_count(root) -> list[str]`.

The entry becomes, on this branch (the release commit moves `ref` with the other sources):

```json
{
  "name": "stayfixed",
  "source": { "source": "url", "url": "https://github.com/stayfixed/stayfixed-plugin.git", "ref": "v0.2.0" },
  "description": "A methodology harness for coding agents: bug ledger, curated working memory behind a trust gate, and fail-closed guards."
}
```

`v0.2.0` names no tag in the plugin repository, which does not exist yet; only a release commit's
marketplace is read by users (`README.md` installs `stayfixed/stayfixed@vX.Y.Z`, and `main` moves
only at a release), and the release commit names the version it releases. That is why the `ref` is
a version source and not a free value: one rule, holding on every commit.

**The rules.** The entry checks join the `VERSION_DRIFT` kind and replace the entry-`version`
refusal, which the new shape subsumes: exactly one entry named `stayfixed`; its `source` is an object
with `"source": "url"`, `"url"` equal to `PLUGIN_URL`, a `ref` of the form `v<X.Y.Z>`, no `sha` (the
release commit cannot know it), and no `version` on the entry. The marketplace is read by its own
branch ahead of `_parse`'s `.json` → `version` rule. "Six sources" becomes "seven" in `TAG_HELP`,
`build()`'s refusal and, in Task 5, `RELEASING.md`. `plugin_tree_count` runs `[sys.executable,
<plugin_tree.py>, "manifest", "--root", root, "--rev", "HEAD", "--json"]` through
`subprocess_runner()`, reads `files` from the JSON data, and keeps `FOLDER_COUNT` and its remedy:
"the plugin tree (scripts/plugin_tree.py) holds N files, over the 512 the plugin directory lists
unheld". A non-zero exit — git failing, a missing path, a symlink, a control character, a root
outside a checkout — is one `FOLDER_COUNT` problem quoting the first stderr line, never an exception
out of `check` ("Findings are returned, not raised"; an escaped `Refusal` would exit `2` and lose
`--json`). It runs under `--tag` as before.

- [ ] **Step 1: Write the failing tests.**
  - `tests/scripts/test_release.py` — fixtures first:
    - `MARKETPLACE` becomes a function of the version writing the `url` entry with `ref:
      "v<version>"`, and `repo()` takes a `marketplace` version beside the others (a default equal
      to `claude`'s is acceptable; `test_collect_reads_every_source_value` passes a distinct value
      and its pinned dict gains `".claude-plugin/marketplace.json"`).
    - One helper, `_with_plugin_paths(root, *, skills: int = 1)`, writes a file under each of the
      nine paths (spelled literally), `skills` files under `skills/`, and commits; every tag test
      that expects `check(root, tag=…) == []` builds on it.
    - Tests:
      - `test_the_marketplace_ref_is_a_version_source` — an entry at `v1.2.4` beside sources at
        `1.2.3` is drift naming `.claude-plugin/marketplace.json`. Mutation: leave `MARKETPLACE` out
        of the sources → expected to redden.
      - `test_a_path_source_is_refused_as_the_plugin_folder_it_used_to_be` — `"source": "./"` is a
        problem saying the plugin is published from `stayfixed/stayfixed-plugin`.
      - `test_an_entry_naming_another_repository_or_no_ref_is_refused` — parametrised: another
        `url`, a `github` source, no `ref`, a `ref` that is a branch name, a `sha` present, a
        `version` on the entry. Mutation (entry in `mutations/tooling.toml`): accept any `url` → the
        other-repository case is expected to redden.
      - `test_a_marketplace_without_the_plugin_entry_is_named` — no entry named `stayfixed`, or two.
      - `test_a_tag_refuses_a_plugin_tree_over_the_directory_count` and
        `test_a_tag_passes_a_plugin_tree_at_the_count` — the tree *totals* 513 and 512 files (the
        other eight paths' files plus `skills/` padding), beside 600 files under `docs/` that are not
        counted. Mutation: count `ls-tree HEAD` of the whole repository → the 512 case is expected to
        redden.
      - `test_a_tag_whose_plugin_tree_cannot_be_read_is_a_count_finding` — a committed symlink
        under `skills/`; one `FOLDER_COUNT` problem quoting the refusal, `check` returns rather than
        raises.
      - `test_a_tag_outside_a_git_checkout_is_refused_for_want_of_a_count` keeps its name; its
        expected sentence becomes "the plugin tree could not be counted: <first stderr line>; run the
        check in the git checkout the tag names" in place of "the plugin folder './' could not be
        counted".
    - These replace `test_a_tag_refuses_a_plugin_folder_over_the_directory_count`,
      `test_a_tag_passes_a_plugin_folder_at_the_count_whatever_the_disk_holds`,
      `test_the_count_reads_the_folder_the_marketplace_source_names` and
      `test_a_plugin_the_marketplace_fetches_from_elsewhere_is_not_counted`. Their seven
      `mutations/tooling.toml` entries are re-pointed, not deleted, where the behaviour survives:
      "stops refusing … over the count" → `…refuses_a_plugin_tree_over_the_directory_count`;
      "refuses … at the count" (`>` → `>=`) → `…passes_a_plugin_tree_at_the_count`; "counts …
      without a tag" and "reads a plugin folder git could not list as empty" →
      `…outside_a_git_checkout…` and `…cannot_be_read_is_a_count_finding`; "counts the index instead
      of HEAD" → the at-the-count test with a staged extra file; the two entries about the source
      the marketplace names go, with the behaviour. Every comment citing a removed test goes with it.
  - `tests/test_payload.py`: `tracked_payload(root)` becomes the members of `HEAD`
    (`(path, len(content), mode)` and `{path: content}`) through `plugin_tree.members`, so the rules
    judge the generated tree; `FILE_MAX_BYTES` stays a module constant (`test_mutation_oracle`
    imports it). `test_the_plugin_folder_is_the_repository_root` is replaced by
    `test_the_payload_is_the_generated_plugin_tree`: the marketplace entry is the `url` source of
    `release().PLUGIN_URL`, and every walked path is `== p or startswith(p + "/")` for a `p` among
    the nine spelled literally. Mutation: walk `git ls-tree -r HEAD` of the root → expected to
    redden. `test_the_tree_is_inside_the_directory_limits` asserts `payload_findings(...) == []`, the
    count included; its count half cannot fail today (218 ≤ 512), and the docstring says
    `test_one_file_past_the_count_is_a_finding` carries the rule. `findings_but_the_count` and its two
    tests go, with their entries. `test_the_walk_reads_the_committed_tree_and_not_the_disk` is rebuilt
    on a scratch repository carrying the plugin paths and keeps three observations — an edit, a
    deletion, a staged file; the symlink and gitlink cases go, because they are `members`' refusals
    now (Task 1's test) and `payload_findings`' own symlink and gitlink rules keep their unit tests.
    Module docstring rewritten: the payload is the generated tree, why, that the count is held on
    every pull request, and that `docs/cli.md` and every file outside the plugin paths are no longer
    judged, by the owner's decision of 2026-10-10.
  - `tests/test_manifests.py::test_marketplace_has_a_description_and_an_unversioned_entry` pins the
    `url` source and `ref == "v" + <plugin.json version>`, with a `mutations/repository.toml` entry
    (the `ref` one patch ahead).

- [ ] **Step 2: Run them; expect them to fail**:
  `uv run pytest tests/scripts/test_release.py tests/test_payload.py tests/test_manifests.py -q`.

- [ ] **Step 3: Implement** the rules above. Edit the entry in `.claude-plugin/marketplace.json`.
  Rewrite the comments the change falsifies, in the same commit: `scripts/mutation_oracle.py`'s
  `GROUP_OF` comment and `tests/scripts/test_mutation_oracle.py`'s `GROUP_FILE_MAX_BYTES` comment say
  that the groups and the cap were sized while the repository root was the plugin, that the plugin
  tree no longer holds `mutations/`, and that the table and the cap stay until the follow-up decides
  (Findings); no value changes. Update `RELEASING.md` section 1's table only where
  `tests/test_documents.py` holds it; the prose is Task 5's.

- [ ] **Step 4: Run** the three modules, then `uv run python scripts/release.py check` (prints one
  version everywhere: `0.2.0`), then commit and prove the named mutations with the oracle.

- [ ] **Step 5: Commit** — `fix(release): judge the generated plugin tree and pin the marketplace to the plugin repository`.

## Wave B — Task 3

### Task 3: Validate, install and attest the rendered tree in CI

**Files:**
- Modify: `.github/workflows/ci.yml` (job `plugin`)
- Modify: `.github/workflows/smoke.yml` (job `installed-plugin`)
- Modify: `.github/workflows/release.yml` (jobs `build`, `github-release`)
- Modify: `tests/test_check_workflow.py`, `tests/test_fixtures.py`
- Modify: `mutations/tooling.toml`

**Interfaces:**
- Consumes: `scripts/plugin_tree.py render --root . --rev REV --out DIR --manifest-file FILE`
  (Task 1); the marketplace name `stayfixed-marketplace`, the entry name `stayfixed` and its `url`
  source shape (Task 2).

What each job does:

- **`ci.yml` `plugin`**: add `astral-sh/setup-uv` at `release.yml`'s pinned sha; after the existing
  install of `@anthropic-ai/claude-code@2.1.261`, render `HEAD` into `$RUNNER_TEMP/plugin`, then
  `claude plugin validate "$RUNNER_TEMP/plugin/.claude-plugin/plugin.json" --strict`, `claude plugin
  validate "$RUNNER_TEMP/plugin/.codex-plugin/plugin.json"`, and `claude plugin validate
  .claude-plugin/marketplace.json --strict` (this repository's catalog, which validation reads
  without fetching). `claude plugin tag --dry-run .` stays, and its comment is corrected to what the
  tool compares (it checks `plugin.json` against marketplace entries that carry a version, and this
  entry carries none); this push is the first measurement of it beside a `url` entry, and the PR body
  records its output, because `RELEASING.md` step 6 runs the same tool.
- **`smoke.yml` `installed-plugin`**: add `astral-sh/setup-uv` at the same sha. Replace `claude
  plugin marketplace add "$PWD"` by a rehearsal of the release's shape, with no network: render
  `HEAD` into `$RUNNER_TEMP/plugin-repo`, make it a git repository with one commit (`git -c
  user.email=… -c user.name=…`, as `scripts/smoke_hooks.py` commits) and the tag `v<version>`
  (version read from `.claude-plugin/plugin.json` with `python3 -c`), write
  `$RUNNER_TEMP/market/.claude-plugin/marketplace.json` naming `stayfixed-marketplace` with one
  entry `stayfixed` whose source is `{"source": "url", "url": "file://$RUNNER_TEMP/plugin-repo",
  "ref": "v<version>"}` — production's source type, over another transport — then `claude plugin
  marketplace add "$RUNNER_TEMP/market"` and `claude plugin install
  stayfixed@stayfixed-marketplace`. The `doctor` step's `PYTHONPATH` becomes the installed root's
  `src` (`${{ steps.install.outputs.root }}/src` in its `env:`), so `doctor` reports on the
  installed tree. A new step holds the install to the render: `diff -r -x .git
  "$RUNNER_TEMP/plugin-repo" "$INSTALLED"`; a red first run naming files the install adds is
  recorded and those names excluded one by one, each with the measurement in a comment. Every other
  step is unchanged and now runs against a tree installed from a tagged git repository, as users
  get it.
- **`release.yml` `build`**: after `uv build`, render the commit the workflow runs on:
  `uv run python scripts/plugin_tree.py render --root . --rev "$GITHUB_SHA" --out
  "$RUNNER_TEMP/plugin" --manifest-file "$RUNNER_TEMP/plugin-tree.txt"` (`GITHUB_SHA` is the
  attestation's source digest, so the render, the source digest `publish_plugin.py` passes and the
  attested commit are one value), attest `$RUNNER_TEMP/plugin-tree.txt` with the same pinned
  `attest-build-provenance` (a second step; the `dist/*` one stays), and upload it as the artifact
  `plugin-tree`. **`github-release`** downloads `plugin-tree` and attaches `plugin-tree.txt` to the
  Release beside `dist/*`, so anyone can compare the plugin repository's tag against it.

- [ ] **Step 1: Write the failing tests** in `tests/test_check_workflow.py`, reading the workflows
  through `tests.workflow_yaml` as the module already does:
  - `test_the_smoke_installs_the_rendered_tree_and_never_the_checkout` — `installed-plugin` runs
    `scripts/plugin_tree.py render`, and every `claude plugin marketplace add` argument starts with
    `"$RUNNER_TEMP/` (an allowlist: `"$PWD"`, `${PWD}`, `$(pwd)`, `.`, `./` and
    `$GITHUB_WORKSPACE` all fail it). Mutation: restore `claude plugin marketplace add "$PWD"` →
    expected to redden.
  - `test_the_smoke_runs_doctor_from_the_installed_tree` — the `doctor` step's `env:` `PYTHONPATH`
    is the install step's `root` output plus `/src`. Mutation: `PYTHONPATH: src` → expected to
    redden.
  - `test_the_smoke_holds_the_install_to_the_render` — a step diffs the render against
    `$INSTALLED`. Mutation: delete the step → expected to redden.
  - `test_the_validator_reads_the_rendered_manifests` — the `plugin` job's validator arguments are
    parsed out of the step, and each `plugin.json` argument starts with the render's `--out`.
    Mutation: validate `.claude-plugin/plugin.json` → expected to redden.
  - `test_the_release_attests_the_plugin_tree_it_rendered_from_the_commit` — `build` renders with
    `--rev "$GITHUB_SHA"`; one `attest-build-provenance` step's `subject-path`, with `${{ runner.temp
    }}` read as `$RUNNER_TEMP`, is the render's `--manifest-file`, at the same pinned sha as the
    `dist/*` one; `github-release` attaches the file. Mutation: drop the second attestation step →
    expected to redden. The `--rev "$GITHUB_SHA"` assertion is a text pin with no behavioural
    mutation (on a tag push `HEAD` is that commit); its sentence says so, and it gets no
    `mutations/` entry.
  - `tests/test_fixtures.py::test_no_workflow_splices_an_expression_into_a_shell` already covers
    the three files; it must stay green.

- [ ] **Step 2: Run them; expect them to fail**:
  `uv run pytest tests/test_check_workflow.py tests/test_fixtures.py -q`.

- [ ] **Step 3: Edit the three workflows.** Comments in the files' existing voice say why: the
  directory reads the plugin repository's commit, so CI validates and installs what that commit
  will hold, runs `doctor` from it, and attests the manifest `publish_plugin.py` checks.

- [ ] **Step 4: Run** the two modules, commit, prove the named mutations with the oracle, and push
  the branch once so `ci` and `smoke` run on GitHub; paste both runs' results and the `claude plugin
  tag --dry-run` output. A red smoke on the `url` source over `file://` stops the wave and is
  reported, not worked around.

- [ ] **Step 5: Commit** — `ci: validate, install and attest the rendered plugin tree`.

## Wave C — Task 4

### Task 4: `publish_plugin.py`: push an attested tree to the plugin repository, and nothing else

**Files:**
- Create: `scripts/publish_plugin.py`
- Create: `tests/scripts/test_publish_plugin.py`
- Modify: `tests/scriptload.py` (add `publish_plugin()`)
- Modify: `mutations/tooling.toml`

**Interfaces:**
- Consumes: `plugin_tree.py render` and `manifest --exact --manifest-file` (Task 1), run;
  `stayfixed.runner.Runner`, `subprocess_runner`; `stayfixed.gitenv.git_run`, `answer_bytes`;
  `stayfixed.release.api.tag_for`.
- Produces:

```python
PLUGIN_REMOTE = "git@github.com:stayfixed/stayfixed-plugin.git"
SIGNER_WORKFLOW = "stayfixed/stayfixed/.github/workflows/release.yml"
SOURCE_REPOSITORY = "stayfixed/stayfixed"

@dataclass(frozen=True)
class Published:
    tag: str
    files: int
    commit: str        # the plugin repository's new commit, or the one already tagged
    pushed: bool
    already: bool      # the remote's tag and main already name a commit holding exactly this manifest

def publish(root: Path, tag: str, *, remote: str, yes: bool, runner: Runner, scratch: Path) -> Published
```

CLI: `uv run python scripts/publish_plugin.py --tag vX.Y.Z [--remote URL] [--yes]`; `scratch` is a
`tempfile.TemporaryDirectory` in the CLI and `tmp_path` in tests.

**Two ways to run git, on purpose.** Everything that reaches the remote (`ls-remote`, `fetch`,
`push`), `gh`, and `plugin_tree.py` run through `runner`, which keeps the owner's environment (the
SSH agent the push needs). Every local object write (`init`, `hash-object`, `mktree`,
`commit-tree`) runs through `gitenv.git_run` in a scratch bare repository: `Runner` closes stdin,
which `mktree` needs, and drops `GIT_INDEX_FILE`, so no temporary index is available either.

The order, each step refusing (`Refusal`, exit `2`) before the next runs:

1. `re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag)`; resolve `refs/tags/<tag>^{commit}` once with
   `rev-parse --verify --end-of-options` to a 40-character sha (a branch of that name cannot stand
   in); the version in `.claude-plugin/plugin.json` at that sha (`git show <sha>:…`) gives
   `tag_for(version)[0] == tag`. Every later step uses the sha, never the tag name.
2. Run `plugin_tree.py render --root <root> --rev <sha> --out <scratch>/tree --manifest-file
   <scratch>/plugin-tree.txt`; a non-zero exit is a refusal quoting its stderr.
3. `gh attestation verify <scratch>/plugin-tree.txt --repo stayfixed/stayfixed --signer-workflow
   stayfixed/stayfixed/.github/workflows/release.yml --source-ref refs/tags/<tag> --source-digest
   <sha> --deny-self-hosted-runners`. A non-zero exit is a refusal quoting gh's stderr verbatim
   (first lines) and saying that this tree is not one a release of this tag attested *or* that gh
   could not check (unauthenticated, offline) — it asserts no cause gh did not state.
4. `git init --bare --quiet <scratch>/plugin.git`; `git ls-remote <remote> refs/heads/main
   refs/tags/<tag>` (exact refs, never a suffix). If the tag is present: fetch `refs/tags/<tag>`
   explicitly into `plugin.git`; run `plugin_tree.py manifest --exact --root <scratch>/plugin.git
   --rev <its sha> --manifest-file <scratch>/remote-tree.txt`. Its bytes equal step 2's *and*
   `main` names the same commit → `Published(already=True, pushed=False)`, stop. Otherwise a
   refusal: `--exact`'s sentence (a path outside the plugin), or the first differing manifest line,
   or "the tag holds this tree but `main` is at <sha>".
5. If `main` is present, fetch `refs/heads/main` explicitly into `plugin.git`; it is the parent.
   An empty remote gives a root commit.
6. Build the commit with plumbing in `plugin.git`: `hash-object -w --no-filters -- <file>…` over
   the rendered files in manifest order; the modes from the manifest file's own lines (the attested
   bytes); one `mktree -z` per directory, deepest first, through `git_run(stdin=…)`; `commit-tree
   <tree> [-p <parent>] -m "stayfixed X.Y.Z" -m "Generated from stayfixed/stayfixed at <sha>
   (<tag>) by scripts/publish_plugin.py."`. The author is the owner's own git identity; a missing
   one is git's sentence, quoted.
7. Read back: `plugin_tree.py manifest --exact --root <scratch>/plugin.git --rev <new commit>
   --manifest-file <scratch>/readback.txt`; bytes equal step 2's, else refusal and nothing pushed.
8. Without `yes`: `Published(pushed=False)` and a plan line ("would push N files as <commit> to
   <remote>: main and <tag>"). With `yes`: `git -C <scratch>/plugin.git -c core.hooksPath=/dev/null
   push --atomic --quiet <remote> <commit>:refs/heads/main <commit>:refs/tags/<tag>` (the tag is
   lightweight). A rejection — `main` moved since step 5, a ruleset — is a refusal quoting git, and
   `--atomic` leaves every remote ref where it was.

Unlike `overlay publish-template`, which runs only `gh repo view` without `--yes`, this builds and
reads back its commit before the gate, on purpose: everything before step 8 is local to `scratch`,
and the dry run's answer is the commit that would be pushed.

The tests' runner is a composite defined in the test module: it appends every argv to its own
`calls` list before dispatching, answers argv starting with `gh` from a `Recorder`, and sends the
rest to `subprocess_runner()`. Each test writes `user.name` and `user.email` into its `HOME`'s
`.gitconfig`.

- [ ] **Step 1: Write the failing tests** (a scratch source repository with the nine paths and a
  tag `v1.2.3` whose `plugin.json` says `1.2.3`; a bare repository in `tmp_path` as the remote):
  - `test_a_verified_tree_is_pushed_with_its_tag_and_reads_back_whole` — with `yes=True`, the
    remote's `main` and `v1.2.3` name one commit, `plugin_tree.members(remote, "v1.2.3",
    exact=True)` matches the source tag's, and the executable bits survive. Mutation: take every
    mode as `100644` in step 6 → expected to redden (through the read-back's refusal first; the test
    asserts that refusal's sentence, which names the reason).
  - `test_without_yes_the_remote_is_unchanged` — `git ls-remote` of the bare remote is empty after
    the run; the reported commit equals `rev-parse` of that commit in `<scratch>/plugin.git`, not a
    literal. Mutation: `if yes` → `if True` → expected to redden.
  - `test_a_refused_attestation_stops_before_anything_is_fetched` — `gh attestation verify`
    answers `1` with a stderr line; no `ls-remote`, `fetch` or `push` appears in the composite's
    `calls`, `<scratch>/plugin.git` does not exist, the remote has no refs, and the refusal quotes the
    stderr line. Mutation: ignore the verify exit code → expected to redden.
  - `test_the_attestation_is_asked_for_this_workflow_this_tag_and_this_commit` — the recorded `gh`
    argv holds `--repo stayfixed/stayfixed`, `--signer-workflow
    stayfixed/stayfixed/.github/workflows/release.yml`, `--source-ref refs/tags/v1.2.3`,
    `--source-digest <the tag's 40-char sha>` and `--deny-self-hosted-runners`, and its file's bytes
    are the render's manifest file. Mutations, one entry each: drop `--source-ref`; drop
    `--source-digest`; drop `--deny-self-hosted-runners`; drop `--signer-workflow`.
  - `test_the_tree_is_rendered_from_the_tag_and_not_the_disk` — an uncommitted edit to a member
    is not in what is pushed.
  - `test_a_branch_named_like_the_tag_does_not_stand_in_for_it` — a branch `v1.2.3` on another
    commit; the pushed tree is the tag's.
  - `test_a_second_publish_of_the_same_tag_pushes_nothing` — two runs with `yes=True`; the second
    returns `already=True`, the remote's refs are unchanged, and the second run's `calls` still hold
    `gh attestation verify` before `ls-remote`.
  - `test_a_remote_commit_holding_a_path_outside_the_plugin_is_not_already_published` — the remote's
    `v1.2.3` and `main` name a commit holding exactly the manifest plus `.mcp.json`; refusal naming
    `.mcp.json`, nothing pushed. Mutation: `--exact` dropped from step 4 → expected to redden.
  - `test_a_tag_on_the_remote_with_another_tree_is_refused` — refusal naming the first differing
    line, nothing pushed. Mutation: treat a present remote tag as absent → expected to redden.
  - `test_a_tag_on_the_remote_whose_main_is_elsewhere_is_refused` — same tree, `main` on another
    commit.
  - `test_the_commit_ignores_the_owners_line_ending_and_hook_configuration` — the test `HOME`'s
    `.gitconfig` sets `core.autocrlf=true`, `core.hooksPath` to a directory whose `pre-push` exits
    `1`, and a global excludes file listing `*.md`; a member with CRLF and `README.md` are pushed
    byte for byte. Mutation: drop `--no-filters` → expected to redden (through the read-back);
    drop `-c core.hooksPath=/dev/null` → expected to redden.
  - `test_a_rejected_push_moves_no_ref` — the bare remote's `update` hook rejects
    `refs/tags/*`; refusal quoting git, and `main` is still absent. Mutation: drop `--atomic` →
    expected to redden.
  - `test_an_unknown_tag_is_refused_before_anything_runs` and
    `test_a_tag_whose_version_is_another_is_refused` and
    `test_a_tag_that_is_not_a_plain_version_is_refused` (parametrised: `v1.2.3\n`, `v1.2.3-rc1`,
    `v١.2.3`) — the composite's `calls` are empty.
  - `test_the_previous_release_is_replaced_whole` — a remote whose `main` holds an extra skill the
    tag no longer has; after the push that skill is gone, and the new commit's parent is the earlier
    `main`.

- [ ] **Step 2: Run them; expect them to fail**:
  `uv run pytest tests/scripts/test_publish_plugin.py -q`.

- [ ] **Step 3: Implement** `publish` and the CLI. The docstring says what it trusts and why: the
  attestation binds the manifest's bytes to this repository's `release.yml`, at this tag and this
  commit, on a GitHub-hosted runner; the owner's checkout only renders, builds and compares; the
  commit is built from the attested modes and the rendered bytes with no working tree, so the
  owner's filters and hooks never touch it; CI holds no credential to the plugin repository.

- [ ] **Step 4: Run** the module, commit, prove the named mutations with the oracle.

- [ ] **Step 5: Commit** — `feat(release): publish the attested plugin tree to its own repository`.

## Wave D — Task 5

### Task 5: Restate the release, the install and the contribution guide

**Files:**
- Modify: `RELEASING.md`, `README.md`, `CONTRIBUTING.md`
- Modify: `tests/test_documents.py`
- Create: `changelog.d/+plugin-repository.change.md`

Every edit stays clear of plan vocabulary (`tests/test_public_anchors.py`) and leaves the pinned
step-1 block (`tests/test_fixtures.py` `_RELEASE_BLOCK`) intact.

- [ ] **Step 1: `RELEASING.md`.**
  - The opening sequence gains the plugin's push between `build` and the `pypi` approval.
  - Section 1: `.claude-plugin/marketplace.json` is a source — the entry's `ref`, `vX.Y.Z` — and
    the sentence calling it "checked for consistency rather than for a number" goes; "six sources"
    becomes seven, and every count that follows from it moves with it: `:3`, step 3's "four
    places you edit by hand" (five, with the `ref`), `:116-117` ("four of the six", "the fifth", "the
    sixth"), `:213` and `:421`; the paragraph saying a tag refuses "a plugin
    folder holding more than 512 files" says the plugin tree.
  - Section 2: the paragraph "If the tree holds more than 512 files, publish the plugin from a
    repository of its own first" is replaced by one saying the plugin is published from
    `stayfixed/stayfixed-plugin`, generated by `scripts/plugin_tree.py`, and that the count is the
    generated tree's, held on every pull request. Step 3 lists the marketplace `ref` among the
    places set by hand. Step 7 becomes: watch `build` (not the whole run); once it is green, the
    plugin's attestation exists, and before approving `pypi`:

    ```bash
    uv run python scripts/publish_plugin.py --tag vX.Y.Z          # verify, build, read back, plan
    uv run python scripts/publish_plugin.py --tag vX.Y.Z --yes    # push main and the tag
    ```

    then approve `pypi`, then move `main` as today. Say why the plugin goes first (the release
    commit's marketplace names a tag that exists only once this has run, and the approval is what
    makes the PyPI page and the Release public) and what a refusal means (the tree is not one CI
    attested for this commit, or gh could not check: reject the `pypi` approval and do not work
    around it).
  - Section 3 gains **The plugin repository**: create `stayfixed/stayfixed-plugin` public and
    empty, the description, and a ruleset with `deletion` and `update` rules over `refs/tags/v*.*.*`
    and a `creation` rule over `refs/heads/v*` (so no branch can shadow a tag), by the same
    create-or-replace script section 3 already gives for this repository, with the repository name
    changed, followed by the same read-back of the ruleset that section 3 gives this repository's,
    before the first `publish_plugin.py --yes`.
  - Section 5: a refused or failed plugin push leaves `main` and the `pypi` approval where they are;
    a pushed plugin tag is spent like this repository's.
  - Section 6: `scripts/plugin_tree.py` `manifest` and `render`, and `scripts/publish_plugin.py`,
    each in two sentences; `check`'s paragraph counts the plugin tree, not "each folder the
    marketplace entries' `source` names".
- [ ] **Step 2: `README.md`.** The Install section keeps both lines `tests/test_documents.py` holds
  and gains one sentence: the marketplace here fetches the plugin from `stayfixed/stayfixed-plugin`
  at the release's tag. Every relative link to a file outside the nine plugin paths becomes an
  absolute link to `https://github.com/stayfixed/stayfixed/blob/main/<path>` (anchors kept); links
  to `skills/README.md` and `LICENSE` stay relative. `main` moves only at a release, so those links
  show the latest release's documents, in the plugin repository, on PyPI and here alike.
  `tests/test_documents.py` gains `test_the_readme_links_only_inside_the_plugin_or_absolutely`:
  every relative link target resolves under one of the nine paths (spelled literally). Mutation
  (`mutations/repository.toml`): restore `](docs/cli.md)` → expected to redden.
- [ ] **Step 3: `CONTRIBUTING.md`**: where it describes the payload guard or the plugin folder, say
  the guard judges the generated tree, and that a file the runtime needs outside `PLUGIN_PATHS` must
  be added there; the paragraph on `GROUP_OF`'s coarse groups drops "every tracked file counts" and
  says, as the Task 2 comments do, that the grouping stays until the follow-up decides.
- [ ] **Step 4: The fragment**, `+plugin-repository.change.md`: the plugin is now installed from
  `stayfixed/stayfixed-plugin`, a repository holding only what runs, at the release's tag, and the
  install commands do not change. Task 6's Step 3 adds what each existing install must do; until it
  has run, say nothing about upgrades.
- [ ] **Step 5: Run** `uv run pytest tests/test_documents.py tests/test_manifests.py
  tests/test_fixtures.py tests/test_public_anchors.py -q` and the plan check.
- [ ] **Step 6: Commit** — `docs: release the plugin from its own repository`.

## Wave E — Task 6 (controller-run)

### Task 6: Rehearse the release's shape with the real CLI

Scratch only, under the controller's scratchpad; nothing is pushed anywhere (`gh attestation
verify` does read GitHub's API). Record the installed `claude` version (2.1.296 on 2026-10-10) and
run each step with it; where a step's outcome could depend on the version, run it again with the
pin, `npx --yes @anthropic-ai/claude-code@2.1.261`, and record both.

- [ ] **Step 1: Validate the rendered tree.** `uv run python scripts/plugin_tree.py render --root .
  --rev HEAD --out <s>/tree --manifest-file <s>/plugin-tree.txt`; `claude plugin validate
  <s>/tree/.claude-plugin/plugin.json --strict`; record the output and the file count.
- [ ] **Step 2: Install from a tagged scratch repository.** As the smoke does, under a temporary
  `CLAUDE_CONFIG_DIR`; run `scripts/smoke_hooks.py` against the installed root and `doctor` with
  `PYTHONPATH` at the installed `src`; record the summary lines, and whether the install adds files
  the render does not hold.
- [ ] **Step 3: The two upgrade populations.** Build a scratch plugin repository whose
  `plugin.json` is bumped to `0.2.1` and committed before tagging `v0.2.1` (an equal version would
  not replace the cache, so it could not show an upgrade). From a `git worktree add <s>/v020
  v0.2.0` scratch marketplace:
  - **Unpinned** (fresh `CLAUDE_CONFIG_DIR`): add the marketplace from `<s>/v020`, install
    `stayfixed`; change that marketplace's entry to the `url` source at `v0.2.1`; run `claude plugin
    marketplace update stayfixed-marketplace` and `claude plugin update
    stayfixed@stayfixed-marketplace`.
  - **Pinned** (fresh `CLAUDE_CONFIG_DIR`): the same install; then a second scratch marketplace at
    the new shape, standing for `@v0.2.1`; remove and re-add the marketplace from it, as a user
    who added `stayfixed/stayfixed@vX.Y.Z` would, and update or reinstall.
  - For each, record what every command printed, the `installPath` that
    `$CLAUDE_CONFIG_DIR/plugins/installed_plugins.json` names afterwards, the version there, and
    whether the hooks run from it. What an existing install must do goes into Task 5's fragments,
    as `+plugin-repository.upgrading.md`.
- [ ] **Step 4: `publish_plugin.py` against a scratch remote.** Record `gh attestation verify
  --help` (the `--source-digest` flag). `git init --bare <s>/remote.git`; run `publish_plugin.py
  --tag v0.2.0 --remote <s>/remote.git` without `--yes`; record the refusal verbatim and which
  failure it was (a path absent at `v0.2.0`, no attestation of `v0.2.0`'s plugin manifest, or gh
  unauthenticated or offline), and that the remote is empty afterwards.
- [ ] **Step 5: Record** Steps 1–4 in Findings, with both `claude` versions and each command's
  output, and commit — `docs(plans): record the plugin repository rehearsal`.

## Findings

Written by Task 6 and by the pull request's review.

### Pre-dispatch review (2026-10-10)

A final review read this plan against `d1a18d4` through the premise, oracle and boundary lenses plus
architecture and simplification, and judged it not ready to dispatch. Every finding that names the
tree was re-checked before it was acted on; all were taken into the text above. The blocking ones:
"already published" compared only the plugin paths, so a remote commit with an extra `.mcp.json`
passed (now `--exact` over the whole commit, and `main` must name it); the attestation was bound to a
tag name, not its commit (now `--source-digest` and a render from `$GITHUB_SHA`); the commit was
built through a working tree under the owner's git configuration (now plumbing in a bare repository);
the tag and the PyPI page went public before the plugin push (now `build` → plugin → approval →
`main`); the smoke's `doctor` judged the checkout (now the installed `src`); the upgrade rehearsal
installed and upgraded one version (now `0.2.1`, two populations); three `publish` assertions
could not fail because `git` bypassed the `Recorder` (now a composite that records every argv); no
git identity reached a test's `git_run` (the review proposed environment variables, which `git_run`
drops; the tests write `HOME`'s `.gitconfig`); `test_release.py`'s fixtures and the count tests'
mutation entries were under-stated; neither CI job that runs the script had `uv`; a sort mutation
could not redden on any accepted tree. Structural changes: `publish` moved to
`scripts/publish_plugin.py`, and no script imports another — `release.py` and the publisher run
`plugin_tree.py`; Task 4 became its own wave. The owner settled four questions (Spec paragraph):
the `url` source, one tag, `docs/cli.md`'s cap retired, absolute README links.

Follow-ups, to file when the pull request closes:

- The private design's §5.9 says the 512 count runs at a release, not at every pull request; this
  plan holds it on every pull request. Amend §5.9, as wave 8's outcome was recorded in §15.7.
- `overlay publish-template` (`src/stayfixed/overlay/publish.py` `_replace_tree`) is a second
  "replace a remote repository's tree whole" implementation beside `publish_plugin.py`, and writes
  through a working tree under the owner's git configuration (autocrlf, excludes, LFS, hooks) — the
  defect class this plan's plumbing avoids. When the runtime unfreezes, one plumbing primitive should
  serve both.
- The plugin is bound to its release by a tag name in a second repository (`ref` without `sha`,
  unavoidable while the release commit precedes the plugin commit); the only after-the-fact check is
  `plugin-tree.txt` on the Release. `doctor`'s docstring names "the pinned SHA" as an anchor the
  plugin path no longer has.
- Whether `GROUP_OF`'s hand-kept table and `GROUP_FILE_MAX_BYTES` still earn their keep now that
  the plugin tree holds no `mutations/` file.
- Codex's install path for a `url` source is unmeasured.
- How an install made from the marketplace on GitHub (`stayfixed/stayfixed`, `@vX.Y.Z` or the
  default branch) moves to the plugin repository: the rehearsal below measured directory
  marketplaces, because `claude plugin marketplace add` takes no `file://` git URL.
- The `gh` commands `RELEASING.md` gives for the plugin repository's creation, its rulesets and
  their read-back have not been run; the first release runs them.

### The release's shape, rehearsed with the real CLI (2026-10-11)

Run by the controller under scratch directories, with the installed `claude` 2.1.296 and the
pinned 2.1.261 (through `npx`); every step gave the same result on both. Nothing was pushed
anywhere; `gh attestation verify` read GitHub's API once.

- **The rendered tree validates.** `plugin_tree.py render --rev 7b18007` wrote 218 files.
  `claude plugin validate .claude-plugin/plugin.json --strict` passed; the Codex manifest passed
  with one warning, "Unknown field 'interface'. Claude Code ignores it at load time."
- **An install from a tagged plugin repository is the rendered tree.** A `url` source over
  `file://`, pinned by `ref: v0.2.0`, installed under a temporary `CLAUDE_CONFIG_DIR`. The installed
  root differs from the render by one file, `.in_use`, which the harness writes there (the first CI
  run of this pull request measured the same on `macos-latest` and `ubuntu-latest`, and the smoke
  now excludes it by name). From the installed root: `smoke_hooks.py` printed "9 entries, 10 row(s),
  0 failure(s)"; `doctor` with `PYTHONPATH` at the installed `src` reported 17 rows, none red;
  `smoke_exfiltration.py` printed "9 row(s), 0 failure(s)".
- **Both upgrade populations move.** A scratch plugin repository at `0.2.1` (the rendered tree with
  both manifests bumped, committed, tagged `v0.2.1`), and marketplaces holding `v0.2.0`'s tree.
  `claude plugin marketplace add` takes `owner/repo`, an `https://` URL or a path — not a `file://`
  git URL — so the marketplaces were directories, and the GitHub transport of the marketplace
  itself is not reproduced here.
  - *Following the default branch:* `v0.2.0` installed from `./`; the marketplace's entry replaced in
    place by the `url` source at `v0.2.1`; `claude plugin marketplace update stayfixed-marketplace`
    then `claude plugin update stayfixed@stayfixed-marketplace` printed "Plugin "stayfixed" updated
    from 0.2.0 to 0.2.1". `installed_plugins.json` named `…/stayfixed/0.2.1` as `installPath`, its
    manifest said `0.2.1`, and the hooks ran from it (9 entries, 10 rows, 0 failures).
  - *Added at a release tag:* `marketplace update` and `plugin update` alone stay at `0.2.0` ("already
    at the latest version"). Adding the new release's marketplace over the registered one printed
    "was already added from … and now points at …. Plugins already installed from it now update
    from the new source", and `plugin update` then moved to `0.2.1`. `claude plugin marketplace
    remove` instead uninstalls the plugin and "deletes their saved options, secrets and data where
    it can"; after re-adding, `plugin update` refuses ("is not installed") until `plugin install`.
  - The `upgrading` fragment says both paths, and that removing is not needed.
  - The `0.2.0` trees were judged by `v0.2.0`'s own `smoke_hooks.py` (13 entries, 14 rows, 0
    failures); the current script does not apply to an older tree.
- **`publish_plugin.py` refuses a tree no release attested.** `gh` 2.101.0 lists `--source-digest`
  ("Enforce that the digest associated with the source repository matches the provided value").
  `publish_plugin.py --tag v0.2.0 --remote <bare>` without `--yes` rendered `v0.2.0` (all nine paths
  are present there) and refused at the attestation: "gh attestation verify exited 1: 'Error: HTTP
  404: Not Found (…/attestations/sha256:ec6f2c5…)'. Either no release of v0.2.0 at efd4b6d… attested
  this tree, or gh could not check; nothing was fetched or pushed"; exit 2, and the bare remote held
  no ref afterwards.
- **`claude plugin tag --dry-run .` beside the `url` entry** (CI, 2.1.261): "Version: 0.2.0 (from
  plugin.json)", the entry found as `plugins[0]`, "would create tag stayfixed--v0.2.0 at HEAD".
