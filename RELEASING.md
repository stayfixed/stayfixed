# Releasing stayfixed

Version discipline itself is enforced — `scripts/release.py check` cross-checks six sources, a
tag and the record of the shipped files, and runs in CI. What was undocumented is everything
around it: how to cut a release at all. This file is that, so the bus factor of the release
process is not one.

The sequence, once, before the detail: `scripts/release.py check` → towncrier assembles
`CHANGELOG.md` from the `changelog.d/` fragments → `claude plugin tag` and the `vX.Y.Z` tag,
pushed without `main` → the PyPI upload and the GitHub Release, attached to `vX.Y.Z` only and
never to the floating `v1`, which immutable releases would freeze → `main` moves to the release
commit → `stayfixed overlay publish-template`, which renders `templates/overlay/` and pushes it to
the template repository from your own authenticated checkout, so the public repository's CI
holds no credential that can write a second repository → from `1.0.0` on, the `v1` alias moves
→ the cross-repository smoke runs at the new tag.

## 1. The sources

`uv run python scripts/release.py check` refuses unless these agree:

| Source | Where the version lives |
|---|---|
| `pyproject.toml` | `project.version` |
| `uv.lock` | the `stayfixed` package entry — stale unless `uv sync` has run |
| `src/stayfixed/__init__.py` | `__version__` |
| `.claude-plugin/plugin.json` | `version` |
| `.codex-plugin/plugin.json` | `version` |
| `CHANGELOG.md` | the first `## <version>` heading after the towncrier marker |
| `hooks/hashes.json` | **not a version.** The record of the three files the harness runs — `hooks/run-hook.sh`, `hooks/hooks.json` and `scripts/stayfixed`. `scripts/release.py check` fails while it is stale and `scripts/release.py hashes` refreshes it, in whichever commit changed one of them. Nothing touches it at release time. |

`.claude-plugin/marketplace.json` carries no version of its own and is checked for consistency
rather than for a number.

`scripts/release.py check --tag vX.Y.Z` adds the tag as a further source and tightens one rule:
a fragment still pending in `changelog.d/` is a finding rather than a licence for `CHANGELOG.md`
to lag. That is the form `release.yml` runs. Section 6 is the script's own reference.

## 2. Cutting a release

**If this is the first release, do section 3 first.** The `pypi` environment is the only human
gate this process has, and it is a gate only once it exists: GitHub **auto-creates** an
environment that a job names and the repository does not have, with no protection rules on it.
So a first release run top to bottom without section 3 waits for nobody — `publish` runs
unapproved and fails on Trusted Publishing for want of a pending publisher, and
`github-release` runs unapproved and creates a public GitHub Release. Section 3 is what makes
step 7's sentence true.

1. **Be on `main`, current, and green.** The release workflow builds from the tag, so anything
   not merged is not in the release.

   ```bash
   git switch main && git pull
   uv run pytest -n auto --cov --cov-report=term-missing --cov-fail-under=92
   uv run ruff check . && uv run ruff format --check . && uv run mypy
   uv run python scripts/mutation_oracle.py
   uv run python scripts/release.py check
   claude plugin validate --strict .claude-plugin/plugin.json
   claude plugin validate --strict .claude-plugin/marketplace.json
   claude plugin validate .codex-plugin/plugin.json
   claude plugin tag --dry-run .
   ```

   **And read back the three settings a tag relies on**, because none of them lives in the
   tree and a repository transfer carries each one over as it was rather than as section 3
   says it should be:

   ```bash
   gh api repos/stayfixed/stayfixed/rulesets \
     --jq '.[] | select(.name == "release tags") | .id' |
     xargs -I{} gh api repos/stayfixed/stayfixed/rulesets/{} \
     --jq '[.target, .enforcement, (.conditions.ref_name.include | sort),
            ([.rules[].type] | sort), (.bypass_actors | length)]'
   # ["tag","active",["refs/tags/stayfixed--v*","refs/tags/v*.*.*"],["deletion","update"],0]
   gh api repos/stayfixed/stayfixed/private-vulnerability-reporting --jq .enabled
   # true
   curl -sS -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/stayfixed/json
   # 404 before the first release; from then on 200, with you listed as owner at
   # https://pypi.org/project/stayfixed/
   ```

   Any other answer stops the release here. A ruleset that lists other patterns leaves the
   tag step 6 pushes movable; reporting that is off sends every reporter `SECURITY.md` directs
   to the advisory form back to a public issue; and a PyPI project somebody else owns is one
   step 5's README would tell every reader to install.

