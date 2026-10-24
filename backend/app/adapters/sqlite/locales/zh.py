"""What SQLite writes, in Chinese (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "SQLite": "SQLite",
    'A SQLite database file in your personal storage. Browse its tables and views, read rows a page at a time with sorting and filtering, and run SQL.': '你个人存储中的 SQLite 数据库文件。浏览其中的表和视图，分页读取行并支持排序和筛选，还可以运行 SQL。',
    "Database file": "数据库文件",
    "Path of the file inside your personal storage, such as data/shop.db": "文件在你个人存储中的路径，例如 data/shop.db",
    "Create the file if it is missing": "文件不存在时创建",
    "Without this, a file that does not exist fails the connection check": "不勾选时，不存在的文件无法通过连接检查",
    "Name a file inside your personal storage": "请指定你个人存储中的一个文件",
    # Opening the file.
    "SQLite {version} is older than this source supports ({oldest})": "SQLite {version} 早于此数据源支持的版本（{oldest}）",
    "The database file does not exist": "数据库文件不存在",
    "The folder for the database file does not exist": "数据库文件所在的文件夹不存在",
    "The path names a folder, not a file": "该路径指向文件夹，而不是文件",
    "The file is not a SQLite database": "该文件不是 SQLite 数据库",
    "The database file is damaged": "数据库文件已损坏",
    "The database file cannot be opened": "无法打开数据库文件",
    "The database file cannot be written": "无法写入数据库文件",
    "The database file is locked by another connection": "数据库文件已被另一个连接锁定",
    "The database did not answer in time": "数据库未及时响应",
    # The catalog and its relations.
    '"{name}" needs a module this server does not have': "“{name}”需要此服务器没有的模块",
    '"{node_id}" is not a relation: expected main.table': "“{node_id}”不是关系：应为 main.表",
    'This SQLite source does not offer the "{representation}" content representation': "此 SQLite 数据源不提供“{representation}”内容表示",
    "Rows of a SQLite file are read only for now": "SQLite 文件中的行目前只读",
    # The console.
    'A connection to this file opens no other file': '到此文件的连接不会打开其他文件',
    'Query plan': '查询计划',
    'The query editor changes tables, views and indexes; this is something else': '查询编辑器只修改表、视图和索引；这是其他内容',
}
