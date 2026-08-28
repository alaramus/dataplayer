# Переименование колонки

Дата: 2026-08-28
Статус: согласовано
Раунд: 13

## Цель

Переименовать одну колонку без пересоздания, потери данных или скрытого
удаления зависимостей. Это первый следующий DDL-срез после add/drop.

## Контракт

`RenameColumnRequest` несёт `node_id`, текущее `name` и `new_name`.
`SupportsRenameColumn` независим от add/drop: будущий источник может разрешать
не все три операции. Возможность конкретной relation по-прежнему определяется
её `column_changes_supported` и объяснением.

Адаптер перечитывает relation model перед statement. Текущее имя обязано
существовать, новое — отсутствовать и отличаться; пробелы по краям и имя длиннее
63 UTF-8 bytes отклоняются. Имена никогда не становятся SQL-фрагментами:
PostgreSQL получает только `Identifier`.

## Зависимости

Statement — `ALTER TABLE <relation> RENAME COLUMN <old> TO <new>`, без
`CASCADE`. Это не add/copy/drop: колонка сохраняет identity и данные, а
PostgreSQL сам обновляет constraints, indexes и catalog dependencies по её
attribute number. Собственные имена выходных колонок зависимых views не
переписываются — они принадлежат view, а не исходной таблице.

## Интерфейс и кеши

Rename находится в actions ячейки конкретной колонки Structure. Диалог
показывает старое имя read-only и принимает новое; явного destructive confirm
нет, потому что операция не удаляет данные, но она всё равно отдельный
осознанный submit.

Успех invalidates relation model и все row queries connector. Grid reconcile
удаляет старое имя из сохранённой раскладки и принимает новое из свежего
`FetchResult`; переносить ширину или фильтр автоматически нельзя, поскольку
клиент не владеет доказательством identity колонки.

## Проверка

Backend проверяет rename, metadata зависимости, duplicate/unknown names,
quoted identifier, view/partition refusal и отсутствие capability. Frontend
проверяет точный generated-client payload и обновление после mutation.
