The configuration loader can now read a `stayfixed.toml` the way a session needs to: a section or
key this release does not know is ignored, a value it cannot use is put back to the preset's one
key at a time, and each is reported in a note naming the key and never the value, so a file a
newer stayfixed wrote keeps every setting this release understands. Commands still refuse such a
file whole. A preset name this release does not ship is now refused as a configuration error,
with the same message as before.
