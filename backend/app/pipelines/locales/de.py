"""Was eine Pipeline und ihre Läufe sagen, auf Deutsch (D226). Die Begriffe folgen dem Glossar der Oberfläche."""

MESSAGES: dict[str, str] = {
    # Einen Lauf ausführen.
    "running its links": "Verbindungen ausführen",
    "{name} is gone, or no longer shared with you": "{name} ist nicht mehr vorhanden oder wird nicht mehr mit Ihnen geteilt",
    "{name} is switched off": "{name} ist ausgeschaltet",
    "{name} can no longer be opened": "{name} kann nicht mehr geöffnet werden",
    "You no longer have read access to {name}": "Sie haben keinen Lesezugriff mehr auf {name}",
    "You no longer have write access to {name}": "Sie haben keinen Schreibzugriff mehr auf {name}",
    "You no longer have structure access to {name}": "Sie haben keinen Strukturzugriff mehr auf {name}",
    "You no longer have own access to {name}": "Sie haben keine Eigentümerrechte mehr an {name}",
    "The link could not run": "Die Verbindung konnte nicht ausgeführt werden",
    "{link} made nothing in this run": "„{link}“ hat in diesem Lauf nichts erzeugt",
    "Its owner is no longer here": "Der Eigentümer ist nicht mehr hier",
    "{kind} is not possible between these connections": "{kind} ist zwischen diesen Verbindungen nicht möglich",
    "{kind} cannot run": "{kind} kann nicht ausgeführt werden",
    "The link it reads": "Die Verbindung, die sie liest",
    "This run could not be read; nothing ran": "Dieser Lauf konnte nicht gelesen werden; nichts wurde ausgeführt",
    # Der Satz eines Laufs.
    "{said}; {count} not run": "{said}; {count} nicht ausgeführt",
    "{done} of {count} links ran": "{done} von {count} Verbindungen ausgeführt",
    "Its one link ran": "Ihre einzige Verbindung wurde ausgeführt",
    "All {count} links ran": "Alle {count} Verbindungen wurden ausgeführt",
    "Stopped at {at} of {count}, {title}: {reason}": "Gestoppt bei {at} von {count}, „{title}“: {reason}",
    "Stopped at {at} of {count}, {title}": "Gestoppt bei {at} von {count}, „{title}“",
    "Stopped on request at {at} of {count}, {title}": "Auf Anfrage gestoppt bei {at} von {count}, „{title}“",
    "Stopped on request before its first link": "Auf Anfrage vor der ersten Verbindung gestoppt",
    "Stopped on request after {done} of {count}": "Auf Anfrage nach {done} von {count} gestoppt",
    # Einen Lauf starten.
    "{number} · {title} needs its table named and its columns chosen": "{number} · „{title}“ benötigt einen Tabellennamen und ausgewählte Spalten",
    "{number} · {title} needs its columns paired": "{number} · „{title}“ benötigt zugeordnete Spalten",
    "a result": "ein Ergebnis",
    "{connection} (top)": "{connection} (oberste Ebene)",
    "Nothing ran: {needs}": "Nichts wurde ausgeführt: {needs}",
    # Die Fläche.
    "This connection is gone, or no longer shared with you": "Diese Verbindung ist nicht mehr vorhanden oder wird nicht mehr mit Ihnen geteilt",
    "This connection is switched off": "Diese Verbindung ist ausgeschaltet",
    "This connection cannot be read": "Diese Verbindung kann nicht gelesen werden",
    "{names} and {last}": "{names} und {last}",
    "{names} write into each other, so the arrows give no first link: this one goes first because its card is furthest left": "{names} schreiben ineinander, daher geben die Pfeile keine erste Verbindung vor: Diese kommt zuerst, weil ihre Karte am weitesten links liegt",
    "{names} write into each other, so the arrows give no first link: this one goes first because its card is highest": "{names} schreiben ineinander, daher geben die Pfeile keine erste Verbindung vor: Diese kommt zuerst, weil ihre Karte am höchsten liegt",
    "{names} write into each other, so the arrows give no first link: this one goes first because it starts from the highest row": "{names} schreiben ineinander, daher geben die Pfeile keine erste Verbindung vor: Diese kommt zuerst, weil sie mit der obersten Zeile beginnt",
    "{names} write into each other, so the arrows give no first link: this one goes first because it was drawn first": "{names} schreiben ineinander, daher geben die Pfeile keine erste Verbindung vor: Diese kommt zuerst, weil sie zuerst gezeichnet wurde",
    "{names} write into each other, so the arrows give no first link: this one goes first because the others wait for links outside them as well": "{names} schreiben ineinander, daher geben die Pfeile keine erste Verbindung vor: Diese kommt zuerst, weil die anderen auch auf Verbindungen außerhalb des Kreises warten",
    "{name} was removed": "{name} wurde entfernt",
    # Suche.
    "Pipelines": "Pipelines",
    "Pipeline": "Pipeline",
    # A link keeping the latest per key (D314).
    "{number} · {title} needs its key and values chosen": "{number} · „{title}“ benötigt Schlüssel und Werte",
    # A pipeline following its topics (D315).
    "Followed; {count} messages carried": "Gefolgt; übertragene Nachrichten: {count}",
    "Only a link reading a topic follows it": "Nur eine Verknüpfung, die ein Topic liest, kann ihm folgen",
    "This following could not be read": "Dieses Folgen ließ sich nicht lesen",
    "following its topics": "folgt seinen Topics",
    # A pipeline switched on with one button (D362, D363).
    "Runs continuously; not run": "Läuft fortlaufend; nicht ausgeführt",
    "Not switched on: {needs}": "Nicht eingeschaltet: {needs}",
    "Same connection": "Dieselbe Verbindung",
    "Nothing can go from here into this connection": "Von hier kann nichts in diese Verbindung gehen",
    "Already linked": "Bereits verknüpft",
    "Nothing can go here": "Hierher kann nichts gehen",
}
