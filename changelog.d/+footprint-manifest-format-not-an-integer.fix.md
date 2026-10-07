A `.stayfixed/manifest.json` whose `format` is not a positive integer — `null`, a string, a
number with a fraction, `true`, `0` or a negative number — is now refused as damaged:
`.stayfixed/manifest.json: 'format' is not a positive integer`, exit `2`. Before, `true`, `0` and
every negative integer were read as the format this stayfixed writes, and the command went on;
the other values were refused as written by a newer stayfixed, with advice to upgrade the plugin,
which could not help. A manifest whose `format` is an integer above the one this stayfixed writes
is still refused with that advice.

`stayfixed detach` meets such a manifest as one it cannot read: it finishes (exit `0`) and leaves
the `stayfixed:ignore` region in `.gitignore` where it is (`ignore_region_removed: false`). Before,
it read `true`, `0` or a negative `format` as valid, and took the region out wherever the manifest
did not record it, with the file when the region was all it held.