2. **Decide the version.** This is a judgement, not a command. The first release is `0.1.0`,
   an alpha, and the tree already says so, with "Development Status :: 3 - Alpha". Every
   mechanism in this file works with whatever number you pick — the gate compares the tag to
   the sources rather than to a number it knows — except the alias, which is the major and
   exists from `1.0.0` on (step 9).

3. **Set it in the four places you edit by hand**, then let the lockfile follow:
   `pyproject.toml`, `src/stayfixed/__init__.py`, and both plugin manifests.

   ```bash
   uv sync
   uv run python scripts/release.py check   # names every source that still disagrees
   ```

   That is four of the six sources; `uv.lock` is the fifth and `uv sync` above writes it.
   `CHANGELOG.md` is the sixth and is still behind here; a pending fragment is what lets it
   lag, and step 4 catches it up.

   **And the release smoke's tag, which a test holds.** `.github/workflows/smoke-release.yml`
   calls `check.yml@vX.Y.Z`, written out, because `uses:` takes no expression; set it to the
   new version here, and in `mutations/`'s "the release smoke calls the alias a 0.x release does
   not have", whose `before` is that line.
   `tests/test_fixtures.py` fails until it names the version the tree carries, and the release
   workflow runs the suite on the tag.

   **And the two example configurations, which a test holds.** `README.md`'s and `docs/cli.md`'s
   example `stayfixed.toml` blocks each carry `version = "X.Y.Z"`, and a copy of a stale one
   makes `stayfixed doctor` warn on a brand-new project. `scripts/release.py check` cannot see
   them, because they are examples and not sources, so `tests/test_documents.py` holds them
   instead: it fails until both name the version the tree carries, and the release workflow runs
   the suite on the tag.

