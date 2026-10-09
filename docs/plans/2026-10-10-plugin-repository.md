# The plugin published from a repository of its own: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **The wave is the dispatch unit, not the task.** Waves are lettered (`A`, `B`, `C`) and own a
> run of the continuously numbered tasks. One implementer, one review round and one reviewer per
> **dispatched** wave; inside a wave every task keeps its own failing test, verification and
> commit. Do not dispatch one subagent per task.
>
> **Task 6 is not dispatched.** It runs the real `claude` CLI against scratch repositories and
> records what it measures; the controller runs it.
>
> **One pull request** (`wp/plugin-repository`), waves in order on one branch, rebased on `dev`
> before every push. Every dispatched seat runs on Opus.

**Goal:** publish the Claude Code plugin from `stayfixed/stayfixed-plugin`, a repository whose
root is a tree generated from this one, so that `0.3.0` can be released: the directory's file
rules judge that tree, CI builds and tests it on every pull request, the release workflow attests
its manifest, and the owner pushes it with one command that refuses a tree the attestation does
not vouch for.

**Architecture:** one stdlib script, `scripts/plugin_tree.py` (create), names the plugin's paths
once and reads them from a commit's tree, never from the disk: `members` lists them with their
modes and blobs, `manifest` is the text a release attests (one line per file: mode, sha256, path),
`render` writes the tree out, and `publish` checks the attestation, replaces the plugin
repository's tree whole, tags it and pushes only with `--yes`. Every guard that judged "the
plugin folder" now judges `members`: the payload test, the release check's file count, the CI
validator, the install smoke. The marketplace entry here becomes a `github` source pinned to the
tag, and its `ref` joins the version sources `scripts/release.py check` holds equal.

**Tech Stack:** Python ≥ 3.11 standard library; `uv`, pytest (`-n auto`), ruff, mypy, the mutation
oracle (`scripts/mutation_oracle.py`), towncrier fragments in `changelog.d/`; GitHub Actions with
`actions/attest-build-provenance` (already pinned in `release.yml`); `gh attestation verify` on the
owner's machine; the `claude` CLI 2.1.261 in CI (the version `ci.yml` and `smoke.yml` pin).

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
plan creates or pushes to it.

**Scope:** the step that `docs/plans/2026-10-04-wave-8-core-cut.md`, Task 17 Step 3, left open, as
its own pull request. A change belongs to this plan iff it (a) generates, counts, renders or
publishes the plugin tree; (b) moves a guard that judged the repository root as the plugin folder
onto the generated tree; (c) points the marketplace entry at the plugin repository, or holds that
entry to the release's version; (d) builds, tests or attests the generated tree in a workflow; (e)
restates the documents those changes falsify (`RELEASING.md`, `README.md`, `CONTRIBUTING.md`,
fragments); or (f) records Task 6's measurements in this plan's Findings. Out: the `0.3.0` release
itself (version strings, `CHANGELOG.md`, tags), which the owner cuts by `RELEASING.md` after this
merges; creating `stayfixed/stayfixed-plugin` or its ruleset; Codex's install path for a `github`
source (unmeasured, recorded in Findings); the directory submission; any command, flag or
configuration key in the shipped CLI.

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
  `sys.path`; `doctor`'s `_own_root` (`src/stayfixed/doctor/checks.py`) is
  `Path(stayfixed.__file__).parents[2]` and needs `hooks/run-hook.sh` there; presets, profiles and
  templates are package resources under `src/stayfixed/`. No runtime code and no skill reads
  `docs/`, `CHANGELOG.md`, `pyproject.toml`, `RELEASING.md` or `uv.lock`.
