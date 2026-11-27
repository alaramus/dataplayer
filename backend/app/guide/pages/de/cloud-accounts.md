# Cloud-Konten

Ein Cloud-Konto ist der Weg, auf dem eine Verbindung in Ihrem Namen eine Cloud
erreicht: um ein Token für die Anmeldung an einer Datenbank zu bekommen oder um
ein Passwort aus einem Geheimnisspeicher zu lesen. Es gehört Ihnen wie ein
SSH-Schlüssel: Eine Verbindung nennt es, und wer die Verbindung mit Ihnen
teilt, verwendet es, ohne es zu sehen. Konten stehen in den **Einstellungen**
unter **Cloud-Konten**; die Seite **Optionen** eines Verbindungsfensters hat
ebenfalls eine Schaltfläche **Neues Konto**.

## Arten

- **Amazon Web Services**: ein **Zugriffsschlüssel** und sein
  **Geheimschlüssel**, für temporäre Anmeldedaten mit **Sitzungstoken**. Es
  kann eine **Rolle** übernehmen — ihre ARN, eine **Externe ID**, Name und
  Dauer der Sitzung.
- **Google Cloud**: eine **Dienstkontoschlüssel**-Datei als JSON. Es kann als
  anderes Dienstkonto handeln, wenn dieses es zulässt.
- **Microsoft Azure**: ein **Dienstprinzipal** — Mandant, Client-ID und
  Client-Geheimnis.
- **HashiCorp Vault**: seine **Adresse**, bei Bedarf ein Namespace und ein
  CA-Zertifikat, und ein **Token** oder Role ID und Secret ID für **AppRole**.

Geheimnisse werden verschlüsselt aufbewahrt und nie wieder angezeigt.
**Testen** macht den günstigsten harmlosen Aufruf, den das Konto erlaubt, und
sagt, wer angemeldet ist.

## Die eigene Identität dieses Servers

Ein Konto kann sich auch als die Maschine anmelden, auf der DataPlayer läuft:
die Standard-Anmeldekette von AWS, die Application Default Credentials von
Google, eine verwaltete Identität von Azure. Jeder könnte sich diese Identität
leihen, daher wird sie nur angeboten, wo die Installation es erlaubt, und dann
nur einem Superuser.

## Was eine Verbindung damit macht

Ein Token wird für jede neue Verbindung ausgestellt und nur im Speicher
gehalten, bis es bald abläuft; nichts Ausgestelltes wird gespeichert. Die
Seite jeder Quelle sagt, welche ihrer Anmeldearten ein Konto nehmen:

- PostgreSQL und MySQL: AWS IAM (RDS), Google Cloud IAM (Cloud SQL), Microsoft
  Entra, ein Geheimnisspeicher, dynamische Vault-Anmeldedaten.
- Redis: AWS IAM (ElastiCache, MemoryDB), Microsoft Entra.
- MongoDB: AWS IAM (MONGODB-AWS), ein Geheimnisspeicher.
- Kafka: AWS IAM (MSK).
- S3: ein AWS-Konto statt eines Schlüssels.

Ein **Geheimnisspeicher** nennt das Geheimnis dort, wo es liegt: bei AWS mit
Name oder ARN; bei Google als `projects/P/secrets/S` oder nur mit dem Namen im
Projekt der Schlüsseldatei; bei Azure als `VAULT/NAME`; bei Vault als
`MOUNT/PATH`. Ein Geheimnis in JSON wird über die Schlüssel `password` und
`username` gelesen, die sich umbenennen lassen; jedes andere ist das Passwort
selbst.

Ein Server, der Passwörter gegen LDAP, PAM, RADIUS oder Active Directory
prüft, braucht kein Konto: Für DataPlayer sieht das wie ein Passwort aus.

## Grenzen

- Ein Konto behält seine Art; legen Sie für eine andere Cloud ein neues an.
- Ein Konto, das eine Verbindung verwendet, kann nicht gelöscht werden; die
  Ablehnung nennt die Verbindungen.
- Ein Token, das während einer langen Sicherung abläuft, hält sie nicht an: Die
  geöffnete Verbindung bleibt gültig.
- Die Kafka-Werkzeuge im Terminal können sich noch nicht mit AWS IAM oder OIDC
  anmelden.
