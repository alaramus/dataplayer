"""ZooKeeper 写给人看的文字，中文 (D226)。"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ZooKeeper": "ZooKeeper",
    "A ZooKeeper server. Walk its znode tree, read a znode's data as text or as JSON with its stat and ACL, edit the data against the version read, page through a znode's children as rows, and work in zkCli in a terminal.": "ZooKeeper 服务器。浏览 znode 树，以文本或 JSON 读取 znode 的数据及其 stat 和 ACL，按读取时的版本编辑数据，以行的形式分页查看 znode 的子节点，并在终端中使用 zkCli。",
    "Anonymous": "匿名",
    "Digest": "Digest",
    "Root path": "根路径",
    "Everything is read under this path, as if it were the top; empty for the whole tree": "所有内容都在此路径下读取，仿佛它就是顶层；留空表示整棵树",
    "A root path starts with / and does not end with one": "根路径以 / 开头，且不以 / 结尾",
    "A root path has no empty, . or .. parts": "根路径不能包含空段、. 或 ..",
    "A ZooKeeper connect string carries no user; choose Digest instead": "ZooKeeper 连接串不包含用户；请改选 Digest",
    "Could not reach the ZooKeeper server": "无法连接到 ZooKeeper 服务器",
    "The root path does not exist on this server": "此服务器上不存在该根路径",
    "The ZooKeeper server could not do that": "ZooKeeper 服务器无法执行此操作",
    "The ZooKeeper server refused that": "ZooKeeper 服务器拒绝了此操作",
    "This connection may not do that to this znode": "此连接无权对该 znode 执行此操作",
    "A znode with that name already exists": "同名 znode 已存在",
    "The znode has children": "该 znode 有子节点",
    "The server refused that ACL": "服务器拒绝了该 ACL",
    # Znodes and their data.
    '"{node_id}" is not a znode of this source': "“{node_id}”不是此数据源的 znode",
    "A znode is opened as text or as a JSON tree": "znode 以文本或 JSON 树的形式打开",
    "View the data as JSON": "以 JSON 查看数据",
    "Edit the data": "编辑数据",
    "View the children": "查看子节点",
    "The data is not JSON": "数据不是 JSON",
    "The data is not UTF-8 text, so it is shown as hex": "数据不是 UTF-8 文本，因此以十六进制显示",
    "The data is not UTF-8 text, so it is shown as hex and not edited here": "数据不是 UTF-8 文本，因此以十六进制显示，且不能在此编辑",
    "zkCli is not signed in. To read znodes with a digest ACL, type: addauth digest {user}:<password>": "zkCli 尚未认证。要读取带 digest ACL 的 znode，请输入：addauth digest {user}:<密码>",
}
