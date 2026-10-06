From 0.2.0, what a script, a CI step or a habit may rely on that is gone, has moved or now ends
differently. Each has its own entry in these notes, with the detail:

  - `stayfixed adopt begin` is gone: `stayfixed adopt promote` moves a project out of
    `initialised` itself, and a project 0.2.0 left in `adopting` keeps working (Changed,
    "`stayfixed adopt begin` is gone").
  - `stayfixed test audit-entrypoints` is gone, and no gate ran it (Changed, "`stayfixed test
    audit-entrypoints` is gone").
  - The `stayfixed release` group (`check`, `notes`, `hashes`) is gone from the installed CLI; it
    only ever checked stayfixed's own release (Changed, "The `stayfixed release` commands are
    gone").
  - `stayfixed docs check` has lost `--memory-graph`, whose link graph `stayfixed memory refs` now
    reports, and `--store` with it (Changed, "`stayfixed docs check --memory-graph` is gone").
  - `stayfixed memory session-context --bundle preset-rules` and `--bundle index` exit `2`, and
    `memory fit --json` no longer lists either bundle (Changed, the entry that begins "The README
    now says, per agent", in its paragraph "Two session-start bundles are gone").
  - `stayfixed doctor` reports the same sixteen checks in a new order, the installation's own
    eleven first: match on each check's name, not its position (Changed, "`stayfixed doctor` lists
    the same sixteen checks in a new order").
  - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, where 0.2.0 exited
    `0`: among other cases, for your own checkout on a new machine before
    `stayfixed setup --overlay` has run, which 0.2.0 reported as a warning, and for the
    per-project entries of a checkout whose `origin` is no longer the remote its overlay record
    binds, which 0.2.0 often read as accounted for (Fixed, the entries that begin
    "`stayfixed doctor`'s `hook-entries` row is red for a hook entry" and "`stayfixed doctor`'s
    `hook-entries` row no longer lets a repository borrow").
  - `stayfixed test hygiene --json` moves its counts under `profiles`, by profile name (Changed,
    "The note after a failing test run now comes from the profile"), and on a tree past the
    stale-bytecode walk's new bound it exits `2`, saying the Python profile could not tell, where
    it named a count (Fixed, "The Python profile's check for stale bytecode now stops").
  - `stayfixed setup` meeting a machine configuration file it may not read exits `1`, where it
    exited `2` (Fixed, "`stayfixed setup` meeting a machine configuration file it is not allowed
    to read").
  - A hook's Python no longer reads `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE` or any other
    `PYTHON*` variable (Fixed, "The hook wrapper now starts Python in isolated mode").
  - `stayfixed overlay upgrade` and `overlay init` remove the overlay template's copy of the
    `attach` skill and `common/rules/README.md`, keeping and naming a copy you edited (Changed,
    "`stayfixed overlay upgrade` and `overlay init` remove two files").
  - The background guard refuses a backgrounded command that begins with `uv run <options>
    sleep`, such as `uv run --no-project sleep 30`, which 0.2.0 allowed, and `stayfixed guard
    bg-cleanup` can exit `1` where 0.2.0 exited `0`, and the reverse, for a backgrounded chain
    whose `; echo` or the command before it runs through `uv run <options>` (Fixed, "The
    background guard now reads a command started through `uv run`").
  - `stayfixed plan check`, the `plan` gate and `stayfixed memory refs` report a dead reference for
    a missing backticked path whatever its extension (`src/lib.rs`, `secrets/.env`), and for one
    followed by a column or a nested symbol path, which 0.2.0 did not check (Fixed,
    "`stayfixed plan check`, the `plan` gate and `stayfixed memory refs` now check a backticked
    path in any language").
