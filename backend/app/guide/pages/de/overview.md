# DataPlayer auf einen Blick

DataPlayer verbindet die Quellen, mit denen Sie arbeiten — Datenbanken, Dateispeicher,
Warteschlangen, Server über SSH und andere — und lässt Sie sie an einer Stelle lesen und
ändern. Diese Seite zeigt, wo was zu finden ist; jeder Teil hat eine eigene Seite.

## Die vier Bereiche

Der Schalter oben in der linken Leiste bestimmt, was den Bildschirm füllt:

- **Daten**: Ihre Verbindungen, ihre Kataloge und die Tabellen, Dateien und Abfragen, die
  von dort geöffnet werden. Siehe [Der Arbeitsbereich](workspace.md) und
  [Verbindungen](connections.md).
- **Pipelines**: Verbindungen auf einer Arbeitsfläche, mit Verknüpfungen, die Zeilen und
  Dateien von einer zur anderen kopieren — von Hand oder nach einem Zeitplan. Siehe
  [Pipelines](pipelines.md).
- **Dashboards**: Metriken, die Agenten und Ihre Verbindungen melden, über die Zeit
  gezeichnet. Siehe [Dashboards](dashboards.md).
- **KI**: Gespräche mit dem Agenten, der Ihre Daten über dieselben Verbindungen liest und
  ändert. Siehe [Der KI-Agent](assistant.md).

Beim Wechsel der Bereiche bleibt das Geöffnete erhalten: Wenn Sie zu **Daten**
zurückkehren, finden Sie dieselben Tabs.

## Am Rand

- **Die Kopfzeile** enthält das Suchfeld, das Verbindungen, Tabellen, Dateien, gespeicherte
  Abfragen, Pipelines, Dashboards, Chats und Seiten dieses Handbuchs findet. Ctrl+K
  (⌘K auf dem Mac) setzt den Cursor hinein. Siehe [Suche](search.md).
- **Das Benutzermenü** oben rechts öffnet **Einstellungen**, **Verwaltung** für einen
  Administrator und **Abmelden**. Siehe [Einstellungen und Konto](preferences.md).
- **Die Leisten** auf beiden Seiten halten Werkzeuge als Symbole: der Bereichsschalter und
  **Schnellchat** oben links; **Dienste**, **Terminals**, **Abfragen** und **Suchindex**
  unten links; das Speichern und Öffnen von Tab-Gruppen oben rechts. Ein Werkzeug lässt
  sich auf seiner Leiste oder auf eine andere Leiste ziehen.
- **Das Feld am Fuß** öffnet sich für **Dienste**, **Terminals**, **Abfragen**,
  **Suchindex** und für einen Administrator **Protokolle**. Siehe
  [Dienste und Terminals](services.md).
- **Die Aktivitätsglocke** unten rechts öffnet **Aktivität**: was auf Ihre Antwort wartet,
  was läuft und was kürzlich passiert ist.

## Wo Sie nachlesen

- eine Quellenart — mit eigener Seite: [PostgreSQL](source-postgres.md),
  [MySQL und MariaDB](source-mysql.md), [SQLite](source-sqlite.md),
  [ClickHouse](source-clickhouse.md), [Cassandra und ScyllaDB](source-cassandra.md),
  [MongoDB](source-mongodb.md), [Redis](source-redis.md),
  [ZooKeeper](source-zookeeper.md), [Kafka](source-kafka.md),
  [RabbitMQ](source-rabbitmq.md), [Binance](source-binance.md),
  [Dateien](source-file.md) und [SSH](source-ssh.md). Dort stehen das Lesen und Bearbeiten
  von Zeilen, Strukturänderungen, die SQL-Konsole und Berichte, jeweils für diese Quelle;
- Hinzufügen, Teilen und Einrichten einer Verbindung — [Verbindungen](connections.md);
- Spalten, Tabs, Fenster und Tab-Gruppen — [Der Arbeitsbereich](workspace.md);
- Daten nach Zeitplan verschieben — [Pipelines](pipelines.md);
- Metriken und Diagramme über die Zeit — [Dashboards](dashboards.md);
- der Agent, der Schnell-Chat und das Anbinden eines externen KI-Agenten —
  [Der KI-Agent](assistant.md);
- hier gestartete Server, Terminals und Sicherungen —
  [Dienste und Terminals](services.md).
