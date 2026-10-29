# Wave 10, CX — Codex parity of the core, as measured: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. **The wave is the dispatch
> unit, not the task:** one implementer per lettered wave, with every task inside it keeping its own
> failing test, verification and commit. Wave M is the controller's and the owner's, and dispatches
> no implementer. Wave A is the one implementer wave, and lands in one pull request into `dev` with
> one final review (the umbrella's "Execution contract", item 4). This plan cites that section by path
> and does not copy it.

**Goal:** say exactly what stayfixed does on Codex, measured on the Codex release current at the
lane's start, and make the code agree only where a measurement gives it a signal to read. That covers
five things:
- the red-run note, from the bug ledger's BR-014;
- how a person trusts the plugin's hooks;
- how skills reach a Codex session;
- the `Stop`-hook recipe on Codex;
- `attach` under Codex's `workspace-write` sandbox.

**Architecture:** two waves, in order.
- **Wave M** measures (Tasks 1–3), with no implementer. The controller prepares a scratch Codex home
  and a scratch repository, and reads every file Codex writes. The owner runs the steps that need a
  signed-in session.
- **Wave A** (Tasks 4–6) is one implementer on branch `wp/codex-parity`. It turns each measurement
  into the smallest change it licenses: one more payload shape for `red_exit`, or none; the
  registry's `reach` and the README's Codex text; the recipe's Codex section and `attach`'s sandbox
  sentence.

Nothing emulates Codex. No task reads a format Codex calls unstable, and none models Codex's trust
store.

**Tech Stack:** Python ≥ 3.11 standard library; `uv`, pytest (`-n auto`), ruff, mypy, the mutation
oracle (`scripts/mutation_oracle.py`, entries routed by `GROUP_OF`), towncrier fragments in
`changelog.d/`; the Codex CLI from npm (`@openai/codex`), installed into a scratch prefix.

**Spec:** the wave-10 umbrella plan, `docs/plans/2026-10-28-wave-10-umbrella.md`:
- lane CX in "Lanes", and its row of "Lane-plan items";
- the edges DM → CX and CX → RD2 in "Launch graph";
- the `README.md`, `src/stayfixed/harnesses.py`, `src/stayfixed/guards/` and `doctor` rows of "File
  ownership and hot spots";
- items 12 and 14 of "Directory and launch inputs".

The private design's §15.10 decision 6 is carried by the CX row, restated here:

> **Measure first, on the Codex version current at the lane's start, before fixing tasks:**
> - whether stayfixed's hooks run once trusted, and how a person trusts them;
> - what Codex's `PostToolUse` carries for the red-run note (BR-014), which speaks on a signal Codex
>   gives or stays documented as silent;
> - how skills reach a Codex session;
> - DM's `Stop`-hook recipe on Codex, whose `Stop` documents only a block.
>
> Nothing emulates Codex. The README's capability table and `doctor` say exactly what was measured,
> with the version and the date. Done when the table is filled; a fix it finds beyond BR-014 is
> filed. Every Codex run is the owner's to start where it needs a signed-in session.

Items 12 and 14 add four things:
- **The recipe.** Codex continues a blocked `Stop` with the reason as a new prompt and caps nothing,
  so there the recipe's `stop_hook_active` let-through is the only bound.
- **BR-014.** On 0.165.0, `PostToolUse`'s `tool_response` is a string with no exit code, and Codex
  has no failure-only event. One route is unmeasured: the hook reading the command's output from
  the session transcript.
- **Trust.** It is keyed by the entry's position and, since 0.164.0, by a hash of the plugin's
  files, so every release asks a Codex user to approve the hooks again. The README promises nothing
  else, and no release reorders `hooks/hooks.json`.
- **The sandbox.** Under `workspace-write`, an `attach` the model runs likely cannot write
  `<repo>/.codex/rules/`, since `.codex` stays read-only; the denial text is recorded.

Codex's public directory reportedly lists no plugin with lifecycle hooks. The capability table states
that only from a dated source.

**Scope:** package launch-readiness, wave 10, lane CX (the umbrella's "Lanes" table), one pull request
on `wp/codex-parity`. Contracts consumed: C5 (the CLI: `stayfixed hook`, `attach`, `doctor`). Contract
produced: none new. The registry's `Reach` values and the README's Codex text change only to what
Task 1 to Task 3 measured. Out:
- the README beyond the Codex capability table and its paragraph, which RD2 rewrites;
- a `doctor` row for Codex hook trust. Reading Codex's trust record would model another tool's state,
  and no verdict needs it. The README says where the trust is granted instead. **Ruling:** the CX
  row asks that `doctor` "say exactly what was measured". `doctor`'s one Codex row, `cli-path`, says
  that a skill invoking `stayfixed` by name fails on Codex without it on `PATH`. Task 5 re-checks
  that sentence against Task 1 and moves it to `V`, or deletes it, and adds no row. If this is wrong,
  the cost is one row a later pull request adds once a verdict needs it;
- Codex's public directory: no task submits there;
- any fix the measurements find beyond BR-014. The controller files it in the bug ledger with the
  `file-bug` skill, and this plan's Findings names its id;
- any gate behaviour. This lane touches no file under `src/stayfixed/assess/` and no gate.

**Premise:** measured on 2026-10-29 at `dev` = `d00b726` (DM merged as #154). The controller
re-measures it at Wave M's start and stops on a mismatch.
- **The registry.** In `src/stayfixed/harnesses.py`, `CODEX` has `settings = (".codex/hooks.json",)`,
  `plugin_root_env = "PLUGIN_ROOT"` and `render = hook_specific_output`, and its `detects` reads
  `PLUGIN_ROOT` or a payload holding both `model` and `permission_mode`. Its `reach` holds three
  values:
  - NOTICES is `_CODEX_HOOKS_UNVERIFIED`: tier `None`, `measured_on="Codex CLI 0.162.0-alpha.17.2"`;
  - GATES is CI only;
  - METHOD is instructions only, `measured_on="Codex CLI 0.160.0"`.
- **The README.** The table in "What each agent enforces" reads `not verified`, `CI only` and
  `instructions only` for `codex`, and `tests/test_documents.py` generates it from the registry. The
  paragraph below it cites Codex CLI 0.162.0-alpha.17.2 with no date. It says that untrusted hooks
  are skipped "without a message", that a failed command arrives on `PostToolUse` with no exit code,
  that whether a stayfixed hook is trusted "is not measured", and that `attach` delivers Codex its
  rules alone, in `.codex/rules/`.
- **The red-run note.** The `test-hygiene` handler (`src/stayfixed/guards/hooks.py`) is registered on
  `PostToolUse` and `PostToolUseFailure` with one once-key. It speaks only when `red_exit`
  (`src/stayfixed/guards/hygiene.py`) finds a non-zero int `tool_response.exit_code`, or an `error`
  starting `Exit code N`.
- **The plugin.** `.codex-plugin/plugin.json` declares neither `skills` nor `hooks`. Codex's plugin
  documentation says a plugin's `skills/` and `hooks/hooks.json` are found at the plugin root by
  default. `scripts/plugin_tree.py` `PLUGIN_PATHS` ships both, beside `.codex-plugin/plugin.json`.
- **`hooks/hooks.json`** has seven `SessionStart` entries, each with `additionalContextLimit: 0`, and
  one each on `PreToolUse`, `PostToolUse` and `PostToolUseFailure` matching `Bash`. It has no `Stop`
  entry.
- **`doctor`** reports 14 rows, and only `cli-path` names Codex.
- **The recipe.** `examples/stop-hook/` is Claude Code only: its README names no Codex behaviour.
- **Codex, desk-read on 2026-10-29.** npm's `@openai/codex` is 0.166.0, and no `codex` is installed
  on the controller's machine. Codex's hooks reference (`https://developers.openai.com/codex/hooks.md`)
  says:
  - a non-managed hook, a plugin's included, runs only once its current definition's hash is trusted
    in `/hooks`, and Codex prints a warning naming `/hooks` when hooks await review;
  - `PostToolUse` runs after a Bash command that exits non-zero too, with `tool_response` the tool's
    "model-facing output";
  - `transcript_path` "isn't a stable interface for hooks";
  - `Stop` carries `stop_hook_active`, "exit `0` with no output is treated as success", and exit 2's
    stderr becomes a new prompt;
  - the default `workspace-write` sandbox keeps `<writable_root>/.git` and, when it exists as a
    directory, `<writable_root>/.codex` read-only (`https://developers.openai.com/codex/sandbox.md`).
    `codex sandbox macos|linux [--permissions-profile <name>] -- COMMAND` runs a command under a
    sandbox with no model call, and the page names no default profile.

  Codex's plugin pages (`https://developers.openai.com/plugins/build/plugins.md`) add three things:
  - a local marketplace is read from `$REPO_ROOT/.agents/plugins/marketplace.json`, a legacy
    `.claude-plugin/marketplace.json`, or `~/.agents/plugins/marketplace.json`;
  - an installed plugin is copied to `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/` and
    loaded from that copy;
  - "Lifecycle hooks are supported for plugins installed manually in Codex desktop", and plugins
    holding lifecycle hooks "aren't eligible for the public plugin directory".

  This is documentation, read on 2026-10-29, not measurement. Wave M measures each point it relies on.
- **What stayfixed says at a session's start.** In a scratch repository whose `stayfixed.toml`
  carries one unknown key, `stayfixed hook SessionStart` with a Codex-shaped payload prints
  `additionalContext` beginning `stayfixed: stayfixed.toml loaded with 1 setting(s) ignored`. The
  controller ran it on 2026-10-29 at `d00b726`. With a valid file and no attached overlay, it prints
  no context, and neither memory bundle prints anything. So the scratch repository plants that one
  unknown key, and the text is the canary Task 2 looks for.

## Execution contract

The wave-10 umbrella plan's section "Execution contract" (`docs/plans/2026-10-28-wave-10-umbrella.md`)
binds this lane. The controller copies the relevant part into every brief.

**This lane's size:**
- **Wave M:** no subagent. The controller runs the steps marked **(controller)**. The owner runs the
  steps marked **(owner)**, eight sessions in all:
  - one interactive session to trust the hooks;
  - six short ones for the three simulated releases, two each: review after the change, re-trust
    after the restore;
  - one `codex exec` of a few model turns.

  Only the `codex exec` calls the model. Each owner step gives its exact commands and the files the
  controller reads afterwards.
- **Wave A:** one implementer dispatch, then one final review with two read-only seats and one
  scoped re-review. No security seat: the diff touches no anchor that repository bytes cannot move.
- **Expected net size:**
  - `src`: between −5 and about +15. The red-run note gains one shape if Task 2 finds a field it
    does not read yet; comments and docstrings are re-dated or deleted;
  - tests: between 0 and about +40;
  - mutation entries: 0 or +1;
  - docs: about ±60 (`README.md`'s Codex paragraph, `docs/cli.md`'s Codex sentences,
    `examples/stop-hook/README.md`'s Codex section).

  No other area grows.
- **The lifecycle matrix** walks no layer: the lane adds and removes no configuration key.

**The pull request body** carries:
- the Codex version and the date of every measurement;
- the Findings table;
- each ledger id the measurements filed.

The body says nothing about gate behaviour.

## Global constraints

- **Measured or unsaid.** Every Codex sentence that ships names the Codex CLI version it was measured
  on, and the date. Wave M measures some sentences on `V`. A sentence it does not re-measure keeps
  its own version and date: 0.162.0-alpha.17.2 on 2026-10-13 for the `--dangerously-bypass-hook-trust`
  and blocking-`PreToolUse` sentences. A sentence with no recorded measurement is deleted, never kept
  as "likely". A documentation page may be cited as documentation with the date it was read, never as
  a measurement.
- **No emulation.** No code reads any of these:
  - `transcript_path`, a rollout file or the `--json` event stream;
  - Codex's trust store or config files;
  - text inside `tool_response` that Codex formats for the model.

  `red_exit` reads a field only if it is a structured field of Codex's own `PostToolUse` payload.
- **Recorded, not hand-built.** A test fixture of a Codex payload holds the bytes Task 2 recorded.
  Only the session id, the turn id, the model slug and the paths are replaced by placeholders, and the
  fixture's comment names the version and the date.
- Standard library only at runtime; no new dependency; writes through `fsops` (`CONTRIBUTING.md`).
- **Public text.** No file outside `docs/plans/` names a wave, a task, a decision id, the plans' word
  for a unit of work, the private design or the owner's private repository. `tests/test_public_anchors.py`
  and `tests/test_neutral.py` hold this. Commit ids in this plan are seven characters.
- **Commits** follow `CONTRIBUTING.md`: `fix(guards): …`, `docs(readme): …`, `docs(examples): …`,
  `refactor(harnesses): …`. One towncrier fragment per user-visible change: type `fix` if BR-014
  speaks on Codex, else `change`.
- `docs/plans/*` and `CHANGELOG.md` are history and are not edited.

## Review focus

Each line is a failure the lane could cause that no single task's tests would show, with what pins it.

1. **A hand-built payload passes as measured.** That was BR-014's own evidence gap. Pinned by Task 4's
   fixture rule (Global constraints), and by the correctness seat diffing the fixture against Task 2's
   recorded file in the Findings.
2. **The Claude Code path moves.** The note must still speak on `PostToolUseFailure` and stay silent
   after a green run. Pinned by `tests/guards/test_hooks.py`'s
   `test_a_red_pytest_over_a_dirty_tree_is_noticed` and `test_a_green_run_or_a_non_pytest_command_is_silence`,
   run in Task 4, Step 4.
3. **The note speaks after a green run on Codex.** That happens if the new shape reads a field Codex
   also sets on success. Pinned by Task 4's test on the recorded green payload.
4. **A Codex sentence ships unmeasured or undated.** Task 5's sweep lists every Codex sentence in
   `README.md`, `docs/cli.md` and the comments and docstrings under `src/stayfixed/`, each with its
   disposition. The correctness seat re-runs the sweep's `grep`. `tests/test_documents.py` holds only
   the table's tiers, not the paragraph's versions.
5. **The recipe loops on Codex.** Codex caps no continuation, so the let-through is the only bound.
   Task 3 measures it once on `V`, and nothing reddens if a later Codex changes it. The recipe's own
   unit test, `test_a_continued_stop_is_let_through_without_a_run`, holds only the recipe's branch.

---

## Wave M — Tasks 1–3 (measurements: the controller and the owner)

**The scene.** The controller writes every raw file under the plan's git-ignored workspace,
`.superpowers/sdd/2026-10-29-wave-10-codex-parity/codex/`, never under the repository. Into Findings it
pastes each command with its output, the paths and ids replaced by placeholders. Every owner block
starts with the same exports, which the controller fills in with absolute paths before handing it
over:

```bash
export X=<the workspace's codex/ directory>
export CX="$X/npm/node_modules/.bin/codex"
export HOME="$X/userhome"          # keeps the owner's own ~/.agents skills and marketplace out
export CODEX_HOME="$X/home"
export PATH="<this worktree>/.venv/bin:$PATH"   # this branch's stayfixed and pytest first
cd "$X/repo"
```

What is under `$X`:
- **`$X/repo`**, the scratch project. Codex is started from here. It holds:
  - a `stayfixed.toml` naming project `cx`, with `agents = ["codex"]` and the one unknown key the
    Premise's canary needs;
  - one uncommitted change;
  - tests/test_red.py (the scratch repository's, not this one's), one failing test;
  - tests/test_green.py, one passing test;
  - the marketplace file .agents/plugins/marketplace.json (the scratch repository's), naming the plugin `stayfixed` at the
    local path `$X/plugin`, in the format Codex's plugin page gives.
- **`$X/plugin`**, the plugin tree `scripts/plugin_tree.py render` makes from this branch's `HEAD`.
- **The user-level hooks**, written by the controller in `$CODEX_HOME/hooks.json`:
  - a recorder on `PostToolUse` (`Bash`) and on `Stop`. Each writes its stdin to two places,
    `$X/records/` and `$X/repo/.cx-records/`, so a sandboxed hook still leaves one of them. The
    second is listed in the scratch repository's `.git/info/exclude`;
  - a `Stop` wrapper that records its stdin, then runs `python3 -I <this worktree>/examples/stop-hook/prove_on_stop.py
    -- pytest -q tests/test_red.py`, records that run's exit code, stdout and stderr, and exits with
    the same code and the same stdout and stderr.

  The recorders and the wrapper are the controller's measurement scripts, kept in the workspace and
  never committed.

### Task 1: The install, the skills, the trust (controller, then owner)

**Interfaces:**
- Produces, in Findings:
  - `V`, the Codex version measured;
  - the commands that installed stayfixed into Codex from this branch;
  - a digest that shows the copy Codex loads is this branch's render;
  - whether Codex lists stayfixed's hooks and skills;
  - the startup text when hooks await review, verbatim;
  - what `/hooks` shows, and how a person trusts;
  - where trust is recorded, by file name only, its format left unread;
  - for each of three simulated releases, which entries `/hooks` asks to review again.
- Consumes: nothing.

- [ ] **Step 1 (controller): Install Codex into the scratch prefix.**
  - Run `npm view @openai/codex version` and set `V` from it.
  - Run `npm install --prefix "$X/npm" "@openai/codex@$V"`, then `"$CX" --version`.
  - Expected: `codex-cli $V`. Paste all three.
  - Also paste `"$CX" sandbox macos --help`; Task 3 picks its profile from it.
- [ ] **Step 2 (controller): Build the scene** as written above. Then run, under the exports:
  - `command -v stayfixed pytest`, expected to name this worktree's `.venv/bin`;
  - `stayfixed hook SessionStart` with a Codex-shaped payload, expected to print the canary text.

  Paste both.
- [ ] **Step 3 (controller): Install the plugin.** Under the exports, run the two verbs
  `src/stayfixed/setup/run.py` spells for `codex`: `codex plugin marketplace add "$X/repo"` and
  `codex plugin add stayfixed@<the marketplace's name>`. Paste every command, exit code and output.
  Then run `find "$CODEX_HOME/plugins/cache" -name hooks.json`. Compare the SHA-256 of the copy found
  with that of `$X/plugin/hooks/hooks.json`, and paste both.
  - If a verb needs a signed-in session, the owner runs this step's two commands, under the exports,
    right after `"$CX" login` in Step 4.
  - If neither verb installs a local plugin, the step records Codex's message. The owner then installs
    through `/plugins` in Step 4 and copies each screen.
- [ ] **Step 4 (owner): The trust session.** Under the exports:

  ```bash
  "$CX" login        # once, for this CODEX_HOME
  "$CX"
  ```

  In the session:
  1. If Codex asks whether to trust this directory, answer yes. It is the scratch repository.
  2. Copy the startup text that names `/hooks`, verbatim, or note that there is none.
  3. Open `/hooks`. Copy the list it shows: each entry's source and event.
  4. Trust every entry. Note each keypress or choice it took.
  5. Open `/skills`. Copy whether stayfixed's skills appear, by name.
  6. Quit without sending a prompt.

  The controller makes a stamp file before this step and runs `find "$CODEX_HOME" "$HOME" -type f
  -newer <stamp>` after it. It pastes the files created or changed, by name only.
- [ ] **Step 5 (owner and controller): Three simulated releases, each from a trusted state.** For
  each change below:
  1. The controller makes the change in `$X/plugin` and runs Step 3's `codex plugin add` again.
  2. The controller checks with Step 3's digest that the cached copy changed.
  3. The owner opens `"$CX"` under the exports and copies which entries `/hooks` lists for review.
  4. The owner trusts them all and quits.
  5. The controller restores `$X/plugin`, reinstalls it, and has the owner trust again, so that the
     next change starts from a trusted state.

  The three changes:
  - **(i)** one byte of `README.md`, outside `hooks/`, with `.codex-plugin/plugin.json`'s `version`
    raised;
  - **(ii)** one entry's `timeout` in `hooks/hooks.json`;
  - **(iii)** the `PreToolUse` and `PostToolUse` entries swapped in `hooks/hooks.json`, their
    contents unchanged.

  Umbrella item 14 expects that all three ask again. That is a hypothesis; record what happens. The
  step ends with the original render installed and `/hooks` showing nothing to review. The owner
  confirms that last state before Task 2.

### Task 2: What `PostToolUse` and `Stop` carry, and what reached the session (owner, then controller)

**Interfaces:**
- Produces, in Findings, for each `Bash` call of the run:
  - the recorded `PostToolUse` payload: its keys, the JSON type of `tool_response`, and every field
    that states an exit status;
  - whether `tool_response`'s text, the `--json` stream or the transcript at `transcript_path` holds
    the exit status. These are measured and recorded, and no code reads them;
  - whether the canary reached the session.

  It also produces the two `Stop` records and the wrapper's records.
- Consumes: Task 1, Step 5's trusted state.

- [ ] **Step 1 (owner): One `codex exec`.** Under the exports:

  ```bash
  "$CX" exec --sandbox workspace-write --json \
    "Run \`command -v stayfixed pytest\`, then \`pytest -q tests/test_red.py\`, then \`pytest -q tests/test_green.py\`. Do not edit any file. Then say done." \
    > "$X/exec.jsonl" 2> "$X/exec.err"
  ```

  It costs a few model turns: three commands, the `Stop` continuation the recipe asks for, and the
  let-through stop. The owner tells the controller when it has ended.
- [ ] **Step 2 (controller): Read the records.**
  - Paste every `PostToolUse` and `Stop` record and each wrapper record, scrubbed as Global
    constraints says. Say which of the two record directories each came from.
  - Paste the first `Bash` call's recorded output, to show which `stayfixed` and `pytest` ran.
  - From `$X/exec.jsonl` and the file at `transcript_path`, paste the lines for the two `pytest`
    calls, and say whether and in what words the exit status appears.
  - Search both for the canary text. Say whether it appears, and as what: developer context, a
    system message, or nothing.
- [ ] **Step 3 (controller): Name the BR-014 outcome**, as one of four:
  - **(a)** a structured field of `PostToolUse`'s payload states a non-zero exit for the red run, and
    none for the green one;
  - **(a′)** that field is `tool_response.exit_code` as an int, which `red_exit` already reads;
  - **(b)** only text states it: `tool_response`'s model-facing text, the stream or the transcript;
  - **(c)** nothing states it.

  Write the outcome into Findings, with the field's path for (a) or (a′).

### Task 3: The recipe on Codex, and `attach` under the sandbox (controller)

**Interfaces:**
- Produces, in Findings:
  - the recipe on Codex: each run's exit code, stdout and stderr, as the wrapper recorded them;
  - whether Codex reported a hook error for the run that exited 0 with empty stdout, from the stream;
  - whether the session took the exit 2 stderr as the next prompt;
  - whether `stop_hook_active` was `true` on the second stop;
  - how many `Stop` records one run made;
  - every path the sandbox denied `attach`, for a repository with and without a `.codex/` directory,
    with the sandbox profile and the platform named.
- Consumes: Task 2's records.

- [ ] **Step 1: Read the recipe's runs** from the wrapper's records, and Codex's handling of each
  from `$X/exec.jsonl`. Expected: two `Stop` records. In the first, `stop_hook_active` is false and
  the recipe exits 2. In the second, it is true and the recipe exits 0 with empty stdout, and Codex
  reports no hook error. That is a hypothesis.
- [ ] **Step 2: Count the continuations.** More than two `Stop` records, or a second one whose
  `stop_hook_active` is not `true`, means the recipe does not bound itself on Codex. The controller
  files that in the bug ledger, and Task 6 says so in the recipe's README.
- [ ] **Step 3: `attach` under the sandbox.**
  - Copy the demo's act 6 setup (its overlay and machine file, as `examples/demo/demo.py` builds them)
    into the workspace, with one rule file in the overlay's `common/codex/`, so that `attach` has a
    rule to place.
  - With a `.codex/` directory present, run `"$CX" sandbox macos --permissions-profile <the
    workspace-write profile Step 1's help names> --log-denials -- stayfixed attach --machine <file>
    --json`.
  - Run it again with no `.codex/` directory.
  - Paste both outputs, their exit codes, and every denied path. The binding id's directory under the
    git common directory and the `~/.local/share/stayfixed/` render may be denied too. Each denial is
    recorded with its path, so the `.codex/` cause is told apart from the others.

  On Linux the command is `codex sandbox linux`. This step records macOS and names the platform.

**Wave M ends** when Findings holds every Task 1 to Task 3 output above. The controller then writes
Wave A's brief from those Findings. A row with no answer is stated as "not measured on Codex `V`",
never guessed.

---

## Wave A — Tasks 4–6 (one implementer, branch `wp/codex-parity`)

### Task 4: BR-014, as Task 2 measured it

**Files:**
- Modify: `src/stayfixed/guards/hygiene.py` (`red_exit`), outcome (a) only;
  `src/stayfixed/guards/hooks.py` (the "placeholder for parity with Codex" comment on the
  `PostToolUse` registration)
- Create: `tests/fixtures/codex-hooks/red.json`, `tests/fixtures/codex-hooks/green.json`, outcomes (a)
  and (a′) only (not a `codex/` directory: `tests/test_neutral.py` reads `codex/` followed by a
  dashed name as a vendor branch)
- Modify: `docs/cli.md` (the `PostToolUse` registration's sentence and the red-run note's Codex
  sentence)
- Test: `tests/guards/test_hygiene.py`, `tests/guards/test_hooks.py`
- Mutations: `mutations/guards.toml`, one entry, outcome (a) only

**Interfaces:**
- Consumes: Task 2, Step 3's outcome and, for (a) or (a′), the field's path.
- Produces:
  - **(a)** `red_exit(raw)` returns the non-zero exit that Codex's field states, and `None` for the
    green payload. The Claude Code shapes are unchanged. The field is Codex-written, not command
    output. If it is a string the command's own output can reach, the outcome is (b), not (a).
  - **(a′)** `red_exit` is unchanged. The recorded fixtures pin that it already reads Codex.
  - **(b) and (c)** `red_exit` is unchanged. `docs/cli.md` says the note is silent on Codex `V`,
    because its `PostToolUse` payload carries no structured exit status. For (b), it adds where the
    status does appear, and that Codex calls the transcript no stable interface for hooks.
  - Every outcome rewrites the registration comment to say what the registration does on Codex `V`.

- [ ] **Step 1: Write the tests.** For (a) and (a′):
  - `test_a_red_codex_run_reports_its_exit`: `red_exit` of the red fixture equals the recorded
    exit code.
  - `test_a_green_codex_run_reports_none`: `red_exit` of the green fixture is `None`.
  - In `tests/guards/test_hooks.py`, `test_a_red_codex_pytest_over_a_dirty_tree_is_noticed`: the red
    fixture through `stayfixed hook PostToolUse` over a dirty tree gives the note, as the Claude Code
    case does.

  For (b) and (c), no test is added: the code is unchanged.
- [ ] **Step 2: Run them.** Run `uv run pytest -q tests/guards -k codex`. Expected: FAIL for (a).
  For (a′) they pass already: they are the regression tests on recorded bytes, and no mutation entry
  is added.
- [ ] **Step 3: For (a), read the field in `red_exit`**, beside the two shapes it reads, with the same
  int and bool checks. Add the mutation entry: the new branch removed, expected to redden
  `test_a_red_codex_run_reports_its_exit`.
- [ ] **Step 4: Run and watch them pass.** Run `uv run pytest -q tests/guards`. Expected: PASS, with
  `test_a_red_pytest_over_a_dirty_tree_is_noticed` and
  `test_a_green_run_or_a_non_pytest_command_is_silence` among them.
- [ ] **Step 5: Edit `docs/cli.md` and the comment** for the outcome. Commit `fix(guards): the
  red-run note reads Codex's exit status` for (a); `test(guards): the red-run note on Codex's recorded
  payloads` for (a′); `docs(cli): the red-run note is silent on Codex, as measured` for (b) and (c).
  The controller then closes or rejects BR-014 with the `close-bug` skill, citing the Findings. Under
  (b), the owner may overrule the "no text is read" rule (Global constraints) at this plan's review;
  without that, the note stays silent.

### Task 5: The registry's Codex reach, and every Codex sentence

**Files:**
- Modify:
  - `src/stayfixed/harnesses.py` (`_CODEX_HOOKS_UNVERIFIED` and the `CODEX` `reach`);
  - `README.md` (the table, by regeneration, and the paragraph below it);
  - `docs/cli.md` (its Codex sentences);
  - `src/stayfixed/doctor/checks.py` (the `cli-path` row's Codex sentence) and
    `src/stayfixed/doctor/commands.py` (its Codex docstring);
  - `.codex-plugin/plugin.json`, only if Task 1 found that Codex did not load the plugin's skills or
    hooks by default.
- Test: `tests/test_documents.py`, `tests/test_harnesses.py`, `tests/doctor/test_checks.py`

**Interfaces:**
- Consumes: Task 1's findings, and Task 2's canary finding.
- Produces:
  - `CODEX.reach[NOTICES]`: a `Reach` with `measured_on=f"Codex CLI {V}"`. Its tier is
    `Tier.CONTEXT` if Task 2 found the canary as developer context in the session. Otherwise it keeps
    tier `None`, with evidence saying what was measured.
  - `CODEX.reach[METHOD]` keeps its 0.160.0 record. Its evidence also cites `AGENTS.md`, which Wave M
    does not measure. The README paragraph states the skills finding on `V` separately.
  - **The sweep:** every hit of `grep -n "Codex" README.md docs/cli.md` and of
    `grep -rn "Codex" src/stayfixed` gets a disposition in the implementer's report:
    - re-dated to `V`, from a Findings row;
    - kept, with its own version and date;
    - deleted.
  - The README paragraph holds only sentences that pass the sweep. It covers:
    - how a person trusts the hooks, and which simulated releases asked again (Task 1, Step 5);
    - the startup text (Task 1, Step 4);
    - the red-run note's outcome;
    - whether skills arrive;
    - that `attach` delivers Codex its rules alone.

    The sentence "skips untrusted ones without a message" goes if Task 1 recorded a startup warning.
    The plugin-directory sentence cites the plugin page as documentation, read on 2026-10-29.

- [ ] **Step 1: Run the sweep's two `grep`s** and write the disposition table into the report before
  any edit.
- [ ] **Step 2: Edit the registry, then each swept sentence.** Regenerate the README table as
  `tests/test_documents.py` derives it, never by hand.
- [ ] **Step 3: Run** `uv run pytest -q tests/test_harnesses.py tests/test_documents.py
  tests/doctor/test_checks.py tests/test_public_anchors.py tests/test_neutral.py`. Expected: PASS. A
  test that pinned a deleted sentence is edited to the new text in the same commit.
- [ ] **Step 4: Commit:** `docs(readme): what stayfixed does on Codex <V>, as measured`.

### Task 6: The recipe's Codex section and `attach`'s sandbox sentence

**Files:**
- Modify: `examples/stop-hook/README.md`, `docs/cli.md` (the `attach` section)
- Test: `tests/test_documents.py`, `tests/test_public_anchors.py`

**Interfaces:**
- Consumes: Task 3's findings.
- Produces:
  - **The recipe's README** gains an "On Codex" section. It covers:
    - where the hook goes (Codex's own `hooks.json`), and that it runs only once trusted in `/hooks`;
    - that Codex continues a blocked stop with the reason as a new prompt and caps nothing, so the
      let-through is the only bound, as Task 3 measured it on `V`;
    - what Task 3 found about exit 0 with empty stdout.

    If Task 3, Step 2 found the recipe does not bound itself on Codex, the section says so first and
    names the ledger id.
  - **`docs/cli.md`'s `attach` section** gains one sentence on what Codex's `workspace-write` sandbox
    denied an `attach` the model runs, path by path as Task 3 recorded, and that a person runs
    `attach` themself.

- [ ] **Step 1: Write both texts** from Findings alone.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_documents.py tests/test_public_anchors.py
  tests/test_neutral.py`. Expected: PASS.
- [ ] **Step 3: Commit:** `docs(examples): the Stop recipe on Codex <V>, as measured`. Then add one
  fragment for the lane's user-visible change (Global constraints).

**Before the push (Wave A):** the full suite, the 3.13 run, the oracle whole if Task 4 took outcome
(a), and the static checks (the umbrella's contract, item 2). Then the controller opens the pull
request, reads its checks with `gh run watch <id> --exit-status`, and writes the Findings below.

---

## Findings

Written by Wave M's controller as each measurement lands, and when the pull request merges:
- the version `V`, and every measured output with its date;
- BR-014's outcome;
- the ledger ids filed;
- the head sha and the net size (`git diff --shortstat`);
- the review's findings and their triage.

**The plan's own three-lens review, 2026-10-29, before execution:** 30 findings, against `d00b726` and
the Codex pages read that day. This revision folds in every defect and risk:
- **the install source:** a local marketplace for this branch's render, checked by digest;
- **releases:** simulated through the cached copy, three of them, each from a trusted state, with
  entry order among them;
- **the canary:** a `SessionStart` canary in place of a note that is silent by construction;
- **the recipe's exit code:** recorded by a wrapper;
- **the outcome table:** a fourth outcome, (a′), and text inside `tool_response` named as (b);
- **`attach` under the sandbox:** a rule file to place, and every denied path recorded, with the
  profile named;
- **who ran:** `PATH` and `HOME` pinned for the owner;
- **the sweep:** every Codex sentence swept in `src` and `docs`;
- **the doctor ruling** written.

It drops one item: the unanchored "no release reorders `hooks/hooks.json`" (Task 1, Step 5 measures
order instead), and the circular `measured_on` test. B3 held: no step emulates Codex.
