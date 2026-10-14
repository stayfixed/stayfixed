`stayfixed setup` meeting a machine configuration file it is not allowed to read now fails
saying the file cannot be read (exit 1), as every other command does, instead of ending with an
internal error that quoted the operating system's message (exit 2).
