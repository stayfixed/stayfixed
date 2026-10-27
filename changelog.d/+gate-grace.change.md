A custom gate that runs past `custom_timeout_seconds`, or is interrupted, now gets SIGTERM first
and SIGKILL only once its command has exited or 5 seconds have passed, where it used to get
SIGKILL at once. What the command started can end its own children in that grace, so a test
runner a gate starts no longer outlives the gate.
