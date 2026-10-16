`stayfixed setup` now asks Claude Code to ask you before an agent's shell runs `stayfixed trust
approve` or its old spelling, by any of the ways it reaches stayfixed — bare, `python -m`,
`python3 -m`, `uvx`, or the absolute path of the `stayfixed` on `PATH` — adding those `ask` rules
to your user settings and recording in the machine configuration file's `[setup] added_rules`
which ones it added; a recorded rule it no longer wants, such as the pair for a `stayfixed` no
longer on `PATH`, is taken back, and `[setup] ask_rules = false` takes back every recorded one and
never a rule you wrote. A rule you delete by hand comes back on the next `setup`; the switch is
the way to drop them. Note that
`claude -p` treats an `ask` rule as a refusal. `stayfixed setup --approval-boundary` also denies
writes to the trust record's directory (`Edit(//<that directory>/**)`) and prints the sandbox
settings that rule needs; it never sets them. `stayfixed doctor` has a nineteenth row,
`approval-boundary`, which reads this project's effective Claude Code settings: red once the
machine holds an approval and the sandbox is off for the project or confines no file
(`sandbox.filesystem.disabled`), the deny rules setup writes are not there byte for byte, or a
setting widens them (a `sandbox.excludedCommands` in your own user settings, admin-required or not,
or in a repository's, or any `allowWrite`, `Edit` allow or `additionalDirectories` entry not shown,
as text, to be a literal path outside the project, the record's directory and the sandbox's own
`claude-<digits>` temporary directory, and strictly inside no other such entry, managed settings'
included), a warning before that, a warning while the sandbox or a deny rule is there only through
a repository's settings file, which a later commit can remove, while managed settings exclude
commands from the sandbox, or while managed settings do not make the sandbox admin-required and
refuse to start without it (`sandbox.failIfUnavailable = true`), and green only then. A `~/` entry
counts as safe only under every home it may mean, `HOME` included, and a user settings directory
`CLAUDE_CONFIG_DIR` names besides `~/.claude` may only make the answer worse: alone it is never
better than a warning, inside the project or another checkout of its repository, case-folded on
macOS, it is never read, and under neither the home nor the project it is never looked at, since
it may lie under a network mount, the row naming the `setup --approval-boundary --settings` run
that writes the rules there; its value is printed cut to its first 120 characters and its
length. The project's and your settings files are read past a leading byte-order mark, as Claude
Code reads them, and a setting of the wrong shape — a sandbox switch that is not `true` or
`false`, a `sandbox` that is not an object, a widening key that is not a list of strings — is a
gap named by its file and key, never read as absent. A project
whose `[stayfixed] agents` does not list `claude` and which carries no Claude Code settings file is
skipped only while the trust record holds no approval.
