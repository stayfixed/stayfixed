"""Contracts for the shared Bash-scanning module the guards import."""

from __future__ import annotations

import pytest

from stayfixed.guards import bashscan


def test_quoted_heredoc_bodies_are_stripped_but_the_command_remains() -> None:
    """A QUOTED delimiter's body is data the shell does not expand — this is the property
    that keeps this repository's own guard fixtures authorable."""
    cmd = "cat > tests/x.py <<'EOF'\nsecret .env mention\nEOF\necho done"
    stripped = bashscan.strip_heredocs(cmd)
    assert ".env" not in stripped
    assert "echo done" in stripped


def test_unquoted_heredoc_bodies_stay_visible() -> None:
    """The inversion of the old `strip_heredocs` contract. An UNQUOTED delimiter's body is
    expanded by the shell, and — when the heredoc is a shell's stdin — executed. Deleting it
    before any check ran is what made `bash <<EOF` / `cat secrets/.env` / `EOF` allowed."""
    cmd = "bash <<EOF\ncat secrets/.env\nEOF\necho done"
    stripped = bashscan.strip_heredocs(cmd)
    assert ".env" in stripped
    assert "echo done" in stripped


def test_unterminated_quoted_heredoc_strips_to_the_end() -> None:
    cmd = "cat <<'EOF'\nline .env"
    assert ".env" not in bashscan.strip_heredocs(cmd)


def test_unterminated_unquoted_heredoc_keeps_its_body() -> None:
    cmd = "bash <<EOF\ncat secrets/.env"
    assert ".env" in bashscan.strip_heredocs(cmd)


def test_heredocs_are_reported_with_their_header_and_quoting() -> None:
    cmd = "bash <<EOF\ncat secrets/.env\nEOF"
    _, heredocs = bashscan.prepare(cmd)
    assert len(heredocs) == 1
    assert heredocs[0].tag == "EOF"
    assert heredocs[0].quoted is False
    assert heredocs[0].header == "bash <<EOF"
    assert heredocs[0].body == "cat secrets/.env"


def test_a_quoted_body_is_still_reported_even_though_it_is_stripped() -> None:
    """Quoting suppresses expansion, never execution: `bash <<'EOF'` runs its body. The text
    half may drop it; the reported list may not, or a caller cannot judge what runs."""
    _, heredocs = bashscan.prepare("bash <<'EOF'\ncat secrets/.env\nEOF")
    assert [(h.quoted, h.body) for h in heredocs] == [(True, "cat secrets/.env")]


def test_backslash_delimiter_counts_as_quoted() -> None:
    _, heredocs = bashscan.prepare("cat <<\\EOF\nbody\nEOF")
    assert [h.quoted for h in heredocs] == [True]


def test_two_heredocs_on_one_line_are_consumed_in_order() -> None:
    cmd = "cat <<'A' <<B\nfirst .env\nA\nsecond secrets/.env\nB"
    text, heredocs = bashscan.prepare(cmd)
    assert [(h.tag, h.quoted) for h in heredocs] == [("A", True), ("B", False)]
    assert "first" not in text
    assert "second" in text


def test_tokenize_keeps_redirects_and_separators() -> None:
    tokens = bashscan.tokenize("echo x > f && cat f")
    assert tokens == ["echo", "x", ">", "f", "&&", "cat", "f"]


def test_tokenize_returns_none_on_unbalanced_quotes() -> None:
    assert bashscan.tokenize("echo 'unterminated") is None


def test_segments_split_on_every_separator() -> None:
    tokens = bashscan.tokenize("a b; c | d && e")
    assert tokens is not None
    assert bashscan.segments(tokens) == [["a", "b"], ["c"], ["d"], ["e"]]


def test_arithmetic_shift_with_spaces_is_not_a_heredoc() -> None:
    cmd = "count=$((1 << 3))\nrm -rf .env\necho done"
    stripped = bashscan.strip_heredocs(cmd)
    assert ".env" in stripped
    assert "echo done" in stripped


def test_arithmetic_shift_without_spaces_is_not_a_heredoc() -> None:
    cmd = "x=$(( 1<<3 ))\ncat secrets/.env"
    assert ".env" in bashscan.strip_heredocs(cmd)


def test_here_string_is_not_a_heredoc() -> None:
    cmd = "echo a <<< word\ncat secrets/.env"
    assert ".env" in bashscan.strip_heredocs(cmd)


