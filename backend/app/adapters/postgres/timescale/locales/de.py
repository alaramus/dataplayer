"""Was die TimescaleDB-Aktionen und -Berichte schreiben, auf Deutsch (D226).

Begriffe folgen dem Glossar der Oberflächen; TimescaleDBs eigene Funktions- und
Optionsnamen bleiben unverändert.
"""

MESSAGES: dict[str, str] = {
    # Längen, wie eine Vorschau sie zeigt.
    "{amount} second": "{amount} Sekunde",
    "{amount} seconds": "{amount} Sekunden",
    "{amount} minute": "{amount} Minute",
    "{amount} minutes": "{amount} Minuten",
    "{amount} hour": "{amount} Stunde",
    "{amount} hours": "{amount} Stunden",
    "{amount} day": "{amount} Tag",
    "{amount} days": "{amount} Tage",
    "{amount} week": "{amount} Woche",
    "{amount} weeks": "{amount} Wochen",
    "{amount} month": "{amount} Monat",
    "{amount} months": "{amount} Monate",
    "{amount} year": "{amount} Jahr",
    "{amount} years": "{amount} Jahre",
    "{amount} value": "{amount} Wert",
    "{amount} values": "{amount} Werte",
    # Berichte.
    "Hypertables": "Hypertables",
    "Hypertable owners, dimension/chunk counts and compression configuration": (
        "Eigentümer der Hypertables, Anzahl der Dimensionen und Chunks, "
        "Komprimierungseinstellungen"
    ),
    "Continuous aggregates": "Kontinuierliche Aggregate",
    "Aggregate owners, source/materialization identities and configuration": (
        "Eigentümer der Aggregate, Identität von Quelle und Materialisierung, Konfiguration"
    ),
    "Chunks": "Chunks",
    "Chunk identities, primary-dimension boundaries and compression status": (
        "Chunk-Identitäten, Grenzen der primären Dimension und Komprimierungsstatus"
    ),
    "Dimensions": "Dimensionen",
    "Time, integer and space dimensions of each hypertable": (
        "Zeitliche, ganzzahlige und räumliche Dimensionen jeder Hypertable"
    ),
    "Policies and jobs": "Richtlinien und Jobs",
    "Native TimescaleDB jobs, including policies and their schedules": (
        "Native TimescaleDB-Jobs, einschließlich Richtlinien und ihrer Zeitpläne"
    ),
    "Job statistics": "Job-Statistiken",
    "Recorded native job runs, outcomes and counters; unrun jobs may be absent": (
        "Aufgezeichnete native Job-Läufe, Ergebnisse und Zähler; nie gelaufene Jobs können fehlen"
    ),
    "Detached chunks": "Abgetrennte Chunks",
    "Tables named like a chunk that no hypertable holds; Attach chunk takes one back": (
        "Tabellen, die wie ein Chunk heißen, zu keiner Hypertable gehören; "
        "„Tabelle als Chunk anhängen“ holt eine zurück"
    ),
    "This report cannot be inspected by this connection": "Diese Verbindung kann diesen Bericht nicht einsehen",
    "The installed TimescaleDB lacks the public API for this view": (
        "Dem installierten TimescaleDB fehlt die öffentliche API für diese Ansicht"
    ),
    # TimescaleDB erkennen.
    "TimescaleDB is not installed on this database": "TimescaleDB ist in dieser Datenbank nicht installiert",
    "This source has no usable TimescaleDB API": "Diese Quelle hat keine nutzbare TimescaleDB-API",
    "This connection may not inspect installed extensions": (
        "Diese Verbindung darf installierte Erweiterungen nicht einsehen"
    ),
    "Installed extensions could not be inspected": "Installierte Erweiterungen konnten nicht gelesen werden",
    "The installed TimescaleDB version could not be read": "Die installierte TimescaleDB-Version konnte nicht gelesen werden",
    "TimescaleDB extension metadata could not be read": "Die Metadaten der TimescaleDB-Erweiterung konnten nicht gelesen werden",
    "This TimescaleDB major version is not supported": "Diese TimescaleDB-Hauptversion wird nicht unterstützt",
    "This connection may not inspect TimescaleDB metadata": "Diese Verbindung darf die TimescaleDB-Metadaten nicht einsehen",
    "TimescaleDB metadata could not be inspected": "Die TimescaleDB-Metadaten konnten nicht gelesen werden",
    "The installed version lacks the supported inspection API": (
        "Der installierten Version fehlt die unterstützte Lese-API"
    ),
    "TimescaleDB action vocabulary could not be inspected": "Es konnte nicht ermittelt werden, welche TimescaleDB-Aktionen verfügbar sind",
    "The TimescaleDB {routine} API is not usable by this connection": (
        "Die TimescaleDB-API {routine} ist für diese Verbindung nicht nutzbar"
    ),
    "The TimescaleDB {type} type is not usable by this connection": (
        "Der TimescaleDB-Typ {type} ist für diese Verbindung nicht nutzbar"
    ),
    "This connection may not lock TimescaleDB public metadata": (
        "Diese Verbindung darf die öffentlichen TimescaleDB-Metadaten nicht sperren"
    ),
    # Die TimescaleDB-Fakten einer Relation.
    "TimescaleDB metadata no longer identifies this relation uniquely": (
        "Die TimescaleDB-Metadaten identifizieren diese Relation nicht mehr eindeutig"
    ),
    "TimescaleDB metadata inspection timed out": "Zeitüberschreitung beim Lesen der TimescaleDB-Metadaten",
    "TimescaleDB metadata could not be inspected safely": "Die TimescaleDB-Metadaten konnten nicht sicher gelesen werden",
    "TimescaleDB size inspection timed out": "Zeitüberschreitung bei der Größenbestimmung in TimescaleDB",
    "TimescaleDB compression inspection timed out": "Zeitüberschreitung beim Lesen der TimescaleDB-Komprimierungsstatistik",
    "TimescaleDB size could not be inspected safely": "Die Größe in TimescaleDB konnte nicht sicher bestimmt werden",
    "TimescaleDB compression statistics could not be inspected safely": (
        "Die TimescaleDB-Komprimierungsstatistik konnte nicht sicher gelesen werden"
    ),
    # Welche Tabellen eine Aktion erfasst.
    "Choose one user hypertable": "Wählen Sie eine Benutzer-Hypertable",
    "Choose one user continuous aggregate": "Wählen Sie ein benutzerdefiniertes kontinuierliches Aggregat",
    "Choose an owned hypertable": "Wählen Sie eine Hypertable, deren Eigentümer Sie sind",
    "Choose an owned hypertable with one time dimension": (
        "Wählen Sie eine Hypertable mit einer Zeitdimension, deren Eigentümer Sie sind"
    ),
    "Choose an owned hypertable partitioned by time": (
        "Wählen Sie eine nach Zeit partitionierte Hypertable, deren Eigentümer Sie sind"
    ),
    "Choose an owned continuous aggregate": "Wählen Sie ein kontinuierliches Aggregat, dessen Eigentümer Sie sind",
    "Only timestamp and date dimensions are supported here": "Hier werden nur Dimensionen vom Typ timestamp und date unterstützt",
    "Only a hypertable with one range dimension is maintained here": (
        "Hier werden nur Hypertables mit einer Bereichsdimension gepflegt"
    ),
    "Only timestamp, date and integer dimensions are supported here": (
        "Hier werden nur Dimensionen vom Typ timestamp, date und ganzzahlige unterstützt"
    ),
    "Only aggregates over timestamp and date dimensions are supported here": (
        "Hier werden nur Aggregate über Dimensionen vom Typ timestamp und date unterstützt"
    ),
    # Einen Plan prüfen und anwenden.
    "The operation plan changed; review it again": "Der Operationsplan hat sich geändert; prüfen Sie ihn erneut",
    "Validation timed out; review the plan again": "Zeitüberschreitung bei der Prüfung; prüfen Sie den Plan erneut",
    "The source changed or is busy; review the plan again": "Die Quelle hat sich geändert oder ist beschäftigt; prüfen Sie den Plan erneut",
    "The change could not be confirmed; reload the source before reviewing again": (
        "Die Änderung konnte nicht bestätigt werden; laden Sie die Quelle neu, bevor Sie erneut prüfen"
    ),
    "The change ran past its {seconds} seconds and was rolled back": (
        "Die Änderung überschritt ihre {seconds} Sekunden und wurde zurückgerollt"
    ),
    "This connection may not make this change or lock its metadata": (
        "Diese Verbindung darf diese Änderung nicht vornehmen oder ihre Metadaten sperren"
    ),
    "The source refused the change": "Die Quelle hat die Änderung abgelehnt",
    "Runs in Activity, one such job per connection at a time; access is checked again before every chunk": (
        "Läuft in Aktivität, ein solcher Job je Verbindung gleichzeitig; der Zugriff wird vor jedem Chunk "
        "erneut geprüft"
    ),
    "Runs in Activity, one such job per connection at a time; access is checked again before every unit": (
        "Läuft in Aktivität, ein solcher Job je Verbindung gleichzeitig; der Zugriff wird vor jeder Einheit "
        "erneut geprüft"
    ),
    # Gemeinsame Zeilen einer Vorschau.
    "Time dimension: {column}": "Zeitdimension: {column}",
    "Unit": "Einheit",
    "{chunk}: {start} to {end}": "{chunk}: {start} bis {end}",
    "…and {count} more": "…und {count} weitere",
    "Whole chunks from the earliest chunk to {end}": "Ganze Chunks vom frühesten Chunk bis {end}",
    "Whole chunks from {start} to {end}": "Ganze Chunks von {start} bis {end}",
    "Give an instant with its time zone, such as 2026-01-15T00:00:00Z, or a whole number": (
        "Geben Sie einen Zeitpunkt mit Zeitzone an, etwa 2026-01-15T00:00:00Z, oder eine ganze Zahl"
    ),
    "The number is outside the range of a bigint": "Die Zahl liegt außerhalb des Bereichs eines bigint",
    "Both ends are instants, or both are numbers": "Beide Grenzen sind Zeitpunkte oder beide sind Zahlen",
    "The range must start before it ends": "Der Bereich muss vor seinem Ende beginnen",
    "The window must start before it ends": "Das Fenster muss vor seinem Ende beginnen",
    "Chunks ending at or before": "Chunks mit Ende spätestens am",
    "With its time zone; only chunks lying entirely inside the window are chosen": (
        "Mit Zeitzone; es werden nur Chunks gewählt, die vollständig im Fenster liegen"
    ),
    "and starting at or after": "und Beginn frühestens am",
    "Leave empty for every earlier chunk": "Leer lassen für alle früheren Chunks",
    # Chunk-Intervall.
    "Change chunk interval": "Chunk-Intervall ändern",
    "Review the interval plan before applying it": "Prüfen Sie den Intervallplan, bevor Sie ihn anwenden",
    "Future chunk interval changed; existing chunks were not repartitioned": (
        "Das Intervall künftiger Chunks wurde geändert; bestehende Chunks wurden nicht neu partitioniert"
    ),
    "Change the future chunk interval for {target}": "Das Intervall künftiger Chunks für {target} ändern",
    "Current interval: {interval}": "Aktuelles Intervall: {interval}",
    "Requested interval: {interval}": "Angefordertes Intervall: {interval}",
    "Only future chunks use the new interval; existing chunks are not repartitioned": (
        "Nur künftige Chunks verwenden das neue Intervall; bestehende Chunks werden nicht neu partitioniert"
    ),
    "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait": (
        "Sperrt die TimescaleDB-Metadaten dieser Datenbank kurzzeitig; die Erstellung neuer Chunks kann warten"
    ),
    "TimescaleDB interval metadata could not be inspected safely": (
        "Die TimescaleDB-Intervallmetadaten konnten nicht sicher gelesen werden"
    ),
    "TimescaleDB interval planning timed out": "Zeitüberschreitung bei der Planung des TimescaleDB-Intervalls",
    "Calendar chunk intervals are not supported by this strategy": (
        "Kalendarische Chunk-Intervalle werden von dieser Strategie nicht unterstützt"
    ),
    "Date dimensions require whole days or weeks": "date-Dimensionen erfordern ganze Tage oder Wochen",
    "Interval validation timed out; review the plan again": "Zeitüberschreitung bei der Intervallprüfung; prüfen Sie den Plan erneut",
    "This connection may not change the interval or lock its metadata": (
        "Diese Verbindung darf das Intervall nicht ändern oder seine Metadaten sperren"
    ),
    "The source refused the interval change": "Die Quelle hat die Intervalländerung abgelehnt",
    "The interval change could not be confirmed; reload the source before reviewing again": (
        "Die Intervalländerung konnte nicht bestätigt werden; laden Sie die Quelle neu, bevor Sie erneut prüfen"
    ),
    # Aufbewahrungs- und Komprimierungsrichtlinien.
    "Set retention policy": "Aufbewahrungsrichtlinie festlegen",
    "Remove retention policy": "Aufbewahrungsrichtlinie entfernen",
    "Set compression policy": "Komprimierungsrichtlinie festlegen",
    "Remove compression policy": "Komprimierungsrichtlinie entfernen",
    "TimescaleDB will keep dropping old chunks by itself, even after this session ends. Set this policy?": (
        "TimescaleDB wird weiterhin von selbst alte Chunks löschen, auch nachdem diese Sitzung endet. "
        "Diese Richtlinie festlegen?"
    ),
    "Drop chunks older than": "Chunks löschen, die älter sind als",
    "Compress chunks older than": "Chunks komprimieren, die älter sind als",
    "Set the retention policy for {target}": "Die Aufbewahrungsrichtlinie für {target} festlegen",
    "Remove the retention policy from {target}": "Die Aufbewahrungsrichtlinie von {target} entfernen",
    "Set the compression policy for {target}": "Die Komprimierungsrichtlinie für {target} festlegen",
    "Remove the compression policy from {target}": "Die Komprimierungsrichtlinie von {target} entfernen",
    "No retention policy exists yet": "Es gibt noch keine Aufbewahrungsrichtlinie",
    "No compression policy exists yet": "Es gibt noch keine Komprimierungsrichtlinie",
    "older than {age}": "älter als {age}",
    "created more than {age} ago": "vor mehr als {age} erstellt",
    "Removes job {job}, which drops chunks {chunks}": "Entfernt Job {job}, der Chunks {chunks} löscht",
    "Replaces job {job}, which drops chunks {chunks}": "Ersetzt Job {job}, der Chunks {chunks} löscht",
    "Removes job {job}, which compresses chunks {chunks}": "Entfernt Job {job}, der Chunks {chunks} komprimiert",
    "Replaces job {job}, which compresses chunks {chunks}": "Ersetzt Job {job}, der Chunks {chunks} komprimiert",
    "The current policy runs every {every}; its replacement uses TimescaleDB's default schedule": (
        "Die aktuelle Richtlinie läuft alle {every}; ihr Ersatz verwendet den TimescaleDB-Standardzeitplan"
    ),
    "New policy: drop chunks older than {age}": "Neue Richtlinie: Chunks löschen, die älter sind als {age}",
    "New policy: compress chunks older than {age}": "Neue Richtlinie: Chunks komprimieren, die älter sind als {age}",
    "TimescaleDB keeps dropping whole chunks older than this on its own schedule, after this session ends": (
        "TimescaleDB löscht weiterhin ganze Chunks, die älter sind als dieser Wert, nach seinem eigenen "
        "Zeitplan, auch nachdem diese Sitzung endet"
    ),
    "TimescaleDB stops dropping old chunks automatically; chunks already dropped do not return": (
        "TimescaleDB hört auf, alte Chunks automatisch zu löschen; bereits gelöschte Chunks kehren nicht zurück"
    ),
    "TimescaleDB keeps compressing chunks older than this on its own schedule; compressed chunks stay readable": (
        "TimescaleDB komprimiert weiterhin Chunks, die älter sind als dieser Wert, nach seinem eigenen "
        "Zeitplan; komprimierte Chunks bleiben lesbar"
    ),
    "TimescaleDB stops compressing chunks automatically; chunks already compressed stay compressed": (
        "TimescaleDB hört auf, Chunks automatisch zu komprimieren; bereits komprimierte Chunks bleiben komprimiert"
    ),
    "Other policy changes made here in this database wait until it commits, and so may a policy run starting meanwhile": (
        "Andere hier in dieser Datenbank vorgenommene Richtlinienänderungen warten auf den Commit, und ebenso "
        "kann ein zwischenzeitlich startender Richtlinienlauf warten"
    ),
    "Review the retention policy plan before applying it": (
        "Prüfen Sie den Plan der Aufbewahrungsrichtlinie, bevor Sie ihn anwenden"
    ),
    "Review the compression policy plan before applying it": (
        "Prüfen Sie den Plan der Komprimierungsrichtlinie, bevor Sie ihn anwenden"
    ),
    "Retention policy set: TimescaleDB drops chunks older than {age} on its own schedule": (
        "Aufbewahrungsrichtlinie festgelegt: TimescaleDB löscht Chunks älter als {age} nach seinem eigenen Zeitplan"
    ),
    "Retention policy removed; TimescaleDB no longer drops old chunks automatically": (
        "Aufbewahrungsrichtlinie entfernt; TimescaleDB löscht alte Chunks nicht mehr automatisch"
    ),
    "Compression policy set: TimescaleDB compresses chunks older than {age} on its own schedule": (
        "Komprimierungsrichtlinie festgelegt: TimescaleDB komprimiert Chunks älter als {age} nach seinem eigenen Zeitplan"
    ),
    "Compression policy removed; TimescaleDB no longer compresses chunks automatically": (
        "Komprimierungsrichtlinie entfernt; TimescaleDB komprimiert Chunks nicht mehr automatisch"
    ),
    "This hypertable has several retention policy jobs; manage them with SQL": (
        "Diese Hypertable hat mehrere Jobs für Aufbewahrungsrichtlinien; verwalten Sie sie mit SQL"
    ),
    "This hypertable has several compression policy jobs; manage them with SQL": (
        "Diese Hypertable hat mehrere Jobs für Komprimierungsrichtlinien; verwalten Sie sie mit SQL"
    ),
    "The existing retention policy could not be read safely; manage it with SQL": (
        "Die bestehende Aufbewahrungsrichtlinie konnte nicht sicher gelesen werden; verwalten Sie sie mit SQL"
    ),
    "The existing compression policy could not be read safely; manage it with SQL": (
        "Die bestehende Komprimierungsrichtlinie konnte nicht sicher gelesen werden; verwalten Sie sie mit SQL"
    ),
    "TimescaleDB retention policy planning timed out": "Zeitüberschreitung bei der Planung der TimescaleDB-Aufbewahrungsrichtlinie",
    "TimescaleDB compression policy planning timed out": "Zeitüberschreitung bei der Planung der TimescaleDB-Komprimierungsrichtlinie",
    "TimescaleDB retention policy metadata could not be inspected safely": (
        "Die Metadaten der TimescaleDB-Aufbewahrungsrichtlinie konnten nicht sicher gelesen werden"
    ),
    "TimescaleDB compression policy metadata could not be inspected safely": (
        "Die Metadaten der TimescaleDB-Komprimierungsrichtlinie konnten nicht sicher gelesen werden"
    ),
    "Enable compression on this hypertable first": "Aktivieren Sie zuerst die Komprimierung für diese Hypertable",
    "This hypertable has no retention policy": "Diese Hypertable hat keine Aufbewahrungsrichtlinie",
    "This hypertable has no compression policy": "Diese Hypertable hat keine Komprimierungsrichtlinie",
    "Date dimensions require whole days, weeks, months or years": (
        "date-Dimensionen erfordern ganze Tage, Wochen, Monate oder Jahre"
    ),
    "The existing retention policy is paused; remove it before setting a new one": (
        "Die bestehende Aufbewahrungsrichtlinie ist pausiert; entfernen Sie sie, bevor Sie eine neue festlegen"
    ),
    "The existing compression policy is paused; remove it before setting a new one": (
        "Die bestehende Komprimierungsrichtlinie ist pausiert; entfernen Sie sie, bevor Sie eine neue festlegen"
    ),
    # Aktualisierungsrichtlinien kontinuierlicher Aggregate.
    "Set refresh policy": "Aktualisierungsrichtlinie festlegen",
    "Remove refresh policy": "Aktualisierungsrichtlinie entfernen",
    "Window starts": "Fensterbeginn",
    "How long ago the refreshed window begins": "Wie lange der Beginn des aktualisierten Fensters zurückliegt",
    "Window ends": "Fensterende",
    "How long ago it ends; more recent than the start": "Wie lange es zurückliegt, dass es endet; näher an der Gegenwart als der Beginn",
    "Refresh every": "Aktualisieren alle",
    "Set the refresh policy for {target}": "Die Aktualisierungsrichtlinie für {target} festlegen",
    "Remove the refresh policy from {target}": "Die Aktualisierungsrichtlinie von {target} entfernen",
    "Source hypertable: {source}": "Quell-Hypertable: {source}",
    "No refresh policy exists yet": "Es gibt noch keine Aktualisierungsrichtlinie",
    "from the earliest data to the latest data": "von den frühesten Daten bis zu den neuesten Daten",
    "from the earliest data to {end} ago": "von den frühesten Daten bis vor {end}",
    "from {start} ago to the latest data": "von vor {start} bis zu den neuesten Daten",
    "from {start} ago to {end} ago": "von vor {start} bis vor {end}",
    "Removes job {job}, which refreshes {window} every {every}": (
        "Entfernt Job {job}, der {window} alle {every} aktualisiert"
    ),
    "Replaces job {job}, which refreshes {window} every {every}": (
        "Ersetzt Job {job}, der {window} alle {every} aktualisiert"
    ),
    "New policy: refresh from {start} ago to {end} ago, every {every}": (
        "Neue Richtlinie: von vor {start} bis vor {end} alle {every} aktualisieren"
    ),
    "The source hypertable has no retention policy": "Die Quell-Hypertable hat keine Aufbewahrungsrichtlinie",
    "The source drops chunks older than {age}; the window starts after that": (
        "Die Quelle löscht Chunks älter als {age}; das Fenster beginnt danach"
    ),
    "The source drops chunks {chunks}; check that it keeps the raw data this window refreshes": (
        "Die Quelle löscht Chunks {chunks}; prüfen Sie, dass sie die Rohdaten behält, die dieses Fenster aktualisiert"
    ),
    "TimescaleDB stops refreshing this aggregate automatically; its materialized rows stay as they are": (
        "TimescaleDB hört auf, dieses Aggregat automatisch zu aktualisieren; seine materialisierten Zeilen "
        "bleiben, wie sie sind"
    ),
    "TimescaleDB keeps refreshing this window on its own schedule, after this session ends": (
        "TimescaleDB aktualisiert dieses Fenster weiterhin nach seinem eigenen Zeitplan, auch nachdem diese "
        "Sitzung endet"
    ),
    "This continuous aggregate has no refresh policy": "Dieses kontinuierliche Aggregat hat keine Aktualisierungsrichtlinie",
    "Review the refresh policy plan before applying it": "Prüfen Sie den Plan der Aktualisierungsrichtlinie, bevor Sie ihn anwenden",
    "Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule": (
        "Aktualisierungsrichtlinie festgelegt: TimescaleDB aktualisiert dieses Aggregat nach seinem eigenen Zeitplan"
    ),
    "Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically": (
        "Aktualisierungsrichtlinie entfernt; TimescaleDB aktualisiert dieses Aggregat nicht mehr automatisch"
    ),
    "The existing refresh policy is paused; remove it before setting a new one": (
        "Die bestehende Aktualisierungsrichtlinie ist pausiert; entfernen Sie sie, bevor Sie eine neue festlegen"
    ),
    "TimescaleDB refresh policy planning timed out": "Zeitüberschreitung bei der Planung der TimescaleDB-Aktualisierungsrichtlinie",
    "TimescaleDB refresh policy metadata could not be inspected safely": (
        "Die Metadaten der TimescaleDB-Aktualisierungsrichtlinie konnten nicht sicher gelesen werden"
    ),
    "This continuous aggregate has several refresh policy jobs; manage them with SQL": (
        "Dieses kontinuierliche Aggregat hat mehrere Jobs für Aktualisierungsrichtlinien; verwalten Sie sie mit SQL"
    ),
    "The existing refresh policy could not be read safely; manage it with SQL": (
        "Die bestehende Aktualisierungsrichtlinie konnte nicht sicher gelesen werden; verwalten Sie sie mit SQL"
    ),
    "Date dimensions require offsets in whole days, weeks, months or years": (
        "date-Dimensionen erfordern Versätze in ganzen Tagen, Wochen, Monaten oder Jahren"
    ),
    "The window must start further back than it ends": "Der Fensterbeginn muss weiter in der Vergangenheit liegen als sein Ende",
    "The window reaches data the source's retention policy drops (older than {age}); refreshing there would remove aggregated rows": (
        "Das Fenster erreicht Daten, die die Aufbewahrungsrichtlinie der Quelle löscht (älter als {age}); "
        "eine Aktualisierung dort würde aggregierte Zeilen entfernen"
    ),
    # Komprimierungseinstellungen.
    "Configure compression": "Komprimierung konfigurieren",
    "Segment by": "segmentby",
    "One column per line; leave empty for none": "Eine Spalte pro Zeile; leer lassen für keine",
    "Order by": "orderby",
    "One column per line, optionally followed by ASC or DESC and NULLS FIRST or NULLS LAST; the time column is added descending when neither list names it": (
        "Eine Spalte pro Zeile, optional gefolgt von ASC oder DESC und NULLS FIRST oder NULLS LAST; die "
        "Zeitspalte wird absteigend hinzugefügt, wenn keine der Listen sie nennt"
    ),
    "TimescaleDB compression settings could not be inspected safely": (
        "Die TimescaleDB-Komprimierungseinstellungen konnten nicht sicher gelesen werden"
    ),
    "Change the compression settings of {target}": "Die Komprimierungseinstellungen von {target} ändern",
    "Enable compression on {target}": "Komprimierung für {target} aktivieren",
    "Current segment by: {columns}": "Aktuelles segmentby: {columns}",
    "Current segment by: none": "Aktuelles segmentby: keines",
    "Current order by: {columns}": "Aktuelles orderby: {columns}",
    "Current order by: none": "Aktuelles orderby: keines",
    "Compression is not enabled yet": "Die Komprimierung ist noch nicht aktiviert",
    "New segment by: {columns}": "Neues segmentby: {columns}",
    "New segment by: none": "Neues segmentby: keines",
    "New order by: {columns}": "Neues orderby: {columns}",
    "Already compressed chunks keep the settings they were compressed with": (
        "Bereits komprimierte Chunks behalten die Einstellungen, mit denen sie komprimiert wurden"
    ),
    "TimescaleDB recommends segmenting or ordering by the unique column {column}": (
        "TimescaleDB empfiehlt, nach der eindeutigen Spalte {column} zu segmentieren oder zu sortieren"
    ),
    "Review the compression settings plan before applying it": (
        "Prüfen Sie den Plan der Komprimierungseinstellungen, bevor Sie ihn anwenden"
    ),
    "Compression settings changed; only chunks compressed from now on use them": (
        "Komprimierungseinstellungen geändert; nur ab jetzt komprimierte Chunks verwenden sie"
    ),
    "Compression enabled; chunks are compressed by a compression policy or on request": (
        "Komprimierung aktiviert; Chunks werden durch eine Komprimierungsrichtlinie oder auf Anforderung komprimiert"
    ),
    "Nothing is compressed now; chunks are compressed later by a compression policy or on request": (
        "Derzeit wird nichts komprimiert; Chunks werden später durch eine Komprimierungsrichtlinie oder "
        "auf Anforderung komprimiert"
    ),
    "Only chunks compressed from now on use these settings; already compressed chunks keep theirs": (
        "Nur ab jetzt komprimierte Chunks verwenden diese Einstellungen; bereits komprimierte behalten ihre"
    ),
    "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits": (
        "Sperrt diese Hypertable während der Einstellungsänderung exklusiv; Lesen und Schreiben warten auf den Commit"
    ),
    "Column \"{column}\" is listed more than once": "Die Spalte „{column}“ ist mehr als einmal aufgeführt",
    "List at most {count} segment-by columns": "Geben Sie höchstens {count} segmentby-Spalten an",
    "List at most {count} order-by columns": "Geben Sie höchstens {count} orderby-Spalten an",
    "Each line names one column": "Jede Zeile nennt eine Spalte",
    "This hypertable has no column \"{column}\"": "Diese Hypertable hat keine Spalte „{column}“",
    "The current compression settings could not be read": "Die aktuellen Komprimierungseinstellungen konnten nicht gelesen werden",
    "TimescaleDB compression settings planning timed out": "Zeitüberschreitung bei der Planung der TimescaleDB-Komprimierungseinstellungen",
    # Eine Tabelle umwandeln.
    "Convert to hypertable": "In eine Hypertable umwandeln",
    "The table becomes a hypertable, which DataPlayer cannot turn back into an ordinary table. Convert it?": (
        "Die Tabelle wird zu einer Hypertable, die DataPlayer nicht wieder in eine gewöhnliche Tabelle "
        "zurückverwandeln kann. Umwandeln?"
    ),
    "Time column": "Zeitspalte",
    "A timestamp or date column of this table": "Eine Spalte dieser Tabelle vom Typ timestamp oder date",
    "Chunk interval": "Chunk-Intervall",
    "The table could not be inspected safely for conversion": (
        "Die Tabelle konnte vor der Umwandlung nicht sicher geprüft werden"
    ),
    "Convert {target} into a hypertable": "{target} in eine Hypertable umwandeln",
    "Time column: {column} ({type})": "Zeitspalte: {column} ({type})",
    "Chunk interval: {interval}": "Chunk-Intervall: {interval}",
    "The table is empty, and the conversion refuses if a row arrives before it runs": (
        "Die Tabelle ist leer, und die Umwandlung schlägt fehl, wenn vor ihrem Lauf eine Zeile eintrifft"
    ),
    "{column} becomes NOT NULL": "{column} wird NOT NULL",
    "{column} becomes NOT NULL; a row without a time makes the conversion fail and roll back": (
        "{column} wird NOT NULL; eine Zeile ohne Zeit lässt die Umwandlung fehlschlagen und zurückrollen"
    ),
    "An index on {column} alone already exists, so TimescaleDB adds none": (
        "Ein Index allein auf {column} existiert bereits, daher fügt TimescaleDB keinen hinzu"
    ),
    "TimescaleDB adds an index on {column}, newest first": (
        "TimescaleDB fügt einen Index auf {column} hinzu, neueste zuerst"
    ),
    "The table keeps its name and identity and becomes a hypertable; DataPlayer cannot turn it back into an ordinary table": (
        "Die Tabelle behält ihren Namen und ihre Identität und wird zu einer Hypertable; DataPlayer kann sie "
        "nicht wieder in eine gewöhnliche Tabelle zurückverwandeln"
    ),
    "Locks this table exclusively for the conversion; its reads and writes wait until it commits": (
        "Sperrt diese Tabelle exklusiv für die Umwandlung; Lesen und Schreiben warten auf den Commit"
    ),
    "Review the conversion plan before applying it": "Prüfen Sie den Umwandlungsplan, bevor Sie ihn anwenden",
    "Converted to a hypertable; rows added from now on are stored in chunks": (
        "In eine Hypertable umgewandelt; ab jetzt hinzugefügte Zeilen werden in Chunks gespeichert"
    ),
    "Choose an existing ordinary table": "Wählen Sie eine vorhandene gewöhnliche Tabelle",
    "This table is already a hypertable": "Diese Tabelle ist bereits eine Hypertable",
    "Foreign keys between this table and a hypertable are not supported": (
        "Fremdschlüssel zwischen dieser Tabelle und einer Hypertable werden nicht unterstützt"
    ),
    "This table has no timestamp or date column to partition by": (
        "Diese Tabelle hat keine Spalte vom Typ timestamp oder date zum Partitionieren"
    ),
    "This table has no timestamp, date or integer column to partition by": (
        "Diese Tabelle hat keine Spalte vom Typ timestamp, date oder ganzzahlige zum Partitionieren"
    ),
    "This table is not empty; only empty tables are converted here": (
        "Diese Tabelle ist nicht leer; hier werden nur leere Tabellen umgewandelt"
    ),
    "This table has too many indexes to inspect": "Diese Tabelle hat zu viele Indizes zum Prüfen",
    "The TimescaleDB conversion API is split across schemas": "Die TimescaleDB-Umwandlungs-API ist über mehrere Schemas verteilt",
    "TimescaleDB conversion planning timed out": "Zeitüberschreitung bei der Planung der TimescaleDB-Umwandlung",
    "Only the table's owner can convert it": "Nur der Eigentümer der Tabelle kann sie umwandeln",
    "This connection may not read the table": "Diese Verbindung darf die Tabelle nicht lesen",
    "Partitioned tables cannot become hypertables": "Partitionierte Tabellen können keine Hypertables werden",
    "Choose an ordinary table": "Wählen Sie eine gewöhnliche Tabelle",
    "Tables with NO INHERIT constraints cannot become hypertables": (
        "Tabellen mit NO INHERIT-Bedingungen können keine Hypertables werden"
    ),
    "Tables that use inheritance cannot become hypertables": (
        "Tabellen, die Vererbung verwenden, können keine Hypertables werden"
    ),
    "Only logged tables can become hypertables": "Nur geloggte Tabellen können Hypertables werden",
    "Tables with rules cannot become hypertables": "Tabellen mit Regeln können keine Hypertables werden",
    "Choose a column this table can be partitioned by: {choices}": (
        "Wählen Sie eine Spalte, nach der diese Tabelle partitioniert werden kann: {choices}"
    ),
    "Unique index \"{index}\" must include \"{column}\", which partitions the table": (
        "Der eindeutige Index „{index}“ muss „{column}“ enthalten, das die Tabelle partitioniert"
    ),
    "An integer or UUID column is converted from Hypertable settings": (
        "Eine ganzzahlige Spalte oder UUID-Spalte wird in den Hypertable-Einstellungen umgewandelt"
    ),
    "Date columns require whole days or weeks": "date-Spalten erfordern ganze Tage oder Wochen",
    # Chunks komprimieren und dekomprimieren.
    "Compress chunks": "Chunks komprimieren",
    "Decompress chunks": "Chunks dekomprimieren",
    "TimescaleDB chunk metadata could not be inspected safely": (
        "Die TimescaleDB-Chunk-Metadaten konnten nicht sicher gelesen werden"
    ),
    "TimescaleDB chunk metadata could not be read": "Die TimescaleDB-Chunk-Metadaten konnten nicht gelesen werden",
    "TimescaleDB chunk planning timed out": "Zeitüberschreitung bei der Planung der TimescaleDB-Chunk-Operation",
    "Compress 1 chunk of {target} as a job": "Job: einen Chunk von {target} komprimieren",
    "Compress {count} chunks of {target} as a job": "Job: {count} Chunks von {target} komprimieren",
    "Decompress 1 chunk of {target} as a job": "Job: einen Chunk von {target} dekomprimieren",
    "Decompress {count} chunks of {target} as a job": "Job: {count} Chunks von {target} dekomprimieren",
    "Already compressed and left as they are: {count}": "Bereits komprimiert und unverändert gelassen: {count}",
    "Already decompressed and left as they are: {count}": "Bereits dekomprimiert und unverändert gelassen: {count}",
    "Compressed chunks stay readable; queries and writes touching a chunk may wait while it is rewritten": (
        "Komprimierte Chunks bleiben lesbar; Abfragen und Schreibvorgänge, die einen Chunk berühren, können "
        "warten, während er neu geschrieben wird"
    ),
    "Decompressed chunks take more space; a compression policy may compress them again on its own schedule": (
        "Dekomprimierte Chunks benötigen mehr Platz; eine Komprimierungsrichtlinie kann sie nach ihrem eigenen "
        "Zeitplan erneut komprimieren"
    ),
    "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted": (
        "Jeder Chunk wird in seiner eigenen Transaktion umgewandelt; ein Abbruch behält die bereits umgewandelten Chunks"
    ),
    "The hypertable could not be found; nothing was converted": "Die Hypertable wurde nicht gefunden; nichts wurde umgewandelt",
    "Every whole chunk inside this window is already compressed": "Jeder ganze Chunk innerhalb dieses Fensters ist bereits komprimiert",
    "No whole chunk inside this window is compressed": "Kein ganzer Chunk innerhalb dieses Fensters ist komprimiert",
    "No whole chunk lies inside this window": "Kein ganzer Chunk liegt innerhalb dieses Fensters",
    "More than {count} chunks lie inside this window; narrow it": (
        "Mehr als {count} Chunks liegen innerhalb dieses Fensters; grenzen Sie es enger ein"
    ),
    "This chunk is in use; nothing was converted": "Dieser Chunk wird verwendet; nichts wurde umgewandelt",
    "The source cancelled converting this chunk after its fifteen minutes; it was rolled back": (
        "Die Quelle brach die Umwandlung dieses Chunks nach seinen fünfzehn Minuten ab; sie wurde zurückgerollt"
    ),
    "This connection may not convert this chunk": "Diese Verbindung darf diesen Chunk nicht umwandeln",
    "The connection was lost while this chunk was being converted; its outcome is unknown": (
        "Die Verbindung ging verloren, während dieser Chunk umgewandelt wurde; sein Ergebnis ist unbekannt"
    ),
    "The source could not be reached; nothing was converted": "Die Quelle war nicht erreichbar; nichts wurde umgewandelt",
    "The hypertable could not be checked in time; nothing was converted": (
        "Die Hypertable konnte nicht rechtzeitig geprüft werden; nichts wurde umgewandelt"
    ),
    "The hypertable could not be checked safely; nothing was converted": (
        "Die Hypertable konnte nicht sicher geprüft werden; nichts wurde umgewandelt"
    ),
    "The hypertable or its TimescaleDB API changed after review; nothing was converted": (
        "Die Hypertable oder ihre TimescaleDB-API hat sich nach der Prüfung geändert; nichts wurde umgewandelt"
    ),
    "This chunk is no longer part of the hypertable": "Dieser Chunk gehört nicht mehr zur Hypertable",
    "The source could not be reached or prepared; nothing was converted": (
        "Die Quelle war nicht erreichbar oder konnte nicht vorbereitet werden; nichts wurde umgewandelt"
    ),
    "The source refused to convert this chunk": "Die Quelle lehnte es ab, diesen Chunk umzuwandeln",
    # Chunk-Wartung.
    "Drop chunks": "Chunks löschen",
    "Drop these chunks and every row in them? This cannot be undone.": (
        "Diese Chunks und alle darin enthaltenen Zeilen löschen? Dies kann nicht rückgängig gemacht werden."
    ),
    "Detach chunks": "Chunks abtrennen",
    "Merge chunks": "Chunks zusammenführen",
    "Merge chunks, reads going on": "Chunks zusammenführen, Lesen läuft weiter",
    "Move chunks to a tablespace": "Chunks in einen Tablespace verschieben",
    "Reorder chunks by an index": "Chunks nach einem Index neu anordnen",
    "Split a chunk": "Einen Chunk aufteilen",
    "Attach a table as a chunk": "Eine Tabelle als Chunk anhängen",
    "Drop chunks…": "Chunks löschen…",
    "Move chunks to a tablespace…": "Chunks in einen Tablespace verschieben…",
    "Reorder chunks by an index…": "Chunks nach einem Index neu anordnen…",
    "Detach chunks…": "Chunks abtrennen…",
    "Merge chunks…": "Chunks zusammenführen…",
    "Merge chunks, reads going on…": "Chunks zusammenführen, Lesen läuft weiter…",
    "Tablespace": "Tablespace",
    "An existing tablespace this connection may create in": (
        "Ein vorhandener Tablespace, in dem diese Verbindung erstellen darf"
    ),
    "Order rows by index": "Zeilen nach Index ordnen",
    "Leave empty for the index on the time column": "Leer lassen für den Index auf der Zeitspalte",
    "Index tablespace": "Index-Tablespace",
    "Leave empty to move the indexes with the chunk": "Leer lassen, um die Indizes zusammen mit dem Chunk zu verschieben",
    "Index": "Index",
    "An index of this hypertable to order rows by": "Ein Index dieser Hypertable, nach dem Zeilen geordnet werden",
    "Split at": "Aufteilen bei",
    "With its time zone; the chunk holding this instant is split at it": (
        "Mit Zeitzone; der Chunk, der diesen Zeitpunkt enthält, wird an ihm aufgeteilt"
    ),
    "Schema of the table": "Schema der Tabelle",
    "Table": "Tabelle",
    "A table with the hypertable's columns, such as a detached chunk": (
        "Eine Tabelle mit den Spalten der Hypertable, etwa ein abgetrennter Chunk"
    ),
    "Covering from": "Abdeckung von",
    "Until": "Bis",
    "Either a window or picked chunks, not both": "Entweder ein Fenster oder gewählte Chunks, nicht beides",
    "Give where the window ends": "Geben Sie an, wo das Fenster endet",
    "With the chunk": "Mit dem Chunk",
    "The index on the time column": "Der Index auf der Zeitspalte",
    "A value of \"{column}\", the {type} column the hypertable is partitioned by": (
        "Ein Wert von „{column}“, der {type}-Spalte, nach der die Hypertable partitioniert ist"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; leave empty for every earlier chunk": (
        "Ein Wert von „{column}“, der {type}-Spalte, nach der die Hypertable partitioniert ist; leer lassen "
        "für alle früheren Chunks"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; the chunk holding it is split at it": (
        "Ein Wert von „{column}“, der {type}-Spalte, nach der die Hypertable partitioniert ist; der Chunk, "
        "der ihn enthält, wird an ihm aufgeteilt"
    ),
    "Drop 1 chunk of {target} as a job": "Job: einen Chunk von {target} löschen",
    "Drop {count} chunks of {target} as a job": "Job: {count} Chunks von {target} löschen",
    "Move 1 chunk of {target} as a job": "Job: einen Chunk von {target} verschieben",
    "Move {count} chunks of {target} as a job": "Job: {count} Chunks von {target} verschieben",
    "Reorder 1 chunk of {target} as a job": "Job: einen Chunk von {target} neu anordnen",
    "Reorder {count} chunks of {target} as a job": "Job: {count} Chunks von {target} neu anordnen",
    "Detach 1 chunk of {target} as a job": "Job: einen Chunk von {target} abtrennen",
    "Detach {count} chunks of {target} as a job": "Job: {count} Chunks von {target} abtrennen",
    "Merge {count} chunks of {target} into one as a job": "Job: {count} Chunks von {target} zu einem zusammenführen",
    "Split {chunk} at {point} as a job": "Job: {chunk} bei {point} aufteilen",
    "Attach {table} to {target} as a chunk as a job": "Job: {table} als Chunk an {target} anhängen",
    "Exactly the chunks picked in the Chunks report, each read again by name": (
        "Genau die im Bericht „Chunks“ gewählten Chunks, jeder erneut namentlich gelesen"
    ),
    "Left as they are, already in {tablespace}: {count}": "Unverändert gelassen, bereits in {tablespace}: {count}",
    "Left as they are, compressed, which reorder_chunk does not rewrite: {count}": (
        "Unverändert gelassen, komprimiert, was reorder_chunk nicht neu schreibt: {count}"
    ),
    "Left as they are, compressed; TimescaleDB detaches only uncompressed chunks: {count}": (
        "Unverändert gelassen, komprimiert; TimescaleDB trennt nur unkomprimierte Chunks ab: {count}"
    ),
    "Left as they are: {count}": "Unverändert gelassen: {count}",
    "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs": (
        "Jede Zeile in diesen Chunks wird gelöscht; jeder Chunk wird namentlich gelöscht, niemals nach einem "
        "beim Joblauf gelesenen Alter"
    ),
    "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; Detached chunks lists it, and Attach chunk brings it back": (
        "Jeder Chunk wird zu einer gewöhnlichen Tabelle unter seinem eigenen Namen und verlässt die Abfragen "
        "der Hypertable; „Abgetrennte Chunks“ listet ihn auf, und „Tabelle als Chunk anhängen“ holt ihn zurück"
    ),
    "The chunks become one, covering their whole range; the table is locked while they merge": (
        "Die Chunks werden zu einem, der ihren gesamten Bereich abdeckt; die Tabelle wird während des "
        "Zusammenführens gesperrt"
    ),
    "The chunks become one, covering their whole range; reads go on meanwhile, writes to them wait": (
        "Die Chunks werden zu einem, der ihren gesamten Bereich abdeckt; Lesen läuft derweil weiter, "
        "Schreiben in sie wartet"
    ),
    "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile": (
        "Jeder Chunk wird in den Tablespace kopiert und die alte Kopie entfernt; Lesen und Schreiben darauf warten derweil"
    ),
    "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile": (
        "Jeder Chunk wird in der Reihenfolge des Index neu geschrieben, was Lesevorgänge entlang ihm "
        "beschleunigt; Lesen und Schreiben warten derweil"
    ),
    "The chunk becomes two, divided at this point; the table is locked while it splits": (
        "Der Chunk wird zu zwei, geteilt an diesem Punkt; die Tabelle wird während des Aufteilens gesperrt"
    ),
    "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit": (
        "Ihre Zeilen fließen in die Abfragen der Hypertable ein; TimescaleDB lehnt eine Tabelle ab, deren "
        "Spalten oder Zeilen nicht passen"
    ),
    "The hypertable could not be found; nothing was changed": "Die Hypertable wurde nicht gefunden; nichts wurde geändert",
    "This hypertable is partitioned by the integer column \"{column}\"; give its values, not instants": (
        "Diese Hypertable ist nach der ganzzahligen Spalte „{column}“ partitioniert; geben Sie ihre Werte an, "
        "nicht Zeitpunkte"
    ),
    "This hypertable is partitioned by time on \"{column}\"; give instants, not numbers": (
        "Diese Hypertable ist nach der Zeit in Spalte „{column}“ partitioniert; geben Sie Zeitpunkte an, nicht Zahlen"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not merged here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Chunks einer nach {columns} per Hash partitionierten Hypertable werden hier nicht zusammengeführt: "
        "In welcher Partition ein Chunk liegt, ist nicht öffentlich, daher konnte das Ergebnis vorab nicht "
        "geprüft werden"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not attached here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Chunks einer nach {columns} per Hash partitionierten Hypertable werden hier nicht angehängt: "
        "In welcher Partition ein Chunk liegt, ist nicht öffentlich, daher konnte das Ergebnis vorab nicht "
        "geprüft werden"
    ),
    "TimescaleDB splits no chunk of a hypertable partitioned by hash as well as by time": (
        "TimescaleDB teilt keinen Chunk einer sowohl per Hash als auch nach Zeit partitionierten Hypertable"
    ),
    "Pick at least one chunk": "Wählen Sie mindestens einen Chunk",
    "Pick at most {count} chunks at a time": "Wählen Sie höchstens {count} Chunks auf einmal",
    "\"{name}\" is not a chunk of this hypertable any more": "„{name}“ ist kein Chunk dieser Hypertable mehr",
    "Tablespace \"{name}\" does not exist or this connection may not create in it": (
        "Der Tablespace „{name}“ existiert nicht, oder diese Verbindung darf darin nichts erstellen"
    ),
    "This hypertable has no index \"{index}\"": "Diese Hypertable hat keinen Index „{index}“",
    "Every whole chunk inside this window is already in {tablespace}": "Jeder ganze Chunk innerhalb dieses Fensters ist bereits in {tablespace}",
    "Every picked chunk is already in {tablespace}": "Jeder gewählte Chunk ist bereits in {tablespace}",
    "Every whole chunk inside this window is compressed, which reorder_chunk does not rewrite": (
        "Jeder ganze Chunk innerhalb dieses Fensters ist komprimiert, was reorder_chunk nicht neu schreibt"
    ),
    "Every picked chunk is compressed, which reorder_chunk does not rewrite": (
        "Jeder gewählte Chunk ist komprimiert, was reorder_chunk nicht neu schreibt"
    ),
    "Every whole chunk inside this window is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Jeder ganze Chunk innerhalb dieses Fensters ist komprimiert; TimescaleDB trennt nur unkomprimierte Chunks ab"
    ),
    "Every picked chunk is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Jeder gewählte Chunk ist komprimiert; TimescaleDB trennt nur unkomprimierte Chunks ab"
    ),
    "Name an index: moving a chunk rewrites it in an index's order": (
        "Nennen Sie einen Index: Beim Verschieben wird ein Chunk in der Reihenfolge eines Index neu geschrieben"
    ),
    "A merge needs at least two chunks": "Ein Zusammenführen erfordert mindestens zwei Chunks",
    "Chunks \"{before}\" and \"{after}\" are not adjacent; choose chunks that touch": (
        "Die Chunks „{before}“ und „{after}“ sind nicht benachbart; wählen Sie aneinandergrenzende Chunks"
    ),
    "TimescaleDB {version} cannot merge compressed chunks; decompress them first": (
        "TimescaleDB {version} kann keine komprimierten Chunks zusammenführen; dekomprimieren Sie sie zuerst"
    ),
    "No chunk holds this point strictly inside its range": "Kein Chunk enthält diesen Punkt streng innerhalb seines Bereichs",
    "There is no table \"{schema}\".\"{table}\"": "Es gibt keine Tabelle „{schema}“.“{table}“",
    "Only an ordinary table can become a chunk": "Nur eine gewöhnliche Tabelle kann zu einem Chunk werden",
    "Only the table's owner can attach it": "Nur der Eigentümer der Tabelle kann sie anhängen",
    "A hypertable cannot become a chunk": "Eine Hypertable kann nicht zu einem Chunk werden",
    "This table is already a chunk": "Diese Tabelle ist bereits ein Chunk",
    "A table that uses inheritance cannot become a chunk": "Eine Tabelle, die Vererbung verwendet, kann nicht zu einem Chunk werden",
    "Chunk \"{name}\" already covers part of this range": "Chunk „{name}“ deckt bereits einen Teil dieses Bereichs ab",
    "The range is empty once read in the column's type": "Der Bereich ist leer, sobald er im Typ der Spalte gelesen wird",
    "This chunk is in use; nothing was changed": "Dieser Chunk wird verwendet; nichts wurde geändert",
    "The source cancelled this unit after its fifteen minutes; it was rolled back": (
        "Die Quelle brach diese Einheit nach ihren fünfzehn Minuten ab; sie wurde zurückgerollt"
    ),
    "This connection may not change this chunk": "Diese Verbindung darf diesen Chunk nicht ändern",
    "The connection was lost while this unit was running; its outcome is unknown": (
        "Die Verbindung ging verloren, während diese Einheit lief; ihr Ergebnis ist unbekannt"
    ),
    "The hypertable could not be checked in time; nothing was changed": (
        "Die Hypertable konnte nicht rechtzeitig geprüft werden; nichts wurde geändert"
    ),
    "The hypertable or its chunks changed after review; nothing was changed": (
        "Die Hypertable oder ihre Chunks haben sich nach der Prüfung geändert; nichts wurde geändert"
    ),
    "The hypertable could not be checked safely; nothing was changed": (
        "Die Hypertable konnte nicht sicher geprüft werden; nichts wurde geändert"
    ),
    "The source could not be reached; nothing was changed": "Die Quelle war nicht erreichbar; nichts wurde geändert",
    "The table to attach is gone; nothing was changed": "Die anzuhängende Tabelle ist verschwunden; nichts wurde geändert",
    "This chunk was compressed after review; it was left as it is": (
        "Dieser Chunk wurde nach der Prüfung komprimiert; er wurde unverändert gelassen"
    ),
    "These chunks changed after review; nothing was merged": "Diese Chunks haben sich nach der Prüfung geändert; nichts wurde zusammengeführt",
    "The index to order rows by is gone; nothing was changed": (
        "Der Index, nach dem Zeilen geordnet werden sollten, ist verschwunden; nichts wurde geändert"
    ),
    "The source could not be reached or prepared; nothing was changed": (
        "Die Quelle war nicht erreichbar oder konnte nicht vorbereitet werden; nichts wurde geändert"
    ),
    "The source refused this unit; nothing was changed": "Die Quelle lehnte diese Einheit ab; nichts wurde geändert",
    "This is not offered over these rows": "Dies wird für diese Zeilen nicht angeboten",
    "A chunk is named by its schema and its name": "Ein Chunk wird durch sein Schema und seinen Namen benannt",
    "The picked chunks belong to {count} hypertables; pick chunks of one": (
        "Die gewählten Chunks gehören zu {count} Hypertables; wählen Sie Chunks einer einzigen"
    ),
    "Some picked rows are not chunks any more; read the report again": (
        "Einige gewählte Zeilen sind keine Chunks mehr; lesen Sie den Bericht erneut"
    ),
    # Chunks überspringen.
    "Skip chunks by a column": "Chunks nach einer Spalte überspringen",
    "Stop skipping chunks by a column": "Chunks nicht mehr nach einer Spalte überspringen",
    "Column": "Spalte",
    "An integer, date or timestamp column queries filter on": (
        "Eine ganzzahlige Spalte oder Spalte vom Typ date oder timestamp, nach der Abfragen filtern"
    ),
    "The hypertable could not be inspected safely": "Die Hypertable konnte nicht sicher geprüft werden",
    "TimescaleDB keeps ranges only of integer, date and timestamp columns, not of \"{column}\" ({type})": (
        "TimescaleDB speichert Bereiche nur von ganzzahligen Spalten und Spalten der Typen date und timestamp, "
        "nicht von „{column}“ ({type})"
    ),
    "Planning chunk skipping timed out": "Zeitüberschreitung bei der Planung des Chunk-Überspringens",
    "Chunks record the range of {column} as they are compressed, and a query filtering on it skips the chunks outside": (
        "Chunks zeichnen beim Komprimieren den Bereich von {column} auf, und eine darauf filternde Abfrage "
        "überspringt die Chunks außerhalb"
    ),
    "Chunks stop recording the range of {column}, if they did": (
        "Chunks zeichnen den Bereich von {column} nicht mehr auf, falls sie es taten"
    ),
    "Changes nothing if it already holds: TimescaleDB keeps which columns record ranges where this application does not read": (
        "Ändert nichts, falls es bereits gilt: TimescaleDB speichert, welche Spalten Bereiche aufzeichnen, "
        "dort, wo diese Anwendung nicht liest"
    ),
    "timescaledb.enable_chunk_skipping is off for this connection; queries use the ranges only in sessions that turn it on": (
        "timescaledb.enable_chunk_skipping ist für diese Verbindung aus; Abfragen verwenden die Bereiche nur "
        "in Sitzungen, die es einschalten"
    ),
    "Skip chunks by {column} on {target}": "Chunks von {target} nach {column} überspringen",
    "Stop skipping chunks by {column} on {target}": "Chunks von {target} nicht mehr nach {column} überspringen",
    "Review the chunk skipping plan before applying it": "Prüfen Sie den Plan zum Überspringen von Chunks, bevor Sie ihn anwenden",
    "Chunk skipping turned on": "Chunk-Überspringen aktiviert",
    "Chunk skipping turned off": "Chunk-Überspringen deaktiviert",
    # Hypertable-Einstellungen: die Hypertable lesen.
    "Hypertable settings": "Hypertable-Einstellungen",
    "Reading the hypertable timed out": "Zeitüberschreitung beim Lesen der Hypertable",
    "Job {job} drops chunks {chunks}, every {every}": "Job {job} löscht Chunks {chunks}, alle {every}",
    "Job {job} drops chunks {chunks}, every {every}; paused": (
        "Job {job} löscht Chunks {chunks}, alle {every}; pausiert"
    ),
    "Job {job} compresses chunks {chunks}, every {every}": "Job {job} komprimiert Chunks {chunks}, alle {every}",
    "Job {job} compresses chunks {chunks}, every {every}; paused": (
        "Job {job} komprimiert Chunks {chunks}, alle {every}; pausiert"
    ),
    "Job {job} reorders chunks by {index}": "Job {job} ordnet Chunks nach {index} neu an",
    "Job {job} reorders chunks by {index}; paused": "Job {job} ordnet Chunks nach {index} neu an; pausiert",
    "Job {job} reorders chunks by an index this editor cannot read": (
        "Job {job} ordnet Chunks nach einem Index neu an, den dieser Editor nicht lesen kann"
    ),
    "Job {job} reorders chunks by an index this editor cannot read; paused": (
        "Job {job} ordnet Chunks nach einem Index neu an, den dieser Editor nicht lesen kann; pausiert"
    ),
    "The current sparse indexes could not be read": "Die aktuellen Sparse-Indizes konnten nicht gelesen werden",
    "This hypertable has a sparse index of a kind this editor does not know; manage it with SQL": (
        "Diese Hypertable hat einen Sparse-Index einer Art, die dieser Editor nicht kennt; verwalten Sie ihn mit SQL"
    ),
    "The current columnstore settings could not be read": (
        "Die aktuellen Columnstore-Einstellungen konnten nicht gelesen werden"
    ),
    "This hypertable merges compressed chunks by a time interval; manage it with SQL": (
        "Diese Hypertable führt komprimierte Chunks nach einem Zeitintervall zusammen; verwalten Sie das mit SQL"
    ),
    "This hypertable has several compaction policy jobs; manage them with SQL": (
        "Diese Hypertable hat mehrere Jobs für Kompaktierungsrichtlinien; verwalten Sie sie mit SQL"
    ),
    "This hypertable has several reorder policy jobs; manage them with SQL": (
        "Diese Hypertable hat mehrere Jobs für Neuordnungsrichtlinien; verwalten Sie sie mit SQL"
    ),
    "The existing reorder policy could not be read safely; manage it with SQL": (
        "Die bestehende Neuordnungsrichtlinie konnte nicht sicher gelesen werden; verwalten Sie sie mit SQL"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; it is edited here from 2.25": (
        "TimescaleDB {version} partitioniert nach UUIDv7 nur teilweise; hier wird dies ab 2.25 bearbeitet"
    ),
    "Only timestamp, date, UUIDv7 and integer time dimensions are edited here": (
        "Hier werden nur Zeitdimensionen der Typen timestamp, date, UUIDv7 und ganzzahlige bearbeitet"
    ),
    "The current chunk interval could not be read": "Das aktuelle Chunk-Intervall konnte nicht gelesen werden",
    "Only hash dimensions beside the time dimension are edited here": (
        "Hier werden nur Hash-Dimensionen neben der Zeitdimension bearbeitet"
    ),
    "The hypertable's chunks and tablespaces could not be read": (
        "Die Chunks und Tablespaces der Hypertable konnten nicht gelesen werden"
    ),
    "This connection may not create functions in schema \"{schema}\"": (
        "Diese Verbindung darf keine Funktionen im Schema „{schema}“ erstellen"
    ),
    "A function named \"{name}\" already exists; choose it from the list or another name": (
        "Eine Funktion namens „{name}“ existiert bereits; wählen Sie sie aus der Liste oder einen anderen Namen"
    ),
    "A chunk interval of an integer column is a number of its values": (
        "Ein Chunk-Intervall einer ganzzahligen Spalte ist eine Anzahl ihrer Werte"
    ),
    "A chunk interval of a {type} column is at most {count}": (
        "Ein Chunk-Intervall einer Spalte vom Typ {type} beträgt höchstens {count}"
    ),
    "A chunk interval is counted in minutes, hours, days or weeks": (
        "Ein Chunk-Intervall wird in Minuten, Stunden, Tagen oder Wochen gezählt"
    ),
    # Hypertable-Einstellungen: die Änderung planen.
    "Locks this hypertable exclusively while it changes; its reads and writes wait until it commits": (
        "Sperrt diese Hypertable während der Änderung exklusiv; Lesen und Schreiben warten auf den Commit"
    ),
    "Other changes to this hypertable's settings wait until it commits": (
        "Andere Änderungen an den Einstellungen dieser Hypertable warten auf den Commit"
    ),
    "A chunk interval of this hypertable is counted in days or weeks": (
        "Ein Chunk-Intervall dieser Hypertable wird in Tagen oder Wochen gezählt"
    ),
    "A chunk interval of this hypertable is counted in minutes or hours or days or weeks": (
        "Ein Chunk-Intervall dieser Hypertable wird in Minuten, Stunden, Tagen oder Wochen gezählt"
    ),
    "A chunk interval of this column is counted in days or weeks": (
        "Ein Chunk-Intervall dieser Spalte wird in Tagen oder Wochen gezählt"
    ),
    "A chunk interval of this column is counted in minutes or hours or days or weeks": (
        "Ein Chunk-Intervall dieser Spalte wird in Minuten, Stunden, Tagen oder Wochen gezählt"
    ),
    "Column \"{column}\" has a type that cannot be used as a hash dimension": (
        "Die Spalte „{column}“ hat einen Typ, der nicht als Hash-Dimension verwendet werden kann"
    ),
    "Column \"{column}\" has a type that cannot be used as a minmax sparse index": (
        "Die Spalte „{column}“ hat einen Typ, der nicht als Minmax-Sparse-Index verwendet werden kann"
    ),
    "Column \"{column}\" has a type that cannot be used as a segment column": (
        "Die Spalte „{column}“ hat einen Typ, der nicht als Segmentierungsspalte verwendet werden kann"
    ),
    "Column \"{column}\" has a type that cannot be used as an order column": (
        "Die Spalte „{column}“ hat einen Typ, der nicht als Sortierspalte verwendet werden kann"
    ),
    "TimescaleDB cannot remove the hash dimension on \"{column}\"": (
        "TimescaleDB kann die Hash-Dimension auf „{column}“ nicht entfernen"
    ),
    "A hash dimension can only be added while the hypertable holds no chunks": (
        "Eine Hash-Dimension kann nur hinzugefügt werden, solange die Hypertable keine Chunks enthält"
    ),
    "The time column cannot also be a hash dimension": "Die Zeitspalte kann nicht zugleich eine Hash-Dimension sein",
    "Unique key \"{key}\" must include \"{column}\" before it can be a hash dimension": (
        "Der eindeutige Schlüssel „{key}“ muss „{column}“ enthalten, bevor es eine Hash-Dimension sein kann"
    ),
    "TimescaleDB {version} has no sparse indexes; they arrived in 2.22": (
        "TimescaleDB {version} hat keine Sparse-Indizes; sie kamen in 2.22"
    ),
    "Column \"{column}\" has the same sparse index twice": "Die Spalte „{column}“ hat denselben Sparse-Index zweimal",
    "Sparse indexes need the order to be named; choose the columns to order by": (
        "Sparse-Indizes erfordern eine benannte Reihenfolge; wählen Sie die Spalten zum Sortieren"
    ),
    "Column \"{column}\" is listed more than once in the columnstore settings": (
        "Die Spalte „{column}“ ist in den Columnstore-Einstellungen mehr als einmal aufgeführt"
    ),
    "The columnstore cannot be turned off while chunks are compressed; decompress them first": (
        "Der Columnstore kann nicht deaktiviert werden, solange Chunks komprimiert sind; dekomprimieren Sie sie zuerst"
    ),
    "TimescaleDB {version} cannot return a setting to its own choice; name the columns instead": (
        "TimescaleDB {version} kann eine Einstellung nicht wieder ihrer eigenen Wahl überlassen; nennen Sie "
        "stattdessen die Spalten"
    ),
    "Merging compressed chunks is set in time, which an integer column does not count in": (
        "Das Zusammenführen komprimierter Chunks wird in Zeit angegeben, die eine ganzzahlige Spalte nicht zählt"
    ),
    "A merge interval is counted in the units of the chunk interval": (
        "Ein Zusammenführungsintervall wird in den Einheiten des Chunk-Intervalls gezählt"
    ),
    "The merge interval must be a whole multiple of the chunk interval, larger than it": (
        "Das Zusammenführungsintervall muss ein ganzzahliges Vielfaches des Chunk-Intervalls und größer als dieses sein"
    ),
    "There is no retention policy to keep": "Es gibt keine Aufbewahrungsrichtlinie, die beibehalten werden könnte",
    "There is no compression policy to keep": "Es gibt keine Komprimierungsrichtlinie, die beibehalten werden könnte",
    "The retention policy of an integer column is a number of its values": (
        "Die Aufbewahrungsrichtlinie einer ganzzahligen Spalte ist eine Anzahl ihrer Werte"
    ),
    "The compression policy of an integer column is a number of its values": (
        "Die Komprimierungsrichtlinie einer ganzzahligen Spalte ist eine Anzahl ihrer Werte"
    ),
    "The retention policy of a {type} column is at most {count}": (
        "Die Aufbewahrungsrichtlinie einer Spalte vom Typ {type} beträgt höchstens {count}"
    ),
    "The compression policy of a {type} column is at most {count}": (
        "Die Komprimierungsrichtlinie einer Spalte vom Typ {type} beträgt höchstens {count}"
    ),
    "The retention policy of a {type} column cannot count in plain numbers": (
        "Die Aufbewahrungsrichtlinie einer Spalte vom Typ {type} kann nicht in reinen Zahlen gezählt werden"
    ),
    "The compression policy of a {type} column cannot count in plain numbers": (
        "Die Komprimierungsrichtlinie einer Spalte vom Typ {type} kann nicht in reinen Zahlen gezählt werden"
    ),
    "The retention policy of a {type} column cannot count in seconds": (
        "Die Aufbewahrungsrichtlinie einer Spalte vom Typ {type} kann nicht in Sekunden gezählt werden"
    ),
    "The compression policy of a {type} column cannot count in seconds": (
        "Die Komprimierungsrichtlinie einer Spalte vom Typ {type} kann nicht in Sekunden gezählt werden"
    ),
    "The retention policy of a {type} column cannot count in minutes": (
        "Die Aufbewahrungsrichtlinie einer Spalte vom Typ {type} kann nicht in Minuten gezählt werden"
    ),
    "The compression policy of a {type} column cannot count in minutes": (
        "Die Komprimierungsrichtlinie einer Spalte vom Typ {type} kann nicht in Minuten gezählt werden"
    ),
    "The retention policy of a {type} column cannot count in hours": (
        "Die Aufbewahrungsrichtlinie einer Spalte vom Typ {type} kann nicht in Stunden gezählt werden"
    ),
    "The compression policy of a {type} column cannot count in hours": (
        "Die Komprimierungsrichtlinie einer Spalte vom Typ {type} kann nicht in Stunden gezählt werden"
    ),
    "The existing reorder policy is paused; remove it before setting a new one": (
        "Die bestehende Neuordnungsrichtlinie ist pausiert; entfernen Sie sie, bevor Sie eine neue festlegen"
    ),
    "Only a hypertable partitioned by an integer column takes an integer_now function": (
        "Nur eine nach einer ganzzahligen Spalte partitionierte Hypertable nimmt eine integer_now-Funktion an"
    ),
    "TimescaleDB cannot take an integer_now function away; keep it or choose another": (
        "TimescaleDB kann eine integer_now-Funktion nicht wegnehmen; behalten Sie sie oder wählen Sie eine andere"
    ),
    "There is no integer_now function to keep": "Es gibt keine integer_now-Funktion, die beibehalten werden könnte",
    "{function} is not a function TimescaleDB accepts as integer_now of a {type} column": (
        "TimescaleDB akzeptiert {function} nicht als integer_now einer Spalte vom Typ {type}"
    ),
    "A {type} column cannot hold the seconds since 1970": "Eine Spalte vom Typ {type} kann die Sekunden seit 1970 nicht aufnehmen",
    "A {type} column cannot hold the milliseconds since 1970": (
        "Eine Spalte vom Typ {type} kann die Millisekunden seit 1970 nicht aufnehmen"
    ),
    "A {type} column cannot hold the microseconds since 1970": (
        "Eine Spalte vom Typ {type} kann die Mikrosekunden seit 1970 nicht aufnehmen"
    ),
    "TimescaleDB {version} has no compaction policy; it arrived in 2.29": (
        "TimescaleDB {version} hat keine Kompaktierungsrichtlinie; sie kam in 2.29"
    ),
    "A compaction policy merges compressed chunks; turn the columnstore on": (
        "Eine Kompaktierungsrichtlinie führt komprimierte Chunks zusammen; aktivieren Sie den Columnstore"
    ),
    "Remove the columnstore policy to turn the columnstore off": (
        "Entfernen Sie die Columnstore-Richtlinie, um den Columnstore zu deaktivieren"
    ),
    "Remove the compaction policy to turn the columnstore off": (
        "Entfernen Sie die Kompaktierungsrichtlinie, um den Columnstore zu deaktivieren"
    ),
    "An age policy on an integer column needs an integer_now function to tell the current value": (
        "Eine Altersrichtlinie für eine ganzzahlige Spalte benötigt eine integer_now-Funktion, die den aktuellen Wert angibt"
    ),
    "Choose the time column the table is partitioned by": "Wählen Sie die Zeitspalte, nach der die Tabelle partitioniert wird",
    "Choose the chunk interval": "Wählen Sie das Chunk-Intervall",
    "TimescaleDB cannot change the time column of a hypertable": "TimescaleDB kann die Zeitspalte einer Hypertable nicht ändern",
    "Planning the hypertable change timed out": "Zeitüberschreitung bei der Planung der Hypertable-Änderung",
    # Hypertable-Einstellungen: die Vorschau.
    "TimescaleDB's choice for each chunk": "TimescaleDBs Wahl für jeden Chunk",
    "TimescaleDB's choice": "TimescaleDBs Wahl",
    "none": "keine",
    "segment by {columns}": "segmentby: {columns}",
    "order by {columns}": "orderby: {columns}",
    "sparse indexes {indexes}": "Sparse-Indizes: {indexes}",
    "{kind} on {column}": "{kind} auf {column}",
    "no merging of chunks": "kein Zusammenführen von Chunks",
    "merge chunks into {length} as they are compressed": "beim Komprimieren Chunks zu {length} zusammenführen",
    "Turn the columnstore on: {changes}": "Columnstore aktivieren: {changes}",
    "Columnstore settings for chunks compressed from now on: {changes}": (
        "Columnstore-Einstellungen für ab jetzt komprimierte Chunks: {changes}"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, and move its rows into chunks": (
        "Die Tabelle nach {column} ({type}) in eine Hypertable umwandeln, Chunks von {length}, und ihre Zeilen "
        "in Chunks verschieben"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, while it is empty": (
        "Die Tabelle nach {column} ({type}) in eine Hypertable umwandeln, Chunks von {length}, solange sie leer ist"
    ),
    "Remove the retention policy (job {job})": "Die Aufbewahrungsrichtlinie entfernen (Job {job})",
    "Remove the columnstore policy (job {job})": "Die Columnstore-Richtlinie entfernen (Job {job})",
    "Remove the reorder policy (job {job})": "Die Neuordnungsrichtlinie entfernen (Job {job})",
    "Remove the compaction policy (job {job})": "Die Kompaktierungsrichtlinie entfernen (Job {job})",
    "Add a retention policy: drop chunks older than {length}": (
        "Eine Aufbewahrungsrichtlinie hinzufügen: Chunks löschen, die älter sind als {length}"
    ),
    "Add a columnstore policy: compress chunks older than {length}": (
        "Eine Columnstore-Richtlinie hinzufügen: Chunks komprimieren, die älter sind als {length}"
    ),
    "Add a compaction policy: merge small compressed chunks on TimescaleDB's schedule": (
        "Eine Kompaktierungsrichtlinie hinzufügen: kleine komprimierte Chunks nach TimescaleDBs Zeitplan zusammenführen"
    ),
    "Add a reorder policy by index {index}": "Eine Neuordnungsrichtlinie nach Index {index} hinzufügen",
    "New chunks cover {length}; existing chunks keep their range": (
        "Neue Chunks umfassen {length}; bestehende Chunks behalten ihren Bereich"
    ),
    "Hash {column} into {partitions} partitions for new chunks": (
        "{column} für neue Chunks in {partitions} Partitionen hashen"
    ),
    "Add a hash dimension on {column} with {partitions} partitions": (
        "Eine Hash-Dimension auf {column} mit {partitions} Partitionen hinzufügen"
    ),
    "Turn the columnstore off": "Columnstore deaktivieren",
    "Place new chunks in tablespace {tablespace} too": "Neue Chunks auch im Tablespace {tablespace} ablegen",
    "Stop placing new chunks in tablespace {tablespace}": (
        "Neue Chunks nicht mehr im Tablespace {tablespace} ablegen"
    ),
    "Create function {function} returning the seconds since 1970 as {type}": (
        "Funktion {function} erstellen, die die Sekunden seit 1970 als {type} zurückgibt"
    ),
    "Create function {function} returning the milliseconds since 1970 as {type}": (
        "Funktion {function} erstellen, die die Millisekunden seit 1970 als {type} zurückgibt"
    ),
    "Create function {function} returning the microseconds since 1970 as {type}": (
        "Funktion {function} erstellen, die die Mikrosekunden seit 1970 als {type} zurückgibt"
    ),
    "Policies take the current value of the time column from {function}": (
        "Richtlinien beziehen den aktuellen Wert der Zeitspalte aus {function}"
    ),
    "Moves about {count} rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Verschiebt etwa {count} Zeilen als Job in Aktivität in Chunks; die Tabelle ist bis zu dessen Ende "
        "für Lesen und Schreiben gesperrt"
    ),
    "Moves an unknown number of rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Verschiebt eine unbekannte Anzahl Zeilen als Job in Aktivität in Chunks; die Tabelle ist bis zu "
        "dessen Ende für Lesen und Schreiben gesperrt"
    ),
    "Rolled back whole if it fails, is cancelled or runs past {seconds} seconds; nothing is left half converted": (
        "Wird als Ganzes zurückgerollt, wenn es fehlschlägt, abgebrochen wird oder {seconds} Sekunden "
        "überschreitet; nichts bleibt halb umgewandelt zurück"
    ),
    "DataPlayer cannot turn a hypertable back into an ordinary table": (
        "DataPlayer kann eine Hypertable nicht wieder in eine gewöhnliche Tabelle zurückverwandeln"
    ),
    "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, after this session ends": (
        "TimescaleDB löscht weiterhin ganze Chunks jenseits des Aufbewahrungsalters nach seinem eigenen "
        "Zeitplan, auch nachdem diese Sitzung endet"
    ),
    "{target} already matches these settings": "{target} entspricht bereits diesen Einstellungen",
    "Change {target}": "{target} ändern",
    "Review the hypertable plan before applying it": "Prüfen Sie den Hypertable-Plan, bevor Sie ihn anwenden",
    "Moving rows into chunks runs as a job; start it from the plan": (
        "Das Verschieben von Zeilen in Chunks läuft als Job; starten Sie ihn aus dem Plan"
    ),
    "Converted to a hypertable": "In eine Hypertable umgewandelt",
    "Hypertable changed: 1 change applied": "Hypertable geändert: eine Änderung angewendet",
    "Hypertable changed: {count} changes applied": "Hypertable geändert: {count} Änderungen angewendet",
    "This change is applied at once rather than as a job": "Diese Änderung wird sofort angewendet, nicht als Job",
    "The table could not be found; nothing was converted": "Die Tabelle wurde nicht gefunden; nichts wurde umgewandelt",
    "The table was renamed after review; nothing was converted": (
        "Die Tabelle wurde nach der Prüfung umbenannt; nichts wurde umgewandelt"
    ),
    # Eine als Hypertable entworfene Tabelle.
    "Hypertable": "Hypertable",
    "Columnstore": "Columnstore",
    "Retention policy": "Aufbewahrungsrichtlinie",
    "Columnstore policy": "Columnstore-Richtlinie",
    "Compaction policy": "Kompaktierungsrichtlinie",
    "Reorder policy": "Neuordnungsrichtlinie",
    "Integer now": "Integer now",
    "Function {name}": "Funktion {name}",
    "Hash dimension {column}": "Hash-Dimension {column}",
    "The segment list names a column that is not there": "Die Segmentliste nennt eine Spalte, die nicht existiert",
    "The order list names a column that is not there": "Die Sortierliste nennt eine Spalte, die nicht existiert",
    "The sparse index names a column that is not there": "Der Sparse-Index nennt eine Spalte, die nicht existiert",
    "The time dimension names a column that is not there": "Die Zeitdimension nennt eine Spalte, die nicht existiert",
    "The hash dimension names a column that is not there": "Die Hash-Dimension nennt eine Spalte, die nicht existiert",
    "Choose the columns to segment by": "Wählen Sie die Spalten zum Segmentieren",
    "Choose the columns to order by": "Wählen Sie die Spalten zum Sortieren",
    "Choose the columns of the sparse indexes": "Wählen Sie die Spalten der Sparse-Indizes",
    "The reorder policy names an index that is not there": "Die Neuordnungsrichtlinie nennt einen Index, der nicht existiert",
    "The TimescaleDB API is split across schemas": "Die TimescaleDB-API ist über mehrere Schemas verteilt",
    "This setting cannot be made while the table is created": "Diese Einstellung kann nicht beim Erstellen der Tabelle vorgenommen werden",
    "\"{column}\" cannot partition a hypertable; choose a timestamp or date column": (
        "„{column}“ kann keine Hypertable partitionieren; wählen Sie eine Spalte vom Typ timestamp oder date"
    ),
    "\"{column}\" partitions the hypertable, so it must have a value": (
        "„{column}“ partitioniert die Hypertable, daher muss es einen Wert haben"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; choose a timestamp column": (
        "TimescaleDB {version} partitioniert nach UUIDv7 nur teilweise; wählen Sie eine Spalte vom Typ timestamp"
    ),
}