4. **Assemble the changelog.**

   ```bash
   uv run python scripts/release.py notes --version X.Y.Z --draft   # read it first; writes nothing
   uv run python scripts/release.py notes --version X.Y.Z
   uv run python scripts/release.py check   # must print "one version everywhere: X.Y.Z"
   ```

   Read what it wrote, and **edit it**. A fragment written as a note to the author rather than
   as a release note is worth fixing now — this is the text users see. The version comes before
   the changelog because `scripts/release.py notes` refuses a `--version` that is not the
   project's; after this step `CHANGELOG.md` carries the heading and `changelog.d/` is empty.
   Four things to look for, in this order:

   - **A fix for something that never shipped.** A `Fixed` entry is a fix *relative to the
     previous release*, so it is honest only if a user of that release could have met the bug,
     and a `Changed` entry only if it changes something that release did. Fragments are the
     per-commit record, so over a development cycle they accumulate fixes to code the same
     cycle introduced; a fold done earlier is undone by the next commit, which is why the check
     belongs here, once, over the assembled file. For each entry, ask whether the code it
     describes was there at the previous tag: `git log --oneline vPREV..HEAD -- <the file it
     touches>` shows whether it arrived after the tag, and `git show vPREV:<path>` shows what
     the released code did, so you can look for the described bug in it. If the bug or the
     behaviour is not there, state the feature as what it now is and delete the fix; keep the
     ones a reader of the previous release has to act on — a grammar that refuses a
     `stayfixed.toml` which loaded before, a flag that means something narrower than it sounds.
     `scripts/release.py check --tag` cannot judge this: it counts pending fragments and never
     reads them.

     **The first release is this rule with nothing to compare against.** There is no previous
     tag, so every `Fixed` entry in 0.1.0 described a bug no user could have met, and read as a
     warning about the release it shipped in. Fold them all into the features they repair
     (`init`, `attach`, `doctor` and `overlay` each accumulated several), and do the same to a
     `Changed` entry that changed something never released.

   - **Lead with what the user sees.** Open each entry with the outcome, then say why or how.
     An entry that opens with the mechanism can be read as meaning the opposite of what it goes
     on to say. When an entry enumerates cases, such as five different refusals, make it a list,
     so a reader can find the one that is theirs.

   - **No internal terms without a user-facing meaning.** A reader of the changelog has not read
     the code. 0.2.0's entries name "the note reader", "a real `stayfixed.toml`" (a file that is
     not a symlink), "the session-start line" and "the `preset-rules` and `standing-rules`
     bundle" (the first since removed) without saying what each is to someone using the tool;
     say what the user would see, or say the thing in the words the commands print.

   - **Contract changes are not fixes.** For a 0.x minor, which may break what the one before
     it did, call out what a script or a habit can depend on, under `Changed` or in a short
     "Upgrading from 0.X" lead above the entries, because a `Fixed` entry hides it. Two of
     0.2.0's sat under `Fixed` and are what that hides: `stayfixed attach --check` exiting `2`
     instead of `0` for a repository whose `memory.mode` is not `overlay` (`docs/cli.md`
     documents the exit codes as the way a caller tells a finding from a refusal, so a CI
     script that ran it goes red), and `attach` newly writing a marked block into
     `.git/info/exclude`, a file it did not touch before. The third, `reply_language` and
     `artifact_language`, which `setup` still records and nothing reads, is the one 0.2.0 did
     call out, under `Changed`.

5. **Edit the README's install section, then commit.** `README.md`'s Install section names the
   release twice, in **Released as X.Y.Z.** and in the tagged `/plugin marketplace add
   stayfixed/stayfixed@vX.Y.Z`; set both to the new version. `tests/test_documents.py` fails
   until they name the version the tree carries, and the release workflow runs the suite on the
   tag. Do it now: the commit below is the release commit, and after step 6 the tag points at
   whatever this commit contains.

   ```bash
   git commit -am "chore(release): X.Y.Z"
   ```

6. **Tag, twice, and check the tag.** `claude plugin tag` creates `stayfixed--vX.Y.Z`, the
   per-plugin shape the plugin tooling writes so a marketplace can resolve *this plugin's*
   version independently of the repository's; `vX.Y.Z` is the shape everything else expects
   and the one `release.yml` triggers on. Both name the same commit, which is why
   `README.md`'s install paragraph can hand a reader `…@vX.Y.Z` — `/plugin marketplace add`
   takes any git ref — while the `stayfixed--` tag is the one the tooling itself looks for.
   Neither is a substitute for the other; make both.

   **No prerelease tags.** `scripts/release.py check --tag` compares the tag to
   `pyproject.toml`'s literal version string, and `uv.lock` normalises a PEP 440 prerelease
   (`0.1.0-rc1` becomes `0.1.0rc1`), so the six-source rule cannot be satisfied by an `rc` today.
   `release.yml` triggers on finals only, deliberately.

   **Push the tags, not `main`.** A pending publisher does not reserve the PyPI name: until a
   distribution exists under it anyone may upload one, and the release commit's README already
   tells a reader to `uv tool install stayfixed`. That text has to be in the release commit,
   because the README is the package's long description and the wheel is built from the tag,
   so what waits is `main`: it moves in step 7, once `publish` has put the name in your hands,
   and not before.

   ```bash
   claude plugin tag .
   git tag vX.Y.Z
   uv run python scripts/release.py check --tag vX.Y.Z
   git push origin vX.Y.Z stayfixed--vX.Y.Z
   ```

