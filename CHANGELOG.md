# Changelog

<!-- towncrier release notes start -->

## 0.3.1 (2026-10-16)

### Fixed

- A repository bound to the overlay over ssh now binds a clone of it made over https, and the other
  way round: `git@host:owner/repo`, `ssh://git@host/owner/repo` and `https://host/owner/repo`, each
  with or without `.git`, are one remote when the host and the path agree (the host in any case, and
  on github.com the path too). A second machine or a teammate who cloned over https used to be
  refused as a different remote and told to pass `--trust-remote`, which then rewrote the record to
  that form. `attach`, `attach --check`, `doctor`, the memory commands and the line stayfixed prints
  when a session starts all apply the rule, and the record keeps the form it was written in. A
  different owner, repository, host, port or user is still a different remote, and the refusal now
  names the three spellings that bind and says any other is compared exactly.


## 0.3.0 (2026-10-14)

### Upgrading

- Each item below is something a script, a CI step or a habit could rely on in 0.2.0 that is gone,
  has moved or now ends differently, with a pointer to its entry in these notes, which has the
  detail:

    - Restart every session that was running when you upgraded in place, from a local marketplace
      or `--plugin-dir`: it can still hold 0.2.0's hook commands, and four of them, its
      `preset-rules` and `index` session-start bundles, exit `2` under this release (Changed, "Two
      session-start bundles are gone").
    - `stayfixed memory session-context --bundle preset-rules` and `--bundle index` exit `2`, and
      `memory fit --json` has lost both bundles' keys (Changed, "Two session-start bundles are
      gone").
    - `stayfixed adopt begin` is gone; `stayfixed adopt promote` moves a project out of
      `initialised` itself (Changed, "`stayfixed adopt begin` is gone").
    - `stayfixed test audit-entrypoints` is gone (Changed, "`stayfixed test audit-entrypoints` is
      gone").
    - The `stayfixed release` commands (`check`, `notes`, `hashes`) are gone from the installed CLI
      (Changed, "The `stayfixed release` commands are gone").
    - `stayfixed docs check` no longer takes `--memory-graph` or `--store`; `stayfixed memory refs`
      reports the link graph (Changed, "`stayfixed docs check --memory-graph` is gone").
    - `stayfixed doctor` lists its checks in a new order, with one more: match a check by its name,
      not its position (Changed, "`stayfixed doctor` lists its checks in a new order").
    - `stayfixed test hygiene --json` reports its counts under `profiles`, by profile name, and the
      top-level `stale` and `roots` keys are gone (Changed, "The note after a failing test run now
      comes from the profile").
    - `stayfixed test hygiene` exits `2` on a tree past the stale-bytecode walk's new bound, where it
      named a count (Fixed, "The Python profile's check for stale bytecode").
    - `stayfixed doctor`'s `hook-entries` row is red, and the report exits `1`, where 0.2.0 read "all
      accounted for" or warned, for an entry claiming stayfixed's marker that your overlay does not
      grant, as it grants it, to this checkout: on a machine that records no overlay (your own
      checkout on a new machine before `stayfixed setup --overlay` has run among them), for a
      checkout whose `origin` is not the remote its overlay record binds, for an entry that is no
      longer exactly what your overlay grants (run `stayfixed attach --store …` again to rewrite it),
      and beside a settings file that opens with a byte-order mark or holds a malformed value beside
      its valid hooks (Fixed, "`stayfixed doctor`'s `hook-entries` row now vouches for a hook
      entry").
    - `stayfixed doctor`'s `hook-entries` row warns, where 0.2.0 could read "all accounted for",
      about a skill, command or agent file whose frontmatter declares hooks or that it cannot read;
      the report's exit code is unchanged (Fixed, "`stayfixed doctor`'s `hook-entries` row now warns
      about each skill").
    - `stayfixed doctor`'s `attached` row is red, and the report exits `1`, where 0.2.0 read ok or
      warned, for an `autoMemoryDirectory` in either settings file other than the store `attach`
      writes there, and, from the main checkout, for a link that reaches nothing; it warns where 0.2.0
      read ok for a link to a store whose approval lapsed, was never given or cannot be read, and in
      the other cases its entry lists (Fixed, "`stayfixed doctor`'s `attached` row now reads a checkout's harness memory
      link").
    - `stayfixed assess`'s `foreign-hooks` advice names a committed settings file whose hook entries
      all claim stayfixed's marker, which 0.2.0 passed over (Fixed, "`stayfixed assess`'s
      `foreign-hooks` item now reads a committed settings file").
    - A hook's Python no longer reads `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE` or any other
      `PYTHON*` variable (Fixed, "The hook wrapper, which starts every hook, no longer lets a
      variable set for a hook choose what runs").
    - In every hook, stayfixed runs `git` only from fixed absolute paths and hands it a fixed
      `PATH`, so a `git`, or a program git runs by name such as `git-lfs`, found only elsewhere is
      not found there, where 0.2.0 ran what the inherited `PATH` named; at a terminal and in
      `stayfixed gate` in CI, the `git` on `PATH` still runs. Where `HOME` is not the password
      database's home, a hook's `git` reads its global configuration, your `safe.directory` and
      excludes among it, under the database's home (Fixed, "The hook wrapper, which starts every
      hook, no longer lets a variable set for a hook choose what runs").
    - Where `HOME` is not the home the password database records for your user, an empty one
      included, every command, at a terminal too, reads and writes `~/.config/stayfixed/config.toml`
      and `trust.json` under the database's home: move the two files you kept under `HOME` there
      before running `stayfixed setup` or `stayfixed memory trust`. No hook makes the harness memory
      link there, and `stayfixed attach` run without a terminal, by an agent say, makes none either
      and says so, where 0.2.0 made it under `HOME` (Fixed, "stayfixed no longer takes your home
      directory from `HOME`").
    - At a terminal where `HOME` is set and empty, `stayfixed attach` and `stayfixed detach` refuse
      (exit `2`) and `stayfixed setup` fails (exit `1`) before writing anything; a user the password
      database lists no home for reads no machine configuration and no trust record unless
      `--machine` names one, and `stayfixed setup` and `stayfixed memory trust` fail (exit `1`)
      asking for it (Fixed, "stayfixed no longer takes your home directory from `HOME`").
    - `stayfixed setup` meeting a machine configuration file it may not read exits `1`, where it
      exited `2` (Fixed, "`stayfixed setup` now finds, before it writes anything, a path it cannot
      use").
    - `stayfixed setup --overlay` refuses (exit `2`) layouts 0.2.0 recorded: an overlay inside a
      checkout of another repository, wherever `--root` is, a checkout of its own nested in one
      included, and a linked worktree of the overlay's own repository nested in another checkout of
      it; and any overlay inside a checkout where the `git` asked gives no usable answer, as git 2.30
      and older and a wrapper printing a banner do (Fixed, "`stayfixed setup --overlay` now judges
      where an overlay may live").
    - `stayfixed setup --git-hooks --uninstall` says what it found, and `--json` gains `found`, where
      0.2.0 printed `removed …` in every case; both it and `stayfixed setup --git-hooks` refuse
      (exit `2`) a hook at mode 000, stayfixed's own or anyone's, which 0.2.0 chained, restored or
      called removed (Fixed, "`stayfixed setup --git-hooks` and its `--uninstall` now say what they
      found").
    - `stayfixed overlay upgrade` and `overlay init` remove the template's copy of the `attach` skill
      and `common/rules/README.md`, keeping and naming a copy you edited (Changed, "`stayfixed
      overlay upgrade` and `overlay init` remove two files").
    - `stayfixed overlay upgrade`'s report and its `unchanged` count leave out a retired file that is
      gone, where 0.2.0 counted a missing `common/memory/README.md` (Fixed, "`stayfixed upgrade`,
      `stayfixed overlay upgrade` and `stayfixed overlay init` no longer keep the record").
    - The background guard refuses a backgrounded `uv run <options> sleep`, such as
      `uv run --no-project sleep 30`, which 0.2.0 allowed, and `stayfixed guard bg-cleanup` can exit
      `1` where 0.2.0 exited `0`, and the reverse, for a backgrounded chain whose `; echo`, or the
      command before it, runs through `uv run <options>` (Fixed, "The background guard now reads a
      command started through `uv run`").
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
    - `stayfixed bugs renumber` whose own write fails, and `stayfixed bugs new` and `bugs index`
      whose index write fails, exit `1`, where each ended in `internal error` with exit `2` (Fixed,
      "`stayfixed bugs renumber OLD NEW` killed part-way" and "`stayfixed bugs new` and `stayfixed
      bugs index` no longer end in `internal error`").
    - In overlay mode, `stayfixed memory index` and `memory fit` warn, and their `--json` reports
      `"trusted": false`, for every store until `stayfixed memory trust --in-repo-memory` has run
      (Fixed, "`stayfixed memory index` (with or without `--check`) and `stayfixed memory fit` now
      warn").
    - `stayfixed attach --check` exits as the run does, `2` or `1`, wherever the run refuses or fails
      before its first write, past the gates `--check` reports instead, such as on a
      `.claude/settings.local.json` whose `permissions` is `null`, where 0.2.0 reported a clean diff
      and exited `0`: a CI step that ran it goes red
      (Fixed, "`stayfixed attach --check` now ends as the run would").
    - Your overlay's `permissions.json` or `hooks.json` holding `null` where rules or hook entries
      go, which 0.2.0 read as granting nothing, is refused (exit `2`) by `stayfixed attach` and
      `attach --check`: remove the key, or give it `{}` or `[]` (Fixed, "`stayfixed attach --check`
      now ends as the run would").
    - `stayfixed attach` and `attach --check` refuse (exit `2`) an overlay whose root or whose
      `projects/` is a file, where they failed (exit `1`), and fail (exit `1`) on an overlay `codex/`
      directory that cannot be listed, where each ended in `internal error` with exit `2` (Fixed,
      "`stayfixed attach` and `attach --check` now find these before anything is written").
    - `stayfixed attach` run from a linked worktree no longer records `autoMemoryDirectory` in that
      worktree's `.claude/settings.local.json`, and run again takes back the key 0.2.0 recorded
      there (Fixed, "`stayfixed attach` run from a linked worktree").
    - `stayfixed attach`, `attach --check` and `detach` refuse (exit `2`), and `stayfixed setup`
      fails (exit `1`) on, a settings file whose indented write-back would pass 64 MiB; cut down by
      hand a `~/.claude/settings.json` that 0.2.0's `setup` wrote back past it (Changed, "`stayfixed
      attach`, `attach --check` and `stayfixed detach` now refuse (exit `2`), before anything is
      written").
    - A file a repository commits that stayfixed reads, and your overlay's record of a project, is
      read only up to 64 MiB, and only when it is a regular file or a link to one; anything else,
      which 0.2.0 read whole or waited on, is a file stayfixed cannot read (Fixed, "Every file a
      repository commits that stayfixed reads").
    - On Python 3.14, a settings file, ledger, manifest or trust record nested deeper than 10,000
      levels is refused, and turns `stayfixed doctor`'s `hook-entries` row red (Fixed, "A file
      holding a number longer than Python converts").
    - Many refusals and failures over a file that could not be read, written or removed give the
      reason in words, in parentheses, and name the file relative to the project or the overlay,
      where they quoted an error class or the error's text beside an absolute path: a script that
      matched the old text has to match the new (Fixed, "A message about a file stayfixed cannot
      read, write or remove").
    - A `.stayfixed/manifest.json` whose `format` is not a positive integer is refused as damaged
      (exit `2`) by `upgrade` and `uninstall`, where 0.2.0 read `true`, `0` or a negative integer as
      its own format, and `stayfixed detach` beside one leaves the `stayfixed:ignore` region in
      `.gitignore` in place (`ignore_region_removed: false`), where 0.2.0 took it out when the
      manifest did not record it (Fixed, "A `.stayfixed/manifest.json` whose `format` is not a
      positive integer").
    - A `stayfixed.toml` holding an integer of 2,147,483,648 or more fails to load (exit `1`), where
      0.2.0 loaded it, and one whose `[stayfixed] preset` is not a string fails with
      "stayfixed.preset must be a string; available: …" (Fixed, "Every integer in
      `stayfixed.toml`").
    - `stayfixed commit check`, and with it the CI commit gate, fails (exit `1`) on a commit message
      carrying `Assisted-by: ChatGPT` or `Generated-by: Cursor`, which 0.2.0 passed, and
      `stayfixed commit strip` and the `prepare-commit-msg` hook strip those lines (Fixed,
      "`stayfixed commit check` now refuses a `-by:` trailer whose name is `ChatGPT` or `Cursor`").
- The Claude Code plugin now comes from `stayfixed/stayfixed-plugin` (Changed, "The Claude Code
  plugin is now installed from `stayfixed/stayfixed-plugin`"). How an existing install moves to this
  release depends on how its marketplace was added:

    - Added without a tag (`/plugin marketplace add stayfixed/stayfixed`), it follows the
      repository's default branch and moves with an update:
      `claude plugin marketplace update stayfixed-marketplace`, then
      `claude plugin update stayfixed@stayfixed-marketplace`.
    - Added at a release tag (`stayfixed/stayfixed@v0.2.0`, say), adding it again at this
      release's tag over the marketplace you have is refused. Remove the marketplace, add it at
      this release's tag, `stayfixed/stayfixed@v0.3.0` as the README's Install section names it,
      and install the plugin again: `claude plugin marketplace remove stayfixed-marketplace`, then
      `claude plugin marketplace add stayfixed/stayfixed@v0.3.0`, then
      `claude plugin install stayfixed@stayfixed-marketplace`. Removing the marketplace uninstalls
      the plugin and deletes the options you saved for it, so set them again after the install.

### Fixed

- A `.stayfixed/manifest.json` whose `format` is not a positive integer (`null`, a string, a number
  with a fraction, `true`, `0` or a negative number) is now refused as damaged:
  `.stayfixed/manifest.json: 'format' is not a positive integer`, exit `2`. `true`, `0` and every
  negative integer were read as the format this stayfixed writes, and the command went on; the other
  values were refused as written by a newer stayfixed, with advice to upgrade the plugin, which could
  not help. A `format` above the one this stayfixed writes is still refused with that advice.
  `stayfixed detach` meets such a manifest as one it cannot read: it finishes (exit `0`) and leaves
  the `stayfixed:ignore` region in `.gitignore` where it is (`ignore_region_removed: false`). It read
  `true`, `0` or a negative `format` as valid, and took the region out wherever the manifest did not
  record it, with the file when the region was all it held.
- A file holding a number longer than Python converts to an integer (4,300 digits by default), or
  JSON nested deeper than Python's parser follows, is now a file that does not parse, met as each
  command already meets one, where it ended many commands in an internal error. The refusal says so
  in its own words ("holds a number longer than this reader converts", "is nested deeper than this
  reader follows"), never with Python's advice to raise an interpreter limit:

  - TOML stayfixed reads that somebody else wrote: `stayfixed.toml` (on either side of
    `stayfixed gate`), `docs/trail.toml`, a profile's `pyproject.toml`, the machine configuration
    file and the overlay's record of a binding are "not valid TOML (holds a number longer than the
    parser converts)". One such line ended `stayfixed doctor`, `gate`, `assess` and `init` in an
    internal error, made a hook say "internal error" where it says "does not load", and turned
    `doctor`'s `attached`, `bundles` and `store-debris` rows red, "this check could not run".
  - `.stayfixed/manifest.json`, refused by `upgrade`, `uninstall` and every other command that reads
    it; one that is not valid JSON is now "not valid JSON" rather than "unreadable".
  - `trust.json`, refused as a trust record that cannot be read, which nothing overwrites, where
    `stayfixed memory trust` ended in an internal error; one that is not valid JSON is worded "is not
    valid JSON: <where the parser stopped>".
  - `~/.claude/settings.json`: `stayfixed setup` fails (exit `1`) naming it, and leaves it as it was.
  - Your overlay's `.claude-plugin/plugin.json` or `marketplace.json`: `stayfixed setup --overlay
    <path>` and `overlay upgrade` refuse the overlay, saying the manifest cannot be read as JSON, and
    `overlay init` meets it as one that is not JSON. The session-start hook reads such a
    `plugin.json` as declaring no `stayfixed.requires`, so it no longer silences the overlay's lines
    at the start of a session, such as the one saying the repository is not attached.
  - A release's `hooks/hashes.json`, and what `gh repo view` answers to `overlay create` and
    `overlay publish-template`, which now says that answer "is not valid JSON" where it said `gh repo
    view` "did not answer with JSON".
  - The input to `stayfixed guard bg-cleanup`, whose refusal of input that is not JSON at all now
    puts "stdin is not valid JSON:" before the parser's message.
  - `.stayfixed/local/attach.json`, which is also a ledger that cannot be read, rather than an
    internal error, when its `store` holds a NUL or a character no path can spell (a lone surrogate),
    when its `store` or an entry's recorded event is not text (`{"store": 5}` named the store `5`),
    or when a list field such as `allow` or `rules` holds something else. `stayfixed doctor`'s
    `attached` and `hook-entries` rows name it as a file that cannot be read, rather than reading
    red, "this check could not run", and `attach` and `detach` say it is not a ledger.
  - A settings file: such a number no longer stops `hook-entries`, which reads it as its text and
    judges the entries beside it; nested that deeply, the file turns `hook-entries` red naming it,
    since nothing can check its entries and Claude Code may still read it. `stayfixed attach` refuses
    to merge into either. A line of either kind in the hook sink's log is no longer counted by the
    `diagnostics` row as a recorded failure.

  The depth bound is 10,000 levels on every Python. Python 3.14's parser follows a file to about
  57,800, so there a settings file, the attach ledger, a manifest or the trust record nested deeper
  than 10,000 was read by `detach`, `init`, `upgrade` and `attach`, which then ended in an internal
  error writing it back, and by `stayfixed doctor` as one it could check. On Python 3.12, whose
  encoder stops near 994 levels when it indents, a settings file, manifest or
  `~/.claude/settings.json` deeper than that is now refused in the same words when `attach`,
  `detach`, `init`, `upgrade`, `overlay init` or `setup` would write it back, where it ended in an
  internal error.
- A message about a file stayfixed cannot read, write or remove now gives the reason in words, in
  parentheses after what could not be done, as in `cannot be read (Permission denied)`,
  `cannot be written (…)` or `cannot be removed (…)`, and names the file relative to the project or
  the overlay. Many named an error class (`IsADirectoryError`, `PermissionError`), quoted the error's
  raw text after a colon, or printed the file's absolute path on this machine. A script that matched
  the old text has to match the new:

  - `stayfixed.toml` and the overlay's project record say `(not a regular file)`,
    `(Permission denied)` or `(larger than this reader reads)`, and the machine configuration file
    `(Permission denied)`; so do `stayfixed doctor`'s `ci-ref` and `diagnostics` rows;
  - `stayfixed init`, `upgrade` and `overlay upgrade` name a file they cannot read relative to the
    tree they write, as in `AGENTS.md cannot be read (not a regular file)` or `AGENTS.md is not
    UTF-8 text`, where the refusal gave its absolute path twice;
  - `stayfixed uninstall` says why `.stayfixed/manifest.json`, `.stayfixed/assessment.json` or
    `.stayfixed/local/artifacts.json` could not be removed, and every command that rewrites
    `stayfixed.toml` (`upgrade`, `init`, `adopt promote`) why it could not be written;
  - `.stayfixed/manifest.json` that cannot be read says `cannot be read (…)`, and one that is not
    UTF-8 `is not UTF-8 text`, where both said `is unreadable:` and the error's text;
  - a trust record that cannot be read is named once, with the reason in words;
  - `stayfixed setup` says why it cannot read `~/.claude/settings.json`, as in `cannot be read (Is a
    directory)`;
  - `stayfixed attach` and `detach` name `.gitignore`, `.stayfixed/manifest.json` and the other
    files they read as the project does, and `stayfixed docs trail` and its `--check` name
    `docs/trail.toml` by its path in the project;
  - a refusal over a symlinked directory names it by its place under the directory being checked
    (`passes through a symlink at 'skills'`), in every command that reports one.
- A symbolic link that loops, leads into a directory nobody may search, or names something longer
  than the filesystem allows is now answered the same way on every supported Python. Python 3.11 to
  3.13 ended several commands in an internal error over one, at times printing the path on this
  machine:

  - `stayfixed setup` given a loop at `~/.claude`, `--home`, `--root`, `--settings` or `--overlay`,
    and `setup --git-hooks` given one at `--root`, refuse (exit `2`) naming the path and saying it
    loops, before anything is written. 3.11 and 3.12 ended in `internal error: RuntimeError`; 3.13
    refused most of them in other words, and recorded an overlay past a looping `--root`.
  - `stayfixed memory index` and `stayfixed detach` meeting a loop at or under `paths.memory`, which a
    clone can commit, no longer end in an internal error on 3.11 and 3.12, and 3.13 no longer reads
    one as the path it names. A `paths.memory` that is itself a loop, in the checkout `detach` runs in
    or in the main checkout, is refused before anything is withdrawn, saying whose it is; a
    `MEMORY.md` that loops is refused like any index link that reaches no place in this project's
    share of the overlay; a group's link that loops is left standing by `detach`, as it leaves any
    link that points elsewhere.
  - A ledger `store` or a note's backticked path that runs through a loop no longer ends
    `stayfixed doctor` in a red row, "this check could not run", or `stayfixed memory refs` in an
    internal error, on 3.11 and 3.12: the store is not this project's, and the path is reported as
    one that does not resolve.
  - A committed `.stayfixed` that links into a directory its user cannot search, or to a name longer
    than the filesystem allows, is refused (exit `2`) naming the link by `stayfixed init`, `upgrade`
    and `uninstall`, where 3.11 to 3.13 ended in an internal error and 3.14 said the footprint's
    manifest was not there. So is a `.codex` that links into a directory its user cannot search, by
    `stayfixed attach`, and by `attach --check`, which reported nothing wrong.
  - A ledger committed as a link to a name longer than the filesystem allows no longer turns
    `doctor`'s `attached` row, on 3.11 to 3.13, into a warning that it could not read something it
    needed, which hid the row's red for a real directory at the harness memory path; with nothing at
    that path the row names the ledger as one that cannot be read.
- Every file a repository commits that stayfixed reads is now read only when it is a regular file,
  or a link to one, and only up to 64 MiB. Anything else is a file stayfixed cannot read, "not a
  regular file" or "larger than this reader reads", met as each command meets one: most fail (exit
  `1`), and the exceptions are named below. These were read to their end: a link to `/dev/zero` read
  until memory ran out, in CI as anywhere else, and a named pipe, or a link to `/dev/stdin` or to a
  FIFO, waited for input that never came.

  - `stayfixed.toml`, which most commands and every hook read first: a named pipe there made every
    command and every hook wait for good, and now fails at once.
  - `.gitignore`: past the cap it stops `stayfixed detach` (exit `1`) before it removes anything, as
    it already stopped `attach`; linked to a device or a pipe, `attach` refuses it (exit `2`) when it
    needs to add its region. A region `stayfixed init` recorded is left in place and the file not
    read.
  - `.stayfixed/manifest.json`, which `init`, `upgrade`, `uninstall` and `detach` read, is
    unreadable past the cap. Each file `init` and `upgrade` would write is listed, past the cap or
    with a named pipe in its place, as that artifact's refusal, and the run writes nothing (exit `1`).
  - `MEMORY.md` and memory notes: `memory index --check` reports a `MEMORY.md` past the cap as
    drifted, and `memory index` takes no entry from it. A note past the cap makes `memory index
    --check` exit `1`, naming it as a file that cannot be read as a note, and `memory refs` exit `1`,
    counting it among the notes it could not parse (`unreadable` in `--json`), where both exited `0`.
    A note or `MEMORY.md` linked to a device or a pipe is quarantined, and the store's trust digest
    moves, where `memory refs`, `inventory`, `index --check`, `trust` and `session-context` waited.
    The trust digest reads a note up to 64 MiB, so a change past that does not move it. A note removed
    or replaced while `memory refs` reads it fails the command (exit `1`) naming the note, where it
    ended in an internal error.
  - Bug-ledger entries: one past the cap or linked to a device is `stayfixed bugs check`'s
    `unreadable-entry` (exit `1`), where `bugs check` passed, or it, `bugs index`, `bugs new` and
    `gate --only bugs` waited for good. Another file the ledger's reference scan reads is named as one
    that could not be read, unless its first 8 KiB are not UTF-8 text, as a model or a database is
    not: it is skipped as a binary, as before.
  - A plan `stayfixed plan check` finds outside a git repository.
  - `.claude/settings.local.json` linked to a device or a pipe: `stayfixed attach`, `attach --check`
    and `stayfixed detach` fail (exit `1`) before anything is written or removed; so does `detach`
    over such a `.stayfixed/local/attach.json`, and `attach` refuses a ledger that is a link at all,
    as before.
  - The committed settings files `stayfixed assess` reads for its `foreign-hooks` finding: one past
    the cap is one it could not look at.
  - Your overlay's `.claude-plugin/plugin.json`, when it is a named pipe or anything else that is not
    a regular file, no longer hangs the session-start hook, `stayfixed doctor`'s `overlay-requires`
    row or `stayfixed overlay upgrade`: it declares no version floor and names no owner, and
    `stayfixed setup` refuses the overlay as before.

  The overlay's record of a project, `projects/<name>/project.toml`, is read up to 64 MiB too, and a
  longer one stops `attach` as a record that cannot be read. `CODEOWNERS`, which `assess` reads, and
  the configuration files a stack profile checks keep the size bounds they had, now held by the read
  itself, so a file that grows while it is read cannot pass them.
- Every integer in `stayfixed.toml`, such as a `[budgets]` value or `[gates] custom_timeout_seconds`,
  must now be below 2,147,483,648, and one at or past that fails to load, "must be a positive integer
  below 2,147,483,648", naming the key and never the value. TOML reads a hexadecimal, octal or binary
  integer at any length, so such a number reached `custom_timeout_seconds`' reader and ended
  `stayfixed assess` and `stayfixed gate` in an internal error. A `[stayfixed] preset` that is not a
  string now fails as "stayfixed.preset must be a string", followed by the presets this version
  ships. A hexadecimal integer whose decimal spelling would pass 4,300 digits no longer ends a
  command in an internal error: `stayfixed init` adopting a `stayfixed.toml` that holds one refuses
  it as the configuration's own error, `stayfixed assess` reads one in a profile's `pyproject.toml`
  as a value it cannot read, and `stayfixed setup` keeps one you wrote in the machine configuration
  file, writing it back in hexadecimal.
- Text a repository commits, and a commit message, are now read in time linear in their length,
  with the same findings as before. Some readers took time that grew with the square of the length
  or faster, so a commit message or a file any change can commit could stall a hook, a command or a
  CI gate:

  - `stayfixed commit check`, and `stayfixed commit strip`, which the `prepare-commit-msg` hook runs
    on every commit: a `-by:` trailer padded with 160,000 blanks took about two minutes, and a line
    that opens like a generated-with footer and goes on into prose doubled its time with each word
    that is both a name and a version, such as `A1` (24 of them took four to seven seconds);
  - `stayfixed plan check` and the `plan` gate: a plan's `- Create:`, `- Test:` and `- Delete:`
    lines, its premise markers, and the rule that a mutation's outcome is not stated as fact, which
    took over ten seconds over 16,000 claims in one paragraph;
  - the fenced code blocks in `plan check`, the `plan` gate, `stayfixed docs check`'s link check over
    the always-loaded document and `stayfixed memory refs`;
  - citations of the ledger's entry files, and the generated index's marker, in `stayfixed bugs
    check`, the `bugs` gate and `bugs index`: 160,000 citations took 36 s;
  - a note's `[[links]]` in `stayfixed memory refs`;
  - the workflow's `uses:` lines in `stayfixed doctor`'s `ci-ref` row: a 256 KiB workflow of them
    took ten seconds.

  Readers also no longer keep a record for each label, segment or word of a long value, which took
  120 MiB or more of extra memory for a value of a million: an email owner on a `CODEOWNERS` line in
  `stayfixed assess`, a commit trailer's address or model name, a ledger citation's path, the blanks
  between two wiki links, and the repository-chosen names and `[paths]` values stayfixed judges
  before it prints or writes them.
- The Python profile's check for stale bytecode, behind `stayfixed test hygiene` and the note after
  a failing pytest run, now stops after listing 500,000 directory entries under `[ledger]
  code_roots`, or after reading 20,000 `.pyc` files, and says it could not tell. It had no limit:
  over a large enough tree the note outlasted the hook's 10-second timeout, so it was never
  delivered, and the same walk ran again after every later failed run. When the walk stops early the
  note says whether stale bytecode was imported could not be told, and `stayfixed test hygiene`
  exits `2`, saying the tree cannot be judged and that narrowing `[ledger] code_roots` is the way
  out, instead of naming a count or calling the tree clean. The check now reads a `.pyc` only when it
  is a regular file: one that is a named pipe, or a link to one such as `/dev/stdin`, hung both, and
  a linked `.pyc` whose target lay outside the code roots was counted as stale. When the check fails,
  `test hygiene` refuses (exit `2`) naming the profile and the kind of error, where it ended in an
  internal error printing the error's message, on Python 3.11 a directory name of the repository's
  choosing.
- The background guard now reads a command started through `uv run` with uv's own options, as the
  note after a failing test run does: a backgrounded command that begins with `uv run <options>
  sleep`, such as `uv run --no-project sleep 30`, is refused as a backgrounded `sleep` is, where
  before it was allowed, while `uv run -m sleep` and `uv run --script sleep`, which run a module or
  a file of that name, are not. Its advice about a backgrounded chain ending in `; echo` reads the
  same way: it sees an echo uv launches past its options and no longer takes one for the command the
  echo hides, so `pytest -q; uv run --no-project echo done` now gets it (`stayfixed guard
  bg-cleanup` exits `1`) and `uv run --frozen echo hi; echo done` no longer does (exit `0`).
- The hook wrapper, which starts every hook, no longer lets a variable set for a hook choose what
  runs. Claude Code applies a repository's `.claude/settings.json` `env` block to every hook, and a
  tool that applies a file the repository commits, such as direnv, mise or a devcontainer, can set
  variables for one too:

  - Python starts in isolated mode (`-I`), both when the wrapper checks a candidate interpreter and
    when it runs stayfixed, so it reads none of its `PYTHON*` variables, loads no user site and puts
    neither the working directory nor the script's own directory on `sys.path`. A `PYTHONPATH`,
    `PYTHONHOME` or `PYTHONUSERBASE` could make it import a `sitecustomize` or `usercustomize` of the
    repository's choosing before stayfixed's first line ran. stayfixed itself still sees the whole
    environment; a variable you relied on to change how a hook's Python starts has no effect now.
  - A shell function exported through the environment no longer stands in for a command the wrapper
    runs. On macOS `/bin/sh` is bash 3.2, which defines a function from any variable named
    `BASH_FUNC_<name>%%`, so such a variable could replace `pwd`, `cd`, `command`, `printf` or
    `test` inside the wrapper and run a program of its choosing. Shell options and dynamic-loader
    variables that act on the shell before its first line, such as `SHELLOPTS` with `PS4`, are out
    of any wrapper's reach (`SECURITY.md`).
  - stayfixed started by the wrapper runs `git` only from fixed absolute paths, the first that
    exists of `/opt/homebrew/bin/git`, `/usr/local/bin/git`, `/home/linuxbrew/.linuxbrew/bin/git`,
    `/run/current-system/sw/bin/git`, `/usr/bin/git` and `/bin/git`, with a `PATH` of those
    directories followed by `/usr/bin:/bin:/usr/sbin:/sbin`. It ran the `git` the inherited `PATH`
    named, a relative entry resolved against the project, so a repository could ship a `git`, or a
    `git-lfs` your own `git` then ran as a filter, and have every hook that asks git anything run
    it. The wrapper no longer runs `dirname` or `env` through `PATH` either. In a hook, therefore:
    - a `git` found only elsewhere, such as MacPorts' `/opt/local/bin`, a per-user Nix profile or
      `~/.local/bin`, does not answer; where none of the paths holds one, git gives no answer, as
      when git is missing;
    - a program git runs by name, such as `git-lfs` or a `core.fsmonitor` program, is found only on
      that `PATH`. Where it lives elsewhere and its filter is marked required, as `git lfs install`
      marks git-lfs's, the git query gives no answer: after a red test run, the note counting
      uncommitted files is gone. A `core.fsmonitor` program, or a filter not marked required, is
      skipped;
    - every `git` is handed the home the password database records for your user as `HOME` (none
      where the database lists none, and in the other cases `SECURITY.md` names), so it reads its
      global configuration, your `safe.directory` and excludes among it, from there, and a
      `.gitconfig` a repository ships cannot name a `core.fsmonitor` program for it.

    `stayfixed gate` in CI, a command you run at your terminal and one an agent runs through its
    shell tool keep the `git` on `PATH`, and the programs it runs by name, as before.
- The note after a failing test run now reaches Claude Code. Claude Code reports a `Bash` command
  that exits non-zero on its `PostToolUseFailure` hook event, never on `PostToolUse`, and the note
  was registered on `PostToolUse` alone, so it never spoke after a red run there. The plugin's
  `hooks/hooks.json` gains a `PostToolUseFailure` entry for `Bash` that runs the same note, once per
  session, from the exit code at the head of the failure's `error`. The `PostToolUse` entry stays,
  and the two share one delivery, so a session gets at most one note; Codex reads the same file and
  ignores the new key.

  The note also reaches a run started through `uv run` with uv's own options, such as
  `uv run --locked pytest`, the command the README and the `attribute-failure` skill suggest,
  `uv --quiet run pytest` or `uv run -- pytest`. Only a bare `uv run pytest` was read through, so a
  failing `uv sync --locked && uv run --locked pytest …` got no note at all. A `uv` command carrying
  an option uv does not list still gets none, so a value such as the package in
  `uv run --with pytest echo` is never taken for the program.
- `[ledger] evidence_boundary_required_for` is now checked against the bug ledger's severities
  (`high`, `medium`, `low`). A value naming none of them — `"critical"`, `"High"`, a misspelling —
  used to load and require the evidence line of no entry, so every `high` entry passed `stayfixed
  bugs check` without one. Such a configuration, accepted until now, is refused (exit 2) by every
  command that reads the ledger, `stayfixed bugs`, `plan check`, `memory refs`, `init` and
  `upgrade` among them, with a message that counts the values and does not quote them;
  `stayfixed uninstall` still runs.
- `stayfixed assess`'s `foreign-hooks` item now reads a committed settings file the way
  `stayfixed doctor`'s `hook-entries` row does:

  - it lists a file holding a hook entry that claims stayfixed's marker (`# stayfixed:<id>` at the
    end of its command). It passed any such entry over as stayfixed's own, whatever its `type` and
    whichever id it claimed, so an entry of `type` `http` that posts every event to a URL read as no
    foreign hook at all. stayfixed writes no hook entry into a committed settings file, and `assess`
    has nothing to compare an entry with, so the marker there vouches for nothing; `doctor`'s
    `hook-entries` row is the one that can account for a marked entry, against what your overlay
    grants;
  - a file holding a number longer than Python converts to an integer (4,300 digits by default),
    valid JSON that a harness reads, is no longer reported as one it could not look at
    (`could-not-look`): its entries are read, and an unmarked one names the file;
  - a file that opens with a byte-order mark, or holds a misplaced value beside valid hook entries,
    has those entries read, as Claude Code runs them.
- `stayfixed attach --check` now ends as the run would, with the same exit code and the same line,
  wherever the run refuses or fails before its first write. 0.2.0's `--check` read the settings file
  and several other inputs with filters of its own, or not at all, reported a clean diff and exited
  `0`, and `attach --yes` then refused or failed:

  - a `.claude/settings.local.json` whose `"permissions"`, or `"allow"` inside it, is `null`; an
    event under `hooks` whose value is `null` or is not a list; an entry group that is not an object,
    or whose `hooks` is `null` or not a list; an entry that is not an object (exit `2`);
  - an existing `.stayfixed/local/attach.json` that is not valid JSON or cannot be read (exit `1`),
    or that names what `attach` never writes or is itself a link (exit `2`);
  - an overlay Codex rule file that is not UTF-8 (exit `1`);
  - a `~/.claude` that is a symlink, as a dotfiles manager leaves it, a `trust.json` that does not
    parse, an `origin` URL that is not UTF-8, a `.gitignore` that is not UTF-8 or holds the
    `stayfixed:ignore` region twice, an exclude file that holds the `stayfixed:attach` block twice or
    sits in a `.git/info` you cannot write, and a `.claude` linked in from elsewhere when the overlay
    grants something to merge into it (exit `2`).

  `null` is now read the same way wherever `attach` reads a settings document: as a value that is
  not the object or list that goes there, never as an absent key. So your overlay's own grant files
  are refused by both commands too, where both read them as granting nothing: a `permissions.json`
  under `common/claude/` or a project's `claude/` whose `"permissions"` or `"allow"` is `null`, and a
  `hooks.json` there with an entry group whose `hooks` is `null`. Remove the key, or give it `{}` or
  `[]`; until you do, `--check` names the clause, and for a repository already attached under such a
  `hooks.json`, `stayfixed doctor`'s `hook-entries` row warns that the overlay could not be asked
  which entries it grants.

  Four things the run refuses (exit `2`) are still gates `--check` reports instead. An allow rule or
  hook entry the run would add without `--yes`, and an `origin` other than the remote the overlay
  recorded, without `--trust-remote`, are reported, the second with exit `1`, and `--check` reads on
  as a run given the flag would. A checkout with no `origin`, and a memory group still a real
  directory in the repository rather than a link into the overlay, are reported with exit `1`, and of
  the rest `--check` reads only the names of the Codex rule files: at a checkout with no `origin` it no longer counts the groups that never
  moved (`real_directories` in `--json` is `0` until the `origin` is added), and a `memory.groups`
  entry outside `paths.memory` no longer ends it with that entry's refusal. A `memory.groups` entry
  that leaves this project's share of the overlay is refused in the run's words. Outside overlay
  mode, `--check` reports the run's refusal of the mode and exits `2` even where the rest cannot be
  read, where it ended with whatever stopped the rest, at times with exit `1`. A refusal that names
  an event prints it escaped when it holds a line break or a control character.
- `stayfixed attach --machine` and `stayfixed detach --machine` run without a terminal are refused, as
  before, with a reason of their own: such a command may be an agent's, and a repository can tell an
  agent which file to name. The refusal said the flag followed the rule `STAYFIXED_CONFIG` and
  `XDG_CONFIG_HOME` follow, two variables no stayfixed command reads to find that file.
- `stayfixed attach` and `attach --check` now find these before anything is written, and say what is
  wrong, where `--check` reported nothing or the system's error, and `attach` failed part-way or ended
  in an internal error:

  - an overlay whose root, or whose `projects/`, is a file rather than a directory, or a symbolic
    link that names nothing, is refused (exit `2`) as a damaged overlay, naming that path and asking
    for the overlay to be repaired. Both failed (exit `1`) on the error for a file inside it, such as
    `[Errno 20] Not a directory`. `stayfixed doctor`'s `attached` row names the same path and says to
    repair the overlay, still as a warning, where it said the overlay had no binding for the project
    and offered to remove the ledger; with `projects/` a file, `hook-entries` judges the checkout's
    entries against what `common/` grants every project, where it warned that the overlay could not
    be asked;
  - an overlay `common/codex/` or `projects/<name>/codex/` directory the user running them cannot
    list, or holding entries that cannot be asked about, fails (exit `1`), naming the directory and
    saying nothing was written, where both ended in `internal error: PermissionError` (exit `2`). A
    Codex rule file there that cannot be read is named the same way, in quotes with any control
    character escaped;
  - a `memory.groups` entry holding a NUL character is refused, as one that leads out of the
    project's notes in the overlay is, and is never printed back;
  - a `[project] name` or `memory.groups` entry longer than the overlay's filesystem takes as a file
    name, where the overlay has no directory for the project yet (or no `projects/` at all), and one
    that would put a path in the project's directory in the overlay past the longest the system
    allows (its binding record, its notes index or a group's directory) are refused, naming neither
    the project nor the group. `attach` wrote some of `.git/info/exclude`, `.gitignore`, the settings
    merge, its ledger and the binding record before failing with an internal error ("File name too
    long") that printed the name.
- `stayfixed attach` now says when it withdrew harness memory links, the links through which Claude
  Code reads a project's notes, and why. When an approved store changed, one line appended to one
  note being enough, the run withdrew the link from every checkout and said only that the link "has
  no approval yet", as of a store nobody approved. It now counts the links it withdrew and says the
  store or its `memory.index_extra` changed since its approval was recorded; a store never approved
  is still told it has no approval yet. What is withdrawn is unchanged.
- `stayfixed attach` run from a linked worktree no longer says the harness memory link could not be
  created right after making it, and no longer records `autoMemoryDirectory` in that worktree's
  `.claude/settings.local.json` beside the link. The link points at the store the main checkout
  holds, and the check that followed compared it with the worktree's own link tree. The same
  comparison made the run say the link waited for `stayfixed memory trust --in-repo-memory` when the
  store was already approved. Where a real directory does stand in the way, the recorded
  `autoMemoryDirectory` now names the main checkout's store. Run `stayfixed attach` from the worktree
  again to take back a key an earlier run recorded there.
- `stayfixed attach`, `attach --check` and `stayfixed doctor`'s `attached` row now read the overlay
  root from the machine configuration once, so a machine file changed during a run can no longer have
  the `--store` checked against one overlay and the binding read from another.
- `stayfixed attach`, and every command that asks which checkout owns a worktree, no longer reports a
  `git` question that ran out of time, a `git` a signal ended, or a worktree removed while the command
  ran as a `git` that cannot run. The refusal names the checkout and the cause: a question that ran
  out of time on a heavily loaded machine, or a `git` a signal ended, says to run the command again,
  and only a `git` that cannot start or fails even `git --version` says to check that `git` runs. A
  `git` a signal ended no longer reads as a worktree that is its own main checkout, which linked
  nothing into it without saying so, and `attach` skips a worktree that disappeared after
  `git worktree list` named it, instead of failing the whole run and leaving every later worktree
  unlinked.
- `stayfixed bugs check --base`, and the `bugs` gate under `stayfixed gate`, now read the base's
  ledger where the base's own `stayfixed.toml` kept it. They listed the base's entries at the
  change's `[paths] bugs`, so a change that moved the ledger found no entries on the base and could
  delete one in the same change and pass, under `stayfixed gate` whenever the base enforced nothing,
  even where the change enforced `bugs` itself. A change to `[ledger] id_prefix` now answers for every
  entry under the old prefix, and a ledger deleted along with a `[paths]` move is named at the paths
  the base kept it at. A base copy that does not load now fails the check (exit `1`), and one whose
  load meets a refusal, or whose `[ledger] id_prefix` the ledger refuses, refuses it (exit `2`),
  rather than reading as a base with no ledger; a base with no `stayfixed.toml` is still read at the
  change's paths. The base's copy is found the way `stayfixed gate` finds it, so `bugs check --base`
  refuses (exit `2`) a project root whose path inside the repository runs through a symlink, as the
  gate does.
- `stayfixed bugs new` and `stayfixed bugs index` no longer end in `internal error` (exit `2`) when
  the index cannot be written, in a directory this user cannot write, say; both exit `1` with the
  reason. `bugs new` writes the entry before the index, so its failure left a filed entry behind a
  line that did not say so, and running the command again filed the same report twice. It now says
  `filed <entry>, but <index> could not be written (<reason>); once it can be, run `stayfixed bugs
  index`, not this command again, which would file it a second time`, followed by the warning a
  failed fetch gives, that the new number may collide with a branch this checkout has not fetched.
- `stayfixed bugs new` no longer fetches from the remotes of a project's submodules. The
  `git fetch` it runs before allocating an identifier now passes `--no-recurse-submodules`: it needs
  only the project's own refs, and under git's default `fetch.recurseSubmodules=on-demand` it also
  asked the remote of each checked-out submodule whose recorded commit the fetch brought in, so a
  submodule remote that could not be reached failed the fetch and printed a warning that
  identifiers might collide.
- `stayfixed bugs renumber OLD NEW` killed part-way is now finished by running the same command
  again. The re-run refused because `NEW` already had an entry file, and `stayfixed bugs check`
  reported only a stale index, whose remedy, `stayfixed bugs index`, turned the check green over two
  live entries for one bug or over mentions of `OLD` the move never rewrote. The re-run recognises
  the move's own half-done state, even when `NEW` was retitled in between, makes the writes still
  missing and leaves the tree an uninterrupted run would have; any other entry already at `NEW` is
  still refused, and the refusal says how to finish by hand a move whose `NEW` was edited after it
  was interrupted. A re-run of a move that finished changes nothing and says so. `bugs check` now
  names that re-run, rather than `bugs index`, when the stale index is the one an interrupted move
  left; where more than one move explains it, as when `stayfixed bugs new` run twice filed two
  entries that differ only in their `id:`, it names each and says only the one that was started
  finishes it. A write of the move's own that fails, such as an index in a directory that cannot be
  written, ends the command with exit `1`, naming the file and the re-run, where it was an internal
  error with exit `2`. `stayfixed bugs renumber X X` fails (exit `1`): there is nothing to move.
- `stayfixed commit check` now refuses a `-by:` trailer whose name is `ChatGPT` or `Cursor`, such as
  `Assisted-by: ChatGPT` or `Generated-by: Cursor`, which it documented as attribution and let
  through. `stayfixed commit strip`, and with it the `prepare-commit-msg` hook, reads the same table,
  so it now strips these lines too. A name is judged whole, as before: a person whose name holds one
  of the words, such as `Cursor Smith`, is not refused.
- `stayfixed detach` no longer leaves another attached checkout of the same repository half
  attached. With the main checkout and a linked worktree both attached, a detach in either one took
  every checkout's link tree, so the other kept its ledger and lost its notes, and its harness memory
  link pointed at nothing. While another checkout still holds an attach ledger, `detach` now
  withdraws only its own checkout's harness memory link, settings, rule copies and ledger, and its
  link tree unless it is the main checkout, whose tree every checkout's harness memory link points
  at. Then it says it kept that tree, beside the exclude block it says it kept, and `--json` reports
  `link_tree_kept`. The last checkout to detach takes back every checkout's link tree and harness
  memory link, as a single detach did; detaching them one at a time can leave empty directories git
  does not show, the `docs/` above `paths.memory` in the checkout that detached first and, where the
  main checkout went first, a linked worktree's `paths.memory`. A linked worktree's harness memory
  link is now recognised and withdrawn rather than left behind dangling. Where a `paths.memory` a
  harness memory link is compared with cannot be asked where it leads, `detach` refuses before it
  withdraws anything, saying whether it is the main checkout's or a linked worktree's, and why.
- `stayfixed detach` now refuses (exit `2`), before it withdraws anything, where this user cannot
  write the directory that holds `.git/info/exclude`, naming the file as `stayfixed attach` does.
  Before, it found out by writing the file, after the settings file, the `.codex/rules/` copies and
  the link tree were withdrawn, and stopped there with the ledger and the exclude block still in
  place.
- `stayfixed doctor` now names the machine configuration file it actually read when that file does
  not load. Run from a terminal with `STAYFIXED_CONFIG` or `XDG_CONFIG_HOME` set and no `--machine`,
  it read `~/.config/stayfixed/config.toml`, as it does whatever those variables say, and then told
  the owner to fix the file the variable names instead, which it had not read.
- `stayfixed doctor`'s `attached` row now reads a checkout's harness memory link the way
  `stayfixed attach` writes it, and reads one machine state the same way from every checkout:

  - a linked worktree attached the ordinary way no longer reads red, "a link to a directory that is
    not this project's note store": `attach` points every checkout's link at the main checkout's
    tree, and the row compared it with the worktree's own;
  - a link that reaches nothing is red from every checkout, where the main checkout warned once its
    own link tree was gone;
  - `autoMemoryDirectory` in `.claude/settings.local.json`, or in the shared `.claude/settings.json`
    (the local key wins), is read beside whatever stands at the harness memory path, since the
    harness reads what it names: any value but the one `attach` writes there, the main checkout's
    store exactly, is red, a `~/…` or relative value included, where a committed key read ok beside
    a link or nothing;
  - a real directory at the harness memory path, always red before, is in place beside the value
    `attach` writes while the store's approval holds, and warns while it does not; with no such key
    it is still red, and the remedy says to move it aside, as `attach` does, rather than remove it,
    since it can hold notes the harness wrote;
  - a link to the store, which read ok whatever the trust record said, warns where the approval
    lapsed, with the way to re-approve, where none was given, and where this machine's trust record
    cannot be read. With nothing in place, a lapsed approval warns too, rather than reading as one
    never given, and a linked worktree asks about the main checkout's store, as `attach` does;
  - beside an attach ledger whose note store does not resolve, nothing in place warns, where it read
    ok, and names the cause: a link tree that is gone is one `stayfixed attach` puts back, and
    anything else is for `stayfixed memory index --check` to explain;
  - a settings file that cannot be read as one JSON object, which the harness may still read, makes
    every answer that would be ok a warning naming the file;
  - where a linked worktree's main checkout's `paths.memory` cannot be asked where it leads, and
    where a trust record that cannot be read sits beside nothing in place, the row warns and says
    why, rather than "this check could not run".
- `stayfixed doctor`'s `hook-entries` row now vouches for a hook entry that claims the stayfixed
  marker only where your overlay grants it, as your overlay grants it, to a checkout the overlay
  binds. What the overlay grants is asked of the overlay this machine records, never of the
  committed files. A repository could commit a marked entry, in `.claude/settings.json` say, and keep
  the row at "all accounted for" or at a warning, and the report at exit `0`; such an entry is now
  red:

  - on a machine that records no private overlay, beside a `.stayfixed/local/attach.json` recording
    that entry or any other, and on every machine beside a `.stayfixed/local/attach.json` that does
    not parse;
  - when `stayfixed.toml`'s `project.name` names another project in your overlay and the clone
    copies an entry that project's `projects/<name>/claude/hooks.json` grants: what a project's own
    directory in the overlay grants now counts only for a checkout whose `origin` is the remote that
    project's record binds, and any other checkout is granted only what `common/` grants every
    project;
  - when `project.name` is a value no directory under the overlay's `projects/` can carry, such as
    the name of a file kept there (on a filesystem that ignores case, `readme.md` beside the
    `README.md` every overlay ships) or a name longer than the filesystem allows. `stayfixed attach`
    and `attach --check` now refuse such a name (exit `2`) before writing anything;
  - when it sits under another event or matcher than the one the overlay grants it under, such as
    `SessionStart` with matcher `*`, or is not the granted entry, every field of it: an entry of
    `type` `http`, which posts every event's input to a URL and ignores `command`, one of `type`
    `prompt`, `agent` or `mcp_tool`, or a `command` entry with an `args`, `shell`, `async` or other
    field your overlay does not grant. An entry `stayfixed attach` wrote is still accounted for
    whatever fields your grant carries, and the order of its keys does not matter;
  - when the settings file holding it opens with a UTF-8 byte-order mark, holds a byte that is not
    UTF-8 (now read as a replacement character), or holds, beside its valid entries, a value that is
    not a list where an event's list goes, a group that is not an object, a group whose `hooks` is
    not a list, or an entry that is not an object. Claude Code 2.1.288 was measured running the valid
    hooks of such a file, and the row read the whole file as one it could not read, a warning. A
    file that is not valid JSON is still one it cannot read; so is one whose misplaced value is an
    object or list that could hold a command, but the entries beside that value are judged too, and
    a marked command inside it is red;
  - on Python 3.11 to 3.13, beside a ledger or another settings file committed as a symbolic link to
    a name longer than the filesystem allows, which made the whole row a warning.

  A checkout of yours whose `origin` is not the remote its record binds, say after you moved
  `origin` from ssh to https, or whose record cannot be read, now has its per-project entries red,
  where they were accounted for or a warning; the row says the binding or the record is what is
  wrong and names the command that settles it. Your own checkout opened on a new machine before
  `stayfixed setup --overlay` has run reads red too, since nothing there can vouch yet for the
  entries your last attach installed: run `stayfixed setup --overlay <path>`, then
  `stayfixed attach`. A ledger that cannot be read beside marked entries your overlay grants is a
  warning, whose remedy is to remove the file and run `stayfixed attach` to write a new one. The row
  still warns while an overlay this machine records cannot be read, or `git` cannot run. An entry is
  named by its place in the whole file, counted across every group's `hooks` list in every event in
  document order, a skipped value holding a place too. Codex's `.codex/hooks.json`, which nobody
  measured, is read as strictly as before.
- `stayfixed doctor`'s `hook-entries` row now warns about each skill, command or agent file whose
  frontmatter declares hooks, saying the row does not judge them. Claude Code 2.1.288 was measured
  running a hook a project skill declared once the skill was invoked, and the row read settings files
  alone, so it answered "all accounted for" beside such a file. It reads every `SKILL.md` below the
  project's `.claude/skills`, and below a `.claude/skills` anywhere else in the repository, which
  Claude Code loads once a session reads a file there, and every `*.md` below `.claude/commands` and
  `.claude/agents`, at any depth. In a git work tree these are the files git lists, tracked or
  untracked, and those in each checked-out submodule's index, so a skill inside a directory git
  ignores, such as an installed dependency's, is not named; outside one, the row walks the tree, up
  to 500,000 directory entries, and says when it stops there. A file is named when its frontmatter
  holds a top-level `hooks` key. Frontmatter the row does not read exactly, in which it finds no
  `hooks` key, is named as one it cannot tell about, and so is a file or directory it cannot read; a
  link that leads out of the checkout, as a dotfiles setup's does, is not followed and is named as
  one that leads out, which marks no fault. These are warnings: none turns the row red or changes the
  exit code.
- `stayfixed doctor`'s `store-debris` row now lists at most 500,000 entries of the note store, and
  past them warns that it cannot say whether the store holds files that are not notes. An `in-repo`
  note store is a tree a repository commits, and the row listed every entry in it, however many.
- `stayfixed init --local ID` in a repository that is already initialised is still refused, and the
  refusal now says how to keep that file out of git instead: list its id under `[artifacts] local` in
  `stayfixed.toml`, then run `stayfixed upgrade`. It used to point at `stayfixed upgrade` alone, which
  has no `--local`.
- `stayfixed memory index` (with or without `--check`) and `stayfixed memory fit` now warn about a
  missing trust record whenever the harness memory link to the store, through which Claude Code reads
  its notes, would wait for one. They used to ask a narrower question, so an overlay-mode store with
  no committed `MEMORY.md` read as trusted, with no warning and `"trusted": true` in `--json`, while
  its link was never made. The warning now prints whenever a note, or the store's own directory, is
  inside the repository and no `stayfixed memory trust --in-repo-memory` record matches it: in
  overlay mode, every store until that record is made. For an overlay store whose notes all live in
  the overlay it says only that the link waits, since the standing-rules and volatile-notes bundles
  still deliver those notes.
- `stayfixed memory index` now takes a note's index line from `metadata.index` when the note has no
  top-level `index:`, ahead of a line `MEMORY.md` already lists for it and of its `description`. A
  note carrying its short line under `metadata:` got its description as its index line, or the
  description another writer had appended to `MEMORY.md`, recorded as `native`. The line is written
  into the note as `index:` with `index_provenance: provisional`, as a line made from the description
  is, so a later edit to `metadata.index` reaches the index only once that `index:` line is changed
  or removed; the run's summary now names the notes it wrote a provisional line into. A note an
  earlier run already gave its description as a top-level `index:` marked `index_provenance: native`
  is left as it is: delete that line, and the next run takes `metadata.index`.
- `stayfixed overlay create` no longer fails with "answered something other than the `isTemplate`
  object it was asked for" when `GH_FORCE_TTY` or `CLICOLOR_FORCE` is set in your environment: either
  one made `gh` colour its JSON output, which stayfixed could not read. Commands that run `gh` now
  leave both variables out of its environment.
- `stayfixed overlay upgrade` no longer renames an overlay's plugin back to `stayfixed-overlay`.
  `overlay init` names the three plugin manifests after your account, so that two people's overlays
  installed side by side do not collide, and an `upgrade` after it rewrote them from the template,
  putting back the shared name and the `your-account` placeholder. A refresh now writes the template
  under the name the manifests already carry, so `upgrade` right after `init` changes nothing, and a
  release that does change a manifest updates it without losing your name.

  `stayfixed overlay init` also no longer stops part-way. A manifest it cannot write is named with a
  `cannot be written` line and the others are still renamed and recorded, where the run ended in an
  internal error and every later `upgrade` treated the renamed manifests as hand-edited. When it
  replaces `common/memory/README.md` with `_README.md` and cannot write the new file, or cannot read
  the template it comes from, it says so and keeps `common/memory/` rather than removing it as empty,
  and the old file's record no longer stays behind. It no longer says it removed a file that was
  already gone.
- `stayfixed plan check` no longer reports the files a plan deletes as dead references once its
  tasks have deleted them. A path the plan lists on a `- Delete:` line now counts as declared for
  the whole plan, as a path on a `- Create:` or `- Test:` line already did, and a line marked
  `(delete)` is exempt as one marked `(create)` is. Before, a finished plan that removed files
  failed the check, and so did any later pull request that edited it.
- `stayfixed plan check`, the `plan` gate and `stayfixed memory refs` now check a backticked path in
  any language, not only one ending in `.py`, `.sh`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`,
  `.ts` or `.tsx`: a plan or a note citing `src/lib.rs`, `cmd/main.go:12` or `app/Foo.java` is told
  when the file is gone, as one citing a Python file always was. A path counts when its last part
  has an extension that starts with a letter, a dotfile such as `secrets/.env` included, so a version
  such as `releases/0.1.9` is still prose. The same rule reads a backticked `owner/lib.js`
  repository name or a dotted branch such as `release/v1.x` as a path claim, which is reported when
  no such file exists; in a note, write such a name in italics instead. A span whose first part is a
  host, such as a Go module path (`example.com/yaml.v3`) or a URL written without its scheme
  (`example.com/docs/a.html`), is prose, while a hidden directory (`.github/`) or a `.d` one
  (`conf.d/`) is still a path. A line and column (`src/b.c:3:14`) and a symbol path of
  any depth (`tests/test_a.py::TestA::test_x`, `src/lib.rs::parser::parse`) are read as a place in
  the file; before, either made the span no reference at all. The plan gate still reads only the
  lines a change writes, so an old plan's lines are checked only when a change rewrites them. The
  entry `stayfixed bugs new` writes now asks for the file "and the symbol or line in it" rather than
  showing a Python file and a pytest node id; entries already filed are unchanged.
- `stayfixed plan check`, the `plan` gate, `stayfixed docs check`'s link check over the always-loaded
  document and `stayfixed memory refs` settle a path only inside the repository, by where it really
  leads: a path reached through a committed symlink that points out of the tree is no longer checked
  against the filesystem, as one spelled with `..` or an absolute path already was not. Before, such
  a symlink let a plan, a link or a note ask whether any file on the machine exists, and read the
  answer off the findings. A symlink that stays inside the tree is still followed. A path too long
  for the filesystem to name, which crashed each of them on Python 3.11 to 3.13, is now reported as
  a dead reference or a missing link.
- `stayfixed setup --git-hooks` and `stayfixed setup --overlay` now print a path a repository can
  spell quoted, with every control character escaped, so an escape sequence in it no longer reaches
  the terminal: the hooks directory, which a repository's `core.hooksPath` or a submodule's name
  chooses, a repository's git directory, and, from `setup --overlay`, the overlay, `--root`, the
  directory `git` was asked from and the path `setup` could not ask about before its first write. The
  lines `setup --git-hooks` prints when it installs or removes the hook, the refusal that
  `--overlay <path>` is not an overlay, the note that it was recorded and `setup`'s report line
  naming it quote the path the same way; `--json` carries it as it is.
- `stayfixed setup --git-hooks` and its `--uninstall` now say what they found, and refuse what they
  cannot handle:

  - `--uninstall` printed `removed <hook>; there was no foreign hook to restore` whether it removed
    stayfixed's hook, found no hook at all, or found one stayfixed did not write and rightly left in
    place. It now prints `there is no stayfixed hook at <hook>; nothing was removed` or `left <hook>
    as it was: it is not stayfixed's hook; nothing was removed` where that is what it found, and
    `--json` gains `found`: `removed`, `absent` or `foreign`. The exit code is `0` in each case, as
    before.
  - A hook at that path that cannot be read, such as one at mode 000, stayfixed's own or anyone's, is
    refused (exit `2`) by both, `<hook> could not be read (<reason>)`, and left where it is.
    `setup --git-hooks` renamed it to `prepare-commit-msg.local` and chained it, and `--uninstall`
    reported it removed while leaving it, or restored it when it had been chained.
  - A FIFO or a directory at that path is not stayfixed's hook: `--uninstall` leaves it in place and
    says so (exit `0`), where it hung on a FIFO and reported a directory as removed, and
    `setup --git-hooks` refuses a FIFO (exit `2`, `not a regular file`), where it hung. A regular
    file there past the 64 MiB read cap is still treated as a foreign hook.
  - `setup --git-hooks` refuses (exit `2`) a `prepare-commit-msg` already in place whose text names
    `prepare-commit-msg.local`, such as one ending in
    `exec "$(git rev-parse --git-common-dir)/hooks/prepare-commit-msg.local" "$@"`. Kept as `.local`
    and run last by stayfixed's hook, it ran itself, and every `git commit` hung until it was killed.
    Remove its chain line, or move it aside, and run the command again. A re-install refuses too, and
    leaves the installed hook as it was, when the kept `.local` already names itself. A chain spelled
    `exec "$0.local" "$@"` does not run itself once kept, and is installed as before.
  - The hook's own comment names `stayfixed setup --git-hooks` as what installs it and its
    `--uninstall` as the way to remove it, where it said no `stayfixed` subcommand installs it. A
    hook an earlier release installed keeps working and is still recognised as stayfixed's; run
    `stayfixed setup --git-hooks` again to replace its text.
- `stayfixed setup --overlay` now judges where an overlay may live against the repository `--root`
  is in:

  - `stayfixed setup --overlay create:<owner>/<name> --yes` run in a home directory that is not a
    repository (no `.git` at or above it) is no longer refused for creating the overlay inside it,
    and neither is the same command run again over the clone it made: a `create:` destination is
    exempt from that comparison while it is not there yet, or when it is the overlay root the machine
    configuration already records. `create:` records the destination resolved, as `--overlay <path>`
    records its path, so a link at `<home>/<name>` is followed once; one whose target is not there is
    refused before anything is created on GitHub.
  - Any other overlay already on disk inside, around or equal to such a `--root`, a `create:`
    destination that is there and not recorded among them, is still refused, before `overlay init`
    writes in it, since a project downloaded as an archive, or a checkout of another version control
    system, can ship one. In a home that is a git work tree with its `.git` there, such as a dotfiles
    clone, `create:` is still refused before anything is created on GitHub; a home whose dotfiles
    repository keeps its git directory elsewhere, and one another version control system tracks, have
    no other checkouts compared.
  - An overlay inside a checkout of any other repository, including a checkout of its own nested in
    one, is now refused wherever `--root` is, and so is a linked worktree of the overlay's own
    repository nested in another checkout of it, in words that say it is the overlay's own
    repository.
  - Inside a checkout, a `git` that exits non-zero, is ended by a signal, prints nothing or answers in
    a shape git does not give (git 2.30 and older print the `--path-format` they do not know, and a
    wrapper can print a banner) is a refusal, where it was read as no repository and the project's
    other checkouts went uncompared.
- `stayfixed setup` now finds, before it writes anything, a path it cannot use, and names it, where
  it ended in an internal error or wrote the machine configuration file first:

  - a `--home` that cannot take what `setup` writes there (one it makes nothing in, such as a home
    holding a writable `.claude` already, is not refused), and a `--settings` directory you cannot
    write into, or that the settings write must read and you cannot, such as a `.claude` at mode
    300. A home under a read-only directory ended in `internal error: PermissionError`, and a
    read-only home had the machine file written and was then refused in words about a symlink that
    was not there;
  - an `--overlay`, `--root` or `--settings` below a directory nobody may search, and an existing
    `--overlay create:` destination that cannot be searched, which ended in an internal error;
  - a regular file at `<home>/.claude`, or a directory at `<home>/.claude/settings.json`, where the
    machine file was written and reading the settings file then failed (exit `1`);
  - a machine configuration file it is not allowed to read: it fails saying the file cannot be read
    (exit `1`), as every other command does, where it ended in an internal error quoting the
    system's message (exit `2`).

  A `--home` that is a link to a directory, such as a home on another volume, is followed once and
  every write under it lands where it leads, where the machine file was written and the settings
  write then refused.
- `stayfixed upgrade`, `stayfixed overlay upgrade` and `stayfixed overlay init` no longer keep the
  record of a file they retire after you have already deleted it. Such a file was read as unchanged,
  so `.stayfixed/manifest.json` carried its record into every later run; it is now listed as
  `remove … (retired, already gone)` and its record is dropped, with nothing removed. A retired file
  that is gone and that the manifest does not record is left out of `overlay upgrade`'s report and
  its `unchanged` count: every run named `common/memory/README.md`, which 0.2.0 retired, among the
  unchanged files of an overlay that had deleted it or never had it, a freshly created one included,
  counting one more file than the overlay holds. The two files this release retires
  (`skills/attach/SKILL.md` and `common/rules/README.md`) are left out the same way. In an overlay
  whose old `common/memory/README.md` was deleted by hand, `overlay init` now writes `_README.md` in
  its place, as it does when it removes the old file itself.
- stayfixed no longer takes your home directory from `HOME` to find the files it keeps for you, at a
  terminal or not: it takes the one the password database records for your user, which no
  environment variable moves. A tool that applies a file the repository commits, such as direnv,
  mise or a devcontainer, can set `HOME` for a hook, and a hook runs inside the project, so a `HOME`
  naming a directory the repository ships made a `trust.json` committed there approve the
  repository's own notes as standing rules with no `stayfixed memory trust` from you. (Claude Code's
  own `.claude/settings.json` `env` block cannot set `HOME`.)

  - `~/.config/stayfixed/config.toml` and `~/.config/stayfixed/trust.json` are found under that home
    by every command, `stayfixed setup` and `stayfixed memory trust` included, so the file you write
    from a terminal is the one a hook reads. A `~` in `[overlay] root` means that home too.
  - From your own terminal, `HOME` still decides `--home`'s default and where `stayfixed attach` puts
    the harness memory link, the link under `~/.claude/projects/` through which Claude Code reads the
    project's notes.
  - Where `HOME` is not the database's home, as in some containers and home-manager setups, nothing
    else is refused: `stayfixed doctor`'s `ignored-env` row warns and names the directory your
    machine files are under, and `stayfixed memory trust` and `stayfixed setup` say which directory
    they wrote under. A hook gives no sign that a file under `HOME` is no longer read: approved notes
    stop being injected and `[personal]` falls back to the preset. Move a `config.toml` or
    `trust.json` you kept under `HOME`'s `.config/stayfixed` to the database's home **before**
    running `stayfixed setup` or `stayfixed memory trust`, or merge them afterwards; move only files
    you put there yourself.
  - In that case no hook makes the harness memory link, since the harness finds its memory through
    `HOME`; the session is told so and what makes the link, and `stayfixed doctor`'s new
    `harness-link` row says the same. `stayfixed attach` run without a terminal, by an agent say,
    makes none either, says so and what makes one, and does the rest of its work (exit `0`). A link
    under `HOME` is still removed when the store's approval lapses, and `stayfixed detach` removes
    one under either home.
  - A user the database lists no home for reads no machine file and no trust record unless
    `--machine` names one: `stayfixed setup` and `stayfixed memory trust` fail asking for it, and a
    hook makes no harness memory link. At a terminal with `HOME` unset, `stayfixed attach` and
    `stayfixed detach` refuse for such a user, saying the database lists no home and that `HOME` set
    at a terminal names one, where they ended in an internal error ("Could not determine home
    directory"). A database home that cannot be written fails `setup` and `memory trust` naming the
    directory.
  - At a terminal where `HOME` is set and empty, which Python reads as the root directory,
    `stayfixed attach` and `stayfixed detach` refuse (exit `2`) and `stayfixed setup` fails (exit
    `1`) before writing anything, saying that `HOME` names no home directory, and `stayfixed
    doctor`'s `attached` row says the same. `attach` with an approved store ended in an internal
    error making the harness memory link under `/.claude`, and `setup` in one creating `/.config`,
    or, given `--machine`, wrote that file and then refused to write `/.claude/settings.json`.

### Changed

- A new overlay's secret scan is brought up to date, and `stayfixed overlay upgrade` brings an
  existing overlay's untouched `.github/workflows/scan.yml` and `.pre-commit-config.yaml` along:

  - the `scan` workflow pins `actions/checkout` v7.0.1 and `gitleaks/gitleaks-action` v3.0.0, both
    on the Node 24 runtime, runs gitleaks v8.30.1 (`GITLEAKS_VERSION`) rather than the 8.24.3 the
    action defaults to, and its checkout no longer keeps the token; the pre-commit hook pins
    gitleaks v8.30.1 at a full commit sha, where it pinned the tag v8.21.2;
  - the workflow grants `pull-requests: read` beside `contents: read`. On a pull request the gitleaks
    action lists the pull request's commits through an endpoint GitHub documents as needing that
    permission on a private repository, which an overlay is, so the scan of a pull request in an
    overlay created from 0.2.0's template was likely to fail (stayfixed did not observe that
    failure);
  - it fetches the full history and scans what the action's range covers: on a push, the commits in
    the push; on a pull request, the first 30 commits the action lists for it; on a manual run, all
    of the history. An overlay on a personal account needs no licence key;
  - it skips a repository marked as a template, such as the overlay template itself, which, public
    and owned by an organisation, failed every run for want of a gitleaks licence key. An overlay
    generated from a template is not one, and still runs the scan.

  A file you or Dependabot have edited is left alone and named; add `pull-requests: read` under its
  `permissions:` yourself. The overlay's own Dependabot configuration keeps the workflow's action
  pins current either way; `GITLEAKS_VERSION` and the hook's `rev:` are bumped by hand, together.
- The Claude Code plugin is now installed from `stayfixed/stayfixed-plugin`, at the release's tag
  and at the commit that tag names, both pinned in the marketplace entry, so a tag moved there does
  not change what installs. That repository holds only what the plugin runs — its two manifests,
  the hooks and their wrapper, the launcher, the `stayfixed` package, the skills, the agents, the
  README and the licence — where the plugin used to be this whole repository, tests, plans and
  tooling included. The marketplace stays in `stayfixed/stayfixed`, so the install commands do not
  change. Each release attests the plugin tree it publishes, and its GitHub Release carries that
  tree's manifest, `plugin-tree.txt` — one line per file with its mode, its sha256 and its path — so
  the plugin repository's tag can be compared with what the release built.
- The `stayfixed release` commands are gone from the installed CLI: they only ever checked this
  repository's own release, and now live in its `scripts/release.py`. Nothing a project runs used
  them.
- The note after a failing test run now comes from the profile of the stack whose test runner
  failed, so a repository in several languages gets the right advice with no configuration. After a
  failing pytest run it reads as before: the line about uncommitted changes, which comes with any
  failing run a profile recognises, then Python's line about stale bytecode. A failing command the
  hook cannot split into words (an unbalanced quote, say) no longer gets the note, where any such
  command containing the word `pytest` did.

  `stayfixed test hygiene` now reports per profile. Its summary names each finding as
  `<profile>: <note>`, and a clean tree reads `tree is clean; the python profile has nothing to
  report`. In `--json` the top-level `stale` and `roots` keys are gone and the counts sit under
  `profiles`, by profile name (`{"dirty": 0, "profiles": {"python": {"stale": 0, "roots": 2}}}`). A
  profile is listed when its markers sit at the repository root, and also whenever it has something
  to report. `test hygiene` refuses (exit `2`), naming the profile, when a shipped profile's hint
  cannot be loaded or answers in something other than text.
- Two session-start bundles are gone: `preset-rules`, which no shipped preset has filled since
  0.2.0, and `index`, which only Codex asked for, where stayfixed does not rely on the plugin's
  hooks. `memory session-context --bundle` accepts `standing-rules` and `volatile-notes`, and a
  session starts with four fewer hook commands. Two things a script may depend on change with them:

  - `memory session-context --bundle index` and `--bundle preset-rules` now exit `2` with a refusal
    naming the bundles that remain (`{"error": "refused", ...}` under `--json`), where they used to
    exit `0`, or `1` where no `stayfixed.toml` loaded or the note store did not resolve;
  - the `bundles` object `memory fit --json` prints has lost its `index` and `preset-rules` keys.

  A session that was already running when stayfixed was upgraded in place, from a local marketplace
  or `--plugin-dir`, can still hold 0.2.0's list of session-start commands, and run through this
  release each of those four exits `2`: restart such sessions after upgrading.
- What stayfixed claims on each agent is now stated per agent, in the README, in `docs/cli.md` and
  in `stayfixed doctor`'s `codex-trust` row. Measured on the Codex CLI `0.162.0-alpha.17.2`, Codex
  runs a plugin's hooks once they are trusted in `/hooks`, skips untrusted ones without a message,
  and passes a blocking `PreToolUse` hook's reason to the model. stayfixed has not verified its own
  session guards and session notices end to end on Codex, so it claims no tier for them there: the
  README's table says "not verified", and so does the `codex-trust` row when `[stayfixed] agents`
  lists `codex`, which also says the repository gates hold in CI. The row is still a skip. On Claude
  Code the session guards block, and the repository gates hold in CI for both agents.
- `stayfixed adopt begin` is gone. `stayfixed adopt promote` already moved a project from
  `initialised` itself, so the minimal path is `stayfixed init`, then `stayfixed assess`, then
  `stayfixed adopt promote` as each gate passes. A project `0.2.0` left in `adopting` keeps working.
- `stayfixed attach`, `attach --check` and `stayfixed detach` now refuse (exit `2`), before anything
  is written, a `.claude/settings.local.json` that stayfixed's indented write-back would make longer
  than the 64 MiB it reads ("would be longer than this reader reads once written back"), and
  `attach` and `--check` refuse it even when the run would not rewrite it. Written back indented, a
  document many levels deep grows by its depth on every line: a 12 KB file 6,000 lists deep came back
  from 0.2.0's `attach` as 72 MB. Every other JSON file stayfixed writes back indented, such as a
  settings file `init`, `upgrade` or `setup` rewrites or an overlay manifest `overlay init` renames,
  is checked the same way before it is written, so no command leaves a file its next read cannot
  take; `stayfixed setup` and `overlay init` fail (exit `1`) naming the file. That includes a
  `~/.claude/settings.json` that 0.2.0's own `setup` already wrote back past 64 MiB, which has to be
  cut down by hand before `setup` runs again.
- `stayfixed docs check --memory-graph` is gone: `stayfixed memory refs` now reports the note store's
  link graph as notices, beside the stale paths it already finds, and its exit code still counts only
  the stale paths. `stayfixed docs check` no longer takes `--store`, which only that graph read, and
  refuses it as a usage error.
- `stayfixed doctor` lists its checks in a new order, one more of them: the installation's own
  eleven first, then the six about the private layer — the binding's, the note store's, the new
  `harness-link` among them, and the private overlay's. Anything that parsed the report by position
  should match on the check's name.
- `stayfixed overlay upgrade` and `overlay init` remove two files the overlay template no longer
  ships: its copy of the `attach` skill (the plugin's own, which also covers detaching and a moved
  remote, is the one that stays) and `common/rules/README.md`, which nothing read. A directory a
  removal leaves empty goes with it, so `skills/` and `common/rules/` disappear unless they still
  hold a file of yours. A copy you edited is kept and named on every run, with the way out: delete
  it once you no longer need your edits, after moving any rules in the README into notes with
  `metadata.startup`. `overlay init` no longer stops at a retired file it cannot remove, which left
  the files it had already removed still recorded in `.stayfixed/manifest.json`: it names that file
  with a `left` line, removes the rest, and the next run finishes the job.
- `stayfixed plan check`, run without naming a plan, and the `plan` gate now check a backticked path
  only on the lines the change adds or rewrites. A delivered plan is a record, and the files it
  names move on; before, a pull request that edited one line of an old plan — an `Interfaces:`
  block, say — failed on every path in it that no longer exists, and the only way through was to
  rewrite the plan's history. A new plan is still checked in full, and naming a plan
  (`stayfixed plan check PATH`) still checks every reference in it.
- `stayfixed test audit-entrypoints` is gone: it read only pytest files and no gate ran it. The
  `run-correctness-audit` skill no longer calls it.


## 0.2.0 (2026-09-30)

### Fixed

- A first `stayfixed attach` now writes the store's `MEMORY.md` when there is none. The index link
  it creates used to dangle, and `stayfixed memory index --check` reported the index out of date,
  until `stayfixed memory index` was run.
- A freshly created overlay now passes `claude plugin validate`: its marketplace names an `owner`
  and both plugin manifests an `author`, which `stayfixed overlay init` sets to your account (an
  existing name of your own is kept). The documentation the overlay ships in `common/memory/` is
  now `_README.md`, which the note reader skips. `stayfixed overlay init` and `stayfixed overlay
  upgrade` remove the old `README.md` where it still holds the text 0.1.x shipped, so `memory index
  --check` no longer reports it unreadable in every attached project; a copy you edited is kept, and
  the line says to rename it to `_README.md`. Where the overlay has no `_README.md`, as one generated
  from a 0.1.x template has not, `overlay init` writes it in the old file's place, so
  `common/memory/` is not left empty for git to drop.
- When a real `stayfixed.toml` does not load (a file or value the loader refuses, or a `[paths]`
  entry that leaves the project or passes through a symlink, such as a symlinked `AGENTS.md`),
  `stayfixed hook` now says so in its own words and points at `stayfixed docs check` for the
  detail, instead of printing `internal error` with the loader's message. The verdict per event is
  unchanged: a `PreToolUse` call is still refused, and every other event still continues open. On
  0.1.1 a refused `PreToolUse` printed that message on the stderr the model reads, and it could
  carry a key, a table name or a `[paths]` value the repository chose (plain names only: letters,
  digits, `.`, `_` and `-`, and in a path also `/`); it now prints only stayfixed's own words.
- `stayfixed attach` and `stayfixed doctor` no longer call a checkout "not the repository it was
  bound to" when the overlay records a different remote URL. URLs are compared exactly, so an https
  clone of a repository the overlay recorded over ssh (or the other way round) is a mismatch too,
  and the message now says so; `--trust-remote` still rebinds it. A checkout with no `origin` is no
  longer a mismatch at all: `attach`, `attach --check` and `doctor` called it one and pointed at
  `--trust-remote`, which then refused for the missing `origin`. The memory commands used to answer
  every binding failure with one sentence, that the overlay does not record this repository's origin
  remote for the project, and to run `stayfixed attach`. They now name the cause (no `origin` in this
  checkout, no remote recorded for the project, an unreadable record, a different remote URL, or an
  overlay root that is no longer a directory on this machine) with the way out that fits it, only a
  different remote URL points at `--trust-remote`, and a missing `origin` is said in the same words
  by the memory commands, `attach`, `attach --check`, `doctor` and the session-start line.
- `stayfixed attach` no longer leaves its machine-local files for `git status` to list. The note
  link tree, the `.codex/rules/` copies and, when `attach` writes it, `.claude/settings.local.json`
  are hidden through a marked block in the repository's own exclude file (`.git/info/exclude`,
  which every worktree shares). A path your own exclude file or global excludes file already hides
  gets no line; a committed `.gitignore` does not count, because a pull can change it. `.gitignore`
  is now written only when it does not already hide `.stayfixed/local/` and
  `.stayfixed/assessment.json`. `stayfixed detach` removes the block and gives the exclude file back
  as it was, but keeps the block while another checkout of the repository is still attached
  (`exclude_block_kept` in `--json`). It also removes the empty directories `attach` created, which
  it used to leave behind: `paths.memory`, the one above it and the harness's
  `~/.claude/projects/<slug>/`.
- `stayfixed attach` now makes every refusal before it writes anything. A repository whose
  `memory.mode` is not `overlay` used to be refused only after `.gitignore`, `.codex/rules/`,
  `.claude/settings.local.json`, the ledger and the overlay's record of the project had been written,
  and `stayfixed attach --check` exited `0` for it; both now exit `2`. A `.stayfixed`, `.codex` or
  `.claude` that is a symlink used to have `.gitignore` and more written and then stop with `internal
  error: UnsafePath`; it is now refused, naming the symlink. An overlay rule file that is not UTF-8
  and a `trust.json` that does not parse used to stop `attach` after `.gitignore` and some or all of
  the rest had been written; both are now found first. `stayfixed detach` likewise refuses, naming it,
  a `.codex`, `.claude`, `.stayfixed`, `.stayfixed/local` or `paths.memory` that became a symlink
  after the attach, before it withdraws anything; it used to stop with `internal error: UnsafePath`,
  in most of those cases after taking the settings file away. A `.claude` linked in from elsewhere
  that `attach` never wrote into no longer stops `detach` at all. When the harness memory link is held
  back until the store is approved, `attach` now says so and names the way out: run `stayfixed memory
  trust --in-repo-memory`, then `stayfixed attach` again.
- `stayfixed docs check --memory-graph` now says when there was no memory store to check, and why,
  instead of passing without a word about the graph; its exit code is unchanged.
- `stayfixed init` no longer glues its `.gitignore` region onto a last line that ends in a lone
  carriage return. git ends a line only at a newline, so it read your last pattern and the region's
  first line as one pattern, and your pattern stopped hiding anything.
- `stayfixed memory index --store <overlay>/projects/<name>/memory` now resolves the same store as a
  plain `stayfixed memory index` in the attached project, `developer` group included, and so writes
  the same `MEMORY.md`. It used to leave the developer notes out, and `--check` then called that
  index current. The same holds for every `memory` command that takes `--store`.
- `stayfixed overlay create --local` now leaves a git repository on branch `main` with no remote,
  and its last line names the two commands that give it one (`git remote add origin <url>` and
  `git push -u origin main`). It used to leave a plain directory. A directory that is already a git
  repository is left on its own branch with its own remotes, and the line says so.
- `stayfixed overlay create`, `stayfixed overlay init`, `stayfixed overlay publish-template`,
  `stayfixed attach` and `stayfixed setup` now quote what `gh`, `git`, `pre-commit` and a harness's
  plugin command print in their failure lines the way stayfixed quotes a name a repository chose: a
  line break or an escape sequence in it is escaped, so it can neither start a CI workflow command
  such as `::error::` nor drive a terminal, and an answer longer than 120 characters is cut to its
  first 120 and its length.
- `stayfixed overlay init` no longer records a plugin manifest you had edited as stayfixed's own. It
  recorded every manifest it renamed as the bytes it wrote, so an edit made before `init` (a
  description of your own, say) read as stayfixed's, and the next `stayfixed overlay upgrade`
  refreshed the file: your edit and the account suffix on its name were gone. Such a manifest is still
  renamed, and `overlay upgrade` now keeps listing it as hand-edited. `init` also reads every
  manifest before it rewrites any, so one that cannot be read stops it with none of them changed.
- `stayfixed setup --overlay create:<owner>/<name>` run again over the overlay it made no longer
  says it created the overlay: it says it found it and generated nothing, and names the files
  `stayfixed overlay init` changed there.

### Changed

- The `recommended` preset no longer carries a `[rules]` table, so the `preset-rules` session-start
  bundle is empty for it. stayfixed supports standing rules and imposes none: yours are notes with
  `metadata.startup` in your overlay's `common/memory/` or a project's memory, which the
  `standing-rules` bundle injects at the start of every session. A preset of your own that carries
  a `[rules]` table is still rendered by `preset-rules`. The machine configuration's
  `reply_language` and `artifact_language` are still recorded by `stayfixed setup`, but nothing
  reads them now: they had a meaning only through the preset's rule about which language each
  audience gets. A language preference you want followed is a standing-rule note of your own too.
- `stayfixed overlay create --template` and `stayfixed setup --overlay create:<owner>/<name>` now
  generate the overlay from `github.com/stayfixed/stayfixed-overlay-template` when you have not
  published your own `<owner>/stayfixed-overlay-template`, so an account that never ran
  `stayfixed overlay publish-template` can still create one; the fallback is looked up on
  github.com whatever host `gh` defaults to. The command names the template it used. When `gh`
  cannot say whether you have your own (an expired token, a network error, no `gh` on the
  machine), it stops with `gh`'s own message and creates nothing, instead of falling back.


## 0.1.1 (2026-09-28)

### Fixed

- The reusable workflow runs when a caller's `uses:` line names a release tag. `0.1.0`'s tag is
  an annotated one, for which the platform reports the tag object rather than the commit, so a
  caller pinned to `check.yml@v0.1.0` fails before any gate runs; pin the commit `stayfixed init`
  writes, or `@v0.1.1`. The gates are now handed the commit the tag names, which is also what an
  upgrade's `[ci] ref` is compared with.


## 0.1.0 (2026-09-28)

### Added

- **Installation.** stayfixed installs as a Claude Code and Codex plugin and as a command-line
  tool (`uv tool install stayfixed`). It needs Python 3.11 or newer on Linux or macOS, and
  imports nothing outside the standard library at runtime, so a hook works wherever `python3`
  does. The plugin ships `hooks/hooks.json`, which both harnesses read with no configuration:
  installing the plugin is enough for the guards to fire and the memory bundles to arrive at
  session start.
- **What a repository can and cannot make stayfixed do.** stayfixed treats a repository as
  untrusted input, since a clone you have not read can commit a `stayfixed.toml`, notes, a
  manifest, a `.claude/settings.json` `env` block and symlinks. Every file stayfixed replaces is
  replaced atomically and keeps its permissions. Every write into a repository walks its path
  one component at a time, refuses a symlink at any component and never leaves the project root,
  so a committed link cannot redirect a write. Your machine configuration is
  `~/.config/stayfixed/config.toml`; neither `STAYFIXED_CONFIG` nor `XDG_CONFIG_HOME` moves it,
  because a repository's settings file could set them, and `--machine` names another file
  explicitly.

  Text a repository chose (file names, note names, configuration keys and values) is never
  printed as found, so it cannot put escape sequences into your terminal or a workflow command
  such as `::error::` into a CI log. A name made of ASCII letters, digits, `.`, `_` and `-` in
  `/`-separated segments prints as itself; any other prints on a summary line as `<unprintable
  name; see --json>`, with the full name escaped in `--json`, and is quoted with control
  characters escaped in a refusal. Refusals over a configuration value name the key and the rule
  in words, never the value. Lists a repository can make arbitrarily long name at most eight
  entries and count the rest (`--json` has them all). A TOML file that does not parse is
  reported as the file and the parser's line and column only. File names that are not UTF-8 are
  handled as their own bytes, and when `git` cannot run or answer, commands say so rather than
  reading the silence as "nothing".

  Exit codes are the same everywhere: `0` success, `1` findings, `2` a refusal or an internal
  error, which a caller must never read as permission. Two exceptions are deliberate: `stayfixed
  test audit-entrypoints` exits `0` with findings, and `stayfixed hook` refuses on an internal
  error only for `PreToolUse`, so a bug in stayfixed never erases a prompt you typed.
- **Machine setup: `stayfixed setup`.** `stayfixed setup --preset recommended` writes your
  personal languages and the preset name into the machine configuration, merges the preset's
  deny rules and your personal values into `~/.claude/settings.json`, registers and installs the
  preset's plugins on every harness that declares a marketplace for them (a missing harness is a
  note, not a failure), and tells you whether `stayfixed` is on `PATH`. `--overlay <path>`
  records a private overlay you already have; `--overlay create:<owner>/<name> --yes` creates
  one on GitHub and records it. Creating a repository is the one outward-facing act `setup`
  performs and the only thing `--yes` confirms.

  Everything `setup` can refuse, it refuses before its first write. An `--overlay` path must be
  a real overlay (both `.claude-plugin/` manifests naming it `stayfixed-overlay[-<owner>]` and
  `stayfixed-overlay-marketplace[-<owner>]`) and must lie outside every checkout of the
  repository `--root` names, linked worktrees included. The machine configuration is merged key
  by key: a value you or an earlier run recorded is never overwritten by a preset default, and
  unknown tables are carried through, but comments do not survive the rewrite. A
  `~/.claude/settings.json` reached through a symlink (stow, chezmoi, a synced home) is refused
  rather than written through; the refusal names the link, and `--settings <path>` writes the
  file where it really is. `--home` and `--machine` point a run at a scratch destination; they
  are not a dry run.

  `stayfixed setup --git-hooks` installs the commit-message hook into this repository's own
  hooks directory, never `core.hooksPath`. An existing hook is kept as
  `prepare-commit-msg.local` and chained to, and `--git-hooks --uninstall` restores it exactly.
- **Starting a project: `stayfixed init`.** `stayfixed init --questions` prints the six values
  `stayfixed init --yes` would take (name, base branch, agents, profile, memory mode, files kept
  out of git), where each came from and the flag that replaces it (`--name`, `--base-branch`,
  `--agent`, `--profile`, `--memory-mode`, `--local`); under `--json` it is a JSON Schema. `init
  --yes` writes the footprint: `stayfixed.toml`, a `CLAUDE.md` pointing at whatever `[paths]
  agents_md` names, an `AGENTS.md` skeleton (or a managed section in an existing one) stating
  your effective budgets, a `.gitignore` block, the documentation skeleton the other commands
  expect, and a CI workflow calling the reusable gate pinned to the commit of the stayfixed
  release that wrote it. Every file is recorded in `.stayfixed/manifest.json`. `--dry-run` shows
  every file first, and a refusal anywhere writes nothing. A file already present, an existing
  `CLAUDE.md` included, is left alone. `init` runs once per repository; after that, use
  `stayfixed upgrade`.

  The base branch comes from `origin/HEAD` only when that names a plain branch under
  `refs/remotes/origin/`, otherwise it is `main`. With no remote, it is the branch checked out.
  A repository whose remote has no `origin/HEAD` (created locally and pushed, or whose only
  remote is `upstream`) gets `main`, never the branch you are on; a `note:` line names
  `--base-branch` and, for `origin`, `git remote set-head origin --auto`.

  A `stayfixed.toml` you wrote by hand is read as the answers, not replaced: `init` adds at most
  a missing `[stayfixed] version`, refuses a file the next command could not load, and names the
  custom gates it configures, whose commands `stayfixed assess` runs unless given `--builtin`.
  The workflow is rendered from the `[ci] ref` your file records, so a file with no ref gets no
  workflow: write a released commit into `[ci] ref` before `init`, or run `stayfixed upgrade`
  afterwards. `--no-ci` writes no workflow and records `[ci] mode = "none"` when this run writes
  the file. When no released tag matches the running version, or the public repository cannot be
  reached, the workflow is skipped with a sentence saying why and which command can still act.

  The first stack profile is `python`. When `[stayfixed] profile` names it (from `--profile`, or
  detected), `init` writes its rules once to `docs/stayfixed/rules/python.md`, the copy the
  project edits; every harness reading `AGENTS.md` gets a pointer and the profile's must-know
  lines, and Claude Code also a path-scoped pointer under `.claude/rules/`. `stayfixed assess`
  runs the profile's eight checks: a lockfile committed or deliberately ignored,
  `requires-python` declared without a cap, one type checker configured, strict pytest markers
  in whichever file pytest reads, marker selection kept out of `addopts`, and Ruff's defaults
  not hidden by a legacy `select`.
- **Keeping the footprint current: `stayfixed upgrade` and `stayfixed uninstall`.** `stayfixed
  upgrade [--dry-run] [--force PATH]` refreshes untouched files after a stayfixed update; files
  you edited, and files stayfixed never wrote, are skipped and named, and `--force` with a path
  overwrites that one. `[stayfixed] version` moves in place, every other byte of
  `stayfixed.toml` kept. When the workflow pins a commit, `[ci] ref`, the pin and the version
  move together or not at all; a `[ci] ref` that is not a commit is left alone. A caller
  workflow you edited is reported `skip_modified`, and `upgrade` then holds the version and
  `[ci] ref` until `--force .github/workflows/stayfixed.yml` or a hand edit brings it in line. A
  project recording a newer stayfixed (a pre-release included) or a version stayfixed cannot
  order is refused. Each run decides first and writes second, so a dry run shows exactly what a
  real one will do; a run stopped by a failed write keeps and records what it did, and the next
  run continues.

  `stayfixed uninstall [--dry-run] [--force PATH]` removes files whose bytes are still
  stayfixed's, takes stayfixed's sections out of files holding other text (shown as `(retired;
  stayfixed's part only, the file stays)`), removes the manifest, and keeps and lists every file
  you edited. It refuses while `.stayfixed/local/` holds notes or edited files, and while the
  manifest records a `stayfixed.toml` that is missing. A `stayfixed.toml` you wrote before
  `init` stays.

  `[artifacts] local` keeps chosen artifacts out of git: they are written under
  `.stayfixed/local/artifacts/`, recorded in `.stayfixed/local/artifacts.json`, refreshed while
  unchanged and never overwritten once edited. It cannot name `config` or `gitignore`. `init`,
  `upgrade` and `uninstall` also refuse, before writing, a `[paths]` layout that aims two
  artifacts at one file (paths differing only in case count as one) and a `[paths]` value
  pointing at an existing file git ignores, such as a `.env`.
- **The `stayfixed.toml` grammar.** The configuration is committed and repository-controlled, so
  it is a closed grammar: unknown sections and keys are refused, and a file that looks valid can
  be refused on the rules below. Each refusal names the key and states the rule.

  `[paths]` values are plain relative paths: segments of letters, digits, `.`, `_` and `-`
  joined by single `/`, none empty, `.` or `..`. A leading `./`, a doubled `//` and a trailing
  `/` are refused, not normalised (except in `ledger.code_roots`, where `"./src"` and `"src/"`
  read as `src`). No value may contain a `.git` component, at any depth or case, or point inside
  `.stayfixed/`; `.github/` and `.gitignore` are unaffected. `[paths] stayfixed` (default
  `docs/stayfixed`) is where stayfixed's own project files go.

  `[project] name` and custom gate names are one lowercase path segment of letters, digits, `.`,
  `_` and `-`, led by a letter or digit. `[project] base_branch`, `release_branch` and `[ci]
  gate_branch` use letters, digits, `.`, `_`, `-` and `/`, led by a letter or digit, and never a
  name git refuses; `release/2.0` is accepted, a name with `+`, `@`, a leading `_` or a
  non-ASCII letter is not. `[ci] gate_branch` defaults to `[project] base_branch`. `[stayfixed]
  preset` is matched exactly, case included, against the shipped presets, and `profile` must be
  a shipped profile. `[stayfixed] state`, `[memory] mode` and `[ci] mode` take only their listed
  values. `[ci] ref` is the full-length commit sha of a released stayfixed tag. Each
  `memory.groups` entry names a subdirectory of `paths.memory` (`""`, `"."` and doubled or
  trailing slashes are refused); a duplicate counts once.

  `[gates]` names the gates a project runs: the built-in `docs`, `bugs`, `plan`, `commit` and
  `trail` by default, and argv commands under `[gates.custom.<name>]`. `[stayfixed] enforced`,
  written by `stayfixed adopt promote`, lists the gates promoted so far; an `installed` project
  whose `enforced` lists only some gates is refused.

  **A `stayfixed.toml` that is a symbolic link is refused by every command**, before anything is
  read through it, and while it is one every agent tool call in that checkout is refused at
  `PreToolUse`. Replace the link with the file.
- **Working memory: `stayfixed memory`.** Notes are Markdown files with frontmatter; `MEMORY.md`
  is a routing index generated from them. Session-start bundles arrive whole: a bundle too large
  for its slot is withheld with a notice rather than cut in half, and `stayfixed memory fit`
  says what fits. In a git worktree the store is linked in, not copied, and every link goes
  through the same contained walk as a file write. `stayfixed memory refs` reports backticked
  repository paths in your notes that no longer exist.

  Notes committed to a repository you cloned reach the model only after `stayfixed memory trust
  --in-repo-memory`, and then inside a marked region that says they are data. When the
  repository changes what it ships, you are asked again, and the harness's link to the store is
  withdrawn until you are. Notes in your own overlay need no approval.

  `stayfixed memory session-context --bundle index` emits `MEMORY.md` on Codex only, since
  Claude Code reads it natively; the harness is read from the environment, so the same command
  answers differently in each. The `recommended` preset's five standing rules (ask at a decision
  fork, work in a worktree by default, keep research sources within two months, read CI after a
  push, split languages by audience) arrive at session start through the `preset-rules` bundle;
  they are never repository content and need no trust record.
- **The private overlay: `stayfixed overlay`.** An overlay is your own repository of standing
  rules, cross-project notes and one record per bound repository. `stayfixed overlay create`
  renders one locally with `--local` (no network call) or on GitHub with `--template`, private
  from the start; neither is a default, so an omitted flag never creates a repository on your
  account. `--template` generates from `<owner>/stayfixed-overlay-template`, which `stayfixed
  overlay publish-template` publishes from your own authenticated checkout. Without `--yes`,
  `publish-template` only reports what it would create, mark and push; a same-named repository
  that is not public is refused rather than flipped, and a `gh` or `git` that cannot answer is
  reported as such, not as "nothing to push".

  `stayfixed overlay init` names the overlay after you in all three plugin manifests so two
  overlays never collide, and installs a commit-time secret scan beside the template's push-time
  one, whose GitHub Actions are pinned at full commit shas and kept current by
  `.github/dependabot.yml`. `stayfixed overlay upgrade` refreshes files you have not edited and
  always names the two files that can grant a capability, permission rules and hook entries,
  whatever their hashes say; run `--dry-run` first to see that list before anything changes. The
  shipped template has deny-only permissions and no hooks. Both commands refuse a `--root` that
  is not an overlay. An overlay may declare the stayfixed it needs as `stayfixed.requires` in
  its plugin manifest, each version component at most nine ASCII digits.
- **Binding a repository: `stayfixed attach` and `stayfixed detach`.** `stayfixed attach --store
  <overlay>/projects/<name>/memory` checks that the overlay recorded this repository's remote
  (`--trust-remote` accepts a different one), prints the permissions and hook entries the
  overlay would add, merges them into `.claude/settings.local.json`, copies your Codex rules
  into `.codex/rules/`, and links your notes into the checkout and every worktree. `--check`
  reports the same and writes nothing. Every refusal `attach` can foresee happens before its
  first write: `--store` must be your overlay's directory for this project, since the overlay
  root comes from your machine configuration and never from the path you type; a new permission
  needs `--yes`; `--machine` is accepted only from an interactive shell; a note group that is
  still a real directory must be moved into the overlay first (`--check` counts them); and a
  `~/.claude` that is a symlink into a dotfiles tree is refused by name, here, in `detach` and
  in the worktree session hook. Make that directory real and let your dotfiles manager adopt the
  files inside it.

  `stayfixed detach` removes exactly what `attach` added, from a ledger under
  `.stayfixed/local/`, and leaves the overlay's binding record so a re-attach does not ask
  again. Run it from the checkout you attached from. The ledger is never an authority: a field
  `attach` could not have written is refused with nothing removed. Directories `attach` created
  are removed only when empty, except the note link directory, and on a repository `stayfixed
  init` set up the `.gitignore` block stays. The overlay's own `hooks/hooks.json` stays empty;
  its hook entries reach a repository only through `attach`'s explicit merge.

  In a repository with `[memory] mode = "overlay"`, a session hears once at its start what
  stands between it and its notes: no overlay recorded, not attached, a different remote, a
  group still a real directory, an overlay requiring a newer stayfixed, or, when nothing else is
  wrong, a branch with no upstream or unpushed commits and uncommitted changes. Each line is
  fixed text naming the command to run; a healthy repository hears nothing. On a compaction the
  unpushed-work check is skipped, so an overlay that becomes unpushed mid-session is reported at
  the next start or resume, or by `stayfixed doctor`.
- **The bug ledger: `stayfixed bugs`.** One Markdown file per bug under the directory
  `stayfixed.toml` names, plus a generated index that is a pure function of those files and
  refuses to delete content it did not write. `stayfixed bugs check` holds every entry to a flat
  frontmatter contract, every high-severity entry to a filled evidence-boundary line, and every
  identifier under your code roots to an existing entry. `stayfixed bugs new` files an entry at
  the next number free across every branch this checkout can see, and warns when it could not
  read that history. `stayfixed bugs renumber` moves an entry and every reference, leaving a
  pointer at the old number. Entries are append-only: with `--base`, which the `bugs` gate
  passes, a deleted ledger is a `ledger-removed` finding and a deleted or renamed entry an
  `entry-removed` finding, and a branch is not blamed for an entry filed after it forked.
- **Documents and plans.** `stayfixed docs check` holds your always-loaded agent document and
  the roadmap's prose to the preset's budgets (a project may lower them, never raise them),
  checks that every local link resolves, and advises, without failing, on broken or repeated
  wiki-links and bracketed bug identifiers in the memory store. `stayfixed docs trail`
  regenerates the design-and-plan listing in your roadmap from the tracked documents and a
  `trail.toml` you own, and will not let a renamed or new document claim it shipped. A
  `trail.toml` theme `pattern` accepts only literal text, `.`, `.*`, `|`, `^`, `$` and `\`
  before punctuation, at most 256 characters, with at most 32 themes; other syntax is refused.
  Inside a git work tree, `docs trail` writes nothing and exits `1` when `git` cannot say which
  documents are ignored, so a local-only document never reaches the committed roadmap.

  `stayfixed plan check` lints the plans a change touches: every path they name exists, no
  verification step presumes its answer, and a mutation's outcome stays an expectation until
  someone has watched it. It lints every plan the merge could alter, across all merge bases. The
  README places stayfixed beside the tools it sits next to and says what each command writes,
  and `docs/methodology/` states the ten principles behind it with dated sources.
- **Hooks and guards.** The hook wrapper finds a Python 3.11 or newer, runs from your project
  root, and refuses with a named `SF_*` token rather than letting a broken guard read as
  permission. Its environment may say where something goes, never which program runs:
  `STAYFIXED_PYTHON_CANDIDATES` is honoured only from an interactive terminal, because a
  committed `env` block applies without a trust prompt; no `python3` inside any checkout of the
  repository is ever run, however `PATH` reached it; and `git` comes from a fixed list of
  absolute paths, never `PATH`. If your only Python 3.11 lives inside your checkout, you will
  get `SF_NO_PY` and a red `wrapper` row in `stayfixed doctor` with the remedy.

  The `PreToolUse` guard (also runnable as `stayfixed guard bg-cleanup`) refuses a backgrounded
  command that would leave an `&` job running past the harness's reap or that begins with
  `sleep`. It advises when a restore line may never be reached, and when a backgrounded command
  ends in `; echo …`, which makes the reported exit code the echo's. `stayfixed commit check`
  fails a pull request whose commit messages carry an AI attribution trailer; `stayfixed commit
  strip`, run by the hook `setup --git-hooks` installs, removes one before the commit exists.
  `stayfixed test hygiene` names the two environment faults that make a red run unattributable,
  and `stayfixed test audit-entrypoints` lists tests that never exercise what they name.

  `stayfixed test attribute --command CMD` decides whether a failing test is your change or your
  environment. It runs the command on the working tree, on `HEAD`'s committed tree and on the
  merge base with your base branch (the last two extracted with `git archive` into a scratch
  directory) and prints the verdict the three exit codes give. It never moves your checkout, but
  the first run does execute your command in your working tree. Put your environment sync in the
  command (`uv sync --locked && uv run pytest …`). With several merge bases it reports the
  attribution as undetermined and runs nothing.
- **Assessing and adopting: `assess`, `gate` and `adopt`.** `stayfixed assess` inventories what
  stands between a repository and enforcement: every configured gate and what no gate runs, such
  as marker comments, tracked `.env` files, committed notes, foreign hooks and workflows, a
  CODEOWNERS file that leaves a workflow or the rest of `.github/` without an owner, commit
  subjects outside the vocabulary, and the profile's checks. The inventory goes to
  `.stayfixed/assessment.json` and `--json`. A gate that could not judge the tree is `could not
  run`, never a finding; when the base is not in the checkout, the summary says why `plan`,
  `commit` and `bugs` could not run and suggests `--base refs/heads/<base_branch>`. `--builtin`
  on `assess`, `gate` and `adopt promote` runs none of the commands `[gates.custom]` names, for
  a clone whose commands you have not agreed to run; without it those commands run, as the
  repository's test suite would.

  The `docs` and `trail` gates judge tracked files, because CI checks out nothing else. When a
  file they read is on disk but untracked, or tracked under a name differing only in case,
  `assess` reports the gate as unable to judge the tree as CI will and `adopt promote` does not
  enforce it. Commit the file, or remove the gate from `[gates] builtin`.

  `stayfixed gate` is the pull-request gate, runnable locally. It reads the base's
  `stayfixed.toml` at an exact commit, runs the configuration check and every configured gate,
  advisory or enforcing, and prints the verdict. A pull request may only tighten: enforce more
  gates, move the state forward, add a gate, drop or re-command one the base does not enforce,
  lower a budget; the preset, profile, harnesses and project name are free, and an upgrade may
  move the version to the running stayfixed and the pin to a released commit. While the base
  enforces any gate, any other change is refused and lands only by a direct push to the base
  branch. A project's first pull request, with no `stayfixed.toml` on the base, is judged by the
  tree's copy. A custom gate runs only the command the base gives it, so one a pull request adds
  or changes is not run until it lands; the base's enforced custom gates run first, no custom
  gate starts once the run has failed, and each command runs in its own process group.

  `stayfixed adopt begin PLAN` starts an adoption with a plan that passes `plan check`.
  `stayfixed adopt promote [GATE…]` enforces the named gates together once they pass, or, with
  no names, every gate that passes now; when all enforce, the project is `installed`. A custom
  gate is promoted only once the base branch has its command.
- **The reusable CI workflow.** Your CI calls stayfixed's gates through one reusable workflow
  pinned at a commit sha; `stayfixed init` writes the caller, `.github/workflows/stayfixed.yml`.
  One `gates` job runs `stayfixed gate` with no resolver and no build backend, in two steps: the
  configuration check and built-in gates, then your `[gates.custom]` gates only if the first
  step passed, so no command your repository wrote runs where the verdict is decided. Python
  starts as `python3 -P -s`, so no module in the checkout and no user-site `.pth` file loads.
  Custom gates run on the bare runner image and install their own toolchain.

  The caller runs only for pull requests into the gate branch, re-runs when one is retargeted,
  reports for that branch's merge queue, and passes the branch as a literal `base:`, so a check
  cannot be won against a looser branch and then retargeted. The base resolves to a commit from
  `refs/remotes/origin/<base>`, so a tag of the same name cannot stand in for it, and the
  stayfixed that runs is checked against the commit your `uses:` line pins before any gate runs.
  The tree under review cannot turn off the gates it faces, but the caller file is one a pull
  request can edit, so protect `.github/` with code-owner review as usual. The `only` input runs
  a chosen few gates (the configuration check always runs), and `timeout-minutes` sets the job
  limit, 15 by default, a whole number from 5 to 60; any other value fails the job, and a job
  that times out is cancelled, never passed.
- **Diagnosing an installation: `stayfixed doctor`.** Sixteen checks over the configuration, the
  hook wrapper, the overlay binding and memory path, every hook entry with its provenance,
  budgets, bundle fit, the overlay's secret scan and the stayfixed version it requires, the note
  store, recent hook failures, `[ci] ref`, and ignored environment variables. It writes and
  repairs nothing; every finding carries the command that fixes it, and `--json` carries all
  sixteen. It exits `1` when any check is red; a `skip` never reaches the exit code. The `files`
  row compares the installed wrapper, hook table and launcher with the hashes the release
  shipped, and says whether a file is modified, absent or unrecorded. The `ci-ref` row checks
  that `[ci] ref` is a released commit and matches the workflow's pin; a missing workflow under
  `[ci] mode = "reusable"` is a warning.

  `doctor --json` is relayed to a model, so no repository-authored text reaches it: hook entries
  are named by position, the hook log is counted and never quoted, and a file it cannot read is
  a warning naming the file, not a red row a clone could force. It reads the workflow only as a
  regular file up to 256 KiB, bounds its one network call at 30 seconds, runs only the hook
  wrapper of its own installation, and trusts the overlay's record over a ledger a clone could
  commit.
- **Skills and agents.** The plugin ships `close-bug` and `memory-sweep`; six procedures an
  agent can be handed (`file-bug`, `sweep-defect-class`, `review-plan-three-lenses`,
  `attribute-failure`, `run-correctness-audit`, `retro-to-guard`); short wrappers for `init`,
  `upgrade`, `uninstall`, `attach`, `setup` and `doctor`; and a read-only `code-navigator`
  agent. Every `stayfixed` invocation in a skill is checked against the real parser. The `init`
  skill asks what `stayfixed init --questions` lets you answer, shows the dry run, writes only
  on an explicit yes, and then starts the adoption (`stayfixed assess`, a plan, and `stayfixed
  adopt begin` on a second explicit yes). Silence, a timeout or an empty answer is never a yes.
  If you decline to run the repository's own gate commands, it uses `--builtin`.
- **Release tooling for this repository.** `stayfixed release` is stayfixed's discipline for its
  own repository, not something it asks of yours. `release check` holds one version across
  `pyproject.toml`, `uv.lock`, the package, both plugin manifests and `CHANGELOG.md`, with
  `--tag` adding the tag and treating a pending changelog fragment as a finding. `release notes
  --version X.Y.Z [--draft]` assembles `CHANGELOG.md` through towncrier. `release hashes`
  records the sha256 of the three files a harness runs in `hooks/hashes.json`, which `release
  check` verifies on every run and `stayfixed doctor` reads on your machine.

### Known limitations

- No moving `v1` alias exists for the reusable workflow during `0.x`, because a `0.x` minor may
  break what came before. Pin the full commit `stayfixed init` writes; `stayfixed doctor`
  reports a `[ci] ref` of `v1` red until the first `1.x` release creates it.
- The `uvx` form of the gate is not shipped yet.
- Windows is not supported: path containment relies on `openat` with `O_NOFOLLOW` and
  `O_DIRECTORY`.
- Ending a custom gate's process group does not end a descendant that left it (a new session or
  a job-control shell's own group) or one stayfixed may not signal (a `sudo` or setuid
  descendant). The base's enforced custom gates share one checkout; only a matrix leg per gate
  separates them.
- A shallow clone cannot be judged by the `plan` and `bugs` gates or by `stayfixed test
  attribute`: use a full-depth checkout.
- Each area's `api.py` is its only supported Python import surface; other names may move without
  notice.
