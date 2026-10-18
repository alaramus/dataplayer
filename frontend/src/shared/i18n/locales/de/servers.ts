/** Mit welchem DataPlayer-Server dieser Tab spricht (features/servers). */
import type { Messages } from "../en"

export const servers: Messages["servers"] = {
  check: {
    https_only: "Diese Seite verwendet HTTPS. Verwenden Sie eine HTTPS-Serveradresse.",
    unreachable:
      "Ein kompatibler DataPlayer-Server war nicht erreichbar. Prüfen Sie Adresse, Serverversion, Zertifikat und erlaubten Frontend-Ursprung (CORS).",
    incompatible: "Dieser Server ist mit dieser Version von DataPlayer nicht kompatibel.",
  },
  name_invalid: "Geben Sie einen Servernamen mit 1 bis 100 Zeichen ein.",
  name: "Servername",
  url: "Server-URL",
  url_example: "https://data.example.com",
  boundary: {
    title: "Mit DataPlayer verbinden",
  },
  link: {
    new_server: "Neuer Server",
    connect_failed: "Die Verbindung zu diesem Server konnte nicht hergestellt werden.",
    title: "Server für diesen Link auswählen",
    notice:
      "Dieser Link verwendet einen anderen Server. Prüfen Sie die Adresse vor dem Verbinden; möglicherweise müssen Sie sich dort anmelden.",
    connect: "Prüfen und verbinden",
  },
  switcher: {
    save_failed: "Der Server konnte in diesem Browser nicht gespeichert werden.",
    compatible: "Kompatibler DataPlayer-Server.",
    saved: "Server gespeichert. Wählen Sie „Verbinden“, um ihn in diesem Tab zu verwenden.",
    choose: "Server auswählen",
    servers: "Server",
    intro: "Wählen Sie den Server für diesen Browser-Tab. Konten sind auf jedem Server getrennt.",
    current: "Aktuell: {name} · {url}",
    current_mark: " · Aktuell",
    check: "Prüfen",
    connect: "Verbinden",
    edit: "Server bearbeiten",
    remove: "Server entfernen",
    add: "Server hinzufügen",
    check_connection: "Testen",
    save_and_connect: "Speichern und verbinden",
    save: "Server speichern",
  },
}
