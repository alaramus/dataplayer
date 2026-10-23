"""文件存储用简体中文写下的内容（D226）。它所依赖的资源管理器带来自己的用语；
两者都写出的同一句话措辞一致。"""

MESSAGES: dict[str, str] = {
    "Files": "文件",
    "Your personal storage on this server. Browse folders and open files through representations appropriate to their content.": "你在此服务器上的个人存储。浏览文件夹，并以适合其内容的表示形式打开文件。",
    "Path": "路径",
    "Path inside your personal storage": "个人存储中的路径",
    "The path must stay inside your personal storage": "路径必须位于你的个人存储中",
    "The folder must stay inside your personal storage": "文件夹必须位于你的个人存储中",
    "Path outside the connector root: {node_id}": "路径位于连接根目录之外：{node_id}",
    "A connection path cannot start or end with spaces": "连接路径不能以空格开头或结尾",
    "Symbolic links are not downloaded": "不下载符号链接",
    "The directory does not exist or cannot be read": "目录不存在或无法读取",
    "Directory is readable": "目录可读",
}
