# Security policy

stayfixed has an explicit threat model: **a repository is untrusted input.** A clone can commit
a `stayfixed.toml`, a `.claude/settings.json` `env` block, a `MEMORY.md`, a `.stayfixed/manifest.json`
and a tree of symlinks, and every one of those reaches stayfixed before any human has read it.
So a bug that lets repository-authored bytes reach the model as instructions, or lets a write
land outside the project root, is a security bug here even where it would be a nuisance
elsewhere.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting:**
<https://github.com/stayfixed/stayfixed/security/advisories/new>

That opens a private advisory only the maintainers can see. Please do **not** open a public
issue for anything in the list below — the public issue tracker discloses a containment bypass
to every user at the moment it is reported, including the ones who have not upgraded.

If private reporting is unavailable to you for any reason, say so in a public issue **without
the details** ("I have a security report and cannot use private reporting") and a maintainer
will arrange another channel.

### What to include

A proof of concept is worth more than a description. The most useful shape is a repository — or
a script that builds one — plus the command you ran and what you observed. Say which operating
system and Python version, because two of the containment paths behave differently on Linux and
macOS by design.

### What to expect

This is a small project with a single maintainer, so please read these as intentions rather
than guarantees:

| | |
|---|---|
| First response | within 7 days |
| Assessment and a plan | within 14 days |
| Fix released | as soon as it is ready; you will be told the date |
| Credit | in the advisory and the changelog, unless you ask otherwise |

## What counts

In scope, and treated as security rather than as an ordinary bug:

- **Containment.** Any write, or any read that feeds a write, that lands outside the project
  root or outside the machine owner's own store — through `..`, an absolute path, a symlink at
  any component, a TOCTOU window, or a configured value that reaches no guard.
- **The trust gate.** Any way repository-authored text reaches the model without
  `stayfixed memory trust` having been given, or reaches it outside `trust.wrap`'s delimited
  region — including through a channel stayfixed hands to the harness, such as a symlink into
  the harness's own project-memory directory.
- **Marker forgery.** Any note, index entry or configuration value that can close or forge the
  repository-data region it is wrapped in.
- **The machine anchors.** Any way a repository can choose which machine configuration file,
  overlay root or `trust.json` stayfixed reads — for example through an environment variable a
  committed settings file can set, `HOME` among them.
- **Destruction.** Any way a repository, or an ordinary mistake, silently destroys the machine
  owner's own state: the trust record, a hand-edited file, or a hook configuration stayfixed did
  not write.

Out of scope:

- Anything that requires the attacker to already be able to write to the machine owner's home
  directory or to `PATH`. stayfixed runs the `git` on your `PATH` by design.
- A repository being able to make stayfixed **refuse** — suppressing memory, failing a hook
  closed. Undesirable, and an ordinary bug, but not a vulnerability: the whole design fails
  closed on purpose.
- Findings in a dependency that stayfixed does not reach; it has no runtime dependencies.
- A variable the dynamic loader reads (`LD_PRELOAD` and `LD_LIBRARY_PATH` on Linux,
  `DYLD_INSERT_LIBRARIES` and `DYLD_LIBRARY_PATH` on macOS) reaching a hook, from a committed `env`
  block or anywhere else. The loader acts on the hook wrapper's own shell before its first line, so
  no wrapper can refuse it. On macOS the wrapper's `/bin/sh` is SIP-protected and drops `DYLD_*`
  before anything below it starts; a shebang that loses that protection is in scope.

## Supported versions

stayfixed is pre-1.0. Only the latest released version is supported; fixes land on `main` and in
the next release rather than being backported.
