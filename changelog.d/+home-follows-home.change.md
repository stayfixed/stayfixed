stayfixed now takes your home directory from `HOME`, as the harness does, at a terminal and
everywhere else: the machine file and `trust.json` live under it, where 0.3.1 read `HOME` only at a
terminal and the password database's home everywhere else. A devcontainer, a home-manager setup or
a scratch `HOME` no longer splits stayfixed from the harness, and `stayfixed doctor`'s
`harness-link` row is gone; its `ignored-env` row now only notes, as information, a `HOME` that
differs from the password database's. A `~/.claude` or `~/.claude/settings.json` that a dotfiles
manager (stow, chezmoi) links elsewhere is written through by `setup` rather than refused.
