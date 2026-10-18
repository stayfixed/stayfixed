A stayfixed older than this release cannot read a bug entry carrying `regression` (an unknown
frontmatter key). Once any entry carries one, `stayfixed bugs check` reports it as
`unreadable-entry`, the index as `stale-index` and every entry relating to it as
`dangling-related`, and `stayfixed bugs new`, `bugs index`, `bugs index --check` and
`bugs renumber` exit 1 naming the key. A repository whose entries carry one needs this release,
or a newer one, wherever any of those commands or the `bugs` gate runs, CI included.
