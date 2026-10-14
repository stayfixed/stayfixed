The hook wrapper now starts Python in isolated mode (`-I`), both when it checks a candidate
interpreter's version and when it runs stayfixed. Before, a `PYTHONPATH`, `PYTHONHOME` or
`PYTHONUSERBASE` reaching a hook — including from a repository's `.claude/settings.json` `env`
block, which stayfixed treats as untrusted — could make Python import code of the repository's
choosing (a `sitecustomize` or `usercustomize`) before stayfixed's first line ran. Python now
reads none of its `PYTHON*` environment variables, loads no user site and puts neither the
working directory nor the script's own directory on `sys.path` inside a hook; stayfixed itself
still sees the whole environment. If you relied on one of those variables to change how a hook's
Python starts, that no longer has any effect.
