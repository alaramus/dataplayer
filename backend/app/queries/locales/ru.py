"""What running queries says, in Russian (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # Before a run.
    "There is nothing to run": "Нечего выполнять",
    "This is more than one statement; run it as a script to run them all": "Здесь больше одной инструкции; чтобы выполнить все, запустите их как скрипт",
    "A script may hold at most {count} statements": "Наибольшее число инструкций в скрипте: {count}",
    "Statement {at} is larger than one statement may be": "Инструкция {at} больше допустимого размера",
    "Statement {at}: {refusal}": "Инструкция {at}: {refusal}",
    "Maintenance commands run outside a transaction; turn the manual transaction off to run this": "Команды обслуживания выполняются вне транзакции; чтобы выполнить эту, выключите ручную транзакцию",
    "A maintenance command runs outside a transaction, so run it on its own": "Команда обслуживания выполняется вне транзакции, поэтому запускайте её отдельно",
    "Statement {at} is a {kind} statement, and this run is a read": "Инструкция {at} относится к классу {kind}, а этот запуск только читает",
    "Statement {at} is a {kind} statement, and statements of that kind are not run here": "Инструкция {at} относится к классу {kind}, а такие инструкции здесь не выполняются",
    "No value was given for {names}": "Не задано значение для: {names}",
    # Writing.
    "A write cannot run in read mode": "Запись нельзя выполнить в режиме чтения",
    "The owner of this connection allows reading only": "Владелец этого подключения разрешает только чтение",
    "A {kind} statement needs read access to this connection": "Для инструкции {kind} нужен доступ на чтение к этому подключению",
    "A {kind} statement needs write access to this connection": "Для инструкции {kind} нужен доступ на запись к этому подключению",
    "A {kind} statement needs structure access to this connection": "Для инструкции {kind} нужен доступ к структуре этого подключения",
    "A {kind} statement needs own access to this connection": "Для инструкции {kind} нужны права владельца этого подключения",
    "Confirm this write before running it": "Подтвердите запись перед выполнением",
    "This run asks for something that cannot be undone; confirm it first": "Этот запуск делает то, что нельзя отменить; сначала подтвердите его",
    "You have read access to this connection": "У вас доступ к этому подключению только на чтение",
    # A run.
    "This run could not be completed": "Не удалось завершить запуск",
    "There was no room to keep this result": "Для этого результата не хватило места",
    # Transactions and history.
    "Committed {count} changing statement, {rows} rows": "Зафиксировано изменяющих инструкций: {count}, строк: {rows}",
    "Committed {count} changing statements, {rows} rows": "Зафиксировано изменяющих инструкций: {count}, строк: {rows}",
    "Rolled back {count} changing statement": "Откачено изменяющих инструкций: {count}",
    "Rolled back {count} changing statements": "Откачено изменяющих инструкций: {count}",
    "Document deleted": "Документ удалён",
    "{count} runs deleted": "Удалено запусков: {count}",
    # Search.
    "Favorites": "Избранное",
    "Untitled query": "Запрос без названия",
    "Only the newest {count} saved queries are searched by their title": "По названию ищутся только последние сохранённые запросы: {count}",
    "Stopped before every saved query was read": "Остановлено, прежде чем были прочитаны все сохранённые запросы",
    "Only the newest {count} saved queries are searched by their text": "По тексту ищутся только последние сохранённые запросы: {count}",
    "Saved query": "Сохранённый запрос",
    "Saved query · {connection}": "Сохранённый запрос · {connection}",
}
