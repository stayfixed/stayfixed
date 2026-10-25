What `stayfixed init` writes into a repository is now called its scaffold, in the documentation and
in what the commands print. The `footprint` key of the `--json` output of `stayfixed init`,
`stayfixed upgrade` and `stayfixed uninstall` is renamed `scaffold`, with no alias, and the report
those commands print is headed `scaffold:` where it was `footprint:`; a script reading either
reads the new name.

`stayfixed uninstall` no longer refuses a repository attached to an overlay: it runs
`stayfixed detach` first, which withdraws the overlay's plugin and the allow rules `attach` placed,
and then takes the scaffold back. Attached means `attach`'s ledger and the render `attach` keeps
outside the repository, which `detach` removes, so a ledger a clone committed detaches nothing; a
`note:` line says so, and the dry run says it would. After an `attach` or a `detach` that stopped
part-way, leaving the ledger without the render, `uninstall` refuses it as a file it would not
remove: run `stayfixed detach`, which finishes from the ledger, then `uninstall`. And
`stayfixed commit strip`, which the commit-message hook runs, now leaves a message as it is when
your own Claude Code settings (`~/.claude/settings.json`) set `attribution.commit` to text: what
your commits carry is then the choice you made in the harness. Set empty, it says your commits
carry nothing, and the hook strips a trailer that arrives anyway, as before.
