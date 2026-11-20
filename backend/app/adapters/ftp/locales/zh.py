"""What FTP writes, in Chinese (D226).

The file side is the explorer's and words itself; these are the words of the
server, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "FTP": "FTP",
    "A server reached over FTP or FTPS. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search and copying between connections. Signs in with a password or anonymously.": "通过 FTP 或 FTPS 访问的服务器。从您选择的位置浏览其文件夹，并像处理自己的文件一样处理其中的文件：表格、对文件运行 SQL、编辑器、归档、搜索以及在连接之间复制。使用密码或匿名登录。",
    "21, or 990 for implicit TLS": "21，隐式 TLS 为 990",
    "Encryption": "加密",
    "TLS, explicit": "TLS，显式",
    "TLS, implicit": "TLS，隐式",
    "No encryption": "不加密",
    "Off only for a server with a certificate of its own making": "仅对使用自制证书的服务器关闭",
    "Where browsing starts; empty is the folder the server signs you into": "浏览的起点；留空为服务器登录后所在的文件夹",
    "The host is a name or an address, without a scheme or a path": "主机是名称或地址，不含协议和路径",
    "The folder is one line": "文件夹只能写在一行内",
    "The user is one line": "用户只能写在一行内",
    "A name with a line break in it cannot be sent to the server": "含换行符的名称无法发送给服务器",
    "Every connection to the server is busy": "与服务器的所有连接都在使用中",
    "That is not an FTP address": "这不是 FTP 地址",
    "The FTP connection has no host": "FTP 连接没有主机",
    "The TLS connection to the server failed": "与服务器的 TLS 连接失败",
    "The file is no longer on the server": "该文件已不在服务器上",
    "The server closed the connection": "服务器关闭了连接",
    "The server did not accept this user and password": "服务器不接受此用户和密码",
    "The server does not let anonymous users in": "服务器不允许匿名用户登录",
    "The server does not offer TLS; choose no encryption to sign in without it": "服务器不提供 TLS；如需不加密登录，请选择不加密",
    "The server has too many connections open": "服务器打开的连接过多",
    "The server is busy; try again": "服务器繁忙；请重试",
    "The server refused that": "服务器拒绝了该操作",
    "The server's certificate was not accepted": "服务器的证书未被接受",
    "The server's name could not be resolved": "无法解析服务器名称",
    "There is no such folder on the server": "服务器上没有这个文件夹",
}
