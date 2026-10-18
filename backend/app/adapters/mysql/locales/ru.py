"""What MySQL writes, in Russian (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MySQL": "MySQL",
    "MySQL or MariaDB. Browse databases, tables and views, and read rows a page at a time with sorting and filtering done by the server.": "MySQL или MariaDB. Просмотр баз данных, таблиц и представлений, чтение строк постранично с сортировкой и фильтрацией на сервере.",
    "Host": "Хост",
    "Port": "Порт",
    "Database": "База данных",
    "Where the catalog opens; every database the user may see is in the catalog": "С неё открывается каталог; в каталоге есть все базы данных, доступные пользователю",
    "User": "Пользователь",
    "Password": "Пароль",
    "Authentication": "Аутентификация",
    "User & Password": "Пользователь и пароль",
    "No password": "Без пароля",
    # Connecting.
    "Connection failed": "Не удалось подключиться",
    "Connection successful": "Подключение установлено",
    "Connection timed out": "Время ожидания подключения истекло",
    "Authentication failed": "Ошибка аутентификации",
    "Database does not exist": "База данных не существует",
    "Could not reach the database server": "Сервер базы данных недоступен",
    "All connections to this source are busy": "Все подключения к этому источнику заняты",
    "{server} {version} is older than this source supports ({oldest})": "{server} {version} старше, чем поддерживает этот источник ({oldest})",
    "That is not a MySQL connection string": "Это не строка подключения MySQL",
    "The connection string names no host": "В строке подключения не указан хост",
    "The connection string names no usable port": "В строке подключения нет подходящего порта",
    "Query failed": "Не удалось выполнить запрос",
    # The catalog and its relations.
    "View as table": "Открыть как таблицу",
    "View DDL": "Показать DDL",
    'Database "{name}" does not exist': "База данных «{name}» не существует",
    '"{node_id}" is not a relation: expected database.table': "«{node_id}» — не отношение: ожидается база_данных.таблица",
    'This MySQL source does not offer the "{representation}" content representation': "Этот источник MySQL не предлагает представление содержимого «{representation}»",
    "This DDL is larger than 256 KB; only its beginning is shown.": "DDL больше 256 КБ, показано только начало.",
    "Changing the structure of a MySQL relation is not supported yet": "Изменение структуры отношения MySQL пока не поддерживается",
    # Rows.
    'Relation has no column "{column}"': "В отношении нет столбца «{column}»",
    'Cannot filter column "{name}" with "{op}"': "Столбец «{name}» нельзя фильтровать по «{op}»",
    'Invalid value for column "{name}"': "Недопустимое значение для столбца «{name}»",
    'Cannot sort column "{column}"': "По столбцу «{column}» нельзя сортировать",
    "Changing rows of a MySQL relation is not supported yet": "Изменение строк отношения MySQL пока не поддерживается",
}
