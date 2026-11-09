"""Что пишет Cassandra, по-русски (D226). Термины следуют глоссарию экранов."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "Cassandra": "Cassandra",
    "Apache Cassandra": "Apache Cassandra",
    "ScyllaDB": "ScyllaDB",
    "Apache Cassandra or ScyllaDB, over CQL. Browse keyspaces, tables and materialized views, and read rows a page at a time with filtering done by the server.": "Apache Cassandra или ScyllaDB через CQL. Просмотр пространств ключей, таблиц и материализованных представлений и постраничное чтение строк с фильтрацией на сервере.",
    "Keyspace": "Пространство ключей",
    "Where the catalog opens; every keyspace the role may see is in the catalog": "Где открывается каталог; в каталоге есть все пространства ключей, которые видит роль",
    "The native protocol's port, 9042 unless the server says otherwise": "Порт нативного протокола, 9042, если сервер не настроен иначе",
    "TLS, with the server's certificate verified": "TLS с проверкой сертификата сервера",
    "Consistency": "Согласованность",
    "How many replicas answer a read and acknowledge a write": "Сколько реплик отвечает на чтение и подтверждает запись",
    "That is not a Cassandra connection string": "Это не строка подключения Cassandra",
    "{product} {version} is older than this source supports ({oldest})": "{product} {version} старше, чем поддерживает этот источник ({oldest})",
    "Keyspace does not exist": "Пространство ключей не существует",
    'Keyspace "{name}" does not exist': "Пространство ключей «{name}» не существует",
    "Not enough replicas are up for the consistency level asked": "Для запрошенного уровня согласованности работает недостаточно реплик",
    # Relations and rows.
    '"{node_id}" is not a relation: expected keyspace.table': "«{node_id}» — не отношение: ожидается пространство_ключей.таблица",
    '"{keyspace}" belongs to the server': "«{keyspace}» принадлежит серверу",
    "Cassandra has no unique keys and no foreign keys": "В Cassandra нет уникальных и внешних ключей",
    "Partition key": "Ключ секции",
    "Clustering column, {order}": "Столбец кластеризации, {order}",
    "Static: one value for the whole partition": "Статический: одно значение на всю секцию",
    'This Cassandra source does not offer the "{representation}" content representation': "Этот источник Cassandra не предлагает представление содержимого «{representation}»",
    "This page is {rows} rows past the last one read; page forward from there": "Эта страница на {rows} строк дальше последней прочитанной; листайте вперёд оттуда",
    "ScyllaDB's LIKE cannot look for % or _ in a value": "LIKE в ScyllaDB не умеет искать % или _ в значении",
    # The console and cqlsh.
    ":{name} is not a value of type {type}": ":{name} — не значение типа {type}",
    "Cassandra keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own, or put the changes in one BATCH": "Cassandra сохраняет изменение сразу и не может его отменить, поэтому изменение не может выполняться вместе с другими операторами; запустите его отдельно или объедините изменения в один BATCH",
    "No value was given for :{name}": "Не задано значение для :{name}",
    "This connection has no keyspace called {name}": "В этом подключении нет пространства ключей {name}",
    "This is not a CQL statement this console runs": "Это не оператор CQL, который выполняет эта консоль",
    "cqlsh cannot read a user or a password that holds a line break": "cqlsh не может прочитать пользователя или пароль с переводом строки",
    "{command} is a cqlsh command, not CQL; run it in cqlsh in a terminal": "{command} — команда cqlsh, а не CQL; выполните её в cqlsh в терминале",
}
