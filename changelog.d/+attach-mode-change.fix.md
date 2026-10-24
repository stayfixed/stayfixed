`stayfixed attach` follows a change of `[memory] mode`. A re-attach out of `overlay` mode takes back
the `autoMemoryDirectory` key and the composed store an earlier attach made, as `stayfixed detach`
does, where the harness used to go on reading the overlay's notes. And a `[memory] mode = "overlay"`
set only in the overlay's project file applies on the first attach, which used to compose nothing
until a second one.
