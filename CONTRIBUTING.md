# Contributing to stayfixed

stayfixed's real conventions used to live only inside `docs/plans/`, which meant a first-time
contributor's pull request could be rejected on rules they had no way to read. This file is
those rules.

## The short version

```bash
uv sync                                           # once
uv run pytest -n auto --cov --cov-fail-under=92   # the suite across workers, at CI's floor
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/mutation_oracle.py          # every declared mutation still reddens
uv run python scripts/release.py check            # version discipline
```

All five run in CI on Linux for Python 3.11, 3.12 and 3.13, and on macOS for 3.13 — including
the mutation oracle, which is this project's headline obligation and not an optional extra, and
the coverage floor, which is why `pytest -q` alone will give you a green tree and a red pull
request. CI runs three more steps you can reproduce only from a build (`uv build`, then
`scripts/check_artifacts.py dist` and an installed-wheel render) and one job you cannot
reproduce without a global install of the harness CLI, the plugin-manifest validator; a failure
in either is ours to diagnose, not yours.

## What this project is, and what that costs a change

stayfixed treats **a repository as untrusted input**. A clone can commit a `stayfixed.toml`, a
`MEMORY.md`, a manifest, an `env` block and a tree of symlinks, and all of it reaches the code
before a human has read any of it. Three rules follow, and a change that breaks one will be
sent back however good it looks otherwise.

**The runtime imports only the standard library.** Hooks run under whatever `python3` the
wrapper finds, before any environment exists, so a third-party import works on your machine and
fails inside a hook on somebody else's. `tests/test_import_boundary.py` enforces this on every
supported interpreter. Development dependencies (`pytest`, `ruff`, `mypy`, `towncrier`) are
fine; a runtime one is not.

**Writes go through `fsops`.** `config.paths.contained()` decides whether a configured path
*may* be written — it gives a user-facing refusal and catches a committed symlink — and
`fsops.write_within` / `mkdirs_within` / `remove_within` then do the write through an
`O_NOFOLLOW` walk, so a component that becomes a symlink after the check cannot redirect it.
Do not add a `Path.write_text`, a `mkdir(parents=True)` or an `os.replace` on a string path to
code that puts files into a repository.

**Repository bytes are data.** Anything a repository authored — a note, an index line, a
`memory.groups` entry, a refusal message built out of one — reaches the model only inside
`trust.wrap`'s delimited region, and only after `stayfixed memory trust`. If you find yourself
putting such a string into a `Result.summary`, a `HookResult.context` or an exception message,
wrap it.

The wrap is for the model and escapes no byte, and the same string also reaches a terminal and a
CI runner, where a line break followed by `::error::` is a workflow command and an escape
sequence drives the screen. So a name the repository chose — a file name, a note's name, a
`memory.groups` entry, a TOML key — is printed through `stayfixed.printed`: `printable` where the
command's `--json` carries the name, and `quoted` in a refusal, where the message is the only
place the name appears.

Two narrower rules follow from the same stance. The code cites each by name, and this is where
the name is defined.

### Named caps

A bound comes from one of three places. A limit a project may tune — a document's line or word
count, a note's time to live — is a key under `[budgets]`, which a project may lower below its
preset and never raise. A limit the harness sets — how much of an index it loads, how many
characters of a hook's output it keeps — is a key under `[native_caps]`. Code reads both
through `Config` (`src/stayfixed/config/schema.py`). Every other bound — a subprocess's
wall-clock timeout, how many bytes of a repository-authored file are read, how deep a parser
descends — is a *named cap*: a constant in the code, almost always a module-level one with a
name, and never a configuration key. None of them is a project's to move, because each one
protects the run itself from a hung program, an oversized file or a pathological input, and a
`stayfixed.toml` is repository-authored (principle 5). The one timeout a project does set,
`[gates] custom_timeout_seconds`, bounds the project's own gate command rather than anything
stayfixed runs for itself.

