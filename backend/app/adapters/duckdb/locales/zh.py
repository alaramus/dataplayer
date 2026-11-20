"""What DuckDB writes, in Chinese (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    'DuckDB': 'DuckDB',
    'A DuckDB database file in your personal storage. Browse its schemas, tables and views, and read rows a page at a time with sorting and filtering.': '您个人存储中的 DuckDB 数据库文件。浏览其模式、表和视图，并按页读取行，支持排序和筛选。',
    'Path of the file inside your personal storage, such as data/shop.duckdb': '文件在您个人存储中的路径，例如 data/shop.duckdb',
    'The database file is in use by another program': '数据库文件正被另一个程序使用',
    'The database reaches past your personal storage, which is refused': '数据库访问超出了您的个人存储范围，已被拒绝',
    'The file is not a DuckDB database this server can read': '该文件不是此服务器能够读取的 DuckDB 数据库',
    'This DuckDB source does not offer the "{representation}" content representation': '此 DuckDB 数据源不提供“{representation}”内容表示',
    "A filter value does not fit its column's type": '筛选值与其列的类型不符',
    'Rows of a DuckDB file are read only for now': 'DuckDB 文件的行目前为只读',
}
