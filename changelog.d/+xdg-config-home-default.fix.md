`stayfixed doctor`'s `ignored-env` row no longer warns about an `XDG_CONFIG_HOME` that names
`$HOME/.config`, as home-manager exports it, or, with `HOME` unset, the password database home's
`.config`: that is the directory stayfixed reads its machine file under, so nothing is lost. Any
other value, and any `STAYFIXED_CONFIG`, is said as information, which changes no status, and the
row now says that no command honours it, not only the hook path.
