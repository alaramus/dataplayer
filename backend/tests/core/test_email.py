"""An email is written in its recipient's language (D227)."""

from app.core.config import settings
from app.core.email import (
    generate_new_account_email,
    generate_reset_password_email,
    generate_test_email,
)
from app.core.translation import LANGUAGES


def test_an_email_in_english_reads_as_it_always_did() -> None:
    email = generate_reset_password_email("a@example.com", "a@example.com", "token")

    assert email.subject == f"{settings.PROJECT_NAME} - Password recovery for user a@example.com"
    assert 'lang="en"' in email.html_content
    assert "Hi a@example.com," in email.html_content
    assert "This link will expire in" in email.html_content
    assert "All rights reserved." in email.html_content


def test_an_email_in_russian_is_russian_throughout() -> None:
    email = generate_new_account_email("b@example.com", "b@example.com", "secret", language="ru")

    assert email.subject == f"{settings.PROJECT_NAME} — новая учётная запись b@example.com"
    assert 'lang="ru"' in email.html_content
    assert f"Добро пожаловать в {settings.PROJECT_NAME}!" in email.html_content
    assert "Имя пользователя" in email.html_content
    assert "Welcome" not in email.html_content
    # What is data stays as it was given.
    assert "b@example.com" in email.html_content
    assert "secret" in email.html_content


def test_an_email_in_german_is_german_throughout() -> None:
    email = generate_new_account_email("d@example.com", "d@example.com", "secret", language="de")

    assert email.subject == f"{settings.PROJECT_NAME} – Neues Konto für d@example.com"
    assert 'lang="de"' in email.html_content
    assert f"Willkommen bei {settings.PROJECT_NAME}!" in email.html_content
    assert "Welcome" not in email.html_content
    # What is data stays as it was given.
    assert "d@example.com" in email.html_content
    assert "secret" in email.html_content


def test_every_email_renders_in_every_language() -> None:
    for language in LANGUAGES:
        for email in (
            generate_test_email("c@example.com", language=language),
            generate_reset_password_email("c@example.com", "c@example.com", "t", language=language),
            generate_new_account_email("c@example.com", "c@example.com", "p", language=language),
        ):
            assert email.subject
            assert "{{" not in email.html_content
