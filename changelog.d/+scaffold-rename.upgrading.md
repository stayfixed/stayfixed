What `stayfixed init` writes into a repository is now called its scaffold, in the documentation and
in what the commands print. The `footprint` key of the `--json` output of `stayfixed init`,
`stayfixed upgrade` and `stayfixed uninstall` is renamed `scaffold`, with no alias, and the report
those commands print is headed `scaffold:` where it was `footprint:`; a script reading either
reads the new name.
