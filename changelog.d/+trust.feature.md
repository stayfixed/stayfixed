`stayfixed trust` is one command family for every approval on the machine. `stayfixed trust list`
shows each kind's state in this checkout — approved, lapsed or missing — and the exact command
that approves what is not; `--all` lists every approval recorded on the machine. `stayfixed trust
approve memory` approves the notes committed to this repository, and is asked of you: run where
standard input is not a terminal, as from an agent's shell tool, it refuses with exit 2, writes
nothing and names the command to run yourself. That check slows an agent's bare call and is no
guarantee against one that can open a terminal. `stayfixed trust revoke memory` withdraws the
approval from anywhere, and exits 1 listing what is recorded when nothing matches. Every message
that told you to run `stayfixed memory trust --in-repo-memory` now names `stayfixed trust approve
memory`, and asks for the person at the machine to run it in their own terminal, telling an agent
that reads it not to. `stayfixed doctor`'s `codex-trust` row is now called `codex-hooks`, and its
`attached` row sends a trust record it cannot read to `stayfixed trust list --all`, which says why
and needs no terminal.