The comment beside a named cap says what it bounds and why the number is what it is. When the number
has to agree with a shipped file, the comment names that file, so a change to either is visibly a
change to both: `doctor`'s `WORKFLOW_MAX_BYTES` names `src/stayfixed/templates/project/stayfixed.yml`,
which it must stay well above, and `NEARLY_FULL` names `hooks/hooks.json`, where a bundle's slot
count is raised. When no such file exists — a timeout on a hung `git`, the longest command
`bg-cleanup` will read — the comment says so rather than inventing one.

### Enumerated writes

A command's section in [docs/cli.md](docs/cli.md) names every path the command writes, in a
paragraph that opens with **Writes** (a read-only command's says "**Writes** nothing"), and the
command writes those paths and no others: a change that makes a command write somewhere new
names the path there in the same commit. `stayfixed hook`, which is internal, is held to the same
rule: its paragraph names what it keeps inside the one directory stayfixed owns under the data
root the harness hands it (`${CLAUDE_PLUGIN_DATA}/stayfixed/`, which `src/stayfixed/hooks/sink.py`
writes), and the one handler that writes outside it.

Removal is held tighter. Every file or directory stayfixed removes is one it names before it looks —
a fixed name in the code, a path its ledger or manifest recorded, one its configuration computes, or
a directory above a file the same run removed — and none is found by listing a directory and
removing what the listing returned, with two exceptions, each inside a directory only stayfixed
writes. The hook sink's sessions are unbounded in number, so it lists its `markers/` directory and
prunes all but the newest `MARKER_SESSIONS_KEPT` sessions. And `stayfixed uninstall` walks
`.stayfixed/local/artifacts/` and removes the directories it finds there that are empty, because
that tree holds nothing but the local artifacts the same run just removed. Both go through `fsops`,
as every removal in a project root does. A temporary directory a command creates for itself and removes whole when
it finishes is outside the rule: nothing but that command ever wrote into it.

## Areas

An area is a subpackage of `src/stayfixed/` that the CLI frame, the hook registry and `doctor`'s
report discover by name — there is no shared registry to edit. One table does name areas, `GROUP_OF` in
`scripts/mutation_oracle.py`, and it is a deliberate exception kept for a reason outside the code
("Tests" gives it): it groups their mutation entries into files, and a new area needs no row there
until its entries outgrow the group they fall into.

Today the discovered ones are `assess`, `attach`, `docs`, `doctor`, `guards`, `hooks`,
`ledger`, `memory`, `overlay`, `project` and `setup`. Three arrived with the install
path: `overlay` renders and upgrades the private overlay, `attach` binds a repository to one and
unbinds it again, and `doctor` reports on what every other area left behind and repairs none
of it. `project` holds the shipped project templates and `init`, the command that writes a
repository's footprint from them, and `assess` runs the gates and the inventory over a
repository as it is, judges a change's `stayfixed.toml` against what its base branch enforces
(`stayfixed gate`), and moves `[stayfixed] state` and `enforced` as a project promotes its gates
(`stayfixed adopt promote`). `assess` publishes no `api.py`: nothing under `src/` or `scripts/`
outside it imports it, and tests reach its modules directly, as they do every area's.
(`config`, `presets`, `profiles`, `release`, `scaffold` and `templates` are subpackages and not
areas, and `harnesses` is a module — area discovery does not find them, because they carry none
of `commands.py`, `hooks.py` and `doctor.py`. `profiles` has a discovery convention of its own,
inside the package: `stayfixed.profiles.hints.hint_modules` lists each profile directory that
ships a `hygiene.py`. `release` still publishes an `api.py`, which holds what an installed
stayfixed reads about its own releases: the tags it pins and the record of the files
a release ships.)

A harness is a value in `harnesses.HARNESSES`, and the hooks core answers through it:
`stayfixed hook` asks `harnesses.detect` which value it runs under and shapes its stdout with
that value's `render`, and the event a handler reads does not say which value that was. That is
all detection decides, and `detect`'s docstring says why. Adding a harness is adding a value — a
positive `detects`, its project-root variable, its `render`, its settings files and its `reach`,
the tier each enforcement surface holds at under it — and nothing that reads those needs an
edit: `doctor` walks the settings files every value names, and the README's table of what each
agent enforces is held equal to every value's `reach` by a test. It is not only a value: what a
new harness still touches outside the registry is listed in the module docstring of
`src/stayfixed/harnesses.py`.

Three of the areas are **delivery**: `overlay`, `attach` and `memory`, the private layer's code
— the overlay, binding a repository to it, and the note store — named in `DELIVERY_AREAS` in
`src/stayfixed/areas.py`. Every other module under `src/stayfixed/`, `cli.py` and the subpackages
that are not areas included, is the **core**, and the rule runs one way: delivery may import the
core, and the core may not import delivery, through an `api.py` or not, at module level or inside
a function, so the private layer can be reworked without touching the core. The core may name
delivery's paths and configuration keys — the `.stayfixed/` namespace and the machine file's keys
are the core's — and may not import delivery's code or call its behaviour except through discovery,
which is how any area plugs into the core: the CLI frame, the hook registry and `doctor`'s report
import an area's `commands.py`, `hooks.py` and `doctor.py` by name and call the `register()` each
publishes, without knowing which area it is, and the bullets below are that contract. One crossing still
exists, and it is pinned in `CORE_TO_DELIVERY` in `tests/test_areas.py` because it is meant to
stay rather than be cut: `stayfixed setup --overlay` creates or records the overlay as the last
step of machine setup, so `setup/run.py` imports the overlay area's `api.py`, inside the two
functions that use it, and those rows stay until the step leaves `setup`. A row is one import
statement and the names it takes, held as a multiset in both directions, so
`test_core_never_imports_delivery` refuses a new crossing, a second statement beside a pinned one,
a pinned statement that takes one more name and a pinned row whose import has gone alike. The rule
reads import statements, so a module named to `importlib.import_module` is invisible to it, and two
rules of their own hold that door. No core module but `areas.py` imports by a string through
`importlib.import_module` or `__import__`, under any alias, except the profile discovery
`DYNAMIC_IMPORTERS` in `tests/test_areas.py` pins with its reason; and the core imports the modules
that can import by a string any other way (`importlib` beyond `importlib.resources`, `pkgutil`,
`runpy`, `zipimport`) only where `MACHINERY_IMPORTERS` pins it, with what each file reaches in them.
Every call of `area_modules` or `area_imports` names `commands`, `hooks` or `doctor` as a literal.
`scripts/` is repository tooling and stays under the `api.py` rule alone. What source cannot show is
when a pardoned statement runs, so `test_in_isolation_no_core_module_loads_a_delivery_area` imports
every core module in a clean interpreter and refuses any delivery module among what it loaded: the
core loads the private layer only when a command asks for it.

- `commands.py` with a `register(groups)` gives the area its CLI group.
- `hooks.py` with a `register() -> list[Handler]` gives it hook handlers. Every import inside a
  handler body, never at module level: `tests/test_areas.py` asserts that discovery in a clean
  interpreter imports neither the configuration layer nor the presets.
- `doctor.py` with a `register() -> Contribution` gives it rows in `stayfixed doctor`'s report: its
  `(name, check)` pairs are asked after the core's own checks, in area-name order, each with the
  report's `Context` and through the same guard, so a check that raises costs its own row and not
  the report. An area that cannot contribute is held to one policy, whatever the cause: a
  `doctor.py` that fails to import, a `register()` that raises or returns anything but a
  `Contribution` of `(name, check)` pairs, and one that contributes a name already in the report — a
  core check's, an earlier area's, or another of its own, since a check's name is unique in the
  report — each puts one red row named after the area where its rows would have been (numbered,
  `<area> (2)`, when the report already has that name), and the rest of the report stands. The
  area's claims (below) go with its rows, so `hook-entries` reads every entry that area put into
  settings files as one nothing records, and goes red too when there is one. A `Contribution` may
  also carry `claims`, which answers `Claims`: the marker ids the area recorded in settings files
  and the commands it still grants there, each under the event and the matcher it grants it under,
  which the core's `hook-entries` row asks with the same `Context`, so an entry the area put there
  is told apart from a repository claiming it did. The record may be repository bytes and the grants
  may not, and an entry is absolved only by an area that both records its id and grants its command
  where the entry sits, never by one area's record and another's grant. `Claims` also carries the
  area's `Wording`, the phrases the row tells its record, its source and their remedies in, so the
  core names no area's files or commands of its own; they are printed verbatim, so they are
  stayfixed's own fixed strings and never built from repository bytes.
  `register()` is called once per report, so anything it creates for its checks — an area that
  reads the note store creates a value that resolves it at most once — is fresh for every report.
  What the core owns and several areas read is on the `Context` instead: `Context.overlay_root`,
  the machine file's `[overlay] root`, is read at most once per report for every area that asks
  the `Context` for it. That is the one answer it caches: code an area reaches through its own
  modules, such as the binding and the note store, resolves the root again.
  `Contribution`, `Context` and `Row` come from `stayfixed.doctor.api`, and, as in a `hooks.py`,
  every import sits inside a function body; `tests/test_areas.py` holds that one.
- `api.py` is the area's import surface. Other areas import from it and from nothing else, and
  its `__all__` must equal exactly what it imports — a test parses the file and checks, and
  `tests/test_areas.py` walks every module under `src/stayfixed/` and `scripts/` and fails on an
  import that reaches past one. The rule holds every package that publishes an `api.py`, an area
  or not (`release` is held to its surface like any area), and every area without one
  (`assess`), none of whose modules anything outside it may import. The list is what consumers
  actually reach for, not what the area finds tidy: a consumer that needs something absent from
  it grows it deliberately, in a commit that says which consumer and why. `cli.py` is the CLI
  frame rather than an area, and its one direct import of `hooks.policy` is named in that test
  rather than skipped silently.
- **`stayfixed.hooks.api` is the one exception, and it is structural rather than drift.** That
  module *defines* the vocabulary two areas share — `EVENTS`, `Policy`, `Decision`, `HookEvent`,
  `HookResult`, `Handler`, `HandlerFn`, `Sink`, `NullSink` and the sink's on-disk layout —
  instead of re-exporting it, because `hooks.dispatch`, `hooks.sink`, `hooks.registry` and every
  area's `hooks.py` import *it*: a name defined in one of those modules and re-exported from
  `api.py` would be an import cycle, not a tidying. So in the one area that ships the common
  vocabulary the rule runs the other way — **a name two areas share is defined in `api.py`** —
  and its `__all__` lists what it defines. No other area may read this as licence: a consumer
  still imports `stayfixed.hooks.api` and never `stayfixed.hooks.dispatch` or `.sink`.
- Every area is a regular package with an `__init__.py`. `pkgutil.iter_modules` does not yield a
  namespace package, so one without it is invisible to all three discovery paths.

The core is language-neutral. A profile under `src/stayfixed/profiles/<name>/` is a directory of
data — `profile.toml` and `rules.md` — and, optionally, a `hygiene.py` whose `HINT` is that
stack's advice after its test runner failed (`stayfixed.profiles.hints` says what a hint
answers, and the command that failed decides which hints speak). That is where one stack's
runner, build artifacts and package manager belong: no module outside a profile's own directory
names a stack — the machinery directly under `profiles/` included — except the pardons
`tests/test_language_neutral.py` lists, each with its reason, and a new mention either moves into
its profile or joins that list with one. None imports a profile's code either: the core finds a
hint by discovery, and that test refuses an import of it without pardon.

