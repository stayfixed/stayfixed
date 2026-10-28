A session on a machine without Python 3.11 or newer on `PATH` is now told that stayfixed is off.
Every hook used to say why on stderr alone, which neither you nor the model sees, so stayfixed was
silently off. Now, when there is no `python3` on `PATH` or the one there is older than 3.11, the
`SessionStart` hook shows you, and adds to the model's context, one line saying stayfixed's hooks
are off in this session and why, and to install Python 3.11 or newer on `PATH`. Every other hook
still exits 0 without a word on stdout.
