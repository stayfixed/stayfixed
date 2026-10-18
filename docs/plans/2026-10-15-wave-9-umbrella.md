# Wave 9 — harness sources, `prove`, profiles as a list: Umbrella Plan

> **For agentic workers:** this plan is not dispatched. It coordinates the wave's lanes, each of
> which has its own plan, its own worktree and its own session; it fixes what crosses a lane: the
> launch graph, the release checkpoints, file ownership and hot spots, the lane-plan items the wave's
> reviews left, the execution contract every lane plan copies into its header, and the wave's
> exit. Its own tasks (Release train and Exit, below) are controller-run with the owner, step by
> step. A lane plan's REQUIRED SUB-SKILL line is superpowers:subagent-driven-development, and its
> header carries the wave-dispatch rule and the section "Execution contract" here, verbatim.

**Goal:** land wave 9 of the extraction design in three releases — `0.4.0` (the value floor,
layered preferences, one trust record, `prove`), `0.5.0` (delivery from the overlay with no trace
in the checkout, memory by layers, onboarding), `0.6.0` (regressions, the `adopt` skill, profiles
as a list) — and check P6's exit on the installed `0.6.0`.

**Architecture:** five lanes in parallel sessions. Harness-sources (HS) is the critical path and
its four pull requests run in order; core-proof (CP) starts with the register engine's list field
(RC1) and `prove`; profiles (PF) follows HS1, HS2 and CP1; the benchmark (BM) and the matcher
spike (SP) touch nothing the plugin ships. Every pull request merges into `dev` when its checks
are green and the launch graph allows, and each release is the owner's checkpoint, cut when its
lanes are on `dev`; HS2, HS3 and HS4 merge into `dev` in that order (amended 2026-10-18 by the owner:
there are no users besides the owner, so no window holds a merge and no integration branch exists).

**Tech Stack:** Python ≥ 3.11 standard library at runtime; `uv`, pytest (`-n auto`), ruff, mypy,
the mutation oracle (`scripts/mutation_oracle.py`), towncrier fragments in `changelog.d/`,
`scripts/release.py`, `scripts/plugin_tree.py`, `scripts/check_artifacts.py`.

**Spec:** the agent-harness extraction design, in a private repository this one cannot link to:
§15.8 (wave 9's decisions 1–45 and C7, settled with the owner on 2026-10-15 in a brainstorm and a
final review, and amended on 2026-10-16 with a second review's rulings), §15.1 (P6's exit), §15.2
(the packages), §15.4 (plans in parallel sessions), §15.5 (the re-plan and its deferred list). A
decision is cited here as "d" and its number. A lane plan's implementer cannot open the spec, so
every value a task needs from it is written into the lane plan itself.

**Scope:** wave 9 as d1 cuts it — packages harness-sources, core-proof (with the slice of
project-record its `regression` field needs) and the profiles row of §15.2, the benchmark's part 1
and final run, and the matcher measurement. A change belongs to this plan iff it fixes something
that crosses lanes: an edge of the launch graph, a release checkpoint, the owner of a file two lanes
touch, a lane-plan item, the execution contract, or the wave's exit. Every change to code belongs
to a lane plan. Out: the `debt` register and the rest of project-record, the TypeScript profile,
the JavaScript and Go profiles' rules and `assess` checks, a mode for a machine holding old copies
(after launch, d1); Codex parity, the metrics report, the visual roadmap and the owner's harness
map (wave 10, d20, d39, d42).

**Premise:** measured on 2026-10-15 at `dev` = `22a9cad` (after `v0.3.0`). 33 commands registered;
`hooks/hooks.json` with 10 entries — 7 `SessionStart` and one each on `PreToolUse`, `PostToolUse`
and `PostToolUseFailure`, all three matching `Bash`; no `Stop` and no `Read` matcher;
`[defaults.memory] mode = "local-only"` in `src/stayfixed/presets/recommended.toml`; a
`stayfixed.toml` the loader refuses makes every `PreToolUse` `Bash` call exit 2
(`src/stayfixed/hooks/commands.py` `_unloadable`); `stayfixed doctor` in a repository with no
`stayfixed.toml` reports `not-initialised` red, and the smoke workflow (`.github/workflows/smoke.yml`)
asserts no red row and the report's row count; `stayfixed upgrade` refuses a checkout with no
manifest (`src/stayfixed/project/upgrade.py`); every CI job runs on GitHub-hosted runners. This is
the tree before HS1, kept as history: HS1 changed three of these (36 commands; a refused
`stayfixed.toml` is a warning, not a refusal; `not-initialised` warns, and `doctor` reports eighteen
rows). Each lane plan measures its own premise against the tree it starts from and stops on a
mismatch there.

