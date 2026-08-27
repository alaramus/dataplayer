# Добавление и удаление колонок

Дата: 2026-08-27
Статус: согласовано
Раунд: 12

## Цель

Добавить первые изменения структуры relation: создать одну колонку и удалить
одну колонку. Команды должны оставаться частью adapter contract, не превращать
frontend в SQL-конструктор и после успеха синхронно обновлять Structure и Rows.

## Главная граница

Тип колонки нельзя передать как произвольную SQL-строку. В отличие от значения,
тип занимает место syntax и не может быть `%s` parameter; простая подстановка
вернула бы ровно тот канал SQL injection, который закрывает D2c. Поэтому relation
model несёт список `ColumnTypeOption`: человек видит title и SQL spelling, а
клиент возвращает только opaque `code`. Адаптер сопоставляет code с заранее
собранным `psycopg.sql.SQL` fragment. Неизвестный code отклоняется до statement.

В первом словаре PostgreSQL есть common scalar types: text, integer, bigint,
numeric, boolean, date, timestamp with time zone, jsonb и uuid. Это не попытка
описать весь PostgreSQL. Length, precision, arrays, domains, enums и composite
types потребуют типизированных параметров option, а не текстового поля «SQL».

## Р1. Возможность относится к конкретной relation

`SupportsAddColumn` и `SupportsDropColumn` независимы от чтения структуры.
`RelationModel` сообщает `column_changes_supported`, reason и type options.
PostgreSQL разрешает команды для ordinary table и partitioned parent. View не
является таблицей. Дочерняя partition получает отдельное объяснение «измените
parent»: её колонки inherited, и локальный жест создавал бы ложное ожидание.

Capability типа остаётся в каталоге возможностей, а точная relation может её
запретить. File adapter не реализует ни один DDL Protocol и на route отвечает
501 вместо заглушки.

## Р2. ADD COLUMN получает только структурированные поля

Команда содержит `node_id`, name, type code и nullable. Имя заново проверяется
по свежей metadata, ограничивается PostgreSQL ceiling в 63 bytes и проходит
только через `Identifier`. Type code проходит закрытый registry. Nullability —
boolean, который добавляет фиксированный `NOT NULL` token.

Default expression в этот раунд не входит. У неё два разных смысла: literal
value и source expression (`now()`, sequence, function). Одно text-поле снова
смешало бы data и syntax. Следствие сказано честно: nullable включён по умолчанию,
а NOT NULL колонка на непустой таблице без default будет отклонена источником.

## Р3. DROP COLUMN не получает CASCADE

Удаление адресует существующую колонку точным именем и показывает destructive
confirmation. PostgreSQL по правилам самой таблицы удалит принадлежащие колонке
indexes и constraints; эта потеря названа в диалоге. Но statement не содержит
`CASCADE`: внешние зависимости должны остановить действие, а не исчезнуть как
побочный эффект одного клика.

Rename и alter type не маскируются комбинацией add/drop. Rename сохраняет
identity и dependencies, alter type требует conversion/USING semantics; это
отдельные будущие контракты.

## Р4. После DDL устаревают две проекции

Structure query перечитывается, чтобы показать новую модель constraints и
indexes. Row queries того же connector тоже invalidated: массив columns и
каждая row shape изменились одновременно. Локально вставить или вырезать один
столбец нельзя — generated metadata и серверный порядок являются ответом
источника, не вычислением клиента.

## Ошибки и проверка

404 означает исчезнувшую relation, 422 — unsupported relation, duplicate или
unknown column/type и безопасно сокращённый отказ DDL, 501 — отсутствие
capability, 502 — failure источника. Backend-тесты проверяют metadata, add/drop,
quoted identifier, unknown type, views, partitions и NOT NULL rejection. Unit
тесты проверяют exact generated-client payload и confirmation. Playwright на
реальной `demo_lab.tags` добавляет уникальную nullable text column, видит её в
Structure, удаляет и видит обновлённую модель.
