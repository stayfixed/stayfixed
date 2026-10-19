The note after a failed pytest run now also follows `py.test` and `poetry run pytest`, and no
longer takes `python script.py -m pytest`, which runs `script.py`, for a pytest run.