def test_a_mid_word_hash_does_not_truncate_the_command() -> None:
    """`shlex`'s own `commenters` ends a token at ANY unquoted `#`, so this command
    tokenized to `['echo', 'a']` and everything after it was invisible to every check."""
    tokens = bashscan.tokenize("echo a#b && cat secrets/.env")
    assert tokens is not None
    assert "secrets/.env" in tokens


def test_a_hash_inside_a_path_argument_survives() -> None:
    assert bashscan.tokenize("git add notes#1.md") == ["git", "add", "notes#1.md"]


def test_a_real_comment_is_removed() -> None:
    tokens = bashscan.tokenize("ls # do not cat secrets/.env")
    assert tokens == ["ls"]


def test_a_hash_inside_quotes_is_not_a_comment() -> None:
    assert bashscan.tokenize('git log --format="%h#%s"') == ["git", "log", "--format=%h#%s"]


def test_a_commented_out_heredoc_does_not_swallow_the_next_line() -> None:
    """`echo hi # <<'EOF'` is a comment, not a redirect. Recognising it as one would delete
    every following line, including the real command a shell would go on to run."""
    text, heredocs = bashscan.prepare("echo hi # <<'EOF'\ncat secrets/.env\nEOF")
    assert heredocs == []
    assert ".env" in text


def test_a_newline_separates_commands_the_way_a_semicolon_does() -> None:
    """`shlex` with `whitespace_split` discards a newline as ordinary whitespace, so a
    multi-line command collapsed into ONE segment whose argv0 was the FIRST line's program.
    Token-based checks survived that; every argv0-keyed one — including the edit-gated
    boundary protecting this module — judged `rm scripts/guard.py` as if it were
    `echo`. `;` denied and `\\n` allowed, one character apart.

    The second half is the same contract read the other way: a newline the shell keeps as a
    literal character of a word is not a separator, or `git commit -m "two\\nlines"` would
    segment into two commands.
    """
    tokens = bashscan.tokenize("echo hi\nrm scripts/guard.py")
    assert tokens is not None
    assert bashscan.segments(tokens) == [
        ["echo", "hi"],
        ["rm", "scripts/guard.py"],
    ]
    quoted = bashscan.tokenize('git commit -m "first line\nsecond line"')
    assert quoted == ["git", "commit", "-m", "first line\nsecond line"]


def test_a_heredoc_tag_inside_a_quoted_string_is_not_a_redirect() -> None:
    """`_HEREDOC.finditer` ran against the raw line, so a `<<'TAG'` that merely APPEARED
    inside a quoted string was taken for a real quoted heredoc and every following line was
    deleted from the text every check reads — the one thing this module must never do.
    `git commit -m "note <<'E' "` is a plausible command, so this was reachable by accident
    and not only on purpose.
    """
    text, heredocs = bashscan.prepare("git commit -m \"note <<'E' \"\ncat secrets/.env")
    assert heredocs == []
    assert "secrets/.env" in text


def test_a_newline_after_a_separator_arrives_as_its_own_token() -> None:
    """The newline's separator must not fuse with a separator the user typed.

    `shlex`'s `punctuation_chars` mode emits a RUN of adjacent punctuation as ONE token, so
    an unpadded `;` written straight after a line already ending in `;` produces `;;` —
    which is not in `_SEPARATORS`, so `segments` does not split there and the multi-line
    hole reopens for any command whose previous line ends in shell punctuation. A trailing
    semicolon is not obfuscation, which is what makes this worth pinning.
    """
    tokens = bashscan.tokenize("echo hi;\nrm scripts/guard.py")
    assert tokens is not None
    assert tokens.count(";") == 2  # the typed one and the newline's, never fused into `;;`
    assert bashscan.segments(tokens) == [
        ["echo", "hi"],
        ["rm", "scripts/guard.py"],
    ]


def test_an_unbalanced_quote_does_not_hide_a_real_heredoc() -> None:
    """Quote tracking across lines is only as good as its own premise.

    When the quotes do not balance, "this `<<` is inside a string" is an unreliable claim,
    and acting on it hides a REAL heredoc: its body never reaches the caller's list, so a
    caller that judges a shell body as a program never sees this one. The scan therefore
    abandons the quote-aware pass and redoes it unaware whenever the pass ends still inside a
    quote — bash will not run an unbalanced command either, so nothing a shell would execute
    loses the quote-aware answer.
    """
    _, heredocs = bashscan.prepare("echo \"unbalanced\nbash <<'EOF'\nrm scripts/guard.py\nEOF")
    assert [(h.tag, h.quoted, h.body) for h in heredocs] == [("EOF", True, "rm scripts/guard.py")]


