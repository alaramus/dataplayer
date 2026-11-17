"""The suite runs in a database of its own and refuses the application's."""

import pytest

from app.core.config import settings
from app.prepare_test_database import database_name, suite_database_url
from tests.utils.services import refuse_unless_suite_database


def test_the_suite_s_database_is_the_application_s_with_test_after_it() -> None:
    url = "postgresql+psycopg://postgres:p%40ss@localhost:5432/app"

    assert suite_database_url(url) == "postgresql+psycopg://postgres:p%40ss@localhost:5432/app_test"
    # One that is already the suite's stays itself, never `app_test_test`.
    assert suite_database_url(suite_database_url(url)) == suite_database_url(url)


def test_this_run_is_in_a_database_ending_in_test() -> None:
    assert database_name(str(settings.DATABASE_URL)).endswith("_test")


def test_the_application_s_database_is_refused_by_name() -> None:
    with pytest.raises(pytest.UsageError, match="does not run in 'app'"):
        refuse_unless_suite_database("postgresql+psycopg://postgres:p@localhost:5432/app")
    refuse_unless_suite_database("postgresql+psycopg://postgres:p@localhost:5432/app_test")
