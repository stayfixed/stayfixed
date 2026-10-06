A TOML file holding an integer longer than Python converts (4,300 digits by default) is now read
as one that does not parse, worded "is not valid TOML (holds a number longer than the parser
converts)", wherever stayfixed reads one somebody else wrote: `stayfixed.toml` on either side of
`stayfixed gate`, `docs/trail.toml`, a profile's `pyproject.toml`, the machine configuration file
and the overlay's record of a binding. Before, one such line ended `stayfixed doctor`,
`stayfixed gate`, `stayfixed assess` and `stayfixed init` in an internal error, made a hook say
"internal error" where it says "does not load", and turned `doctor`'s `attached`, `bundles` and
`store-debris` rows red "this check could not run". The same goes for JSON past Python's parser,
nested deeper than it follows or holding such a number, in a release's `hooks/hashes.json`, the
overlay's plugin and marketplace manifests that `stayfixed overlay init` and `overlay upgrade` read,
what `gh repo view` answers to `stayfixed overlay create` and `overlay publish-template`, and the
input `stayfixed guard bg-cleanup` reads: each is now the refusal or failure a file that is not
JSON already got, where it was an internal error.
