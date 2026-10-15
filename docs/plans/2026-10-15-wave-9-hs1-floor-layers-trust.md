# Wave 9, HS1 — the value floor, layered preferences, one approval primitive: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **The wave is the dispatch unit, not the task.** Waves are lettered (`A`, `B`, …) and own a
> run of the continuously numbered tasks. One implementer, one review round and one reviewer per
> **dispatched** wave; inside a wave every task keeps its own failing test, verification and
> commit. Do not dispatch one subagent per task.
>
> **Waves A and E are not dispatched.** A measures Claude Code with the owner at the keyboard;
> E runs the final review seats and opens the pull request. The controller runs both.
>
> **One pull request**, `wp/hs1-floor-layers-trust` into `dev`, in release window R1 of the
> umbrella plan (`docs/plans/2026-10-15-wave-9-umbrella.md`), merged before RC1 and CP1 so that
> the value floor reaches `0.4.0`.

**Goal:** a session is never killed by its configuration and the guards work with none;
preferences resolve in declared layers whose every key has a class; repository gates keep their
ratchet as one reusable relation; and every approval on a machine is one record in core, driven
by one `stayfixed trust` family — the foundation HS2, HS3, CP2 and PF1 build on.

**Architecture:** the hook path stops refusing on configuration: `config.session.session_config`
answers a `Config` for every checkout — the file's, the preset's floor where there is no file, or
the floor plus a warning where the file does not load — and `Config.origin` tells handlers which.
`config.classes` holds one class per key and `config.layers` resolves preferences over the layers
C7 names; HS1 wires the preset, the repository and the machine file, and HS2 adds the overlay's
three. `assess.rule` keeps judging a pull request against its base and gains `judge_layer`, the
same relation applied to a layer. `stayfixed.approvals` replaces `src/stayfixed/memory/trust.py`'s private
record with a core one keyed by kind and subject; areas contribute kinds through an `approvals.py`
module discovered like `doctor.py`, and the new core area `trust` is the command family.

**Tech Stack:** Python ≥ 3.11 standard library at runtime; `uv`, pytest (`-n auto`), ruff, mypy,
the mutation oracle (`scripts/mutation_oracle.py`), towncrier fragments in `changelog.d/`.

**Spec:** the agent-harness extraction design, in a private repository this one cannot link to —
§15.8 decisions 4 (the value floor), 5 (the machine owner's freedom), 11 (approvals), 12 (key
classes), 13 (layers), 15 (the ratchet) and 43 (contracts); §5.4 (machine paths, from the
password database's home); §9.4 (in-repo notes as data). The umbrella plan fixes the launch
graph, the release window and file ownership.

**Scope:** pull request HS1 of package harness-sources (licensed changes to C1, C4 and C5 by
§15.8 decision 43). A change belongs here iff it (a) makes a session survive its configuration or
lets the guards run without one; (b) classes a configuration key or resolves a preference over
layers; (c) lets the base branch or the machine owner raise a budget, or reshapes `assess.rule`
into a reusable relation; (d) moves an approval into `stayfixed.approvals` or adds the `trust`
family, its kinds, its terminal check, its `ask` rule or the boundary's `doctor` row; or (e)
restates the documents those changes falsify. Out: the overlay's layers, binding, pins and the
`overlay`/`checkout` kinds (HS2); `harness` memory and the reviewed record (HS3); `profiles` as
a list (PF1); `regressions` (CP2).

**Premise:** measured on 2026-10-15 at `dev` = `22a9cad`. A task that finds one no longer holds
stops and reports the mismatch.

- `src/stayfixed/hooks/commands.py` `run_hook` loads `stayfixed.toml` only when it is a regular
  file; a `ConfigError`, `PathEscape` or `PathUnasked` reaches `_unloadable`, which exits 2 on
  every event `refuses_on_internal_error` names (`PreToolUse` among them), and a symlinked file
  reaches `_linked` with the same verdicts. A `MachineConfigError` is re-raised into the generic
  internal-error arm. With no file, `config` is `None`.
- Four handlers return early on `config is None`: `_bg_cleanup` and `_test_hygiene`
  (`src/stayfixed/guards/hooks.py`), `_link_worktree` (`src/stayfixed/memory/hooks.py`),
  `_overlay_status` (`src/stayfixed/attach/hooks.py`).
- `src/stayfixed/config/loader.py` `loads` refuses an unknown section and `_build` an unknown key
  with `ConfigError`; `preset_defaults(project, *, preset)` builds a `Config` from the preset
  alone. `Config` (`src/stayfixed/config/schema.py`) has twelve fields and no default.
- `Budgets.effective` is `min(preset, configured)`: nothing can raise a budget.
  `src/stayfixed/assess/rule.py` judges `budgets.*` with `_budget` (lower or equal is tightened,
  anything else refused), `state`/`enforced` with `_enforcement`, `gates.builtin` and
  `gates.custom.*` by their rows, and every other key with `_other` (refused while the base
  enforces anything, noted otherwise) — `ledger.code_roots` and
  `ledger.evidence_boundary_required_for` among them.
- `src/stayfixed/memory/trust.py` keeps the one approval record, `trust.json` beside the machine
  file (`_trust_file`, `_recorded`, `_write_record`, `UnreadableTrustRecord`), keyed by the
  store's resolved path; `stayfixed memory trust --in-repo-memory` (`run_trust`) writes it with no
  terminal check. "memory trust" appears in 9 source files, 5 test files, `docs/cli.md`,
  `README.md`, `CONTRIBUTING.md` and `docs/methodology/principles.md`.
- `src/stayfixed/setup/run.py` `_write_user_settings` merges deny rules and `pluginConfigs` into
  the user settings and never writes `permissions.ask`. The machine file has the tables
  `[personal]`, `[overlay]` and `[machine]` (`src/stayfixed/setup/machine.py` `write_machine`).
- Areas are discovered by submodule name (`src/stayfixed/areas.py` `area_modules`,
  `area_imports`); `doctor`'s core checks are the `CHECKS` tuple in
  `src/stayfixed/doctor/checks.py`, first `not-initialised`.

## Global Constraints

- Runtime imports the standard library only; every write goes through `stayfixed.fsops`; a value
  the repository wrote is printed through `stayfixed.printed`, never raw (`CONTRIBUTING.md`).
- The machine's home is the password database's (`config.machine.passwd_home`), never `HOME` or
  `XDG_*` from the environment (§5.4); the approval record lives beside the machine file
  (§15.8 decision 11), never in an overlay.
- A hook's exit code is 0 or 2; `PreToolUse` refuses only when a guard decides to, never because
  configuration did not load (decision 4). A containment failure refuses the value, never the
  session.
- Core never imports a delivery area (`attach`, `memory`, `overlay`); `tests/boundaries/`
  holds it. A kind a delivery area owns reaches core through discovery, as `doctor.py` does.
- Every new assertion ships with the mutation that reddens it, in the group file
  `scripts/mutation_oracle.py` `GROUP_OF` routes its source to (`src/stayfixed/` → `core`,
  `memory/` → `records`, `setup/` → `install`, `doctor/` → `doctor`, `assess/` → `assess`,
  `guards/` → `guards`), or a sentence saying why none exists.
- Each task restates the documents its change falsifies (`docs/cli.md` sections, `README.md`,
  `SECURITY.md`, skills) and writes its changelog fragment in `changelog.d/` in the same commit.
- The approval boundary is stated honestly: approvals hold against repository bytes and a
  `git pull`, never against an agent with an unsandboxed shell; the terminal check and the `ask`
  rule are speed bumps (decision 11).

## Execution contract

Copied verbatim from the umbrella plan, "Execution contract"; the controller copies the relevant
part into every brief.

1. **The wave is the dispatch unit.** Waves are lettered and own a run of continuously numbered
   tasks; one implementer, one review round and one reviewer per dispatched wave, every task
   keeping its own failing test, verification and commit. An implementer's first pass is sized
   for about 200k tokens: at most about 900 plan lines and three tasks per wave. Resume the same
   implementer for a fix round only while its context is under about 300k; past that, the round
   goes to a fresh agent with the review package. The controller records each implementer's
   token total in the plan's Findings. Every subagent runs on Opus (`model: opus`).
2. **Every implementer brief says:** report a mismatch with the tree instead of guessing; run a
   command and paste what it printed before writing any claim about it; focused runs while
   iterating and one full run before the commit; a plan's predicted mutation outcome is a
   hypothesis — design your own if it does not redden, and paste the raw output either way; no
   line numbers from the plan; this brief is a message, not a file, so cite only the plan; write
   nothing under the repository but the task's files, use `<scratchpad>/<wave>-<role>/`, never
   run a script you did not write, and read `git diff --stat` before committing; the static
   checks at CI's scope (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`);
   start a long run in the background and wait on its own output, never with `pgrep`.
3. **Every reviewer brief adds:** run every command yourself and never use the Agent tool; do not
   run `git checkout`, `restore`, `stash` or `clean`; what already passed, by sha and suite, and
   run only the test that decides a finding you suspect; no citation may point at a brief, a
   dispatch or a report; what later tasks own.
4. **The final review** of each pull request is at least four parallel read-only seats:
   correctness, architecture, security, and a lifecycle seat that walks section 5 of this
   contract against the diff.
5. **The lifecycle matrix**, walked at pre-flight like a task and again by the lifecycle seat:
   every command the pull request adds or changes × every change of configuration — set a value,
   change it, unset it, move a path, a step that fails part-way, `uninstall` — and, from HS1 on,
   × every layer that can carry the value (preset, repository, the overlay's three scopes, the
   machine file).
6. **The parallelism map.** Read-only seats run beside each other and beside the implementer;
   writers of one worktree serialise; one mutation oracle runs at a time per host; no local full
   gate runs while a pull request's CI runs on the self-hosted runner.
7. **Templates.** A fix brief enumerates the sibling instances of the defect's class (the
   `sweep-defect-class` skill) and reports the neighbour probes it ran. A security ruling names
   its minimal preconditions, its anchor's provenance (who can write the bytes it trusts), and
   one legitimate user it must not refuse.
