A TOML file holding an integer longer than Python converts (4,300 digits by default) is now read
as one that does not parse, worded "is not valid TOML (holds a number longer than the parser
converts)", wherever stayfixed reads one somebody else wrote: `stayfixed.toml` on either side of
`stayfixed gate`, `docs/trail.toml`, a profile's `pyproject.toml`, the machine configuration file
and the overlay's record of a binding. Before, one such line ended `stayfixed doctor`,
`stayfixed gate`, `stayfixed assess` and `stayfixed init` in an internal error, made a hook say
"internal error" where it says "does not load", and turned `doctor`'s `attached`, `bundles` and
`store-debris` rows red "this check could not run". The same goes for JSON past Python's parser,
nested deeper than it follows or holding such a number, in a release's `hooks/hashes.json`, in the
overlay's manifests where `stayfixed overlay init` renames them and where `overlay upgrade` reads
whose overlay it is, and in what `gh repo view` answers to `stayfixed overlay create` and
`overlay publish-template`: each is now the refusal or failure a file that is not JSON already
got, where it was an internal error. `stayfixed guard bg-cleanup` now refuses input nested deeper
than the parser follows as input it cannot read, where it ended in an internal error, and words
its refusal of such a number in its own terms rather than with Python's advice to raise a limit.

Two refusals of input that is not JSON at all now read a little differently, because every JSON
object is read through one reader: `stayfixed guard bg-cleanup` puts "stdin is not valid JSON:"
before the parser's message, which it used to print alone, and `stayfixed overlay
publish-template` says what `gh repo view` answered "is not valid JSON", where it said `gh repo
view` "did not answer with JSON".
