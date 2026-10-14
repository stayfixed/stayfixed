`stayfixed attach --machine` and `stayfixed detach --machine` run without a terminal are refused,
as before, with a reason of their own: such a command may be an agent's, and a repository can tell
an agent which file to name. The refusal used to say the flag followed the rule `STAYFIXED_CONFIG`
and `XDG_CONFIG_HOME` follow, two variables no stayfixed command reads to find that file.
