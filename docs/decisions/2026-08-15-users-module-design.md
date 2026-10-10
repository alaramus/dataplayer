# Breaking the flat layer up into a users module

Date: 2026-08-15
Status: agreed
Subproject: 2a

## Goal

Remove the flat layer inherited from the template from the backend:
`app/models.py`, `app/crud.py`, `app/utils.py`, `app/api/deps.py` and
`app/api/routes/`. Afterwards all code lives in feature modules, and the
application keeps one way of organising it instead of two.

This is decision R5 from the first slice's spec, deferred then so as not to
widen the slice: the move touches users and login without adding anything to
working with connectors.

## Why this is not cosmetic

A single models file and a single CRUD file for the whole application is the
start of the path that led the old application's `common_option_adapter.py` to
3685 lines. The files are small now, and that is exactly why they are cheap to
split.

The second consequence matters more than the first: the direction of
dependencies becomes one-way. `core` knows about nobody, `users` knows about
`core`, `connectors` and `adapters` know about `core` and `users` — for the
sake of `CurrentUser`. There are no arrows back.

## Target structure

```
backend/app/
├── main.py
├── api/main.py          router assembly only
├── core/
│   ├── config.py
│   ├── db.py            + SessionDep
│   ├── security.py
│   ├── crypto.py
│   ├── schemas.py       new: Message, get_datetime_utc
│   ├── email.py         from utils.py: sending emails and their templates
│   └── routes.py        /utils: health check, test email
├── users/
│   ├── models.py        User, User*, Token, TokenPayload, NewPassword
│   ├── crud.py
│   ├── deps.py          CurrentUser, get_current_user,
│   │                    get_current_active_superuser
│   ├── tokens.py        from utils.py: password reset tokens
│   ├── routes.py        /users
│   ├── auth_routes.py   /login, /password-recovery, /reset-password
│   └── private_routes.py
├── adapters/
└── connectors/
```

The tests move in mirror: `tests/users/` instead of `tests/api/routes/` and
`tests/crud/`.

### Where everything goes

| Was | Becomes |
| --- | --- |
| `app/models.py` — the `User*` models | `app/users/models.py` |
| `app/models.py` — `Token`, `TokenPayload`, `NewPassword` | `app/users/models.py` |
| `app/models.py` — `Message`, `get_datetime_utc` | `app/core/schemas.py` |
| `app/crud.py` | `app/users/crud.py` |
| `app/api/deps.py` — `SessionDep`, `get_db` | `app/core/db.py` |
| `app/api/deps.py` — everything else | `app/users/deps.py` |
| `app/api/routes/users.py` | `app/users/routes.py` |
| `app/api/routes/login.py` | `app/users/auth_routes.py` |
| `app/api/routes/private.py` | `app/users/private_routes.py` |
| `app/api/routes/utils.py` — health check and test email | `app/core/routes.py`: this has nothing to do with users |
| `app/utils.py` — emails | `app/core/email.py` |
| `app/utils.py` — password reset tokens | `app/users/tokens.py` |

## Done criterion

**The public API does not change by a single byte.** A snapshot of
`openapi.json` before and after the move must match byte for byte. For a pure
move this is stronger than "the tests pass": it catches a changed tag, router
order or operation name, that is, a breakage of the generated client.

In addition:

- all 101 tests pass;
- `mypy --strict` and `ruff` are clean;
- **only import paths are edited in the tests**. If a test's logic had to
  change, the move broke something, and that has to be fixed rather than the
  test adjusted.

## Not in this subproject

Renames, signature changes, new functions, behaviour changes, frontend edits,
migrations. Only moving code and fixing imports.

## Risk

Circular imports. `users/deps.py` pulls in `core/db.py` and `users/models.py`,
`connectors/routes.py` pulls in `users/deps.py`. There is no cycle here, but
`app/api/main.py` imports everything at once, so a mistake in placing
`SessionDep` creates a cycle immediately. Caught by importing the application.
