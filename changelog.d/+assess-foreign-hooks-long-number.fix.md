`stayfixed assess` no longer reports a committed hook settings file as one it could not look at
when the file holds a number longer than Python converts to an integer (4,300 digits by default).
Such a file is valid JSON that a harness reads, so its `foreign-hooks` item now names the file when
it holds a hook entry without stayfixed's marker, as `stayfixed doctor`'s `hook-entries` row already
did, instead of a `could-not-look` warning.
