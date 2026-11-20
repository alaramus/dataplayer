"""What FTP writes, in Russian (D226).

The file side is the explorer's and words itself; these are the words of the
server, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "FTP": "FTP",
    "A server reached over FTP or FTPS. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search and copying between connections. Signs in with a password or anonymously.": "Сервер, доступный по FTP или FTPS. Просмотр его папок с выбранного места и работа с файлами как со своими: таблицы, SQL по файлам, редактор, архивы, поиск и копирование между подключениями. Вход по паролю или анонимно.",
    "21, or 990 for implicit TLS": "21, или 990 для неявного TLS",
    "Encryption": "Шифрование",
    "TLS, explicit": "TLS, явный",
    "TLS, implicit": "TLS, неявный",
    "No encryption": "Без шифрования",
    "Off only for a server with a certificate of its own making": "Выключайте только для сервера с самодельным сертификатом",
    "Where browsing starts; empty is the folder the server signs you into": "С какого места начинается просмотр; пусто — папка, в которую сервер пускает при входе",
    "The host is a name or an address, without a scheme or a path": "Хост — это имя или адрес, без схемы и пути",
    "The folder is one line": "Папка пишется в одну строку",
    "The user is one line": "Пользователь пишется в одну строку",
    "A name with a line break in it cannot be sent to the server": "Имя с переводом строки нельзя отправить серверу",
    "Every connection to the server is busy": "Все соединения с сервером заняты",
    "That is not an FTP address": "Это не адрес FTP",
    "The FTP connection has no host": "У подключения FTP нет хоста",
    "The TLS connection to the server failed": "Не удалось установить TLS-соединение с сервером",
    "The file is no longer on the server": "Этого файла больше нет на сервере",
    "The server closed the connection": "Сервер закрыл соединение",
    "The server did not accept this user and password": "Сервер не принял этого пользователя и пароль",
    "The server does not let anonymous users in": "Сервер не пускает анонимных пользователей",
    "The server does not offer TLS; choose no encryption to sign in without it": "Сервер не поддерживает TLS; чтобы войти без него, выберите «Без шифрования»",
    "The server has too many connections open": "У сервера открыто слишком много соединений",
    "The server is busy; try again": "Сервер занят; попробуйте ещё раз",
    "The server refused that": "Сервер отказал",
    "The server's certificate was not accepted": "Сертификат сервера не принят",
    "The server's name could not be resolved": "Не удалось найти адрес сервера по имени",
    "There is no such folder on the server": "На сервере нет такой папки",
}
