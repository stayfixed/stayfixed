#!/usr/bin/env python3
"""Push the plugin tree a release attested to the plugin's own repository, and nothing else.

    uv run python scripts/publish_plugin.py --tag vX.Y.Z [--remote URL] [--yes]

The plugin is published from `stayfixed/stayfixed-plugin`, a repository whose root is the tree
`scripts/plugin_tree.py` renders from a commit of this one. CI renders that tree at the release's
tag and attests its manifest; this is the owner's one command that takes the same tree to the
plugin repository. Without `--yes` it does everything but the push, and says which commit it would
push; with `--yes` it pushes that commit as `main` and as the tag, atomically.

**What it trusts, and why.** The attestation, and only the attestation, says which tree may be
published: `gh attestation verify` binds the manifest's bytes to this repository's `release.yml`
(`--signer-workflow`), run for this tag (`--source-ref`) at this commit (`--source-digest`), on a
GitHub-hosted runner (`--deny-self-hosted-runners`). The owner's checkout only renders, builds and
compares: the tag is resolved once to a commit and every later step names that commit, so a
branch of the tag's name, a local edit or a staged file is not what is rendered; and what is
pushed is read back whole and compared with the attested manifest byte for byte before anything
leaves the machine. The commit is built from the attested modes and the rendered bytes with git
plumbing in a scratch bare repository — no working tree, no index, `hash-object --no-filters`,
and a push with `core.hooksPath` pointed at nothing — so the owner's line-ending conversion,
attributes, excludes and hooks never touch it. CI holds no credential to the plugin repository:
the owner's own git pushes, with the owner's own key.

**Two ways to run git, on purpose.** What reaches the remote (`ls-remote`, `fetch`, `push`), `gh`
and `plugin_tree.py` run through the `Runner`, which keeps the owner's environment — the SSH agent
the push needs, the token `gh` reads. Every local object write (`init`, `hash-object`, `mktree`,
`commit-tree`) runs through `gitenv.git_run` in the scratch repository: the `Runner` closes stdin,
which `mktree` reads, and `git_run` hands git a fixed few variables, so nothing in the
environment points it at another repository or index.

**A re-run is safe.** A remote whose tag already names a commit holding exactly the attested
manifest — no path beside the plugin's — and whose `main` names that same commit is "already
published": exit `0`, nothing pushed. Anything else under that tag is a refusal, and the push is
`--atomic`, so `main` never moves without its tag.

The command goes through the CLI frame's `run`, as `scripts/release.py`'s do: `--json` anywhere on
the line, exit `0`, and `2` for a refusal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from stayfixed.cli import JSON_EPILOG, run
from stayfixed.errors import Refusal
from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, answer_bytes, answer_lines, git_run
from stayfixed.printed import clipped, quoted
from stayfixed.release.api import tag_for
from stayfixed.result import Result
from stayfixed.runner import Completed, Runner, subprocess_runner

# The plugin's own repository, as the owner's git reaches it to push.
PLUGIN_REMOTE = "git@github.com:stayfixed/stayfixed-plugin.git"
# The workflow whose run attests the tree, and the repository it runs in: `gh attestation verify`
# matches `--signer-workflow` exactly, so this is the workflow's path with its repository.
SIGNER_WORKFLOW = "stayfixed/stayfixed/.github/workflows/release.yml"
SOURCE_REPOSITORY = "stayfixed/stayfixed"
# The repository this script lives in: the one whose tag is published.
ROOT = Path(__file__).resolve().parents[1]
PLUGIN_TREE = Path(__file__).resolve().with_name("plugin_tree.py")
# The manifest's first line as `plugin_tree.py` writes it. A manifest that opens with another is
# one this script does not know how to read, and it refuses rather than guess at its lines.
MANIFEST_FORMAT = "stayfixed-plugin-tree 1"
# The only modes the manifest may name, and the only ones the plugin repository's tree holds.
FILE_MODES = frozenset({"100644", "100755"})
# A release's tag: `v` and three dot-separated runs of ASCII digits, and nothing after them.
TAG_PATTERN = r"v[0-9]+\.[0-9]+\.[0-9]+"
MAIN = "refs/heads/main"
# A full object name, SHA-1's or SHA-256's, as `ls-remote` prints one.
OBJECT_NAME = r"[0-9a-f]{40}|[0-9a-f]{64}"
# How many of a program's stderr lines a refusal quotes.
QUOTED_LINES = 6


@dataclass(frozen=True)
class Published:
    tag: str
    files: int
    commit: str  # the plugin repository's new commit, or the one already tagged
    pushed: bool
    already: bool  # the remote's tag and main already name a commit holding exactly this manifest


def _said(done: Completed) -> str:
    """The first lines a program wrote to stderr (else stdout), each quoted, or its exit code.

    Each line through `clipped`: `gh` and `git` print what the remote says, and a line break
    followed by `::error::`, or an escape sequence, is not text this script prints raw."""
    lines = [line for line in done.stderr.split("\n") if line.strip()]
    lines = lines or [line for line in done.stdout.split("\n") if line.strip()]
    if not lines:
        return f"exit {done.code}, and nothing said"
    return " / ".join(clipped(line.strip()) for line in lines[:QUOTED_LINES])


def _plugin_tree(runner: Runner, root: Path, *args: str) -> None:
    """Run `scripts/plugin_tree.py` with `args`; a non-zero exit is a refusal quoting it."""
    done = runner.launch([sys.executable, str(PLUGIN_TREE), *args], root)
    if done.code != 0:
        raise Refusal(f"scripts/plugin_tree.py {args[0]} refused: {_said(done)}")


def _tag_commit(root: Path, tag: str) -> tuple[str, str]:
    """The commit `refs/tags/<tag>` names, and the version its `plugin.json` says, which must be
    the one the tag is spelled from."""
    if not re.fullmatch(TAG_PATTERN, tag):
        raise Refusal(f"{quoted(tag)} is not a plain version tag, vX.Y.Z")
    code, answer = git_run(
        root, "rev-parse", "--verify", "--end-of-options", f"refs/tags/{tag}^{{commit}}"
    )
    sha = answer.removesuffix("\n")
    if code != 0 or len(sha) != 40:
        raise Refusal(f"no tag {tag} names a commit in {root} (git rev-parse exited {code})")
    code, answer = git_run(root, "cat-file", "blob", f"{sha}:.claude-plugin/plugin.json")
    try:
        manifest = json.loads(answer_bytes(answer).decode("utf-8")) if code == 0 else None
    except ValueError:
        manifest = None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str):
        raise Refusal(f".claude-plugin/plugin.json at {tag} ({sha}) names no version")
    if tag_for(version)[0] != tag:
        raise Refusal(f"{tag} names {sha}, whose .claude-plugin/plugin.json says {quoted(version)}")
    return sha, version


def _verify(runner: Runner, root: Path, attested: Path, tag: str, sha: str) -> None:
    """Ask `gh` whether this repository's release workflow attested exactly this manifest, for
    this tag at this commit, on a GitHub-hosted runner."""
    argv = [
        "gh",
        "attestation",
        "verify",
        str(attested),
        "--repo",
        SOURCE_REPOSITORY,
        "--signer-workflow",
        SIGNER_WORKFLOW,
        "--source-ref",
        f"refs/tags/{tag}",
        "--source-digest",
        sha,
        "--deny-self-hosted-runners",
    ]
    verified = runner.launch(argv, root)
    if verified.code != 0:
        # gh exits non-zero both for "no attestation vouches for this" and for "I could not
        # ask" (unauthenticated, offline); which one it was is in what it said, not here.
        raise Refusal(
            f"gh attestation verify exited {verified.code}: {_said(verified)}. Either no release "
            f"of {tag} at {sha} attested this tree, or gh could not check; nothing was fetched "
            "or pushed"
        )


def _manifest_rows(text: bytes) -> list[tuple[str, str]]:
    """`(mode, path)` for every file the attested manifest names, in its order."""
    try:
        lines = text.decode("utf-8").split("\n")
    except UnicodeDecodeError:
        raise Refusal(f"the rendered manifest is not UTF-8, as {MANIFEST_FORMAT!r} is") from None
    if not lines or lines[0] != MANIFEST_FORMAT or lines[-1] != "":
        raise Refusal(f"the rendered manifest does not open with {MANIFEST_FORMAT!r}")
    rows = []
    for number, line in enumerate(lines[1:-1], start=2):
        fields = line.split(" ", 2)
        if len(fields) != 3:
            raise Refusal(
                f"the rendered manifest's line {number} is not a file's, as {MANIFEST_FORMAT!r} "
                f"writes one: {clipped(line)}"
            )
        mode, _digest, path = fields
        # No test reddens on this check alone: `plugin_tree.py` writes no other mode, and a mode
        # edited into the file after the render is built as written and then refused by the
        # read-back, whose `members` takes only a regular file's. It keeps that edit from
        # reaching `mktree` at all.
        if mode not in FILE_MODES:
            raise Refusal(f"the rendered manifest names mode {quoted(mode)} for {quoted(path)}")
        rows.append((mode, path))
    return rows


def _first_difference(want: bytes, found: bytes) -> str:
    """Where `found` parts from `want`, as the first differing line of the two manifests."""
    expected = want.decode("utf-8", "replace").split("\n")
    seen = found.decode("utf-8", "replace").split("\n")
    for number in range(max(len(expected), len(seen))):
        line = expected[number] if number < len(expected) else "<no line>"
        other = seen[number] if number < len(seen) else "<no line>"
        if line != other:
            return f"line {number + 1} is {clipped(other)} where the attested has {clipped(line)}"
    return "the two manifests are the same"  # never reached: the callers compare first


def _network(runner: Runner, git_dir: Path, *args: str) -> Completed:
    return runner.launch(["git", "-C", str(git_dir), *args], git_dir)


def _remote_refs(runner: Runner, git_dir: Path, remote: str, tag: str) -> dict[str, str]:
    """`main` and the tag on the remote, by their exact names: `ls-remote` matches a pattern
    against a ref's tail, so a `refs/heads/x/refs/heads/main` would answer it too."""
    wanted = (MAIN, f"refs/tags/{tag}")
    listed = _network(runner, git_dir, "ls-remote", "--end-of-options", remote, *wanted)
    if listed.code != 0:
        raise Refusal(f"git ls-remote {remote} exited {listed.code}: {_said(listed)}")
    found = {}
    for line in listed.stdout.split("\n"):
        sha, _, ref = line.partition("\t")
        if ref not in wanted:
            continue
        # An object name and nothing else: it is handed on to `fetch`, `plugin_tree.py` and
        # `commit-tree -p`, and the remote chose it.
        if not re.fullmatch(OBJECT_NAME, sha):
            raise Refusal(f"git ls-remote {remote} answered {clipped(sha)} for {ref}")
        found[ref] = sha
    return found


