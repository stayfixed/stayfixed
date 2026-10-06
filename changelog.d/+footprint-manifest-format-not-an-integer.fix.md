A `.stayfixed/manifest.json` whose `format` is not a positive integer — `null`, a string, a
number with a fraction, `true`, `0` or a negative number — is now refused as damaged:
`.stayfixed/manifest.json: 'format' is not a positive integer`. Before, every such value but `true`
was refused as written by a newer stayfixed, with advice to upgrade the plugin, which could not
help, and `true` was read as the format this stayfixed writes. A manifest whose `format` is an
integer above the one this stayfixed writes is still refused with that advice.
