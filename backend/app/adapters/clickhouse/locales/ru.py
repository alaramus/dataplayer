"""Что пишет ClickHouse, по-русски (D226). Термины следуют глоссарию экранов."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    'A ClickHouse server, over its HTTP interface. Browse databases, tables and views, read rows a page at a time with sorting and filtering done by the server, and run SQL.': 'Сервер ClickHouse через его HTTP-интерфейс. Просмотр баз данных, таблиц и представлений, чтение строк постранично с сортировкой и фильтрацией на сервере и выполнение SQL.',
    "The HTTP interface: 8123, or 8443 with TLS": "HTTP-интерфейс: 8123 или 8443 с TLS",
    "TLS": "TLS",
    "HTTPS, with the server's certificate verified": "HTTPS с проверкой сертификата сервера",
    "That is not a ClickHouse connection string": "Это не строка подключения ClickHouse",
    "ClickHouse {version} is older than this source supports ({oldest})": "ClickHouse {version} старше, чем поддерживает этот источник ({oldest})",
    # Relations and rows.
    'This ClickHouse source does not offer the "{representation}" content representation': "Этот источник ClickHouse не предлагает представление содержимого «{representation}»",
    "A filter value does not fit its column": "Значение фильтра не подходит для своего столбца",
    "Changing the structure of a ClickHouse table is not supported yet": "Изменение структуры таблицы ClickHouse пока не поддерживается",
    "Editing ClickHouse rows is not supported yet": "Правка строк ClickHouse пока не поддерживается",
    # The console.
    'ClickHouse keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own': 'ClickHouse сохраняет изменение сразу и не может его отменить, поэтому изменение не может выполняться вместе с другими операторами; запустите его отдельно',
    'Detaching and attaching tables is not done from the query editor': 'Отсоединение и присоединение таблиц не выполняется из редактора запросов',
    'Named collections are not changed from the query editor': 'Именованные коллекции не изменяются из редактора запросов',
    'SYSTEM commands manage the server and are not run from the query editor': 'Команды SYSTEM управляют сервером и не выполняются из редактора запросов',
    'The console shows a result itself; leave FORMAT out': 'Консоль сама показывает результат; уберите FORMAT',
    'The query editor changes databases, tables, views and dictionaries; this is something else': 'Редактор запросов изменяет базы данных, таблицы, представления и словари; это что-то другое',
}
