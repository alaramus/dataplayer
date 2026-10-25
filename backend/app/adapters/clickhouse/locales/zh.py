"""ClickHouse 写出的内容，中文版（D226）。术语遵循界面术语表。"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    'A ClickHouse server, over its HTTP interface. Browse databases, tables and views, read rows a page at a time with sorting and filtering done by the server, and run SQL.': '通过 HTTP 接口连接的 ClickHouse 服务器。浏览数据库、表和视图，按页读取行（排序和筛选由服务器完成），并运行 SQL。',
    "The HTTP interface: 8123, or 8443 with TLS": "HTTP 接口：8123，或使用 TLS 时为 8443",
    "TLS": "TLS",
    "HTTPS, with the server's certificate verified": "HTTPS，并验证服务器的证书",
    "That is not a ClickHouse connection string": "这不是 ClickHouse 连接字符串",
    "ClickHouse {version} is older than this source supports ({oldest})": "ClickHouse {version} 早于此数据源支持的版本（{oldest}）",
    # Relations and rows.
    'This ClickHouse source does not offer the "{representation}" content representation': "此 ClickHouse 数据源不提供“{representation}”内容表示",
    "A filter value does not fit its column": "筛选值不适合其所在的列",
    "Changing the structure of a ClickHouse table is not supported yet": "暂不支持更改 ClickHouse 表的结构",
    "Editing ClickHouse rows is not supported yet": "暂不支持编辑 ClickHouse 的行",
    # The console.
    'ClickHouse keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own': 'ClickHouse 在更改完成时立即保留且无法撤销，因此更改不能与其他语句在同一次运行中执行；请单独运行它',
    'Detaching and attaching tables is not done from the query editor': '不在查询编辑器中分离或附加表',
    'Named collections are not changed from the query editor': '不在查询编辑器中更改命名集合',
    'SYSTEM commands manage the server and are not run from the query editor': 'SYSTEM 命令用于管理服务器，不在查询编辑器中运行',
    'The console shows a result itself; leave FORMAT out': '控制台会自行显示结果；请去掉 FORMAT',
    'The query editor changes databases, tables, views and dictionaries; this is something else': '查询编辑器更改数据库、表、视图和字典；这是其他内容',
}
