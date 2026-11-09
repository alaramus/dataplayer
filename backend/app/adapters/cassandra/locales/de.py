"""Was Cassandra schreibt, auf Deutsch (D226). Begriffe folgen dem Glossar der Bildschirme."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "Cassandra": "Cassandra",
    "Apache Cassandra": "Apache Cassandra",
    "ScyllaDB": "ScyllaDB",
    "Apache Cassandra or ScyllaDB, over CQL. Browse keyspaces, tables and materialized views, and read rows a page at a time with filtering done by the server.": "Apache Cassandra oder ScyllaDB über CQL. Keyspaces, Tabellen und materialisierte Sichten durchsuchen und Zeilen seitenweise lesen, gefiltert vom Server.",
    "Keyspace": "Keyspace",
    "Where the catalog opens; every keyspace the role may see is in the catalog": "Wo sich der Katalog öffnet; jeder Keyspace, den die Rolle sehen darf, steht im Katalog",
    "The native protocol's port, 9042 unless the server says otherwise": "Der Port des nativen Protokolls, 9042, sofern der Server nichts anderes vorgibt",
    "TLS, with the server's certificate verified": "TLS mit Prüfung des Serverzertifikats",
    "Consistency": "Konsistenz",
    "How many replicas answer a read and acknowledge a write": "Wie viele Replikate einen Lesevorgang beantworten und einen Schreibvorgang bestätigen",
    "That is not a Cassandra connection string": "Das ist keine Cassandra-Verbindungszeichenfolge",
    "{product} {version} is older than this source supports ({oldest})": "{product} {version} ist älter, als diese Quelle unterstützt ({oldest})",
    "Keyspace does not exist": "Der Keyspace existiert nicht",
    'Keyspace "{name}" does not exist': "Keyspace „{name}“ existiert nicht",
    "Not enough replicas are up for the consistency level asked": "Für die verlangte Konsistenzstufe laufen nicht genug Replikate",
    # Relations and rows.
    '"{node_id}" is not a relation: expected keyspace.table': "„{node_id}“ ist keine Relation: erwartet wird keyspace.tabelle",
    '"{keyspace}" belongs to the server': "„{keyspace}“ gehört dem Server",
    "Cassandra has no unique keys and no foreign keys": "Cassandra hat keine eindeutigen Schlüssel und keine Fremdschlüssel",
    "Partition key": "Partitionsschlüssel",
    "Clustering column, {order}": "Clustering-Spalte, {order}",
    "Static: one value for the whole partition": "Statisch: ein Wert für die ganze Partition",
    'This Cassandra source does not offer the "{representation}" content representation': "Diese Cassandra-Quelle bietet die Inhaltsdarstellung „{representation}“ nicht an",
    "This page is {rows} rows past the last one read; page forward from there": "Diese Seite liegt {rows} Zeilen hinter der zuletzt gelesenen; blättern Sie von dort aus weiter",
    "ScyllaDB's LIKE cannot look for % or _ in a value": "LIKE in ScyllaDB kann nicht nach % oder _ in einem Wert suchen",
    # The console and cqlsh.
    ":{name} is not a value of type {type}": ":{name} ist kein Wert vom Typ {type}",
    "Cassandra keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own, or put the changes in one BATCH": "Cassandra speichert eine Änderung sofort und kann sie nicht rückgängig machen, daher kann eine Änderung nicht zusammen mit anderen Anweisungen laufen; führen Sie sie allein aus oder fassen Sie die Änderungen in einem BATCH zusammen",
    "No value was given for :{name}": "Für :{name} wurde kein Wert angegeben",
    "This connection has no keyspace called {name}": "Diese Verbindung hat keinen Keyspace namens {name}",
    "This is not a CQL statement this console runs": "Das ist keine CQL-Anweisung, die diese Konsole ausführt",
    "cqlsh cannot read a user or a password that holds a line break": "cqlsh kann keinen Benutzer und kein Passwort mit Zeilenumbruch lesen",
    "{command} is a cqlsh command, not CQL; run it in cqlsh in a terminal": "{command} ist ein cqlsh-Befehl, kein CQL; führen Sie ihn in cqlsh in einem Terminal aus",
}
