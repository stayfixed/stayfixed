# Wave 9, HS1 — the value floor, layered preferences, one trust record: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **The wave is the dispatch unit, not the task.** Waves are lettered (`A`, `B`, …) and own a
> run of the continuously numbered tasks. One implementer, one review round and one reviewer per
> **dispatched** wave; inside a wave every task keeps its own failing test, verification and
> commit. Do not dispatch one subagent per task.
>
> **Waves A and F are not dispatched.** A measures Claude Code with the owner at the keyboard;
> F runs the final review seats and opens the pull request. The controller runs both.
>
> **One pull request**, `wp/hs1-floor-layers-trust` into `dev`, in release window R1 of the
> umbrella plan (`docs/plans/2026-10-15-wave-9-umbrella.md`).

**Goal:** a session is never killed by its configuration and the guards work with none; what the
machine owner sets reaches every session, with or without a `stayfixed.toml`; every configuration
key has a class that says who may set it; budgets may be raised by the base branch and the owner;
and every approval on a machine is one versioned record in core, driven by one
`stayfixed trust` family — the foundation HS2, HS3, CP2 and PF1 build on.

**Architecture:** a session builds a `SessionConfig(config | None, owner, warnings)`. `owner` is
what the machine owner controls — `[personal]`, `[guards]` and the session budgets — resolved by
one function from the preset and the machine file whether or not the repository has a
`stayfixed.toml`, so the guards always know the owner's switches. `config` is the project's
configuration, loaded in a NOTE mode in which an unknown key is ignored and an invalid value
resets only that key to the preset, each with a note; it is `None` only when there is no file, or
when the file is a symlink or not TOML. `Config` gains no field. `config.classes` holds one class
per key and which layers may set each class, and `classes.resolve` is the one place a key from a
layer that may not set it is refused. Hook handlers receive the `SessionConfig`. The approval
record moves out of `src/stayfixed/memory/trust.py` into a core package `stayfixed.trust`, still the file
`trust.json`, now versioned; areas contribute kinds through `approvals.py` modules discovered like
`doctor.py`.

**Tech Stack:** Python ≥ 3.11 standard library at runtime; `uv`, pytest (`-n auto`), ruff, mypy,
the mutation oracle (`scripts/mutation_oracle.py`), towncrier fragments in `changelog.d/`.