8. **Verification.** The controller re-verifies only heads it pushes or merges, re-derives the
   pull request's body from the diff before every push, and reads `gh pr checks` until every job
   has ended before reporting a pull request done.
9. **Second finding at one seam.** At the second review finding that points at the same function,
   reader or boundary, the next step is a redesign of that seam put to the owner, not a third
   patch.

## Review Focus

Inputs no task below would exercise unless it is told to; each line's test is added to the task
named.

1. **A `stayfixed.toml` from a newer release** — an unknown section, an unknown key and an
   unknown enum value together (`[memory] mode = "harness"`). Expected: `ls` is allowed, the
   guards still judge, one warning line at `SessionStart`. Task 2 and Task 3.
2. **A broken machine file** (not TOML) during a session. Expected: the guards run on the
   preset's `[personal]`, the warning names the machine file, not `stayfixed.toml`. Task 2.
3. **An empty `stayfixed.toml`** (valid TOML, no `project.name`). Expected: the fallback, never
   the floor's "no configuration" wording. Task 2.
4. **`trust.json` present and `approvals.json` absent** (every machine on `0.3.0`). Expected:
   each recorded memory approval still answers approved, with no prompt. Task 7.
5. **`stayfixed trust approve memory` from an agent's shell tool** (stdin not a terminal).
   Expected: exit 2, the exact command for a person to run, and no byte written. Task 8.

---

## Waves

| Wave | Tasks | Dispatched | Plan lines (approx.) |
|---|---|---|---|
| A | 1 | no — controller and owner | 40 |
| B | 2–3 | yes | 190 |
| C | 4–6 | yes | 260 |
| D | 7–9 | yes | 280 |
| E | 10 | no — controller | 40 |

**Launch graph** (drawn over the Interfaces blocks): A → D (Task 9 writes the settings Task 1
measured); B → C (Task 5 resolves over the `Config` that Task 2 gives an origin and Task 3 gives
notes); C → D (Task 9 adds `guards.approval_ask` to Task 4's table and Task 5's `Guards`). Every
dispatched wave writes `src/stayfixed/config/schema.py`, so B, C and D run in that order.

---

### Wave A — Task 1 (controller and owner, not dispatched)

#### Task 1: Measure the boundary's settings on Claude Code

Decision 11 rests on settings no one has run here. Record each answer, with the command and what
it printed, in Findings under "Task 1"; Task 9 consumes them.