- **Five runtime uses of `REPOSITORY_URL`/`REPOSITORY_SLUG` mean this repository and stay:**
  `src/stayfixed/doctor/checks.py` (`cli-path` remedy), `src/stayfixed/overlay/doctor.py`, `src/stayfixed/setup/run.py` (`INSTALL_COMMAND`),
  `src/stayfixed/release/pins.py` (`git ls-remote` of this repository's tags, for the `check.yml` pin `init`
  writes), `src/stayfixed/project/templates.py` (the reusable workflow's `uses:`). `check.yml` stays here.
- **The release count skips a non-path source.** `scripts/release.py` `plugin_folder_counts`
  `continue`s past an entry whose `source` is not a string, and
  `tests/scripts/test_release.py::test_a_plugin_the_marketplace_fetches_from_elsewhere_is_not_counted`
  pins that. Changing the entry without changing the count makes the 512 check at a tag check
  nothing.
- **The payload guard walks the whole tree.** `tests/test_payload.py` `tracked_payload` lists every
  row of `git ls-tree -r -l -z HEAD` and reads blobs through `git cat-file --batch`;
  `test_the_tree_is_inside_the_directory_limits` drops only the count's finding
  (`findings_but_the_count`). `FILES_MAX` is read from `scripts/release.py` `PLUGIN_FILES_MAX`
  (512). `docs/cli.md` is in that walk and 498 bytes under `FILE_MAX_BYTES`.
- **CI installs the repository root.** `smoke.yml` `installed-plugin` runs
  `claude plugin marketplace add "$PWD"` and `claude plugin install stayfixed@stayfixed-marketplace`,
  then `diff -r hooks "$INSTALLED/hooks"`, `scripts/smoke_hooks.py`, `doctor` (17 rows) and
  `scripts/smoke_exfiltration.py` against the installed root. `ci.yml` `plugin` validates
  `.claude-plugin/plugin.json --strict`, `.claude-plugin/marketplace.json --strict`,
  `.codex-plugin/plugin.json`, and runs `claude plugin tag --dry-run .`. No test pins the `plugin`
  job or the `marketplace add` line; `tests/test_check_workflow.py` pins the two smoke summary lines.
- **The release attests `dist/*` only.** `release.yml` `build` runs `scripts/release.py check --tag
  "$GITHUB_REF_NAME"` (pinned by `tests/test_fixtures.py`), the suite, `uv build`, then
  `actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8` on `dist/*` with
  `id-token: write` and `attestations: write`. `github-release` creates the Release from `dist/*`.
- **The marketplace documents `github` sources with `ref` and `sha`, and `url` sources take
  `file://`** (code.claude.com, "Marketplace reference", fetched 2026-10-10). A `ref`-only pin is
  the only one available here: the release commit names the plugin repository's tag before the
  owner pushes the commit it will name.
- **`overlay publish-template` is the pattern, not a library.** `src/stayfixed/overlay/publish.py`
  renders, clones with `gh repo clone`, empties the clone but `.git`, writes, `add -A`, commits and
  pushes, all through `Runner.launch`; nothing happens without `--yes`. Its helpers are private and
  `src/stayfixed/overlay/api.py` exports none of them, and `tests/boundaries/test_api_surface.py` refuses a
  script that imports past an area's `api.py`. Its `_replace_tree` writes UTF-8 text only; a plugin
  tree needs bytes and the executable bit. Scripts may import top-level modules directly
  (`scripts/release.py` imports `stayfixed.gitenv.git_run`, `fsops`, `runner`, `errors`, `cli.run`).
- **`gitenv.git_run` returns text decoded with `surrogateescape`, and `gitenv.answer_bytes` turns it
  back into the bytes git wrote.**
- **Test doubles.** `tests/runners.py` `Recorder` answers any program by argv prefix and records
  every call; `tests/scriptload.py` loads a script as a module (`release()`). Tests never run `gh` or
  `claude`; they may run `git`.
- **Routing.** `GROUP_OF` sends `scripts/*.py` and `.github/workflows/*.yml` to
  `mutations/tooling.toml`, and `tests/test_payload.py`, the marketplace file and the README to
  `mutations/repository.toml`.
- **Fragments** are `changelog.d/+<slug>.<type>.md`, types `upgrading`, `feature`, `fix`, `change`.

## Global Constraints

- **Runtime is untouched.** Nothing under `src/stayfixed/`, `hooks/`, `scripts/stayfixed`, `skills/`
  or `agents/` changes, so `hooks/hashes.json` does not change either. If a task finds it must
  touch one, it stops and reports.
- **Scripts import only the standard library and top-level `stayfixed` modules** (never past an
  area's `api.py`), and the script runs as `uv run python scripts/plugin_tree.py …`.
- **The tree is read from a commit, never from the disk.** A file edited, deleted or only staged is
  not in what the directory, the attestation or the plugin repository sees.
- **The plugin's paths are named once**, in `scripts/plugin_tree.py` `PLUGIN_PATHS`; every other
  reader imports or runs that script.
- **Nothing in this plan writes to a remote.** `publish` pushes only with `--yes`, and no test,
  workflow or task runs it with `--yes` against anything but a scratch repository on disk.
- **Every new assertion ships with the mutation that reddens it, or a sentence saying why none
  exists** (`CONTRIBUTING.md`, "Tests"). A mutation named here is a hypothesis until a run watched
  it fail; a load-bearing guard gets a `mutations/` entry in the group file its path routes to.
- **A removed or renamed test takes its mutation entries and every comment citing it along in the
  same commit** (`tests/scripts/test_mutation_oracle.py` resolves cited entry names).
- **Every value that reaches a workflow shell arrives through `env:`**
  (`tests/test_fixtures.py::test_no_workflow_splices_an_expression_into_a_shell`).
- **Tests never run `gh`, `claude`, `codex`, `pip` or `pre-commit`,** and never read the
  developer's `~/.claude`, `~/.codex` or `~/.config/stayfixed`.
- **Neutral text.** Committed text names no project outside this repository, no home directory or
  login, and no private repository; commit ids in text are 7 characters or 40.
- **User-visible changes carry a towncrier fragment** written as a release note for a stranger.
- Conventional commit subjects describing intent; no attribution trailer.

## Review Focus

1. **A release whose marketplace `ref` names a tag the plugin repository does not have yet.** The
   release commit and its tag exist before the owner pushes the plugin; a user who adds the
   marketplace in that window gets an install error, not a wrong plugin. `RELEASING.md` orders the
   push before `main` moves (Task 5), and Task 2's check holds `ref` equal to the version.
2. **A plugin tree that differs from what CI attested** — a local edit, a different checkout, a
   line-ending conversion, a lost executable bit. `publish` must refuse before it clones, and the
   committed tree must read back to the same manifest before anything is pushed (Task 4).
3. **A re-run of `publish` after a push that half happened, or after a success.** A tag already on
   the remote with the same manifest is "already published" (exit `0`, nothing pushed); with a
   different one it is a refusal; the push is `--atomic` so a branch never moves without its tags
   (Task 4).
4. **An existing `0.2.0` install whose marketplace entry changes from `./` to a `github` source.**
   What `claude plugin marketplace update` and `claude plugin update` do then is unmeasured; Task 6
   measures it with a `url` source over a scratch repository, and Task 5's fragment says what a
   user must do if anything.
5. **A path added to the repository that the runtime needs but `PLUGIN_PATHS` omits.** The install
   smoke runs every hook entry and `doctor` against the rendered tree (Task 3), so an omission fails
   CI rather than a user's session.

## Execution contract

Every seat's brief carries the section of this contract that applies to it, copied rather than
referenced, a fix round and a post-PR dispatch included.

**1. Final review.** Three parallel read-only seats — **correctness**, **architecture** (one list of
plugin paths, every guard moved and none left judging the repository root, the script's imports
within the boundary rule), **security** (what `publish` trusts: the attestation's signer workflow
and source ref, the remote, the tag; what it refuses before it writes; that no workflow gains a
credential to a second repository; `env:` for every value reaching a shell) — and a **lifecycle**
seat that walks section 2.

**2. Lifecycle matrix.** Checked at pre-flight like a task, walked by the lifecycle seat. A cell
names the test or step that covers it, or "—" when the change cannot reach it.

| Command \ change | re-run, nothing changed | from a `0.2.0` tree or install | a path missing or not regular | killed or failing part-way | uninstalled |
|---|---|---|---|---|---|
| `plugin_tree.py manifest` / `render` (Task 1) | Task 1 `test_render_twice_writes_the_same_tree_and_manifest` | Task 1 `test_members_at_an_older_commit_are_that_commits` | Task 1 `test_a_symlink_or_submodule_among_the_members_is_refused`, `test_render_refuses_a_destination_that_is_not_empty` | Task 1 `test_render_refuses_a_destination_that_is_not_empty` (a killed render leaves a non-empty directory; the next run refuses it rather than mixing trees) | — |
| `release.py check [--tag]` (Task 2) | `tests/test_manifests.py::test_the_repository_passes_release_check` | Task 2 `test_a_path_source_is_refused_as_the_plugin_folder_it_used_to_be` | Task 2 `test_a_marketplace_without_the_plugin_entry_is_named` | — | — |
| `plugin_tree.py publish` (Task 4) | Task 4 `test_a_second_publish_of_the_same_tag_pushes_nothing` | — (no earlier release was published from the plugin repository) | Task 4 `test_an_unknown_tag_is_refused_before_anything_runs` | Task 4 `test_a_tag_on_the_remote_with_another_tree_is_refused`, `test_a_refused_attestation_stops_before_the_clone`, `test_without_yes_the_remote_is_unchanged` | — |
| CI `plugin`, `installed-plugin`, `build` (Task 3) | — (a workflow run is its own re-run) | Task 6 Step 3 (the upgrade path, measured) | Task 3 `test_the_smoke_installs_the_rendered_tree_and_never_the_checkout` | — | — |

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
  re-applying the original text, and report what happened. If it does not redden, design one that
  does and say so; do not weaken it.
- Line numbers in this plan are as of `21bdbcb`; locate by the quoted text.
- Static checks at CI's scope: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
- Do not spawn subagents. Do not run `git restore`, `git checkout -- <path>`, `git stash`,
  `git reset --hard` or `git clean`. Never run `gh`, and never run `publish` with `--yes` against
  any remote but a scratch repository under your scratchpad or the test's `tmp_path`.
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

## Waves

| Wave | Tasks | Mode | Size (plan lines) |
|---|---|---|---|
| 0 | — | this file, committed first on `wp/plugin-repository` | — |
| A | 1–2 | dispatched | ~190 |
| B | 3–4 | dispatched | ~200 |
| C | 5 | dispatched | ~60 |
| D | 6 | controller-run, real `claude` CLI | ~45 |

Launch graph, drawn last and over what each task consumes:

```text
Wave 0 ──> A ──> B ──> C ──> D ──[PR]
```

- **Task 1 → Task 2**: the payload test and the release count read `plugin_tree.members` and
  `PLUGIN_PATHS`.
- **Task 1 → Task 3**: every workflow runs `scripts/plugin_tree.py render` and `manifest`.
- **Task 1 → Task 4**: `publish` renders through `members` and compares through `manifest`.
- **Task 2 → Task 3**: the smoke's scratch marketplace copies the entry's name and marketplace name
  Task 2 holds.
- **Tasks 2–4 → Task 5**: the documents restate what those tasks made true.
- **Task 3 → Task 6**: the rehearsal runs the commands the workflows run, by hand, with the real CLI.

A and B are not merged into one wave: Task 4's `publish` alone reads `src/stayfixed/overlay/publish.py`, the
runner seam and the attestation contract, and B would pass the ceiling with Tasks 1–2 in it.

## File structure

| Path | Task | Responsibility |
|---|---|---|
| `scripts/plugin_tree.py` (create) | 1, 4 | `PLUGIN_PATHS`, `Member`, `members`, `manifest`, `render`, `publish`; the CLI `render`, `manifest`, `publish` |
| `tests/scripts/test_plugin_tree.py` (create) | 1, 4 | the script's behaviour on scratch repositories, `gh` through `Recorder` |
| `tests/scriptload.py` | 1 | `plugin_tree()`, loaded once, as `release()` is |
| `tests/test_payload.py` | 2 | walks `members(ROOT, "HEAD")`; holds the count on every pull request |
| `scripts/release.py` | 2 | the marketplace `ref` as a version source; the count over `members` |
| `tests/scripts/test_release.py` | 2 | the count and the entry's checks |
| `.claude-plugin/marketplace.json` | 2 | the `github` source pinned to `v<version>` |
| `tests/test_manifests.py` | 2 | the entry's shape |
| `.github/workflows/ci.yml`, `smoke.yml`, `release.yml` | 3 | validate, install and attest the rendered tree |
| `tests/test_check_workflow.py` | 3 | the workflows render the tree and never install or count the checkout |
| `RELEASING.md`, `README.md`, `CONTRIBUTING.md` | 5 | the release step, the one-time setup, where the plugin is fetched from |
| `changelog.d/+plugin-repository.change.md` (create) | 5 | the release note |
| this file, Findings | 6 | the rehearsal's measurements |

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

def members(root: Path, rev: str) -> list[Member]      # sorted by path's UTF-8 bytes
def manifest(entries: Iterable[Member]) -> str          # FORMAT, then "<mode> <sha256> <path>\n" per member
def render(entries: Iterable[Member], out: Path) -> None
```

- `members` raises `stayfixed.errors.Refusal` naming the rev for a rev git cannot resolve to a
  commit, naming the path for a `PLUGIN_PATHS` entry absent at that commit, and naming the path and
  its mode for a symlink (`120000`) or submodule (`160000`) under one: the directory blocks both
  where the plugin loads them, and a tree that holds one is not a tree to publish.
- `render` writes into `out`, which must be absent or an empty directory (else `Refusal`), creates
  parents, writes bytes, and sets `0o755` for `100755` and `0o644` for `100644`; it writes no
  manifest into the tree.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_plugin_tree.py`, each on a scratch
  repository built with `tests.gitfixture.git` (`init -q -b main`, files with their modes,
  `add -A`, `commit`):
  - `test_members_lists_every_plugin_path_with_its_mode_and_nothing_else` — a repository holding
    every `PLUGIN_PATHS` entry plus one file under each of `docs/` and `tests/` and a `pyproject.toml`; the members are
    exactly the plugin paths' files, `hooks/run-hook.sh` and `scripts/stayfixed` at `100755`.
    Mutation: drop `"agents"` from `PLUGIN_PATHS` → expected to redden.
  - `test_members_read_the_commit_and_not_the_disk` — after the commit, edit one member on disk,
    delete another, stage a new file under `skills/`; `members(root, "HEAD")` is the commit's.
    Mutation: read `content` from `root / path` → expected to redden.
  - `test_members_at_an_older_commit_are_that_commits` — two commits; `members(root, first_sha)`
    holds the first commit's bytes.
  - `test_a_symlink_or_submodule_among_the_members_is_refused` — parametrised over a symlink under
    `skills/` and a gitlink under `src/stayfixed/` planted with `update-index --cacheinfo`; the
    refusal names the path.
  - `test_a_missing_plugin_path_is_refused_by_name` — no `LICENSE` at the commit.
  - `test_an_unresolvable_rev_is_refused_by_name`.
  - `test_the_manifest_is_one_line_per_member_in_byte_order` — pins `FORMAT` as the first line, the
    line shape, a path that sorts differently by code point and by UTF-8 bytes in byte order, and a
    final newline. Mutation: sort by `str` → expected to redden on the chosen pair.
  - `test_the_manifest_changes_with_one_byte_and_with_one_mode` — Mutation: drop the mode from the
    line → the mode case is expected to redden.
  - `test_render_writes_bytes_and_the_executable_bit` — a member holding a NUL byte and CRLF
    survives byte for byte; `100755` renders with the owner's execute bit, `100644` without.
  - `test_render_refuses_a_destination_that_is_not_empty`.
  - `test_render_twice_writes_the_same_tree_and_manifest` — two renders into two directories, the
    file sets and bytes equal, and `manifest(members(...))` equal across runs.
  - `test_the_cli_prints_the_manifest_and_renders` — `main(["manifest", "--root", r, "--rev",
    "HEAD"])` prints exactly `manifest(...)`; `main(["render", "--root", r, "--rev", "HEAD",
    "--out", o, "--manifest-file", m])` writes the tree and the manifest file outside it; a refusal
    exits `2` with its sentence on stderr.

- [ ] **Step 2: Run them; expect them to fail** on the missing module:
  `uv run pytest tests/scripts/test_plugin_tree.py -q`.

- [ ] **Step 3: Implement.** Git through `stayfixed.gitenv.git_run`; the listing is
  `ls-tree -r -z --full-tree <rev> -- <PLUGIN_PATHS…>`, each record `"<mode> <type> <oid>\t<path>"`;
  the rev is resolved first with `rev-parse --verify --end-of-options <rev>^{commit}`; blob bytes
  are `gitenv.answer_bytes(git_run(root, "cat-file", "blob", oid))`. A `PLUGIN_PATHS` entry is
  "absent" when no listed path equals it or starts with it plus `/`. The CLI follows
  `scripts/release.py`'s frame (`stayfixed.cli.run`, `Result`, exit `0`/`1`/`2`, `--json`
  accepted). Module docstring: what the plugin tree is, why it is read from a commit, and that the
  manifest is the text a release attests.

- [ ] **Step 4: Run** the module, then commit, then add `mutations/tooling.toml` entries for the
  three load-bearing mutations above (`PLUGIN_PATHS` entry dropped, content read from disk, sort by
  `str`) and prove them: `uv run python scripts/mutation_oracle.py plugin_tree`.

- [ ] **Step 5: Commit** — `feat(release): name the plugin's paths once and read them from a commit`.

### Task 2: Judge the generated tree, not the repository root, and pin the marketplace to the plugin repository

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `scripts/release.py` (`SOURCES`/`collect`, `checked_by_kind`, `plugin_folder_counts`)
- Modify: `tests/scripts/test_release.py`
- Modify: `tests/test_payload.py`
- Modify: `tests/test_manifests.py`
- Modify: `mutations/tooling.toml`, `mutations/repository.toml`

**Interfaces:**
- Consumes: `plugin_tree.members`, `PLUGIN_PATHS` (Task 1).
- Produces: in `scripts/release.py`, `PLUGIN_REPOSITORY = "stayfixed/stayfixed-plugin"`;
  `MARKETPLACE` is a version source whose value is the entry's `ref` with its leading `v` removed
  (so `collect(root)[MARKETPLACE] == "0.2.0"` on this branch); `plugin_folder_counts(root)`
  replaced by `plugin_tree_count(root) -> list[str]`, which counts `members(root, "HEAD")`.

The entry becomes, on this branch (the release commit moves `ref` with the other sources):

```json
{
  "name": "stayfixed",
  "source": { "source": "github", "repo": "stayfixed/stayfixed-plugin", "ref": "v0.2.0" },
  "description": "A methodology harness for coding agents: bug ledger, curated working memory behind a trust gate, and fail-closed guards."
}
```

`v0.2.0` names no tag in the plugin repository, which does not exist yet; only the release commit's
marketplace is read by users (`README.md` installs `stayfixed/stayfixed@vX.Y.Z`, and the default
branch is `main`), and the release commit names the version it releases. That is why the `ref` is a
version source and not a free value: one rule, holding on every commit.

- [ ] **Step 1: Write the failing tests.**
  - `tests/scripts/test_release.py`:
    - `test_the_marketplace_ref_is_a_version_source` — an entry at `v1.2.4` beside sources at
      `1.2.3` is drift naming `.claude-plugin/marketplace.json`. Mutation: leave `MARKETPLACE` out
      of the sources → expected to redden.
    - `test_a_path_source_is_refused_as_the_plugin_folder_it_used_to_be` — `"source": "./"` is a
      problem saying the plugin is published from `stayfixed/stayfixed-plugin`.
    - `test_an_entry_naming_another_repository_or_no_ref_is_refused` — parametrised: another `repo`,
      no `ref`, a `ref` that is a branch name, a `sha` present (the release commit cannot know it).
    - `test_a_marketplace_without_the_plugin_entry_is_named` — no entry named `stayfixed`, or two.
    - `test_a_tag_refuses_a_plugin_tree_over_the_directory_count` and
      `test_a_tag_passes_a_plugin_tree_at_the_count` — a scratch repository with 513 and 512 files
      under `skills/` beside the other plugin paths, and 600 files under `docs/` that are not
      counted. These replace `test_a_tag_refuses_a_plugin_folder_over_the_directory_count`,
      `test_a_tag_passes_a_plugin_folder_at_the_count_whatever_the_disk_holds`,
      `test_the_count_reads_the_folder_the_marketplace_source_names` and
      `test_a_plugin_the_marketplace_fetches_from_elsewhere_is_not_counted`, which go, with their
      mutation entries and every comment citing them. Mutation: count `ls-tree HEAD` of the whole
      repository → the 512-with-600-docs case is expected to redden.
    - `test_a_tag_outside_a_git_checkout_is_refused_for_want_of_a_count` keeps its name and its
      sentence's shape.
  - `tests/test_payload.py`: `tracked_payload(root)` becomes the members of `HEAD`
    (`(path, len(content), mode)` and `{path: content}`) through `plugin_tree.members`, so the rules
    judge the generated tree; `test_the_plugin_folder_is_the_repository_root` is replaced by
    `test_the_payload_is_the_generated_plugin_tree` (the marketplace entry is the `github` source
    of `release().PLUGIN_REPOSITORY`, and the walk's paths all start with a `PLUGIN_PATHS` entry);
    `test_the_tree_is_inside_the_directory_limits` asserts `payload_findings(...) == []`, the count
    included, and `findings_but_the_count` with its two tests goes (the count holds on every pull
    request now, since the tree is 218 files). `test_the_walk_reads_the_committed_tree_and_not_the_disk`
    is rebuilt on a scratch repository carrying the plugin paths, keeping its four observations (an
    edit, a deletion, a staged file, a symlink, the gitlink) where `members` reports them — the
    symlink and the gitlink now as `members`' refusal. Module docstring rewritten: the payload is
    the generated tree, why, and that the count is held on every pull request. Mutation: walk
    `git ls-tree -r HEAD` of the root → `test_the_payload_is_the_generated_plugin_tree` is expected to redden.
  - `tests/test_manifests.py::test_marketplace_has_a_description_and_an_unversioned_entry` pins the
    `github` source and `ref == "v" + <plugin.json version>`.

- [ ] **Step 2: Run them; expect them to fail**:
  `uv run pytest tests/scripts/test_release.py tests/test_payload.py tests/test_manifests.py -q`.

- [ ] **Step 3: Implement.** `scripts/release.py` loads `scripts/plugin_tree.py` as a sibling module
  (`importlib` from `Path(__file__).with_name("plugin_tree.py")`, the way `tests/scriptload.py`
  does, so `uv run python scripts/release.py` needs no `sys.path` edit); the entry checks join the
  `VERSION_DRIFT` kind; `plugin_tree_count` keeps `FOLDER_COUNT`, its "could not be counted"
  sentence and its remedy, now "the plugin tree (scripts/plugin_tree.py) holds N files, over the
  512 …", and runs under `--tag` as before. Edit the entry in `.claude-plugin/marketplace.json`.
  Update `RELEASING.md` section 1's table only where `tests/test_documents.py` holds it; the prose
  is Task 5's.

- [ ] **Step 4: Run** the three modules, then `uv run python scripts/release.py check` (prints one
  version everywhere: `0.2.0`), then commit and prove the named mutations with the oracle.

- [ ] **Step 5: Commit** — `fix(release): judge the generated plugin tree and pin the marketplace to the plugin repository`.

## Wave B — Tasks 3–4

### Task 3: Validate, install and attest the rendered tree in CI

**Files:**
- Modify: `.github/workflows/ci.yml` (job `plugin`)
- Modify: `.github/workflows/smoke.yml` (job `installed-plugin`)
- Modify: `.github/workflows/release.yml` (jobs `build`, `github-release`)
- Modify: `tests/test_check_workflow.py`, `tests/test_fixtures.py`
- Modify: `mutations/tooling.toml`

**Interfaces:**
- Consumes: `scripts/plugin_tree.py render --root . --rev HEAD --out DIR --manifest-file FILE`
  (Task 1); the marketplace name `stayfixed-marketplace` and entry name `stayfixed` (Task 2).

What each job does:

- **`ci.yml` `plugin`**: after the existing install of `@anthropic-ai/claude-code@2.1.261`, render
  `HEAD` into `$RUNNER_TEMP/plugin`, then `claude plugin validate
  "$RUNNER_TEMP/plugin/.claude-plugin/plugin.json" --strict`, `claude plugin validate
  "$RUNNER_TEMP/plugin/.codex-plugin/plugin.json"`, and `claude plugin validate
  .claude-plugin/marketplace.json --strict` (this repository's catalog, which validation reads
  without fetching). `claude plugin tag --dry-run .` stays: it compares the manifests' version.
- **`smoke.yml` `installed-plugin`**: replace `claude plugin marketplace add "$PWD"` by a rehearsal
  of the release's shape, with no network: render `HEAD` into `$RUNNER_TEMP/plugin-repo`, make it a
  git repository with one commit and the tag `v<version>` (version read from
  `.claude-plugin/plugin.json` with `python3 -c`), write
  `$RUNNER_TEMP/market/.claude-plugin/marketplace.json` naming `stayfixed-marketplace` with one
  entry `stayfixed` whose source is `{"source": "url", "url": "file://$RUNNER_TEMP/plugin-repo",
  "ref": "v<version>"}`, then `claude plugin marketplace add "$RUNNER_TEMP/market"` and
  `claude plugin install stayfixed@stayfixed-marketplace`. Every later step is unchanged and now
  runs against a tree installed from a tagged git repository, as users get it. The `diff -r hooks
  "$INSTALLED/hooks"` step stays.
- **`release.yml` `build`**: after `uv build`, render the tag:
  `uv run python scripts/plugin_tree.py render --root . --rev "$GITHUB_REF_NAME" --out
  "$RUNNER_TEMP/plugin" --manifest-file "$RUNNER_TEMP/plugin-tree.txt"`,
  attest `$RUNNER_TEMP/plugin-tree.txt` with the same pinned `attest-build-provenance` (a second
  step; the `dist/*` one stays), and upload it as the artifact `plugin-tree`.
  **`github-release`** downloads `plugin-tree` and attaches `plugin-tree.txt` to the Release beside
  `dist/*`, so anyone can compare the plugin repository's tag against it.

- [ ] **Step 1: Write the failing tests** in `tests/test_check_workflow.py` (the workflows are read
  as text, the way the module already reads them):
  - `test_the_smoke_installs_the_rendered_tree_and_never_the_checkout` — `installed-plugin` runs
    `scripts/plugin_tree.py render`, adds a marketplace under `$RUNNER_TEMP`, and no step adds
    `"$PWD"` or `.` as a marketplace. Mutation: restore `claude plugin marketplace add "$PWD"` →
    expected to redden.
  - `test_the_validator_reads_the_rendered_manifests` — `ci.yml` `plugin` validates
    `plugin.json` and the Codex manifest under the render's `--out`, never `.claude-plugin/plugin.json`
    at the root.
  - `test_the_release_attests_the_plugin_tree_it_rendered_from_the_tag` — `build` renders with
    `--rev "$GITHUB_REF_NAME"` (the runner's own variable, as the step before it reads), one `attest-build-provenance` step's `subject-path` is the render's
    `--manifest-file`, at the same pinned sha as the `dist/*` one, and `github-release` attaches the
    file. Mutation: `--rev HEAD` in `build` → expected to redden.
  - `tests/test_fixtures.py::test_no_workflow_splices_an_expression_into_a_shell` already covers
    the three files; it must stay green.

- [ ] **Step 2: Run them; expect them to fail**:
  `uv run pytest tests/test_check_workflow.py tests/test_fixtures.py -q`.

- [ ] **Step 3: Edit the three workflows.** Comments in the files' existing voice say why: the
  directory reads the plugin repository's commit, so CI validates and installs what that commit
  will hold, and attests the manifest the owner's `publish` checks.

- [ ] **Step 4: Run** the two modules, commit, prove the named mutations with the oracle, and push
  the branch once so `ci` and `smoke` run on GitHub; paste both runs' results. A red smoke on the
  `url` source over `file://` stops the wave and is reported, not worked around.

- [ ] **Step 5: Commit** — `ci: validate, install and attest the rendered plugin tree`.

### Task 4: `publish`: push an attested tree to the plugin repository, and nothing else

**Files:**
- Modify: `scripts/plugin_tree.py` (add `publish` and its CLI command)
- Modify: `tests/scripts/test_plugin_tree.py`
- Modify: `mutations/tooling.toml`

**Interfaces:**
- Consumes: `members`, `manifest`, `render` (Task 1); `stayfixed.runner.Runner`,
  `subprocess_runner`; `stayfixed.release.api.tag_for`.
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
    already: bool      # the remote already carried this tag with this manifest

def publish(root: Path, tag: str, *, remote: str, yes: bool, runner: Runner, scratch: Path) -> Published
```

CLI: `uv run python scripts/plugin_tree.py publish --tag vX.Y.Z [--remote URL] [--yes]`.

The order, each step refusing (`Refusal`, exit `2`) before the next runs:

1. `tag` matches `^v\d+\.\d+\.\d+$` and resolves to a commit in `root`; the version at that commit
   (`.claude-plugin/plugin.json` read with `git show <tag>:…`) is the tag's.
2. `render(members(root, tag), scratch / "tree")`; write `manifest(...)` to
   `scratch / "plugin-tree.txt"`.
3. `gh attestation verify <scratch>/plugin-tree.txt --repo stayfixed/stayfixed --signer-workflow
   stayfixed/stayfixed/.github/workflows/release.yml --source-ref refs/tags/<tag>
   --deny-self-hosted-runners` through `runner`; a non-zero exit is a refusal quoting gh's first
   stderr line and saying that the tree rendered here is not the one the release attested.
4. `git ls-remote --tags <remote> refs/tags/<tag>`: present → fetch it into a scratch repository,
   read `manifest(members(scratch_repo, "FETCH_HEAD"))`; equal → `Published(already=True,
   pushed=False)` and stop; different → refusal naming both manifests' first differing line.
5. `git clone --quiet --no-tags <remote> <scratch>/clone` (an empty repository clones with a
   warning and no commit); remove everything but `.git` with `fsops.remove_within` /
   `rmdir_within`; write every member's bytes and mode under the clone.
6. `git add -A`; `git commit --quiet --allow-empty -m "stayfixed X.Y.Z" -m "Generated from
   stayfixed/stayfixed at <40-char sha> (<tag>) by scripts/plugin_tree.py."` (the owner's own git
   identity; nothing sets one).
7. Read back: `manifest(members(clone, "HEAD"))` equals step 2's, else refusal and nothing pushed.
8. Tag `<tag>` and `stayfixed--<tag>` (lightweight, as `RELEASING.md` step 6 tags this repository).
9. Without `yes`: `Published(pushed=False)` and a plan line ("would push N files as <commit>, tags
   …, to <remote>"). With `yes`: `git push --atomic <remote> HEAD:refs/heads/main
   refs/tags/<tag> refs/tags/stayfixed--<tag>`.

Every `git` here runs through `runner` with an explicit `cwd`, so the tests answer `gh` from a
`Recorder` and run real `git` against a bare repository in `tmp_path` (a composite runner: the
`Recorder` for argv starting with `gh`, `subprocess_runner()` otherwise).

- [ ] **Step 1: Write the failing tests** (a scratch source repository with the plugin paths and a
  tag `v1.2.3` whose `plugin.json` says `1.2.3`; a bare repository as the remote):
  - `test_a_verified_tree_is_pushed_with_both_tags_and_reads_back_whole` — with `yes=True`, the
    remote's `main` and both tags name one commit whose `manifest(members(...))` is the source
    tag's; the executable bits survive the round trip. Mutation: write members with mode `0o644`
    always → expected to redden.
  - `test_without_yes_the_remote_is_unchanged` — `git ls-remote` of the bare repository is empty
    after the run, and the result names the commit it would push.
  - `test_a_refused_attestation_stops_before_the_clone` — `gh attestation verify` answers `1`; no
    `git clone` and no `git push` appear in the recorded calls, and the refusal quotes gh's stderr.
    Mutation: ignore the verify exit code → expected to redden.
  - `test_the_attestation_is_asked_for_this_workflow_and_this_tag` — the recorded `gh` argv holds
    `--signer-workflow stayfixed/stayfixed/.github/workflows/release.yml`, `--source-ref
    refs/tags/v1.2.3` and `--deny-self-hosted-runners`, and its file is the manifest the render
    wrote. Mutation: drop `--source-ref` → expected to redden.
  - `test_the_tree_is_rendered_from_the_tag_and_not_the_disk` — an uncommitted edit to a member
    is not in what is pushed.
  - `test_a_second_publish_of_the_same_tag_pushes_nothing` — two runs with `yes=True`; the second
    returns `already=True`, and the remote's refs are unchanged.
  - `test_a_tag_on_the_remote_with_another_tree_is_refused` — the remote carries `v1.2.3` on a
    different tree; refusal, nothing pushed.
  - `test_an_unknown_tag_is_refused_before_anything_runs` and
    `test_a_tag_whose_version_is_another_is_refused` — no runner call at all.
  - `test_the_previous_release_is_replaced_whole` — a remote whose `main` holds an extra skill the tag no longer has;
    after the push that skill is gone, and the history keeps the earlier commit as
    the parent.

- [ ] **Step 2: Run them; expect them to fail**:
  `uv run pytest tests/scripts/test_plugin_tree.py -q -k publish`.

- [ ] **Step 3: Implement** `publish` and the `publish` command; `scratch` is a
  `tempfile.TemporaryDirectory` in the CLI and `tmp_path` in tests. The docstring says what it
  trusts and why: the attestation binds the manifest to this repository's `release.yml` at this
  tag on a GitHub-hosted runner; the owner's checkout only renders and compares; CI holds no
  credential to the plugin repository.

- [ ] **Step 4: Run** the module, commit, prove the named mutations with the oracle.

- [ ] **Step 5: Commit** — `feat(release): publish the attested plugin tree to its own repository`.

## Wave C — Task 5

### Task 5: Restate the release, the install and the contribution guide

**Files:**
- Modify: `RELEASING.md`, `README.md`, `CONTRIBUTING.md`
- Create: `changelog.d/+plugin-repository.change.md`
- Modify: `tests/test_documents.py` only where it pins a sentence these edits change

- [ ] **Step 1: `RELEASING.md`.**
  - The opening sequence gains the plugin's push between the Release and `main`.
  - Section 1's table: `.claude-plugin/marketplace.json` is a source — the entry's `ref`, `vX.Y.Z` —
    and the sentence calling it "checked for consistency rather than for a number" goes.
  - Section 2: the paragraph "If the tree holds more than 512 files, publish the plugin from a
    repository of its own first" is replaced by one saying the plugin is published from
    `stayfixed/stayfixed-plugin`, generated by `scripts/plugin_tree.py`, and that the count is the
    generated tree's, held on every pull request. Step 3 lists the marketplace `ref` among the
    places set by hand. A new step between 7's approval and `git push origin main`:

    ```bash
    uv run python scripts/plugin_tree.py publish --tag vX.Y.Z          # verify, render, plan
    uv run python scripts/plugin_tree.py publish --tag vX.Y.Z --yes    # push main and both tags
    ```

    with why `main` waits for it (the release commit's marketplace names a tag that exists only
    once this has run) and what a refusal means (the tree is not the one CI attested: do not
    work around it).
  - Section 3 gains **The plugin repository**: create `stayfixed/stayfixed-plugin` public and
    empty, the description, and the tag ruleset over `refs/tags/v*.*.*` and
    `refs/tags/stayfixed--v*` with `deletion` and `update` rules, by the same create-or-replace
    script section 3 already gives for this repository, with the repository name changed.
  - Section 5: a refused or failed `publish` leaves `main` where it is; a pushed plugin tag is
    spent like this repository's.
  - Section 6: `scripts/plugin_tree.py` `manifest`, `render`, `publish`, each in two sentences.
- [ ] **Step 2: `README.md`.** The Install section keeps both lines `tests/test_documents.py`
  holds and gains one sentence: the marketplace here fetches the plugin from
  `stayfixed/stayfixed-plugin` at the release's tag. **`CONTRIBUTING.md`**: where it describes the
  payload guard or the plugin folder, say the guard judges the generated tree, and that a file the
  runtime needs outside `PLUGIN_PATHS` must be added there.
- [ ] **Step 3: The fragment**, `+plugin-repository.change.md`: the plugin is now installed from
  `stayfixed/stayfixed-plugin`, a repository holding only what runs, at the release's tag, and the
  install commands do not change. Task 6's Step 3 may add what an existing install must do; until
  it has run, say nothing about upgrades.
- [ ] **Step 4: Run** `uv run pytest tests/test_documents.py tests/test_manifests.py -q` and the
  plan check.
- [ ] **Step 5: Commit** — `docs: release the plugin from its own repository`.

## Wave D — Task 6 (controller-run)

### Task 6: Rehearse the release's shape with the real CLI

Scratch only, under the controller's scratchpad; nothing reaches GitHub.

- [ ] **Step 1: Validate the rendered tree.** `uv run python scripts/plugin_tree.py render --root .
  --rev HEAD --out <s>/tree --manifest-file <s>/plugin-tree.txt`; `claude plugin validate
  <s>/tree/.claude-plugin/plugin.json --strict`; record the output and the file count.
- [ ] **Step 2: Install from a tagged scratch repository.** As the smoke does, under a temporary
  `CLAUDE_CONFIG_DIR`, with the installed `claude`; run `scripts/smoke_hooks.py` against the
  installed root; record the summary line.
- [ ] **Step 3: The upgrade path.** Under a fresh `CLAUDE_CONFIG_DIR`: a scratch marketplace at
  `v0.2.0`'s shape (`git worktree add <s>/v020 v0.2.0`, marketplace added from it, `stayfixed`
  installed); then change that marketplace's entry to the `url` source of Step 2's repository at a
  tag and run `claude plugin marketplace update stayfixed-marketplace` and `claude plugin update
  stayfixed@stayfixed-marketplace`. Record what each printed, which root `claude plugin details
  stayfixed` names afterwards, and whether the hooks run from it. If an existing install needs a
  user action, Task 5's fragment says it, as an `upgrading` fragment.
- [ ] **Step 4: `publish` against a scratch remote.** `git init --bare <s>/remote.git`; run
  `publish --tag v0.2.0 --remote <s>/remote.git` without `--yes`; record the refusal (no
  attestation of `v0.2.0`'s plugin manifest exists), which is the guard working, and that the
  remote is empty afterwards.
- [ ] **Step 5: Record** Steps 1–4 in Findings, with the `claude` version and each command's
  output, and commit — `docs(plans): record the plugin repository rehearsal`.

## Findings

Written by Task 6 and by the pull request's review.
