"""查询执行用简体中文写下的内容（D226）。术语遵循界面词汇表。"""

MESSAGES: dict[str, str] = {
    # 运行之前。
    "There is nothing to run": "没有可运行的内容",
    "This is more than one statement; run it as a script to run them all": "这不止一条语句；请将其作为脚本运行以执行全部语句",
    "A script may hold at most {count} statements": "脚本最多可包含 {count} 条语句",
    "Statement {at} is larger than one statement may be": "第 {at} 条语句超出了单条语句的大小上限",
    "Statement {at}: {refusal}": "第 {at} 条语句：{refusal}",
    "Maintenance commands run outside a transaction; turn the manual transaction off to run this": "维护命令在事务之外运行；请关闭手动事务以运行此命令",
    "A maintenance command runs outside a transaction, so run it on its own": "维护命令在事务之外运行，因此请单独运行它",
    "Statement {at} is a {kind} statement, and this run is a read": "第 {at} 条语句是 {kind} 语句，而本次运行是读取",
    "Statement {at} is a {kind} statement, and statements of that kind are not run here": "第 {at} 条语句是 {kind} 语句，此类语句不在此处运行",
    "No value was given for {names}": "未为 {names} 提供值",
    # 写入。
    "A write cannot run in read mode": "写入无法在读取模式下运行",
    "The owner of this connection allows reading only": "此连接的所有者仅允许读取",
    "A {kind} statement needs read access to this connection": "{kind} 语句需要对此连接的读取访问权限",
    "A {kind} statement needs write access to this connection": "{kind} 语句需要对此连接的写入访问权限",
    "A {kind} statement needs structure access to this connection": "{kind} 语句需要对此连接的结构访问权限",
    "A {kind} statement needs own access to this connection": "{kind} 语句需要对此连接的所有者权限",
    "Confirm this write before running it": "运行前请确认此写入",
    "This run asks for something that cannot be undone; confirm it first": "本次运行请求了无法撤销的操作；请先确认",
    "You have read access to this connection": "你拥有对此连接的读取访问权限",
    # 一次运行。
    "This run could not be completed": "本次运行无法完成",
    "There was no room to keep this result": "没有空间保留此结果",
    # 事务和历史记录。
    "Committed {count} changing statement, {rows} rows": "已提交 {count} 条更改语句，{rows} 行",
    "Committed {count} changing statements, {rows} rows": "已提交 {count} 条更改语句，{rows} 行",
    "Rolled back {count} changing statement": "已回滚 {count} 条更改语句",
    "Rolled back {count} changing statements": "已回滚 {count} 条更改语句",
    "Document deleted": "文档已删除",
    "{count} runs deleted": "已删除 {count} 次运行",
    # 搜索。
    "Favorites": "收藏",
    "Untitled query": "无标题查询",
    "Only the newest {count} saved queries are searched by their title": "仅按标题搜索最新的 {count} 个已保存查询",
    "Stopped before every saved query was read": "在读取所有已保存查询之前停止",
    "Only the newest {count} saved queries are searched by their text": "仅按文本搜索最新的 {count} 个已保存查询",
    "Saved query": "已保存查询",
    "Saved query · {connection}": "已保存查询 · {connection}",
}