**Files:** none in the tree.

- [ ] **Step 1:** in a scratch configuration (`CLAUDE_CONFIG_DIR=<scratchpad>/a1-cfg`, no
  credentials beyond the owner's token file, as the wave-7 delivery spike ran), with Claude Code
  `claude --version` recorded: with `sandbox.enabled = true` and with it unset, ask a `-p` turn to
  run `printf x >> <home>/.config/stayfixed/approvals.json` through its shell tool. Record which
  setting stops the write, the exact keys, and whether a `permissions.deny` rule of the form
  `Edit(<path>)` or `Write(<path>)` also stops a shell write or only the file tools.
- [ ] **Step 2:** with `permissions.ask` holding `Bash(stayfixed trust approve:*)`, ask an
  interactive turn and a `-p` turn to run `stayfixed trust approve memory`. Record what each
  surface does (prompt, deny, run) and the exact rule spelling that matched.
- [ ] **Step 3:** with a `SessionStart` hook printing `{"systemMessage": "x"}` and exit 0, record
  whether the terminal and the desktop Code tab show `x` to the person, and whether it reaches
  the model's context. Task 2 chooses its warning's channel from this.
- [ ] **Step 4:** remove the scratch configuration with the owner's yes.

---

### Wave B — Tasks 2–3 (dispatched)

#### Task 2: The value floor — every checkout gets a `Config`, and a session never dies of one

**Files:**
- Create: `src/stayfixed/config/session.py` (create)
- Modify: `src/stayfixed/config/schema.py`, `src/stayfixed/config/loader.py`,
  `src/stayfixed/hooks/commands.py`, `src/stayfixed/hooks/dispatch.py`,
  `src/stayfixed/guards/hooks.py`, `src/stayfixed/memory/hooks.py`,
  `src/stayfixed/attach/hooks.py`
- Test: `tests/config/test_session.py` (create), `tests/hooks/test_floor.py` (create)
- Modify: `docs/cli.md` (the `hook <event>` and Hooks sections), `README.md` (what runs without
  `stayfixed.toml`), `mutations/core.toml`

**Interfaces:**
- Consumes: `loader.load`, `loader.preset_defaults`, `ConfigError`, `MachineConfigError`,
  `PathEscape`, `PathUnasked`; Task 1's answer on `systemMessage`.
- Produces:
  - `schema.Origin(StrEnum)`: `FILE = "file"`, `FLOOR = "floor"`, `FALLBACK = "fallback"`.
  - `schema.Config.origin: Origin = Origin.FILE` — the last field, with a default, so every
    existing constructor is unchanged.
  - `session.SessionConfig(config: Config, warning: str | None)` (frozen).
  - `session.session_config(root: Path | None, *, machine: Path | None = None) -> SessionConfig`
    — never raises for anything the repository or the machine file holds.
  - `session.FLOOR_PROJECT = "project"` — the floor's `project.name`, a value the grammar admits
    and no repository-derived text.
  - `dispatch.dispatch(..., notice: str | None = None)` — a `SessionStart` notice rendered on
    the channel Task 1 chose; ignored on every other event.

- [ ] **Step 1: Write the failing tests** in `tests/config/test_session.py`:

```python
def test_no_file_is_the_floor(tmp_path):
    answer = session_config(tmp_path, machine=tmp_path / "none.toml")
    assert answer.config.origin is Origin.FLOOR and answer.warning is None
    assert answer.config.project.name == FLOOR_PROJECT

@pytest.mark.parametrize("text", ['[memory]\nmode = "harness"\n', "", "[[[", '[paths]\nbugs = "../x"\n'])
def test_a_file_that_does_not_load_falls_back_with_a_warning(tmp_path, text):
    (tmp_path / "stayfixed.toml").write_text(text)
    answer = session_config(tmp_path, machine=tmp_path / "none.toml")
    assert answer.config.origin is Origin.FALLBACK
    assert answer.warning == FALLBACK_WARNING     # stayfixed's words; no byte of `text`

def test_a_symlinked_file_falls_back(tmp_path): ...       # origin FALLBACK, LINKED_WARNING

def test_a_broken_machine_file_falls_back_naming_the_machine_file(tmp_path):
    (tmp_path / "stayfixed.toml").write_text(MINIMAL)   # loads
    (tmp_path / "m.toml").write_text("[[[")
    answer = session_config(tmp_path, machine=tmp_path / "m.toml")
    assert answer.config.origin is Origin.FILE            # the project's file is fine
    assert answer.config.personal == preset_personal()
    assert answer.warning == MACHINE_WARNING
```

  `MINIMAL` is the smallest `stayfixed.toml` the loader accepts (`[project] name = "p"` under
  the preset); `preset_personal()` reads the preset's `[defaults.personal]`. The warnings are
  module constants in `session.py`, each naming the file class and the command that prints the
  detail (`stayfixed docs check` for `stayfixed.toml`, `stayfixed doctor` for the machine file),
  as `UNLOADABLE` does today.

- [ ] **Step 2: Write the failing hook tests** in `tests/hooks/test_floor.py`, through `run_hook`
  with a crafted payload (`tests/crafted.py`) and the stdin seam the existing hook tests use:

```python
def test_an_unloadable_file_never_refuses_a_command(tmp_path, ...):
    write(tmp_path / "stayfixed.toml", '[memory]\nmode = "harness"\n')
    code, out, err = run_pretooluse(tmp_path, command="ls")
    assert code == 0

def test_the_background_guard_judges_without_a_file(tmp_path, ...):
    code, _, err = run_pretooluse(tmp_path, command="sleep 9 &")
    assert code == 2 and BG_CLEANUP_REASON in err      # the guard's own refusal

def test_the_background_guard_judges_under_a_fallback(tmp_path, ...): ...   # same, broken file

def test_session_start_carries_the_warning_once(tmp_path, ...):
    write(tmp_path / "stayfixed.toml", "[[[")
    out = run_sessionstart(tmp_path)
    assert out.count(FALLBACK_WARNING) == 1

@pytest.mark.parametrize("handler", ["worktree-link", "overlay-status", "test-hygiene"])
def test_project_handlers_stay_silent_off_the_file(tmp_path, handler, ...): ...
```

  The last test runs each handler with a `FLOOR` and a `FALLBACK` config and asserts it returns
  the empty result it returned for `None`; a handler registered later that reads repository
  paths joins its parameter list.

- [ ] **Step 3: Run them.** `uv run pytest tests/config/test_session.py tests/hooks/test_floor.py -q`.
  Expected: the session tests fail on import, the hook tests fail with exit 2 on `ls`.
- [ ] **Step 4: Implement.** `session_config`: no root or no file → `preset_defaults(FLOOR_PROJECT)`
  with `origin=FLOOR`; a symlink, a `ConfigError` other than `MachineConfigError`, `PathEscape`
  or `PathUnasked` → the same with `origin=FALLBACK` and the matching warning; a
  `MachineConfigError` → load the project's file with the preset's `Personal` in place of the
  machine file's (`loads(..., personal=...)`) and `MACHINE_WARNING`; if that load fails too, the
  fallback with both warnings joined. `run_hook` calls it once, passes `notice=answer.warning`
  only on `SessionStart`, and writes the warning to the diagnostics sink on every other event
  (the sink's `diagnostic`, reason `config-fallback`). `_linked`, `_unloadable` and their
  constants go. `_bg_cleanup` drops its `config is None` arm; the three project handlers test
  `config.origin is not Origin.FILE` instead of `config is None`.
- [ ] **Step 5: Mutations.** In `mutations/core.toml`: `session_config` answering `FILE` for the
  fallback; `run_hook` passing the notice on every event; `_bg_cleanup` keeping its early return.
  Expected: each reddens its named test in this task.
- [ ] **Step 6: Documents.** `docs/cli.md`'s `hook <event>` section: the exit-code table loses
  "configuration does not load → refused"; the Hooks section states the floor, the fallback and
  the one warning. `README.md`'s "What runs where" paragraph: the guards run in any repository
  where the plugin is enabled. Fragment `changelog.d/+value-floor.change.md`.
- [ ] **Step 7: Run** `uv run pytest tests/config tests/hooks tests/guards tests/memory tests/attach -q -n auto`,
  then the full suite once. Expected: green.
- [ ] **Step 8: Commit** — `feat(hooks): never refuse a session for its configuration, and run the guards without one`.

#### Task 3: Unknown keys from a newer release are noted, not refused, where a session reads them

**Files:**
- Modify: `src/stayfixed/config/loader.py`, `src/stayfixed/config/session.py`,
  `src/stayfixed/doctor/checks.py`
- Test: `tests/config/test_loader_unknown.py` (create), `tests/doctor/test_configuration_row.py` (create)
- Modify: `docs/cli.md` (Configuration; the `doctor` table), `mutations/core.toml`, `mutations/doctor.toml`

**Interfaces:**
- Consumes: Task 2's `session_config`.
- Produces:
  - `loader.Unknown(StrEnum)`: `REFUSE = "refuse"` (every command but the session and
    `doctor`), `NOTE = "note"`.
  - `loader.loads(..., unknown: Unknown = Unknown.REFUSE) -> Config` and
    `loader.load(..., unknown: Unknown = Unknown.REFUSE) -> Config`.
  - `schema.Config.notes: tuple[str, ...] = ()` — under `NOTE`, one sentence per dropped section
    or key, naming the section and key by the grammar the loader holds them to and never quoting
    a value.
  - A core `doctor` check `configuration`, second in `CHECKS`: green when `notes` is empty, a
    warning row listing them otherwise.

- [ ] **Step 1: Write the failing tests:**

```python
def test_an_unknown_section_is_dropped_with_a_note_under_note(tmp_path):
    config = loads('[project]\nname = "p"\n[newer]\nx = 1\n', tmp_path, unknown=Unknown.NOTE, machine=NONE)
    assert config.notes == (UNKNOWN_SECTION_NOTE.format(section="newer"),)

def test_an_unknown_key_is_dropped_with_a_note_under_note(tmp_path): ...   # [memory] future = 1

def test_refuse_stays_the_default(tmp_path):
    with pytest.raises(ConfigError):
        loads('[project]\nname = "p"\n[newer]\n', tmp_path, machine=NONE)

def test_an_unknown_value_is_not_a_note(tmp_path):
    with pytest.raises(ConfigError):     # an enum value is a value, not a key: Task 2's fallback
        loads('[project]\nname = "p"\n[memory]\nmode = "harness"\n', tmp_path, unknown=Unknown.NOTE, machine=NONE)

def test_the_session_reads_with_note(tmp_path): ...    # origin FILE, notes non-empty, no warning
def test_doctor_lists_the_notes(tmp_path): ...         # row "configuration", WARN, both notes
```

  A key of a section stayfixed reserves for another layer (`guards`, `overlay`, `machine`) gets
  its own note, `RESERVED_SECTION_NOTE`, which says the section belongs to the machine file —
  §15.8 decision 5's "never from `stayfixed.toml`".

- [ ] **Step 2: Run** `uv run pytest tests/config/test_loader_unknown.py tests/doctor/test_configuration_row.py -q`.
  Expected: fail (no `unknown` parameter, no row).
- [ ] **Step 3: Implement.** `loads` and `_build` take the mode; under `NOTE` an unknown section
  or key is removed from `raw` before validation and recorded; everything else refuses as today.
  `session_config` loads with `NOTE`; `doctor` builds its `Config` with `NOTE` and the new row
  reports what was dropped. `gate`, `docs check`, `bugs check`, `plan check` keep `REFUSE`.
- [ ] **Step 4: Mutations:** `_build` dropping a key under `REFUSE`; the row ignoring `notes`.
  Expected: each reddens its test.
- [ ] **Step 5: Documents** — Configuration: which commands refuse an unknown key and which note
  it. Fragment `changelog.d/+unknown-keys.change.md`.
- [ ] **Step 6: Run** the config, hooks and doctor tests, then the full suite once. Expected: green.
- [ ] **Step 7: Commit** — `feat(config): a session and doctor note what a newer release added instead of refusing it`.

---

### Wave C — Tasks 4–6 (dispatched)

#### Task 4: Every configuration key has one class

**Files:**
- Create: `src/stayfixed/config/classes.py` (create)
- Test: `tests/config/test_classes.py` (create)
- Modify: `CONTRIBUTING.md` ("Configuration": a field needs its class), `mutations/core.toml`

**Interfaces:**
- Produces:
  - `classes.KeyClass(StrEnum)`: `MACHINE_ONLY`, `PREFERENCE`, `SESSION_PARAMETER`,
    `GATE_PARAMETER`, `REPOSITORY_ONLY`, `PLUGIN_OWNED`.
  - `classes.CLASSES: Mapping[str, KeyClass]` — keyed by dotted key (`memory.mode`) or a section
    wildcard (`project.*`, `paths.*`, `personal.*`, `guards.*`, `native_caps.*`, `ci.*`,
    `commit_messages.*`).
  - `classes.class_of(key: str) -> KeyClass` — exact key first, then the section wildcard;
    `KeyError` for a key with neither.
  - `classes.GATE_BUDGETS: frozenset[str]` and `classes.SESSION_BUDGETS: frozenset[str]` — the
    split of `Budgets.NAMES`.

- [ ] **Step 1: Write the failing tests.** The table is §15.8 decision 12's, row for row:

```python
def test_every_schema_field_has_exactly_one_class():
    for key in schema_keys():
        class_of(key)                      # KeyError names the field with no class
    assert exact_keys(CLASSES) <= set(schema_keys())   # no row for a key that does not exist
    # schema_keys(): every dotted key the dataclasses of `Config` define (Budgets.NAMES,
    # NativeCaps.NAMES and Gates.custom as `gates.custom`), plus `guards.bg_cleanup`;
    # exact_keys(): the table's keys that are not section wildcards.

def test_the_budget_split_is_total_and_disjoint():
    assert GATE_BUDGETS | SESSION_BUDGETS == set(Budgets.NAMES)
    assert not GATE_BUDGETS & SESSION_BUDGETS
    assert SESSION_BUDGETS == {"memory_index_words", "startup_rules_words",
                               "volatile_notes_words", "volatile_ttl_days"}

@pytest.mark.parametrize("key, expected", [
    ("personal.reply_language", KeyClass.MACHINE_ONLY), ("guards.bg_cleanup", KeyClass.MACHINE_ONLY),
    ("memory.mode", KeyClass.PREFERENCE), ("memory.groups", KeyClass.PREFERENCE),
    ("budgets.startup_rules_words", KeyClass.SESSION_PARAMETER),
    ("budgets.agents_md_lines", KeyClass.GATE_PARAMETER), ("stayfixed.state", KeyClass.GATE_PARAMETER),
    ("ledger.code_roots", KeyClass.GATE_PARAMETER), ("gates.custom", KeyClass.GATE_PARAMETER),
    ("paths.bugs", KeyClass.REPOSITORY_ONLY), ("stayfixed.preset", KeyClass.REPOSITORY_ONLY),
    ("native_caps.hook_output_chars", KeyClass.PLUGIN_OWNED),
])
def test_decision_12s_rows(key, expected):
    assert class_of(key) is expected
```

  `stayfixed.profile` is `PREFERENCE` here and PF1 renames it; a field PF1, HS3 or CP2 adds fails
  `test_every_schema_field_has_exactly_one_class` until its row lands, which is the point.

- [ ] **Step 2: Run** `uv run pytest tests/config/test_classes.py -q`. Expected: import error.
- [ ] **Step 3: Implement** the module as a table and two lookups; each row's comment names
  decision 12's reason in a clause.
- [ ] **Step 4: Mutation:** move `ledger.code_roots` to `REPOSITORY_ONLY`. Expected: the
  parametrised row reddens.
- [ ] **Step 5: Commit** — `feat(config): class every key, so a layer knows what it may set`.

#### Task 5: Preferences resolve in layers; the machine owner switches a session guard

**Files:**
- Create: `src/stayfixed/config/layers.py` (create)
- Modify: `src/stayfixed/config/schema.py`, `src/stayfixed/config/loader.py`,
  `src/stayfixed/config/session.py`, `src/stayfixed/setup/machine.py`,
  `src/stayfixed/guards/hooks.py`, `src/stayfixed/doctor/checks.py`
- Test: `tests/config/test_layers.py` (create), `tests/guards/test_guard_switch.py` (create),
  `tests/doctor/test_preferences_row.py` (create)
- Modify: `docs/cli.md` (Configuration, `doctor`, `setup`), `mutations/core.toml`,
  `mutations/guards.toml`

**Interfaces:**
- Consumes: Task 4's `class_of`; Task 2's `Config.origin`.
- Produces:
  - `layers.LayerName(StrEnum)`: `PRESET`, `REPOSITORY`, `COMMON`, `PROJECT`, `MACHINE_SCOPE`,
    `MACHINE_FILE`; `layers.ORDER` is that tuple, lowest first.
  - `layers.Layer(name: LayerName, values: Mapping[str, object])` (frozen; dotted keys).
  - `layers.Effective(value: object, layer: LayerName)` (frozen).
  - `layers.resolve(stack: Sequence[Layer]) -> Resolution` where
    `Resolution(values: Mapping[str, Effective], refused: tuple[tuple[str, LayerName], ...])`:
    for each key whose class is `PREFERENCE`, `SESSION_PARAMETER` or `MACHINE_ONLY`, the highest
    layer in `ORDER` that sets it wins; a `MACHINE_ONLY` key from `REPOSITORY` is dropped into
    `refused`; `GATE_PARAMETER`, `REPOSITORY_ONLY` and `PLUGIN_OWNED` keys are not resolved here
    (Task 6 and the loader own them). A list preference's merge rule is its own: `resolve` takes
    `merge: Mapping[str, Callable[[object, object], object]]`, empty in HS1 (PF1 adds `profiles`'
    union).
  - `schema.Guards(bg_cleanup: bool = True)` and `schema.Config.guards: Guards = Guards()`;
    `schema.Config.preferences: Mapping[str, Effective]`, defaulted through
    `field(default_factory=dict)` — what `doctor` prints.
  - The machine file's new tables `[guards]` (`bg_cleanup = false`) and `[budgets]` (the session
    budgets only); `src/stayfixed/setup/machine.py` `write_machine` carries both through untouched, as it does
    every table.

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_higher_layer_wins_and_says_which():
    got = resolve([Layer(PRESET, {"memory.mode": "local-only"}),
                   Layer(REPOSITORY, {"memory.mode": "in-repo"}),
                   Layer(MACHINE_FILE, {"memory.mode": "local-only"})])
    assert got.values["memory.mode"] == Effective("local-only", MACHINE_FILE)

def test_the_repository_cannot_set_a_machine_only_key():
    got = resolve([Layer(PRESET, {"guards.bg_cleanup": True}), Layer(REPOSITORY, {"guards.bg_cleanup": False})])
    assert got.values["guards.bg_cleanup"] == Effective(True, PRESET)
    assert got.refused == (("guards.bg_cleanup", REPOSITORY),)

def test_gate_parameters_are_not_layered_here():
    got = resolve([Layer(REPOSITORY, {"budgets.agents_md_lines": 10})])
    assert "budgets.agents_md_lines" not in got.values

def test_the_owner_switches_the_background_guard_off_in_the_machine_file(tmp_path, ...):
    machine = tmp_path / "m.toml"; machine.write_text("[guards]\nbg_cleanup = false\n")
    code, _, _ = run_pretooluse(tmp_path, command="sleep 9 &", machine=machine)
    assert code == 0

def test_a_repository_cannot_switch_it_off(tmp_path, ...): ...   # [guards] in stayfixed.toml → note, guard still refuses
def test_a_session_budget_from_the_machine_file_raises_the_preset(tmp_path): ...
def test_doctor_prints_each_preference_with_its_layer(tmp_path): ...   # row "preferences"
```

  A test that names a machine file passes it as `--machine` or through the owner-home seam the
  existing hook tests use (`tests/ownerhome.py`); none reads the real `~/.config/stayfixed`.

- [ ] **Step 2: Run** the three new files. Expected: import errors and the guard refusing.
- [ ] **Step 3: Implement.** The loader builds the `PRESET` and `REPOSITORY` layers from the
  dataclass values it already derives and a `MACHINE_FILE` layer from the machine file's
  `[personal]`, `[guards]` and `[budgets]`, resolves them, and sets `personal`, `guards`, the
  session budgets' configured values and `preferences` from the resolution. `_bg_cleanup`
  returns the empty result when `config.guards.bg_cleanup` is false. `doctor`'s `preferences`
  row lists every resolved key as `key = value (layer)`, values through `printed.printable`.
  The machine file's `[guards]` and `[budgets]` keys are validated against `Guards` and
  `SESSION_BUDGETS`; an unknown one is a note, as Task 3's are.
- [ ] **Step 4: Mutations:** `resolve` letting `REPOSITORY` set a `MACHINE_ONLY` key;
  `_bg_cleanup` ignoring the switch. Expected: each reddens its test.
- [ ] **Step 5: Documents.** Configuration gains "Layers" (the order, and which classes each
  layer may set, from decision 12's table); `setup`'s section names the two new machine tables;
  `doctor`'s table gains `preferences`. Fragment `changelog.d/+layers.feature.md`.
- [ ] **Step 6: Run** the config, guards, hooks, setup and doctor tests, then the full suite once.
- [ ] **Step 7: Commit** — `feat(config): resolve preferences in layers, and let the machine owner switch a session guard`.

#### Task 6: Budgets the base branch may raise, and the ratchet as one relation

**Files:**
- Modify: `src/stayfixed/config/schema.py` (`Budgets.effective`), `src/stayfixed/assess/rule.py`,
  `src/stayfixed/doctor/checks.py` (`_budgets`)
- Test: `tests/assess/test_rule_layers.py` (create), `tests/config/test_budgets_raise.py` (create)
- Modify: `docs/cli.md` (Configuration, `gate`), `README.md` (budgets), `mutations/assess.toml`,
  `mutations/core.toml`

**Interfaces:**
- Consumes: Task 4's `GATE_BUDGETS`, `SESSION_BUDGETS`.
- Produces:
  - `Budgets.effective(name) -> int` — the configured value when one is set, else the preset's;
    no ceiling but the platform caps its consumers already apply.
  - `rule.judge_layer(base: Config, layered: Config) -> tuple[Change, ...]` — every key's verdict
    for a layer applied over `base`, through the same rows as `judge`, with no upgrade admitted
    (a layer never moves `stayfixed.version` or `ci.ref`). HS2 applies the overlay's layers with
    it; a `REFUSED` change keeps the base's value.
  - Rows: `budgets.<gate budget>` → `_budget` (unchanged); `budgets.<session budget>` →
    `_neutral`; `ledger.code_roots` and `ledger.evidence_boundary_required_for` → `_additive`
    (a superset is `TIGHTENED`, equal `NEUTRAL`, anything else `_other`).

- [ ] **Step 1: Write the failing tests:**

```python
def test_the_base_branch_raises_a_budget(tmp_path):
    config = loads(MINIMAL + "[budgets]\nagents_md_lines = 900\n", tmp_path, machine=NONE)
    assert config.budgets.effective("agents_md_lines") == 900          # preset is lower

def test_a_pull_request_still_may_only_lower_a_gate_budget(tmp_path): ...   # REFUSED when raised
def test_a_pull_request_may_change_a_session_budget(tmp_path): ...          # NEUTRAL either way
def test_adding_a_code_root_tightens(tmp_path): ...                         # TIGHTENED
def test_removing_a_code_root_is_refused_while_enforcing(tmp_path): ...     # REFUSED
def test_a_layer_cannot_upgrade(tmp_path): ...       # judge_layer on a changed ci.ref → REFUSED
def test_judge_layer_agrees_with_judge_on_every_row(tmp_path): ...          # same verdicts
```

- [ ] **Step 2: Run** them. Expected: the raise reads the preset, the code-root rows read `_other`.
- [ ] **Step 3: Implement** the rows and `judge_layer` (a `_Sides` whose `workflow_sha` is `None`
  and whose `released` answers `None`, which `_upgrade` already reads as "no upgrade"). `doctor`'s
  `budgets` row says "raised" or "lowered" against the preset and names a clamp only where a
  consumer applies a platform cap.
- [ ] **Step 4: Mutations:** `_additive` admitting a subset; `effective` keeping `min`. Expected:
  each reddens its test.
- [ ] **Step 5: Documents.** Configuration: who may raise and who may only lower, per budget;
  `gate`: the two `ledger` rows. Fragment `changelog.d/+budgets-raise.change.md`.
- [ ] **Step 6: Run** the assess, config and doctor tests, then the full suite once.
- [ ] **Step 7: Commit** — `feat(assess): let the base branch raise a budget, and judge a layer by the pull request's rows`.

---

### Wave D — Tasks 7–9 (dispatched)

#### Task 7: One approval record, in core

**Files:**
- Create: `src/stayfixed/approvals.py` (create)
- Modify: `src/stayfixed/memory/trust.py`
- Test: `tests/test_approvals.py` (create)
- Modify: `SECURITY.md` (what an approval holds against), `mutations/core.toml`,
  `mutations/records.toml`

**Interfaces:**
- Consumes: `config.machine.machine_config_path`, `fsops`, `jsonobject.json_object`.
- Produces:
  - `approvals.RECORD = "approvals.json"`, beside the machine file; `LEGACY = "trust.json"`.
  - `approvals.Approval(kind: str, subject: str, digest: str, approved_at: str)` (frozen).
  - `approvals.State(StrEnum)`: `APPROVED`, `LAPSED` (recorded, other digest), `MISSING`.
  - `approvals.UnreadableApprovals(Refusal)` — the record exists and does not parse; never
    overwritten.
  - `approvals.record_path(machine: Path | None) -> Path | None`.
  - `approvals.recorded(machine: Path | None) -> dict[tuple[str, str], Approval]` — the record,
    and, while `approvals.json` does not exist, every `trust.json` entry read as kind `memory`.
  - `approvals.state(machine, kind: str, subject: str, current: str) -> State`.
  - `approvals.approve(machine, kind, subject, digest, *, now: datetime) -> Approval` and
    `approvals.revoke(machine, kind, subject) -> bool` — the first write imports the legacy
    entries; `trust.json` is left as it is.
  - `src/stayfixed/memory/trust.py` keeps its public functions (`state`, `record`, `may_inject`,
    `approval_recorded`, `require_readable_record`, `snapshot`, `refresh_if_trusted`) and their
    behaviour; each reads and writes through `approvals` with kind `memory` and the store's
    path key. `UnreadableTrustRecord` becomes an alias of `UnreadableApprovals`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_machine_on_0_3_0_keeps_its_memory_approvals(tmp_path):
    (tmp_path / "trust.json").write_text(json.dumps({"/s": "d"}))
    assert state(tmp_path / "config.toml", "memory", "/s", "d") is State.APPROVED

def test_the_first_write_imports_and_leaves_the_legacy_file(tmp_path): ...
def test_a_broken_record_refuses_and_is_never_overwritten(tmp_path):
    (tmp_path / "approvals.json").write_text("{")
    with pytest.raises(UnreadableApprovals):
        approve(tmp_path / "config.toml", "memory", "/s", "d", now=T0)
    assert (tmp_path / "approvals.json").read_text() == "{"
def test_lapsed_and_missing_are_told_apart(tmp_path): ...
def test_two_kinds_never_share_a_subject(tmp_path): ...     # ("memory","/s") vs ("checkout","/s")
def test_the_record_is_beside_the_machine_file_and_ignores_xdg(tmp_path, monkeypatch): ...
```

  And in `tests/memory/test_trust.py`, the existing tests stay green untouched: they are the
  proof that `src/stayfixed/memory/trust.py`'s behaviour did not move.

- [ ] **Step 2: Run** them. Expected: import error.
- [ ] **Step 3: Implement.** One JSON object `{"version": 1, "approvals": [ {kind, subject,
  digest, approved_at}, … ]}`, written through `fsops`; a record of an unknown `version` is
  `UnreadableApprovals`. `src/stayfixed/memory/trust.py` delegates.
- [ ] **Step 4: Mutations:** `recorded` skipping the legacy import; `approve` writing over an
  unreadable record. Expected: each reddens its test.
- [ ] **Step 5: Documents.** `SECURITY.md`: approvals hold against repository bytes and a
  `git pull`; against an agent with an unsandboxed shell the harness's write restriction is the
  boundary. Fragment `changelog.d/+approvals.change.md`.
- [ ] **Step 6: Run** `tests/test_approvals.py tests/memory tests/attach`, then the full suite once.
- [ ] **Step 7: Commit** — `feat: keep every approval on the machine in one core record`.

#### Task 8: `stayfixed trust list | approve | revoke`, with kinds the areas contribute

**Files:**
- Create: `src/stayfixed/trust/__init__.py` (create), `src/stayfixed/trust/commands.py` (create),
  `src/stayfixed/memory/approvals.py` (create)
- Modify: `src/stayfixed/approvals.py` (the kind protocol), `src/stayfixed/memory/commands.py`
  (the alias), the refusal sentences that name `memory trust` in `src/stayfixed/memory/`,
  `src/stayfixed/attach/` and `src/stayfixed/hooks/`, `skills/attach/SKILL.md`
- Test: `tests/trust/test_commands.py` (create), `tests/trust/__init__.py` (create)
- Modify: `docs/cli.md` (a `trust` section; `memory trust` marked an alias until `0.5.0`),
  `README.md` (the command table), `CONTRIBUTING.md` ("Areas": the `approvals.py` convention),
  `tests/boundaries/` (the discovered `approvals.py` is not a core-to-delivery import),
  `mutations/core.toml`

**Interfaces:**
- Consumes: Task 7's record.
- Produces:
  - `approvals.Subject(key: str, label: str, digest: str)` (frozen) — `label` is what a person
    reads, printed through `printed.printable`.
  - `approvals.ApprovalKind(name: str, describe: Callable[[Path, Path | None], Subject])`
    (frozen) — `describe(root, machine)` computes the subject of the checkout at `root`.
  - `approvals.kinds() -> dict[str, ApprovalKind]` — every `stayfixed.<area>.approvals.KINDS`,
    through `areas.area_modules("approvals")`; two kinds of one name refuse.
  - `approvals.INTERACTIVE: Callable[[], bool] = sys.stdin.isatty` — the seam tests replace.
  - `trust` commands: `trust list [--json]`; `trust approve KIND`; `trust revoke KIND`; each
    takes the shared `--root` and `--machine` flags. `approve` and `revoke` refuse with exit 2
    when `INTERACTIVE()` is false, printing `NOT_A_TERMINAL`, which names the exact command for a
    person to run; neither ever accepts `--yes`.
  - `src/stayfixed/memory/approvals.py` (create): `KINDS = (ApprovalKind("memory", _describe),)`, where `_describe`
    resolves the store as `memory trust` does today and its digest is `trust.store_digest`.
  - `memory trust --in-repo-memory` runs `trust approve memory` and prints `ALIAS_NOTE`
    (the new spelling, and that the alias is removed in `0.5.0`).

- [ ] **Step 1: Write the failing tests:**

```python
def test_an_agent_cannot_approve_from_its_shell(tmp_path, monkeypatch):
    monkeypatch.setattr(approvals, "INTERACTIVE", lambda: False)
    code, out = cli(["trust", "approve", "memory", "--root", str(repo), "--machine", str(m)])
    assert code == 2 and "stayfixed trust approve memory" in out
    assert not (tmp_path / "approvals.json").exists()

def test_a_person_approves_and_list_says_approved(...): ...
def test_revoke_removes_only_that_subject(...): ...
def test_list_reads_lapsed_after_a_note_changes(...): ...
def test_an_unknown_kind_names_the_known_ones(...): ...
def test_the_alias_does_what_approve_does_and_says_so(...): ...
def test_kind_discovery_refuses_a_duplicate_name(...): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/trust -q`. Expected: no `trust` command.
- [ ] **Step 3: Implement** the area (`register(groups)` as every area's `commands.py`), the
  discovery and the memory kind. Every sentence that told a person to run `stayfixed memory trust
  --in-repo-memory` now names `stayfixed trust approve memory` and says to run it in a terminal;
  the existing tests asserting those sentences are updated in the same commit, by name.
- [ ] **Step 4: Mutations:** `approve` skipping the terminal check; `kinds` accepting a duplicate.
  Expected: each reddens its test.
- [ ] **Step 5: Documents.** `docs/cli.md`'s `trust` section with its writes (the record), its
  exit codes, and the boundary sentence; the README row; `CONTRIBUTING.md`'s convention. Fragment
  `changelog.d/+trust.feature.md` and `changelog.d/+memory-trust-alias.upgrading.md`.
- [ ] **Step 6: Run** `tests/trust tests/memory tests/attach tests/test_documents.py tests/skills
  tests/boundaries`, then the full suite once.
- [ ] **Step 7: Commit** — `feat(trust): one command family for every approval, asked of a person at a terminal`.

#### Task 9: The `ask` rule, and `doctor`'s approval-boundary row

**Files:**
- Modify: `src/stayfixed/setup/run.py` (`_write_user_settings`), `src/stayfixed/doctor/checks.py`
- Test: `tests/setup/test_ask_rule.py` (create), `tests/doctor/test_approval_boundary.py` (create)
- Modify: `docs/cli.md` (`setup`, `doctor`), `skills/setup/SKILL.md`, `mutations/install.toml`,
  `mutations/doctor.toml`

**Interfaces:**
- Consumes: Task 1's measured rule spelling and sandbox keys; Task 5's `guards` machine table.
- Produces:
  - `src/stayfixed/setup/run.py` `ASK_RULES: tuple[str, ...]` — the rules for `trust approve`, `trust revoke`
    and (for HS3) `memory promote`, in Task 1's spelling. `_write_user_settings` adds the missing
    ones to `permissions.ask`, and removes exactly these strings when the machine file holds
    `[guards] approval_ask = false`; it never touches another rule.
  - `schema.Guards.approval_ask: bool = True`, a `MACHINE_ONLY` key (Task 4's table gains its row).
  - A core `doctor` check `approval-boundary`: red unless the user settings hold Task 1's
    sandbox setting and a deny rule covering the approval record's directory; the row's detail
    names the two settings to add and says what they stop.
  - `setup --approval-boundary` writes those two settings, with the owner's confirmation in the
    skill, through the same merge.

- [ ] **Step 1: Write the failing tests:**

```python
def test_setup_adds_the_ask_rules_once(tmp_path): ...            # twice → no duplicates
def test_setup_removes_only_its_own_rules_when_switched_off(tmp_path): ...
def test_setup_never_touches_another_ask_rule(tmp_path): ...
def test_doctor_is_red_without_the_sandbox(tmp_path): ...
def test_doctor_is_green_with_the_sandbox_and_the_deny_rule(tmp_path): ...
def test_approval_boundary_writes_both_and_keeps_the_rest(tmp_path): ...
```

- [ ] **Step 2: Run** them. Expected: no rules written, no row.
- [ ] **Step 3: Implement** with Task 1's spellings as module constants, each with a comment
  naming Task 1's Findings and the Claude Code version measured.
- [ ] **Step 4: Mutations:** the removal taking every `ask` rule; the row passing without the deny
  rule. Expected: each reddens its test.
- [ ] **Step 5: Documents** — `setup`: the `ask` rules and how to switch them off, and
  `--approval-boundary`; `doctor`: the row; the setup skill asks before `--approval-boundary`.
  Fragment `changelog.d/+approval-boundary.feature.md`.
- [ ] **Step 6: Run** the setup and doctor tests, then the full suite once.
- [ ] **Step 7: Commit** — `feat(setup): an ask rule on approvals, and doctor's approval-boundary row`.

---

### Wave E — Task 10 (controller, not dispatched)

#### Task 10: Final review and the pull request

- [ ] **Step 1:** run, once, on the branch's head: `uv run pytest -n auto --cov --cov-fail-under=92`,
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
  `uv run python scripts/mutation_oracle.py`, `uv run stayfixed plan check`. Paste each result
  into Findings.
- [ ] **Step 2:** the four seats of the execution contract, in parallel, on Opus; the lifecycle
  seat walks every command this pull request changed (`hook <event>`, `trust list | approve |
  revoke`, `memory trust`, `setup`, `setup --approval-boundary`, `doctor`) × set, change, unset,
  a broken file, a newer release's file, `uninstall` × the preset, repository and machine-file
  layers. Fix rounds follow the contract.
- [ ] **Step 3:** open the pull request into `dev` with a body derived from the diff: what a
  session no longer refuses, what the owner may now switch or raise, the new record and command,
  and what HS2, HS3, CP2 and PF1 take from it (the Interfaces blocks above). Read `gh pr checks`
  until every job has ended.

---

## Findings

Written by Tasks 1 and 10, and by the controller when a wave's implementer reports (its token
total, its fix rounds).
