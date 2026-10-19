---
name: setup
description: Configure the machine for stayfixed — the preset, the personal parameters, and the per-repository git hook. Use on a new computer, when the user asks to install stayfixed's defaults, or when a commit-message hook is wanted.
---

# Machine setup

1. Run `stayfixed setup --preset recommended` and relay what it writes to the machine
   configuration file and which plugins the preset enables. It asks nothing;
   `--yes` exists only to confirm creating an overlay repository (step 4).
2. For the commit-message hook, run `stayfixed setup --git-hooks` inside the repository and
   relay what it installed and what existing hook it kept and chained to;
   `stayfixed setup --git-hooks --uninstall` restores it.
3. A language preference the user wants followed is a personal standing rule, a note with
   `metadata.startup` in the overlay; do not guess it.
4. Offer the private overlay — one repository holding the user's own standing rules,
   cross-project notes and per-project bindings. `setup` is what records it, through
   `--overlay`, and there are two ways in:
   - **They already have one**: `stayfixed setup --preset recommended --overlay /path/to/it`.
     The path is validated against the overlay's own layout, and refused if it is inside,
     around or equal to the directory `setup` runs in, if it is in another checkout of that
     directory's repository, or if it is inside a checkout of any other repository.
   - **They do not**: `stayfixed setup --preset recommended --overlay create:<owner>/stayfixed-private --yes`
     creates it on their GitHub account and records it in one step. Creating a repository on
     their account needs their word first, so **ask before running it** — `--yes` is that
     consent and nothing about the overlay happens unless `--overlay` is named at all.

   The lower-level path still exists and is for two cases only — an overlay rendered without
   recording it, or one somebody else created that needs renaming:
   `stayfixed overlay create --owner NAME --local` renders one on this machine with no network
   call, `stayfixed overlay create --owner NAME --name stayfixed-private --template` creates it on
   GitHub from their own published template, or from the publisher's public one when they have
   none, and `stayfixed overlay init --owner NAME --root PATH` makes it theirs. Relay what
   `init` renamed and whether the secret scan installed.
5. After a stayfixed release, `stayfixed overlay upgrade --root PATH --dry-run` says what would
   change. Relay the report, and relay the `ASK FIRST` list separately: those two files can
   grant a capability, so the user agrees to them by name before the run without `--dry-run`.
6. `stayfixed setup --approval-boundary` prints the deny rule and the sandbox settings that keep
   an agent's shell out of the trust record's directory, and writes nothing. Relay its line for
   the user to set; never write a `sandbox` key or that deny rule yourself. With the sandbox on,
   the agent's shell cannot write the machine directory at all: when `setup`, `trust revoke` or
   `memory index` says a person must run it in their own terminal, outside the agent's sandbox,
   relay that sentence and stop — never retry it outside the sandbox yourself.
7. **The preset's plugins install on Claude Code only.** Codex has no verified non-interactive
   marketplace source for them, so `setup` reports the gap as a note rather than attempting an
   unverified install. Relay that note and tell the user to add those plugins by hand on Codex;
   do not present the run as having configured both harnesses.
8. `--home` and `--machine` point the `--preset` run at a scratch destination instead of the
   real home directory and `~/.config/stayfixed/config.toml`. They are **not** a dry run — the
   same files are written, just elsewhere — and `--git-hooks` ignores both. Do not offer them
   as a way to preview what `setup` would do; there is no such mode.
