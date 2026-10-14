The `stayfixed release` commands are gone from the installed CLI: they only ever checked this
repository's own release, and now live in its `scripts/release.py`. Nothing a project runs used
them.
