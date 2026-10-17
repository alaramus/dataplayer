"""What the TimescaleDB actions and reports write, in Russian (D226).

Terms follow the screens' glossary; TimescaleDB's own function and option
names stay as they are.
"""

MESSAGES: dict[str, str] = {
    # Lengths, as a preview shows them.
    "{amount} second": "{amount} с",
    "{amount} seconds": "{amount} с",
    "{amount} minute": "{amount} мин",
    "{amount} minutes": "{amount} мин",
    "{amount} hour": "{amount} ч",
    "{amount} hours": "{amount} ч",
    "{amount} day": "{amount} дн.",
    "{amount} days": "{amount} дн.",
    "{amount} week": "{amount} нед.",
    "{amount} weeks": "{amount} нед.",
    "{amount} month": "{amount} мес.",
    "{amount} months": "{amount} мес.",
    "{amount} year": "{amount} г.",
    "{amount} years": "{amount} г.",
    "{amount} value": "{amount} знач.",
    "{amount} values": "{amount} знач.",
    # Reports.
    "Hypertables": "Гипертаблицы",
    "Hypertable owners, dimension/chunk counts and compression configuration": (
        "Владельцы гипертаблиц, число измерений и чанков, настройки сжатия"
    ),
    "Continuous aggregates": "Непрерывные агрегаты",
    "Aggregate owners, source/materialization identities and configuration": (
        "Владельцы агрегатов, исходные и материализованные таблицы, настройки"
    ),
    "Chunks": "Чанки",
    "Chunk identities, primary-dimension boundaries and compression status": (
        "Чанки, границы по основному измерению и состояние сжатия"
    ),
    "Dimensions": "Измерения",
    "Time, integer and space dimensions of each hypertable": (
        "Временные, целочисленные и пространственные измерения каждой гипертаблицы"
    ),
    "Policies and jobs": "Политики и задачи",
    "Native TimescaleDB jobs, including policies and their schedules": (
        "Собственные задачи TimescaleDB, включая политики и их расписания"
    ),
    "Job statistics": "Статистика задач",
    "Recorded native job runs, outcomes and counters; unrun jobs may be absent": (
        "Записанные запуски задач, их итоги и счётчики; задачи, которые ещё не запускались, могут отсутствовать"
    ),
    "Detached chunks": "Отсоединённые чанки",
    "Tables named like a chunk that no hypertable holds; Attach chunk takes one back": (
        "Таблицы с именем чанка, которые не входят ни в одну гипертаблицу; «Присоединить таблицу как чанк» "
        "возвращает такую таблицу"
    ),
    "This report cannot be inspected by this connection": "Это подключение не может прочитать этот отчёт",
    "The installed TimescaleDB lacks the public API for this view": (
        "В установленной версии TimescaleDB нет открытого API для этого представления"
    ),
    # Discovering TimescaleDB.
    "TimescaleDB is not installed on this database": "TimescaleDB не установлен в этой базе данных",
    "This source has no usable TimescaleDB API": "У этого источника нет пригодного API TimescaleDB",
    "This connection may not inspect installed extensions": (
        "Этому подключению нельзя просматривать установленные расширения"
    ),
    "Installed extensions could not be inspected": "Не удалось прочитать установленные расширения",
    "The installed TimescaleDB version could not be read": "Не удалось прочитать установленную версию TimescaleDB",
    "TimescaleDB extension metadata could not be read": "Не удалось прочитать метаданные расширения TimescaleDB",
    "This TimescaleDB major version is not supported": "Эта основная версия TimescaleDB не поддерживается",
    "This connection may not inspect TimescaleDB metadata": "Этому подключению нельзя читать метаданные TimescaleDB",
    "TimescaleDB metadata could not be inspected": "Не удалось прочитать метаданные TimescaleDB",
    "The installed version lacks the supported inspection API": (
        "В установленной версии нет поддерживаемого API для чтения метаданных"
    ),
    "TimescaleDB action vocabulary could not be inspected": "Не удалось определить, какие действия TimescaleDB доступны",
    "The TimescaleDB {routine} API is not usable by this connection": (
        "Это подключение не может использовать API TimescaleDB {routine}"
    ),
    "The TimescaleDB {type} type is not usable by this connection": (
        "Это подключение не может использовать тип TimescaleDB {type}"
    ),
    "This connection may not lock TimescaleDB public metadata": (
        "Этому подключению нельзя блокировать открытые метаданные TimescaleDB"
    ),
    # A relation's TimescaleDB facts.
    "TimescaleDB metadata no longer identifies this relation uniquely": (
        "Метаданные TimescaleDB больше не определяют это отношение однозначно"
    ),
    "TimescaleDB metadata inspection timed out": "Время чтения метаданных TimescaleDB истекло",
    "TimescaleDB metadata could not be inspected safely": "Не удалось безопасно прочитать метаданные TimescaleDB",
    "TimescaleDB size inspection timed out": "Время определения размера в TimescaleDB истекло",
    "TimescaleDB compression inspection timed out": "Время чтения статистики сжатия TimescaleDB истекло",
    "TimescaleDB size could not be inspected safely": "Не удалось безопасно определить размер в TimescaleDB",
    "TimescaleDB compression statistics could not be inspected safely": (
        "Не удалось безопасно прочитать статистику сжатия TimescaleDB"
    ),
    # Which tables an action takes.
    "Choose one user hypertable": "Выберите одну пользовательскую гипертаблицу",
    "Choose one user continuous aggregate": "Выберите один пользовательский непрерывный агрегат",
    "Choose an owned hypertable": "Выберите гипертаблицу, владельцем которой вы являетесь",
    "Choose an owned hypertable with one time dimension": (
        "Выберите гипертаблицу с одним временным измерением, владельцем которой вы являетесь"
    ),
    "Choose an owned hypertable partitioned by time": (
        "Выберите гипертаблицу с секционированием по времени, владельцем которой вы являетесь"
    ),
    "Choose an owned continuous aggregate": "Выберите непрерывный агрегат, владельцем которого вы являетесь",
    "Only timestamp and date dimensions are supported here": "Здесь поддерживаются только измерения типов timestamp и date",
    "Only a hypertable with one range dimension is maintained here": (
        "Здесь обслуживаются только гипертаблицы с одним измерением по диапазону"
    ),
    "Only timestamp, date and integer dimensions are supported here": (
        "Здесь поддерживаются только измерения типов timestamp, date и целочисленные"
    ),
    "Only aggregates over timestamp and date dimensions are supported here": (
        "Здесь поддерживаются только агрегаты по измерениям типов timestamp и date"
    ),
    # Reviewing and applying a plan.
    "The operation plan changed; review it again": "План операции изменился; проверьте его снова",
    "Validation timed out; review the plan again": "Время проверки истекло; проверьте план снова",
    "The source changed or is busy; review the plan again": "Источник изменился или занят; проверьте план снова",
    "The change could not be confirmed; reload the source before reviewing again": (
        "Не удалось подтвердить изменение; перезагрузите источник, прежде чем проверять снова"
    ),
    "The change ran past its {seconds} seconds and was rolled back": (
        "Изменение не уложилось в {seconds} с и было откачено"
    ),
    "This connection may not make this change or lock its metadata": (
        "Этому подключению нельзя вносить это изменение или блокировать его метаданные"
    ),
    "The source refused the change": "Источник отказался вносить изменение",
    "Runs in Activity, one such job per connection at a time; access is checked again before every chunk": (
        "Выполняется в разделе «Активность», одна такая задача на подключение одновременно; "
        "доступ проверяется заново перед каждым чанком"
    ),
    "Runs in Activity, one such job per connection at a time; access is checked again before every unit": (
        "Выполняется в разделе «Активность», одна такая задача на подключение одновременно; "
        "доступ проверяется заново перед каждым шагом"
    ),
    # Shared lines of a preview.
    "Time dimension: {column}": "Временное измерение: {column}",
    "Unit": "Единица",
    "{chunk}: {start} to {end}": "{chunk}: с {start} по {end}",
    "…and {count} more": "…и ещё {count}",
    "Whole chunks from the earliest chunk to {end}": "Целые чанки от самого раннего до {end}",
    "Whole chunks from {start} to {end}": "Целые чанки с {start} по {end}",
    "Give an instant with its time zone, such as 2026-01-15T00:00:00Z, or a whole number": (
        "Укажите момент времени с часовым поясом, например 2026-01-15T00:00:00Z, или целое число"
    ),
    "The number is outside the range of a bigint": "Число выходит за пределы диапазона bigint",
    "Both ends are instants, or both are numbers": "Обе границы должны быть моментами времени или обе — числами",
    "The range must start before it ends": "Начало диапазона должно быть раньше его конца",
    "The window must start before it ends": "Начало окна должно быть раньше его конца",
    "Chunks ending at or before": "Чанки, заканчивающиеся не позже",
    "With its time zone; only chunks lying entirely inside the window are chosen": (
        "С часовым поясом; выбираются только чанки, целиком лежащие внутри окна"
    ),
    "and starting at or after": "и начинающиеся не раньше",
    "Leave empty for every earlier chunk": "Оставьте пустым, чтобы взять все более ранние чанки",
    # Chunk interval.
    "Change chunk interval": "Изменить интервал чанков",
    "Review the interval plan before applying it": "Проверьте план изменения интервала, прежде чем применять его",
    "Future chunk interval changed; existing chunks were not repartitioned": (
        "Интервал будущих чанков изменён; существующие чанки не перераспределялись"
    ),
    "Change the future chunk interval for {target}": "Изменить интервал будущих чанков {target}",
    "Current interval: {interval}": "Текущий интервал: {interval}",
    "Requested interval: {interval}": "Новый интервал: {interval}",
    "Only future chunks use the new interval; existing chunks are not repartitioned": (
        "Новый интервал действует только для будущих чанков; существующие чанки не перераспределяются"
    ),
    "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait": (
        "Ненадолго блокирует метаданные TimescaleDB во всей базе данных; создание новых чанков может подождать"
    ),
    "TimescaleDB interval metadata could not be inspected safely": (
        "Не удалось безопасно прочитать метаданные интервала TimescaleDB"
    ),
    "TimescaleDB interval planning timed out": "Время планирования интервала TimescaleDB истекло",
    "Calendar chunk intervals are not supported by this strategy": (
        "Календарные интервалы чанков в этом способе не поддерживаются"
    ),
    "Date dimensions require whole days or weeks": "Для измерений типа date нужны целые дни или недели",
    "Interval validation timed out; review the plan again": "Время проверки интервала истекло; проверьте план снова",
    "This connection may not change the interval or lock its metadata": (
        "Этому подключению нельзя менять интервал или блокировать его метаданные"
    ),
    "The source refused the interval change": "Источник отказался менять интервал",
    "The interval change could not be confirmed; reload the source before reviewing again": (
        "Не удалось подтвердить изменение интервала; перезагрузите источник, прежде чем проверять снова"
    ),
    # Retention and compression policies.
    "Set retention policy": "Задать политику хранения",
    "Remove retention policy": "Удалить политику хранения",
    "Set compression policy": "Задать политику сжатия",
    "Remove compression policy": "Удалить политику сжатия",
    "TimescaleDB will keep dropping old chunks by itself, even after this session ends. Set this policy?": (
        "TimescaleDB будет сам удалять старые чанки, даже после завершения этого сеанса. Задать политику?"
    ),
    "Drop chunks older than": "Удалять чанки старше",
    "Compress chunks older than": "Сжимать чанки старше",
    "Set the retention policy for {target}": "Задать политику хранения для {target}",
    "Remove the retention policy from {target}": "Удалить политику хранения у {target}",
    "Set the compression policy for {target}": "Задать политику сжатия для {target}",
    "Remove the compression policy from {target}": "Удалить политику сжатия у {target}",
    "No retention policy exists yet": "Политики хранения пока нет",
    "No compression policy exists yet": "Политики сжатия пока нет",
    "older than {age}": "старше {age}",
    "created more than {age} ago": "созданные более {age} назад",
    "Removes job {job}, which drops chunks {chunks}": "Удаляет задачу {job}, которая удаляет чанки {chunks}",
    "Replaces job {job}, which drops chunks {chunks}": "Заменяет задачу {job}, которая удаляет чанки {chunks}",
    "Removes job {job}, which compresses chunks {chunks}": "Удаляет задачу {job}, которая сжимает чанки {chunks}",
    "Replaces job {job}, which compresses chunks {chunks}": "Заменяет задачу {job}, которая сжимает чанки {chunks}",
    "The current policy runs every {every}; its replacement uses TimescaleDB's default schedule": (
        "Текущая политика выполняется каждые {every}; новая будет работать по расписанию TimescaleDB по умолчанию"
    ),
    "New policy: drop chunks older than {age}": "Новая политика: удалять чанки старше {age}",
    "New policy: compress chunks older than {age}": "Новая политика: сжимать чанки старше {age}",
    "TimescaleDB keeps dropping whole chunks older than this on its own schedule, after this session ends": (
        "TimescaleDB будет удалять целые чанки старше этого срока по своему расписанию и после завершения сеанса"
    ),
    "TimescaleDB stops dropping old chunks automatically; chunks already dropped do not return": (
        "TimescaleDB перестанет автоматически удалять старые чанки; уже удалённые чанки не вернутся"
    ),
    "TimescaleDB keeps compressing chunks older than this on its own schedule; compressed chunks stay readable": (
        "TimescaleDB будет сжимать чанки старше этого срока по своему расписанию; сжатые чанки остаются доступными "
        "для чтения"
    ),
    "TimescaleDB stops compressing chunks automatically; chunks already compressed stay compressed": (
        "TimescaleDB перестанет автоматически сжимать чанки; уже сжатые чанки останутся сжатыми"
    ),
    "Other policy changes made here in this database wait until it commits, and so may a policy run starting meanwhile": (
        "Другие изменения политик в этой базе данных ждут фиксации, как и запуск политики, начавшийся в это время"
    ),
    "Review the retention policy plan before applying it": (
        "Проверьте план политики хранения, прежде чем применять его"
    ),
    "Review the compression policy plan before applying it": (
        "Проверьте план политики сжатия, прежде чем применять его"
    ),
    "Retention policy set: TimescaleDB drops chunks older than {age} on its own schedule": (
        "Политика хранения задана: TimescaleDB удаляет чанки старше {age} по своему расписанию"
    ),
    "Retention policy removed; TimescaleDB no longer drops old chunks automatically": (
        "Политика хранения удалена; TimescaleDB больше не удаляет старые чанки автоматически"
    ),
    "Compression policy set: TimescaleDB compresses chunks older than {age} on its own schedule": (
        "Политика сжатия задана: TimescaleDB сжимает чанки старше {age} по своему расписанию"
    ),
    "Compression policy removed; TimescaleDB no longer compresses chunks automatically": (
        "Политика сжатия удалена; TimescaleDB больше не сжимает чанки автоматически"
    ),
    "This hypertable has several retention policy jobs; manage them with SQL": (
        "У этой гипертаблицы несколько задач политики хранения; управляйте ими через SQL"
    ),
    "This hypertable has several compression policy jobs; manage them with SQL": (
        "У этой гипертаблицы несколько задач политики сжатия; управляйте ими через SQL"
    ),
    "The existing retention policy could not be read safely; manage it with SQL": (
        "Не удалось безопасно прочитать текущую политику хранения; управляйте ею через SQL"
    ),
    "The existing compression policy could not be read safely; manage it with SQL": (
        "Не удалось безопасно прочитать текущую политику сжатия; управляйте ею через SQL"
    ),
    "TimescaleDB retention policy planning timed out": "Время планирования политики хранения TimescaleDB истекло",
    "TimescaleDB compression policy planning timed out": "Время планирования политики сжатия TimescaleDB истекло",
    "TimescaleDB retention policy metadata could not be inspected safely": (
        "Не удалось безопасно прочитать метаданные политики хранения TimescaleDB"
    ),
    "TimescaleDB compression policy metadata could not be inspected safely": (
        "Не удалось безопасно прочитать метаданные политики сжатия TimescaleDB"
    ),
    "Enable compression on this hypertable first": "Сначала включите сжатие для этой гипертаблицы",
    "This hypertable has no retention policy": "У этой гипертаблицы нет политики хранения",
    "This hypertable has no compression policy": "У этой гипертаблицы нет политики сжатия",
    "Date dimensions require whole days, weeks, months or years": (
        "Для измерений типа date нужны целые дни, недели, месяцы или годы"
    ),
    "The existing retention policy is paused; remove it before setting a new one": (
        "Текущая политика хранения приостановлена; удалите её, прежде чем задавать новую"
    ),
    "The existing compression policy is paused; remove it before setting a new one": (
        "Текущая политика сжатия приостановлена; удалите её, прежде чем задавать новую"
    ),
    # Refresh policies of continuous aggregates.
    "Set refresh policy": "Задать политику обновления",
    "Remove refresh policy": "Удалить политику обновления",
    "Window starts": "Начало окна",
    "How long ago the refreshed window begins": "Как давно начинается обновляемое окно",
    "Window ends": "Конец окна",
    "How long ago it ends; more recent than the start": "Как давно оно заканчивается; ближе к настоящему, чем начало",
    "Refresh every": "Обновлять каждые",
    "Set the refresh policy for {target}": "Задать политику обновления для {target}",
    "Remove the refresh policy from {target}": "Удалить политику обновления у {target}",
    "Source hypertable: {source}": "Исходная гипертаблица: {source}",
    "No refresh policy exists yet": "Политики обновления пока нет",
    "from the earliest data to the latest data": "от самых ранних данных до самых свежих",
    "from the earliest data to {end} ago": "от самых ранних данных до момента {end} назад",
    "from {start} ago to the latest data": "от момента {start} назад до самых свежих данных",
    "from {start} ago to {end} ago": "от момента {start} назад до момента {end} назад",
    "Removes job {job}, which refreshes {window} every {every}": (
        "Удаляет задачу {job}, которая обновляет данные {window} каждые {every}"
    ),
    "Replaces job {job}, which refreshes {window} every {every}": (
        "Заменяет задачу {job}, которая обновляет данные {window} каждые {every}"
    ),
    "New policy: refresh from {start} ago to {end} ago, every {every}": (
        "Новая политика: обновлять данные от момента {start} назад до момента {end} назад каждые {every}"
    ),
    "The source hypertable has no retention policy": "У исходной гипертаблицы нет политики хранения",
    "The source drops chunks older than {age}; the window starts after that": (
        "Источник удаляет чанки старше {age}; окно начинается позже"
    ),
    "The source drops chunks {chunks}; check that it keeps the raw data this window refreshes": (
        "Источник удаляет чанки {chunks}; убедитесь, что он хранит исходные данные, которые обновляет это окно"
    ),
    "TimescaleDB stops refreshing this aggregate automatically; its materialized rows stay as they are": (
        "TimescaleDB перестанет автоматически обновлять этот агрегат; его материализованные строки останутся как есть"
    ),
    "TimescaleDB keeps refreshing this window on its own schedule, after this session ends": (
        "TimescaleDB будет обновлять это окно по своему расписанию и после завершения сеанса"
    ),
    "This continuous aggregate has no refresh policy": "У этого непрерывного агрегата нет политики обновления",
    "Review the refresh policy plan before applying it": "Проверьте план политики обновления, прежде чем применять его",
    "Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule": (
        "Политика обновления задана: TimescaleDB обновляет этот агрегат по своему расписанию"
    ),
    "Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically": (
        "Политика обновления удалена; TimescaleDB больше не обновляет этот агрегат автоматически"
    ),
    "The existing refresh policy is paused; remove it before setting a new one": (
        "Текущая политика обновления приостановлена; удалите её, прежде чем задавать новую"
    ),
    "TimescaleDB refresh policy planning timed out": "Время планирования политики обновления TimescaleDB истекло",
    "TimescaleDB refresh policy metadata could not be inspected safely": (
        "Не удалось безопасно прочитать метаданные политики обновления TimescaleDB"
    ),
    "This continuous aggregate has several refresh policy jobs; manage them with SQL": (
        "У этого непрерывного агрегата несколько задач политики обновления; управляйте ими через SQL"
    ),
    "The existing refresh policy could not be read safely; manage it with SQL": (
        "Не удалось безопасно прочитать текущую политику обновления; управляйте ею через SQL"
    ),
    "Date dimensions require offsets in whole days, weeks, months or years": (
        "Для измерений типа date смещения задаются целыми днями, неделями, месяцами или годами"
    ),
    "The window must start further back than it ends": "Начало окна должно быть дальше в прошлом, чем его конец",
    "The window reaches data the source's retention policy drops (older than {age}); refreshing there would remove aggregated rows": (
        "Окно захватывает данные, которые удаляет политика хранения источника (старше {age}); обновление там "
        "удалит агрегированные строки"
    ),
    # Compression settings.
    "Configure compression": "Настроить сжатие",
    "Segment by": "Сегментировать по",
    "One column per line; leave empty for none": "По одному столбцу в строке; оставьте пустым, чтобы не задавать",
    "Order by": "Упорядочить по",
    "One column per line, optionally followed by ASC or DESC and NULLS FIRST or NULLS LAST; the time column is added descending when neither list names it": (
        "По одному столбцу в строке, при необходимости с ASC или DESC и NULLS FIRST или NULLS LAST; если ни один "
        "список не называет столбец времени, он добавляется по убыванию"
    ),
    "TimescaleDB compression settings could not be inspected safely": (
        "Не удалось безопасно прочитать настройки сжатия TimescaleDB"
    ),
    "Change the compression settings of {target}": "Изменить настройки сжатия {target}",
    "Enable compression on {target}": "Включить сжатие для {target}",
    "Current segment by: {columns}": "Сейчас сегментируется по: {columns}",
    "Current segment by: none": "Сейчас сегментация не задана",
    "Current order by: {columns}": "Сейчас упорядочивается по: {columns}",
    "Current order by: none": "Сейчас порядок не задан",
    "Compression is not enabled yet": "Сжатие пока не включено",
    "New segment by: {columns}": "Новая сегментация по: {columns}",
    "New segment by: none": "Новая сегментация: не задана",
    "New order by: {columns}": "Новый порядок по: {columns}",
    "Already compressed chunks keep the settings they were compressed with": (
        "Уже сжатые чанки сохраняют настройки, с которыми были сжаты"
    ),
    "TimescaleDB recommends segmenting or ordering by the unique column {column}": (
        "TimescaleDB рекомендует сегментировать или упорядочивать по уникальному столбцу {column}"
    ),
    "Review the compression settings plan before applying it": (
        "Проверьте план настроек сжатия, прежде чем применять его"
    ),
    "Compression settings changed; only chunks compressed from now on use them": (
        "Настройки сжатия изменены; они действуют только для чанков, сжатых с этого момента"
    ),
    "Compression enabled; chunks are compressed by a compression policy or on request": (
        "Сжатие включено; чанки сжимаются политикой сжатия или по запросу"
    ),
    "Nothing is compressed now; chunks are compressed later by a compression policy or on request": (
        "Сейчас ничего не сжимается; чанки будут сжаты позже политикой сжатия или по запросу"
    ),
    "Only chunks compressed from now on use these settings; already compressed chunks keep theirs": (
        "Эти настройки действуют только для чанков, сжатых с этого момента; уже сжатые сохраняют свои"
    ),
    "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits": (
        "Монопольно блокирует гипертаблицу на время изменения настроек; чтение и запись ждут фиксации"
    ),
    "Column \"{column}\" is listed more than once": "Столбец «{column}» указан больше одного раза",
    "List at most {count} segment-by columns": "Укажите не больше {count} столбцов сегментации",
    "List at most {count} order-by columns": "Укажите не больше {count} столбцов порядка",
    "Each line names one column": "В каждой строке должен быть один столбец",
    "This hypertable has no column \"{column}\"": "В этой гипертаблице нет столбца «{column}»",
    "The current compression settings could not be read": "Не удалось прочитать текущие настройки сжатия",
    "TimescaleDB compression settings planning timed out": "Время планирования настроек сжатия TimescaleDB истекло",
    # Converting a table.
    "Convert to hypertable": "Преобразовать в гипертаблицу",
    "The table becomes a hypertable, which DataPlayer cannot turn back into an ordinary table. Convert it?": (
        "Таблица станет гипертаблицей, и DataPlayer не сможет снова сделать её обычной таблицей. Преобразовать?"
    ),
    "Time column": "Столбец времени",
    "A timestamp or date column of this table": "Столбец этой таблицы типа timestamp или date",
    "Chunk interval": "Интервал чанков",
    "The table could not be inspected safely for conversion": (
        "Не удалось безопасно проверить таблицу перед преобразованием"
    ),
    "Convert {target} into a hypertable": "Преобразовать {target} в гипертаблицу",
    "Time column: {column} ({type})": "Столбец времени: {column} ({type})",
    "Chunk interval: {interval}": "Интервал чанков: {interval}",
    "The table is empty, and the conversion refuses if a row arrives before it runs": (
        "Таблица пуста; преобразование будет отклонено, если до его запуска появится строка"
    ),
    "{column} becomes NOT NULL": "{column} становится NOT NULL",
    "{column} becomes NOT NULL; a row without a time makes the conversion fail and roll back": (
        "{column} становится NOT NULL; строка без времени приведёт к ошибке и откату преобразования"
    ),
    "An index on {column} alone already exists, so TimescaleDB adds none": (
        "Индекс только по {column} уже есть, поэтому TimescaleDB не добавит новый"
    ),
    "TimescaleDB adds an index on {column}, newest first": (
        "TimescaleDB добавит индекс по {column}, сначала самые новые"
    ),
    "The table keeps its name and identity and becomes a hypertable; DataPlayer cannot turn it back into an ordinary table": (
        "Таблица сохранит имя и идентичность и станет гипертаблицей; DataPlayer не сможет снова сделать её "
        "обычной таблицей"
    ),
    "Locks this table exclusively for the conversion; its reads and writes wait until it commits": (
        "Монопольно блокирует таблицу на время преобразования; чтение и запись ждут фиксации"
    ),
    "Review the conversion plan before applying it": "Проверьте план преобразования, прежде чем применять его",
    "Converted to a hypertable; rows added from now on are stored in chunks": (
        "Преобразовано в гипертаблицу; добавляемые строки теперь хранятся в чанках"
    ),
    "Choose an existing ordinary table": "Выберите существующую обычную таблицу",
    "This table is already a hypertable": "Эта таблица уже гипертаблица",
    "Foreign keys between this table and a hypertable are not supported": (
        "Внешние ключи между этой таблицей и гипертаблицей не поддерживаются"
    ),
    "This table has no timestamp or date column to partition by": (
        "В этой таблице нет столбца типа timestamp или date для секционирования"
    ),
    "This table has no timestamp, date or integer column to partition by": (
        "В этой таблице нет столбца типа timestamp, date или целочисленного для секционирования"
    ),
    "This table is not empty; only empty tables are converted here": (
        "Эта таблица не пуста; здесь преобразуются только пустые таблицы"
    ),
    "This table has too many indexes to inspect": "У этой таблицы слишком много индексов для проверки",
    "The TimescaleDB conversion API is split across schemas": "API преобразования TimescaleDB разнесён по разным схемам",
    "TimescaleDB conversion planning timed out": "Время планирования преобразования TimescaleDB истекло",
    "Only the table's owner can convert it": "Преобразовать таблицу может только её владелец",
    "This connection may not read the table": "Этому подключению нельзя читать эту таблицу",
    "Partitioned tables cannot become hypertables": "Секционированные таблицы не могут стать гипертаблицами",
    "Choose an ordinary table": "Выберите обычную таблицу",
    "Tables with NO INHERIT constraints cannot become hypertables": (
        "Таблицы с ограничениями NO INHERIT не могут стать гипертаблицами"
    ),
    "Tables that use inheritance cannot become hypertables": (
        "Таблицы, использующие наследование, не могут стать гипертаблицами"
    ),
    "Only logged tables can become hypertables": "Гипертаблицами могут стать только журналируемые таблицы",
    "Tables with rules cannot become hypertables": "Таблицы с правилами не могут стать гипертаблицами",
    "Choose a column this table can be partitioned by: {choices}": (
        "Выберите столбец, по которому можно секционировать эту таблицу: {choices}"
    ),
    "Unique index \"{index}\" must include \"{column}\", which partitions the table": (
        "Уникальный индекс «{index}» должен включать «{column}» — столбец секционирования таблицы"
    ),
    "An integer or UUID column is converted from Hypertable settings": (
        "Таблица с целочисленным столбцом или столбцом UUID преобразуется в окне «Настройки гипертаблицы»"
    ),
    "Date columns require whole days or weeks": "Для столбцов типа date нужны целые дни или недели",
    # Compressing and decompressing chunks.
    "Compress chunks": "Сжать чанки",
    "Decompress chunks": "Распаковать чанки",
    "TimescaleDB chunk metadata could not be inspected safely": (
        "Не удалось безопасно прочитать метаданные чанков TimescaleDB"
    ),
    "TimescaleDB chunk metadata could not be read": "Не удалось прочитать метаданные чанков TimescaleDB",
    "TimescaleDB chunk planning timed out": "Время планирования операции с чанками TimescaleDB истекло",
    "Compress 1 chunk of {target} as a job": "Задача: сжать один чанк {target}",
    "Compress {count} chunks of {target} as a job": "Задача: сжать чанки {target} ({count})",
    "Decompress 1 chunk of {target} as a job": "Задача: распаковать один чанк {target}",
    "Decompress {count} chunks of {target} as a job": "Задача: распаковать чанки {target} ({count})",
    "Already compressed and left as they are: {count}": "Уже сжаты и оставлены как есть: {count}",
    "Already decompressed and left as they are: {count}": "Уже распакованы и оставлены как есть: {count}",
    "Compressed chunks stay readable; queries and writes touching a chunk may wait while it is rewritten": (
        "Сжатые чанки остаются доступными для чтения; запросы и запись в чанк могут ждать, пока он переписывается"
    ),
    "Decompressed chunks take more space; a compression policy may compress them again on its own schedule": (
        "Распакованные чанки занимают больше места; политика сжатия может снова сжать их по своему расписанию"
    ),
    "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted": (
        "Каждый чанк обрабатывается в своей транзакции; при отмене уже обработанные чанки сохраняются"
    ),
    "The hypertable could not be found; nothing was converted": "Гипертаблица не найдена; ничего не изменено",
    "Every whole chunk inside this window is already compressed": "Все целые чанки в этом окне уже сжаты",
    "No whole chunk inside this window is compressed": "В этом окне нет сжатых целых чанков",
    "No whole chunk lies inside this window": "В этом окне нет ни одного целого чанка",
    "More than {count} chunks lie inside this window; narrow it": "В этом окне больше {count} чанков; сузьте его",
    "This chunk is in use; nothing was converted": "Этот чанк используется; ничего не изменено",
    "The source cancelled converting this chunk after its fifteen minutes; it was rolled back": (
        "Источник прервал обработку этого чанка через пятнадцать минут; она откачена"
    ),
    "This connection may not convert this chunk": "Этому подключению нельзя обрабатывать этот чанк",
    "The connection was lost while this chunk was being converted; its outcome is unknown": (
        "Подключение прервалось во время обработки этого чанка; результат неизвестен"
    ),
    "The source could not be reached; nothing was converted": "Источник недоступен; ничего не изменено",
    "The hypertable could not be checked in time; nothing was converted": (
        "Не удалось вовремя проверить гипертаблицу; ничего не изменено"
    ),
    "The hypertable could not be checked safely; nothing was converted": (
        "Не удалось безопасно проверить гипертаблицу; ничего не изменено"
    ),
    "The hypertable or its TimescaleDB API changed after review; nothing was converted": (
        "Гипертаблица или её API TimescaleDB изменились после проверки; ничего не изменено"
    ),
    "This chunk is no longer part of the hypertable": "Этот чанк больше не входит в гипертаблицу",
    "The source could not be reached or prepared; nothing was converted": (
        "Источник недоступен или не удалось его подготовить; ничего не изменено"
    ),
    "The source refused to convert this chunk": "Источник отказался обрабатывать этот чанк",
    # Chunk maintenance.
    "Drop chunks": "Удалить чанки",
    "Drop these chunks and every row in them? This cannot be undone.": (
        "Удалить эти чанки и все строки в них? Это нельзя отменить."
    ),
    "Detach chunks": "Отсоединить чанки",
    "Merge chunks": "Объединить чанки",
    "Merge chunks, reads going on": "Объединить чанки, не прерывая чтение",
    "Move chunks to a tablespace": "Переместить чанки в табличное пространство",
    "Reorder chunks by an index": "Переупорядочить чанки по индексу",
    "Split a chunk": "Разделить чанк",
    "Attach a table as a chunk": "Присоединить таблицу как чанк",
    "Drop chunks…": "Удалить чанки…",
    "Move chunks to a tablespace…": "Переместить чанки в табличное пространство…",
    "Reorder chunks by an index…": "Переупорядочить чанки по индексу…",
    "Detach chunks…": "Отсоединить чанки…",
    "Merge chunks…": "Объединить чанки…",
    "Merge chunks, reads going on…": "Объединить чанки, не прерывая чтение…",
    "Tablespace": "Табличное пространство",
    "An existing tablespace this connection may create in": (
        "Существующее табличное пространство, в котором это подключение может создавать объекты"
    ),
    "Order rows by index": "Упорядочить строки по индексу",
    "Leave empty for the index on the time column": "Оставьте пустым, чтобы взять индекс по столбцу времени",
    "Index tablespace": "Табличное пространство индексов",
    "Leave empty to move the indexes with the chunk": "Оставьте пустым, чтобы переместить индексы вместе с чанком",
    "Index": "Индекс",
    "An index of this hypertable to order rows by": "Индекс этой гипертаблицы, по которому упорядочить строки",
    "Split at": "Разделить в точке",
    "With its time zone; the chunk holding this instant is split at it": (
        "С часовым поясом; чанк, содержащий этот момент, делится в нём"
    ),
    "Schema of the table": "Схема таблицы",
    "Table": "Таблица",
    "A table with the hypertable's columns, such as a detached chunk": (
        "Таблица со столбцами гипертаблицы, например отсоединённый чанк"
    ),
    "Covering from": "Охватывает с",
    "Until": "По",
    "Either a window or picked chunks, not both": "Укажите либо окно, либо выбранные чанки, но не то и другое",
    "Give where the window ends": "Укажите, где заканчивается окно",
    "With the chunk": "Вместе с чанком",
    "The index on the time column": "Индекс по столбцу времени",
    "A value of \"{column}\", the {type} column the hypertable is partitioned by": (
        "Значение «{column}» — столбца типа {type}, по которому секционирована гипертаблица"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; leave empty for every earlier chunk": (
        "Значение «{column}» — столбца типа {type}, по которому секционирована гипертаблица; оставьте пустым, "
        "чтобы взять все более ранние чанки"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; the chunk holding it is split at it": (
        "Значение «{column}» — столбца типа {type}, по которому секционирована гипертаблица; чанк, содержащий "
        "его, делится в этой точке"
    ),
    "Drop 1 chunk of {target} as a job": "Задача: удалить один чанк {target}",
    "Drop {count} chunks of {target} as a job": "Задача: удалить чанки {target} ({count})",
    "Move 1 chunk of {target} as a job": "Задача: переместить один чанк {target}",
    "Move {count} chunks of {target} as a job": "Задача: переместить чанки {target} ({count})",
    "Reorder 1 chunk of {target} as a job": "Задача: переупорядочить один чанк {target}",
    "Reorder {count} chunks of {target} as a job": "Задача: переупорядочить чанки {target} ({count})",
    "Detach 1 chunk of {target} as a job": "Задача: отсоединить один чанк {target}",
    "Detach {count} chunks of {target} as a job": "Задача: отсоединить чанки {target} ({count})",
    "Merge {count} chunks of {target} into one as a job": "Задача: объединить чанки {target} ({count}) в один",
    "Split {chunk} at {point} as a job": "Задача: разделить {chunk} в точке {point}",
    "Attach {table} to {target} as a chunk as a job": "Задача: присоединить {table} к {target} как чанк",
    "Exactly the chunks picked in the Chunks report, each read again by name": (
        "Ровно те чанки, что выбраны в отчёте «Чанки»; каждый перечитывается по имени"
    ),
    "Left as they are, already in {tablespace}: {count}": "Оставлены как есть, уже в {tablespace}: {count}",
    "Left as they are, compressed, which reorder_chunk does not rewrite: {count}": (
        "Оставлены как есть, сжатые — reorder_chunk их не переписывает: {count}"
    ),
    "Left as they are, compressed; TimescaleDB detaches only uncompressed chunks: {count}": (
        "Оставлены как есть, сжатые — TimescaleDB отсоединяет только несжатые чанки: {count}"
    ),
    "Left as they are: {count}": "Оставлены как есть: {count}",
    "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs": (
        "Все строки в этих чанках удаляются; каждый чанк удаляется по имени, а не по возрасту, прочитанному "
        "при запуске задачи"
    ),
    "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; Detached chunks lists it, and Attach chunk brings it back": (
        "Каждый чанк становится обычной таблицей со своим именем и выпадает из запросов к гипертаблице; "
        "он появится в отчёте «Отсоединённые чанки», а «Присоединить таблицу как чанк» вернёт его"
    ),
    "The chunks become one, covering their whole range; the table is locked while they merge": (
        "Чанки объединяются в один на весь их диапазон; таблица блокируется на время объединения"
    ),
    "The chunks become one, covering their whole range; reads go on meanwhile, writes to them wait": (
        "Чанки объединяются в один на весь их диапазон; чтение продолжается, запись в них ждёт"
    ),
    "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile": (
        "Каждый чанк копируется в табличное пространство, а старая копия удаляется; чтение и запись в него "
        "в это время ждут"
    ),
    "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile": (
        "Каждый чанк переписывается в порядке индекса, что ускоряет чтение по нему; чтение и запись в это "
        "время ждут"
    ),
    "The chunk becomes two, divided at this point; the table is locked while it splits": (
        "Чанк делится на два в этой точке; таблица блокируется на время разделения"
    ),
    "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit": (
        "Её строки попадут в запросы к гипертаблице; TimescaleDB отклонит таблицу, если её столбцы или строки "
        "не подходят"
    ),
    "The hypertable could not be found; nothing was changed": "Гипертаблица не найдена; ничего не изменено",
    "This hypertable is partitioned by the integer column \"{column}\"; give its values, not instants": (
        "Эта гипертаблица секционирована по целочисленному столбцу «{column}»; укажите его значения, "
        "а не моменты времени"
    ),
    "This hypertable is partitioned by time on \"{column}\"; give instants, not numbers": (
        "Эта гипертаблица секционирована по времени в столбце «{column}»; укажите моменты времени, а не числа"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not merged here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Чанки гипертаблицы, секционированной по хешу {columns}, здесь не объединяются: в какой секции чанк, "
        "не раскрывается, поэтому результат нельзя проверить заранее"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not attached here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Чанки гипертаблицы, секционированной по хешу {columns}, здесь не присоединяются: в какой секции чанк, "
        "не раскрывается, поэтому результат нельзя проверить заранее"
    ),
    "TimescaleDB splits no chunk of a hypertable partitioned by hash as well as by time": (
        "TimescaleDB не делит чанки гипертаблицы, секционированной и по хешу, и по времени"
    ),
    "Pick at least one chunk": "Выберите хотя бы один чанк",
    "Pick at most {count} chunks at a time": "За раз можно выбрать не больше {count} чанков",
    "\"{name}\" is not a chunk of this hypertable any more": "«{name}» больше не чанк этой гипертаблицы",
    "Tablespace \"{name}\" does not exist or this connection may not create in it": (
        "Табличного пространства «{name}» нет, или этому подключению нельзя создавать в нём объекты"
    ),
    "This hypertable has no index \"{index}\"": "У этой гипертаблицы нет индекса «{index}»",
    "Every whole chunk inside this window is already in {tablespace}": "Все целые чанки в этом окне уже в {tablespace}",
    "Every picked chunk is already in {tablespace}": "Все выбранные чанки уже в {tablespace}",
    "Every whole chunk inside this window is compressed, which reorder_chunk does not rewrite": (
        "Все целые чанки в этом окне сжаты, а reorder_chunk сжатые чанки не переписывает"
    ),
    "Every picked chunk is compressed, which reorder_chunk does not rewrite": (
        "Все выбранные чанки сжаты, а reorder_chunk сжатые чанки не переписывает"
    ),
    "Every whole chunk inside this window is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Все целые чанки в этом окне сжаты; TimescaleDB отсоединяет только несжатые чанки"
    ),
    "Every picked chunk is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Все выбранные чанки сжаты; TimescaleDB отсоединяет только несжатые чанки"
    ),
    "Name an index: moving a chunk rewrites it in an index's order": (
        "Укажите индекс: при перемещении чанк переписывается в порядке индекса"
    ),
    "A merge needs at least two chunks": "Для объединения нужно хотя бы два чанка",
    "Chunks \"{before}\" and \"{after}\" are not adjacent; choose chunks that touch": (
        "Чанки «{before}» и «{after}» не соседние; выберите примыкающие друг к другу чанки"
    ),
    "TimescaleDB {version} cannot merge compressed chunks; decompress them first": (
        "TimescaleDB {version} не умеет объединять сжатые чанки; сначала распакуйте их"
    ),
    "No chunk holds this point strictly inside its range": "Ни один чанк не содержит эту точку строго внутри диапазона",
    "There is no table \"{schema}\".\"{table}\"": "Таблицы «{schema}».«{table}» нет",
    "Only an ordinary table can become a chunk": "Чанком может стать только обычная таблица",
    "Only the table's owner can attach it": "Присоединить таблицу может только её владелец",
    "A hypertable cannot become a chunk": "Гипертаблица не может стать чанком",
    "This table is already a chunk": "Эта таблица уже чанк",
    "A table that uses inheritance cannot become a chunk": "Таблица, использующая наследование, не может стать чанком",
    "Chunk \"{name}\" already covers part of this range": "Чанк «{name}» уже охватывает часть этого диапазона",
    "The range is empty once read in the column's type": "В типе столбца этот диапазон оказывается пустым",
    "This chunk is in use; nothing was changed": "Этот чанк используется; ничего не изменено",
    "The source cancelled this unit after its fifteen minutes; it was rolled back": (
        "Источник прервал этот шаг через пятнадцать минут; он откачен"
    ),
    "This connection may not change this chunk": "Этому подключению нельзя менять этот чанк",
    "The connection was lost while this unit was running; its outcome is unknown": (
        "Подключение прервалось во время этого шага; результат неизвестен"
    ),
    "The hypertable could not be checked in time; nothing was changed": (
        "Не удалось вовремя проверить гипертаблицу; ничего не изменено"
    ),
    "The hypertable or its chunks changed after review; nothing was changed": (
        "Гипертаблица или её чанки изменились после проверки; ничего не изменено"
    ),
    "The hypertable could not be checked safely; nothing was changed": (
        "Не удалось безопасно проверить гипертаблицу; ничего не изменено"
    ),
    "The source could not be reached; nothing was changed": "Источник недоступен; ничего не изменено",
    "The table to attach is gone; nothing was changed": "Присоединяемой таблицы больше нет; ничего не изменено",
    "This chunk was compressed after review; it was left as it is": (
        "Этот чанк был сжат после проверки; он оставлен как есть"
    ),
    "These chunks changed after review; nothing was merged": "Эти чанки изменились после проверки; ничего не объединено",
    "The index to order rows by is gone; nothing was changed": (
        "Индекса, по которому упорядочивались строки, больше нет; ничего не изменено"
    ),
    "The source could not be reached or prepared; nothing was changed": (
        "Источник недоступен или не удалось его подготовить; ничего не изменено"
    ),
    "The source refused this unit; nothing was changed": "Источник отклонил этот шаг; ничего не изменено",
    "This is not offered over these rows": "Для этих строк это действие недоступно",
    "A chunk is named by its schema and its name": "Чанк задаётся схемой и именем",
    "The picked chunks belong to {count} hypertables; pick chunks of one": (
        "Выбранные чанки относятся к разным гипертаблицам ({count}); выберите чанки одной"
    ),
    "Some picked rows are not chunks any more; read the report again": (
        "Некоторые выбранные строки больше не чанки; прочитайте отчёт заново"
    ),
    # Chunk skipping.
    "Skip chunks by a column": "Пропускать чанки по столбцу",
    "Stop skipping chunks by a column": "Не пропускать чанки по столбцу",
    "Column": "Столбец",
    "An integer, date or timestamp column queries filter on": (
        "Целочисленный столбец или столбец типа date или timestamp, по которому фильтруют запросы"
    ),
    "The hypertable could not be inspected safely": "Не удалось безопасно проверить гипертаблицу",
    "TimescaleDB keeps ranges only of integer, date and timestamp columns, not of \"{column}\" ({type})": (
        "TimescaleDB хранит диапазоны только целочисленных столбцов и столбцов типов date и timestamp, "
        "а не «{column}» ({type})"
    ),
    "Planning chunk skipping timed out": "Время планирования пропуска чанков истекло",
    "Chunks record the range of {column} as they are compressed, and a query filtering on it skips the chunks outside": (
        "При сжатии чанки запоминают диапазон {column}, и запрос с фильтром по нему пропускает чанки вне диапазона"
    ),
    "Chunks stop recording the range of {column}, if they did": (
        "Чанки перестают запоминать диапазон {column}, если запоминали"
    ),
    "Changes nothing if it already holds: TimescaleDB keeps which columns record ranges where this application does not read": (
        "Ничего не меняет, если так уже есть: TimescaleDB хранит, какие столбцы запоминают диапазоны, там, "
        "где это приложение не читает"
    ),
    "timescaledb.enable_chunk_skipping is off for this connection; queries use the ranges only in sessions that turn it on": (
        "Для этого подключения timescaledb.enable_chunk_skipping выключен; запросы используют диапазоны только "
        "в сеансах, где он включён"
    ),
    "Skip chunks by {column} on {target}": "Пропускать чанки {target} по {column}",
    "Stop skipping chunks by {column} on {target}": "Не пропускать чанки {target} по {column}",
    "Review the chunk skipping plan before applying it": "Проверьте план пропуска чанков, прежде чем применять его",
    "Chunk skipping turned on": "Пропуск чанков включён",
    "Chunk skipping turned off": "Пропуск чанков выключен",
    # Hypertable settings: reading the hypertable.
    "Hypertable settings": "Настройки гипертаблицы",
    "Reading the hypertable timed out": "Время чтения гипертаблицы истекло",
    "Job {job} drops chunks {chunks}, every {every}": "Задача {job} удаляет чанки {chunks}, каждые {every}",
    "Job {job} drops chunks {chunks}, every {every}; paused": (
        "Задача {job} удаляет чанки {chunks}, каждые {every}; приостановлено"
    ),
    "Job {job} compresses chunks {chunks}, every {every}": "Задача {job} сжимает чанки {chunks}, каждые {every}",
    "Job {job} compresses chunks {chunks}, every {every}; paused": (
        "Задача {job} сжимает чанки {chunks}, каждые {every}; приостановлено"
    ),
    "Job {job} reorders chunks by {index}": "Задача {job} переупорядочивает чанки по {index}",
    "Job {job} reorders chunks by {index}; paused": "Задача {job} переупорядочивает чанки по {index}; приостановлено",
    "Job {job} reorders chunks by an index this editor cannot read": (
        "Задача {job} переупорядочивает чанки по индексу, который этот редактор не может прочитать"
    ),
    "Job {job} reorders chunks by an index this editor cannot read; paused": (
        "Задача {job} переупорядочивает чанки по индексу, который этот редактор не может прочитать; приостановлено"
    ),
    "The current sparse indexes could not be read": "Не удалось прочитать текущие разреженные индексы",
    "This hypertable has a sparse index of a kind this editor does not know; manage it with SQL": (
        "У этой гипертаблицы есть разреженный индекс неизвестного этому редактору вида; управляйте им через SQL"
    ),
    "The current columnstore settings could not be read": (
        "Не удалось прочитать текущие настройки колоночного хранилища"
    ),
    "This hypertable merges compressed chunks by a time interval; manage it with SQL": (
        "Эта гипертаблица объединяет сжатые чанки по интервалу времени; управляйте этим через SQL"
    ),
    "This hypertable has several compaction policy jobs; manage them with SQL": (
        "У этой гипертаблицы несколько задач политики уплотнения; управляйте ими через SQL"
    ),
    "This hypertable has several reorder policy jobs; manage them with SQL": (
        "У этой гипертаблицы несколько задач политики переупорядочивания; управляйте ими через SQL"
    ),
    "The existing reorder policy could not be read safely; manage it with SQL": (
        "Не удалось безопасно прочитать текущую политику переупорядочивания; управляйте ею через SQL"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; it is edited here from 2.25": (
        "TimescaleDB {version} секционирует по UUIDv7 лишь частично; здесь это редактируется начиная с 2.25"
    ),
    "Only timestamp, date, UUIDv7 and integer time dimensions are edited here": (
        "Здесь редактируются только временные измерения типов timestamp, date, UUIDv7 и целочисленные"
    ),
    "The current chunk interval could not be read": "Не удалось прочитать текущий интервал чанков",
    "Only hash dimensions beside the time dimension are edited here": (
        "Здесь редактируются только хеш-измерения в дополнение к временному"
    ),
    "The hypertable's chunks and tablespaces could not be read": (
        "Не удалось прочитать чанки и табличные пространства гипертаблицы"
    ),
    "This connection may not create functions in schema \"{schema}\"": (
        "Этому подключению нельзя создавать функции в схеме «{schema}»"
    ),
    "A function named \"{name}\" already exists; choose it from the list or another name": (
        "Функция «{name}» уже существует; выберите её из списка или другое имя"
    ),
    "A chunk interval of an integer column is a number of its values": (
        "Интервал чанков целочисленного столбца задаётся числом его значений"
    ),
    "A chunk interval of a {type} column is at most {count}": (
        "Интервал чанков столбца типа {type} — не больше {count}"
    ),
    "A chunk interval is counted in minutes, hours, days or weeks": (
        "Интервал чанков задаётся в минутах, часах, днях или неделях"
    ),
    # Hypertable settings: planning the change.
    "Locks this hypertable exclusively while it changes; its reads and writes wait until it commits": (
        "Монопольно блокирует гипертаблицу на время изменения; чтение и запись ждут фиксации"
    ),
    "Other changes to this hypertable's settings wait until it commits": (
        "Другие изменения настроек этой гипертаблицы ждут фиксации"
    ),
    "A chunk interval of this hypertable is counted in days or weeks": (
        "Интервал чанков этой гипертаблицы задаётся в днях или неделях"
    ),
    "A chunk interval of this hypertable is counted in minutes or hours or days or weeks": (
        "Интервал чанков этой гипертаблицы задаётся в минутах, часах, днях или неделях"
    ),
    "A chunk interval of this column is counted in days or weeks": (
        "Интервал чанков для этого столбца задаётся в днях или неделях"
    ),
    "A chunk interval of this column is counted in minutes or hours or days or weeks": (
        "Интервал чанков для этого столбца задаётся в минутах, часах, днях или неделях"
    ),
    "Column \"{column}\" has a type that cannot be used as a hash dimension": (
        "Тип столбца «{column}» не подходит для хеш-измерения"
    ),
    "Column \"{column}\" has a type that cannot be used as a minmax sparse index": (
        "Тип столбца «{column}» не подходит для разреженного индекса minmax"
    ),
    "Column \"{column}\" has a type that cannot be used as a segment column": (
        "Тип столбца «{column}» не подходит для сегментации"
    ),
    "Column \"{column}\" has a type that cannot be used as an order column": (
        "Тип столбца «{column}» не подходит для упорядочивания"
    ),
    "TimescaleDB cannot remove the hash dimension on \"{column}\"": (
        "TimescaleDB не умеет удалять хеш-измерение по «{column}»"
    ),
    "A hash dimension can only be added while the hypertable holds no chunks": (
        "Хеш-измерение можно добавить, только пока в гипертаблице нет чанков"
    ),
    "The time column cannot also be a hash dimension": "Столбец времени не может быть ещё и хеш-измерением",
    "Unique key \"{key}\" must include \"{column}\" before it can be a hash dimension": (
        "Чтобы «{column}» стал хеш-измерением, уникальный ключ «{key}» должен его включать"
    ),
    "TimescaleDB {version} has no sparse indexes; they arrived in 2.22": (
        "В TimescaleDB {version} нет разреженных индексов; они появились в 2.22"
    ),
    "Column \"{column}\" has the same sparse index twice": "У столбца «{column}» один и тот же разреженный индекс указан дважды",
    "Sparse indexes need the order to be named; choose the columns to order by": (
        "Для разреженных индексов нужен заданный порядок; выберите столбцы для упорядочивания"
    ),
    "Column \"{column}\" is listed more than once in the columnstore settings": (
        "Столбец «{column}» указан в настройках колоночного хранилища больше одного раза"
    ),
    "The columnstore cannot be turned off while chunks are compressed; decompress them first": (
        "Колоночное хранилище нельзя выключить, пока есть сжатые чанки; сначала распакуйте их"
    ),
    "TimescaleDB {version} cannot return a setting to its own choice; name the columns instead": (
        "TimescaleDB {version} не умеет возвращать настройку к собственному выбору; укажите столбцы"
    ),
    "Merging compressed chunks is set in time, which an integer column does not count in": (
        "Объединение сжатых чанков задаётся временем, а целочисленный столбец его не измеряет"
    ),
    "A merge interval is counted in the units of the chunk interval": (
        "Интервал объединения задаётся в единицах интервала чанков"
    ),
    "The merge interval must be a whole multiple of the chunk interval, larger than it": (
        "Интервал объединения должен быть кратен интервалу чанков и больше его"
    ),
    "There is no retention policy to keep": "Нет политики хранения, которую можно сохранить",
    "There is no compression policy to keep": "Нет политики сжатия, которую можно сохранить",
    "The retention policy of an integer column is a number of its values": (
        "Политика хранения для целочисленного столбца задаётся числом его значений"
    ),
    "The compression policy of an integer column is a number of its values": (
        "Политика сжатия для целочисленного столбца задаётся числом его значений"
    ),
    "The retention policy of a {type} column is at most {count}": (
        "Политика хранения для столбца типа {type} — не больше {count}"
    ),
    "The compression policy of a {type} column is at most {count}": (
        "Политика сжатия для столбца типа {type} — не больше {count}"
    ),
    "The retention policy of a {type} column cannot count in plain numbers": (
        "Политику хранения для столбца типа {type} нельзя задать простым числом"
    ),
    "The compression policy of a {type} column cannot count in plain numbers": (
        "Политику сжатия для столбца типа {type} нельзя задать простым числом"
    ),
    "The retention policy of a {type} column cannot count in seconds": (
        "Политику хранения для столбца типа {type} нельзя задать в секундах"
    ),
    "The compression policy of a {type} column cannot count in seconds": (
        "Политику сжатия для столбца типа {type} нельзя задать в секундах"
    ),
    "The retention policy of a {type} column cannot count in minutes": (
        "Политику хранения для столбца типа {type} нельзя задать в минутах"
    ),
    "The compression policy of a {type} column cannot count in minutes": (
        "Политику сжатия для столбца типа {type} нельзя задать в минутах"
    ),
    "The retention policy of a {type} column cannot count in hours": (
        "Политику хранения для столбца типа {type} нельзя задать в часах"
    ),
    "The compression policy of a {type} column cannot count in hours": (
        "Политику сжатия для столбца типа {type} нельзя задать в часах"
    ),
    "The existing reorder policy is paused; remove it before setting a new one": (
        "Текущая политика переупорядочивания приостановлена; удалите её, прежде чем задавать новую"
    ),
    "Only a hypertable partitioned by an integer column takes an integer_now function": (
        "Функцию integer_now принимает только гипертаблица, секционированная по целочисленному столбцу"
    ),
    "TimescaleDB cannot take an integer_now function away; keep it or choose another": (
        "TimescaleDB не умеет убирать функцию integer_now; оставьте её или выберите другую"
    ),
    "There is no integer_now function to keep": "Нет функции integer_now, которую можно сохранить",
    "{function} is not a function TimescaleDB accepts as integer_now of a {type} column": (
        "TimescaleDB не принимает {function} как integer_now для столбца типа {type}"
    ),
    "A {type} column cannot hold the seconds since 1970": "Столбец типа {type} не вмещает число секунд с 1970 года",
    "A {type} column cannot hold the milliseconds since 1970": (
        "Столбец типа {type} не вмещает число миллисекунд с 1970 года"
    ),
    "A {type} column cannot hold the microseconds since 1970": (
        "Столбец типа {type} не вмещает число микросекунд с 1970 года"
    ),
    "TimescaleDB {version} has no compaction policy; it arrived in 2.29": (
        "В TimescaleDB {version} нет политики уплотнения; она появилась в 2.29"
    ),
    "A compaction policy merges compressed chunks; turn the columnstore on": (
        "Политика уплотнения объединяет сжатые чанки; включите колоночное хранилище"
    ),
    "Remove the columnstore policy to turn the columnstore off": (
        "Чтобы выключить колоночное хранилище, удалите политику колоночного хранилища"
    ),
    "Remove the compaction policy to turn the columnstore off": (
        "Чтобы выключить колоночное хранилище, удалите политику уплотнения"
    ),
    "An age policy on an integer column needs an integer_now function to tell the current value": (
        "Политике по возрасту для целочисленного столбца нужна функция integer_now, сообщающая текущее значение"
    ),
    "Choose the time column the table is partitioned by": "Выберите столбец времени, по которому секционируется таблица",
    "Choose the chunk interval": "Выберите интервал чанков",
    "TimescaleDB cannot change the time column of a hypertable": "TimescaleDB не умеет менять столбец времени гипертаблицы",
    "Planning the hypertable change timed out": "Время планирования изменения гипертаблицы истекло",
    # Hypertable settings: the preview.
    "TimescaleDB's choice for each chunk": "по выбору TimescaleDB для каждого чанка",
    "TimescaleDB's choice": "по выбору TimescaleDB",
    "none": "нет",
    "segment by {columns}": "сегментация: {columns}",
    "order by {columns}": "порядок: {columns}",
    "sparse indexes {indexes}": "разреженные индексы: {indexes}",
    "{kind} on {column}": "{kind} по {column}",
    "no merging of chunks": "без объединения чанков",
    "merge chunks into {length} as they are compressed": "при сжатии объединять чанки до {length}",
    "Turn the columnstore on: {changes}": "Включить колоночное хранилище: {changes}",
    "Columnstore settings for chunks compressed from now on: {changes}": (
        "Настройки колоночного хранилища для чанков, сжатых с этого момента: {changes}"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, and move its rows into chunks": (
        "Преобразовать таблицу в гипертаблицу по {column} ({type}), чанки по {length}, и перенести её строки "
        "в чанки"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, while it is empty": (
        "Преобразовать таблицу в гипертаблицу по {column} ({type}), чанки по {length}, пока она пуста"
    ),
    "Remove the retention policy (job {job})": "Удалить политику хранения (задача {job})",
    "Remove the columnstore policy (job {job})": "Удалить политику колоночного хранилища (задача {job})",
    "Remove the reorder policy (job {job})": "Удалить политику переупорядочивания (задача {job})",
    "Remove the compaction policy (job {job})": "Удалить политику уплотнения (задача {job})",
    "Add a retention policy: drop chunks older than {length}": (
        "Добавить политику хранения: удалять чанки старше {length}"
    ),
    "Add a columnstore policy: compress chunks older than {length}": (
        "Добавить политику колоночного хранилища: сжимать чанки старше {length}"
    ),
    "Add a compaction policy: merge small compressed chunks on TimescaleDB's schedule": (
        "Добавить политику уплотнения: объединять небольшие сжатые чанки по расписанию TimescaleDB"
    ),
    "Add a reorder policy by index {index}": "Добавить политику переупорядочивания по индексу {index}",
    "New chunks cover {length}; existing chunks keep their range": (
        "Новые чанки охватывают {length}; существующие чанки сохраняют свой диапазон"
    ),
    "Hash {column} into {partitions} partitions for new chunks": (
        "Для новых чанков хешировать {column}, секций: {partitions}"
    ),
    "Add a hash dimension on {column} with {partitions} partitions": (
        "Добавить хеш-измерение по {column}, секций: {partitions}"
    ),
    "Turn the columnstore off": "Выключить колоночное хранилище",
    "Place new chunks in tablespace {tablespace} too": "Размещать новые чанки также в табличном пространстве {tablespace}",
    "Stop placing new chunks in tablespace {tablespace}": (
        "Перестать размещать новые чанки в табличном пространстве {tablespace}"
    ),
    "Create function {function} returning the seconds since 1970 as {type}": (
        "Создать функцию {function}, возвращающую число секунд с 1970 года как {type}"
    ),
    "Create function {function} returning the milliseconds since 1970 as {type}": (
        "Создать функцию {function}, возвращающую число миллисекунд с 1970 года как {type}"
    ),
    "Create function {function} returning the microseconds since 1970 as {type}": (
        "Создать функцию {function}, возвращающую число микросекунд с 1970 года как {type}"
    ),
    "Policies take the current value of the time column from {function}": (
        "Политики берут текущее значение столбца времени из {function}"
    ),
    "Moves about {count} rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Переносит строки в чанки (примерно {count}) задачей в разделе «Активность»; до её окончания таблица "
        "заблокирована для чтения и записи"
    ),
    "Moves an unknown number of rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Переносит строки в чанки (сколько — неизвестно) задачей в разделе «Активность»; до её окончания таблица "
        "заблокирована для чтения и записи"
    ),
    "Rolled back whole if it fails, is cancelled or runs past {seconds} seconds; nothing is left half converted": (
        "Откатывается целиком при ошибке, отмене или если не уложится в {seconds} с; наполовину преобразованным "
        "ничего не останется"
    ),
    "DataPlayer cannot turn a hypertable back into an ordinary table": (
        "DataPlayer не может снова сделать гипертаблицу обычной таблицей"
    ),
    "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, after this session ends": (
        "TimescaleDB будет удалять целые чанки старше срока хранения по своему расписанию и после завершения сеанса"
    ),
    "{target} already matches these settings": "{target} уже соответствует этим настройкам",
    "Change {target}": "Изменить {target}",
    "Review the hypertable plan before applying it": "Проверьте план изменения гипертаблицы, прежде чем применять его",
    "Moving rows into chunks runs as a job; start it from the plan": (
        "Перенос строк в чанки выполняется задачей; запустите её из плана"
    ),
    "Converted to a hypertable": "Преобразовано в гипертаблицу",
    "Hypertable changed: 1 change applied": "Гипертаблица изменена: применено одно изменение",
    "Hypertable changed: {count} changes applied": "Гипертаблица изменена, применено изменений: {count}",
    "This change is applied at once rather than as a job": "Это изменение применяется сразу, а не задачей",
    "The table could not be found; nothing was converted": "Таблица не найдена; ничего не преобразовано",
    "The table was renamed after review; nothing was converted": (
        "Таблица переименована после проверки; ничего не преобразовано"
    ),
    # A table designed as a hypertable.
    "Hypertable": "Гипертаблица",
    "Columnstore": "Колоночное хранилище",
    "Retention policy": "Политика хранения",
    "Columnstore policy": "Политика колоночного хранилища",
    "Compaction policy": "Политика уплотнения",
    "Reorder policy": "Политика переупорядочивания",
    "Integer now": "Integer now",
    "Function {name}": "Функция {name}",
    "Hash dimension {column}": "Хеш-измерение {column}",
    "The segment list names a column that is not there": "В списке сегментации указан несуществующий столбец",
    "The order list names a column that is not there": "В списке порядка указан несуществующий столбец",
    "The sparse index names a column that is not there": "В разреженном индексе указан несуществующий столбец",
    "The time dimension names a column that is not there": "Во временном измерении указан несуществующий столбец",
    "The hash dimension names a column that is not there": "В хеш-измерении указан несуществующий столбец",
    "Choose the columns to segment by": "Выберите столбцы для сегментации",
    "Choose the columns to order by": "Выберите столбцы для упорядочивания",
    "Choose the columns of the sparse indexes": "Выберите столбцы разреженных индексов",
    "The reorder policy names an index that is not there": "В политике переупорядочивания указан несуществующий индекс",
    "The TimescaleDB API is split across schemas": "API TimescaleDB разнесён по разным схемам",
    "This setting cannot be made while the table is created": "Эту настройку нельзя задать при создании таблицы",
    "\"{column}\" cannot partition a hypertable; choose a timestamp or date column": (
        "По «{column}» нельзя секционировать гипертаблицу; выберите столбец типа timestamp или date"
    ),
    "\"{column}\" partitions the hypertable, so it must have a value": (
        "По «{column}» секционируется гипертаблица, поэтому у него должно быть значение"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; choose a timestamp column": (
        "TimescaleDB {version} секционирует по UUIDv7 лишь частично; выберите столбец типа timestamp"
    ),
}