---

## Lanes

| Lane | Pull request | Branch | Targets | Plan | Release |
|---|---|---|---|---|---|
| HS | HS1 — the value floor (d4, D-2), key classes and who sets them (d12), layered preferences (d13), the owner's guard switch (d5), budgets (d5, d12), the ratchet rows (d15), one trust record and `stayfixed trust` (d11) | `wp/hs1-floor-layers-trust` | `dev` | `docs/plans/2026-10-15-wave-9-hs1-floor-layers-trust.md` | `0.4.0` |
| HS | HS2 — scopes (d7), binding and confirmation (d8), the allowlist record (d9), pins (d10), the rendered plugin (d17), pinned rules (d19), Codex and worktrees (d20), `doctor --footprint` (d21), `attach`/`detach` (d22), where a tightening applies (d16) | `wp/hs2-delivery` | `dev` | `docs/plans/<date>-wave-9-delivery.md` (create), one plan for HS2, HS3 and HS4, written after HS2's measurements (d18) | `0.5.0` |
| HS | HS3 — `harness` by default (d14), the composed store (d23), in-repo notes (d24), `local-only` (d25), the reviewed record (d26), the index (d27), the durable-note guard (d28), the memory doctor (d29) | `wp/hs3-memory` | `dev` | the same plan | `0.5.0` |
| HS | HS4 — scopes in the template (d7), `setup --overlay` (d30), the overlay's identity (d31), migration through `attach` (d32), the guided `init` (d33), the scaffold rename (d21) | `wp/hs4-onboarding` | `dev` | the same plan | `0.5.0` |
| CP | RC1 — the list field with quoted items, read-only (d39) | `wp/rc1-list-field` | `dev` | `docs/plans/2026-10-18-wave-9-cp-proof.md`, one plan for RC1, CP1 and SP | `0.4.0` |
| CP | CP1 — the report readers, the five runner adapters, `prove`, evidence records (d34, d35) | `wp/cp1-prove` | `dev` | the same plan | `0.4.0` |
| CP | CP2 — regressions (d36) | `wp/cp2-regressions` | `dev` | `docs/plans/<date>-wave-9-release-0-6.md` (create), one plan for CP2, CP3, PF1 and PF2, written once HS4 has merged into `dev` | `0.6.0` |
| CP | CP3 — the `adopt` skill and BR-010 (d37) | `wp/cp3-adopt` | `dev` | the same plan | `0.6.0` |
| PF | PF1 — profiles as a layered list with detection (d38) | `wp/pf1-profiles` | `dev` | the same plan as CP2's | `0.6.0` |
| PF | PF2 — profile context delivered (d38) | `wp/pf2-profile-context` | `dev` | the same plan | `0.6.0` |
| BM | benchmark part 1, then the final run (d40) | `wp/bench` | `dev` | the wave-7 side-lanes plan's Lane 2, rewritten in place against the tree | any |
| SP | the matcher measurement (d41) | `wp/matcher-spike` | `dev` | the RC1 and CP1 plan, Wave J | any |

A lane plan is written in its lane's session from §15.8, this plan and the section "Lane-plan
items" below, and it cites the decisions by number. The delivery plan is written only after HS2's
four measurements (d18) are recorded, because two of them choose a mechanism.

**Amended 2026-10-18 by the owner:** the remaining lanes share three plans instead of six — RC1, CP1
and SP in one; HS2, HS3 and HS4 in one, since they reach `dev` one after another for one release; CP2,
CP3, PF1 and PF2 in one, since they land in one release and share `src/stayfixed/config/`,
`src/stayfixed/doctor/` and `src/stayfixed/assess/rule.py`. A plan still dispatches by waves and
opens one pull request per row; the pull requests and branches are unchanged.

## Launch graph

Drawn over the imports and the Interfaces blocks each lane plan names, never over file lists
alone. An edge means "merged into `dev`".