def _fetch(runner: Runner, git_dir: Path, remote: str, ref: str) -> None:
    """Fetch `ref`'s objects into the scratch repository, and no other ref or tag."""
    args = ("fetch", "--quiet", "--no-tags", "--end-of-options", remote, ref)
    fetched = _network(runner, git_dir, *args)
    if fetched.code != 0:
        raise Refusal(f"git fetch {remote} {ref} exited {fetched.code}: {_said(fetched)}")


def _already(
    runner: Runner, root: Path, scratch: Path, remote: str, tag: str, held: dict[str, str]
) -> str:
    """The commit the remote's tag names, if it holds exactly the attested tree and `main` names
    it too; any other state of the remote under this tag is a refusal."""
    git_dir, tagged = scratch / "plugin.git", held[f"refs/tags/{tag}"]
    _fetch(runner, git_dir, remote, f"refs/tags/{tag}")
    remote_tree = scratch / "remote-tree.txt"
    # `--exact`: a path beside the plugin's in that commit is not the attested tree either.
    exact = ("manifest", "--exact", "--root", str(git_dir), "--rev", tagged)
    _plugin_tree(runner, root, *exact, "--manifest-file", str(remote_tree))
    attested = (scratch / "plugin-tree.txt").read_bytes()
    if remote_tree.read_bytes() != attested:
        found = _first_difference(attested, remote_tree.read_bytes())
        raise Refusal(f"{remote} already has {tag}, holding another tree: {found}")
    code, answer = git_run(
        git_dir, "rev-parse", "--verify", "--end-of-options", f"{tagged}^{{commit}}"
    )
    commit = answer.removesuffix("\n")
    if code != 0 or not commit:
        raise Refusal(f"{remote}'s {tag} ({tagged}) names no commit")
    if held.get(MAIN) != commit:
        at = held.get(MAIN, "absent")
        raise Refusal(f"{remote}'s {tag} holds this tree at {commit}, but main is at {at}")
    return commit


