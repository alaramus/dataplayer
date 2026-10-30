"""MongoDB 写出的内容，中文版（D226）。术语遵循界面术语表。"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server.": "MongoDB 服务器。浏览数据库、集合和视图，并按页以行的形式读取文档，字段由文档本身确定，排序和筛选在服务器上完成。",
    "Authentication database": "认证数据库",
    "Where the user is defined; admin unless it was made in another database": "用户所在的数据库；除非用户创建在其他数据库中，否则为 admin",
    "Encrypted, with the server's certificate verified": "加密，并验证服务器证书",
    "That is not a MongoDB connection string": "这不是 MongoDB 连接字符串",
    "A mongodb+srv address is not supported; name one server with mongodb://": "不支持 mongodb+srv 地址；请用 mongodb:// 指定一台服务器",
    "Name one server; a list of servers is not supported": "请指定一台服务器；不支持服务器列表",
    "MongoDB {version} is older than this source supports ({oldest})": "MongoDB {version} 早于此数据源支持的版本（{oldest}）",
    "The server asks for a user and a password": "服务器要求提供用户和密码",
    "The connection settings are not usable": "这些连接设置无法使用",
    "The server refused the request": "服务器拒绝了请求",
    # Collections and documents.
    "View the definition": "查看定义",
    '"{node_id}" is not a collection: expected database.collection': "“{node_id}”不是集合：应为 数据库.集合",
    '"{name}" belongs to the server': "“{name}”属于服务器",
    "A collection has no columns of its own; every document has its own fields": "集合没有自己的列；每个文档都有自己的字段",
    "Indexes are not changed here yet": "此处暂不能修改索引",
    "MongoDB has no constraints but unique indexes": "MongoDB 除唯一索引外没有约束",
    "Documents are not changed here yet": "此处暂不能修改文档",
    'This MongoDB source does not offer the "{representation}" content representation': "此 MongoDB 数据源不提供“{representation}”内容表示",
}
