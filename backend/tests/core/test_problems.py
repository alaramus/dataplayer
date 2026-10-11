"""A coded refusal: its shape on the wire and its catalogue (D225)."""

import string

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.problems import MESSAGES, PROBLEM_CODES, Problem


def test_every_code_has_its_english_and_nothing_else_does() -> None:
    assert set(MESSAGES) == set(PROBLEM_CODES)


def test_parameters_are_named_and_never_positional() -> None:
    """The browser fills a sentence by name; `{}` or `{0}` would arrive blank."""
    for code, template in MESSAGES.items():
        for _, field, _, _ in string.Formatter().parse(template):
            if field is not None:
                assert field.isidentifier(), (code, template)


async def test_a_problem_answers_with_its_code_parameters_and_english() -> None:
    application = FastAPI()

    @application.get("/refuse")
    async def refuse() -> None:
        raise Problem(404, "users.not_found")

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/refuse")

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "users.not_found",
            "params": {},
            "message": "User not found",
        }
    }


async def test_the_login_refusal_is_coded(client: AsyncClient) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "nobody@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "auth.wrong_credentials"
