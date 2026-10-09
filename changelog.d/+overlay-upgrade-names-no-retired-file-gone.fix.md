`stayfixed overlay upgrade` no longer lists a file a release no longer ships as `unchanged` once
it is gone. Every run named `common/memory/README.md`, which 0.2.0 retired, among the unchanged
files and counted it in an overlay that had deleted it or never had it, a freshly created one
included, so the summary counted one more unchanged file than the overlay holds. A retired file
that is gone and that `.stayfixed/manifest.json` does not record is now left out of the report
and its count, the two this release retires (`skills/attach/SKILL.md` and
`common/rules/README.md`) among them.
