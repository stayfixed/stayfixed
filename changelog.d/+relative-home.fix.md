A relative `HOME` now names no home directory, as an empty one does: `setup`, `attach` and `detach`
refuse, and no command reads or writes a machine file or a trust record under the directory it
happens to run from. Taken as typed, `HOME=h` gave every working directory a machine file of its
own, and a hook run inside a clone read one the clone could commit.