7. **Watch the workflow.**

   ```bash
   gh run list --workflow release --limit 1
   gh run watch <id> --exit-status
   ```

   `build` runs the gate against the tag, tests, builds and attests. **Once section 3's `pypi`
   environment exists with a required reviewer**, `publish` and `github-release` both wait for
   it. An approval is given per environment, not per job, so one approval starts both and one
   rejection stops both; `github-release` does not depend on `publish`, so a failed upload still
   leaves you a Release. Without that environment both jobs run straight
   through the name GitHub invents for them, and nothing on this tag waits for a human.

   When `publish` is green and `https://pypi.org/project/stayfixed/` lists you as owner, move
   `main` to the release commit:

   ```bash
   git push origin main
   ```

   If `publish` failed because the name was taken in the meantime, `github-release` has still
   published a Release whose README tells readers to install that name. Delete the Release
   (`gh release delete vX.Y.Z`), leave `main` where it is, still saying nothing is released,
   and settle the name with PyPI before anything else. The tags cannot be removed (section 5).

8. **Publish the overlay template**, from this checkout, with an authenticated `gh` and an SSH
   key GitHub knows:

   ```bash
   uv run stayfixed overlay publish-template --owner stayfixed        # read the plan
   uv run stayfixed overlay publish-template --owner stayfixed --yes  # do it
   ```

   Without `--yes` nothing outward-facing happens: it renders, asks `gh` what is there, and
   reports what it would create, mark and push.

9. **Move the alias — from `1.0.0` on; a `0.x` release moves none.** The alias is the major:
   a project that writes `@v1` takes every release the alias moves to. Under semantic
   versioning a `0.x` minor may break what the one before it did, so a `v0` alias would hand
   every project on it breaking changes unannounced, and `stayfixed doctor` knows `v1` and no
   other alias. So a `0.x` project pins the commit `stayfixed init` writes, and this step starts
   at the first `1.x` release:

   ```bash
   git tag -f v1 vX.Y.Z && git push -f origin v1
   git ls-remote origin refs/tags/v1 refs/tags/vX.Y.Z   # both lines name one commit
   ```

   The alias resolves as any tag does, which step 10 proves for the release tag itself; what
   is left to check is that it names the release, and the listing above is that check.

10. **Run the cross-repository smoke at the release tag**, at every release. It calls
    `check.yml` at `@dev` and at the `vX.Y.Z` step 3 wrote into `smoke-release.yml`, which
    resolves only now that the tag is pushed.

    ```bash
    gh workflow run smoke-release.yml
    gh run watch <id> --exit-status
    ```

## 3. One-time setup

**Trusted Publishing.** The workflow authenticates to PyPI with a short-lived OIDC token rather
than a stored secret, which requires a one-time registration on PyPI:

**PyPI → Your projects → stayfixed → Publishing → Add a new publisher (GitHub)**

| Field | Value |
|---|---|
| Owner | `stayfixed` |
| Repository | `stayfixed` |
| Workflow | `release.yml` |
| Environment | `pypi` |

For the very first release, before the project exists on PyPI, use PyPI's **pending publisher**
form instead — same fields, reached from your account's publishing settings.

**The `pypi` environment — before the first tag, not after it.** Create it in **GitHub →
Settings → Environments**, and add yourself as a required reviewer. That is the last human
gate, and both `publish` and `github-release` wait behind it: a tag pushed by mistake waits
for an approval instead of becoming a permanent PyPI release or a public GitHub Release.
PyPI does not allow re-uploading a version. **Create it first**: naming an environment that
does not exist does not fail the job — GitHub creates one on the spot, with no protection
rules — so a release cut before this step would have the gate's two `environment:` lines and
none of the gate.

This paragraph is no longer the whole of the defence. `release.yml`'s `environment-gate` job
reads the environment's protection-rule count over the API before either gated job can start,
and fails the run when it is zero: the order these two sections are written in is now checked
rather than asked for. If the workflow's own token cannot read
`GET /repos/OWNER/REPO/environments/NAME` — the endpoint is not open to every default token —
the gate refuses by default, and the way to say "it is a real gate, the read is simply closed
to me" is a repository variable, **Settings → Secrets and variables → Actions → Variables**,
`PYPI_ENVIRONMENT_PROTECTED = true`. It stands in for the *read* only: an environment that
reads back with zero rules fails whatever the variable says. Set it only after the environment
and its reviewer exist.

