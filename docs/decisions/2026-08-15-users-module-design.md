# Расформирование плоского слоя в модуль пользователей

Дата: 2026-08-15
Статус: согласовано
Подпроект: 2а

## Цель

Убрать из бэкенда плоский слой, доставшийся от шаблона: `app/models.py`,
`app/crud.py`, `app/utils.py`, `app/api/deps.py` и `app/api/routes/`. После
работы весь код живёт в модулях функциональности, и в приложении остаётся один
способ его организации вместо двух.

Это решение Р5 из спека первого среза, отложенное тогда, чтобы не расширять
срез: перестановка затрагивает пользователей и вход, не добавляя ничего к
работе с коннекторами.

## Почему это не косметика

Единственный файл моделей и единственный файл CRUD на всё приложение — это
начало пути, приведшего `common_option_adapter.py` старого приложения к 3685
строкам. Сейчас файлы малы, и именно поэтому их дёшево разделить.

Второе следствие важнее первого: направление зависимостей становится
односторонним. `core` не знает ни о ком, `users` знает о `core`, `connectors`
и `adapters` знают о `core` и `users` — ради `CurrentUser`. Обратных стрелок
нет.

## Целевая структура

```
backend/app/
├── main.py
├── api/main.py          только сборка роутеров
├── core/
│   ├── config.py
│   ├── db.py            + SessionDep
│   ├── security.py
│   ├── crypto.py
│   ├── schemas.py       новый: Message, get_datetime_utc
│   ├── email.py         из utils.py: отправка и шаблоны писем
│   └── routes.py        /utils: проверка живости, тестовое письмо
├── users/
│   ├── models.py        User, User*, Token, TokenPayload, NewPassword
│   ├── crud.py
│   ├── deps.py          CurrentUser, get_current_user,
│   │                    get_current_active_superuser
│   ├── tokens.py        из utils.py: токены сброса пароля
│   ├── routes.py        /users
│   ├── auth_routes.py   /login, /password-recovery, /reset-password
│   └── private_routes.py
├── adapters/
└── connectors/
```

Тесты переезжают зеркально: `tests/users/` вместо `tests/api/routes/` и
`tests/crud/`.

### Куда что уходит

| Было | Стало |
| --- | --- |
| `app/models.py` — модели `User*` | `app/users/models.py` |
| `app/models.py` — `Token`, `TokenPayload`, `NewPassword` | `app/users/models.py` |
| `app/models.py` — `Message`, `get_datetime_utc` | `app/core/schemas.py` |
| `app/crud.py` | `app/users/crud.py` |
| `app/api/deps.py` — `SessionDep`, `get_db` | `app/core/db.py` |
| `app/api/deps.py` — всё остальное | `app/users/deps.py` |
| `app/api/routes/users.py` | `app/users/routes.py` |
| `app/api/routes/login.py` | `app/users/auth_routes.py` |
| `app/api/routes/private.py` | `app/users/private_routes.py` |
| `app/api/routes/utils.py` — проверка живости и тестовое письмо | `app/core/routes.py`: к пользователям это не относится |
| `app/utils.py` — письма | `app/core/email.py` |
| `app/utils.py` — токены сброса пароля | `app/users/tokens.py` |

## Критерий готовности

**Публичный API не меняется ни на байт.** Снимок `openapi.json` до перестановки
и после должен совпасть побайтово. Для чистой перестановки это сильнее, чем
«тесты проходят»: поймает изменившийся тег, порядок роутеров или имя операции,
то есть поломку сгенерированного клиента.

Дополнительно:

- все 101 тест проходят;
- `mypy --strict` и `ruff` чисты;
- **в тестах правятся только пути импортов**. Если понадобилось изменить логику
  теста, значит перестановка что-то сломала, и это надо чинить, а не
  подгонять тест.

## Чего в подпроекте нет

Переименований, изменений сигнатур, новых функций, изменений поведения, правок
фронтенда, миграций. Только перемещение кода и правка импортов.

## Риск

Циклические импорты. `users/deps.py` тянет `core/db.py` и `users/models.py`,
`connectors/routes.py` тянет `users/deps.py`. Цикла здесь нет, но
`app/api/main.py` импортирует всё сразу, поэтому ошибка в размещении
`SessionDep` создаст цикл немедленно. Ловится импортом приложения.
