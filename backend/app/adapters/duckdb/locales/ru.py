"""What DuckDB writes, in Russian (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    'DuckDB': 'DuckDB',
    'A DuckDB database file in your personal storage. Browse its schemas, tables and views, and read rows a page at a time with sorting and filtering.': 'Файл базы данных DuckDB в вашем личном хранилище. Просмотр схем, таблиц и представлений и чтение строк постранично с сортировкой и фильтрацией.',
    'Path of the file inside your personal storage, such as data/shop.duckdb': 'Путь к файлу внутри вашего личного хранилища, например data/shop.duckdb',
    'The database file is in use by another program': 'Файл базы данных занят другой программой',
    'The database reaches past your personal storage, which is refused': 'База данных обращается за пределы вашего личного хранилища, это запрещено',
    'The file is not a DuckDB database this server can read': 'Файл не является базой данных DuckDB, которую может прочитать этот сервер',
    'This DuckDB source does not offer the "{representation}" content representation': 'Этот источник DuckDB не предлагает представление содержимого «{representation}»',
    "A filter value does not fit its column's type": 'Значение фильтра не подходит к типу колонки',
    'Rows of a DuckDB file are read only for now': 'Строки файла DuckDB пока доступны только для чтения',
}
