`stayfixed commit check` now refuses a `-by:` trailer whose name is `ChatGPT` or `Cursor`, such as
`Assisted-by: ChatGPT` or `Generated-by: Cursor`, which it documented as attribution and let
through. `stayfixed commit strip`, and with it the `prepare-commit-msg` hook, reads the same table,
so it now strips these lines too. A name is judged whole, as before: a person whose name holds one
of the words, such as `Cursor Smith`, is not refused.