Two top-level trees are documents rather than areas. `skills/` holds the Agent Skills this
plugin ships and `agents/` the agent files; [skills/README.md](skills/README.md) is their
contract — a skill body is **action language** and never names a harness tool, a `SKILL.md` is
capped at 80 lines with the detail in `<skill>/references/`, and every `stayfixed …` invocation
in a skill must parse against the real parser or be listed in `NOT_YET_SHIPPED` against the
package that will ship it. `tests/skills/test_skills.py` holds all three, and the change that
ships a command deletes its `NOT_YET_SHIPPED` entry.

## Tests

**Every new assertion ships with the mutation that reddens it, or a sentence saying why none
exists.** This is the project's strongest test convention and the easiest to satisfy vacuously:
write the assertion, break the line of source it is about, watch it fail, put the source back.
Say what you broke, in the test's own comment or in the commit message.

For a guard that is genuinely load-bearing — a containment check, a trust gate, a refusal that
something downstream reads as permission — add it to `mutations/` instead of only describing it,
and the check becomes reproducible:

```bash
uv run python scripts/mutation_oracle.py            # every declared mutation
uv run python scripts/mutation_oracle.py fsops      # only the matching ones
uv run python scripts/mutation_oracle.py --jobs 2   # at most two entries at a time
```

Each entry names one file, one exact line to change, and the tests that must fail when it does.
The keys are `name`, `file`, `before`, `after` and `reddens` — `reddens`, not `tests`, and
`name` is required: the oracle raises `KeyError: 'name'` on an entry without one. `reddens` is an
any-of list: an entry is caught when at least one named test goes red, so name only tests that do,
and give a test that must redden on its own an entry of its own. `before` is an
exact substring of the file and `after` is what replaces it, so an entry whose `before` has
drifted is a finding rather than a skip. The oracle proves `HEAD`: it applies every
mutation to a throwaway worktree, so it never writes your working tree, and it refuses when a
mutated file — **or any test file that a selected entry's `reddens` names** — has uncommitted
changes, because that edit is work the run cannot see. Which is why a mutation run comes
*after* the commit it is about, and why an uncommitted test edit mid-change stops it too.