**Spec:** the agent-harness extraction design, in a private repository this one cannot link to —
§15.8 decisions 4 (the value floor and its shape), 5 (the machine owner's freedom), 11 (approvals),
12 (key classes), 13 (layers), 15 (the ratchet's rows) and 43 (contracts), as amended on 2026-10-16
(the floor's shape, a `doctor` that is not red on a default install, one name `trust`); §5.4
(machine paths, from the password database's home); §9.4 (in-repo notes as data). Every value a task
needs from the spec is written into the task.

**Scope:** pull request HS1 of package harness-sources (licensed changes to C1, C4 and C5 by
§15.8 decision 43). A change belongs here iff it (a) makes a session survive its configuration,
lets the guards run without one, or carries the owner's layer into a session; (b) classes a key
or refuses one from a layer that may not set it; (c) lets the base branch or the owner raise a
budget, or routes `assess.rule`'s rows through the class table; (d) moves the approval record into
`stayfixed.trust` or adds the `trust` family, its kinds, its terminal check, its `ask` rules or the
boundary's `doctor` row; (e) makes `doctor` work and stay non-red with nothing configured; or (f)
restates the documents those changes falsify. Out: the overlay's layers, binding, pins and the
`overlay`/`checkout` kinds (HS2); `harness` memory, the reviewed record and the removal of the
`memory trust` alias (HS3); the commit attribution default (HS4); `profiles` as a list (PF1);
`regressions` (CP2); applying a layer's tightening to a repository gate (HS2, through the rows
Task 7 routes).

**Premise:** measured on 2026-10-15 at `dev` = `22a9cad`. A task that finds one no longer holds
stops and reports the mismatch.

- `src/stayfixed/hooks/commands.py` `run_hook` loads `stayfixed.toml` only when it is a regular
  file; a `ConfigError`, `PathEscape` (a `Refusal`, not a `ConfigError`) or `PathUnasked` reaches
  `_unloadable`, which exits 2 on every event `refuses_on_internal_error` names (`PreToolUse`
  among them); a symlinked file reaches `_linked` with the same verdicts; a `MachineConfigError`
  is re-raised into the generic internal-error arm, which refuses on `PreToolUse`. With no file,
  `config` is `None`.
- `load_preset` (`src/stayfixed/presets/__init__.py`) raises a plain `Failure`, not a
  `ConfigError`, for a preset name this version does not ship, so it reaches the same arm.
- Handlers are `(event, config: Config | None) -> HookResult`. Four return early on `config is
  None`: `_bg_cleanup` and `_test_hygiene` (`src/stayfixed/guards/hooks.py`), `_link_worktree`
  (`src/stayfixed/memory/hooks.py`), `_overlay_status` (`src/stayfixed/attach/hooks.py`). The
  background guard judges only a call whose `tool_input.run_in_background` is `true`; its
  refusals are `SLEEP_REASON` and `LEAK_REASON` (`src/stayfixed/guards/bgcleanup.py`).
- `src/stayfixed/config/loader.py` `loads` refuses an unknown section and `_build` an unknown key
  with `ConfigError`; `[budgets]` and `[gates.custom.*]` refuse unknown keys in their own readers
  (`_budgets`, `_gates`); `_personal` reads the machine file's `[personal]` and raises
  `MachineConfigError`. `tests/config/test_loader.py` holds `HEAD` (`[stayfixed]` with `version`
  and `preset`) and `MINIMAL` (`HEAD` plus `[project] name`).
- `src/stayfixed/assess/rule.py` `_values` walks `fields(config)` and then `fields()` of each
  field's value, so every `Config` field must be a dataclass. Rows: `_budget` for every
  `budgets.*` (lower or equal is tightened, anything else refused), `_enforcement`,
  `_builtin_gates`, `_custom_gate`, `_upgrade`, `_neutral` for five named keys, `_other` for the
  rest (refused while the base enforces anything, noted otherwise).
- `Budgets.effective` is `min(preset, configured)`.
- `src/stayfixed/memory/trust.py` keeps the one approval record, `trust.json` beside the machine
  file: a flat JSON object, resolved store path → digest. `stayfixed memory trust
  --in-repo-memory` writes it; it is called with no terminal in `tests/memory/test_commands.py`,
  `tests/test_install_path.py`, `tests/hooks/test_wrapper.py` and three times in
  `scripts/smoke_exfiltration.py`, and emulated in `tests/scripts/test_smoke_scripts.py`.
- `stayfixed doctor` reports seventeen checks; `CHECKS` in `src/stayfixed/doctor/checks.py` holds
  the core's, first `not-initialised`. With no `stayfixed.toml` that row is red ("the plugin's
  hooks are silent in this repository") and every other row is skipped. The smoke workflow
  (`.github/workflows/smoke.yml`, "doctor on the installed plugin reports no red row") asserts no
  red row and the row count; `README.md`, `docs/cli.md` and `skills/doctor/SKILL.md` say
  "seventeen checks".
- `src/stayfixed/setup/run.py` `_write_user_settings` merges deny rules and `pluginConfigs` and
  never writes `permissions.ask`. The machine file's tables are `[personal]`, `[overlay]`,
  `[machine]` (`src/stayfixed/setup/machine.py` `write_machine` carries unknown tables through).
- Areas are discovered by submodule name (`src/stayfixed/areas.py`), whose docstring names three
  submodules (`commands.py`, `hooks.py`, `doctor.py`).

## Global Constraints

- Runtime imports the standard library only; every write goes through `stayfixed.fsops`; a value
  the repository wrote is printed through `stayfixed.printed`, never raw (`CONTRIBUTING.md`).
- The machine's home is the password database's (`config.machine.passwd_home`), never `HOME` or
  `XDG_*` from the environment; the trust record is `trust.json` beside the machine file, never in
  an overlay.
- A hook's exit code is 0 or 2; `PreToolUse` refuses only when a guard decides to, never because
  a configuration file, the machine file or a preset name did not load.
- An invalid value resets that one key to the preset, with a note; the whole project
  configuration is dropped only when the file is a symlink, is not UTF-8, cannot be read, or is
  not TOML. A containment failure resets the value, never the session. Amended on 2026-10-16 by
  the owner's ruling on wave B's review (the NOTE retry's seam): a key whose reset leaves nothing
  usable — a required key with no default, or a preset value that itself fails containment in this
  repository — makes the NOTE load raise one typed refusal naming that key, decided before any key
  is removed (a key is removed only when a fallback exists), and the session falls back to the floor
  whole with a warning naming the key; the guards still run on the preset and the owner's layer.
- `Config` gains no field: `assess.rule` compares configurations field by field.
- Core never imports a delivery area (`attach`, `memory`, `overlay`); `tests/boundaries/` holds it.
  A kind a delivery area owns reaches core through discovery.
- Approvals hold against repository bytes and a `git pull`, never against an agent with an
  unsandboxed shell; the terminal check is a speed bump, and the harness's sandbox is that
  agent's boundary, which stayfixed does not check (amended 2026-10-17: Task 10's ask rules and
  doctor row were cut). `attach`, `upgrade` and `--yes` never approve. `revoke` needs no
  terminal: it is the fail-safe direction.
- `doctor` is not red on a default install: with nothing configured it warns.
- Every new assertion ships with the mutation that reddens it, in the group file
  `scripts/mutation_oracle.py` `GROUP_OF` routes its source to (`src/stayfixed/` → `core`;
  `memory/`, `docs/`, `ledger/` → `records`; `setup/`, `overlay/` → `install`; `doctor/` → `doctor`;
  `assess/` → `assess`; `guards/` → `guards`; `attach/` → `attach`), or a sentence saying why none
  exists. A test asserting a refusal asserts its exact constant, never a substring the input
  already contains.
- Each task restates the documents its change falsifies, following "Shipped sentences" below, and
  writes its changelog fragment in `changelog.d/` in the same commit.

## Shipped sentences

A sentence several tasks rewrite is a chain: each task quotes the previous task's "to" as its
"from". `tests/test_documents.py` holds the doctor count; Task 9 adds a test that holds every shipped
document's mention of `memory trust` to its alias note.

| Sentence | Where | Task | From → to |
|---|---|---|---|
| The guards have no switch | `README.md`, "What each agent enforces" | 3 | "stayfixed has no switch that turns a guard off" → "the machine owner may switch a session guard off in the machine file; a repository never can" |
| The guards without configuration | `README.md`, "What each agent enforces"; `docs/cli.md`, the `hook <event>` section | 5 | an unloadable `stayfixed.toml` refuses → the guards run on the preset and the owner's layer; one warning at `SessionStart` |
| `not-initialised` | `src/stayfixed/doctor/checks.py`; `docs/cli.md`'s `doctor` table | 6 | "the plugin's hooks are silent in this repository" (red) → what works without configuration (warn) |
| The doctor count | `README.md` (two lines), `docs/cli.md` ("Seventeen checks", "Ten of the seventeen"), `skills/doctor/SKILL.md`, `.github/workflows/smoke.yml` | 6 | seventeen → eighteen (`preferences`, Task 6); Task 10's nineteenth row was cut on 2026-10-17 |
| Budgets are only lowered | `docs/cli.md` ("a project may lower a preset's budget, never raise it"; "A budget is only ever lowered"); `CONTRIBUTING.md` ("preset and never raise") | 7 | → the base branch and the owner raise or lower; a pull request lowers a gate's budget only |
| The trust record | `README.md`'s machine-files table; `docs/cli.md` | 8 | a flat map of approvals → a versioned record of kinds and subjects, same file |
| `memory trust` | `README.md`, `docs/cli.md`, `SECURITY.md`, `CONTRIBUTING.md`, `docs/methodology/principles.md`, `src/stayfixed/config/machine.py`, every refusal sentence under `src/stayfixed/` | 9 | `stayfixed memory trust --in-repo-memory` → `stayfixed trust approve memory`, run by a person at a terminal; the alias noted once |
| `codex-trust` | `src/stayfixed/doctor/checks.py`; `docs/cli.md` | 9 | → `codex-hooks` |

## Execution contract

Copied verbatim from the umbrella plan, "Execution contract"; the controller copies the relevant
part into every brief.

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

## Review Focus

Inputs no task would exercise unless told to; each line's test is in the task named.

1. **A `stayfixed.toml` from a newer release** — an unknown section, an unknown key and an unknown
   enum value (`[memory] mode = "harness"`) together. Expected: `ls` allowed; the background guard
   still refuses a backgrounded `sleep`; the project's other settings (a raised budget, a `[paths]`
   value) survive; one warning at `SessionStart`, worded "written by a newer stayfixed" when its
   `version` is later than the running one. Task 4 and Task 5.
2. **A broken machine file** (not TOML) during a session. Expected: the guards run on the preset's
   owner values; the warning names the machine file. Task 3 and Task 5.
3. **A repository with no `stayfixed.toml` and a machine file saying `[guards] bg_cleanup =
   false`.** Expected: the guard is off; the same command with no `[guards]` is refused. Task 5.
4. **`trust.json` from `0.3.0`** (a flat map), then a `0.3.0` reading the record `0.4.0` wrote.
   Expected: every recorded memory approval answers approved on `0.4.0`; `0.3.0` reads no approval
   and asks again, never a stale one. Task 8.
5. **`stayfixed trust approve memory` from an agent's shell tool** (stdin not a terminal, through a
   real subprocess). Expected: exit 2, `NOT_A_TERMINAL`, no byte written; under a pseudo-terminal,
   exit 0. Task 9.

---

## Waves

| Wave | Tasks | Dispatched | Plan lines (approx.) |
|---|---|---|---|
| A | 1 | no — controller and owner | 50 |
| B | 2–4 | yes | 280 |
| C | 5–6 | yes | 200 |
| D | 7–9 | yes | 300 |
| E | 10 | yes | 70 |
| F | 11 | no — controller | 30 |

**Launch graph** (drawn over the Interfaces blocks): A → C (Task 5's warning channel) and A → E
(Task 10's measured settings); Task 2 → Tasks 3, 4, 7, 10 (`classes`); Tasks 3, 4 → Task 5
(`resolve_owner`, `loads_noting`); Task 5 → Task 6 (`session_config`); Task 8 → Task 9 → Task 10
(the record, the kinds, the command names the `ask` rules match). B, C, D and E each write under
`src/stayfixed/config/` or `src/stayfixed/doctor/`, so they run in order.

---

### Wave A — Task 1 (controller and owner, not dispatched)

#### Task 1: Measure the boundary's settings on Claude Code

Record each answer, with the command and what it printed, in Findings under "Task 1". Nothing in
this task writes under the owner's real home: every probe path is under `<scratchpad>/a1/`, and the
scratch configuration is removed at Step 6.

**Files:** none in the tree.

- [ ] **Step 1: The sandbox and its overrides.** In `CLAUDE_CONFIG_DIR=<scratchpad>/a1/cfg`, with
  `claude --version` recorded, ask a `-p` turn to run `printf x >> <scratchpad>/a1/canary/rec`
  through its shell tool under each of: no sandbox; user `sandbox.enabled = true`; that plus a
  project settings file setting `sandbox.enabled = false`; that plus a local file doing
  the same; that plus user `allowUnsandboxedCommands = false`. Record which combination stops the
  write, the exact keys and their precedence, whether `dangerouslyDisableSandbox` is reachable from
  the agent, and the managed-settings path on macOS and Linux.
- [ ] **Step 2: Deny rules.** With the sandbox on, record whether a `permissions.deny` rule
  `Edit(<scratchpad>/a1/canary/**)` or `Write(…)` stops a shell write or only the file tools, and
  the exact path spelling that matched.
- [ ] **Step 3: The `ask` rule.** With user `permissions.ask` holding
  `Bash(stayfixed trust approve:*)`, record what an interactive turn and a `-p` turn do (prompt,
  deny, run) for each spelling: `stayfixed trust approve memory`,
  `script -q /dev/null stayfixed trust approve memory`, `python -m stayfixed trust approve memory`,
  `uvx stayfixed …`, an absolute path to `stayfixed`; and the same with a project
  `permissions.allow` or `defaultMode` set against the user's `ask`.
- [ ] **Step 4: A terminal in the shell tool.** Record whether `[ -t 0 ]` holds in the agent's shell
  tool on the terminal surface and on the desktop Code tab.
- [ ] **Step 5: The warning's channel.** With a `SessionStart` hook printing
  `{"systemMessage": "x"}` and exit 0, record whether the terminal and the desktop Code tab show `x`
  to the person and whether it reaches the model's context. **Fallbacks, chosen now:** if
  `systemMessage` is not shown on a surface, Task 5 emits the warning as `additionalContext` there;
  if `-p` treats `ask` as deny, Task 10's reference says so and the rule stays; if a deny rule stops
  only the file tools, Task 10's row requires the sandbox and treats the deny rule as covering the
  file tools only.
- [ ] **Step 6:** remove `<scratchpad>/a1/` with the owner's yes.

---

### Wave B — Tasks 2–4 (dispatched)

#### Task 2: One class per key, the layers that may set it, and `resolve`

**Files:**
- Create: `src/stayfixed/config/classes.py` (create)
- Test: `tests/config/test_classes.py` (create)
- Modify: `CONTRIBUTING.md` ("Configuration": a new field needs its class), `mutations/core.toml`

**Interfaces:**
- Consumes: the dataclasses of `src/stayfixed/config/schema.py`.
- Produces:
  - `classes.KeyClass(StrEnum)`: `MACHINE_ONLY`, `PREFERENCE`, `SESSION_PARAMETER`,
    `GATE_PARAMETER`, `REPOSITORY_ONLY`, `PLUGIN_OWNED`.
  - `classes.LayerName(StrEnum)`: `PRESET`, `REPOSITORY`, `OVERLAY_COMMON`, `OVERLAY_PROJECT`,
    `OVERLAY_MACHINE`, `MACHINE_FILE`; `classes.ORDER: tuple[LayerName, ...]`, lowest first, in
    that order (amended 2026-10-17: shipped under the `OVERLAY_*` names, since "project" means
    the repository everywhere else a person reads it).
  - `classes.ALLOWED: Mapping[KeyClass, frozenset[LayerName]]`: `MACHINE_ONLY` — every layer but
    `REPOSITORY`; `PREFERENCE` and `SESSION_PARAMETER` — every layer; `GATE_PARAMETER` and
    `REPOSITORY_ONLY` — `PRESET`, `REPOSITORY` (HS2 adds `PROJECT` for a repository with no file,
    and applies an overlay's tightening through the gate rows, not here); `PLUGIN_OWNED` — `PRESET`.
  - `classes.CLASSES: Mapping[str, KeyClass]` — the table below, keyed by dotted key or a section
    wildcard `section.*`.
  - `classes.class_of(key: str) -> KeyClass` — exact key first, then the wildcard; `KeyError` for
    neither.
  - `classes.GATE_BUDGETS`, `classes.SESSION_BUDGETS: frozenset[str]`.
  - `classes.Layer(name: LayerName, values: Mapping[str, object])` (frozen, dotted keys).
  - `classes.Resolution(values: Mapping[str, object], provenance: Mapping[str, LayerName],
    notes: tuple[str, ...])` (frozen).
  - `classes.resolve(stack: Sequence[Layer], *, merge: Mapping[str, Callable[[object, object],
    object]] | None = None) -> Resolution` — for every key in any layer: a layer `ALLOWED` does not
    admit for the key's class contributes nothing and adds `REFUSED_LAYER_NOTE` (naming the key and
    the layer, never the value); otherwise the highest layer in `ORDER` wins, or `merge[key]` folds
    the values lowest first. An unknown key raises `KeyError` (the loader removes unknown keys
    before calling it).

  The table, from the spec's decision 12 (a wildcard covers every field of its section). Amended
  2026-10-17: `setup.*` left the table with Task 10's `[setup]` record.

  | Key | Class |
  |---|---|
  | `personal.*`, `guards.*` | `MACHINE_ONLY` |
  | `memory.mode`, `memory.groups`, `memory.index_extra`, `stayfixed.profile` | `PREFERENCE` |
  | `budgets.memory_index_words`, `budgets.startup_rules_words`, `budgets.volatile_notes_words`, `budgets.volatile_ttl_days` | `SESSION_PARAMETER` |
  | `budgets.agents_md_lines`, `budgets.agents_md_words`, `budgets.status_lines`, `budgets.roadmap_prose_lines`, `budgets.roadmap_prose_words`, `stayfixed.state`, `stayfixed.enforced`, `gates.builtin`, `gates.custom`, `ledger.code_roots`, `ledger.evidence_boundary_required_for` | `GATE_PARAMETER` |
  | `stayfixed.version`, `stayfixed.preset`, `stayfixed.agents`, `project.*`, `paths.*`, `ledger.id_prefix`, `artifacts.local`, `ci.*`, `gates.custom_timeout_seconds`, `commit_messages.*` | `REPOSITORY_ONLY` |
  | `native_caps.*` | `PLUGIN_OWNED` |

- [ ] **Step 1: Write the failing tests:**

```python
NOT_KEYS = ("NAMES",)          # pinned: the ClassVar tuples of Budgets and NativeCaps, not fields

def test_every_schema_key_has_one_class():
    for key in schema_keys():          # every dataclass field of Config's sections, dotted, with
        class_of(key)                  # Budgets.NAMES and NativeCaps.NAMES expanded, gates.custom
    assert exact_keys(CLASSES) <= set(schema_keys()) | MACHINE_FILE_KEYS

def test_no_exact_key_contradicts_its_wildcard():
    for key in exact_keys(CLASSES):
        wildcard = key.split(".")[0] + ".*"
        assert wildcard not in CLASSES or CLASSES[wildcard] is CLASSES[key]

def test_the_budget_split_is_total_and_disjoint(): ...      # GATE ∪ SESSION == Budgets.NAMES

@pytest.mark.parametrize("key, expected", TABLE_ROWS)       # one row per key the table names
def test_the_table(key, expected): assert class_of(key) is expected

def test_a_higher_layer_wins_and_says_which():
    got = resolve([Layer(PRESET, {"memory.mode": "local-only"}),
                   Layer(MACHINE_FILE, {"memory.mode": "overlay"}),
                   Layer(REPOSITORY, {"memory.mode": "in-repo"})])   # given out of order
    assert got.values["memory.mode"] == "overlay"
    assert got.provenance["memory.mode"] is MACHINE_FILE

def test_the_repository_cannot_set_a_machine_only_key():
    got = resolve([Layer(PRESET, {"guards.bg_cleanup": True}), Layer(REPOSITORY, {"guards.bg_cleanup": False})])
    assert got.values["guards.bg_cleanup"] is True and got.provenance["guards.bg_cleanup"] is PRESET
    assert got.notes == (REFUSED_LAYER_NOTE.format(key="guards.bg_cleanup", layer="repository"),)

def test_merge_folds_lowest_first(): ...   # merge={"k": lambda a, b: a + b} over three layers
```

  `schema_keys()` derives keys from `dataclasses.fields`, skipping only the names in `NOT_KEYS`, so a
  scalar field added to a section is a key and fails the first test until it has a class.
  `MACHINE_FILE_KEYS` is `{"guards.bg_cleanup"}` (amended 2026-10-17: the `setup.*` keys left
  with Task 10's ask rules); the `personal.*` fields are schema keys already.

- [ ] **Step 2: Run** `uv run pytest tests/config/test_classes.py -q`. Expected: import error.
- [ ] **Step 3: Implement** the module: the table, the two lookups, `resolve`.
- [ ] **Step 4: Mutations** in `mutations/core.toml`: `ledger.code_roots` moved to `REPOSITORY_ONLY`;
  `ALLOWED[MACHINE_ONLY]` admitting `REPOSITORY`; `resolve` keeping the lowest layer. Expected: each
  reddens its named test. Add a field to `Memory` in a scratch patch and paste the first test's red.
- [ ] **Step 5: Commit** — `feat(config): class every key, and the layers that may set each class`.

#### Task 3: The owner's layer — personal values, the guards' switches, the session budgets

**Files:**
- Create: `src/stayfixed/config/owner.py` (create)
- Modify: `src/stayfixed/setup/machine.py` (`write_machine` carries `[guards]`, `[budgets]` and
  `[setup]`)
- Test: `tests/config/test_owner.py` (create)
- Modify: `README.md` ("What each agent enforces", per Shipped sentences), `docs/cli.md`
  (Configuration: the machine file's tables), `mutations/core.toml`

**Interfaces:**
- Consumes: Task 2's `resolve`, `Layer`, `SESSION_BUDGETS`; `loader.read_machine_toml`,
  `presets.load_preset`.
- Produces:
  - `owner.Guards(bg_cleanup: bool = True)` (frozen).
  - `owner.Owner(personal: Personal, guards: Guards, session_budgets: Mapping[str, int],
    provenance: Mapping[str, LayerName], notes: tuple[str, ...])` (frozen).
  - `owner.resolve_owner(machine: Path | None, *, preset: str = "recommended",
    unknown: Unknown = Unknown.NOTE) -> Owner` — the preset's `[defaults.personal]`, `Guards()` and
    no session budget, overridden by the machine file's `[personal]`, `[guards]` and `[budgets]`
    (session budgets only). Under `NOTE`: an unreadable or non-TOML machine file gives the preset's
    values and `MACHINE_FILE_NOTE`; an unknown key, or a `[budgets]` key outside `SESSION_BUDGETS`,
    is a note; an invalid value resets that key. Under `REFUSE`, an unreadable or non-TOML machine
    file raises `MachineConfigError`, and the rest are notes as under `NOTE`, which a command prints
    on stderr (`owner.said_on_stderr`); amended 2026-10-17 by the owner, after the final review,
    from "each of those raises". `preset` is a name this build ships (amended 2026-10-17: the
    loader and the session hold it to that before they ask). Task 3 defines `loader.Unknown` (`REFUSE`, `NOTE`); Task 4
    gives the project loader its NOTE mode.

- [ ] **Step 1: Write the failing tests:**

```python
def test_no_machine_file_is_the_preset(tmp_path):
    got = resolve_owner(tmp_path / "none.toml")
    assert got.guards == Guards() and got.session_budgets == {} and got.notes == ()

def test_the_machine_file_switches_the_background_guard_off(tmp_path):
    m = tmp_path / "m.toml"; m.write_text("[guards]\nbg_cleanup = false\n")
    assert resolve_owner(m).guards.bg_cleanup is False

def test_a_session_budget_is_the_owners(tmp_path): ...       # [budgets] startup_rules_words = 9000
def test_a_gate_budget_in_the_machine_file_is_a_note(tmp_path): ...   # agents_md_lines: ignored, noted
def test_a_broken_machine_file_is_the_preset_and_names_the_file(tmp_path):
    m = tmp_path / "m.toml"; m.write_text("[[[")
    got = resolve_owner(m)
    assert got.personal == preset_personal() and got.notes == (MACHINE_FILE_NOTE,)
def test_refuse_raises_for_a_broken_machine_file(tmp_path): ...
def test_write_machine_keeps_guards_budgets_and_setup(tmp_path): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/config/test_owner.py -q`. Expected: import error.
- [ ] **Step 3: Implement.** Layers `PRESET` and `MACHINE_FILE` through `resolve`, then build
  `Personal` and `Guards`; the session budgets are the resolved `budgets.*` keys whose layer is
  `MACHINE_FILE`.
- [ ] **Step 4: Mutations:** a broken file raising under `NOTE`; a gate budget admitted. Expected:
  each reddens its test.
- [ ] **Step 5: Documents** per Shipped sentences ("The guards have no switch"). Fragment
  `changelog.d/+owner-layer.feature.md`.
- [ ] **Step 6: Run** `tests/config tests/setup`, then the full suite once.
- [ ] **Step 7: Commit** — `feat(config): one owner's layer from the preset and the machine file`.

#### Task 4: The NOTE loader — an unknown key is ignored, an invalid value resets only its key

**Files:**
- Modify: `src/stayfixed/config/loader.py`
- Test: `tests/config/test_loader_note.py` (create)
- Modify: `docs/cli.md` (Configuration: which commands refuse and which note), `mutations/core.toml`

**Interfaces:**
- Consumes: Task 2's `resolve` (for the repository's machine-only sections), Task 3's `Owner`.
- Produces:
  - `loader.Unknown(StrEnum)` (defined by Task 3, used here): `REFUSE` (the default; every CLI
    command but `doctor` and `memory session-context`), `NOTE`.
  - `ConfigError.key: str | None` — the dotted key a per-key refusal is about; `None` for a refusal
    of the whole document. Every validator that refuses one key sets it: `_build`, `_enum`,
    `_positive`, the `[budgets]` and `[gates.custom.*]` readers, the `project.*` grammars,
    `validate_paths` (whose `PathEscape` and `PathUnasked` the NOTE path catches by key), and the
    preset name (checked against `shipped_presets()` before `load_preset` runs).
  - `loader.Noted(config: Config, notes: tuple[str, ...])` (frozen).
  - `loader.loads_noting(text: str, root: Path, *, owner: Owner, label: str | None = None) -> Noted`
    — `loads` under `NOTE`: an unknown section or key is removed with `UNKNOWN_NOTE`; a repository's
    `[personal]`, `[guards]` or `[setup]` goes through `resolve` and is removed with its note; a
    `ConfigError` or path refusal carrying a `key` removes that key from the document (the preset's
    value applies) with `RESET_NOTE`, and the load is retried, at most once per key the document
    holds; a refusal with no `key` propagates. `owner.personal` and `owner.session_budgets` are
    folded into the `Config` (the session budgets as configured values that win over the
    repository's).
  - `loads(...)` and `load(...)` keep their signatures and behaviour (REFUSE); `loads` also takes
    `owner: Owner | None = None`, folded the same way.

- [ ] **Step 1: Write the failing tests** (every text starts from `HEAD`, as `test_loader.py` does):

```python
HEAD = '[stayfixed]\nversion = "0.1.0"\npreset = "recommended"\n'
MINIMAL = HEAD + '\n[project]\nname = "sample"\n'

@pytest.mark.parametrize("extra, named", [
    ("[newer]\nx = 1\n", "newer"),                                     # a section, in loads
    ("[memory]\nfuture = 1\n", "memory.future"),                       # a key, in _build
    ("[budgets]\nfuture = 1\n", "budgets.future"),                     # a key, in _budgets
    ('[gates.custom.g]\nrun = ["x"]\nfuture = 1\n', "gates.custom.g.future"),   # a key, in _gates
])
def test_an_unknown_name_is_ignored_with_a_note(tmp_path, extra, named):
    got = loads_noting(MINIMAL + extra, tmp_path, owner=OWNER)
    assert any(named in note for note in got.notes)
    assert_never_raw(*got.notes)                    # tests/crafted.py: no value reaches a note

def test_an_invalid_value_resets_only_its_key(tmp_path):
    got = loads_noting(MINIMAL + '[memory]\nmode = "harness"\n[budgets]\nagents_md_lines = 900\n',
                       tmp_path, owner=OWNER)
    assert got.config.memory.mode == preset_mode()
    assert got.config.budgets.configured["agents_md_lines"] == 900

def test_an_escaping_path_resets_only_that_path(tmp_path): ...       # [paths] bugs = "../x"
def test_an_unknown_preset_resets_to_recommended(tmp_path): ...      # preset = "future"
def test_a_repository_guards_section_is_refused_by_resolve(tmp_path): ...   # note; the owner's value kept
@pytest.mark.parametrize("extra", [...every case above...])
def test_refuse_still_refuses_each_of_them(tmp_path, extra): ...    # pytest.raises(..., match=<its message>)
def test_a_document_level_refusal_propagates(tmp_path): ...          # "[[[" raises under NOTE
```

- [ ] **Step 2: Run** `uv run pytest tests/config/test_loader_note.py tests/config/test_loader.py -q`.
  Expected: the new tests fail; `test_loader.py` stays green.
- [ ] **Step 3: Implement.** The retry is bounded by the number of dotted keys the document holds,
  so a validator that sets a `key` the document does not hold cannot loop.
- [ ] **Step 4: Mutations:** the NOTE path dropping the whole document on a keyed refusal; `_build`
  dropping an unknown key under `REFUSE`; the preset name read before its membership check; the
  NOTE path catching `ConfigError` but not `PathEscape`. Expected: each reddens its test.
- [ ] **Step 5: Documents** — Configuration. Fragment `changelog.d/+note-mode.change.md`.
- [ ] **Step 6: Run** `tests/config tests/assess`, then the full suite once.
- [ ] **Step 7: Commit** — `feat(config): a NOTE mode that ignores what it does not know and resets only what is invalid`.

---

### Wave C — Tasks 5–6 (dispatched)

#### Task 5: The session — `SessionConfig`, the guards with any configuration, one warning

**Files:**
- Create: `src/stayfixed/config/session.py` (create)
- Modify: `src/stayfixed/hooks/commands.py`, `src/stayfixed/hooks/dispatch.py`,
  `src/stayfixed/hooks/registry.py`, `src/stayfixed/harnesses.py` (each harness's rendering of the
  notice and the cap that counts it), every `src/stayfixed/*/hooks.py` (the handler signature),
  `src/stayfixed/memory/commands.py` (`memory session-context` loads with `loads_noting`)
- Test: `tests/config/test_session.py` (create), `tests/hooks/test_floor.py` (create); retire or
  re-anchor what this task makes untrue (Step 6)
- Modify: `docs/cli.md` (the `hook <event>` and Hooks sections), `README.md`, `mutations/core.toml`,
  `mutations/guards.toml`, `mutations/records.toml`, `mutations/attach.toml`

**Interfaces:**
- Consumes: Task 3's `resolve_owner`, `Owner`; Task 4's `loads_noting`; Task 1's channel.
- Produces:
  - `session.SessionConfig(config: Config | None, owner: Owner, warnings: tuple[str, ...])` (frozen).
  - `session.session_config(root: Path | None, *, machine: Path | None = None) -> SessionConfig` —
    never raises for anything the repository or the machine file holds. No file → `config=None`, no
    warning. A symlink, a file not UTF-8 or unreadable, or not TOML → `config=None` and
    `FALLBACK_WARNING`. A file that loads with notes → the config and one warning:
    `NEWER_RELEASE_WARNING` when its `[stayfixed] version` is later than the running one (the
    remedy `stayfixed upgrade`'s `VERSION_AHEAD` names), `NOTED_WARNING` otherwise, each giving the
    number of ignored or reset keys and naming `stayfixed doctor`. The owner's notes add
    `MACHINE_FILE_WARNING`. Every warning is a constant in stayfixed's own words.
  - Handlers: `Handler.run(event: HookEvent, session: SessionConfig) -> HookResult`. A handler about
    the project returns its empty result when `session.config is None`; `_bg_cleanup` judges with
    any `session` and returns the empty result when `session.owner.guards.bg_cleanup` is false.
  - `dispatch.dispatch(..., notice: tuple[str, ...] = ())` — on `SessionStart`, the notice is
    rendered through the channel Task 1 chose, counted inside the output cap; on every other event
    it is ignored, and `run_hook` writes `config-fallback` to the diagnostics sink once per session
    (`once_key`).

- [ ] **Step 1: Write the failing session tests** in `tests/config/test_session.py`:

```python
def test_no_file_is_no_config_and_no_warning(tmp_path): ...

@pytest.mark.parametrize("make", [unparseable, not_utf8, symlink_to_loadable, symlink_to_dev_zero])
def test_a_file_that_cannot_be_read_as_toml_falls_back_whole(tmp_path, make):
    make(tmp_path)
    got = session_config(tmp_path, machine=tmp_path / "none.toml")
    assert got.config is None and got.warnings == (FALLBACK_WARNING,)

def test_a_newer_release_keeps_every_other_setting(tmp_path):
    write(tmp_path, HEAD_LATER + '[project]\nname = "p"\n[newer]\n[memory]\nmode = "harness"\n'
          '[budgets]\nagents_md_lines = 900\n')
    got = session_config(tmp_path, machine=NONE)
    assert got.config.budgets.configured["agents_md_lines"] == 900
    assert got.warnings == (NEWER_RELEASE_WARNING.format(count=2),)

def test_a_broken_machine_file_keeps_the_project(tmp_path): ...   # config loads; MACHINE_FILE_WARNING
def test_both_broken(tmp_path): ...                                # config None; both warnings
```

  `HEAD_LATER` is `HEAD` with a `version` one minor above the running one.

- [ ] **Step 2: Write the failing hook tests** in `tests/hooks/test_floor.py`, through the `hook`
  helper of `tests/hooks/test_hook_command.py` (a subprocess with `floor_env()`), each paired with a
  control:

```python
BACKGROUND_SLEEP = {"command": "sleep 9", "run_in_background": True}

@pytest.mark.parametrize("project", [no_file, unparseable, newer_release, broken_machine_file, both_broken])
def test_the_background_guard_judges_whatever_the_configuration(tmp_path, project):
    project(tmp_path)
    code, out, err = hook(tmp_path, "PreToolUse", tool_input=BACKGROUND_SLEEP)
    assert code == 2 and SLEEP_REASON in err
    code, _, _ = hook(tmp_path, "PreToolUse", tool_input={"command": "ls"})
    assert code == 0                                       # the control: never refused for its config

def test_the_owner_switches_the_guard_off_with_no_stayfixed_toml(tmp_path):
    machine_with(tmp_path, "[guards]\nbg_cleanup = false\n")
    assert hook(tmp_path, "PreToolUse", tool_input=BACKGROUND_SLEEP)[0] == 0
    machine_with(tmp_path, "")                             # the control
    assert hook(tmp_path, "PreToolUse", tool_input=BACKGROUND_SLEEP)[0] == 2

def test_session_start_carries_each_warning_once(tmp_path):
    write(tmp_path, "[[[")
    payload = json.loads(hook(tmp_path, "SessionStart")[1])
    assert notice_texts(payload).count(FALLBACK_WARNING) == 1   # parsed, never a raw-string count

def test_pre_tool_use_prints_no_warning_and_logs_it_once(tmp_path): ...   # stdout empty; one config-fallback in the sink

@pytest.mark.parametrize("handler, speaks", PROJECT_HANDLERS)   # worktree-link, overlay-status, test-hygiene
def test_project_handlers_speak_on_a_file_and_stay_silent_without_one(tmp_path, handler, speaks):
    speaks(tmp_path)                                       # a real file under which the handler speaks
    assert run_handler(handler, session_config(tmp_path, machine=NONE)).context
    assert not run_handler(handler, SessionConfig(None, OWNER, ())).context

def test_memory_session_context_reads_a_newer_key_with_a_note(tmp_path): ...   # bundles not emptied
```

  A test names a machine file through `--machine` or the owner-home seam of `tests/ownerhome.py`;
  none reads the real `~/.config/stayfixed`. `notice_texts` reads the channel Task 1 chose.

- [ ] **Step 3: Run** both files. Expected: the session tests fail on import; the guard is refused
  with "does not load" instead of judging.
- [ ] **Step 4: Implement.** `run_hook` calls `session_config` once and dispatches with it;
  `_linked`, `_unloadable`, `LINKED`, `UNLOADABLE`, `REFUSED_VALUE`, `ESCAPING_PATH`, `UNASKED_PATH`
  go. A `Failure` from `load_preset` can no longer reach the generic arm (Task 4 checks the name
  first).
- [ ] **Step 5: Mutations:** `session_config` answering `config=None` for a file that loads with
  notes; `dispatch` rendering the notice on `PreToolUse`; `_bg_cleanup` treating `config=None` as a
  project handler does (`mutations/guards.toml`); each project handler judging on `config=None`
  (one entry each, in `records`, `attach`, `guards`). Expected: each reddens a test of this task.
- [ ] **Step 6: Retire and re-anchor.** The tests that assert today's refusals —
  `test_a_broken_repository_config_on_pre_tool_use_refuses`,
  `test_a_symlinked_config_gets_one_named_verdict_whatever_it_points_at`,
  `test_an_unloadable_config_refuses_a_tool_call_in_its_own_words`,
  `test_a_path_that_cannot_be_checked_for_a_symlink_refuses_a_tool_call_in_those_words` (in
  `tests/hooks/test_hook_command.py`) and the `config is None` assertion in
  `tests/guards/test_hooks.py` — are rewritten to the new verdicts in this commit, by name; every
  `mutations/*.toml` entry whose `before` text this task deletes is re-anchored on
  `src/stayfixed/config/session.py` or removed with its reason in the commit message.
- [ ] **Step 7: Documents** per Shipped sentences ("The guards without configuration"). Fragment
  `changelog.d/+value-floor.change.md`.
- [ ] **Step 8: Run** `tests/config tests/hooks tests/guards tests/memory tests/attach`, then the
  full suite once.
- [ ] **Step 9: Commit** — `feat(hooks): a session never dies of its configuration, and the guards run with none`.

#### Task 6: `doctor` with nothing configured, and the owner's preferences

**Files:**
- Modify: `src/stayfixed/doctor/checks.py`, `src/stayfixed/doctor/model.py` (`Context.config:
  Config | None`, `Context.session: SessionConfig`), every area `doctor.py` that reads
  `context.config` (it skips when it is `None`)
- Test: `tests/doctor/test_floor_report.py` (create)
- Modify: `docs/cli.md` (`doctor`), `README.md`, `skills/doctor/SKILL.md`,
  `.github/workflows/smoke.yml`, `tests/doctor/test_command.py`, `tests/test_documents.py`,
  `mutations/doctor.toml`

**Interfaces:**
- Consumes: Task 5's `session_config`.
- Produces:
  - `doctor` loads through `session_config`; `Context` carries the session.
  - `not-initialised`: with no file, a **warning** — `NOT_INITIALISED` says the guards, `prove` and
    `doctor` work without configuration and `stayfixed init` adds the rest; with a file that loaded
    with notes, a warning listing them (key names only); green otherwise. A file that falls back
    whole is red, with the warning's words.
  - Every core check that does not read `context.config` runs with no file; a check that does skips
    with `NO_CONFIG_SKIP`.
  - A core row `preferences`, after `budgets`: each owner key and each preference as `key (layer)`,
    the value printed only when it is a boolean, a number, an enumerated value or a name the loader
    validated against its grammar.

- [ ] **Step 1: Write the failing tests:**

```python
def test_no_stayfixed_toml_is_a_warning_and_no_row_is_red(tmp_path):
    report = run_checks_for(tmp_path, machine=NONE)
    assert row(report, "not-initialised").status == WARN
    assert not [r for r in report if r.status == RED]

@pytest.mark.parametrize("name", ["versions", "files", "wrapper", "cli-path", "diagnostics", "ignored-env", "preferences"])
def test_rows_that_need_no_configuration_run_without_one(tmp_path, name): ...   # not skipped

def test_notes_are_listed_by_key(tmp_path): ...
def test_a_whole_fallback_is_red(tmp_path): ...
def test_preferences_names_the_layer_and_hides_free_text(tmp_path): ...    # index_extra's value not printed
```

  If one of the parametrised rows turns out to read the configuration, the implementer reports the
  mismatch rather than skipping it from the list.

- [ ] **Step 2: Run** them. Expected: `not-initialised` red and every other row skipped.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Mutations:** `not-initialised` red with no file; `preferences` printing a free-text
  value. Expected: each reddens its test.
- [ ] **Step 5: Counts.** The smoke workflow's row count, `tests/doctor/test_command.py`'s counts and
  the documents' "seventeen" go to eighteen, per Shipped sentences.
- [ ] **Step 6: Run** `tests/doctor tests/test_documents.py`, then the full suite once.
- [ ] **Step 7: Commit** — `feat(doctor): report a repository with no configuration without calling it broken`.

---

### Wave D — Tasks 7–9 (dispatched)

#### Task 7: Budgets the base branch and the owner raise; the ratchet's rows through the class table

**Files:**
- Modify: `src/stayfixed/config/schema.py` (`Budgets.effective`), `src/stayfixed/assess/rule.py`,
  `src/stayfixed/doctor/checks.py` (`_budgets`)
- Test: `tests/assess/test_rule_classes.py` (create), `tests/config/test_budgets_raise.py` (create)
- Modify: `docs/cli.md`, `CONTRIBUTING.md` (per Shipped sentences), `mutations/assess.toml`,
  `mutations/core.toml`

**Interfaces:**
- Consumes: Task 2's `class_of`, `GATE_BUDGETS`.
- Produces:
  - `Budgets.effective(name) -> int` — the configured value when set, else the preset's.
  - `rule._row(key)` asks `class_of` first: `PREFERENCE`, `MACHINE_ONLY` and `PLUGIN_OWNED` keys
    are `_neutral`; every budget, a gate's or a session's, is `_budget` (amended 2026-10-17 by the
    owner, after the re-review: a session budget was `_neutral`, so a pull request could raise
    `memory_index_words` and loosen a base gate running `memory index --check`); `ledger.code_roots` and
    `ledger.evidence_boundary_required_for` are `_additive` (a superset is `TIGHTENED`, equal
    `NEUTRAL`, anything else `_other`); every other key keeps today's row. A pull request may change
    `memory.mode`, a preference.

- [ ] **Step 1: Write the failing tests:**

```python
def test_the_base_branch_raises_a_gate_budget(tmp_path):
    config = loads(MINIMAL + "[budgets]\nagents_md_lines = 900\n", tmp_path, machine=NONE)
    assert config.budgets.effective("agents_md_lines") == 900          # above the preset's
def test_a_pull_request_still_only_lowers_a_gate_budget(tmp_path): ...  # REFUSED raised, TIGHTENED lowered
def test_a_pull_request_only_lowers_a_session_budget(tmp_path): ...     # REFUSED raised, TIGHTENED lowered
def test_a_pull_request_may_change_memory_mode(tmp_path): ...           # NEUTRAL
def test_adding_a_code_root_tightens_and_removing_one_is_refused_while_enforcing(tmp_path): ...
def test_removing_a_code_root_is_noted_when_nothing_enforces(tmp_path): ...
```

- [ ] **Step 2: Run** them. Expected: the raise reads the preset; the code-root rows and
  `memory.mode` read `_other`.
- [ ] **Step 3: Implement.** `doctor`'s `budgets` row says "raised" or "lowered" against the preset,
  and names a clamp only where a consumer applies a platform cap.
- [ ] **Step 4: Mutations:** `_additive` admitting a subset; `effective` keeping `min`; `_row` asking
  the old table before `class_of`. Expected: each reddens its test.
- [ ] **Step 5: Documents** per Shipped sentences ("Budgets are only lowered"). Fragment
  `changelog.d/+budgets-raise.change.md`.
- [ ] **Step 6: Run** `tests/assess tests/config tests/doctor`, then the full suite once.
- [ ] **Step 7: Commit** — `feat(assess): let the base branch raise a budget, and judge keys by their class`.

#### Task 8: One trust record, in core, versioned

**Files:**
- Create: `src/stayfixed/trust/__init__.py` (create), `src/stayfixed/trust/record.py` (create),
  `src/stayfixed/trust/api.py` (create)
- Modify: `src/stayfixed/memory/trust.py`, `src/stayfixed/memory/commands.py` (its use of
  `record_path`)
- Test: `tests/trust/__init__.py` (create), `tests/trust/test_record.py` (create)
- Modify: `README.md` (the machine-files table), `docs/cli.md`, `SECURITY.md`,
  `tests/memory/test_commands.py` (named below), `mutations/core.toml`, `mutations/records.toml`

**Interfaces:**
- Consumes: `config.machine.machine_config_path`, `fsops`, `jsonobject.json_object`.
- Produces:
  - `record.RECORD = "trust.json"`, beside the machine file; `record.VERSION = 1`.
  - `record.Approval(kind: str, subject: str, digest: str, approved_at: str)` (frozen).
  - `record.State(StrEnum)`: `APPROVED`, `LAPSED` (recorded with another digest), `MISSING`.
  - `record.UnreadableTrust(Refusal)` — the file exists and is neither a version-1 record nor
    `0.3.0`'s flat map; never overwritten. `memory.trust.UnreadableTrustRecord` is an alias of it.
  - `record.record_path(machine: Path | None) -> Path | None`.
  - `record.recorded(machine) -> dict[tuple[str, str], Approval]` — a flat map (every value a
    string) reads as kind `memory`, one approval per entry.
  - `record.state(machine, kind: str, subject: str, current: str) -> State`, and
    `record.state_in(approvals, kind, subject, current) -> State`, the same answer out of a record
    read once.
  - `record.approve_all(machine, kind, digests: Mapping[str, str], *, now: datetime) ->
    dict[str, State]` and `record.revoke_all(machine, kind, subjects: Iterable[str]) -> list[str]`
    — each writes the whole record once as version 1 through `fsops` (an atomic replace), whatever
    the number of subjects; `revoke_all` answers the subjects it withdrew and writes nothing for
    none. Two writers at once: the last write wins and neither file is torn; no lock is taken, and
    the reference says so.
  - `src/stayfixed/trust/api.py` (create) publishes what its consumers import, and no writer of the
    record: `record_path`, `recorded`, `state`, `refresh`, `State`, `Approval`, `UnreadableTrust`,
    among the rest `tests/trust/test_surface.py` lists.
  - `src/stayfixed/memory/trust.py` keeps its public functions and their behaviour, each through `trust.api` with
    kind `memory` and the store's path key.

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_0_3_0_record_keeps_every_memory_approval(tmp_path):
    (tmp_path / "trust.json").write_text(json.dumps({"/s": "d"}))
    assert state(tmp_path / "config.toml", "memory", "/s", "d") is State.APPROVED
def test_the_first_write_upgrades_the_file_in_place(tmp_path): ...   # version 1; the old entry kept
def test_0_3_0s_reader_sees_no_approval_in_a_version_1_record(tmp_path):
    approve(tmp_path / "config.toml", "memory", "/s", "d", now=T0)
    assert legacy_reader(tmp_path / "trust.json") == {}   # 0.3.0's filter, copied as a literal
def test_an_unreadable_record_refuses_and_is_never_overwritten(tmp_path): ...   # "{", and version 2
def test_lapsed_missing_and_approved_are_told_apart(tmp_path): ...
def test_two_kinds_never_share_a_subject(tmp_path): ...
def test_revoke_of_nothing_says_so(tmp_path): ...             # False; file unchanged
def test_the_record_ignores_xdg_and_home(tmp_path, monkeypatch): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/trust -q`. Expected: import error.
- [ ] **Step 3: Implement**, and route `src/stayfixed/memory/trust.py` through `trust.api`.
- [ ] **Step 4: Rewrite, by name, the tests that read the old shape** in
  `tests/memory/test_commands.py`:
  `test_trust_writes_to_the_machine_file_it_was_given_not_to_the_home_directory`,
  `test_trust_with_no_home_in_the_database_fails_and_writes_nothing`,
  `test_trust_without_the_flag_is_refused_not_silently_granted`; each asserts the version-1 record
  (or its absence) instead of the flat map. A negative test that searches for `trust.json` keeps
  searching for it — the file name did not change, so none goes vacuous. Every
  `mutations/records.toml` entry whose `before` text moves to `src/stayfixed/trust/record.py` moves
  to `mutations/core.toml`, re-anchored.
- [ ] **Step 5: Mutations:** `state` ignoring the digest; `LAPSED` read as `MISSING`; the key built
  from the subject alone; `approve` writing over an unreadable record; the flat-map reader dropped.
  Expected: each reddens its test.
- [ ] **Step 6: Documents** per Shipped sentences ("The trust record"); `SECURITY.md`: approvals hold
  against repository bytes and a `git pull`, and against an agent with an unsandboxed shell the
  harness's write restriction is the boundary. Fragment `changelog.d/+trust-record.change.md`.
- [ ] **Step 7: Run** `tests/trust tests/memory tests/attach tests/test_owner_home_seam.py`, then the
  full suite once.
- [ ] **Step 8: Commit** — `feat(trust): keep every approval on the machine in one versioned core record`.

#### Task 9: `stayfixed trust list | approve | revoke`, kinds the areas contribute

**Files:**
- Create: `src/stayfixed/trust/kinds.py` (create), `src/stayfixed/trust/commands.py` (create),
  `src/stayfixed/memory/approvals.py` (create), `scripts/ptyrun.py` (create)
- Modify: `src/stayfixed/trust/api.py` (create), extended from Task 8, `src/stayfixed/areas.py` (the docstring: four submodules),
  `src/stayfixed/memory/commands.py` (the alias), `src/stayfixed/doctor/checks.py` (`codex-trust` →
  `codex-hooks`), every refusal sentence naming `memory trust` under `src/stayfixed/`,
  `src/stayfixed/config/machine.py` (its docstring), `scripts/smoke_exfiltration.py`
- Test: `tests/trust/test_commands.py` (create); the callers named in Premise
- Modify: `docs/cli.md` (a `trust` section; the alias), `README.md`, `SECURITY.md`, `CONTRIBUTING.md`
  ("Areas": the `approvals.py` convention), `docs/methodology/principles.md`, `skills/` wording that
  names the command, `tests/test_documents.py`, the discovery pins in `tests/` that count
  submodules, `tests/boundaries/` (a discovered `approvals.py` is not a core-to-delivery import),
  `mutations/core.toml`, `mutations/records.toml`

**Interfaces:**
- Consumes: Task 8's record.
- Produces:
  - `kinds.Subject(key: str, label: str, digest: str)` (frozen) — `label` is what a person reads,
    printed through `printed.printable`.
  - `kinds.KindContext(root: Path, machine: Path | None, options: Mapping[str, str])` (frozen) —
    `options` carries a kind's own flags (`memory`'s `--store`).
  - `kinds.ApprovalKind(name: str, describe: Callable[[KindContext], tuple[Subject, ...]],
    flags: tuple[str, ...] = ())` (frozen) — one checkout may have several subjects of a kind.
  - `kinds.kinds() -> dict[str, ApprovalKind]` — every `stayfixed.<area>.approvals.KINDS`, through
    `areas.area_modules("approvals")`; two kinds of one name refuse.
  - `kinds.interactive() -> bool` — `sys.stdin is not None and sys.stdin.isatty()`, the seam tests
    replace.
  - Commands: `trust list [--all] [--json]` — one line per kind for this checkout, its state, and on
    every line not approved the exact command that approves it; `--all` lists every record on the
    machine. `trust approve KIND [kind flags]` — refuses with exit 2 and `NOT_A_TERMINAL` (naming the
    exact command for a person to run) when `interactive()` is false; otherwise prints each
    subject's label and digest, then records them. `trust revoke KIND [--subject KEY]` — needs no
    terminal; a revoke that matches nothing exits 1 and lists the kind's recorded subjects. None takes
    `--yes`.
  - `memory/approvals.py` (create): `KINDS = (ApprovalKind("memory", _describe, flags=("--store",)),)`;
    `_describe` resolves the store as `memory trust` does today; the digest is `trust.store_digest`.
  - `memory trust --in-repo-memory` runs the same approve path, terminal check included, and prints
    `ALIAS_NOTE` (the new spelling; the alias is removed in `0.5.0`).
  - `scripts/ptyrun.py` (create): `run_in_pty(argv: Sequence[str], *, env: Mapping[str, str],
    cwd: Path | None = None, deadline: float = DEADLINE_SECONDS) -> tuple[int, str]` — runs a
    command under `pty.openpty` and `subprocess.Popen` and returns its exit code and output, or
    kills its process group and raises `TimeoutError` when it has not exited within `deadline`
    seconds; the smoke scripts and the tests that approve through a subprocess use it.

- [ ] **Step 1: Write the failing tests:**

```python
SPELLINGS = [["trust", "approve", "memory"], ["memory", "trust", "--in-repo-memory"]]

@pytest.mark.parametrize("argv", SPELLINGS)
def test_no_terminal_no_approval(tmp_path, argv):
    proc = subprocess.run([*stayfixed_argv(owner), *argv, "--root", str(repo), "--machine", str(m)],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, env=floor_env())
    assert proc.returncode == 2 and NOT_A_TERMINAL in proc.stdout + proc.stderr
    assert record_path(m) is None or not record_path(m).exists()

@pytest.mark.parametrize("argv", SPELLINGS)
def test_a_terminal_approves(tmp_path, argv):
    code, _ = run_in_pty([*stayfixed_argv(owner), *argv, "--root", str(repo), "--machine", str(m)], env=floor_env())
    assert code == 0 and state(m, "memory", key, digest) is State.APPROVED

def test_revoke_needs_no_terminal(...): ...
def test_revoke_of_nothing_lists_what_is_recorded(...): ...
def test_list_names_the_command_on_every_unapproved_line(...): ...
def test_list_reads_lapsed_after_a_note_changes(...): ...
def test_an_unknown_kind_names_the_known_ones(...): ...
def test_kind_discovery_refuses_a_duplicate_name(...): ...
def test_no_shipped_document_names_memory_trust_outside_its_alias_note(): ...   # tests/test_documents.py
```

- [ ] **Step 2: Run** `uv run pytest tests/trust -q`. Expected: no `trust` command.
- [ ] **Step 3: Implement.** Every call of `memory trust` the Premise names moves to `run_in_pty` (a
  subprocess) or to the `interactive` seam (in-process `invoke`), in this commit; the emulation in
  `tests/scripts/test_smoke_scripts.py` follows the new spelling. Every refusal sentence that told a
  person to run `stayfixed memory trust --in-repo-memory` names `stayfixed trust approve memory` and
  says to run it in a terminal; the tests asserting those sentences change with them, by name.
- [ ] **Step 4: Mutations:** `approve` skipping `interactive()`; the alias skipping it; `kinds`
  accepting a duplicate; `revoke` of nothing exiting 0. Expected: each reddens its test.
- [ ] **Step 5: Documents** per Shipped sentences (`memory trust`, `codex-trust`). Fragments
  `changelog.d/+trust.feature.md` and `changelog.d/+memory-trust-alias.upgrading.md` (the alias now
  needs a terminal too).
- [ ] **Step 6: Run** `tests/trust tests/memory tests/attach tests/hooks tests/scripts tests/skills
  tests/boundaries tests/test_documents.py tests/test_install_path.py`, then the full suite once.
- [ ] **Step 7: Commit** — `feat(trust): one command family for every approval, asked of a person at a terminal`.

---

### Wave E — Task 10 (dispatched)

#### Task 10: The `ask` rules, and `doctor`'s approval-boundary row

**Files:**
- Modify: `src/stayfixed/setup/run.py`, `src/stayfixed/setup/machine.py`,
  `src/stayfixed/doctor/checks.py`
- Test: `tests/setup/test_ask_rules.py` (create), `tests/doctor/test_approval_boundary.py` (create)
- Modify: `docs/cli.md` (`setup`, `doctor`), `skills/setup/SKILL.md`, `README.md`,
  `.github/workflows/smoke.yml`, `tests/doctor/test_command.py`, `mutations/install.toml`,
  `mutations/doctor.toml`

**Interfaces:** amended 2026-10-17, after the final review found the `approval-boundary` row
unsound after a dozen fix rounds at one seam: the owner narrowed the record to what it defends,
repository bytes, and left the session's own agent to the harness's sandbox. What shipped:
- Consumes: Task 1's measured deny-rule spelling and managed-settings paths.
- Produces: `setup --approval-boundary`, which writes nothing and prints the deny rule over the
  trust record's directory (`trust.boundary.record_deny_rules`), `trust.boundary.SANDBOX_ON` for
  the user settings and `trust.boundary.ENFORCING_SETTINGS` for the managed settings file
  (`trust.boundary.managed_named`); it refuses beside `--preset`, `--overlay`, `--settings`,
  `--yes` or `--git-hooks`. No `ask` rules, no `[setup]` table and no `doctor` row.

As planned, and cut:
- Consumes: Task 1's measured spellings, keys, precedence and managed-settings paths; Task 9's
  command names; Task 2's `setup.*` class.
- Produces:
  - `src/stayfixed/setup/run.py` `ASK_RULES: tuple[str, ...]` — Task 1's spellings for `trust approve` and the
    alias (HS3 adds `memory promote`); never `revoke`. `setup` adds the missing ones to the user's
    `permissions.ask` and records each it added in the machine file's `[setup] added_rules`; with
    `[setup] ask_rules = false` it removes exactly the recorded ones, never a rule it did not add.
  - `setup --approval-boundary` adds a deny rule covering the trust record's directory, in Task 1's
    spelling, recorded the same way, and prints the sandbox settings for the person to set
    (`sandbox.enabled`, `allowUnsandboxedCommands = false`); it never writes a `sandbox` key.
  - A core `doctor` check `approval-boundary`: **skipped** when this machine has no Claude Code user
    settings directory; **red** when the trust record holds at least one approval and the effective
    settings — managed, user (`CLAUDE_CONFIG_DIR`-aware), the project's and the local file, in Task
    1's precedence — lack the sandbox, or let a repository file turn it off, or lack the deny rule
    for the record's directory; a **warning** for the same gaps with no approval yet; green
    otherwise. The detail names the missing setting and what it stops.

- [ ] **Step 1: Write the failing tests** (settings files built from Task 1's literals, written as
  constants in the test with the Claude Code version they were measured on):

```python
def test_setup_adds_the_ask_rules_once_and_records_them(tmp_path): ...
def test_switching_off_removes_only_recorded_rules(tmp_path): ...   # an identical rule the owner typed first stays
def test_setup_never_writes_a_sandbox_key(tmp_path): ...

@pytest.mark.parametrize("settings, approvals, expected", [
    (NOTHING, 0, WARN), (NOTHING, 1, RED),
    (SANDBOX_ONLY, 1, RED), (SANDBOX_AND_DENY_ELSEWHERE, 1, RED),
    (SANDBOX_AND_DENY, 1, GREEN), (SANDBOX_AND_DENY_BUT_PROJECT_DISABLES, 1, RED),
])
def test_the_boundary_row(tmp_path, settings, approvals, expected): ...

def test_the_row_skips_without_claude_code(tmp_path): ...
```

- [ ] **Step 2: Run** them. Expected: no rules, no row.
- [ ] **Step 3: Implement**; each Task 1 literal is a module constant with a comment naming Task 1's
  Findings and the version measured.
- [ ] **Step 4: Mutations:** removal taking every `ask` rule; the row passing without the deny rule;
  the row ignoring a project file that disables the sandbox. Expected: each reddens its test.
- [ ] **Step 5: Documents and counts** per Shipped sentences (eighteen → nineteen); the setup skill
  asks before `--approval-boundary`. Fragment `changelog.d/+approval-boundary.feature.md`.
- [ ] **Step 6: Run** `tests/setup tests/doctor tests/test_documents.py`, then the full suite once.
- [ ] **Step 7: Commit** — `feat(setup): ask rules on approvals, and doctor's approval-boundary row`.

---

### Wave F — Task 11 (controller, not dispatched)

#### Task 11: Final review and the pull request

- [ ] **Step 1:** run, once, on the branch's head: `uv run pytest -n auto --cov --cov-fail-under=92`,
  the same suite on `--python 3.13` and `--python 3.11.4`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy`, `uv run python scripts/mutation_oracle.py`,
  `uv run python scripts/release.py check`, `uv run stayfixed plan check`. Paste each result into
  Findings.
- [ ] **Step 2:** the four seats of the execution contract, in parallel, on Opus. The lifecycle seat
  walks every command this pull request changed (`hook <event>`, `memory session-context`,
  `trust list | approve | revoke`, `memory trust`, `setup`, `setup --approval-boundary`, `doctor`) ×
  set, change, unset, a broken file, a newer release's file, a broken machine file, `uninstall` × the
  preset, repository and machine-file layers. Fix rounds follow the contract.
- [ ] **Step 3:** open the pull request into `dev` with a body derived from the diff: what a session
  no longer refuses, what the owner may now switch or raise, the record and the command, what
  `doctor` says on a default install, and what HS2, HS3, CP2 and PF1 take from it (the Interfaces
  blocks above). Wait for its checks as the contract's item 8 says.

---

## Findings

Written by Tasks 1 and 11, and by the controller when a wave's implementer reports (its token total,
its fix rounds).

### Task 1 — measured 2026-10-16 on Claude Code 2.1.296 (macOS)

Probes ran in an isolated `CLAUDE_CONFIG_DIR=<scratchpad>/a1/cfg`, in a scratch git repository
`<scratchpad>/a1/proj`, with `claude -p --model haiku --output-format stream-json --verbose`; a probe
counts as "wrote" when its canary file grew. The canary for Step 1 sits at
`/Users/Shared/stayfixed-a1/canary/rec`, outside the per-user temp directory, which the sandbox
leaves writable (a first canary under the scratchpad was written with the sandbox on, so it proved
nothing and was moved). The interactive steps were run by the owner in a terminal.

**Step 1 — the sandbox and its overrides** (a `printf x >> <canary>` asked of the shell tool, with
the instruction to retry once with `dangerouslyDisableSandbox` if the sandbox blocks it;
`--allowedTools Bash`):

| Settings | Wrote | What happened |
|---|---|---|
| none | yes | ran unsandboxed |
| user `sandbox.enabled = true` | yes | blocked, then the agent's retry with `dangerouslyDisableSandbox: true` ran unsandboxed |
| + the project settings file setting `sandbox.enabled = false` | yes | ran unsandboxed: the project file turns the user's sandbox off |
| + the local settings file doing the same | yes | ran unsandboxed |
| + user `sandbox.allowUnsandboxedCommands = false` | yes | the project file still turns the sandbox off |
| user `enabled` + `allowUnsandboxedCommands = false`, project `enabled = false`, no local file | yes | the same |
| user `enabled`, project `enabled = false`, `--settings '{"sandbox":{"allowUnsandboxedCommands":false}}'` | no | the project's `false` is ignored; the retry is ignored |
| user `enabled` + `allowUnsandboxedCommands = false`, no project file | no | blocked; the retry with `dangerouslyDisableSandbox` was ignored |

So `dangerouslyDisableSandbox` is reachable from the agent unless `allowUnsandboxedCommands` is
false; a repository's project or local file turns a user's `sandbox.enabled = true` off, and a
user's `allowUnsandboxedCommands = false` does not stop it. Only managed settings or `--settings`
make the sandbox admin-required, which is when a repository's `false` is ignored — as the
sandboxing documentation states for 2.1.285 and later. Managed settings live in
`/Library/Application Support/ClaudeCode/managed-settings.json` (macOS) and
`/etc/claude-code/managed-settings.json` (Linux and WSL), each with an optional
`managed-settings.d/` beside it.

**Step 2 — deny rules** (user `sandbox.enabled = true` and one `permissions.deny` rule over
`<scratchpad>/a1/proj/inner/**`; a shell write and a `Write`-tool write into that directory):

| Rule | Shell write | `Write` tool |
|---|---|---|
| `Edit(//<absolute path>/**)` | stopped (the unsandboxed retry was denied) | stopped |
| `Edit(./inner/**)` | stopped | stopped |
| `Edit(<absolute path>/**)` (one leading slash) | wrote | wrote |
| `Write(...)`, any of the three spellings | wrote | wrote |

An `Edit` deny rule covers both the sandboxed shell and the file tools; a `Write` deny rule covers
neither; a single leading slash anchors at the working directory, so an absolute path needs `//`.

**Step 3 — the `ask` rule** (user `permissions.ask = ["Bash(stayfixed trust approve:*)"]`, fake
`stayfixed`, `uvx` and `python` first on `PATH`, `--allowedTools Bash`):

| Spelling | `-p` |
|---|---|
| `stayfixed trust approve memory` | denied |
| `script -q /dev/null stayfixed trust approve memory` | denied |
| `python -m stayfixed trust approve memory` | ran |
| `uvx stayfixed trust approve memory` | ran |
| `<absolute path>/stayfixed trust approve memory` | ran |
| bare, with a project `permissions.allow = ["Bash(stayfixed:*)"]` | denied |
| bare, with a project `permissions.defaultMode = "bypassPermissions"` | denied |
| bare, with no `ask` rule (the control) | ran |

Interactively, in a terminal in auto mode, the bare spelling showed the prompt "Ask rule
Bash(stayfixed trust approve:*) overrides auto mode for this command". So `-p` treats `ask` as
deny; a project `allow` or `defaultMode` does not lift a user's `ask`; the rule matches its own
prefix and the `script` wrapper, and every other spelling needs a rule of its own.

**Step 4 — a terminal in the shell tool:** `[ -t 0 ]` is false in the agent's shell tool, both in
a terminal session ("notty") and on the desktop Code tab.

**Step 5 — the warning's channel** (a `SessionStart` hook printing `{"systemMessage": "x"}`):
the terminal shows the person `SessionStart:startup says: x` (on 2.1.296 and 2.1.301); in `-p` the
model, asked to quote its context, did not see a `systemMessage`, and did see a
`hookSpecificOutput.additionalContext` printed beside it. The desktop Code tab's display of
`systemMessage` was not observed.

**What Tasks 5 and 10 take from this:**

- Task 5 renders the notice through both channels: `systemMessage` for the person and
  `additionalContext` for the model, which also covers a surface that does not show a
  `systemMessage`; both count inside the output cap.
- Task 10's deny rule is `Edit(//<the trust record's directory>/**)`; its `ask` rules cover each
  spelling that bypasses the bare one (`python -m stayfixed`, `uvx stayfixed`, the absolute path of
  the `stayfixed` that `setup` runs as) for `trust approve` and the alias; its reference says `-p`
  treats `ask` as deny. The `approval-boundary` row reads a repository's project and local files as
  able to turn the sandbox off unless managed settings make it admin-required.

### Wave B — Tasks 2–4

- Implementer: 359,623 tokens, three commits; one fix round, by a fresh implementer (263,771 tokens)
  since the first was past 300k, on the review's two Important findings (a committed comment citing
  a report; 24 tests with no declared mutation) and seven Minor ones; the scoped re-review found all
  addressed. Reviewer 212,967 tokens, re-reviewer 156,676.
- Two Minor findings pointed at the same seam — the NOTE retry when a removed key has no usable
  fallback (`[project] name = "has space"` surfaced as "missing required key(s): name"; a committed
  `docs` symlink failed the preset's `paths.architecture`). Put to the owner, who chose a typed
  refusal and a whole fallback at the session (Global Constraints, amended); Task 5 builds it.

### Wave C — Tasks 5–6

- Implementer 709,103 tokens (ended without a hand-back; its report file was complete); one fix
  round by a fresh implementer (375,367 tokens). The review found the NOTE retry's third failure at
  one seam (a section that is not a table surfaced as a missing key), so the retry was redesigned
  rather than patched: a refused key is removed only when a fallback exists, decided before the
  removal. Also: an oracle survivor wave B's `_preset` change had left, and unbounded key names in
  a doctor detail the doctor skill relays to the model (now at most three, each clipped). Codex's
  hooks reference lists `systemMessage` as a common output field, so one render serves both.

### Wave D — Tasks 7–9

- Implementer 483,530 tokens; one fix round (343,092 tokens): the terminal check's refusal now
  addresses the person and tells an agent to stop instead of naming the bypass; four refusal arms of
  the version-1 reader gained tests; the alias keeps its old `--json` keys for its one release; the
  refresh became a compare-and-set that keeps `approved_at`; subjects print as `~/…`.

### Wave E — Task 10

- Implementer 696,924 tokens, then three fix rounds (640,475; 425,517; 278,214). Six automated
  security passes and three reviews went over the `approval-boundary` row's reading of settings
  entries. Emulating Claude Code's glob matcher kept failing (a regex built from a settings string,
  unnormalised paths, live-filesystem calls on settings paths), so the owner ruled the final shape:
  a widening entry is safe only as a literal absolute or `~/` path outside the project that, as
  text, neither is, contains nor lies inside the record's directory; everything else is a gap;
  deny coverage counts setup's spellings byte for byte; no filesystem call and no regex on a
  settings string. Later rounds added: green only from managed or user settings, with managed
  `failIfUnavailable`; `filesystem.disabled` and every `excludedCommands` judged; `CLAUDE_CONFIG_DIR`
  may only worsen the row; stayfixed's own writes from a sandboxed shell fail with a sentence.

### Wave F — Task 11

- Four parallel seats (correctness 372,090 tokens; architecture 300,695; security 280,062;
  lifecycle 305,808) found no Critical and seven Important issues: commands never read the owner's
  layer (three seats); a ~200 KB `stayfixed.toml` of bad custom gates pushed the NOTE retry past
  the hook's 10 s timeout, which Claude Code lets through (now `NOTE_REMOVAL_LIMIT`, one parse);
  widening keys of the wrong type read as empty; a byte-order mark hid a project settings file;
  `trust revoke` blocked by a file `trust list` could not load; `CLAUDE_CONFIG_DIR` printed whole;
  `resolve`'s documented role. One fix wave (716,774 tokens) and one scoped re-review.
- After a six-seat final review on 2026-10-17 found seven more classes at the `approval-boundary`
  row's seam and a defective `[setup]` record, the owner narrowed Task 10 (its Interfaces block
  says what shipped): the row, the `ask` rules, their record and `setup`'s writes into the
  `CLAUDE_CONFIG_DIR` directory were removed, and `setup --approval-boundary` became advice that
  writes nothing. The owner also ruled that a command warns, never refuses, on a key of the
  machine file it cannot use (Task 3's Interfaces block), and that the closed `PreToolUse` entry
  takes `onFailure: "block"` in this pull request, after the NOTE retry's cost was bounded by the
  document's length and a session's read capped at 1 MiB.
- A five-seat re-review the same day found two Important issues, both fixed before merge: a
  `[paths]` value of tens of thousands of components made the containment walk quadratic, so a
  72 KB committed file kept the hook past its timeout, which `onFailure: "block"` turned into a
  blocked `Bash` call (now a 1024-character cap, a walk down from the root, a session read of
  256 KiB and at most 1 MiB rebuilt; the densest file measured 0.25 s, 1.5 s on efficiency cores);
  and `doctor` exited 0 over a machine file every command refuses (now the `preferences` row is
  red, and the overlay rows say the file could not be read). The machine file's notes are said
  once a command (`command.command_owner`), and `Unknown` became `resolve_owner(strict=)`. The
  owner ruled that a pull request may only lower a session's budget, as a gate's (Task 7's
  Interfaces block).
- Follow-ups for the owner: doctor relaying at most three clipped key names; a pull request
  narrowing `memory.groups`.
