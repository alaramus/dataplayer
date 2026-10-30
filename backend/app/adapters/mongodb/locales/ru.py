"""Что пишет MongoDB, по-русски (D226). Термины следуют глоссарию экранов."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
    "Authentication database": "База данных аутентификации",
    "Where the user is defined; admin unless it was made in another database": "Где определён пользователь; admin, если он не создан в другой базе данных",
    "Encrypted, with the server's certificate verified": "С шифрованием и проверкой сертификата сервера",
    "That is not a MongoDB connection string": "Это не строка подключения MongoDB",
    "A mongodb+srv address is not supported; name one server with mongodb://": "Адрес mongodb+srv не поддерживается; укажите один сервер через mongodb://",
    "Name one server; a list of servers is not supported": "Укажите один сервер; список серверов не поддерживается",
    "MongoDB {version} is older than this source supports ({oldest})": "MongoDB {version} старше, чем поддерживает этот источник ({oldest})",
    "The server asks for a user and a password": "Сервер требует пользователя и пароль",
    "The connection settings are not usable": "С этими настройками подключиться нельзя",
    "The server refused the request": "Сервер отклонил запрос",
    # Collections and documents.
    "View the definition": "Показать определение",
    '"{node_id}" is not a collection: expected database.collection': "«{node_id}» — не коллекция: ожидается база_данных.коллекция",
    '"{name}" belongs to the server': "«{name}» принадлежит серверу",
    "A collection has no columns of its own; every document has its own fields": "У коллекции нет собственных столбцов: у каждого документа свои поля",
    "Indexes are not changed here yet": "Индексы здесь пока не изменяются",
    "MongoDB has no constraints but unique indexes": "В MongoDB нет ограничений, кроме уникальных индексов",
    'This MongoDB source does not offer the "{representation}" content representation': "Этот источник MongoDB не предлагает представление содержимого «{representation}»",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server, and work in mongosh in a terminal.": "Сервер MongoDB. Просмотр баз данных, коллекций и представлений, чтение документов постранично в виде строк — поля определяются по самим документам, сортировка и фильтрация выполняются на сервере — и работа в mongosh в терминале.",
    "A console does not go through an SSH tunnel yet": "Консоль пока не работает через SSH-туннель",
    "A time series takes new documents; the ones in it are not changed here": "Временной ряд принимает новые документы; те, что в нём уже есть, здесь не изменяются",
    "A view's documents come from its pipeline and cannot be changed": "Документы представления берутся из его конвейера и не могут быть изменены",
    "Another document already has that value in a unique index": "У другого документа уже есть такое значение в уникальном индексе",
    "The collection's validator refused the document": "Валидатор коллекции отклонил документ",
    "This document is larger than 256 KB; only its beginning is shown.": "Этот документ больше 256 КБ; показано только его начало.",
    "View as documents": "Показать как документы",
}
