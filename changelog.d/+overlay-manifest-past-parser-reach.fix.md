`stayfixed setup --overlay <path>` and `stayfixed overlay upgrade` now refuse a directory whose
`.claude-plugin/plugin.json` or `.claude-plugin/marketplace.json` is nested deeper than Python's
JSON parser follows, or holds a number longer than Python converts to an integer (4,300 digits by
default), saying the manifest cannot be read as JSON. Either used to end the command in an internal
error.
