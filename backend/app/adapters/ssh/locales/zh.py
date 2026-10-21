"""SSH 用简体中文写下的内容（D226）。术语遵循界面词汇表。

文件部分属于资源管理器并自行表述；这些词涉及服务器、其密钥和身份验证。
"""

MESSAGES: dict[str, str] = {
    # 数据源及其连接表单。
    "SSH": "SSH",
    "A server reached over SSH. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search, and a terminal. Signs in with a password or one of your SSH keys, and only to the server whose key you confirmed.": "通过 SSH 访问的服务器。从你选择的位置浏览其文件夹，像处理自己的文件一样处理其中的文件：表、对文件执行 SQL、编辑器、压缩包、搜索以及终端。使用密码或你的某个 SSH 密钥登录，并且只登录到你已确认其密钥的服务器。",
    "Authentication": "身份验证",
    "Host": "主机",
    "Port": "端口",
    "User": "用户",
    "Folder": "文件夹",
    "Where browsing starts; empty is the user's home folder": "浏览的起始位置；留空则为用户的主目录",
    "Server key": "服务器密钥",
    "What this server proves itself with; fetch it and compare": "此服务器用来证明自身身份的密钥；获取它并进行比对",
    "Key": "键",
    "One of your SSH keys; its public half goes to the server": "你的某个 SSH 密钥；其公钥部分会发送到服务器",
    "Password": "密码",
    # 地址。
    "The SSH connection has no host": "SSH 连接没有主机",
    "That is not an SSH URL": "这不是 SSH URL",
    "Enter the host first": "请先输入主机",
    # 密钥。
    "This is not a server key this application can read": "这不是此应用能够读取的服务器密钥",
    "That passphrase does not open this key": "该口令无法打开此密钥",
    "This key is protected by a passphrase; enter it": "此密钥受口令保护；请输入口令",
    "This is not a private key this application can read": "这不是此应用能够读取的私钥",
    # 连接。
    "Connection successful": "连接成功",
    "This connection signs in with a key, and none is at hand": "此连接使用密钥登录，但当前没有可用的密钥",
    "Fetch the server's key and confirm it before connecting": "请先获取服务器密钥并确认，然后再连接",
    "The server key of this connection cannot be read": "无法读取此连接的服务器密钥",
    "The SSH key could not be opened with its passphrase": "无法使用其口令打开 SSH 密钥",
    "The server did not present a key": "服务器未提供密钥",
    "The server presented a different key than the one this connection trusts. If it was reinstalled, fetch its key again and compare it": "服务器提供的密钥与此连接信任的密钥不同。如果服务器已重新安装，请重新获取其密钥并进行比对",
    "The server refused these credentials": "服务器拒绝了这些凭据",
    "That is no longer on the server": "该内容已不在服务器上",
    "The server does not let this user do that": "服务器不允许此用户执行该操作",
    "The server could not do that": "服务器无法执行该操作",
    "The server did not answer in time": "服务器未及时响应",
    "Could not reach the server": "无法连接到服务器",
    "Not a path below this folder: {path}": "不是此文件夹下的路径：{path}",
    # 通过 SFTP 访问的文件。
    "Symbolic links are not downloaded": "不下载符号链接",
    "A folder holding a symbolic link is not copied here": "包含符号链接的文件夹不会复制到此处",
    "What came out": "输出结果",
    "The file is no longer open": "文件已不再打开",
    "The file could not be read from the server": "无法从服务器读取文件",
    "The file could not be created on the server": "无法在服务器上创建文件",
    "The file could not be written on the server": "无法在服务器上写入文件",
    "The file could not be put in place on the server": "无法在服务器上放置文件",
    # 终端。
    "The server did not open a shell for this account": "服务器未为此账户打开 shell",
}