```mermaid
graph LR
  HS1 --> HS2
  HS1 --> HS3
  HS2 --> HS3
  HS2 --> HS4
  HS3 --> HS4
  HS1 --> PF1
  HS2 --> PF1
  CP1 --> PF1
  HS2 --> PF2
  PF1 --> PF2
  RC1 --> CP2
  HS1 --> CP2
  HS2 --> CP2
  CP1 --> CP2
  CP1 --> CP3
  HS4 --> CP3
```

What each edge carries:

- **HS1 → HS2, HS3, CP2, PF1.** `stayfixed.trust` (the record, `ApprovalKind`, the `approvals.py`
  discovery convention, the `trust` commands), `stayfixed.config.classes` (`KeyClass`, `ALLOWED`,
  `class_of`, `resolve`), `stayfixed.config.owner` (`Owner`, `resolve_owner`) and
  `stayfixed.config.session` (`SessionConfig`, `session_config`). HS2 adds the
  `overlay` and `checkout` kinds and wires the overlay's three layers into `resolve`; HS3 rewrites
  the `memory` kind and removes the `memory trust` alias; CP2 adds the `regressions` kind; PF1
  makes `profiles` a layered preference with a union merge. As HS1 shipped, `resolve` decides who
  may set a key and gives doctor's `preferences` row its provenance, while the loader still builds
  `Config`'s values: HS2's first task builds the preference and session values from a `Resolution`
  and carries the provenance on `SessionConfig`, so doctor stops deriving it a second time. HS1 also
  ships `stayfixed.config.reading` (the names both loaders share), `ApprovalKind.flags` as a mapping
  of flag to help text, the layer names `OVERLAY_COMMON`, `OVERLAY_PROJECT`, `OVERLAY_MACHINE`, and
  `stayfixed.trust.boundary` (amended 2026-10-17: after the narrowing, the sandboxed-write refusal
  and the spellings `setup --approval-boundary` prints; doctor reads no settings for it).
- **HS2 → HS3.** The binding id, the confirmed checkout and the machine data directory's layout;
  HS3's pointer to the composed store is whatever HS2's measurement of an absolute
  `autoMemoryDirectory` chose.
- **HS2 → CP2.** A confirmed checkout, which a local regressions run requires (d36).
- **HS2 → PF1.** The overlay's layers, in which a profile may be enabled.
- **HS2, HS3 → HS4.** `attach` as the migration's entry and the reviewed record the migration
  promotes into.
- **CP1 → PF1, CP2, CP3.** The runner-adapter protocol PF1 lists beside a profile, `prove`'s
  verdicts CP2 requires of a regression, and the evidence records. In `0.4.0` an evidence record is
  keyed by a digest of the normalised `origin`, else of the checkout's real path; HS2 adds the
  binding id as the first key.
- **RC1 → CP2.** `regression`'s list grammar.
- **HS4 → CP3.** `init`'s guided walk, whose last step offers the `adopt` skill.
- **HS2, PF1 → PF2.** The `paths:` handler on `PostToolUse` for `Read`, `Edit` and `Write`, and
  active profiles.

## Release train

A release is cut on `origin/main` from `dev` by `RELEASING.md`, so whatever is on `dev` when it is
cut ships. Amended 2026-10-18 by the owner: there are no users besides the owner, so no window holds
a merge. Each pull request merges into `dev` when its checks are green and the launch graph allows;
the releases are the owner's checkpoints, each cut once its lanes are on `dev`.

| Release | Cut once these are on `dev` | Then |
|---|---|---|
| `0.4.0` | RC1, CP1, HS1 | Task 1 |
| `0.5.0` | HS2, HS3, HS4, and the migration seat has passed on `dev` | Task 2 |
| `0.6.0` | CP2, CP3, PF1, PF2 | Task 3, then Tasks 4–5 |

A lane of a later release that lands first ships in the earlier release cut after it, which is
harmless with no users; BM and SP touch nothing `scripts/plugin_tree.py` puts in the plugin. A pull
request's checks are read with `gh pr checks` on its own head after the latest `dev` has come into it
by `git merge origin/dev`, since a push to `dev` re-runs no open pull request's checks and `ci.yml`
runs on `push` to `main` only.

## File ownership and hot spots

A file two lanes touch has one owner at a time, in merge order; the other lane rebases on it. Every lane writes
its own changelog fragments, its own `docs/cli.md` sections and its own mutation entries, appended
to the group file `scripts/mutation_oracle.py` `GROUP_OF` routes them to.

