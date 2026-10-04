When a profile's check fails, `stayfixed test hygiene` now refuses (exit 2) naming the profile and
the kind of error, where before it printed the error's own message: on Python 3.11 a directory
name too long to open reached the output whole, so a repository could put text of its choosing
there.
