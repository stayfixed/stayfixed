`stayfixed setup --git-hooks` now refuses, with exit `2`, a `prepare-commit-msg` hook already in
place whose text names `prepare-commit-msg.local`, such as one ending in
`exec "$(git rev-parse --git-common-dir)/hooks/prepare-commit-msg.local" "$@"`. It used to keep that
hook as `prepare-commit-msg.local` without reading it, where stayfixed's hook runs it last, and the
kept hook then ran itself: every `git commit` hung until it was killed. The refusal names the hook;
remove its chain line, or move it aside, and run the command again. A re-install refuses too when
the `.local` beside stayfixed's hook names itself, which already makes every commit run until it is
killed, and says so; it leaves the installed hook as it was. A chain spelled
`exec "$0.local" "$@"` does not run itself once kept, and is installed as before.
