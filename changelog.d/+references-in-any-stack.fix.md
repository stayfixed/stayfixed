`stayfixed plan check`, the `plan` gate and `stayfixed memory refs` now check a backticked path in
any language, not only one ending in `.py`, `.sh`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`,
`.ts` or `.tsx`: a plan or a note citing `src/lib.rs`, `cmd/main.go:12` or `app/Foo.java` is told
when the file is gone, as one citing a Python file always was. A path counts when its last part
has an extension that starts with a letter, a dotfile such as `secrets/.env` included, so a version
such as `releases/0.1.9` is still prose. The same rule reads a backticked `owner/lib.js`
repository name, a dotted branch such as `release/v1.x` and a URL written without its scheme
(`example.com/docs/a.html`) as a path claim, which is reported when no such file exists; in a
note, write such a name in italics instead. A line and column (`src/b.c:3:14`) and a symbol path of
any depth (`tests/test_a.py::TestA::test_x`, `src/lib.rs::parser::parse`) are read as a place in
the file; before, either made the span no reference at all. The plan gate still reads only the
lines a change writes, so an old plan's lines are checked only when a change rewrites them. The
entry `stayfixed bugs new` writes now asks for the file "and the symbol or line in it" rather than
showing a Python file and a pytest node id; entries already filed are unchanged.