The oracle proves several entries at once: one worktree per job, each job proving one entry at
a time in a checkout no other job touches, with as many jobs as the process has CPUs up to four
unless `--jobs` says otherwise. So a test that a `reddens` names runs beside other tests in
other processes and must be safe to — no shared path outside `tmp_path`, no wall-clock bound
that load could break. A test that fails under contention fails on the mutated run for a reason
that is not the mutation, and that reads as *caught*. The product's own bounds on `git` are one
such clock, so `tests/conftest.py` lifts every `git_run` bound to a floor of its own, through
the environment variable `gitenv.FLOOR_VARIABLE`, which the product honours only as a raise
(`src/stayfixed/gitenv.py` says why that is safe). A `stayfixed` the suite starts as a separate
process gets the same floor: a spawner that strips the developer's own variables takes
`tests.floor.developer_free_environ()`, which keeps the floor, and one that builds its child's
environment from nothing adds `tests.floor.floor_env()`. A test about a bound running out
removes the variable and passes a small bound of its own, as `tests/test_git_run.py` does. The
floor also hides a bound shrunk below git's own latency, so
that file holds every bound a `git_run` call passes to at least a second, and a bound you add is
a row in its table.

```toml
[[mutation]]
name = "the containment walk stops refusing '..'"
file = "src/stayfixed/fsops.py"
before = "        if part in (_PARENT, _HERE):"
after = "        if part in (_HERE,):"
reddens = ["tests/test_fsops.py::test_a_parent_component_never_leaves_the_root"]
```