def _scratch_repository(scratch: Path) -> Path:
    """An empty bare repository under `scratch`, for the commit to be built in."""
    git_dir = scratch / "plugin.git"
    # No template: the owner's `init.templateDir` could otherwise hand this repository hooks,
    # attributes or configuration of its own. No test reddens on its removal alone: a template's
    # attributes reach nothing past `hash-object --no-filters`, and its hooks nothing past the
    # push's `core.hooksPath`, which are the two lines the template would otherwise act through.
    code, _ = git_run(scratch, "init", "--bare", "--quiet", "--template=", str(git_dir))
    if code != 0:
        raise Refusal(f"git init --bare exited {code} in {scratch}")
    return git_dir


def _parent(git_dir: Path, remote: str, parent: str) -> None:
    """Refuse a `main` the fetch did not bring: one moved on the remote after it was listed."""
    code, _ = git_run(git_dir, "rev-parse", "--verify", "--end-of-options", f"{parent}^{{commit}}")
    if code != 0:
        raise Refusal(
            f"{remote}'s main was {parent} when it was listed, and the fetch that followed did "
            "not bring that commit: main moved on the remote in between. Nothing was pushed; "
            "run the command again"
        )


def _mktree(git_dir: Path, entries: list[tuple[str, str, str, str]]) -> str:
    """One tree object from `(mode, kind, object, name)` entries; `mktree` sorts them itself."""
    # Each name goes to git as the UTF-8 bytes the manifest holds, whatever the filesystem's
    # codec: `git_run` encodes `stdin` with that codec and `surrogateescape`, which `fsdecode`
    # undoes exactly.
    given = "".join(
        f"{mode} {kind} {obj}\t{os.fsdecode(name.encode('utf-8'))}\0"
        for mode, kind, obj, name in entries
    )
    code, answer = git_run(git_dir, "mktree", "-z", stdin=given, timeout=QUERY_TIMEOUT_SECONDS)
    tree = answer.removesuffix("\n")
    if code != 0 or not tree:
        raise Refusal(f"git mktree exited {code} in {git_dir}")
    return tree


