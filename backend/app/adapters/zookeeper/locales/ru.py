"""Что пишет ZooKeeper, по-русски (D226). Термины следуют глоссарию экранов."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ZooKeeper": "ZooKeeper",
    "A ZooKeeper server. Walk its znode tree, read a znode's data as text or as JSON with its stat and ACL, edit the data against the version read, page through a znode's children as rows, and work in zkCli in a terminal.": "Сервер ZooKeeper. Обход дерева znode, чтение данных узла как текста или JSON вместе с его stat и ACL, правка данных с проверкой прочитанной версии, постраничный просмотр дочерних узлов в виде строк и работа в zkCli в терминале.",
    "Anonymous": "Анонимно",
    "Digest": "Digest",
    "Root path": "Корневой путь",
    "Everything is read under this path, as if it were the top; empty for the whole tree": "Всё читается под этим путём, как будто он вершина; пусто — всё дерево",
    "A root path starts with / and does not end with one": "Корневой путь начинается с / и не заканчивается им",
    "A root path has no empty, . or .. parts": "В корневом пути нет пустых частей, . и ..",
    "A ZooKeeper connect string carries no user; choose Digest instead": "Строка подключения ZooKeeper не содержит пользователя; выберите Digest",
    "Could not reach the ZooKeeper server": "Не удалось связаться с сервером ZooKeeper",
    "The root path does not exist on this server": "На этом сервере нет такого корневого пути",
    "The ZooKeeper server could not do that": "Сервер ZooKeeper не смог это выполнить",
    "The ZooKeeper server refused that": "Сервер ZooKeeper отказал",
    "This connection may not do that to this znode": "Этому подключению это действие с узлом не разрешено",
    "A znode with that name already exists": "Узел с таким именем уже существует",
    "The znode has children": "У узла есть дочерние узлы",
    "The server refused that ACL": "Сервер отклонил этот ACL",
    # Znodes and their data.
    '"{node_id}" is not a znode of this source': "«{node_id}» — не узел этого источника",
    "A znode is opened as text or as a JSON tree": "Узел открывается как текст или как дерево JSON",
    "View the data as JSON": "Показать данные как JSON",
    "Edit the data": "Изменить данные",
    "View the children": "Показать дочерние узлы",
    "The data is not JSON": "Данные — не JSON",
    "The data is not UTF-8 text, so it is shown as hex": "Данные — не текст UTF-8, поэтому показаны в шестнадцатеричном виде",
    "The data is not UTF-8 text, so it is shown as hex and not edited here": "Данные — не текст UTF-8, поэтому показаны в шестнадцатеричном виде и здесь не редактируются",
    "zkCli is not signed in. To read znodes with a digest ACL, type: addauth digest {user}:<password>": "zkCli не выполнил вход. Чтобы читать узлы с digest-ACL, введите: addauth digest {user}:<пароль>",
}
