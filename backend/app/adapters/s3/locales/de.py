"""What S3 writes, in German (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the editor, archives, search and copying between connections. Buckets are made and deleted here too. Signs in with an access key.": "Amazon S3 oder ein Speicher, der dessen API spricht. Buckets und Ordner durchsuchen und mit Objekten wie mit eigenen Dateien arbeiten: Tabellen, SQL über Dateien, der Editor, Archive, die Suche und Kopieren zwischen Verbindungen. Buckets werden hier auch angelegt und gelöscht. Anmeldung mit einem Zugriffsschlüssel.",
    "The store's address, such as https://s3.example.com; empty for Amazon S3": "Die Adresse des Speichers, etwa https://s3.example.com; leer für Amazon S3",
    "Region": "Region",
    "Empty is us-east-1": "Leer ist us-east-1",
    "Access key": "Zugriffsschlüssel",
    "Bucket": "Bucket",
    "Empty shows every bucket this key may list": "Leer zeigt jeden Bucket, den dieser Schlüssel auflisten darf",
    "Where browsing starts inside the bucket": "Wo das Durchsuchen im Bucket beginnt",
    "Addressing": "Adressierung",
    "Auto is virtual-hosted on Amazon S3 and path-style elsewhere": "Automatisch ist virtual-hosted bei Amazon S3 und path-style anderswo",
    "Verify the certificate": "Zertifikat prüfen",
    "Off only for a store with a certificate of its own making": "Nur ausschalten für einen Speicher mit selbst ausgestelltem Zertifikat",
    "The endpoint must be an http or https address": "Der Endpunkt muss eine http- oder https-Adresse sein",
    "A bucket is one name, without slashes": "Ein Bucket ist ein Name, ohne Schrägstriche",
    "The folder must stay inside the bucket": "Der Ordner muss im Bucket bleiben",
    "A folder needs the bucket it is in": "Ein Ordner braucht den Bucket, in dem er liegt",
    "The store does not know this access key": "Der Speicher kennt diesen Zugriffsschlüssel nicht",
    "The secret key does not match the access key": "Der geheime Schlüssel passt nicht zum Zugriffsschlüssel",
    "The store does not let this key do that": "Der Speicher erlaubt diesem Schlüssel das nicht",
    "There is no such bucket in this store": "Diesen Bucket gibt es in diesem Speicher nicht",
    "The bucket is in another region than this connection names": "Der Bucket liegt in einer anderen Region als der, die diese Verbindung nennt",
    "This object is archived and has to be restored first": "Dieses Objekt ist archiviert und muss zuerst wiederhergestellt werden",
    "That is no longer in the store": "Das ist nicht mehr im Speicher",
    "The store's certificate was not accepted": "Das Zertifikat des Speichers wurde nicht akzeptiert",
    "The store did not answer in time": "Der Speicher hat nicht rechtzeitig geantwortet",
    "Could not reach the store": "Der Speicher war nicht erreichbar",
    "The store could not do that": "Der Speicher konnte das nicht ausführen",
    "Only buckets are kept at the root of the store": "Im Stamm des Speichers liegen nur Buckets",
    "{name} holds more than {count} objects; this store changes them one by one, so it is refused": "{name} enthält mehr als {count} Objekte; dieser Speicher ändert sie einzeln, deshalb wird es abgelehnt",
    "The store did not delete every object": "Der Speicher hat nicht jedes Objekt gelöscht",
    "A bucket is not renamed or copied as a whole": "Ein Bucket wird nicht als Ganzes umbenannt oder kopiert",
    "A bucket's name is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending with a letter or a digit": "Der Name eines Buckets besteht aus 3 bis 63 Kleinbuchstaben, Ziffern, Punkten und Bindestrichen und beginnt und endet mit einem Buchstaben oder einer Ziffer",
    "{name} keeps old versions of its objects; empty it with a lifecycle rule, then delete it": "{name} bewahrt alte Versionen seiner Objekte auf; leeren Sie ihn mit einer Lebenszyklusregel und löschen Sie ihn dann",
}
