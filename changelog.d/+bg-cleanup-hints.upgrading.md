The `bg-cleanup` session guard no longer refuses a backgrounded `Bash` call: a leaked `&` job or a
leading `sleep` now gets a hint naming the remedy, and the call runs. A trailing `wait` counts as
cleanup. `stayfixed guard bg-cleanup` is gone, so a script or CI step that called it must drop the
call.
