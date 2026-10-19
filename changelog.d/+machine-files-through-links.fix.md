A `~/.config/stayfixed/config.toml` or `~/.config/stayfixed/trust.json` that a dotfiles manager
(stow, chezmoi) links elsewhere is now written through: `stayfixed setup` and every approval,
refresh and revocation write the file the link leads to, and the link stays, and a write that fails
there names the directory the link leads to. Before, the next write put a regular file in the
link's place, so the dotfiles copy kept the old settings and approvals.
