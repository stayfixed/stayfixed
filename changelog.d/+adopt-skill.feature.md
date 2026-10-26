The adoption is a skill of its own, `adopt`, which `init` offers as its last step and which can be
invoked on its own in a later session or in a clone of an adopted repository. Its first step runs
`stayfixed assess --builtin`, so no command the repository configures runs before you are asked:
when that run names custom gates it left out, the skill names them, says the next command runs
their commands on this machine and waits for an explicit yes, and silence, a timeout or an empty
answer is a no that holds for every later command of the adoption. It no longer depends on the
`note:` `init` prints about a kept `stayfixed.toml`'s custom gates.