def test_a_fused_punctuation_run_still_separates_commands() -> None:
    """A separator welded to its neighbour is still a separator.

    `punctuation_chars` fuses adjacent punctuation, so `);`, `;;`, `&;`, `));` and `;>` are
    none of them members of `_SEPARATORS` and `segments` carried straight past them into one
    segment — the same argv0-blindness as the newline defect, reached with an ordinary typed
    `;` and no newline anywhere.

    The second assertion is the part most likely to break when this is changed: the boundary
    check finds a write target by looking at `segment[index - 1]`, so the `>` of a fused `;>`
    has to end up at the FRONT of the segment it opens. Before, `;>` matched neither a
    separator nor a redirect operator, and the write was invisible to both checks at once.
    """
    tokens = bashscan.tokenize("(cd /tmp); rm scripts/guard.py")
    assert tokens is not None
    assert bashscan.segments(tokens) == [
        ["(", "cd", "/tmp", ")"],
        ["rm", "scripts/guard.py"],
    ]
    redirected = bashscan.tokenize("echo hi;>scripts/guard.py")
    assert redirected is not None
    assert bashscan.segments(redirected) == [
        ["echo", "hi"],
        [">", "scripts/guard.py"],
    ]
    # a redirect operator that CONTAINS a separator character must survive whole
    compound = bashscan.tokenize("ls /x &>/tmp/out.log")
    assert compound is not None
    assert bashscan.segments(compound) == [["ls", "/x", "&>", "/tmp/out.log"]]


# --- 2026-08-23 security fix: `\<newline>` line continuations ------------------------------


def test_line_continuation_outside_quotes_is_joined() -> None:
    """`shlex` strips the backslash but leaves the newline inside the token, so
    `secrets/\\<newline>.env` never equalled `secrets/.env` until this pass joined it
    first — verified against real bash: `cat secrets/\\<newline>.env` reads the file."""
    tokens = bashscan.tokenize("cat secrets/\\\n.env")
    assert tokens == ["cat", "secrets/.env"]


def test_line_continuation_splitting_the_verb_is_joined() -> None:
    tokens = bashscan.tokenize("ca\\\nt secrets/.env")
    assert tokens == ["cat", "secrets/.env"]


def test_two_line_continuations_in_one_argument_are_both_joined() -> None:
    tokens = bashscan.tokenize("cat sec\\\nrets/\\\n.env")
    assert tokens == ["cat", "secrets/.env"]


def test_line_continuation_inside_double_quotes_is_joined() -> None:
    """Bash strips `\\<newline>` inside double quotes exactly as it does outside them —
    verified with `bash -c 'echo "secrets/\\<newline>.env"'`, which prints the joined
    path. `\\<newline>` is one of the five sequences double quotes still give backslash
    special meaning for (alongside `\\"`, `\\\\`, `\\$`, and `` \\` ``)."""
    tokens = bashscan.tokenize('echo "secrets/\\\n.env"')
    assert tokens == ["echo", "secrets/.env"]


def test_line_continuation_inside_single_quotes_is_left_alone() -> None:
    """The one direction stripping must NOT take: inside `'...'` bash gives backslash no
    special meaning at all, so `\\<newline>` stays two literal characters — verified with
    `bash -c "echo 'secrets/\\<newline>.env'" | od -c`, where both the backslash and the
    newline survive in the printed argument. Stripping it anyway would make the guard see
    `secrets/.env` for an argument bash never produces — a false denial, and proof the
    guard would be running on a different command than the one that executes."""
    tokens = bashscan.tokenize("echo 'secrets/\\\n.env'")
    assert tokens == ["echo", "secrets/\\\n.env"]


def test_line_continuation_does_not_apply_inside_a_comment() -> None:
    """A backslash has no special meaning inside a comment — verified against real bash:
    `echo hi # comment \\<newline>rm ...` still runs `rm ...` as its own statement, because
    the comment ends at the literal newline regardless of what precedes it. Stripping
    continuations before comments are recognised would glue this "comment" to the next
    line and hide a real command inside it — the reverse of what this fix is for, so the
    two passes must run in this order and this line must still split into two segments."""
    tokens = bashscan.tokenize("echo hi # comment \\\nrm scripts/guard.py")
    assert tokens is not None
    assert bashscan.segments(tokens) == [["echo", "hi"], ["rm", "scripts/guard.py"]]


