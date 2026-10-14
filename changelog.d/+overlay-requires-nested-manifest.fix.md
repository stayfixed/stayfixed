An overlay whose `.claude-plugin/plugin.json` is valid JSON nested deeper than Python's parser
follows no longer silences the overlay's lines at the start of a session, such as the one saying
the repository is not attached: the manifest is read as one that declares no `stayfixed.requires`,
as a manifest that cannot be read already was.
