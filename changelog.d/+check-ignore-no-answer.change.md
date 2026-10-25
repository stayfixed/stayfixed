`stayfixed init`, `upgrade` and `uninstall` refuse, with nothing written, whenever
`git check-ignore` cannot say whether a file the run would write or remove at a place a `[paths]`
value chose is ignored: when it times out, is not installed, or fails on the batch, as it does
when one path lies inside a submodule. That is 0.3.1's behaviour and its refusal, which says to
run the command again once `git check-ignore` works; it is kept because a repository can make
`git check-ignore` time out (git reads every `.gitignore` along each path it is asked about), so
giving way to a timeout would let a pulled commit write to a git-ignored file such as `.env`.