def _build(
    git_dir: Path,
    rendered: Path,
    rows: list[tuple[str, str]],
    parent: str | None,
    paragraphs: tuple[str, ...],
) -> str:
    """The commit holding each rendered file at its manifest mode, and nothing else."""
    files = [str(rendered / path) for _, path in rows]
    code, answer = git_run(
        git_dir, "hash-object", "-w", "--no-filters", "--", *files, timeout=QUERY_TIMEOUT_SECONDS
    )
    blobs = answer_lines(answer)
    if code != 0 or len(blobs) != len(rows):
        raise Refusal(f"git hash-object exited {code} in {git_dir} over the rendered tree")
    directories: dict[str, list[tuple[str, str, str, str]]] = {"": []}
    for (mode, path), blob in zip(rows, blobs, strict=True):
        directory, _, name = path.rpartition("/")
        directories.setdefault(directory, []).append((mode, "blob", blob, name))
        while directory:
            directory = directory.rpartition("/")[0]
            directories.setdefault(directory, [])
    # Deepest first, so each directory's own tree exists before its parent's names it.
    for directory in sorted(directories, key=lambda d: d.count("/") + bool(d), reverse=True):
        if directory:
            above, _, name = directory.rpartition("/")
            tree = _mktree(git_dir, directories[directory])
            directories[above].append(("040000", "tree", tree, name))
    root_tree = _mktree(git_dir, directories[""])
    lineage = ("-p", parent) if parent is not None else ()
    message = [arg for paragraph in paragraphs for arg in ("-m", paragraph)]
    code, answer = git_run(git_dir, "commit-tree", root_tree, *lineage, *message)
    commit = answer.removesuffix("\n")
    if code != 0 or not commit:
        # `git_run` keeps git's stderr to itself, so git's own sentence is not here to quote.
        # The parent is known to be present (`_parent`), so the cause left is the identity, and
        # `git_run` hands git neither the environment's `GIT_AUTHOR_*` nor a scratch repository
        # any `includeIf "gitdir:…"` matches: only the global configuration's identity reaches it.
        raise Refusal(
            f"git commit-tree exited {code} in {git_dir} and wrote no commit; the commit is "
            "authored by the identity in your global git configuration, so set user.name and "
            "user.email there (git config --global): an identity from GIT_AUTHOR_* variables "
            'or from an includeIf "gitdir:…" section does not reach this script\'s git'
        )
    return commit


