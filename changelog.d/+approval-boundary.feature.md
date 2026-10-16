`stayfixed setup` now asks Claude Code to ask you before an agent's shell runs `stayfixed trust
approve` or its old spelling, by any of the ways it reaches stayfixed — bare, `python -m`,
`python3 -m`, `uvx`, or the absolute path setup runs as — adding those `ask` rules to your user
settings and recording in the machine configuration file's `[setup] added_rules` which ones it
added; `[setup] ask_rules = false` takes back exactly those and never a rule you wrote. Note that
`claude -p` treats an `ask` rule as a refusal. `stayfixed setup --approval-boundary` also denies
writes to the trust record's directory (`Edit(//<that directory>/**)`) and prints the sandbox
settings that rule needs; it never sets them. `stayfixed doctor` has a nineteenth row,
`approval-boundary`, which reads this project's effective Claude Code settings: red once the
machine holds an approval and the sandbox is off for the project, the deny rules setup writes are
not there byte for byte, or a setting widens them (a repository's `sandbox.excludedCommands`, or
any `allowWrite`, `Edit` allow or `additionalDirectories` entry not shown, as text, to be a literal
path outside the project and the record's directory), a warning before that, a warning while a
repository's settings could still turn the sandbox off, and green only when managed settings make
it admin-required. It reads `CLAUDE_CONFIG_DIR` only when run at a terminal, and says when it
passed one over.
