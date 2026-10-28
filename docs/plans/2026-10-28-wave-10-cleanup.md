# Wave 10, CL6–CL9 — four deletion-only cuts: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. **The wave is the dispatch
> unit, not the task:** one implementer per lettered wave, with every task inside it keeping its own
> failing test, verification and commit. Each wave is one pull request into `dev`, with one final
> review (section "Execution contract" below, item 4). The section "Execution contract" is the
> wave-10 umbrella plan's, verbatim.

**Goal:** remove four controls that fail the design rule. Each pull request deletes the control
together with its tests, documentation rows and mutation entries, and leaves `src` smaller.
- **CL6:** the release record `hooks/hashes.json`.
- **CL7:** the reusable workflow's `timeout-minutes` bound.
- **CL8:** the skill-frontmatter hooks walk and the marker-provenance red.
- **CL9:** compatibility code for releases only the owner ran.

**Architecture:** four waves, A to D, one pull request each, run in the order A, B, C, D. A, C and D
edit the same `doctor` files, so they merge one after another. B touches only the reusable workflow
and may run beside A in its own worktree. No wave adds a feature. The only `src` lines a wave writes
are a caller's adaptation to a removal.

**Tech Stack:** Python ≥ 3.11 standard library; `uv`, pytest (`-n auto`), ruff, mypy, the mutation
oracle (`scripts/mutation_oracle.py`, entries in `mutations/*.toml` routed by `GROUP_OF`), towncrier
fragments in `changelog.d/`.

**Spec:** the wave-10 umbrella plan, `docs/plans/2026-10-28-wave-10-umbrella.md`, lane CL, and its
"Lane-plan items" row for CL. The private design's §15.10 decision 4 is restated here:

> The cleanup cuts, one deletion-only pull request each:
> - (a) `hooks/hashes.json`, `release.py hashes` and the hash half of `doctor`'s `files` row. Their
>   own documentation says a determined attacker is not their threat, and they turn red on the
>   owner's own edits.
> - (b) The reusable workflow's 5–60 bound and its failing step on `timeout-minutes`. The caller file
>   is pull-request content, so the bound stops nobody and refuses a legitimate long caller. The
>   value passes through.
> - (c) The skill-frontmatter hooks walk and the marker-provenance red. No verdict reads them, and
>   the harness's own workspace trust is the anchor.
> - (d) The `0.3.x` record reader, the `retired-deny` row with the preset's `[deny] retired`, and the
>   retired-files table in `src/stayfixed/overlay/template.py`. There are no users to keep them for.
>
> Kept: the overlay's pre-commit secret scan. Waits until after launch: folding `trust` into
> memory's reviewed record.

