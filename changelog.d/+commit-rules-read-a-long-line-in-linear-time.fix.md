`stayfixed commit check`, and `stayfixed commit strip`, which the `prepare-commit-msg` hook that
`stayfixed setup --git-hooks` installs runs on every commit, now read a commit message line that
holds a `-by:` trailer in time linear in its length. The value was found by a pattern that
rescanned the blanks inside it from every character, so a trailer line padded with 160,000 blanks
took about two minutes, and one with a million blanks over an hour: any commit message could stall
the hook or a pull request's `commit check` in CI. The verdicts are unchanged.
