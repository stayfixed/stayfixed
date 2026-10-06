On Python 3.14, a JSON file nested deeper than 10,000 levels — a `.claude/settings.json` or
`settings.local.json`, the attach ledger, a manifest, the trust record — is now refused as "nested
deeper than this reader follows", the words Python 3.11 to 3.13 give it in this release. 3.14's
parser follows such a file to about 57,800 levels, further than the rest of the interpreter does,
so `stayfixed detach`, `init`, `upgrade` and `attach` read one and then ended in an internal error
writing it back, and `stayfixed doctor` read it as one it could check where every other supported
Python reads it as one it cannot. On Python 3.12, whose encoder stops near 994 levels when it
indents while its parser reads about 9,996, a settings file, manifest or `~/.claude/settings.json`
between the two is now refused in the same words when `attach`, `detach`, `init`, `upgrade`,
`overlay init` or `setup` would write it back, where it ended in an internal error.
