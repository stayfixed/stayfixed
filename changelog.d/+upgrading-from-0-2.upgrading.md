From 0.2.0, what a script, a CI step or a habit may rely on that is gone, has moved or now ends
differently. Each has its own entry in these notes, with the detail:

  - If you upgrade in place, from a local marketplace or `--plugin-dir`, restart every session
    that was running: such a session can still hold 0.2.0's list of hook commands, and four of
    them, its `preset-rules` and `index` session-start bundles, exit `2` under this release
    (Changed, "Two session-start bundles are gone").
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
    `memory fit --json` no longer lists either bundle (Changed, "Two session-start bundles are
    gone").
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
  - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, for a stayfixed entry
    in `.claude/settings.local.json` that is no longer exactly what your overlay grants: one you
    edited by hand in any field, a `timeout` say, or one whose grant in the overlay has gained or
    changed a field since your last `stayfixed attach`. 0.2.0 compared only its marker and its
    command. Run
    `stayfixed attach --store …` again, which rewrites the entry as granted (Fixed, "`stayfixed
    doctor`'s `hook-entries` row now accounts for a stayfixed hook entry only where your overlay
    grants it").
  - `stayfixed test hygiene --json` moves its counts under `profiles`, by profile name (Changed,
    "The note after a failing test run now comes from the profile"), and on a tree past the
    stale-bytecode walk's new bound it exits `2`, saying the Python profile could not tell, where
    it named a count (Fixed, "The Python profile's check for stale bytecode now stops").
  - `stayfixed setup` meeting a machine configuration file it may not read exits `1`, where it
    exited `2` (Fixed, "`stayfixed setup` meeting a machine configuration file it is not allowed
    to read").
  - A hook's Python no longer reads `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE` or any other
    `PYTHON*` variable (Fixed, "The hook wrapper now starts Python in isolated mode").
  - Where `HOME` is not the home the password database records for your user, as in some
    containers and home-manager setups, every command, `stayfixed setup` and `stayfixed memory
    trust` included, now reads and writes `~/.config/stayfixed/config.toml` and `trust.json` under
    the database's home, and a `~` in `[overlay] root` means that home. A hook gives no sign of
    the move: approved notes stop being injected and `[personal]` falls back to the preset. Move
    the two files you keep under `HOME`'s `.config/stayfixed` there **before** running `setup` or
    `memory trust`, or merge them afterwards; `stayfixed doctor`'s `ignored-env` row names the
    directory (Fixed, "stayfixed no longer takes your home directory from `HOME`").
  - In that case, too, a hook makes no harness memory link. For an overlay store, `stayfixed
    attach` from a terminal makes it under `HOME`; for an in-repo or local-only store, only a
    session started with `HOME` set to the database's home gets one. A command run without a
    terminal, by an agent say, puts the link under the database's home and looks for it there:
    `stayfixed attach` run by an agent makes it there, and `stayfixed doctor`'s `attached` row run
    by an agent checks that path (Fixed, "stayfixed no longer takes your home directory from
    `HOME`").
  - A user the password database lists no home for reads no machine configuration and no trust
    record unless `--machine` names one: `stayfixed setup` and `stayfixed memory trust` fail
    (exit `1`) asking for `--machine`, and hooks make no harness memory link. A database home that
    cannot be written fails the same two commands naming the directory (Fixed, "stayfixed no
    longer takes your home directory from `HOME`").
  - `stayfixed overlay upgrade` and `overlay init` remove the overlay template's copy of the
    `attach` skill and `common/rules/README.md`, keeping and naming a copy you edited (Changed,
    "`stayfixed overlay upgrade` and `overlay init` remove two files"), and `overlay upgrade`'s
    report, and its `unchanged` count, leave out a retired file that is gone, where 0.2.0 listed
    a deleted `common/memory/README.md` as unchanged (Fixed, "`stayfixed overlay upgrade` no
    longer lists a file a release no longer ships").
  - The background guard refuses a backgrounded command that begins with `uv run <options>
    sleep`, such as `uv run --no-project sleep 30`, which 0.2.0 allowed, and `stayfixed guard
    bg-cleanup` can exit `1` where 0.2.0 exited `0`, and the reverse, for a backgrounded chain
    whose `; echo` or the command before it runs through `uv run <options>` (Fixed, "The
    background guard now reads a command started through `uv run`"). It still reads no other
    wrapper: a backgrounded `nohup sleep`, `timeout … sleep`, `uvx sleep` or `bash -c "sleep …"`
    passes, as in 0.2.0.
  - `stayfixed plan check`, the `plan` gate and `stayfixed memory refs` report a dead reference for
    a missing backticked path whatever its extension (`src/lib.rs`, `secrets/.env`), and for one
    followed by a column or a nested symbol path, which 0.2.0 did not check (Fixed,
    "`stayfixed plan check`, the `plan` gate and `stayfixed memory refs` now check a backticked
    path in any language").
  - `stayfixed bugs check --base` and the `bugs` gate read the base's ledger where the base's
    `stayfixed.toml` kept it, so a change that moves the ledger by `[paths]` or changes
    `[ledger] id_prefix` answers for every base entry it does not carry along. A base whose
    `stayfixed.toml` does not load fails the check (exit 1); one whose load meets a refusal, or
    whose `id_prefix` the ledger refuses, is refused (exit 2); and `bugs check --base` refuses
    (exit 2) a project root whose path inside the repository runs through a symlink, as
    `stayfixed gate` does. Each of these passed in 0.2.0 (Fixed, "`stayfixed bugs check --base`,
    and the `bugs` gate under `stayfixed gate`, now read").
  - A `[ledger] evidence_boundary_required_for` value that is not `high`, `medium` or `low`,
    which 0.2.0 loaded and enforced nothing for, is refused (exit 2) by `stayfixed bugs`, `plan
    check`, `memory refs`, `init` and `upgrade`: correct the value (Fixed,
    "`[ledger] evidence_boundary_required_for` is now checked").
  - In overlay mode, `stayfixed memory index` and `memory fit` warn, and their `--json` reports
    `"trusted": false`, for every store until `stayfixed memory trust --in-repo-memory` has run,
    where 0.2.0 reported `true` for a store with no committed `MEMORY.md` (Fixed, "`stayfixed
    memory index` (with or without `--check`) and `stayfixed memory fit` now warn").
  - On Python 3.14, a settings file, ledger, manifest or trust record nested deeper than 10,000
    levels is refused as nested deeper than the reader follows; `stayfixed doctor` and an
    `attach` with nothing to write read one in 0.2.0. For `doctor` that makes the `hook-entries`
    row red, so the report exits `1` where 0.2.0 exited `0` (Fixed, "On Python 3.14, a JSON file
    nested deeper than").
  - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, for a marked entry
    nothing vouches for in a settings file that opens with a byte-order mark or holds a malformed
    value beside its valid hooks, where it warned and exited `0`, and for a marked command inside
    such a value or in an entry object written where a group goes, where it warned or read "all
    accounted for" (Fixed, "`stayfixed doctor`'s `hook-entries` row now judges the hook entries in
    a settings file that").
  - `stayfixed attach --check` ends with the real run's code and line wherever the run fails or
    refuses before its first write, where 0.2.0 reported a clean diff and exited `0`: `2` for a
    `.claude/settings.local.json` the run refuses, such as one whose `permissions` is `null`, a
    `~/.claude` that is a symlink, a `trust.json` that does not parse or a doubled
    `stayfixed:ignore` region, and `1` or `2` for a `.stayfixed/local/attach.json` the run cannot
    take, such as one that is not valid JSON, and `1` for an overlay Codex rule that is not UTF-8.
    A CI step that ran it goes red (Fixed, "`stayfixed attach --check` now refuses, with exit
    `2`").
  - Your overlay's `permissions.json` with `"permissions": null` or `"allow": null`, or its
    `hooks.json` with an entry group whose `hooks` is `null`, which 0.2.0 read as granting nothing,
    is refused (exit `2`) by `stayfixed attach` and `attach --check`: remove the key, or give it
    `{}` or `[]`. Such a `hooks.json` also leaves `stayfixed doctor`'s `hook-entries` row a
    warning that the overlay could not be asked, where 0.2.0 judged the entries against the rest of
    the file (Fixed, "`stayfixed attach --check` now refuses, with exit `2`").
  - `stayfixed attach` and `attach --check` refuse (exit `2`) an overlay whose root or whose
    `projects/` is a file, where 0.2.0 failed (exit `1`) on the operating system's error for a file
    inside it (Fixed, "`stayfixed attach` and `attach --check` now refuse (exit `2`) an overlay
    whose root").
  - `stayfixed attach`, `attach --check` and `detach` refuse (exit `2`) a
    `.claude/settings.local.json` whose indented write-back would pass 64 MiB, a short file nested
    thousands of levels deep, which 0.2.0 wrote back; `attach` and `--check` refuse it even when
    the run would not rewrite it. `stayfixed setup` fails (exit `1`) on such a
    `~/.claude/settings.json`, which 0.2.0's `setup` wrote back, and on the 72 MB file 0.2.0's
    `setup` left there from a 12 KB one: cut that file down by hand before running `setup` (Changed,
    "`stayfixed attach`, `attach --check` and `stayfixed detach` now refuse, before anything is
    written, a `.claude/settings.local.json`").
  - A file a repository commits that stayfixed reads, and your overlay's record of a project, is
    read only up to 64 MiB, and one longer, which 0.2.0 read whole, is one stayfixed cannot read;
    the machine configuration, `trust.json`, `~/.claude/settings.json` and the overlay's Codex rule
    files are still read whole. `stayfixed attach`, `attach --check` and `detach` fail (exit `1`)
    on such a `.claude/settings.local.json` and on such a `.stayfixed/local/attach.json`, and
    `detach` on such a `.gitignore` when the region in it is the one `attach` wrote. A settings
    file 0.2.0's own `attach` wrote back past that size has to be cut down by hand before
    `detach` can run. A `stayfixed.toml` past the cap fails (exit `1`) every command that loads
    it. A memory note past the cap makes `stayfixed memory index --check` exit `1` naming it as a
    file that cannot be read as a note, and `memory refs` exit `1` counting it among the notes it
    could not parse (its path is in `--json`'s `unreadable`); a bug-ledger entry past it makes
    `stayfixed bugs check` exit `1` with `unreadable-entry`, where 0.2.0 read each whole and exited
    `0` (Fixed, "Every file a repository commits that stayfixed reads is now read only up to 64
    MiB").
  - Many refusals and failures say why a file could not be read, written or removed in words, and
    name it relative to the project or the overlay, where they quoted an error class or the error's
    text beside an absolute path: `(Permission denied)` for `(PermissionError)` in `stayfixed
    doctor`'s `diagnostics` row and in the `stayfixed.toml`, machine-file and project-record
    messages, `AGENTS.md cannot be read: not a regular file` in `init`, `upgrade` and `overlay
    upgrade`. A script that matched the old text has to match the new (Fixed, "Every
    file a repository commits that stayfixed reads", in its last list).
  - A `.stayfixed/manifest.json` whose `format` is `true`, `0` or a negative integer, which 0.2.0
    read as the format it writes and went on, is refused as damaged (exit `2`) by `upgrade` and
    `uninstall`. `detach` still finishes (exit `0`), and leaves the `stayfixed:ignore` region in
    `.gitignore` in place, as for any manifest it cannot read (`ignore_region_removed: false`),
    where 0.2.0 took the region out when such a manifest did not record it, and the file with it
    when the region was all it held. Every other `format` that is not a positive integer is
    refused as damaged too, where 0.2.0 refused it as "written by a newer stayfixed" (Fixed, "A
    `.stayfixed/manifest.json` whose `format` is not a positive integer").
  - `stayfixed bugs renumber` whose own write fails, and `stayfixed bugs new` and `bugs index`
    whose index write fails, now exit `1`, naming the file and what to run, where each ended in
    `internal error` with exit `2` (Fixed, "`stayfixed bugs renumber OLD NEW` killed part-way"
    and "`stayfixed bugs new` and `stayfixed bugs index` no longer end in `internal error`").
  - `stayfixed setup --git-hooks --uninstall` prints what it found, `there is no stayfixed hook
    at <hook>; nothing was removed` or `left <hook> as it was: …`, where 0.2.0 printed `removed …`
    for every case, and `--json` gains `found`. Over a hook it cannot read as a regular file (one
    at mode 000, stayfixed's own or anyone's, a FIFO, a directory) `--uninstall` refuses (exit `2`)
    where 0.2.0 exited `0` or hung, and `setup --git-hooks` refuses (exit `2`) a hook at mode 000,
    stayfixed's own or anyone's, which 0.2.0 renamed to `prepare-commit-msg.local`, chained and
    later restored, and a FIFO, on which 0.2.0 hung: make such a hook readable, or move it aside,
    first. A foreign hook past the 64 MiB read cap is still chained and left alone, as in 0.2.0
    (Fixed, "`stayfixed setup --git-hooks --uninstall` now says what it found").
  - `stayfixed attach` run from a linked worktree no longer records `autoMemoryDirectory` in that
    worktree's `.claude/settings.local.json` after making the harness memory link, and run again it
    takes back the key 0.2.0 recorded there, deleting the file when the key was all it held; where
    a real directory does stand in the way, the recorded value is the owning checkout's store, not
    the worktree's own copy of the link tree (Fixed, "`stayfixed attach` run from a linked
    worktree").
  - `stayfixed doctor`'s `hook-entries` row warns, where 0.2.0 could read "all accounted for", for a
    skill, command or agent file whose frontmatter declares hooks, at any depth and in a nested
    `.claude/skills`, for a file there it cannot read, for a link there that leads out of the
    checkout, and, outside a git work tree, for a checkout too large to walk; the report's exit
    code is unchanged. To find nested skills it asks git once more (`git ls-files`, and again
    through the submodules where a `.gitmodules` is present), each query bounded at 30 seconds
    (Fixed, "`stayfixed doctor`'s `hook-entries` row now warns about each skill").
  - `stayfixed assess`'s `foreign-hooks` advice names a committed settings file whose hook entries
    all claim stayfixed's marker, which 0.2.0 passed over as stayfixed's own (Fixed, "`stayfixed
    assess`'s `foreign-hooks` item now lists").
  - A `stayfixed.toml` holding an integer of 2,147,483,648 or more fails to load (exit `1`),
    where 0.2.0 loaded it, and one whose `[stayfixed] preset` is not a string fails with
    "stayfixed.preset must be a string; available: …", where 0.2.0 failed on `preset = 5` or
    `true` as a name it does not ship and ended in an internal error on a hexadecimal one past
    4,300 decimal digits (Fixed, "Every integer in `stayfixed.toml`").
