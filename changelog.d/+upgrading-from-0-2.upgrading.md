Each item below is something a script, a CI step or a habit could rely on in 0.2.0 that is gone,
has moved or now ends differently, with a pointer to its entry in these notes, which has the
detail:

  - Restart every session that was running when you upgraded in place, from a local marketplace
    or `--plugin-dir`: it can still hold 0.2.0's hook commands, and four of them, its
    `preset-rules` and `index` session-start bundles, exit `2` under this release (Changed, "Two
    session-start bundles are gone").
  - `stayfixed adopt begin` is gone; `stayfixed adopt promote` moves a project out of
    `initialised` itself (Changed, "`stayfixed adopt begin` is gone").
  - `stayfixed test audit-entrypoints` is gone (Changed, "`stayfixed test audit-entrypoints` is
    gone").
  - The `stayfixed release` commands (`check`, `notes`, `hashes`) are gone from the installed CLI
    (Changed, "The `stayfixed release` commands are gone").
  - `stayfixed docs check` no longer takes `--memory-graph` or `--store`; `stayfixed memory refs`
    reports the link graph (Changed, "`stayfixed docs check --memory-graph` is gone").
  - `stayfixed memory session-context --bundle preset-rules` and `--bundle index` exit `2`, and
    `memory fit --json` has lost both bundles' keys (Changed, "Two session-start bundles are
    gone").
  - `stayfixed doctor` lists its checks in a new order, with one more: match a check by its name,
    not its position (Changed, "`stayfixed doctor` lists its checks in a new order").
  - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, for a hook entry
    claiming stayfixed's marker that nothing on this machine vouches for, your own checkout on a
    new machine before `stayfixed setup --overlay` has run among them (Fixed, "`stayfixed
    doctor`'s `hook-entries` row is red for a hook entry").
  - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, for the per-project
    entries of a checkout whose `origin` is not the remote its overlay record binds (Fixed,
    "`stayfixed doctor`'s `hook-entries` row no longer lets a repository borrow").
  - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, for a stayfixed entry
    in `.claude/settings.local.json` that is no longer exactly what your overlay grants: run
    `stayfixed attach --store …` again to rewrite it (Fixed, "`stayfixed doctor`'s `hook-entries`
    row now accounts for a stayfixed hook entry only where your overlay grants it").
  - `stayfixed test hygiene --json` reports its counts under `profiles`, by profile name (Changed,
    "The note after a failing test run now comes from the profile").
  - `stayfixed test hygiene` exits `2` on a tree past the stale-bytecode walk's new bound, where it
    named a count (Fixed, "The Python profile's check for stale bytecode now stops").
  - `stayfixed setup` meeting a machine configuration file it may not read exits `1`, where it
    exited `2` (Fixed, "`stayfixed setup` meeting a machine configuration file it is not allowed
    to read").
  - A hook's Python no longer reads `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE` or any other
    `PYTHON*` variable (Fixed, "The hook wrapper now starts Python in isolated mode").
  - Where `HOME` is not the home the password database records for your user, an empty one
    included, every command, at a terminal too, reads and writes
    `~/.config/stayfixed/config.toml` and `trust.json` under the database's home: move the two
    files you kept under `HOME` there before running `stayfixed setup` or `stayfixed memory trust`
    (Fixed, "stayfixed no longer takes your home directory from `HOME`").
  - In that case no hook makes the harness memory link, the link under `~/.claude/projects/`
    through which Claude Code reads the project's notes, and `stayfixed attach` run without a
    terminal, by an agent say, makes none either and says so, where 0.2.0 made it under `HOME`
    (Fixed, "stayfixed no longer takes your home directory from `HOME`").
  - At a terminal where `HOME` is set and empty, `stayfixed attach` and `stayfixed detach` refuse
    (exit `2`) and `stayfixed setup` fails (exit `1`) before writing anything (Fixed, "At a
    terminal where `HOME` is set and empty").
  - A user the password database lists no home for reads no machine configuration and no trust
    record unless `--machine` names one, and `stayfixed setup` and `stayfixed memory trust` fail
    (exit `1`) asking for it (Fixed, "stayfixed no longer takes your home directory from `HOME`").
  - `stayfixed overlay upgrade` and `overlay init` remove the template's copy of the `attach` skill
    and `common/rules/README.md`, keeping and naming a copy you edited (Changed, "`stayfixed
    overlay upgrade` and `overlay init` remove two files").
  - `stayfixed overlay upgrade`'s report and its `unchanged` count leave out a retired file that is
    gone, where 0.2.0 counted a missing `common/memory/README.md` (Fixed, "`stayfixed overlay
    upgrade` no longer lists a file a release no longer ships").
  - The background guard refuses a backgrounded `uv run <options> sleep`, such as
    `uv run --no-project sleep 30`, which 0.2.0 allowed (Fixed, "The background guard now reads a
    command started through `uv run`").
  - `stayfixed guard bg-cleanup` can exit `1` where 0.2.0 exited `0`, and the reverse, for a
    backgrounded chain whose `; echo`, or the command before it, runs through `uv run <options>`
    (Fixed, "The background guard now reads a command started through `uv run`").
  - `stayfixed plan check`, the `plan` gate and `stayfixed memory refs` report a missing backticked
    path whatever its extension, and one followed by a column or a nested symbol path (Fixed,
    "`stayfixed plan check`, the `plan` gate and `stayfixed memory refs` now check a backticked
    path in any language").
  - `stayfixed bugs check --base` and the `bugs` gate read the base's ledger where the base's own
    `stayfixed.toml` kept it, and fail (exit `1`) or refuse (exit `2`) a base copy that does not
    load, where each passed (Fixed, "`stayfixed bugs check --base`, and the `bugs` gate under
    `stayfixed gate`, now read").
  - A `[ledger] evidence_boundary_required_for` value other than `high`, `medium` or `low` is
    refused (exit `2`) by every command that reads the ledger (Fixed, "`[ledger]
    evidence_boundary_required_for` is now checked").
  - In overlay mode, `stayfixed memory index` and `memory fit` warn, and their `--json` reports
    `"trusted": false`, for every store until `stayfixed memory trust --in-repo-memory` has run
    (Fixed, "`stayfixed memory index` (with or without `--check`) and `stayfixed memory fit` now
    warn").
  - On Python 3.14, a settings file, ledger, manifest or trust record nested deeper than 10,000
    levels is refused, and turns `stayfixed doctor`'s `hook-entries` row red (Fixed, "On Python
    3.14, a JSON file nested deeper than").
  - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, for a marked entry
    nothing vouches for in a settings file that opens with a byte-order mark or holds a malformed
    value beside its valid hooks, where it warned (Fixed, "`stayfixed doctor`'s `hook-entries` row
    now judges the hook entries in a settings file that").
  - `stayfixed attach --check` exits as the run does, `2` or `1`, where the run refuses or fails
    before its first write past the gates `--check` reports instead, such as on a
    `.claude/settings.local.json` whose `permissions` is `null`, where 0.2.0 reported a clean diff
    and exited `0`: a CI step that ran it goes red (Fixed, "`stayfixed attach --check` now
    refuses, with exit `2`").
  - Your overlay's `permissions.json` or `hooks.json` holding `null` where rules or hook entries
    go, which 0.2.0 read as granting nothing, is refused (exit `2`) by `stayfixed attach` and
    `attach --check`: remove the key, or give it `{}` or `[]` (Fixed, "`stayfixed attach --check`
    now refuses, with exit `2`").
  - `stayfixed attach` and `attach --check` refuse (exit `2`) an overlay whose root or whose
    `projects/` is a file, where they failed (exit `1`) (Fixed, "`stayfixed attach` and `attach
    --check` now refuse (exit `2`) an overlay whose root").
  - `stayfixed attach`, `attach --check` and `detach` refuse (exit `2`), and `stayfixed setup`
    fails (exit `1`) on, a settings file whose indented write-back would pass 64 MiB; cut down by
    hand a `~/.claude/settings.json` that 0.2.0's `setup` wrote back past it (Changed, "`stayfixed
    attach`, `attach --check` and `stayfixed detach` now refuse, before anything is written, a
    `.claude/settings.local.json`").
  - A file a repository commits that stayfixed reads, and your overlay's record of a project, is
    read only up to 64 MiB, and a longer one, which 0.2.0 read whole, is one stayfixed cannot
    read (Fixed, "Every file a repository commits that stayfixed reads is now read only up to 64
    MiB").
  - Refusals and failures over a file that could not be read, written or removed give the reason
    in words, in parentheses, and name the file relative to the project or the overlay, where they
    quoted an error class or the error's text beside an absolute path: a script that matched the
    old text has to match the new (Fixed, "Every file a repository commits that stayfixed reads",
    in its last list).
  - A `.stayfixed/manifest.json` whose `format` is not a positive integer is refused as damaged
    (exit `2`) by `upgrade` and `uninstall`, where 0.2.0 read `true`, `0` or a negative integer as
    its own format (Fixed, "A `.stayfixed/manifest.json` whose `format` is not a positive
    integer").
  - `stayfixed detach` beside such a manifest leaves the `stayfixed:ignore` region in `.gitignore`
    in place (`ignore_region_removed: false`), where 0.2.0 took it out when the manifest did not
    record it (Fixed, "A `.stayfixed/manifest.json` whose `format` is not a positive integer").
  - `stayfixed bugs renumber` whose own write fails, and `stayfixed bugs new` and `bugs index`
    whose index write fails, exit `1`, where each ended in `internal error` with exit `2` (Fixed,
    "`stayfixed bugs renumber OLD NEW` killed part-way" and "`stayfixed bugs new` and `stayfixed
    bugs index` no longer end in `internal error`").
  - `stayfixed setup --git-hooks --uninstall` says what it found, and `--json` gains `found`, where
    0.2.0 printed `removed …` in every case (Fixed, "`stayfixed setup --git-hooks --uninstall` now
    says what it found").
  - `stayfixed setup --git-hooks` and its `--uninstall` refuse (exit `2`) a hook at mode 000,
    stayfixed's own or anyone's, which 0.2.0 chained, restored or called removed (Fixed,
    "`stayfixed setup --git-hooks --uninstall` now says what it found").
  - `stayfixed attach` run from a linked worktree no longer records `autoMemoryDirectory` in that
    worktree's `.claude/settings.local.json`, and run again takes back the key 0.2.0 recorded
    there (Fixed, "`stayfixed attach` run from a linked worktree").
  - `stayfixed doctor`'s `hook-entries` row warns, where 0.2.0 could read "all accounted for",
    about a skill, command or agent file whose frontmatter declares hooks or that it cannot read
    whole; the report's exit code is unchanged (Fixed, "`stayfixed doctor`'s `hook-entries` row
    now warns about each skill").
  - `stayfixed assess`'s `foreign-hooks` advice names a committed settings file whose hook entries
    all claim stayfixed's marker, which 0.2.0 passed over (Fixed, "`stayfixed assess`'s
    `foreign-hooks` item now lists").
  - A `stayfixed.toml` holding an integer of 2,147,483,648 or more fails to load (exit `1`), where
    0.2.0 loaded it (Fixed, "Every integer in `stayfixed.toml`").
  - A `stayfixed.toml` whose `[stayfixed] preset` is not a string fails with "stayfixed.preset
    must be a string; available: …" (Fixed, "Every integer in `stayfixed.toml`").
  - In every hook, stayfixed runs `git` only from fixed absolute paths and hands it a fixed
    `PATH`, so a `git`, or a program git runs by name such as `git-lfs`, found only elsewhere is
    not found there, where 0.2.0 ran what the inherited `PATH` named; at a terminal and in
    `stayfixed gate` in CI, the `git` on `PATH` still runs (Fixed, "When the hook wrapper launches
    it, as it does for every hook, stayfixed now runs `git` only from fixed absolute paths").
  - Where `HOME` is not the database's home, a hook's `git` reads its global configuration, your
    `safe.directory` and excludes among it, under the database's home, where 0.2.0 read it under
    `HOME` (Fixed, "When the hook wrapper launches it, as it does for every hook, stayfixed now
    runs `git` only from fixed absolute paths").
