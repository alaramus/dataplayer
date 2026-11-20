"""What DuckDB writes, in Chinese (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    'DuckDB': 'DuckDB',
    'Path of the file inside your personal storage, such as data/shop.duckdb': '文件在您个人存储中的路径，例如 data/shop.duckdb',
    'The database file is in use by another program': '数据库文件正被另一个程序使用',
    'The database reaches past your personal storage, which is refused': '数据库访问超出了您的个人存储范围，已被拒绝',
    'The file is not a DuckDB database this server can read': '该文件不是此服务器能够读取的 DuckDB 数据库',
    'This DuckDB source does not offer the "{representation}" content representation': '此 DuckDB 数据源不提供“{representation}”内容表示',
    "A filter value does not fit its column's type": '筛选值与其列的类型不符',
    'Rows of a DuckDB file are read only for now': 'DuckDB 文件的行目前为只读',
    'A DuckDB database file in your personal storage. Browse its schemas, tables and views, read rows a page at a time with sorting and filtering, and run SQL over the file and the other files of your storage.': '您个人存储中的 DuckDB 数据库文件。浏览其模式、表和视图，按页读取行并支持排序和筛选，还可对该文件及存储中的其他文件运行 SQL。',
    'A connection to this file opens no other database': '连接到此文件不会打开其他数据库',
    'DuckDB has no savepoints, so a change cannot be tried out inside a held transaction; run it in auto-commit, where it is tried out first': 'DuckDB 没有保存点，因此无法在保持的事务中试运行更改；请在自动提交模式下运行，那里会先试运行',
    'Extensions are not installed or loaded here': '此处不安装也不加载扩展',
    "Files are not written or loaded from the query editor; load one with INSERT … SELECT * FROM '~/file.csv'": "查询编辑器不写入也不加载文件；请用 INSERT … SELECT * FROM '~/file.csv' 加载文件",
    'Secrets are of no use here: this engine reaches no network': '此处密钥毫无用处：此引擎不访问任何网络',
    'Statements are not prepared here; write parameters as $name': '此处不预备语句；请将参数写作 $name',
    "The engine's settings are fixed; the schema is chosen above the editor": '引擎的设置是固定的；模式在编辑器上方选择',
    'The query editor changes tables, views, indexes, schemas, sequences, types and macros; this is something else': '查询编辑器可更改表、视图、索引、模式、序列、类型和宏；这是别的东西',
    'The statement could not be read': '无法读取该语句',
    'This result holds a moment with a time zone; select it with SELECT to see it': '此结果包含带时区的时刻；请用 SELECT 选择它以查看',
}
