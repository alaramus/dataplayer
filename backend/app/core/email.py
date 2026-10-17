import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import emails
from jinja2 import Template

from app.core.config import settings
from app.core.locales.ru import MESSAGES as RU
from app.core.translation import N_, Language, in_language, register, say

logger = logging.getLogger(__name__)

# Templates live in the app package, one level above this module.
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "email-templates"

# One template per email, its sentences written `{{ say("…") }}`: a copy of
# the markup per language would be as many copies to keep in step (D227).
register("ru", RU)

TEST_SUBJECT = N_("{project} - Test email")
RESET_SUBJECT = N_("{project} - Password recovery for user {email}")
NEW_ACCOUNT_SUBJECT = N_("{project} - New account for user {name}")


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(
    *, template_name: str, context: dict[str, Any], language: Language = "en"
) -> str:
    """An email in the recipient's language: the template's `say` words each
    sentence, and `language` is what the page says it is written in."""
    template_str = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    template = Template(template_str)
    html_content: str = in_language(
        language, lambda: template.render(context, say=say, language=language)
    )
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    assert settings.emails_enabled, "no provided configuration for email variables"
    assert settings.EMAILS_FROM_EMAIL  # For type checker
    message = emails.message.Message(
        subject=subject,
        html=html_content,
        mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
    )
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    logger.info(f"send email result: {response}")


def generate_test_email(email_to: str, language: Language = "en") -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = in_language(language, lambda: say(TEST_SUBJECT, project=project_name))
    html_content = render_email_template(
        template_name="test_email.html",
        context={"project_name": settings.PROJECT_NAME, "email": email_to},
        language=language,
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_password_email(
    email_to: str, email: str, token: str, language: Language = "en"
) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = in_language(
        language, lambda: say(RESET_SUBJECT, project=project_name, email=email)
    )
    link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
        language=language,
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_new_account_email(
    email_to: str, username: str, password: str, language: Language = "en"
) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = in_language(
        language, lambda: say(NEW_ACCOUNT_SUBJECT, project=project_name, name=username)
    )
    html_content = render_email_template(
        template_name="new_account.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "password": password,
            "email": email_to,
            "link": settings.FRONTEND_HOST,
        },
        language=language,
    )
    return EmailData(html_content=html_content, subject=subject)
