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
  --test-reporter-destination=stdout`, written `<junit+spec>` below.
- vitest ran `vitest run --reporter=json --outputFile.json=<report> --reporter=default`, written
  `<json+default>` below.
- `go test` ran with `GOENV=off GOFLAGS= GOTOOLCHAIN=local`; the report is the command's stdout.

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
