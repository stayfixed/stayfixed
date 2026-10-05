`stayfixed setup` meeting a `~/.claude/settings.json` that is valid JSON nested deeper than Python's
parser follows, or that holds a number longer than Python converts to an integer (4,300 digits by
default), now fails saying so and naming the file (exit 1), and leaves the file as it was, instead
of ending with an internal error.
