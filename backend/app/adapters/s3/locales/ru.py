"""What S3 writes, in Russian (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the editor, archives, search and copying between connections. Buckets are made and deleted here too. Signs in with an access key.": "Amazon S3 или хранилище, совместимое с его API. Просмотр бакетов и папок и работа с объектами как со своими файлами: таблицы, SQL по файлам, редактор, архивы, поиск и копирование между подключениями. Здесь же создаются и удаляются бакеты. Вход по ключу доступа.",
    "The store's address, such as https://s3.example.com; empty for Amazon S3": "Адрес хранилища, например https://s3.example.com; пусто для Amazon S3",
    "Region": "Регион",
    "Empty is us-east-1": "Пусто — us-east-1",
    "Access key": "Ключ доступа",
    "Bucket": "Бакет",
    "Empty shows every bucket this key may list": "Пусто — все бакеты, которые видит этот ключ",
    "Where browsing starts inside the bucket": "С какого места внутри бакета начинается просмотр",
    "Addressing": "Адресация",
    "Auto is virtual-hosted on Amazon S3 and path-style elsewhere": "Авто — virtual-hosted для Amazon S3 и path-style для остальных",
    "Verify the certificate": "Проверять сертификат",
    "Off only for a store with a certificate of its own making": "Выключайте только для хранилища с самодельным сертификатом",
    "The endpoint must be an http or https address": "Точка доступа должна быть адресом http или https",
    "A bucket is one name, without slashes": "Бакет — это одно имя, без косых черт",
    "The folder must stay inside the bucket": "Папка должна оставаться внутри бакета",
    "A folder needs the bucket it is in": "Для папки нужен бакет, в котором она лежит",
    "The store does not know this access key": "Хранилище не знает этот ключ доступа",
    "The secret key does not match the access key": "Секретный ключ не подходит к ключу доступа",
    "The store does not let this key do that": "Хранилище не разрешает этому ключу это сделать",
    "There is no such bucket in this store": "В этом хранилище нет такого бакета",
    "The bucket is in another region than this connection names": "Бакет находится в другом регионе, чем указан в подключении",
    "This object is archived and has to be restored first": "Объект в архиве, сначала его нужно восстановить",
    "That is no longer in the store": "Этого уже нет в хранилище",
    "The store's certificate was not accepted": "Сертификат хранилища не принят",
    "The store did not answer in time": "Хранилище не ответило вовремя",
    "Could not reach the store": "Не удалось связаться с хранилищем",
    "The store could not do that": "Хранилище не смогло это сделать",
    "Only buckets are kept at the root of the store": "В корне хранилища лежат только бакеты",
    "{name} holds more than {count} objects; this store changes them one by one, so it is refused": "В {name} больше {count} объектов; хранилище меняет их по одному, поэтому это не делается",
    "The store did not delete every object": "Хранилище удалило не все объекты",
    "A bucket is not renamed or copied as a whole": "Бакет нельзя переименовать или скопировать целиком",
    "A bucket's name is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending with a letter or a digit": "Имя бакета — от 3 до 63 строчных латинских букв, цифр, точек и дефисов, начинается и заканчивается буквой или цифрой",
    "{name} keeps old versions of its objects; empty it with a lifecycle rule, then delete it": "{name} хранит старые версии объектов; очистите его правилом жизненного цикла, потом удалите",
}
