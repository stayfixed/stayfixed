`stayfixed overlay upgrade` no longer lists a file a release no longer ships as `unchanged` once
it is gone. After an upgrade removed `skills/attach/SKILL.md` and `common/rules/README.md`, every
later run named both, and `common/memory/README.md`, among the unchanged files and counted them,
so the summary counted more unchanged files than the overlay holds; a fresh overlay that never had
them did the same on its first run. A retired file that is gone and that `.stayfixed/manifest.json`
does not record is now left out of the report and its count.