def publish(
    root: Path, tag: str, *, remote: str, yes: bool, runner: Runner, scratch: Path
) -> Published:
    """Publish the plugin tree `tag` names in `root` to `remote`'s `main` and `tag`, under `yes`.

    Each step refuses before the next runs, and everything before the push is local to
    `scratch`: the tag resolved to one commit; the tree rendered from it; the attestation
    verified; the remote's `main` and tag read (already published, or a refusal, when the tag is
    there); the commit built on `main` with plumbing; that commit read back whole and compared
    with the attested manifest; and only then, with `yes`, the atomic push.
    """
    sha, version = _tag_commit(root, tag)
    rendered, attested = scratch / "tree", scratch / "plugin-tree.txt"
    source = str(root.resolve())
    render = ("render", "--root", source, "--rev", sha, "--out", str(rendered))
    _plugin_tree(runner, root, *render, "--manifest-file", str(attested))
    _verify(runner, root, attested, tag, sha)
    expected = attested.read_bytes()
    rows = _manifest_rows(expected)
    git_dir = _scratch_repository(scratch)
    held = _remote_refs(runner, git_dir, remote, tag)
    tagged = held.get(f"refs/tags/{tag}")
    if tagged is not None:
        commit = _already(runner, root, scratch, remote, tag, held)
        return Published(tag, len(rows), commit, pushed=False, already=True)
    parent = held.get(MAIN)
    if parent is not None:
        _fetch(runner, git_dir, remote, MAIN)
        _parent(git_dir, remote, parent)

    paragraphs = (
        f"stayfixed {version}",
        f"Generated from {SOURCE_REPOSITORY} at {sha} ({tag}) by scripts/publish_plugin.py.",
    )
    commit = _build(git_dir, rendered, rows, parent, paragraphs)
    readback = scratch / "readback.txt"
    built = ("manifest", "--exact", "--root", str(git_dir), "--rev", commit)
    _plugin_tree(runner, root, *built, "--manifest-file", str(readback))
    if readback.read_bytes() != expected:
        found = _first_difference(expected, readback.read_bytes())
        raise Refusal(
            f"the commit built for {remote} reads back as another tree: {found}; nothing was pushed"
        )

    if yes:
        pushed = _network(
            runner,
            git_dir,
            "-c",
            "core.hooksPath=/dev/null",
            "push",
            "--atomic",
            "--quiet",
            "--end-of-options",
            remote,
            f"{commit}:{MAIN}",
            f"{commit}:refs/tags/{tag}",
        )
        if pushed.code != 0:
            raise Refusal(
                f"git push to {remote} exited {pushed.code}, and the push is atomic, so neither "
                f"main nor {tag} moved: {_said(pushed)}"
            )
    return Published(tag, len(rows), commit, pushed=yes, already=False)


# --- The command --------------------------------------------------------------------------------


def remote_argument(remote: str) -> str:
    """`remote` as git should be given it from the scratch repository, which is where every git
    that reaches it runs (`git -C`): a relative path to a local repository made absolute against
    the directory the command was run in, and anything else — a URL, an scp-like `host:path` —
    as it was given. git reads a colon before the first slash as scp-like, so this does too."""
    if "://" in remote or ":" in remote.split("/", 1)[0]:
        return remote
    path = Path(remote)
    return str(path.resolve()) if path.exists() and not path.is_absolute() else remote


def run_publish(args: argparse.Namespace) -> Result:
    remote = remote_argument(args.remote)
    with tempfile.TemporaryDirectory(prefix="stayfixed-publish-") as scratch:
        done = publish(
            ROOT,
            args.tag,
            remote=remote,
            yes=args.yes,
            runner=subprocess_runner(),
            scratch=Path(scratch),
        )
    data = {**asdict(done), "remote": remote}
    where = f"{done.files} files as {done.commit} to {remote}: main and {done.tag}"
    if done.already:
        return Result(f"already published: {where}; nothing was pushed", data)
    if done.pushed:
        return Result(f"pushed {where}", data)
    return Result(f"would push {where}; run again with --yes to push", data)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="scripts/publish_plugin.py",
        description="Push the plugin tree a release attested to the plugin's own repository.",
        epilog=JSON_EPILOG,
    )
    top.add_argument("--tag", required=True, help="the release's tag, vX.Y.Z")
    top.add_argument(
        "--remote", default=PLUGIN_REMOTE, help=f"the plugin repository (default {PLUGIN_REMOTE})"
    )
    top.add_argument(
        "--yes", action="store_true", help="push; without it, build and compare, and say what"
    )
    top.set_defaults(func=run_publish)
    return top


def main(argv: list[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv, parser=parser())


if __name__ == "__main__":
    sys.exit(main())
