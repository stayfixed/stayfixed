`stayfixed doctor`'s `ignored-env` row no longer warns about an `XDG_CONFIG_HOME` that names
`$HOME/.config`, as home-manager exports it, or, with `HOME` unset, the password database home's
`.config`: that is the directory stayfixed reads its machine file under, so nothing is lost. Any other value, and any `STAYFIXED_CONFIG`, still warns, and the
warning now says that no command honours it, not only the hook path.
