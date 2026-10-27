The adoption, a step of the `init` skill in 0.3.1, is a skill of its own, `adopt`, which `init`
offers as its last step and which can be
invoked on its own in a later session or in a clone of an adopted repository. Every command it
names that runs gates takes `--builtin`, so no command the repository configures runs, unless you
said yes in that session: its first step runs `stayfixed assess --builtin`, names every custom
gate that run left out, says the command without the flag runs their commands on this machine and
waits for your explicit yes; silence, a timeout or an empty answer is a no, and a yes lasts only
for that session. A `--builtin` run that prints no summary stops the adoption until its cause is
cleared.
