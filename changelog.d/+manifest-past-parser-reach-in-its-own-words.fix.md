A `.stayfixed/manifest.json` nested deeper than Python's JSON parser follows, or holding a number
longer than Python converts to an integer (4,300 digits by default), is now refused by `stayfixed
upgrade`, `uninstall` and every other command that reads it with a sentence about the file: it "is
nested deeper than this reader follows" or "holds a number longer than this reader converts". The
refusal used to quote Python's own error, which for the long number told the reader to raise an
interpreter limit. A manifest that is not valid JSON is now said to be "not valid JSON" rather than
"unreadable".