def test_an_escaped_backslash_before_a_newline_is_not_a_continuation() -> None:
    """`\\\\` outside quotes is an escaped backslash — bash consumes the pair into one
    literal `\\`, which leaves the following newline unescaped and therefore a REAL
    separator, not a continuation. Verified against real bash: `echo a\\\\` + newline +
    `b` prints `a\\` and then fails to run `b` as a separate, unjoined command — the
    opposite of `echo a\\\\\\` + newline + `b`, which bash joins into `echo a\\b`. Both
    shapes are pinned here because they exercise the same escape-parity the module's other
    passes already rely on, and a continuation pass that got this backward would silently
    re-open the exact hole this fix closes for any argument built by doubling a backslash."""
    two_backslashes = bashscan.tokenize("echo a\\\\\nrm scripts/guard.py")
    assert two_backslashes is not None
    assert bashscan.segments(two_backslashes) == [
        ["echo", "a\\"],
        ["rm", "scripts/guard.py"],
    ]
    three_backslashes = bashscan.tokenize("echo a\\\\\\\nb")
    assert three_backslashes == ["echo", "a\\b"]


def test_a_trailing_continuation_with_nothing_after_it_elides_to_nothing() -> None:
    """A continuation as the very last two characters of the command has nothing to join
    onto — it still elides, leaving a shorter but perfectly ordinary, parseable command
    rather than a dangling escape. This is a different shape from a bare trailing
    backslash with NO newline at all, which was already, and remains, unparseable
    (`test_tokenize_returns_none_on_unbalanced_quotes`'s sibling case) — unaffected by
    this fix either way, since there is no newline for it to pair with."""
    tokens = bashscan.tokenize("echo a\\\n")
    assert tokens == ["echo", "a"]


def test_line_continuation_inside_a_quoted_heredoc_body_is_left_alone() -> None:
    """A quoted-delimiter heredoc body gets no expansion at all, so bash performs no
    continuation-joining inside it either — verified: `cat <<'EOF'` with a body
    continuation keeps both the backslash and the newline. The body is already absent from
    `prepare`'s text (quoted bodies are stripped by `scan_heredocs`), so this pass has
    nothing to do here and the reported body must come back untouched."""
    _, heredocs = bashscan.prepare("cat <<'EOF'\nfoo\\\nbar\nEOF")
    assert [h.body for h in heredocs] == ["foo\\\nbar"]


# --- `heredoc_body_end`, the offset scan a caller inside a `$(...)` needs ------------------


def test_heredoc_body_end_steps_over_a_body_to_its_terminator() -> None:
    """The offset handed back is just PAST the terminator line, so a caller resumes on the
    next line rather than on the `EOF` it must not read as command text."""
    text = "cat <<'EOF'\nbody\nEOF\n)"
    end = bashscan.heredoc_body_end(text, text.index("<<"))
    assert end is not None
    assert text[end:] == ")"


def test_heredoc_body_end_ignores_quotes_and_parens_in_the_body() -> None:
    """The whole point: a body is DATA, so an apostrophe opens nothing and a paren nests
    nothing. Both characters appear in the body below and neither moves the answer."""
    text = "cat <<'EOF'\nfix(guard): the lexer's contract\nEOF\n)"
    end = bashscan.heredoc_body_end(text, text.index("<<"))
    assert end is not None
    assert text[end:] == ")"


def test_heredoc_body_end_accepts_every_delimiter_spelling() -> None:
    """`<<'TAG'`, `<<"TAG"`, `<<\\TAG` and a bare `<<TAG` are all redirects; quoting decides
    expansion, not whether a body is there to step over. `<<-` strips leading tabs from the
    terminator line, which `.strip()` already tolerates."""
    for header, terminator in (
        ("<<'EOF'", "EOF"),
        ('<<"EOF"', "EOF"),
        ("<<\\EOF", "EOF"),
        ("<<EOF", "EOF"),
        ("<<-EOF", "\tEOF"),
    ):
        text = f"cat {header}\nbody\n{terminator}\n)"
        end = bashscan.heredoc_body_end(text, text.index("<<"))
        assert end is not None, header
        assert text[end:] == ")", header


def test_heredoc_body_end_answers_none_without_a_terminator_line() -> None:
    """Deliberately NOT the "run to the end" answer `scan_heredocs` gives an unterminated
    body. This function's caller scans text `prepare` has already stripped, so the common
    way to reach a `<<TAG` with no terminator is a heredoc that was found and removed
    normally, leaving its header behind — and consuming to the end there swallows whatever
    delimiter the caller was counting. `None` means "nothing to step over"."""
    assert bashscan.heredoc_body_end("cat <<'EOF'\n)", 4) is None
    assert bashscan.heredoc_body_end("cat <<'EOF'", 4) is None