| File or area | Owner, in order | Note |
|---|---|---|
| `hooks/hooks.json`, `hooks/hashes.json` | HS2 (the `PostToolUse` `Read\|Edit\|Write` handler), HS3 (the durable-note guard) | no other lane registers an entry |
| `hooks/run-hook.sh`, `pyproject.toml`, `.claude-plugin/`, `.codex-plugin/` | the release tasks only | |
| `src/stayfixed/hooks/commands.py`, `src/stayfixed/hooks/dispatch.py` | HS1, then HS2 | |
| `src/stayfixed/config/` (`schema.py`, `loader.py`, `session.py`, `classes.py`) | HS1, then HS2 (overlay layers), HS3 (`harness`), PF1 (`profiles`), CP2 (`gates.regressions`) | each rebases on the last; the class-table test fails a field added without its class |
| `src/stayfixed/presets/recommended.toml` | HS1 (budgets), HS3 (drops `[defaults.memory] mode`), HS4 (`attribution_check` default) | |
| `src/stayfixed/assess/rule.py` | HS1, then PF1 (the `profiles` union row), CP2 | |
| `src/stayfixed/trust/` | HS1, then HS2 (`overlay`, `checkout`), HS3 (`memory`), CP2 (`regressions`) | |
| `src/stayfixed/memory/trust.py` | HS1 (the record moves to core), HS3 (the reviewed record) | |
| `src/stayfixed/ledger/` | RC1, then CP2 | |
| `src/stayfixed/profiles/` | CP1 (adapters under `profiles/python/`, `profiles/javascript/`, `profiles/go/`), PF1 (the model and the list) | per pull request (§15.4) |
| `src/stayfixed/project/`, `skills/init/` | HS3 (`upgrade`'s memory migration), HS4 (the walk), PF1 (the profile step; rules released from the manifest), CP3 (the adopt step) | a chain: each quotes the previous lane's text it rewrites |
| `src/stayfixed/setup/` | HS1 (`--approval-boundary`, advice only), HS4 | |
| `src/stayfixed/templates/overlay/`, `scripts/check_artifacts.py`, `ci.yml`'s overlay-render step | CP1 (the adapters in `WHEEL_MUST`), then HS4 | `overlay create` and `overlay init` retire into `setup --overlay` |
| `src/stayfixed/doctor/`, `tests/doctor/test_command.py`, `.github/workflows/smoke.yml`, `scripts/smoke_hooks.py` | HS1 → HS2 → HS3 → HS4 → CP2 → PF1 | **hot spot**: each lane that adds or renames a `doctor` row or a hook entry updates the smoke workflow's row and entry counts and quotes the previous lane's numbers in its plan |
| `.github/workflows/check.yml`, `tests/test_check_workflow.py` | CP1 (the evidence upload), CP2 (the regressions step) | |
| `.github/workflows/ci.yml` | CP1 (the `runners` job), HS4 (the overlay-render step) | |
| `src/stayfixed/assess/commands.py`, `src/stayfixed/assess/gates.py` | CP1 (the gate's record; `kill_group` moves to `src/stayfixed/processes.py` (create)), then CP2 | |
| `docs/cli.md`'s `gate` section | CP1 (its record), CP2 (regressions) | |
| `README.md`'s machine-files table | HS1, CP1 (the evidence directory), HS2, HS3 | **hot spot**: each lane quotes the previous lane's rows |
| `tests/boundaries/test_delivery.py`, `tests/test_language_neutral.py` | CP1 (the adapter discovery, `xml.parsers.expat`), then PF1 | |
| `README.md` network table, `tests/outbound/policy.py` | CP1 (`prove`'s launches), CP2 (regressions), HS2 (`claude plugin install`), HS4 (`gh`) | |
| `README.md`, `docs/cli.md`: "footprint" → "scaffold" | HS4 | one mechanical commit inside HS4's pull request; the `footprint` category goes with no alias |
| `skills/` | each skill's lane: `trust`-related wording HS1, `attach` HS2, `init` HS4, `adopt` CP3 | |

**Old spellings** (amended 2026-10-18 by the owner, against d3's one release of aliases: there are
no users besides the owner): a pull request that renames a command, a flag or a configuration key
removes the old spelling in the same pull request. `memory trust`, which HS1 kept and no release has
shipped, goes in HS3; `overlay create`, `overlay init` and the `footprint` category go in HS4, which
replaces them; `profile` becomes `profiles` in PF1.

## Lane-plan items

What the wave's two reviews found that a lane plan must carry and §15.8 does not spell out. Each
lane plan cites the ids it takes.

| Lane | Items |
|---|---|
| HS1 | Carried in the HS1 plan. |
| HS2 | Measure before fixing tasks: copy or in place [P-HS-1]; an absolute `autoMemoryDirectory` in a main checkout and its worktrees [F5, N4]; worktree and desktop worktree sessions [P-HS-22]; a committed `enabledPlugins` for a directory marketplace [O-7]. Then: `attach` refuses a tracked or foreign-written `settings.local.json` [B-7]; the exclusion in `.git/info/exclude`, written before `plugin install` [P-HS-15, C-40]; `detach` versus a shared slug [BR-027, P-HS-21]; the path-rule handler on `Read\|Edit\|Write`, once per file per session [U-9]; `attach` shows the binding and the diff on one screen, and `common/` pins are approved once per machine [U-17]; `attach --trust-remote` retires into `trust approve checkout`, with no alias [X-24]; the `overlay` kind takes one subject per pinned part and one for the rule set [N-21]; the overlay's node id is re-checked by `attach` and `doctor` when its `HEAD` moved, with one `SessionStart` line until then (D-1). |
| HS3 | The expected digest set comes from an independent `os.walk` (nested, non-`.md`, dotfiles, symlinks) [O-20]; worktree-link fixtures with differing stores and the bare-repository "cannot tell" case [O-19]; one fixture with both kinds of index line [O-21]; native top-level topic files indexed and their pointer lines kept [N3]; the reviewed-record tests: a note written through the shell is unreviewed, promote marks it, a killed session leaves it unreviewed [F2, O-22]; the loader keeps `local-only` for a `stayfixed.toml` older than `0.5.0` [N-4]; remove the `memory trust` alias. |
| HS4 | BR-018's three cases and `_populated`'s replacement [P-HS-18]; map the overlay's `machine/` to `machines/<name>/` [P-HS-19]; remove the old overlay plugin and its marketplace [C-41]; one user entry for creating an overlay [U-18 of the first review]; the README outbound row for `gh` [P-HS-20]; the guided walk's four-line texts in `init --questions --json`, `agents` detected, `attribution_check` and commit types asked, `setup`'s plugin installs opt-in, nothing of the user's `pluginConfigs` or comments overwritten [N5]; the skip path's defaults: attribution check off, the conventional commit types, no recommended plugins [N-18]; the scaffold rename [O-8]. |
| RC1 | Capture literals for `bugs new`'s entry, `bugs check` (text and `--json`) and `renumber` before touching the engine, from the tree rather than the `v0.3.0` tag (owner, 2026-10-18) [O-23]; quoted list items for `regression` [P-CP-17]. |
| CP1 | The JUnit reader counts testcases (the node dialect; predefined entities allowed; `record_xml_attribute`) [P-CP-6]; vitest's default output lies inside the repository, and its configuration-against-CLI precedence is measured [P-CP-7]; recognition of `npx` and `poetry run`, with `npm test` → `not proven` [P-CP-8]; the `jest`/`vitest` words against `tests/test_language_neutral.py` [P-CP-9]; per-reader empty and all-skipped fixtures, including `go test -run NoSuchTest` [O-13]; each forging route as a test (test2json framing, `TestMain` with `os.Exit(0)`, an `atexit` rewrite, an untracked `conftest.py`, `-exec`, environment injection, a realpath that differs); an argv or variable the run's own invocation sets explicitly is `refused`, one merely inherited is scrubbed [N-13]; the evidence record's `0.4.0` key; jest's `--passWithNoTests` and vitest's reporter precedence measured first. |
| CP2 | The evidence upload needs `if: always()`, an explicit exception to the judging step's rule [P-CP-11] (built by CP1, which CP2 inherits); regressions in the project's-own-gates step [F9]; the project key for an unbound checkout [C-39]; the merge-base control fixture commits before the branch point [N-23]; `regressions` is not added to the preset's default `builtin`. |
| CP3 | The `adopt` skill as the last step of the full `init` walk [O-3d]; BR-010. |
| PF1 | Profiles as a layered list with detection, the union merge in `resolve`; committed rules files released from the manifest, which `upgrade` owns today; detection picks several, not one [P-CP-20]; `profile` renamed with no alias. |
| PF2 | Profile context through `SessionStart` and the path-rule handler. |
| BM | Rewrite the side-lanes plan's stale steps: `scripts/release.py check`; the existing `mutations/repository.toml`; the retired 512-file limit; the existing `tests/test_payload.py`; the final run built with `scripts/plugin_tree.py` [P-CP-22]. Every paid run waits for the owner's yes. |
| SP | Both paths (`PreToolUse` on `Skill`, `UserPromptExpansion` on `/skill`); define a skill invocation on Codex [P-CP-23]. |

## Execution contract

Every lane plan carries this section in its header, verbatim, and the controller copies the
relevant part into every brief, post-pull-request dispatches included.

1. **The wave is the dispatch unit.** Waves are lettered and own a run of continuously numbered
   tasks; one implementer, one review round and one reviewer per dispatched wave, every task
   keeping its own failing test, verification and commit. An implementer's first pass is sized
   for about 200k tokens: at most about 900 plan lines and three tasks per wave. Resume the same
   implementer for a fix round only while its context is under about 300k; past that, the round
   goes to a fresh agent with the review package. The controller records each implementer's token
   total in the plan's Findings. Every subagent runs on Opus (`model: opus`).
2. **Every implementer brief says:** report a mismatch with the tree instead of guessing; run a
   command and paste what it printed before writing any claim about it; focused runs while
   iterating, and before the commit one full run of `uv run pytest -n auto --cov
   --cov-fail-under=92` with `uv run python scripts/release.py check`; before a push, the suite
   again on Python 3.13 and 3.11.4 (`uv run --python <version> pytest -n auto`); a plan's predicted
   mutation outcome is a hypothesis — design your own if it does not redden, and paste the raw
   output either way; no line numbers from the plan; this brief is a message, not a file, so cite
   only the plan; write nothing under the repository but the task's files, use
   `<scratchpad>/<wave>-<role>/`, never run a script you did not write, and read `git diff --stat`
   before committing; the static checks at CI's scope (`uv run ruff check .`,
   `uv run ruff format --check .`, `uv run mypy`); do not use the Agent tool; do not run
   `git checkout`, `restore`, `stash` or `clean`; start a long run in the background and wait on
   its own output, never with `pgrep`.
3. **Every reviewer brief adds:** run every command yourself and never use the Agent tool; do not
   run `git checkout`, `restore`, `stash` or `clean`; what already passed, by sha and suite, and run
   only the test that decides a finding you suspect; no citation may point at a brief, a dispatch
   or a report; what later tasks own.
4. **The final review** of each pull request is at least four parallel read-only seats:
   correctness, architecture, security, and a lifecycle seat that walks section 5 of this contract
   against the diff.
5. **The lifecycle matrix**, walked at pre-flight like a task and again by the lifecycle seat:
   every command the pull request adds or changes × every change of configuration — set a value,
   change it, unset it, move a path, a step that fails part-way, `uninstall` — and, from HS1 on, ×
   every layer that can carry the value (preset, repository, the overlay's three scopes, the
   machine file).
6. **The parallelism map.** Read-only seats run beside each other and beside the implementer;
   writers of one worktree serialise; one heavy local run (the full suite, the mutation oracle) at
   a time per host; no local full run while the same branch's CI runs.
7. **Templates.** A fix brief enumerates the sibling instances of the defect's class (the
   `sweep-defect-class` skill) and reports the neighbour probes it ran. A security ruling names its
   minimal preconditions, its anchor's provenance (who can write the bytes it trusts), and one
   legitimate user it must not refuse.
8. **Verification.** The controller re-verifies only heads it pushes or merges, re-derives the pull
   request's body from the diff before every push, takes the run id from `gh pr checks` and waits
   with `gh run watch <run-id> --exit-status` until every job has ended (never a `head_sha` query,
   which finds no run for a pull request's merge ref) before reporting a pull request done.
9. **Second finding at one seam.** At the second review finding that points at the same function,
   reader or boundary, the next step is a redesign of that seam put to the owner, not a third patch.

## Release train tasks

The owner runs every push of a release (the commits, the tags, `scripts/publish_plugin.py`) and
approves the `pypi` deployment in GitHub's web interface. The controller runs only checks,
read-backs and dry runs, and never calls the pending-deployments API.

### Task 1: Cut `0.4.0` (controller, with the owner)

- [ ] **Step 1:** when RC1, CP1 and HS1 have merged into `dev` and `gh pr checks` read every job
  green on each, run `uv run python scripts/release.py check` on `dev` — `RELEASING.md`'s first
  step, run once over the release — and paste its output into Findings.
- [ ] **Step 2:** the owner follows `RELEASING.md` for `0.4.0`; the changelog's upgrading section
  names `memory trust` → `trust approve memory` (asked of a person at a terminal; the old spelling
  stays until HS3 removes it), the guards that run without `stayfixed.toml`, `stayfixed prove`, and
  a session that warns where it refused.
- [ ] **Step 3:** with `0.4.0` installed on the owner's machine, `stayfixed doctor --json` reads
  `0.4.0` for both the CLI and the plugin; paste the two values into Findings.

### Task 2: The delivery set and `0.5.0` (controller, with the owner)

- [ ] **Step 1:** when HS2, HS3 and HS4 have merged into `dev`, run a migration seat against `dev`'s
  head, beside HS4's own final review. The migration seat is a writer: it runs d32's `attach` on a
  copy of the owner's overlay and two copies of attached checkouts, under an isolated `HOME`,
  `CLAUDE_CONFIG_DIR`, `XDG_CONFIG_HOME` and `GIT_CONFIG_GLOBAL`, never the owner's real
  installation, and no other writer runs while it does. Until it passes, the owner cuts no release
  from `dev`.
- [ ] **Step 2:** the owner cuts `0.5.0` by `RELEASING.md`; the upgrading section names the run of
  `stayfixed attach` that migrates an attached checkout, the one promote of the existing notes, and
  the spellings that are gone (`memory trust`, `overlay create`, `overlay init`).

### Task 3: Cut `0.6.0` (controller, with the owner)

- [ ] **Step 1:** when CP2, CP3, PF1 and PF2 have merged, the owner cuts `0.6.0` by `RELEASING.md`;
  the upgrading section names the rename `profile` → `profiles` and the opt-in
  `[gates] regressions`.
- [ ] **Step 2:** with `0.6.0` installed on both of the owner's computers, paste each one's
  `stayfixed doctor --json` versions into Findings.

## Exit

### Task 4: P6's exit on the installed `0.6.0` (controller, with the owner)

**Files:**
- Create: `tests/fixtures/p6/README.md` (create) — the two repositories below and the commands,
  with no private design id in it, since it lies outside `docs/plans`.

The oracle is fixed now, before HS2 is written, so the subject never chooses it (d44):

- **The public clone:** `anthropics/claude-code` at its commit of 2026-10-15T19:21:45Z
  (`03b5892ee77de289bcd5dfa39f541525ade74aff`), which tracks a `.claude/` directory and has no
  `stayfixed.toml`. At that commit it tracks only `.claude/commands/*.md`, with no `!` negation and
  no tracked settings file, so d44's negation and settings properties live in the fixture below;
  the owner confirms that split in Step 1, or names another public repository.
- **The negation fixture:** a repository the step builds with `git init`, whose tracked
  `.gitignore` holds `.claude/*` then `!.claude/settings.json` and `!.claude/rules/`, with a tracked
  Claude Code project settings file — the `!` negations a public repository may carry, which beat an exclude
  line.

Before any `claude` run in a clone, read its tracked Claude Code files and pin their digests in
Findings: a `claude` session in a clone runs its committed hooks, `env`, `statusLine` and MCP
servers. Where the step needs only a `SessionStart`, it drives one with
`stayfixed hook SessionStart` and a crafted payload instead.

- [ ] **Step 1: The isolated machine.** Set `HOME`, `CLAUDE_CONFIG_DIR`, `XDG_CONFIG_HOME` and
  `GIT_CONFIG_GLOBAL` to directories under the scratchpad and `GIT_CONFIG_NOSYSTEM=1`; install
  `0.6.0` there; create a scratch overlay with `stayfixed setup --overlay <path>`, holding a canary
  rule in `common/` and one in `projects/<name>/`, a canary skill and one pinned hook; approve its
  parts and the binding with `stayfixed trust approve` run under a pseudo-terminal by the owner;
  record the owner's word on the clone and the fixture split above.
- [ ] **Step 2: Each repository.** Run `git status --porcelain=v1 -z -uall` and
  `sha256sum .git/info/exclude` before `attach`; after `attach` and one `SessionStart`; after
  `detach`. Expected: every status empty; the exclude digest after `attach` differs from the
  empty-file digest, and `git check-ignore -v` names `.git/info/exclude` for each placed path; the
  digest after `detach` equals the one before `attach`; `stayfixed doctor --footprint` exits 0
  after `attach`; the isolated `installed_plugins.json` holds the rendered plugin's row; the
  `SessionStart` output holds both canaries.
- [ ] **Step 3: The control.** Apply a scratch patch, never committed, that makes `attach` write one
  extra untracked file, and run Step 2 again. Expected: the status after `attach` names that file.
- [ ] **Step 4: The observables (d44)**, each with its expected literal, in Findings:

  | Clause | Observable | Expected |
  |---|---|---|
  | On the installed `0.6.0` | the plugin row's `gitCommitSha`; `command -v stayfixed` | the sha `0.6.0`'s marketplace entry pins; a path under the uv tools directory |
  | The harness arrives | `claude -p --debug-file <file>` in the bound checkout, forced offline with `ANTHROPIC_BASE_URL=http://127.0.0.1:9` and an invalid `ANTHROPIC_API_KEY`, since an isolated `HOME` still reached a credential outside it | both canaries in the logged `SessionStart` context; the canary skill listed; no request succeeded in the log |
  | It runs through the overlay | `stayfixed doctor --json`; the checkout tree; `settings.local.json` | a delivery digest; no `docs/memory` link tree; only entries carrying stayfixed's marker |
  | The second computer restores | `stayfixed trust list --json` and `stayfixed doctor --json`'s preferences on both computers | the same number of approvals on each; the preference tables equal but for `machines/` rows |
  | The owner's projects | a session and a worktree session in each of the owner's two projects | both canaries in each |

### Task 5: core-proof's acceptance and the record (controller)

- [ ] **Step 1:** run the acceptance below on the installed `0.6.0`, not on a checkout. The tests
  ship only in the sdist, so: unpack the `0.6.0` sdist under the scratchpad; run `npm ci` in its
  `tests/fixtures/prove/node/`, with Node and Go at the CP plan's Task 1 pins; print
  `stayfixed.__file__` and `stayfixed.__version__` from
  `uv tool run --from stayfixed==0.6.0 --with pytest --with pytest-xdist python -I -c …` (Expected: a
  site-packages path and `0.6.0`); then, in the same environment, `STAYFIXED_REQUIRE_RUNNERS=1 python -I
  -m pytest -p no:cacheprovider <ids>` (Expected: every id passes, 0 skipped). Then two smokes of the
  installed binary: `stayfixed prove -- pytest -q` in a scratch project (Expected: exit 0, `proved`)
  and `stayfixed prove -- sh -c 'echo 3 passed'` (Expected: exit 1, `not proven`). Paste the output.

  | Acceptance clause (§15.8, after d37) | Test id |
  |---|---|
  | each reader's genuine passing run is `proved`, exit 0, counts equal a literal | the CP plan's Task 14 table |
  | a stdout-forged run is `not proven` | the same |
  | an empty and an all-skipped run are `failed`, `go test -run NoSuchTest` included | the same |
  | a stand-in runner and each refused forging route are `refused`, exit 2 | the same |
  | the same variable merely inherited is scrubbed and the run still counted | the same |
  | a closed entry whose countable regression passes keeps the gate green, and a passing sibling is not named; a failing regression fails the gate and names its entry | named in the CP2 plan |
  | a base whose regression argv names a countable failing test, edited by the pull request to a countable passing one, stays `failed`; the reverse edit stays green; the same edit committed to the base before the branch point flips the verdict | named in the CP2 plan |

- [ ] **Step 2:** record in Findings the counts before (at `22a9cad`) and after (at `0.6.0`):
  commands registered, hook entries by event, source lines under `src/stayfixed`, mutation entries,
  skills; each lane's implementer token totals; and what wave 10 inherits (Codex parity, the metrics
  report, the visual roadmap, the owner's harness map).

---

## Findings

Written by Tasks 1–5 and by each lane's controller when its pull request merges.