The set is one file per group of the tree, and an entry goes in the group file its `file` routes
to: `GROUP_OF` in `scripts/mutation_oracle.py` maps path prefixes to groups, the longest matching
prefix winning and the empty prefix's group taking anything outside `src/stayfixed/`. The groups are
coarse on purpose. The plugin directory holds the version for a reviewer when a file reaches
256 KiB and when the plugin passes 512 files, and the plugin folder is this repository's root, so
every tracked file counts: one file per area would need no table, and would spend about twenty of
those 512 where eight do. That trade is why `GROUP_OF` is a table kept by hand, the exception to
"no shared registry" under "Areas". The size is checked on every pull request
(`tests/test_payload.py`) and the count only at a release, where `scripts/release.py check --tag`
refuses a plugin folder holding more than 512 files: this repository is more than the plugin, so
a pull request may carry it past the count, and a release past it publishes the plugin from a
repository of its own whose root is the plugin ([RELEASING.md](RELEASING.md), section 2, says
why not from a subfolder of this one). `tests/scripts/test_mutation_oracle.py` reddens on an
entry in the wrong file and on a file that reaches its cap, three quarters of the directory's; a
group that does is split by its largest area, which is an edit to `GROUP_OF`.
A comment that cites an entry names the set and the entry's quoted name — `mutations/`'s "the
containment walk stops refusing '..'" — and never its group file, so a regroup leaves the comment
true. That makes a name a reference, and two things hold it to one: the oracle refuses a name
two entries share, and `tests/scripts/test_mutation_oracle.py` resolves every such citation in a
tracked file outside `docs/plans/` against the declared names, so renaming an entry is an edit to
every comment that cites it.

