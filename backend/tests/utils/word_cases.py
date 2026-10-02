"""One table of how a name matches the words, read by every implementation's tests.

The rule is D202's: every word in the name, case-folded, in any order, and a
class for how well. The application's own objects, the explorer's walk,
PostgreSQL's query and Redis's scan each class names, and each is tested
against these rows so that none can drift from the others.
"""

from app.adapters.search import MatchClass

# (typed, name, class) — None where the name does not match at all.
CASES: list[tuple[str, str, MatchClass | None]] = [
    ("orders", "orders", "exact"),
    ("ORDERS", "orders", "exact"),
    ("orders", "Orders", "exact"),
    ("orders 2024", "orders 2024", "exact"),
    ("orders orders", "orders", "exact"),
    ("straße", "STRASSE", "exact"),
    ("order", "orders", "prefix"),
    ("orders", "orders_2024.csv", "prefix"),
    ("auth", "Auth tokens", "prefix"),
    ("user", "user:42:token", "prefix"),
    ("2024 orders", "orders_2024.csv", "word"),
    ("csv", "orders_2024.csv", "word"),
    ("class", "pg_class", "word"),
    ("token", "session:42:token", "word"),
    ("100%", "growth 100%", "word"),
    ("ders", "orders_2024.csv", "substring"),
    ("lass", "pg_class", "substring"),
    ("auth", "oauth2", "substring"),
    ("orders 2023", "orders_2024.csv", None),
    ("100%", "100_percent", None),
    ("%", "orders", None),
    ("_", "orders", None),
    ("o*", "orders", None),
    ("ord?", "orders", None),
]