**Tag protection.** A repository ruleset over `refs/tags/v*.*.*` and `refs/tags/stayfixed--v*`
with `deletion` and `update` rules, so a semver tag is immutable while the `v1` alias, once a
`1.x` release creates it — it matches neither pattern — can still move. The same body creates
the ruleset or, when one named `release tags` already exists, replaces it in place; a second
`POST` beside an existing one would leave two rulesets and fix neither:

```bash
cat > "${TMPDIR:-/tmp}/release-tags.json" <<'JSON'
{"name": "release tags", "target": "tag", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/tags/v*.*.*", "refs/tags/stayfixed--v*"], "exclude": []}},
 "rules": [{"type": "deletion"}, {"type": "update"}]}
JSON
id=$(gh api repos/stayfixed/stayfixed/rulesets --jq '.[] | select(.name == "release tags") | .id')
if [ -n "$id" ]; then
  gh api -X PUT "repos/stayfixed/stayfixed/rulesets/$id" --input "${TMPDIR:-/tmp}/release-tags.json"
else
  gh api -X POST repos/stayfixed/stayfixed/rulesets --input "${TMPDIR:-/tmp}/release-tags.json"
fi
```

**Private vulnerability reporting.** `SECURITY.md`, `CODE_OF_CONDUCT.md` and both issue-template
files send reporters to the advisory form, which exists only while the repository setting is on:

```bash
gh api -X PUT repos/stayfixed/stayfixed/private-vulnerability-reporting
```

**A conduct contact address.** `CODE_OF_CONDUCT.md` still routes a report through the security
advisory form. That is worth a real address before the repository is advertised.

## 4. The harness CLI version

`.github/workflows/ci.yml` and `.github/workflows/smoke.yml` each `npm install -g
@anthropic-ai/claude-code@<version>` — the validator the first one runs and the installer the
second one runs are the same tool, and the two pins must move together. A global npm install is
not a manifest, so Dependabot does not see either of them: bump both by hand, in one commit,
and let the smoke run say whether an install still works.

**The overlay template's own action pins.** `src/stayfixed/templates/overlay/.github/workflows/scan.yml`
pins two actions by full-length sha, and this repository's `.github/dependabot.yml` scans
`.github/workflows/` at the root and nothing else — a nested tree under `src/` is not a
workflow directory the platform reads, so those two pins rot here until somebody looks.
The same file's `GITLEAKS_VERSION` and the `rev:` of the template's `.pre-commit-config.yaml`
(a sha, with its release in a `# frozen:` comment) are not action pins at all, so no configured
Dependabot sees them (it has a `pre-commit` ecosystem, which neither `dependabot.yml` sets up):
bump them by hand, to one gitleaks release, in one commit.
`tests/overlay/test_template.py` holds the two equal.
A rendered overlay ships its own `dependabot.yml` and keeps itself current from then on;
what this line is about is the state every *new* overlay starts from. Check them here, at
the release that publishes the template.

**The project workflow's pin, and what the first tag unlocks.** There is a second sha-pinned
template now: `src/stayfixed/templates/project/stayfixed.yml`, the caller `stayfixed init` renders
into an adopting project's `.github/workflows/`. Its `uses:` line is not pinned in the tree —
the sha is filled in at render time, and it is the commit of the *released* stayfixed that did
the rendering, read off this repository's own `v*` tags. So nothing here rots, and nothing here
needs checking at a release; what a release changes is whether the workflow can be written at
all. Before the first tag `init` finds no released commit to name, reports the workflow skipped
with that reason, and writes nothing into `.github/` — which means every project initialised
before the first release carries no CI caller and no `[ci] ref`, and gets both when `stayfixed
upgrade` ships. The first tag is the event that changes that, and it changes it for new
projects only.