**Scope:** package launch-readiness, wave 10, lane CL (the umbrella's "Lanes" table). Contracts
consumed: C1 (configuration: CL9 removes the preset's `[deny] retired`), C5 (the CLI:
`release.py hashes` is a repository script, not a command, and `doctor`'s rows change). Out:
- every other back-compat branch the survey found (in `src/stayfixed/attach/write.py`, `src/stayfixed/attach/exclude.py`,
  `src/stayfixed/scaffold/engine.py` before the ledger, `src/stayfixed/project/uninstall.py`, `src/stayfixed/project/footprint.py`,
  `src/stayfixed/memory/index.py`, `src/stayfixed/assess/state.py`, `src/stayfixed/ledger/register.py`), which is filed, not cut;
- `src/stayfixed/assess/probes.py`'s `foreign-hooks` probe, which shares the marker rule CL8 removes from `doctor`.
  CL8's pull request names it for the owner and does not touch it.

**Premise:** measured on 2026-10-28 at `dev` = `9d8492c` by a read-only survey. Each wave
re-measures its own part before its first edit and stops on a mismatch.
- **Doctor.** `doctor` reports 17 rows: 12 in `CHECKS` (`src/stayfixed/doctor/checks.py`), plus
  `attach` 1, `memory` 2 and `overlay` 2. CL6 and CL8 leave 17; CL9 makes it 16.
- **The release record.** `hooks/hashes.json` exists, and `src/stayfixed/release/hashes.py` defines
  `HASHED_FILES`, `RECORD`, `FORMAT`, `UnreadableRecord`, `digests` and `read_record`.
  `scripts/release.py` has a `hashes` subcommand (`write_record`, `drift`, `run_hashes`,
  `RECORD_DRIFT`). `scripts/check_artifacts.py`'s `SDIST_MUST` spreads `*HASHED_FILES, RECORD`.
- **The timeout bound.** `.github/workflows/check.yml` has a `timeout-minutes` input (number, default
  15), a job bound
  `${{ inputs.timeout-minutes >= 5 && inputs.timeout-minutes <= 60 && inputs.timeout-minutes || 15 }}`
  and a first step, "The time limit is inside its bounds". `smoke.yml`'s `same-repository-form` job
  passes `timeout-minutes: 25`.
- **The frontmatter walk.** `src/stayfixed/doctor/frontmatter.py` and
  `src/stayfixed/doctor/hooked.py` hold 966 lines, used only by the `hook-entries` row through
  `src/stayfixed/doctor/entries.py`, and by `src/stayfixed/harnesses.py`'s `Hooked` and
  `Harness.hooked`.
- **The compatibility code.**
  - `src/stayfixed/trust/record.py` `recorded` returns `{}` for a 0.3.x flat map.
  - `doctor`'s `retired-deny` row reads the preset's `[deny] retired`
    (`src/stayfixed/presets/recommended.toml`).
  - `src/stayfixed/overlay/template.py` `_RETIRED` names four retired files, which
    `src/stayfixed/overlay/upgrade.py` folds into `shipped`.
- **The oracle** holds 2,670 entries, and a `reddens` naming a deleted test fails the oracle loudly.

## Execution contract

The wave-10 umbrella plan's "Execution contract", verbatim:

1. **The wave is the dispatch unit.**
   - Waves are lettered and own a run of continuously numbered tasks.
   - Each dispatched wave gets one implementer and no review of its own: the pull request's final
     review is the review.
   - Every task keeps its own failing test, verification and commit.
   - A fix round goes to the same implementer while its context allows, else to a fresh agent with
     the review package.
   - Every subagent runs on Opus (`model: opus`).
2. **Every implementer brief says:**
   - Report a mismatch with the tree instead of guessing.
   - Run a command and paste what it printed before writing any claim about it.
   - Run focused tests while iterating and at each commit. Before each push, run once:
     - `uv run pytest -n auto --cov --cov-fail-under=92`, with `uv run python scripts/release.py check`;
     - the suite again on Python 3.13 (`uv run --python 3.13 pytest -n auto`), the oracle's
       interpreter in CI, since a local uv Python is often newer than any CI leg (CI holds 3.11.4
       and the rest).
   - A plan's predicted mutation outcome is a hypothesis: design your own if it does not redden,
     and paste the raw output either way.
   - Take no line numbers from the plan.
   - This brief is a message, not a file, so cite only the plan.
   - Write nothing under the repository but the task's files; use `<scratchpad>/<wave>-<role>/`.
   - Never run a script you did not write, and read `git diff --stat` before committing.
   - Run the static checks at CI's scope: `uv run ruff check .`, `uv run ruff format --check .`,
     `uv run mypy`.
   - Do not use the Agent tool, and do not run `git checkout`, `restore`, `stash` or `clean`.
   - Start a long run in the background and wait on its own output, never with `pgrep`.
3. **Every reviewer brief adds:**
   - Run every command yourself, and never use the Agent tool.
   - Do not run `git checkout`, `restore`, `stash` or `clean`.
   - What already passed, by sha and suite; run only the test that decides a finding you suspect.
   - No citation may point at a brief, a dispatch or a report.
   - What later tasks own.
4. **One final review per pull request**, with two read-only seats: correctness, and "who does this
   refuse, and what can be deleted".
   - A security seat joins only when the diff touches an anchor repository bytes cannot move (CI's
     base read, the binding id in the git common directory, repository-path containment, the exclude
     ordering).
   - Reviewers give findings only, with no replacement text. A separate triage sends on only
     correctness and requirement gaps.
   - Then one scoped re-review of the fixes, and stop: no per-wave reviews, and no minor finding
     rides a round.
5. **The lifecycle matrix**, walked at pre-flight like a task and again by the correctness seat:
   every configuration key the pull request adds or removes × every change of configuration (set a
   value, change it, unset it, move a path, a step that fails part-way, `uninstall`) × only the
   layers the key's class admits. Each cell states its expected outcome. The class-table test holds
   where a key may be set, and a command that reads no configuration walks no layer.
6. **The parallelism map.**
   - Read-only seats run beside each other and beside the implementer.
   - Writers of one worktree serialise.
   - One heavy local run (the full suite, the mutation oracle) at a time per host.
   - No local full run while the same branch's CI runs.
7. **Templates.**
   - A fix brief enumerates the sibling instances of the defect's class only to delete them or fold
     them into one rule, never to extend a refusal list.
   - After a simplification ruling, it carries a net budget: `src` below zero, tests and mutation
     entries at zero or less, never met by deleting a test that holds behaviour.
   - A new defect found during a cut is filed in the ledger, not fixed, unless the fix deletes code.
   - A security ruling names its minimal preconditions, its anchor's provenance (who can write the
     bytes it trusts), and one legitimate user it must not refuse.
8. **Verification.**
   - The controller re-verifies only heads it pushes or merges.
   - It re-derives the pull request's body from the diff before every push.
   - It takes the run id from `gh pr checks` and waits with `gh run watch <run-id> --exit-status`
     until every job has ended, before reporting a pull request done. Never a `head_sha` query,
     which finds no run for a pull request's merge ref.
9. **Second finding at one seam.** At the second review finding that points at the same function,
   reader or boundary, the next step is a redesign of that seam put to the owner, not a third patch.
   A second bypass of the same refusal list counts as the same seam.
10. **Mutation entries.** A new entry only for a branch that decides a verdict, a containment or a
    data-loss path. Other assertions need neither an entry nor a "why none" sentence. Deleting a
    control deletes its entries.
11. **Net size in every report.** Every review package and every lane report prints
    `git diff --shortstat <base> HEAD -- src tests mutations docs`. A lane plan states its expected
    dispatch count and size before its first dispatch.

**This lane's size:**
- four implementer dispatches (waves A–D), and two review seats plus one re-review per pull request;
- expected net size: `src` about −1,500 lines (CL8 alone about −1,100), tests about −2,000, mutation
  entries about −170, docs about −250. No wave's `src` or tests net is positive.

**Every pull request body** carries a "What this removes and what is lost" section: the adversary
the removed control named, why that adversary reaches its anchor or is already stopped, and what no
row or check reports any more. The section is written from the diff, not from this plan.

## Global constraints

- Standard library only at runtime; no new dependency, no new module.
- Every write goes through `fsops`, as `CONTRIBUTING.md` requires.
- **Deletion is the unit.** A control's tests, its `docs/cli.md` and `README.md` rows, its
  `CONTRIBUTING.md` or `RELEASING.md` mentions, its skill text and its mutation entries go in the
  same commit as its code. A test that holds behaviour still shipped is never deleted. A test of
  the removed control is deleted, not edited to pass.
- **No old spelling stays.** A removed command, flag or key is gone with no alias (d3 as amended).
- **Commits** follow `CONTRIBUTING.md`'s conventional style: `refactor(doctor): …`, `ci: …`,
  `refactor(release): …`, `refactor(trust): …`. Each pull request has one towncrier fragment in
  `changelog.d/`: type `change` (the repository has no `removed` type), or `upgrading` where a user-visible behaviour goes.
- `docs/plans/*` and `CHANGELOG.md` are history and are not edited.

## Review focus

Each line is a failure the cuts could cause that no single task's tests would show, with the test
that pins it.

1. **The sdist silently stops requiring the three files.** If `HASHED_FILES` is deleted from
   `SDIST_MUST` without replacement, the sdist no longer has to carry `hooks/run-hook.sh`,
   `hooks/hooks.json` or `scripts/stayfixed`. Pinned by Task 1's
   `test_the_sdist_must_carry_the_hook_wrapper_hooks_file_and_launcher`.
2. **A green `files` row now proves less.** The row tests only the executable bit. A stale
   `hooks.json`, or an edited wrapper that still runs, is no longer reported. Task 2 states this in
   `docs/cli.md`, and the pull request's "What is lost" section says it.
3. **A caller that passes an out-of-range timeout is now handed to the platform.** The platform's own
   limit (360 minutes for a job on a hosted runner) bounds it. Task 3's test pins that the value
   reaches the job as given.
4. **A 0.3.x `trust.json` now refuses instead of reading as empty.** Task 6 pins the refusal and its
   message. The controller checks first that the owner's machines hold a version-1 record.
5. **`overlay upgrade` no longer removes the four retired overlay files.** Task 8 pins that `upgrade`
   plans nothing for them, and the fragment says the owner deletes them by hand if they are still
   there.

---

## Wave A — Tasks 1–2 (CL6, branch `cleanup/hashes`)

### Task 1: Remove the release record from the release tooling and the package

**Files:**
- Delete: `hooks/hashes.json`, `src/stayfixed/release/hashes.py`, `tests/release/test_hashes.py`
- Modify: `scripts/release.py`, `scripts/check_artifacts.py`, `src/stayfixed/release/api.py`,
  `src/stayfixed/harnesses.py` (the wrapper bullet's comment), `RELEASING.md`, `CONTRIBUTING.md`
- Test: `tests/scripts/test_release.py`, `tests/scripts/test_check_artifacts.py`,
  `tests/test_manifests.py`, `tests/boundaries/test_api_surface.py`, `tests/release/test_surface.py`,
  `tests/test_install_path.py` (a comment only)
- Mutations: `mutations/core.toml` (the nine entries whose `file` is `src/stayfixed/release/hashes.py`),
  `mutations/tooling.toml` (the eight release-record entries, and the `reddens` of "the release
  script tells its reader to run the command the CLI no longer ships")

**Interfaces:**
- Produces:
  - `scripts/release.py` offers the subcommands `check`, `notes` and `pin`, and nothing else.
  - `scripts/check_artifacts.py` `SDIST_MUST` names `hooks/run-hook.sh`, `hooks/hooks.json` and
    `scripts/stayfixed` as literals.
  - `stayfixed.release.api` exports `PACKAGE`, `Pin`, `Resolution`, `is_released`, `released`,
    `resolve_pin` and `tag_for`.
  - `release.py check --json` has no "release record drift" key.
- Consumes: nothing from another wave.

- [ ] **Step 1: Write the failing tests.**
  - In `tests/scripts/test_release.py`, change the subcommand-list assertion to
    `["check", "notes", "pin"]`, and remove `"release record drift"` from the `kinds ==` mapping.
  - In `tests/scripts/test_check_artifacts.py`, add
    `test_the_sdist_must_carry_the_hook_wrapper_hooks_file_and_launcher`. It asserts that
    `{"hooks/run-hook.sh", "hooks/hooks.json", "scripts/stayfixed"} <= set(SDIST_MUST)` and that
    `"hooks/hashes.json" not in SDIST_MUST`.
  - In `test_a_member_missing_from_the_sdist_is_named`, use another member (`CHANGELOG.md`) instead
    of `hooks/hashes.json`.
  - In `tests/boundaries/test_api_surface.py`, point the sample imports at `stayfixed.release.pins`.
  - In `tests/release/test_surface.py`, drop the six names from `required`.
- [ ] **Step 2: Run the tests and watch them fail.** Run
  `uv run pytest -q tests/scripts/test_release.py tests/scripts/test_check_artifacts.py tests/release/test_surface.py tests/boundaries/test_api_surface.py`.
  Expected: FAIL on the subcommand list and on `SDIST_MUST`.
- [ ] **Step 3: Delete.**
  - Delete the three files.
  - In `scripts/release.py`, delete `write_record`, `drift`, `run_hashes`, the `hashes` subparser,
    `RECORD_DRIFT`, the record block in the check, its imports and the usage docstring's line.
  - In `SDIST_MUST`, spell the three paths as literals and drop `RECORD`.
  - Remove the record names from `stayfixed.release.api`.
  - Delete the tests that hold only the record:
    - in `tests/scripts/test_release.py`, the "release record" block,
      `test_a_tree_that_ships_every_recorded_file_is_told_when_the_record_is_missing` and
      `test_a_project_with_its_own_hooks_directory_is_not_told_about_a_release_record`;
    - in `tests/test_manifests.py`, `test_the_repository_itself_carries_a_current_release_record`
      and `test_a_drifted_record_fails_the_hashes_check`.
  - Delete the mutation entries listed under Files, and edit the one `reddens`.
  - Edit the docs:
    - `RELEASING.md`: the table row, the `**hashes**` paragraph and the three other mentions;
    - `CONTRIBUTING.md`: `hashes` in the scripts list;
    - `src/stayfixed/harnesses.py`: the comment naming `hooks/hashes.json`.
- [ ] **Step 4: Run the tests and watch them pass.** Run the Step 2 command, then
  `uv run python scripts/release.py check`. Expected: PASS, and `check` exits 0.
- [ ] **Step 5: Commit:** `refactor(release): drop the hooks/hashes.json release record`.

### Task 2: `doctor`'s `files` row keeps only the executable bit

**Files:**
- Modify: `src/stayfixed/doctor/checks.py` (`_files`), `docs/cli.md` (the `files` row and the
  "no release record" prose), `skills/doctor/SKILL.md`
- Test: `tests/doctor/test_checks.py`
- Mutations: `mutations/doctor.toml` (the six `doctor files` record entries)

**Interfaces:**
- Consumes: Task 1's removal of `read_record` and `digests`.
- Produces: `_files` returns SKIP when the plugin root is unreadable, RED when `hooks/run-hook.sh`
  is not executable, and OK otherwise.

- [ ] **Step 1: Write the failing tests.**
  - In `tests/doctor/test_checks.py`, make `_planted_plugin` plant the wrapper alone.
  - Add `test_files_is_ok_for_an_executable_wrapper_with_no_release_record`. It asserts status `OK`
    and that the summary names `hooks/run-hook.sh`.
  - Rename `test_a_wrapper_that_lost_its_executable_bit_is_red_although_no_hashes_exist` to
    `test_a_wrapper_that_lost_its_executable_bit_is_red`, keeping its assertions.
- [ ] **Step 2: Run and watch it fail.** Run `uv run pytest -q tests/doctor/test_checks.py -k files`.
  Expected: FAIL, because the import of `read_record` breaks or the row reports SKIP for a missing
  record.
- [ ] **Step 3: Delete everything in `_files` after the executable-bit check.** That is the
  unreadable-record red, the no-record SKIP, the union and its messages. The row ends in an OK row.
  - Delete the five record tests the survey names in `tests/doctor/test_checks.py`, and the six
    mutation entries.
  - In `docs/cli.md`, edit the `files` row so it says what the row no longer reports: a stale
    `hooks/hooks.json` or an edited wrapper that still runs. Also edit the "no release record" prose
    and the skip-arm count.
  - In `skills/doctor/SKILL.md`, edit the "no release record" clause.
- [ ] **Step 4: Run the tests and watch them pass.** Run `uv run pytest -q tests/doctor tests/test_install_path.py`.
  Expected: PASS. Then run `uv run python scripts/mutation_oracle.py --file src/stayfixed/doctor/checks.py`.
  If the oracle takes no such flag, run it whole. Expected: no survivor and no missing `reddens`.
- [ ] **Step 5: Commit:** `refactor(doctor): the files row checks the executable bit only`. Then add
  the fragment `changelog.d/+release-record.change.md`. It names the removed record and command, and
  what `doctor files` no longer reports.

**Before the push (Wave A):** the full suite, the 3.13 run, the oracle whole, and the static checks.
Then the controller opens the pull request with its "What this removes and what is lost" section,
including that the `wrapper` row still reports a missing or unreadable launcher.

---

## Wave B — Task 3 (CL7, branch `cleanup/timeout-bound`)

### Task 3: The reusable workflow passes `timeout-minutes` through

**Files:**
- Modify: `.github/workflows/check.yml`, `docs/cli.md` (the input row and the paragraph "The time
  limit is bounded, and running out still fails")
- Test: `tests/test_check_workflow.py`
- Mutations: `mutations/tooling.toml`, three entries:
  - "the reusable workflow's time limit reaches ten hours";
  - "the time limit's bound step admits any value";
  - "the time limit's refusal stops failing the job".

  "no real run passes the reusable workflow a time limit of its own" stays, because `smoke.yml`
  still passes 25.

**Interfaces:**
- Produces: the input `timeout-minutes` (number, default 15) is unchanged for callers. The job's
  bound is `${{ inputs.timeout-minutes }}`, and no step checks the value.
- Consumes: nothing.

- [ ] **Step 1: Write the failing test.** Add `test_the_job_s_time_limit_is_the_input_as_given` to
  `tests/test_check_workflow.py`. It asserts that `jobs.gates.timeout-minutes` reads
  `${{ inputs.timeout-minutes }}`, that the first step is "The caller's repository", and that no step
  is named "The time limit is inside its bounds".
- [ ] **Step 2: Run and watch it fail.** Run `uv run pytest -q tests/test_check_workflow.py -k time_limit`.
  Expected: FAIL.
- [ ] **Step 3: Edit the workflow and its tests.**
  - In `check.yml`, replace the expression with `${{ inputs.timeout-minutes }}`, and delete the comment
    block above it and the bound step.
  - Make the input's description "the job's time limit in minutes, handed to the runner as given".
  - In the tests, delete the bound tests and helpers the survey names (`_BOUND`, `BOUND_STEP`,
    `TIMEOUT_LEAST`, `TIMEOUT_MOST`, `TIMEOUT_DEFAULT` and the four bound tests). Edit `STEPS`,
    `SCRIPTS` and the first-step assertion.
  - Delete the three mutation entries.
  - In `docs/cli.md`, replace the paragraph: the value is the caller's, and the platform's own job
    limit bounds it.
- [ ] **Step 4: Run and watch it pass.** Run `uv run pytest -q tests/test_check_workflow.py tests/test_workflow_yaml.py`.
  Expected: PASS.
- [ ] **Step 5: Commit:** `ci: pass the reusable workflow's timeout-minutes through unbounded`.
  Then add the fragment `changelog.d/+timeout-bound.change.md`.

**Before the push (Wave B):** as for Wave A. Then open the pull request.

---

## Wave C — Tasks 4–5 (CL8, branch `cleanup/frontmatter-walk`, after Wave A has merged)

### Task 4: Remove the skill-frontmatter hooks walk

**Files:**
- Delete: `src/stayfixed/doctor/frontmatter.py`, `src/stayfixed/doctor/hooked.py`
- Modify:
  - `src/stayfixed/doctor/entries.py`: `_informed`, `_SEEN`, `_skill_hooks`, `_skill_unread`,
    `_skill_unparsed`, `_linked_out`, `_skill_untold`, the `hooked` import, and the `informed`
    argument of `_told` and `hook_entries`;
  - `src/stayfixed/harnesses.py`: `Hooked`, `Harness.hooked` and `CLAUDE`'s `hooked=`;
  - `src/stayfixed/fsops.py` (a comment);
  - `docs/cli.md`: the `hook-entries` row, the section from "`hook-entries` judges the entries of
    settings files and nothing else" through "The plugin and agent rows share that limit", and the
    launch counts.
- Test: `tests/doctor/test_checks.py` (the skill block), `tests/test_fsops.py` (the two
  `src/stayfixed/doctor/hooked.py` `OTHER_PREDICATES` entries), `tests/test_install_path.py` (`DOCTOR_LAUNCHES`)
- Mutations: `mutations/doctor.toml`, about 131 entries, all removed:
  - every entry whose `file` is `src/stayfixed/doctor/frontmatter.py` (96) or `src/stayfixed/doctor/hooked.py` (33);
  - in `entries.py`, "hook-entries reads no project skill" and "a skill declaring hooks makes
    hook-entries red";
  - in `harnesses.py`, "hook-entries reads no command or agent file", and the registry comment entry
    in `mutations/core.toml` above the same pair.

**Interfaces:**
- Produces: `hook_entries(...)` without `informed`. The `hook-entries` row reports the
  settings-file entries only, with no information line about skill, command or agent frontmatter.
  `Harness` has no `hooked` field.
- Consumes: Wave A merged (shared `tests/doctor/test_checks.py` and `docs/cli.md`).

- [ ] **Step 1: Write the failing test.** Add
  `test_hook_entries_says_nothing_of_skill_frontmatter` to `tests/doctor/test_checks.py`: a project
  skill declaring `hooks:` in its frontmatter leaves the row's text free of "skill" and of the
  skill's name, and the row's status is unchanged.
- [ ] **Step 2: Run and watch it fail.** Run `uv run pytest -q tests/doctor/test_checks.py -k skill_frontmatter`.
  Expected: FAIL, since the row names the skill today.
- [ ] **Step 3: Delete.**
  - Delete the two modules and the `entries.py` and `harnesses.py` parts listed above.
  - Delete the skill block of tests, from
    `test_a_project_skill_declaring_hooks_is_information_naming_it` through
    `test_a_skill_in_a_checked_out_submodule_is_named`, with their helpers and the
    `hooked._read_place` patch.
  - Delete the two `OTHER_PREDICATES` entries.
  - Delete the mutation entries.
  - Re-measure `DOCTOR_LAUNCHES` by running `tests/test_install_path.py`, set the measured number,
    and edit `docs/cli.md`'s launch counts to match.
- [ ] **Step 4: Run and watch it pass.** Run `uv run pytest -q tests/doctor tests/test_fsops.py tests/test_install_path.py tests/test_documents.py`.
  Expected: PASS. Then run `uv run mypy`, which also catches a leftover `Hooked` or `informed`
  reference.
- [ ] **Step 5: Commit:** `refactor(doctor): drop the skill-frontmatter hooks walk`.

### Task 5: Remove the marker-provenance red from `hook-entries`

**Files:**
- Modify: `src/stayfixed/doctor/entries.py` (`_MARKED`, `_MARKED_ELSEWHERE`, `WRITTEN`, `_marked`,
  `_marked_elsewhere`, the marker branch of `_classify`, and whatever of `_UNCHECKED`, `_HIDDEN` and
  `_BLIND` keys only on the marker or on `written`), `docs/cli.md`
- Test: `tests/doctor/test_checks.py`, `tests/attach/test_doctor.py` (the remedy text "takes back the
  ones an earlier release recorded in its ledger")
- Mutations: `mutations/doctor.toml`:
  - "hook-entries reads a marked entry in a file stayfixed writes as a warning";
  - "a marked entry in a file stayfixed does not write is red";
  - "hook-entries says nothing of a marked command the walk skipped".

**Interfaces:**
- Produces: an entry carrying stayfixed's marker is counted as stayfixed's wherever it sits, with no
  red and no warning about where it sits. Foreign entries are counted and named as today.
- Consumes: Task 4.

- [ ] **Step 1: Write the failing test.** Add
  `test_a_marked_entry_in_any_settings_file_is_counted_and_not_red` to `tests/doctor/test_checks.py`:
  a marked entry in a file stayfixed does not write gives status OK and is counted among stayfixed's
  entries.
- [ ] **Step 2: Run and watch it fail.** Run `uv run pytest -q tests/doctor/test_checks.py -k marked_entry`.
  Expected: FAIL, since the row is red today.
- [ ] **Step 3: Delete the provenance branches and their tests and mutation entries.**
  - Before deleting `_UNCHECKED`, `_HIDDEN` or `_BLIND`, read each. A branch that reports something
    other than marker placement stays, and the pull request names it.
  - Edit the remedy text in both test files, and the `docs/cli.md` prose.
  - Name `src/stayfixed/assess/probes.py`'s `foreign-hooks` probe in the pull request body for the owner, without
    touching it.
- [ ] **Step 4: Run and watch it pass.** Run `uv run pytest -q tests/doctor tests/attach/test_doctor.py`.
  Expected: PASS.
- [ ] **Step 5: Commit:** `refactor(doctor): hook-entries no longer judges where a marked entry sits`.
  Then add the fragment `changelog.d/+frontmatter-walk.change.md`, covering both tasks.

**Before the push (Wave C):** as for Wave A. Then open the pull request.

---

## Wave D — Tasks 6–8 (CL9, branch `cleanup/back-compat`, after Wave C has merged)

**Pre-flight (controller, before dispatch):** read the `version` key of `trust.json` beside the
owner's machine file on each of the owner's machines, and paste it. Expected: `1`. A flat map, with
no `version` key, means that machine needs one `memory promote` first, and Task 6 waits for the
owner's word.

### Task 6: The trust record reads version 1 only

**Files:**
- Modify: `src/stayfixed/trust/record.py` (the flat-map branch of `recorded`, `NOT_A_RECORD`'s
  wording, the docstrings, and `Approval`'s "empty for 0.3.0"), `src/stayfixed/trust/commands.py`
  (the `'before 0.4.0'` wording)
- Test: `tests/trust/test_record.py`
- Mutations: `mutations/core.toml`, "a trust record with approvals and no version reads as 0.3.0's
  flat map"

**Interfaces:**
- Produces: `recorded(machine)` refuses a document with no `version` key, through the same refusal
  as any other non-record (`NOT_A_RECORD`), and never overwrites it.
- Consumes: nothing.

- [ ] **Step 1: Write the failing test.** Add `test_a_flat_map_with_no_version_is_refused_and_kept`
  to `tests/trust/test_record.py`. It asserts that the refusal's message names the path, and that
  the file's bytes are unchanged afterwards.
- [ ] **Step 2: Run and watch it fail.** Run `uv run pytest -q tests/trust/test_record.py -k flat_map`.
  Expected: FAIL, since today `recorded` returns `{}`.
- [ ] **Step 3: Delete the branch.**
  - Delete `test_a_0_3_record_holds_no_approval_and_the_first_write_replaces_it`,
    `test_0_3_0s_reader_sees_no_approval_in_a_version_1_record`, `legacy_reader`, and the
    `no-version` case that expected an empty record.
  - Delete the mutation entry.
  - Edit the wording in `src/stayfixed/trust/commands.py`.
- [ ] **Step 4: Run and watch it pass.** Run `uv run pytest -q tests/trust tests/memory`. Expected:
  PASS.
- [ ] **Step 5: Commit:** `refactor(trust): read version-1 records only`.

### Task 7: Remove the `retired-deny` row and the preset's `[deny] retired`

**Files:**
- Modify:
  - `src/stayfixed/doctor/checks.py`: `_retired_deny`, `RETIRED_DENY_REMEDY`, `_SETTINGS_LABEL`
    and the `CHECKS` entry, then re-check the imports;
  - `src/stayfixed/presets/recommended.toml`: `[deny] retired` and its comment;
  - `src/stayfixed/setup/run.py`: the `retired=` parameter of `_write_user_settings` and its caller.
- Modify every pin of `doctor`'s 17 rows, to 16:
  - `README.md` (two places), `skills/doctor/SKILL.md`;
  - `docs/cli.md`: "Seventeen", and "the installation's own twelve" becomes eleven;
  - `.github/workflows/smoke.yml`: the comment and `assert len(rows) == 17`;
  - `mutations/repository.toml`: two `before` anchors.
- Test:
  - `tests/doctor/test_checks.py`: the three `retired-deny` tests, the `REPORT` entry, the counts;
  - `tests/doctor/test_command.py` and `tests/test_install_path.py`: the counts;
  - `tests/setup/test_setup.py`: `test_setup_takes_the_retired_env_masks_back_out_and_keeps_the_owners_rules`;
  - `tests/setup/test_machine.py`: the `deny["retired"]` assertion;
  - `tests/test_documents.py`: add "fifteen" and "sixteen" to `_NUMBER_WORDS`.
- Mutations:
  - `mutations/doctor.toml`: "the retired-deny row names no retired rule" and "the retired-deny row
    raises on user settings that are not JSON";
  - `mutations/install.toml`: "setup leaves the retired deny rules in place".

**Interfaces:**
- Produces: `doctor` reports 16 rows, `CHECKS` has 11 entries, the preset has no `[deny] retired`,
  and `setup` writes no retirement step.
- Consumes: Wave C merged (shared `doctor` files).

- [ ] **Step 1: Write the failing test.** Change the count assertion in `tests/doctor/test_command.py`
  to 16, and add `test_the_preset_has_no_retired_deny_rules` to `tests/setup/test_machine.py`.
- [ ] **Step 2: Run and watch it fail.** Run `uv run pytest -q tests/doctor/test_command.py tests/setup/test_machine.py`.
  Expected: FAIL.
- [ ] **Step 3: Delete the row, the preset key and the setup parameter, with their tests and
  mutation entries.**
  - Move every pin to 16, and add the number words.
  - Re-anchor the two `mutations/repository.toml` entries on the new text.
- [ ] **Step 4: Run and watch it pass.** Run `uv run pytest -q tests/doctor tests/setup tests/test_install_path.py tests/test_documents.py`,
  then `uv run python scripts/mutation_oracle.py`. Expected: PASS, no survivor, no unanchored
  `before`.
- [ ] **Step 5: Commit:** `refactor(doctor): drop the retired-deny row and the preset's retired deny rules`.

### Task 8: Remove the overlay template's retired-files table

**Files:**
- Modify:
  - `src/stayfixed/overlay/template.py`: `_RETIRED`, `retired()` and the `RETIRED_MEMORY_README`
    import;
  - `src/stayfixed/overlay/layout.py`: `RETIRED_MEMORY_README`;
  - `src/stayfixed/overlay/upgrade.py`: `shipped = [*templates(), *retired()]` becomes `templates()`;
  - `src/stayfixed/scaffold/engine.py`: the record-less retired branch;
  - `src/stayfixed/scaffold/model.py`: `Template.shipped` and `Template.remedy`, only if nothing
    else reads them;
  - `docs/cli.md`: the `overlay upgrade` paragraph about four removed files.
- Test: `tests/overlay/test_upgrade.py` (the retired constants and tests),
  `tests/overlay/test_template.py` (`test_no_retired_file_is_one_the_template_ships`)
- Mutations:
  - `mutations/install.toml`: the five template-digest entries;
  - `mutations/scaffold.toml`: the five "retired overlay file" entries.

**Interfaces:**
- Produces: `overlay upgrade` plans the shipped template files only. A file `_RETIRED` used to name
  is left alone wherever it is.
- Consumes: nothing beyond Task 7's commit.

- [ ] **Step 1: Write the failing test.** Add `test_upgrade_plans_nothing_for_a_formerly_retired_file`
  to `tests/overlay/test_upgrade.py`: an overlay holding the retired memory README (the path `RETIRED_MEMORY_README`
  names) with the 0.2.0 bytes gets no action for it, and the file is unchanged after `apply`.
- [ ] **Step 2: Run and watch it fail.** Run `uv run pytest -q tests/overlay -k formerly_retired`.
  Expected: FAIL, since today it is planned for removal.
- [ ] **Step 3: Delete the table and its plumbing.**
  - Before deleting `Template.shipped` and `remedy`, grep for their readers. If another reader
    exists, they stay, and the pull request says so.
  - Delete the tests and the mutation entries.
  - If the scaffold engine keeps a ledger record for an id no longer listed, file that in the ledger
    and do not fix it here.
- [ ] **Step 4: Run and watch it pass.** Run `uv run pytest -q tests/overlay tests/scaffold`.
  Expected: PASS.
- [ ] **Step 5: Commit:** `refactor(overlay): drop the retired-files table`. Then add the fragment
  `changelog.d/+back-compat.upgrading.md`. It names:
  - the 0.3.x record's refusal;
  - `doctor`'s 16 rows;
  - the preset's removed key;
  - that the owner deletes the four retired overlay files by hand if they are still there.

**Before the push (Wave D):** as for Wave A. Then open the pull request.

---

## Findings

Written by each wave's controller when its pull request merges: the head sha, the net size
(`git diff --shortstat`), the review's findings and their triage, and anything filed.
