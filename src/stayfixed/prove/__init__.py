"""`prove`: run a test command and count what its runner reported.

The area holds the command (`commands.py`), the run and its verdict cascade and receipt
(`run.py`), the tree's state a receipt names (`tree.py`), and the readers: one per report format
(`junit.py`, `results.py`, `events.py`), each counting a runner's own report and never a line the
command printed, behind `reports.read_report`, with the counts they return (`counts.py`).
Consumers reach it through `api.py`. Deliberately empty of imports, so importing one module loads
no other.
"""
