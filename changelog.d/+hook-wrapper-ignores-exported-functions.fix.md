A shell function exported through the environment no longer stands in for a command the hook
wrapper runs. On macOS `/bin/sh` is bash 3.2, which defines a function from any variable named
`BASH_FUNC_<name>%%`, so a variable set for a hook could replace `pwd`, `cd`, `command`, `printf`
or `test` inside the wrapper, and run a program of its choosing before stayfixed's own checks,
with the hook's answer unchanged. The wrapper now drops every such function before its first
command, and writes each test as `test …` rather than `[ … ]`, a name bash 3.2 does not let it
drop. Shell options and dynamic-loader variables that a harness applies to the shell before the
wrapper's first line, such as `SHELLOPTS` with `PS4`, are the harness's to filter (`SECURITY.md`).
