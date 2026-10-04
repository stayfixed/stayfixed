# Your stayfixed overlay

This repository is the private half of stayfixed. It holds the things that are yours rather
than any one project's: the standing rules you want every session to start with, the notes
that span projects, and one record per repository binding that repository to this overlay.

**Keep it private.** Nothing here is meant to be published. It may name hosts, accounts and
the paths of environment files; it must never hold a credential, and two scans run to keep it
that way — a pre-commit hook and a workflow on every push.

**It is not stayfixed.** The tool ships separately, as a public plugin and a command-line
program. This repository carries no code: it carries content stayfixed reads, and it depends on
a stayfixed recent enough to understand this layout. That dependency is declared, in
`.claude-plugin/plugin.json` under `stayfixed.requires`, and two things read it:
`stayfixed doctor` reports red when the stayfixed running does not satisfy it, and a session
in a bound repository says so once at its start. Neither harness reads it, so an older
stayfixed is told rather than stopped.

## What is where

`stayfixed overlay create` renders fifteen files here: the fourteen this layout ships, and
`.stayfixed/manifest.json`, which the scaffold engine writes beside them and which the last table
below accounts for. These are the ones that are yours to fill in:

| Path | What it holds |
|---|---|
| `common/memory/` | notes that belong to you rather than to one project, and your personal standing rules: a note carrying `metadata.startup` is injected in full at the start of every session |
| `common/claude/permissions.json` | **your own** `permissions.allow` rules. `stayfixed attach` merges this list into a bound repository's `.claude/settings.local.json`, and nothing else in the file is read — a `deny` list here reaches nothing. It ships empty, because a plugin author may never grant a permission; only you may, on your own instance. |
| `common/claude/hooks.json` | **your own** hook entries, merged into a bound repository the same way. Ships empty for the same reason. |
| `common/codex/common.rules` | the same, for the other harness: one standing-rule file, which `attach` copies into a bound repository's `.codex/rules/`. Ships with a header comment and nothing else. |
| `projects/<name>/` | one directory per bound repository: its record (`project.toml`), and its notes |

And these are the machinery. Leave them alone unless you know why:

| Path | What it holds |
|---|---|
| `hooks/hooks.json` | **this repository's own** hook entries as a plugin — not the same file as `common/claude/hooks.json`, which is what `attach` merges into *other* repositories. Both ship as `{"hooks": {}}`; this one fires here, that one fires there. |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | what makes this repository installable as a Claude Code plugin, and the one-plugin marketplace that publishes it. `stayfixed overlay init` suffixes both names with your account. `version` is **this overlay's** own, not stayfixed's, and starts at `0.0.0` because you have not released it; `stayfixed.requires` is the stayfixed this layout needs, and is what `stayfixed doctor` and a session's first lines read (above). |
| `.codex-plugin/plugin.json` | the same manifest for Codex. |
| `.pre-commit-config.yaml` | the gitleaks hook, pinned at a revision: the commit-time half of "no credential enters this repository". `stayfixed overlay init` installs it. |
| `.github/workflows/scan.yml` | the push-time half, with every action pinned to a commit sha. |
| `.github/dependabot.yml` | what keeps those pins from rotting: a monthly grouped pull request that moves each sha and the version comment beside it. You read it before you merge it. |
| `.gitignore` | env files, in every spelling, so a credential cannot be added by accident. |
| `README.md` | this file. |
| `.stayfixed/manifest.json` | the digest of every file above as `stayfixed overlay create` wrote it. `stayfixed overlay upgrade` compares against it to tell a file you have edited from one you have not, and refreshes only the second kind. It is the fifteenth file, and the one nothing in `templates/overlay/` holds: the scaffold engine writes it at create time. |

Your `.env` files are denied to the agent by `stayfixed setup`, which writes those deny rules into
`~/.claude/settings.json` at machine scope — once, for every project on the machine. They are not
kept here, because a second copy of a security rule is a copy that drifts.

## Making it yours

Run `stayfixed overlay init` once after creating this repository. It suffixes the plugin and
marketplace names with your account so two overlays never collide, and installs the secret
scan. After that, `stayfixed attach` binds a repository to it and `stayfixed overlay upgrade`
refreshes the files you have not edited when a new stayfixed is released.

## Installing it as a plugin

This repository is also a Claude Code plugin, and nothing installs it for you. Two commands do,
with the names `stayfixed overlay init` gave it (`<owner>` is your account and `<name>` this
repository's name):

```bash
claude plugin marketplace add git@github.com:<owner>/<name>.git
claude plugin install stayfixed-overlay-<owner>@stayfixed-overlay-marketplace-<owner>
```

The harness clones it with your own credentials, so the repository stays private.