A comment in a group file speaks for the entry below it and for the entries after that which carry
no comment of their own — the file's header speaks for the file and heads no entry — and never by
position for any other: an entry is named, never "the one above". A block split across group files
is stitched by quoted name: each entry that sits in a different group file from the comment that
speaks for it carries a one-line pointer, beginning "In the block led by", that cites the block's
lead entry and says the comment's gist, and the citation test holds that pointer like any other
citation.

The oracle sweeps before it runs. A killed run — `kill -9`, a CI timeout, a cancelled agent —
cannot run its own cleanup, and `git worktree prune` does not collect what it leaves: prune only
drops entries whose directory is gone, and a killed run leaves its directory standing. So the
first thing a run does is drop every `stayfixed-oracle-*` checkout but its own, naming on stderr
what it dropped.

CI runs the whole set in a job of its own, called `oracle`, on one configuration —
`ubuntu-latest` with Python 3.13 — while the tests go on running on all four. The oracle proves
that a mutation reddens a test, which is a property of the code and of the tests rather than of
the platform, and at 657 to 751 s a run it was 76% of the `checks` job and had pushed it past
its fifteen-minute bound. Its own job has its own budget, and `ci.yml` says what that budget
buys in further entries; `test_the_mutation_oracle_has_a_job_of_its_own_with_a_budget_that_fits`
reddens when the set outgrows it, so you find that out here rather than from a cancelled job.

Say plainly what narrowed: your local run is still the full check, and CI's guarantee is now
that the set holds on Linux under 3.13. A mutation that holds there and not on macOS would
reach `main`, where before it would have been caught in the pull request.

Four things are findings: a mutation that *survives*; one whose `before`
line no longer exists, because the assertion and the line it is about have drifted apart; one
whose `before` line appears more than once in the file, because then the entry does not name a
line; and one whose named tests do not pass on a clean tree before the mutation is applied,
because a test that is red, skipped or misspelled cannot prove anything about a guard. A fifth is
not a finding about your entry but about the mutation you chose: one that stops the named tests
from *running* — an `after` that breaks the import, say — is reported as proving nothing, because
pytest's non-zero exit there says only that something went wrong. This is not a coverage
substitute; `--cov` is the breadth measure. It is the set of guards whose load-bearingness has
to be proven rather than merely executed, which is exactly the distinction that let
`fsops.open_within` be covered by twelve tests and contain nothing.

