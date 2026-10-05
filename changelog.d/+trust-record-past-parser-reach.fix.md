A `trust.json` beside the machine configuration that is nested deeper than Python's JSON parser
follows, or holds a number longer than Python converts to an integer (4,300 digits by default), is
now refused as a trust record that cannot be read, which nothing overwrites, as a record that is not
valid JSON already was. `stayfixed memory trust` used to end in an internal error on either. A
record that is not valid JSON is now worded "is not valid JSON: <where the parser stopped>" rather
than with that position in parentheses.