def test_heredoc_body_end_answers_none_where_there_is_no_redirect() -> None:
    """A herestring has no body, and neither of its later `<` characters may be mistaken for
    the start of one; an ordinary comparison is not a redirect either."""
    for text, index in (
        ("cat <<<'word'", 4),
        ("cat <<<'word'", 5),
        ("cat <<<'word'", 6),
        ("test 1 < 2", 7),
        ("echo a", 0),
    ):
        assert bashscan.heredoc_body_end(text, index) is None, (text, index)


def test_heredoc_body_end_accepts_a_redirect_glued_to_the_preceding_word() -> None:
    """`cat<<'EOF'` and `2<<EOF` are both valid bash -- the first an ordinary no-space
    spelling, the second a file descriptor -- and `_HEREDOC`'s lookbehind used to reject a
    word character before `<<`, so the heredoc-offset fix reached only the spacing it happened
    to be written with. The `<` half of that lookbehind is kept and pinned by
    `test_heredoc_body_end_answers_none_where_there_is_no_redirect`."""
    for header in ("cat<<'EOF'", "2<<EOF", "cat 2<<EOF"):
        text = f"{header}\nbody\nEOF\n)"
        end = bashscan.heredoc_body_end(text, text.index("<<"))
        assert end is not None, header
        assert text[end:] == ")", header


def test_arithmetic_shift_is_not_taken_for_a_heredoc() -> None:
    """The control for relaxing that lookbehind: `$((1<<2))` must stay unmatched. It is the
    trailing `(?!\\S)` that rejects it -- `)` follows the tag -- not the lookbehind, which is
    why relaxing the lookbehind does not reach it."""
    for text in ("$((1<<2))", "echo $((n<<3))"):
        assert bashscan.heredoc_body_end(text, text.index("<<")) is None, text


def test_scan_heredocs_finds_a_glued_redirect() -> None:
    """The same relaxation seen through the caller that shares `_HEREDOC`: a quoted body
    leaves the general text and is still REPORTED, so `bgcleanup._nested_programs` can judge
    it."""
    stripped, heredocs = bashscan.prepare("bash<<'EOF'\ncat secrets/.env\nEOF")
    assert "secrets/.env" not in stripped
    assert [h.body for h in heredocs] == ["cat secrets/.env"]


def test_heredoc_body_end_tolerates_an_indented_terminator_without_a_dash() -> None:
    """`heredoc_body_end` compares `line.strip()` to the tag. The docstring justifies that
    by `<<-`, which strips leading tabs -- but the leniency applies to every heredoc, so it
    is pinned here for a plain `<<` too rather than left as an unasserted claim."""
    text = "cat <<'EOF'\nbody\n   EOF\n)"
    end = bashscan.heredoc_body_end(text, text.index("<<"))
    assert end is not None
    assert text[end:] == ")"


# --- `command_words`, moved here because two guards need the same argv0 resolution ---------


def test_command_words_strips_a_leading_assignment_and_wrapper() -> None:
    """`Path(segment[0]).name` alone missed `PYTHONPATH=src pytest` and `FOO=1 BAR=2 pytest`
    entirely, so an argv0 test saw the assignment instead of the program."""
    assert bashscan.command_words(["FOO=1", "env", "sleep", "3"]) == ["sleep", "3"]


def test_command_words_strips_uv_run_with_nothing_before_the_program() -> None:
    """CI's own invocation shape, with nothing between `uv run` and the program it launches.
    Oracle: `mutations/`, "`uv run` stops being stripped off a segment"."""
    assert bashscan.command_words(["uv", "run", "pytest"]) == ["pytest"]


