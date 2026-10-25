"""Что пишет ClickHouse, по-русски (D226). Термины следуют глоссарию экранов."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    "A ClickHouse server, over its HTTP interface. Browse databases, tables and views, and read rows a page at a time with sorting and filtering done by the server.": "Сервер ClickHouse через его HTTP-интерфейс. Просмотр баз данных, таблиц и представлений и чтение строк постранично с сортировкой и фильтрацией на сервере.",
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
}
