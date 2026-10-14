`stayfixed test hygiene`, and the note after a failing pytest run, no longer hang on a `.pyc` file
that is a named pipe, or a symlink to one such as `/dev/stdin`: the stale-bytecode check now reads
a `.pyc` only when it is a regular file. A `.pyc` that is a symlink is no longer followed, so one
whose target lies outside the code roots is no longer counted as stale bytecode.
