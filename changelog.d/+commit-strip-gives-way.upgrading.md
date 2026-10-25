`stayfixed commit strip`, which the commit-message hook runs, now leaves a message's attribution
lines in place when your own Claude Code settings (`~/.claude/settings.json`) set
`attribution.commit` to text: what your commits carry is then the choice you made in the harness,
and the hook prints `kept N attribution line(s)` with that reason. It is all or nothing: every line
the strip would have taken is kept, not only the one the setting names. Set empty, or to
whitespace alone, the setting says your commits carry nothing, and the hook strips a trailer that
arrives anyway, as before; a message with nothing to strip prints `nothing to strip`, which the
hook keeps off the terminal, whatever the setting. To have every trailer stripped as in 0.3.1,
take `attribution.commit` out of your settings or set it empty.
