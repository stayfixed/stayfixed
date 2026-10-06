A `.stayfixed/manifest.json` whose `format` is `null`, a string or any other value that is not an
integer is now refused as damaged: `.stayfixed/manifest.json: 'format' is not an integer`. Before,
it was refused as written by a newer stayfixed, and the refusal told you to upgrade the plugin,
which could not help. A manifest whose `format` is an integer above the one this stayfixed writes
is still refused with that advice.
