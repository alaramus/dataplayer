"""What SSH writes, in Russian (D226). Terms follow the screens' glossary.

The file side is the explorer's and words itself; these are the words of the
server, its key and signing in.
"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "SSH": "SSH",
    "A server reached over SSH. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search, and a terminal. Signs in with a password or one of your SSH keys, and only to the server whose key you confirmed.": "Сервер, доступный по SSH. Просмотр папок с выбранного места и работа с файлами как со своими: таблицы, SQL по файлам, редактор, архивы, поиск и терминал. Вход по паролю или одним из ваших SSH-ключей и только на сервер, ключ которого вы подтвердили.",
    "Authentication": "Аутентификация",
    "Host": "Хост",
    "Port": "Порт",
    "User": "Пользователь",
    "Folder": "Папка",
    "Where browsing starts; empty is the user's home folder": "С какой папки начинается просмотр; если пусто — домашняя папка пользователя",
    "Server key": "Ключ сервера",
    "What this server proves itself with; fetch it and compare": "Чем сервер подтверждает, что это он; получите ключ и сверьте его",
    "Key": "Ключ",
    "One of your SSH keys; its public half goes to the server": "Один из ваших SSH-ключей; на сервер передаётся его открытая часть",
    "Password": "Пароль",
    # Addresses.
    "The SSH connection has no host": "В SSH-подключении не указан хост",
    "That is not an SSH URL": "Это не SSH-адрес",
    "Enter the host first": "Сначала укажите хост",
    # Keys.
    "This is not a server key this application can read": "Этот ключ сервера не удаётся прочитать",
    "That passphrase does not open this key": "Эта парольная фраза не подходит к ключу",
    "This key is protected by a passphrase; enter it": "Ключ защищён парольной фразой; введите её",
    "This is not a private key this application can read": "Этот закрытый ключ не удаётся прочитать",
    # Connecting.
    "Connection successful": "Подключение установлено",
    "This connection signs in with a key, and none is at hand": "Это подключение входит по ключу, а ключ недоступен",
    "Fetch the server's key and confirm it before connecting": "Перед подключением получите ключ сервера и подтвердите его",
    "The server key of this connection cannot be read": "Не удаётся прочитать ключ сервера этого подключения",
    "The SSH key could not be opened with its passphrase": "Не удалось открыть SSH-ключ его парольной фразой",
    "The server did not present a key": "Сервер не предъявил ключ",
    "The server presented a different key than the one this connection trusts. If it was reinstalled, fetch its key again and compare it": "Сервер предъявил не тот ключ, которому доверяет это подключение. Если сервер переустановили, получите его ключ заново и сверьте",
    "The server refused these credentials": "Сервер не принял эти учётные данные",
    "That is no longer on the server": "Этого больше нет на сервере",
    "The server does not let this user do that": "Сервер не разрешает это этому пользователю",
    "The server could not do that": "Серверу не удалось это выполнить",
    "The server did not answer in time": "Сервер не ответил вовремя",
    "Could not reach the server": "Сервер недоступен",
    "Not a path below this folder: {path}": "Путь вне этой папки: {path}",
    # Files over SFTP.
    "Symbolic links are not downloaded": "Символические ссылки не скачиваются",
    "A folder holding a symbolic link is not copied here": "Папка с символической ссылкой здесь не копируется",
    "What came out": "Результат",
    "The file is no longer open": "Файл уже закрыт",
    "The file could not be read from the server": "Не удалось прочитать файл с сервера",
    "The file could not be created on the server": "Не удалось создать файл на сервере",
    "The file could not be written on the server": "Не удалось записать файл на сервер",
    "The file could not be put in place on the server": "Не удалось поместить файл на место на сервере",
    # The terminal.
    "The server did not open a shell for this account": "Сервер не открыл оболочку для этой учётной записи",
}
