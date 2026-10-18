# Recorded runner reports

The bytes five test runners wrote, each recorded once by running the runner itself, so the readers
under `stayfixed.prove` are tested against real reports rather than remembered ones. Every file in
`reports/` has one row below; `tests/prove/test_fixtures.py` holds the table to the directory.

How they were recorded:

- Every run was in a scratch directory, and the scratch directory's absolute path was then
  rewritten to `/work` in each file, so no report carries the recording machine's paths. Nothing
  else was edited.
- The three-test case is the same in every runner: one test that passes (named
  `a&amp;b café` where the runner allows a free name, `TestPasses` in Go), one that fails, and one
  that is skipped.
- pytest ran with plugin autoloading disabled (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`) and the ini
  option that keeps a non-ASCII test id unescaped.
- `node --test` ran with two reporters, junit to `<report>` and spec to stdout:
  `--test-reporter=junit --test-reporter-destination=<report> --test-reporter=spec
  --test-reporter-destination=stdout`, written `<junit+spec>` below. The `node24-` files were
  recorded the same way with Node 24.10.0, the active LTS, which writes no `file` attribute and
  names a whole-file testcase by the file's path from the directory node ran in; each ran in the
  directory of its own case, as the `node-` files did.
- vitest ran `vitest run --reporter=json --outputFile.json=<report> --reporter=default`, written
  `<json+default>` below.
- `go test` ran with `GOENV=off GOFLAGS= GOTOOLCHAIN=local`, so no setting of the recording
  machine's shaped the stream (`prove` itself sets none of them); the report is the command's
  stdout.

| File | Runner | Version | Command | Recorded |
|---|---|---|---|---|
| `pytest-xunit1.xml` | pytest | 9.1.1 (CPython 3.13.16) | `python -m pytest --junitxml=<report> -o junit_family=xunit1`, three tests, exit 1 | 2026-10-18 |
| `pytest-xunit2.xml` | pytest | 9.1.1 (CPython 3.13.16) | `python -m pytest --junitxml=<report> -o junit_family=xunit2`, three tests, exit 1 | 2026-10-18 |
| `pytest-record-xml-attribute.xml` | pytest | 9.1.1 (CPython 3.13.16) | as `pytest-xunit1.xml`, the passing test calling `record_xml_attribute` and `record_property`, exit 1 | 2026-10-18 |
| `pytest-empty.xml` | pytest | 9.1.1 (CPython 3.13.16) | `python -m pytest --junitxml=<report> -o junit_family=xunit2 -k no_such_test`, exit 5 | 2026-10-18 |
| `pytest-all-skipped.xml` | pytest | 9.1.1 (CPython 3.13.16) | `python -m pytest --junitxml=<report> -o junit_family=xunit2 -k skipped`, one skipped test, exit 0 | 2026-10-18 |
| `pytest-setup-plan.xml` | pytest | 9.1.1 (CPython 3.13.16) | `python -m pytest --junitxml=<report> -o junit_family=xunit2 --setup-plan`, three tests: the failing one reported as passed, exit 0 | 2026-10-18 |
| `node-junit.xml` | node --test | 26.12.0 | `node --test <junit+spec>`, three tests, exit 1 | 2026-10-18 |
| `node-empty.xml` | node --test | 26.12.0 | `node --test <junit+spec>` in a directory with no test file, exit 0 | 2026-10-18 |
| `node-all-skipped.xml` | node --test | 26.12.0 | `node --test <junit+spec>`, two skipped tests, exit 0 | 2026-10-18 |
| `node-name-pattern.xml` | node --test | 26.12.0 | `node --test <junit+spec> --test-name-pattern=no_such_test` over the three tests: one whole-file testcase, exit 0 | 2026-10-18 |
| `node-no-tests.xml` | node --test | 26.12.0 | `node --test <junit+spec>` over a test file that defines no test: one whole-file testcase, exit 0 | 2026-10-18 |
| `node-exit0.xml` | node --test | 26.12.0 | `node --test <junit+spec>` over a test file calling `process.exit(0)` before its test: one whole-file testcase, exit 0 | 2026-10-18 |
| `node-load-failure.xml` | node --test | 26.12.0 | `node --test <junit+spec>` over one passing file, one with a syntax error and one that throws on load: two whole-file testcases with a `failure` child, exit 1 | 2026-10-18 |
| `node24-name-pattern.xml` | node --test | 24.10.0 | as `node-name-pattern.xml`, the three tests' file at the top: one whole-file testcase named `three.test.mjs`, no `file` attribute, exit 0 | 2026-10-18 |
| `node24-nested-pattern.xml` | node --test | 24.10.0 | as `node24-name-pattern.xml`, the file at `test/deep/three.test.mjs`: the whole-file testcase named by that path, exit 0 | 2026-10-18 |
| `node24-no-tests.xml` | node --test | 24.10.0 | as `node-no-tests.xml`: one whole-file testcase named `notests.test.mjs`, no `file` attribute, exit 0 | 2026-10-18 |
| `node24-nested.xml` | node --test | 24.10.0 | `node --test <junit+spec>` over `test/real.test.mjs` (one passing test) and `test/deep/empty.test.mjs` (no test): the whole-file testcase named `test/deep/empty.test.mjs`, exit 0 | 2026-10-18 |
| `node24-exit0.xml` | node --test | 24.10.0 | as `node-exit0.xml`: one whole-file testcase named `exit0.test.mjs`, exit 0 | 2026-10-18 |
| `node24-load-failure.xml` | node --test | 24.10.0 | as `node-load-failure.xml`, the file with a syntax error at `test/broken.test.mjs`: two whole-file testcases, named by their paths, each with a `failure` attribute and child, exit 1 | 2026-10-18 |
| `jest.json` | jest | 30.5.2 | `node node_modules/jest/bin/jest.js --ci --json --outputFile=<report>`, three tests, exit 1 | 2026-10-18 |
| `jest-todo.json` | jest | 30.5.2 | as `jest.json` over one passing test, one `test.todo` and one `test.skip`, exit 0 | 2026-10-18 |
| `jest-empty.json` | jest | 30.5.2 | as `jest.json` in a project with no test file, exit 1 | 2026-10-18 |
| `jest-empty-pass-with-no-tests.json` | jest | 30.5.2 | as `jest-empty.json` with `--passWithNoTests`, exit 0 | 2026-10-18 |
| `jest-all-skipped.json` | jest | 30.5.2 | as `jest.json` over two `test.skip`, exit 0 | 2026-10-18 |
| `jest-load-failure.json` | jest | 30.5.2 | as `jest.json` over one passing file and one requiring a missing module: the totals say one passed and none failed, exit 1 | 2026-10-18 |
| `vitest.json` | vitest | 5.0.5 (Node 26.12.0) | `node node_modules/vitest/vitest.mjs run <json+default>`, three tests, exit 1 | 2026-10-18 |
| `vitest-todo.json` | vitest | 5.0.5 (Node 26.12.0) | as `vitest.json` over one passing test, one `test.todo` and one `test.skip`, exit 0 | 2026-10-18 |
| `vitest-empty.json` | vitest | 5.0.5 (Node 26.12.0) | as `vitest.json` in a project with no test file, exit 1 | 2026-10-18 |
| `vitest-all-skipped.json` | vitest | 5.0.5 (Node 26.12.0) | as `vitest.json` over two `test.skip`, exit 0 | 2026-10-18 |
| `vitest-load-failure.json` | vitest | 5.0.5 (Node 26.12.0) | as `vitest.json` over one passing file and one importing a missing module: the totals say one passed and none failed, exit 1 | 2026-10-18 |
| `go.jsonl` | go test | 1.27.2 | `go test -json ./plain/`, three tests, exit 1 | 2026-10-18 |
| `go-subtest.jsonl` | go test | 1.27.2 | `go test -json ./three/`, the three tests and a fourth with one passing subtest, exit 1 | 2026-10-18 |
| `go-run-no-such-test.jsonl` | go test | 1.27.2 | `go test -json -run NoSuchTest ./three/`, exit 0 | 2026-10-18 |
| `go-testmain-exit0.jsonl` | go test | 1.27.2 | `go test -json ./testmain/`, a `TestMain` calling `os.Exit(0)` without `m.Run`, exit 0 | 2026-10-18 |
| `go-build-fail.jsonl` | go test | 1.27.2 | `go test -json ./broken/`, a test file that does not compile: a `build-fail` event and then the package's own `fail`, exit 1 | 2026-10-18 |
| `go-framing.jsonl` | go test | 1.27.2 | `go test -json ./framing/`, a `TestMain` printing `\x16--- PASS: TestForged` before `m.Run`: a `pass` event for a test that never ran, exit 0 | 2026-10-18 |

## What the adapters were measured on

`docs/cli.md`'s `stayfixed prove` section says what each adapter recognises, adds and refuses; the
measurements behind it, each made on the version named, are here.

- **pytest 9.1.1.** `--junitxml=<report> -o junit_family=xunit2`, added last among pytest's
  options, win over a `--junitxml` or `junit_family` of the command's own and over an `addopts`
  that sets them. `--setup-plan` reports the tests it only sets up as passed
  (`pytest-setup-plan.xml`), and `--trace`, its standard input at its end, reports a failing test
  as passed.
- **jest 30.5.2.** A run of no test prints "No tests found" and exits before it writes its report
  wherever its standard error is a pipe, and writes it where it is a terminal or a file. `-u false`
  is off. `--collectTests` exits 0 reporting a failing test as passed; `--testResultsProcessor`
  keeps the counts, so it is free.
- **vitest 5.0.5.** `-t.u` sets `-u`, and `--update=false` is the text `false`, which rewrites
  snapshots; `--update=none`, `--no-update` and `--update=new` do not.
- **Node 26.12.0 and 24.10.0.** Node reads `_` in an option's name as `-`. Node 26.12.0 reads
  Node's options written after the files under `--test`; Node 24.10.0 does not (the run is as
  without them), so on 24 a refusal or `never-ends` there is only the safe side. Given more
  `--test-reporter`s than `--test-reporter-destination`s, or the other way round, Node stops
  before any test runs (`ERR_INVALID_ARG_VALUE`). A whole-file testcase is named by the file's path
  from the directory node runs in, with a `file` attribute on 26 and none on 24 (the `node24-`
  files).
- **Go 1.27.2.** `-c` writes nothing to standard output, and a `-json=false` after the adapter's
  `-json` turns the stream into text; the go command reads a duplicate `-json` as one.
- **uv 0.12.19.** A runner missing behind `uv run` is uv's error, `Failed to spawn`, exit 2: no
  event stream for `go test`, which then counts no test, and no report for the others.

## The runners' fixtures

`node/` is what the `runners` CI job installs and the JavaScript adapters' real-runner tests run:
`package.json` and `package-lock.json` pin jest 30.5.2 and vitest 5.0.5 and everything they need
(the lockfile recorded when those versions were pinned, the package renamed), and `jest/`, `vitest/`
and `node-test/` hold the three-test case in each runner's own form. An `npm ci` of the two files,
anywhere but in this checkout, installs the packages; `STAYFIXED_NODE_MODULES` names the
`node_modules` it made (`tests/prove/real_runners.py`).

`go/` is the module the `go test` adapter's real-runner tests copy and run: `three/` holds the
three-test case, `passing/` one passing and one skipped test, `skipped/` two skipped ones,
`testmain/` a `TestMain` that exits 0 before any test, `framing/` one that prints test2json's
framing for a test that never ran, `printing/` a failing test that prints a whole `pass` event, and
`broken/` a test file that does not compile. Its `go.mod` asks for Go 1.24, so the image's 1.24.7
and the pinned 1.27.2 both run it.

The `runners` CI job installs Go 1.27.2 as the toolchain module the `go` command itself switches
to, `golang.org/toolchain@v0.0.1-go1.27.2.linux-amd64`, the zip
`https://proxy.golang.org/golang.org/toolchain/@v/v0.0.1-go1.27.2.linux-amd64.zip`, and checks it
against SHA-256 `3a467ed067f27cd55bf3a702f8e2bf12479f53c9d8ae0de548f48ebcb3c67796` before it
unpacks it. The digest was recorded on 2026-10-18 from the zip the Go module proxy served when the
version was pinned, the download `go` made into its module cache; the module hash `go` recorded
beside it is `h1:N6Xv/1OLzI0jVVkUwkrxHRZc/GCTARUo6idcngKwlDE=`, which the Go checksum database's
entry for that module and version can be checked against. `tests/test_runners_job.py` holds the
job's digest equal to this one.