## 5. If something goes wrong

- **Anything goes wrong after the tags are pushed.** The ruleset refuses to delete or move a
  pushed `vX.Y.Z` or `stayfixed--vX.Y.Z`, for everyone, so that version is spent whether or not
  anything was published: a wrong tag, a red `build`, a rejected approval or a failed upload.
  `main` has not moved, so nothing else needs undoing. Fix the release commit locally and cut
  X.Y.(Z+1) from step 3, the `CHANGELOG.md` heading included. If a Release was created for the
  spent version, delete it, as step 7 says for a taken name.
- **PyPI published a bad release.** You cannot replace it. Yank it on PyPI (which hides it from
  resolvers without breaking anyone who has already pinned it) and release a patch version.
- **`scripts/release.py check` fails in the workflow but passed locally.** Almost always
  `uv.lock`: `uv sync` was not run after the version bump, so the lockfile still carries the old
  one. The other candidate is `hooks/hashes.json`, if a shipped file moved without
  `scripts/release.py hashes`.
- **`publish-template` pushed the wrong tree.** The next `publish-template` fixes it: it
  replaces the tree whole rather than merging into it.

## 6. The release script

`scripts/release.py` is this repository's own tooling, not a command stayfixed ships: it only
ever checked the stayfixed repository itself. It runs through the same frame as the CLI, so
`--json` is accepted anywhere on the line and prints one object, and it exits `0` on success,
`1` on findings and `2` on a refusal.

```bash
uv run python scripts/release.py check [--tag TAG]               # one version everywhere
uv run python scripts/release.py notes --version X.Y.Z [--draft]  # assemble CHANGELOG.md
uv run python scripts/release.py hashes [--check]                 # the record of the shipped files
```

**`check`** cross-checks the six sources of section 1 and exits `1` naming every one that
disagrees. Its `--json` object carries `summary`, `versions` (every source and what it says) and
`problems` (empty on a clean run), and it carries all three whether or not there is drift — the
drift is in `problems`, not in the shape. A source it cannot parse at all is still a failure and
prints `error` instead. `--tag` accepts both tag shapes, `vX.Y.Z` and `stayfixed--vX.Y.Z`,
because either may be the ref a run was created from. It writes nothing; it reads the sources,
the fragments pending in `changelog.d/`, and `hooks/hashes.json` beside the three files it
records.

**`notes`** is a wrapper around towncrier, which does the rendering while `[tool.towncrier]` in
`pyproject.toml` owns the format. A `--version` that is not the project's is refused (`2`) before
towncrier runs, because assembling under another number writes a `CHANGELOG.md` heading that
`check` then refuses; a towncrier that cannot be run is a finding (`1`) naming it as the
development dependency it is. Without `--draft` it writes `CHANGELOG.md` and consumes the
fragments: towncrier removes each one from `changelog.d/` and, in a git checkout, stages both
changes — `git add` of `CHANGELOG.md`, `git rm` of each tracked fragment, which removes the
directory itself when the tracked fragments were all it held. With `--draft` it writes nothing
and prints the rendered section.

**`hashes`** records the sha256 of the three files the harness executes without Python —
`hooks/run-hook.sh`, `hooks/hooks.json` and `scripts/stayfixed` — into `hooks/hashes.json` beside
them; a wheel's own contents are the packaging tool's to attest. The record is refused rather
than written when any of the three is missing: a record naming two of three would still claim to
be what the release shipped, while naming less, and every later comparison would report drift
against that claim. It is not a release-time command: `check` compares the record to the
tree on every run, so editing any of the three without re-recording fails the gate in the same
commit, which is what makes it a record somebody has watched fail. `stayfixed doctor`'s `files`
row reads the installed record against the installed files. Under `--check` it writes nothing,
exits `1` on drift, and its `--json` object carries `summary`, `files` and `problems` in both
outcomes.
