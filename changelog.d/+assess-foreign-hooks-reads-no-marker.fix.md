`stayfixed assess`'s `foreign-hooks` item now lists a committed settings file holding a hook entry
that claims stayfixed's marker (`# stayfixed:<id>` at the end of its command). It used to pass any
such entry over as stayfixed's own, whatever its `type` and whichever id it claimed, so an entry of
`type` `http` that posts every event to a URL read as no foreign hook at all. stayfixed writes no
hook entry into a committed settings file — `stayfixed attach` merges into
`.claude/settings.local.json`, which a repository keeps out of git — and `assess` has no grant to
compare an entry with, so the marker there vouches for nothing. `stayfixed doctor`'s `hook-entries`
row is the one that can account for a marked entry, against what your overlay grants.
