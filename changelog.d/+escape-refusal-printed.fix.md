A bug entry's refusal of an unsupported escape in a frontmatter value, such as `\<ESC>` in a
`title`, now prints a character that does not print, an ESC or a line break, escaped rather than
raw, so it no longer reaches your terminal as a control sequence.
