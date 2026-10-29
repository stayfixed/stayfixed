`examples/stop-hook/prove_on_stop.py` is a Claude Code `Stop` hook that runs your test command
under `stayfixed prove` when the agent finishes, keeps it working on any verdict but `proved`, and
lets a stop through once `stop_hook_active` says the agent is already working on because of it. Its
README gives the settings snippet to add to your own `~/.claude/settings.json`. It costs one run of
the command on every stop that is not a continuation, a turn that edited nothing included, so a
fast selection of tests is yours to choose, and `proved` then covers only what that selection ran.
The agent it stops can edit the hook's settings file or weaken the tests, so it holds only as far as
your own install and the harness's sandbox keep the settings file out of the agent's writes.
