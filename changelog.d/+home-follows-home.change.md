stayfixed now takes your home directory from `HOME`, as the harness does, at a terminal and
everywhere else: the machine file, `trust.json` and the harness memory link all live under it. A
devcontainer, a home-manager setup or a scratch `HOME` no longer splits stayfixed from the harness,
a hook makes the harness memory link wherever a session's `HOME` is, and `stayfixed doctor`'s
`harness-link` row is gone; its `ignored-env` row now only notes, as information, a `HOME` that
differs from the password database's. A `~/.claude` or `~/.claude/settings.json` that a dotfiles
manager (stow, chezmoi) links elsewhere is written through rather than refused, by `setup` and by
the harness memory link alike.
