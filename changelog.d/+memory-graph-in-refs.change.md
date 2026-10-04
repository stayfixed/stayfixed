`stayfixed docs check --memory-graph` is gone: `stayfixed memory refs` now reports the note store's
link graph as notices, beside the stale paths it already finds, and its exit code still counts only
the stale paths. `stayfixed docs check` no longer takes `--store`, which only that graph read, and
refuses it as a usage error.