Writing the oracle found two entries that did not hold, which is the argument for having it.

Name a test after the behaviour, not the function:
`test_a_corrupt_record_is_never_overwritten`, not `test_recorded`.

Comment *why*, in the test. Most of this suite's comments name the defect the test exists to
catch, which is what makes a later reader able to tell a load-bearing assertion from decoration.

**The neutrality gate walks every tracked file.** `tests/test_neutral.py` holds the whole tree
to a denylist and three shape rules: no string that identifies the repository these guards were
extracted from, no personal email address, no bare abbreviated commit id, no vendor-prefixed
branch name (`codex/…`, `claude/…`, `cursor/…`). The denylist is stored as digests rather than
as the strings, because a gate that lists what it is hiding publishes it in the very repository
the rule is about — so a hit reads `token be440e8c9338 at 812` and not the word you wrote.

```bash
uv run pytest tests/test_neutral.py
uv run pytest "tests/test_neutral.py::test_no_tracked_file_carries_a_project_identifying_string[docs/cli.md]"
```

The second form is how you ask about one file: the walk is parametrised and the case id is the
file's own path from the repository root.

The number after `at` is the character offset of the first matching window in the lower-cased
file, and the entry's own length is what you read from there: slice that many characters out of
your file at that offset and you are looking at the string the gate refused. Characters and not
bytes, because the sentence before this one is the instruction and an em dash is three bytes:
the gate used to report the byte offset, and on a line in this repository's own house style the
two differed by four. Two entries are four characters long, which is why the offset is printed
at all — a four-character window is not something a contributor can guess. Rewrite the line;
do not add an entry to the exemption.

A test must never read or write the developer's real `~/.config/stayfixed/`, `~/.claude/` or
`~/.codex/`. Pass `--machine` to a command, `machine=` to `resolve`, `home=` where a function
takes one, and use `tmp_path` for everything else. A test must not shell out to `gh`, `claude`,
`codex` or `pre-commit` either: `stayfixed.runner.Runner` is the seam those calls go through, and a
stub records the argv, which is the part of them that can be wrong in a way somebody notices.

## Commits and changelog

Conventional-commit subjects (`feat(memory):`, `fix(scaffold):`, `docs(plans):`), describing
**intent** rather than mechanics. `fix(memory): stop a half-built worktree tree and a refusal
from vanishing` is the house style; `fix: update worktree.py` is not.

User-visible changes need a towncrier fragment in `changelog.d/`, named
`+<slug>.<type>.md` where type is `feature`, `fix` or `change`. The leading `+` is towncrier's
orphan prefix, and it is not decoration: without it towncrier reads the slug as an issue
reference and prints it in parentheses at the end of the bullet, so the release notes everyone
reads would carry a file-name slug that means nothing to them. Write the fragment as a release
note someone outside the project can read — not as a note to yourself about the change.

`uv run python scripts/release.py check` cross-checks the version across `pyproject.toml`,
`uv.lock`, the package, and both plugin manifests. It runs in CI; run it before you push. It is
this repository's own tooling and not a command stayfixed ships, as are its `notes` and `hashes`
beside it ([RELEASING.md](RELEASING.md) says when each runs).

## Plans

Substantial work is planned first, in `docs/plans/YYYY-MM-DD-<slug>.md`, against the extraction
design. That design document is not public yet — it lives in a private repository — so a plan's
references to it cannot be followed from here. You do not need a plan for a bug fix or a
documentation change; open an issue or a pull request and say what you found.

The delivered plans in `docs/plans/` are a record, not a work list. Their `**Interfaces:**`
blocks are kept current and are what later work builds against; their code blocks are
as-planned and may differ from what shipped.

## Security

Do not open a public issue for a containment bypass or a trust-gate bypass. See
[SECURITY.md](SECURITY.md).

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
