from __future__ import annotations

import pytest

from stayfixed.envfiles import is_env_file


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        ".env.prod",
        ".env.production.local",
        # A name no deny rule in the preset lists, which only this answer refuses.
        ".env.preprod",
        # A template suffix that is not the last one is not a template.
        ".env.example.local",
        # Case-folded: on macOS and Windows `.ENV` opens the file `.env` does.
        # Mutation: `mutations/`'s "an env file is compared exactly, not case-folded".
        ".ENV",
        ".Env.Prod",
    ],
)
def test_an_env_file_is_one(name: str) -> None:
    # Mutation: `mutations/`'s "nothing named .env.<x> is an env file" -> `.env.prod` and the
    # rest of the dotted names are let through.
    assert is_env_file(name)


@pytest.mark.parametrize(
    "name",
    [
        # The templates a project commits for an agent to read and keep in step with the code.
        # Mutation: `mutations/`'s "a template is an env file" -> all of these are refused.
        ".env.example",
        ".env.prod.example",
        ".env.sample",
        ".env.template",
        ".ENV.EXAMPLE",
        # Names that only look like one.
        "env",
        ".envrc",
        ".environment",
        "app.env",
        "",
    ],
)
def test_a_template_or_another_file_is_not(name: str) -> None:
    assert not is_env_file(name)