@pytest.mark.parametrize(
    ("command", "program"),
    [
        # The shapes the README, the `attribute-failure` skill and `docs/cli.md` recommend.
        ("uv run --locked pytest -q", ["pytest", "-q"]),
        ("uv run --locked pytest tests/x.py::t", ["pytest", "tests/x.py::t"]),
        # `--` ends uv's options, and the word after it is the program whatever it looks like.
        ("uv run -- pytest", ["pytest"]),
        ("uv run -- -x", ["-x"]),
        # A lone `-` is the program too: uv reads the script from standard input (measured).
        ("uv run --no-project -", ["-"]),
        # uv's global options may stand before `run`, with their values.
        ("uv --quiet run pytest", ["pytest"]),
        ("uv -n --directory . run pytest", ["pytest"]),
        ("uv --directory run run pytest", ["pytest"]),
        # A value-taking option takes its value, as the next word or fused to it.
        ("uv run --python 3.11 pytest", ["pytest"]),
        ("uv run --python=3.11 pytest", ["pytest"]),
        ("uv run -p 3.11 pytest", ["pytest"]),
        ("uv run -p3.11 pytest", ["pytest"]),
        ("uv run -np3.11 pytest", ["pytest"]),
        # Stacked short flags are one word.
        ("uv run -qq --frozen pytest", ["pytest"]),
        # The first word that is not an option is the program, and every later word is its own.
        ("uv run --frozen echo --locked", ["echo", "--locked"]),
        ("uv run env FOO=1 pytest", ["pytest"]),
        ("uv run", []),
    ],
)
def test_command_words_strips_uv_run_past_uvs_own_options(command: str, program: list[str]) -> None:
    """`uv run --locked pytest`, the shape the documentation recommends, used to arrive as
    `--locked pytest`, so no hint recognised the run and the red-run notice said nothing at
    all. uv's options are read by its own tables (`uv --help`, `uv run --help`), so the word
    `uv run` launches is the one resolved. Oracle: `mutations/`, "uv's global options stop
    being skipped before `run`", "`--` stops ending uv's options", "a lone `-` is read as a uv
    option", "a fused short value stops being one word"."""
    assert bashscan.command_words(command.split()) == program


@pytest.mark.parametrize(
    "command", ["uv run -m pytest -q", "uv run -qm pytest", "uv run --script tests/run.py"]
)
def test_a_module_or_script_uv_runs_is_the_program_only_to_a_caller_that_asks(
    command: str,
) -> None:
    """The word after `-m` or `--script` is a module or a file, never a program on the path,
    so by default the command stays whole: the conservative reading, which a guard that judges
    the program inherits without having to remember a flag. A caller asking which runner ran
    (`modules_as_programs=True`, the red-run hint) reads `-m pytest` as `pytest`. Oracle:
    `mutations/`, "a module or script name reads as the program by default", "a module or
    script name is never read as what uv runs"."""
    words = command.split()
    assert bashscan.command_words(words) == words
    assert bashscan.command_words(words, modules_as_programs=True) == words[3:]


@pytest.mark.parametrize(
    ("command", "program"),
    [
        ("uv run --with pytest echo hi", ["echo", "hi"]),
        ("uv run -w pytest echo hi", ["echo", "hi"]),
        ("uv --cache-dir pytest run echo hi", ["echo", "hi"]),
    ],
)
def test_command_words_never_reads_a_uv_options_value_as_the_program(
    command: str, program: list[str]
) -> None:
    """The wrong-note direction: `--with pytest` names a package, and `echo` is what runs. An
    option that takes a value and was read as a flag would make `pytest` the program and hand
    a pytest note to an `echo`. Oracle: `mutations/`, "a value-taking uv option stops taking
    the next word"."""
    assert bashscan.command_words(command.split()) == program


@pytest.mark.parametrize(
    "command",
    [
        # An option in neither table: uv's hidden and future options among them.
        "uv run --frobnicate pytest",
        "uv run -x pytest",
        "uv run -nx pytest",
        # A flag given a value is not a flag uv accepts.
        "uv run --locked=yes pytest",
        # `-h` prints uv's help, and the word after it never runs.
        "uv run -h pytest",
        # `run`'s own options are refused before `run` (measured: uv exits 2).
        "uv --locked run pytest",
        "uv --python 3.11 run pytest",
        # Another uv command launches nothing.
        "uv sync --locked",
        "uv --quiet",
    ],
)
def test_command_words_leaves_a_uv_command_it_cannot_read_whole(command: str) -> None:
    """The under-report, kept where it is still the safe direction: an option this scanner
    cannot classify might take a value, and guessing it a flag reads that value as the program
    (`--with pytest echo` would become a pytest run). So such a command is left as written and
    its program is `uv`, which no hint recognises and no guard refuses. Oracle: `mutations/`,
    "an unknown uv option is read as a flag", "an unknown short uv option is read as a flag", "a
    uv flag given a value is read as a flag", "`run`'s options are skipped before `run`", "a uv
    command other than `run` is unwrapped", "a uv command that never reaches `run` is
    unwrapped"."""
    assert bashscan.command_words(command.split()) == command.split()
