"""What SQLite writes, in Russian (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "SQLite": "SQLite",
    'A SQLite database file in your personal storage. Browse its tables and views, read and edit rows a page at a time with sorting and filtering, and run SQL.': 'Файл базы данных SQLite в вашем личном хранилище. Просмотр таблиц и представлений, чтение и правка строк постранично с сортировкой и фильтрацией и выполнение SQL.',
    "Database file": "Файл базы данных",
    "Path of the file inside your personal storage, such as data/shop.db": "Путь к файлу внутри вашего личного хранилища, например data/shop.db",
    "Create the file if it is missing": "Создать файл, если его нет",
    "Without this, a file that does not exist fails the connection check": "Без этого отсутствующий файл не пройдёт проверку подключения",
    "Name a file inside your personal storage": "Укажите файл внутри вашего личного хранилища",
    # Opening the file.
    "SQLite {version} is older than this source supports ({oldest})": "SQLite {version} старше, чем поддерживает этот источник ({oldest})",
    "The database file does not exist": "Файл базы данных не существует",
    "The folder for the database file does not exist": "Папки для файла базы данных не существует",
    "The path names a folder, not a file": "Путь указывает на папку, а не на файл",
    "The file is not a SQLite database": "Файл не является базой данных SQLite",
    "The database file is damaged": "Файл базы данных повреждён",
    "The database file cannot be opened": "Не удаётся открыть файл базы данных",
    "The database file cannot be written": "В файл базы данных нельзя записать",
    "The database file is locked by another connection": "Файл базы данных заблокирован другим подключением",
    "The database did not answer in time": "База данных не ответила вовремя",
    # The catalog and its relations.
    '"{name}" needs a module this server does not have': "«{name}» требует модуля, которого нет на этом сервере",
    '"{node_id}" is not a relation: expected main.table': "«{node_id}» не является отношением: ожидается main.таблица",
    'This SQLite source does not offer the "{representation}" content representation': "Этот источник SQLite не предлагает представление содержимого «{representation}»",
    # The console.
    'A connection to this file opens no other file': 'Подключение к этому файлу не открывает другие файлы',
    'Query plan': 'План запроса',
    'The query editor changes tables, views and indexes; this is something else': 'Редактор запросов изменяет таблицы, представления и индексы; это что-то другое',
    # Changing rows.
    '"{name}" belongs to SQLite': '«{name}» принадлежит SQLite',
    'Rows of a virtual table are not changed here': 'Строки виртуальной таблицы здесь не меняются',
    'The rows of this table cannot be told apart': 'Строки этой таблицы невозможно отличить друг от друга',
    'The value is not of the type its column holds': 'Значение не того типа, который хранит столбец',
}
