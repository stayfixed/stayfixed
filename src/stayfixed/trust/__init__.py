"""Every approval a person gave on this machine, in one record the core keeps.

An approval is a person's say-so that something a repository authored may be used: a store of
notes committed to it, today. Each is one kind and one subject, and holds while what was approved
still hashes to the digest recorded for it. `record` keeps them all in `trust.json` beside the
machine file, never in an overlay and never under a directory an environment variable names.
Other packages import `stayfixed.trust.api`, never a module of this one.
"""
