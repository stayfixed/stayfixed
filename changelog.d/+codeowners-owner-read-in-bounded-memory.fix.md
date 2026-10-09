`stayfixed assess` now reads an email owner on a `CODEOWNERS` line without keeping a record for each
label of its domain: an owner of a million labels took 120 MiB more memory to read. The same owners
are read as before.
