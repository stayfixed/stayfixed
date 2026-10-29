`examples/stop-hook/prove_on_stop.py` is a Claude Code `Stop` hook that runs your test command
under `stayfixed prove` when the agent finishes, keeps it working on any verdict but `proved`, and
lets a stop through once `stop_hook_active` says the agent is already working on because of it. Its
README gives the settings snippet to add to your own `~/.claude/settings.json`. It costs one run of
the command on every stop that is not a continuation, a turn that edited nothing included, so a
fast selection of tests is yours to choose, and `proved` then covers only what that selection ran.
The adversary is the agent's "done", and the agent can edit the hook's settings file or weaken the
tests, so the anchor is your own install and the harness's sandbox; even then the recipe is a
convenience, not a control. It sends the agent on at most once per stop and stops no agent that
means to finish, and the check that holds is your project's own CI run of its tests.
