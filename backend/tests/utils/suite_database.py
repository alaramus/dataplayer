"""The database the suite runs in, chosen on import, before anything opens one.

Imported first by `tests/conftest.py`: `app.core.db` builds its engine from
the address when it is first imported, so changing it afterwards would change
nothing. The choice itself is the registry's (`services.point_at_suite_database`).
"""

from tests.utils.services import point_at_suite_database

point_at_suite_database()
