"""Was ClickHouse schreibt, auf Deutsch (D226). Begriffe folgen dem Glossar der Bildschirme."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    'A ClickHouse server, over its HTTP interface. Browse databases, tables and views, read rows a page at a time with sorting and filtering done by the server, and run SQL.': 'Ein ClickHouse-Server über seine HTTP-Schnittstelle. Datenbanken, Tabellen und Sichten durchsuchen, Zeilen seitenweise lesen, sortiert und gefiltert vom Server, und SQL ausführen.',
    "The HTTP interface: 8123, or 8443 with TLS": "Die HTTP-Schnittstelle: 8123, oder 8443 mit TLS",
    "TLS": "TLS",
    "HTTPS, with the server's certificate verified": "HTTPS, mit geprüftem Zertifikat des Servers",
    "That is not a ClickHouse connection string": "Das ist keine ClickHouse-Verbindungszeichenfolge",
    "ClickHouse {version} is older than this source supports ({oldest})": "ClickHouse {version} ist älter, als diese Quelle unterstützt ({oldest})",
    # Relations and rows.
    'This ClickHouse source does not offer the "{representation}" content representation': "Diese ClickHouse-Quelle bietet die Inhaltsdarstellung „{representation}“ nicht an",
    "A filter value does not fit its column": "Ein Filterwert passt nicht zu seiner Spalte",
    "Changing the structure of a ClickHouse table is not supported yet": "Die Struktur einer ClickHouse-Tabelle lässt sich noch nicht ändern",
    "Editing ClickHouse rows is not supported yet": "ClickHouse-Zeilen lassen sich noch nicht bearbeiten",
    # The console.
    'ClickHouse keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own': 'ClickHouse übernimmt eine Änderung sofort und kann sie nicht rückgängig machen, daher kann eine Änderung keinen Lauf mit anderen Anweisungen teilen; führen Sie sie allein aus',
    'Detaching and attaching tables is not done from the query editor': 'Tabellen werden nicht aus dem Abfrageeditor getrennt oder angefügt',
    'Named collections are not changed from the query editor': 'Benannte Sammlungen werden nicht aus dem Abfrageeditor geändert',
    'SYSTEM commands manage the server and are not run from the query editor': 'SYSTEM-Befehle verwalten den Server und werden nicht aus dem Abfrageeditor ausgeführt',
    'The console shows a result itself; leave FORMAT out': 'Die Konsole zeigt ein Ergebnis selbst an; lassen Sie FORMAT weg',
    'The query editor changes databases, tables, views and dictionaries; this is something else': 'Der Abfrageeditor ändert Datenbanken, Tabellen, Sichten und Wörterbücher; dies ist etwas anderes',
}
