import type { Messages } from "../en"

/** Cloud-Konten, mit denen sich Verbindungen anmelden (features/cloudAccounts). */
export const cloud_accounts: Messages["cloud_accounts"] = {
  section: {
    title: "Cloud-Konten",
    hint: "Konten, von denen Ihre Verbindungen Passwörter und Tokens bekommen: Amazon Web Services, Google Cloud, Microsoft Azure und HashiCorp Vault. Ein Token wird für jede neue Verbindung ausgestellt und nie gespeichert. Hier eingegebene Geheimnisse werden verschlüsselt aufbewahrt und nie wieder angezeigt.",
    form_hint: "Konten, von denen Ihre Verbindungen Passwörter und Tokens bekommen; eines dient jeder Verbindung. Seine Geheimnisse werden verschlüsselt aufbewahrt und nie wieder angezeigt.",
    new_account: "Neues Konto",
    empty: "Noch keine Cloud-Konten",
    unused: "Keine Verbindung verwendet es",
    used_by: "Verwendet von {names}",
    ambient: "Identität dieses Servers",
    test: "Konto testen",
    test_failed: "Das Konto konnte nicht getestet werden",
    edit: "Konto ändern",
    delete_title: "Dieses Konto löschen?",
    delete_message: "{name} und seine Geheimnisse verschwinden von diesem Server. Die Anmeldedaten selbst bleiben in der Cloud.",
    delete: "Löschen",
    delete_failed: "Das Konto konnte nicht gelöscht werden",
    delete_used: "Richten Sie seine Verbindungen zuerst auf ein anderes Konto",
    delete_account: "Dieses Konto löschen",
  },
  dialog: {
    title_new: "Neues Cloud-Konto",
    title_edit: "Cloud-Konto ändern",
    subtitle: "Geheimnisse werden verschlüsselt aufbewahrt und nie wieder angezeigt",
    name: "Name",
    kind: "Cloud",
    make: "Anlegen",
    save: "Speichern",
    made: "Konto angelegt",
    saved: "Konto gespeichert",
    save_failed: "Das Konto konnte nicht gespeichert werden",
  },
}
