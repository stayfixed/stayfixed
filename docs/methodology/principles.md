# Principles

Ten principles, numbered so the README can point at one. Each has a statement, what stayfixed
does about it today, its sources, and a **Backing** line whose vocabulary
[README.md](README.md) defines. Citations resolve to [sources.md](sources.md).

## 1. A bug is a file, and its index is a rendering

**Statement.** A defect is recorded as one file with a stable identifier, a status from a
closed vocabulary, and — for the severe ones — a line saying what the evidence does *not*
establish. The index over those files is generated, refuses to overwrite content it did not
write, and is never the place a fact is entered.

**What stayfixed does.** `bugs new` allocates the next identifier across every ref, `bugs
index` renders the index as a pure function of the entries, `bugs check` sweeps the code
roots for identifiers with no entry behind them and entries whose evidence boundary is the
template's placeholder, and `bugs renumber` moves an entry and rewrites every mention, leaving a
`void` entry at the old number. Against the base a change is judged on, `bugs check` reports an
entry the change forked with and deleted: an identifier once allocated keeps its file. The
identifier grammar is one definition, read from the project's configuration.

**Why a file.** An issue tracker records a conversation; a file records a claim a later
session can falsify. The "what this evidence does not establish" line is the part that
makes an entry a hypothesis rather than a diagnosis — the reporter says where their
knowledge ends, so the next reader starts there instead of inheriting the frame.

**Backing:** thin. The falsifiability framing is this project's own; no independent source
claims that a ledger of files beats a tracker for agent-driven work, and a comparison over
projects that used both would change this label. What is sourced is the platform side: a
generated index resolved by regeneration is the same move a hashed manifest makes for
scaffolded files [S11], and the skills that teach an agent to read an entry are ordinary
skills in the format every harness reads [S4] [S14].

## 2. An assertion nobody has watched fail advertises coverage it may not have

**Statement.** A new or preserved assertion ships with the mutation that reddens it, or with
a sentence saying why no mutation exists. A test that cannot fail is not a test; a test that
fails for a reason other than the one it names proves nothing about that reason.

**What stayfixed does.** `mutations/` declares, for each load-bearing guard, the one line
to change and the tests that must go red when it does; `scripts/mutation_oracle.py` applies
each, runs only the named tests, and fails on a survivor, on a `before` line that no longer
exists, and on a named test that does not pass on the clean tree first. CI runs the whole
set. The convention is stated in `CONTRIBUTING.md`, and the plans that built this tool
record each mutation's outcome in the commit that ran it.

**Why.** Generated tests that lack strong assertions or restate the implementation are a
measured phenomenon [S23], and an implementation and its tests can be wrong together while
staying mutually consistent [S24]. On the evaluation side, a behaviour that passes once is
not a behaviour that passes [S20], and run-to-run inconsistency of agent evaluations has
been quantified [S21]: an assertion has to be watched failing under the change it names,
not argued about.

**Backing:** sourced. The mechanism (a declared mutation set run in CI) is this project's;
the claim it serves is the four sources'.

## 3. A memory index is a routing table, not a summary

**Statement.** A note carries a rule, one line of why, how to apply it, and a bare pointer
to where the evidence lives. The index carries one line per note — a trigger and what the
note settles — and is rendered from those lines, never edited by hand. An entry that can be
quoted gets quoted instead of opened, so an entry must not read as a finished claim.

**What stayfixed does.** Each note's `index:` line is the routing line; `memory index`
renders `MEMORY.md` from them under a declared section order and harvests back any line a
second writer appended, so the harness's own memory writer and stayfixed share one directory
without either rewriting the other's keys. `memory inventory` reports each note's size and
whether its line is curated, harvested or provisional; `memory refs` checks that every path a
note names still exists, and reports the link graph beside it as advice.

**Why.** The harness loads the first 200 lines or 25 KB of the index into every session
[S5], so the index is a budget and every word in it is paid on every turn [S17]. There is no
standard for coding-agent memory to adopt instead [S16]; the published shapes closest to
this one keep linked notes with generated descriptions [S18] or a separate indexed store
[S19], and the second is exactly the second source of truth this design refuses.

**Backing:** sourced. The label is about the constraint this principle answers — the budget
every session pays [S5] [S17] and the absence of a standard to adopt instead [S16] — and that
constraint is the sources'. The rule-plus-pointer form built on top of it is this project's
practice, *thin* on its own, and would be *measured* once a before/after over sessions
exists; the label follows the constraint, because the constraint is what makes a routing
table rather than a summary the only affordable shape.

