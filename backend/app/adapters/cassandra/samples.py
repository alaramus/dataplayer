"""Something worth looking at, put into an empty Cassandra or ScyllaDB node (D352).

A node this application started for somebody is empty, and an empty node
demonstrates nothing. The lab tells the story the other servers' labs tell —
organizations, their people, projects and tasks, and their traffic — in what
CQL has: a partition key and clustering columns in both orders, a static
column, a set, a list, a map, a user-defined type, a duration, a decimal, a
secondary index, a materialized view, a counter table, and twenty thousand page
views across thirty days to page through and filter.

CQL has no `INSERT … SELECT` and no generator of rows, so the rows are made
here from a fixed seed and written with prepared statements. It lives in a
keyspace of its own, `demo_lab`, dropped first. ScyllaDB keeps it out of
tablets, because a materialized view and a secondary index want the classic
layout there.

Not an action and not a route: it is offered only where this server has just
started the node itself (D80).
"""

import asyncio
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from cassandra.util import Duration, uuid_from_time

from app.adapters.cassandra.session import CassandraSession
from app.core.translation import say

SAMPLE_KEYSPACE = "demo_lab"
PAGE_VIEWS = 20_000
_PARALLEL = 64
_START = datetime(2026, 10, 1, tzinfo=UTC)


def _schema(data_center: str, scylla: bool) -> list[str]:
    tablets = " AND tablets = {'enabled': false}" if scylla else ""
    centre = data_center.replace("'", "''")
    return [
        "DROP KEYSPACE IF EXISTS demo_lab",
        "CREATE KEYSPACE demo_lab WITH replication = "
        f"{{'class': 'NetworkTopologyStrategy', '{centre}': 1}}{tablets}",
        "CREATE TYPE demo_lab.address (street text, city text, postcode text)",
        """CREATE TABLE demo_lab.organizations (
            organization_id int PRIMARY KEY,
            slug text,
            display_name text,
            founded_on date,
            plan text,
            features set<text>,
            settings map<text, text>,
            created_at timestamp
        ) WITH comment = 'Customers of the lab, one row each'""",
        """CREATE TABLE demo_lab.users_by_organization (
            organization_id int,
            user_id int,
            organization_name text static,
            email text,
            full_name text,
            reputation int,
            is_admin boolean,
            last_ip inet,
            home frozen<address>,
            tags list<text>,
            PRIMARY KEY ((organization_id), user_id)
        ) WITH comment = 'People, kept together by the organization they belong to'""",
        "CREATE INDEX users_email_idx ON demo_lab.users_by_organization (email)",
        """CREATE TABLE demo_lab.tasks_by_project (
            project_id int,
            created_at timestamp,
            task_id uuid,
            title text,
            status text,
            estimate decimal,
            spent duration,
            assignee_id int,
            PRIMARY KEY ((project_id), created_at, task_id)
        ) WITH CLUSTERING ORDER BY (created_at DESC, task_id ASC)
          AND comment = 'Tasks of a project, newest first'""",
        """CREATE MATERIALIZED VIEW demo_lab.tasks_by_status AS
            SELECT project_id, created_at, task_id, title, status FROM demo_lab.tasks_by_project
            WHERE status IS NOT NULL AND project_id IS NOT NULL
              AND created_at IS NOT NULL AND task_id IS NOT NULL
            PRIMARY KEY ((status), project_id, created_at, task_id)""",
        """CREATE TABLE demo_lab.page_views (
            day date,
            viewed_at timestamp,
            view_id timeuuid,
            path text,
            user_id int,
            duration_ms int,
            PRIMARY KEY ((day), viewed_at, view_id)
        ) WITH CLUSTERING ORDER BY (viewed_at DESC, view_id ASC)
          AND comment = 'Every page view, one partition a day'""",
        """CREATE TABLE demo_lab.views_by_path (
            path text PRIMARY KEY,
            views counter
        ) WITH comment = 'Page views added up, a counter per path'""",
    ]


_PLANS = ("free", "team", "enterprise")
_FEATURES = ("sso", "audit", "export", "api", "reports")
_CITIES = ("Lisbon", "Oslo", "Tallinn", "Lyon", "Porto", "Gdansk")
_STATUSES = ("todo", "doing", "review", "done")
_PATHS = (
    "/",
    "/pricing",
    "/docs",
    "/docs/cql",
    "/blog",
    "/signup",
    "/login",
    "/dashboard",
)
_NAMES = (
    "Ada",
    "Ben",
    "Chloe",
    "Dmitri",
    "Eva",
    "Farid",
    "Grace",
    "Hiro",
    "Ines",
    "Jonas",
)


