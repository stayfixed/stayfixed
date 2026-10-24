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
   cross-project notes and per-project bindings. `setup` is what makes and records it, through
   `--overlay`, and there are three ways in:
   - **They already have one**: `stayfixed setup --preset recommended --overlay /path/to/it`.
     The path is validated against the overlay's identity record, `stayfixed-overlay.toml`, and
     refused if it is inside, around or equal to the directory `setup` runs in, if it is in
     another checkout of that directory's repository, or if it is inside a checkout of any other
     repository. An overlay made before the record shipped is refused with the file and its keys
     named: relay that, since the user adds the record by hand.
   - **They want one on this machine only for now**: `stayfixed setup --preset recommended
     --overlay /path/that/does/not/exist` renders the shipped template there with no network
     call, makes it a git repository, installs the secret scan and records it. Relay the note on
     giving it a remote and filling in `owner` and `name` in its record.
   - **They want one on GitHub**: `stayfixed setup --preset recommended --overlay create:<owner>/stayfixed-private --yes`
     creates it on their GitHub account, from their own published template or the publisher's
     public one, names its record after them and records it in one step. Creating a repository
     on their account needs their word first, so **ask before running it** — `--yes` is that
     consent and nothing about the overlay happens unless `--overlay` is named at all.

   Relay whether the secret scan installed.
5. After a stayfixed release, `stayfixed overlay upgrade --root PATH --dry-run` says what would
   change. Relay the report, and relay the `ASK FIRST` list separately: those two files can
   grant a capability, so the user agrees to them by name before the run without `--dry-run`.
6. `stayfixed setup --approval-boundary` prints the deny rule and the sandbox settings that keep
   an agent's shell out of the trust record's directory, and writes nothing. Relay its line for
   the user to set; never write a `sandbox` key or that deny rule yourself. With the sandbox on,
   the agent's shell cannot write the machine directory at all: when `setup` or `trust revoke`
   says a person must run it in their own terminal, outside the agent's sandbox,
   relay that sentence and stop — never retry it outside the sandbox yourself.
7. **The preset's plugins install on Claude Code only.** Codex has no verified non-interactive
   marketplace source for them, so `setup` reports the gap as a note rather than attempting an
   unverified install. Relay that note and tell the user to add those plugins by hand on Codex;
   do not present the run as having configured both harnesses.
8. `--home` and `--machine` point the `--preset` run at a scratch destination instead of the
   real home directory and `~/.config/stayfixed/config.toml`. They are **not** a dry run — the
   same files are written, just elsewhere — and `--git-hooks` ignores both. Do not offer them
   as a way to preview what `setup` would do; there is no such mode.
