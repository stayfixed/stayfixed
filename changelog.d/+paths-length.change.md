A `[paths]` value is now at most 1024 characters, the longest path macOS accepts. A longer one is
refused by every command, naming its key, and a session puts it back to the preset's: checking a
value of tens of thousands of components used to keep a `PreToolUse` hook past its timeout, which
let the call through unchecked.