def _rows(seed: int = 42) -> dict[str, list[list[Any]]]:
    """Every row of the lab, made from one seed so that two labs are the same."""
    chance = random.Random(seed)
    organizations: list[list[Any]] = []
    users: list[list[Any]] = []
    tasks: list[list[Any]] = []
    views: list[list[Any]] = []
    for organization_id in range(1, 9):
        name = f"Org {organization_id:02d}"
        organizations.append(
            [
                organization_id,
                f"org-{organization_id:02d}",
                name,
                date(2010 + organization_id, organization_id, 10),
                _PLANS[organization_id % 3],
                set(chance.sample(_FEATURES, k=1 + organization_id % 4)),
                {"locale": "en", "theme": "dark" if organization_id % 2 else "light"},
                _START - timedelta(days=400 - organization_id * 20),
            ]
        )
        for number in range(1, 13):
            user_id = organization_id * 100 + number
            first = _NAMES[(user_id * 7) % len(_NAMES)]
            users.append(
                [
                    organization_id,
                    user_id,
                    name,
                    f"{first.lower()}.{user_id}@org{organization_id:02d}.example",
                    f"{first} {chr(65 + number)}.",
                    chance.randint(-5, 500),
                    number == 1,
                    f"10.{organization_id}.0.{number}",
                    {
                        "street": f"{number} Main Street",
                        "city": _CITIES[user_id % len(_CITIES)],
                        "postcode": f"{1000 + user_id}",
                    },
                    chance.sample(
                        ("ops", "design", "backend", "frontend", "sales"), k=2
                    ),
                ]
            )
    for project_id in range(1, 13):
        for number in range(25):
            created = _START + timedelta(hours=project_id * 7 + number * 13)
            tasks.append(
                [
                    project_id,
                    created,
                    uuid.UUID(int=project_id * 1000 + number),
                    f"Task {number + 1} of project {project_id}",
                    _STATUSES[(project_id + number) % 4],
                    Decimal(chance.randint(1, 80)) / Decimal(4),
                    Duration(
                        0,
                        chance.randint(0, 3),
                        chance.randint(0, 8) * 3_600_000_000_000,
                    ),
                    chance.randint(101, 812),
                ]
            )
    for _ in range(PAGE_VIEWS):
        moment = _START + timedelta(seconds=chance.randint(0, 30 * 86_400 - 1))
        views.append(
            [
                moment.date(),
                moment,
                uuid_from_time(
                    moment.timestamp(),
                    node=0x0DA7A9_1A7E2,
                    clock_seq=chance.randint(0, 0x3FFF),
                ),
                chance.choice(_PATHS),
                chance.randint(101, 812),
                chance.randint(20, 4000),
            ]
        )
    return {
        "organizations": organizations,
        "users_by_organization": users,
        "tasks_by_project": tasks,
        "page_views": views,
    }


_INSERTS = {
    "organizations": (
        "INSERT INTO demo_lab.organizations (organization_id, slug, display_name, founded_on, "
        "plan, features, settings, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "users_by_organization": (
        "INSERT INTO demo_lab.users_by_organization (organization_id, user_id, organization_name, "
        "email, full_name, reputation, is_admin, last_ip, home, tags) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "tasks_by_project": (
        "INSERT INTO demo_lab.tasks_by_project (project_id, created_at, task_id, title, status, "
        "estimate, spent, assignee_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "page_views": (
        "INSERT INTO demo_lab.page_views (day, viewed_at, view_id, path, user_id, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    ),
}
_COUNT = "UPDATE demo_lab.views_by_path SET views = views + ? WHERE path = ?"


class CassandraSamples:
    def __init__(self, session: CassandraSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        """Make the lab, fill it, and say what is now there."""
        async with self._session.held():
            return await self._install()

    async def _install(self) -> str:
        profile = await self._session.profile()
        for statement in _schema(profile.data_center or "datacenter1", profile.scylla):
            await self._session.page(statement, wait_seconds=120)
        rows = await asyncio.to_thread(_rows)
        gate = asyncio.Semaphore(_PARALLEL)

        async def write(statement: str, values: list[Any]) -> None:
            async with gate:
                await self._session.page(statement, values)

        for table, statement in _INSERTS.items():
            await asyncio.gather(*(write(statement, values) for values in rows[table]))
        counted: dict[str, int] = {}
        for view in rows["page_views"]:
            counted[view[3]] = counted.get(view[3], 0) + 1
        await asyncio.gather(
            *(write(_COUNT, [count, path]) for path, count in counted.items())
        )
        return say(
            "{schema}: {tables} tables",
            schema=SAMPLE_KEYSPACE,
            tables=len(_INSERTS) + 1,
        )
