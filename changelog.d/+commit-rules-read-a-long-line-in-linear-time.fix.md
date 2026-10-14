`stayfixed commit check`, and `stayfixed commit strip`, which the `prepare-commit-msg` hook that
`stayfixed setup --git-hooks` installs runs on every commit, now read every commit message line in
time linear in its length, with the same verdicts. Two rules read some lines far more slowly than
that, so any commit message could stall the hook or a pull request's `commit check` in CI:

- a `-by:` trailer line padded with blanks: 160,000 of them took about two minutes, and a million
  would take over an hour;
- a line that opens like a generated-with footer and goes on into prose: one with 24 words that
  are both a name and a version, such as `A1`, took four to seven seconds, each further word
  doubled that, and one with 16,000 slashes took over a second.

They now also judge a trailer without keeping a record for each label of its address or each word
of a model's name: a trailer of a million of either took 120 MiB more memory to judge.