## 4. Standing rules arrive whole; everything else is routed

**Statement.** A small set of rules holds for a whole session whatever it turns out to be
about. Those cannot be routed, because there is no moment at which anyone would look one up:
by the time one is needed, the session has already acted without it. They are injected in full
at session start, ranked, and never truncated. Everything else is a pointer the index routes
to.

**What stayfixed does.** Which rules those are is each person's to write, and stayfixed ships
none: a standing rule is a note with `metadata.startup` in the overlay's `common/memory/` or a
project's memory, and the `recommended` preset carries no rule of its own. `memory
session-context` renders two bundles — standing rules and volatile notes — each across
numbered parts sized to the platform's per-entry cap, and `memory fit` reports a bundle that
does not fit its slots.
Standing rules are flagged when they outgrow their budget and still delivered, because a
standing rule that does not arrive is a standing rule that gets broken; volatile notes
degrade to descriptions instead.

**Why.** Each hook's output is capped at 10,000 characters and replaced by a preview and a
file path above that [S3], and this project measured its own single-script injection at
about 17 KB on 2026-09-05 — so "every standing rule in full" was a promise the previous
harness did not keep, and the reader got a 2 KB preview. One entry per bundle, each clamped,
is what makes the promise true.

**Backing:** measured. The cap is sourced [S3]; the failure it caused was measured on one
harness on one day, and the bundle design follows from that measurement.

## 5. A repository is untrusted input

**Statement.** A clone you have not read can commit a configuration file, a memory index, a
manifest, a settings file with an environment block, and a tree of symlinks — and every one
of them reaches the tooling before a human does. Repository-controlled values may choose
names, paths inside the project and document layout; they may never set standing rules,
widen permissions, install hooks, pick a write path outside the root, or select their own
enforcement level.

**What stayfixed does.** Notes that live in the repository reach the model only after
`memory trust --in-repo-memory` recorded a hash of the store, and then inside a delimited
region with a per-invocation nonce that says "this is data". Every write goes through a
path walk that refuses a symlink at any component and refuses to leave the project root.
Budgets are clamped to plugin-owned ceilings, so a project cannot raise its own payload
cap. The machine-level configuration's location is not selectable by an environment
variable, because a committed settings file can set one [S3].

**Why.** Prompt injection through content the model reads and supply-chain compromise
through configuration it trusts are the first and one of the top entries of the current
OWASP list for LLM applications [S22]; Codex hashes a plugin's hooks before trusting them
for the same reason [S7].

**Backing:** sourced. The threat classes are the sources'; the containment mechanism is
this project's and is held by its own containment tests and mutation entries.

## 6. Fail closed only where the platform blocks, and say so where it cannot

**Statement.** A guard for an action with a high cost of error refuses when it cannot
decide; a context-injecting handler stays silent. Fail-closed is expressible only where the
platform blocks on a non-zero exit — before a tool call — and never on session start, where
exit codes are ignored, or on prompt submission, where a blocking exit erases the prompt.
A guard that cannot fail closed must say so rather than pretend.

**What stayfixed does today.** Every handler declares its policy, `open` or `closed`; the
guards over a shell call, a commit message and a test run are closed, the memory handlers
open. Not this, yet: the guarantee belongs in a shell wrapper rather than in Python, because
a Python process cannot fail closed about its own absence — the wrapper is designed to probe
for an interpreter at or above the floor, refuse with the blocking exit when none is found,
and map every other exit code to it with a printed reason. It ships with the hooks file that
calls it, in the `hooks-core` package; neither is in the tree today.

**Why.** The exit-code semantics differ per event and are documented per event [S3]; Codex
runs some hooks asynchronously and an asynchronous hook cannot block [S7]. A hook whose
binary is missing exits 127, which the harness treats as a non-blocking error — so the
guard silently becomes permission, which is why the wrapper is specified at all.

**Backing:** sourced. The per-event semantics are the platforms' [S3] [S7], and that is the
claim the label is about: where fail-closed is expressible at all is a platform fact, not a
finding. This project's spikes measured the fail-open matrix and kept it as a test, but they
confirm the documented semantics rather than establish them — unlike principle 4, where the
measurement *is* the claim and the label is *measured* for that reason.

## 7. Enforcement is earned, not declared

**Statement.** Rules written into a repository that historically does not follow them do
not take. A gate should run advisory until the repository has been brought to the point
where it would pass, and only then enforce — and the decision to enforce should be read from
the base branch, never from the change under review.

**What stayfixed does today.** The state machine ships per gate. `stayfixed assess` inventories
what stands between a repository and enforcement, and `stayfixed adopt promote` enforces every
gate that passes now and names the rest, or enforces the gates it is given only if all of them
pass; its first promotion is what starts the adoption. The gate a pull request faces
reads the base branch's configuration and admits only a change that tightens it, under the
repository settings `docs/cli.md` names. What it does not do yet is hold the line inside a gate
— fail new findings while grandfathering old ones — which current linters do [S33] and which is
recorded as the next step.

**Why.** The alternative in the field is a constitution declared before the first commit
[S11] or a process layer that tells the agent how to work without asking whether the
repository does [S10]. Neither has a way to introduce a rule into a codebase that violates
it two hundred times, which is where every existing project starts.

**Backing:** thin. This is a design argument from experience with one repository's adoption of
its own rules. Nothing external states it, and no repository has yet adopted through `init` and
had its advisory period's findings counted. The label changes when one has.

## 8. A personal overlay is a versioned plugin, not a dotfiles sync

**Statement.** The rules and memory that belong to a person rather than a project should
travel as a plugin that declares a dependency on the public one and carries its own upgrade
manifest — installable on a fresh machine by the same command that installs everything
else, private by construction, and never a prerequisite for the public tool to be useful.

**What stayfixed does today.** The public plugin runs with `memory.mode = "local-only"` and
no overlay; `overlay` mode, `attach` and the template repository are later work packages.
The memory store's resolution already honours an overlay symlink only when its target lies
inside a recorded overlay root that binds this repository's remote.

**Why.** A plugin with a declared dependency and a manifest is now a specified, portable
unit [S15]; one plugin root serves both harnesses, because each reads its own manifest from
it [S1] [S8] and Codex exports that root under both names [S9]; a private marketplace can
serve one [S6]; and the plugin's data directory survives updates while the plugin root does
not [S2], which is the distinction the overlay's upgrade path is built on. The overlay's own
CI scans every push for secrets rather than relying on the platform's scanning, whose
coverage of a private repository depends on the plan [S32] and moved as recently as this
summer [S26].

**Backing:** sourced. The mechanism is the sources'; the claim that it beats a dotfiles
sync is experience with three projects on one machine and would be *thin* on its own — the
label follows the mechanism, because the mechanism is what this principle constrains.

## 9. One version string, and immutable pins

**Statement.** The version lives in one place per artifact and every other place is
checked against it, because a stale version pins update delivery: shipped commits never
reach installed users. A project's reference to a shared workflow is a full-length commit
SHA written by the tool that installed it and bumped by the tool that upgrades it; a
floating alias is a documented opt-in.

**What stayfixed does.** Its repository's release check, `scripts/release.py check`,
cross-checks the version across `pyproject.toml`, the lockfile, the package, both plugin
manifests and `CHANGELOG.md`; the marketplace entries carry no version because the plugin's
own overrides it silently [S6]. Changelog entries are fragments assembled at release [S12].
The CLI installs from a git tag with no resolver at hook time [S13].

**Why.** `plugin.json`'s `version` is what update delivery reads [S2]; a full-length SHA is
the only immutable reference to a reusable workflow [S25].

**Backing:** sourced.

## 10. Sources age in months, and durable artifacts share one language

**Statement.** When researching tooling or the state of a fast-moving field, a source older
than two months is background, cited as such and confirmed by a fresh one before anything
is built on it. And everything durable — documents, comments, commits, pull requests — is
written in one language, whatever language the conversation is in, because artifacts are
read by tools, by later contributors and by a possible public extraction.

**What stayfixed does.** The freshness rule is the row grammar of [sources.md](sources.md)
and a test over it. The language half is a person's own standing rule, a note with
`metadata.startup`, and stayfixed enforces nothing about it: the machine configuration's
`artifact_language` and `reply_language` are recorded by `stayfixed setup` and read by nothing
in this release. The four "harness" sources in the [README](README.md) are the freshness rule's
own worked example: the term moved from a company blog [S27] to a discipline [S28] to an
open-sourced platform [S30] and a research framing [S29] in nine months, with the pattern
essay it all descends from [S31] published eleven months before the earliest of the four
and still the clearest statement of why simple composable pieces beat a framework.

**Backing:** thin. Both are working rules stated by the person whose harness this is, kept
because each was adopted after a concrete cost — a citation to a tool that had changed its
storage engine; a history with two languages in it — and neither has evidence beyond that.
A count of citations that turned out stale at two, four and six months would change the
first; the second is a preference and will stay one.
