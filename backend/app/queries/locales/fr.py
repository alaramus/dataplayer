"""Ce que l'exécution de requêtes dit, en français (D226). Les termes suivent le glossaire de l'interface."""

MESSAGES: dict[str, str] = {
    # Avant une exécution.
    "There is nothing to run": "Il n'y a rien à exécuter",
    "This is more than one statement; run it as a script to run them all": "Ceci contient plus d'une instruction ; exécutez-le comme un script pour les exécuter toutes",
    "A script may hold at most {count} statements": "Un script peut contenir au plus {count} instructions",
    "Statement {at} is larger than one statement may be": "L'instruction {at} est plus grande qu'une instruction ne peut l'être",
    "Statement {at}: {refusal}": "Instruction {at} : {refusal}",
    "Maintenance commands run outside a transaction; turn the manual transaction off to run this": "Les commandes de maintenance s'exécutent hors transaction ; désactivez la transaction manuelle pour exécuter celle-ci",
    "A maintenance command runs outside a transaction, so run it on its own": "Une commande de maintenance s'exécute hors transaction, exécutez-la donc seule",
    "Statement {at} is a {kind} statement, and this run is a read": "L'instruction {at} est une instruction {kind}, et cette exécution est une lecture",
    "Statement {at} is a {kind} statement, and statements of that kind are not run here": "L'instruction {at} est une instruction {kind}, et les instructions de ce type ne s'exécutent pas ici",
    "No value was given for {names}": "Aucune valeur n'a été fournie pour {names}",
    # Écriture.
    "A write cannot run in read mode": "Une écriture ne peut pas s'exécuter en mode lecture",
    "The owner of this connection allows reading only": "Le propriétaire de cette connexion n'autorise que la lecture",
    "A {kind} statement needs read access to this connection": "Une instruction {kind} nécessite un accès en lecture à cette connexion",
    "A {kind} statement needs write access to this connection": "Une instruction {kind} nécessite un accès en écriture à cette connexion",
    "A {kind} statement needs structure access to this connection": "Une instruction {kind} nécessite un accès à la structure de cette connexion",
    "A {kind} statement needs own access to this connection": "Une instruction {kind} nécessite des droits de propriétaire sur cette connexion",
    "Confirm this write before running it": "Confirmez cette écriture avant de l'exécuter",
    "This run asks for something that cannot be undone; confirm it first": "Cette exécution demande quelque chose d'irréversible ; confirmez-la d'abord",
    "You have read access to this connection": "Vous avez un accès en lecture à cette connexion",
    # Une exécution.
    "This run could not be completed": "Cette exécution n'a pas pu être terminée",
    "There was no room to keep this result": "Il n'y avait pas de place pour conserver ce résultat",
    # Transactions et historique.
    "Committed {count} changing statement, {rows} rows": "{count} instruction de modification validée, {rows} lignes",
    "Committed {count} changing statements, {rows} rows": "{count} instructions de modification validées, {rows} lignes",
    "Rolled back {count} changing statement": "{count} instruction de modification annulée",
    "Rolled back {count} changing statements": "{count} instructions de modification annulées",
    "Document deleted": "Document supprimé",
    "{count} runs deleted": "{count} exécutions supprimées",
    # Recherche.
    "Favorites": "Favoris",
    "Untitled query": "Requête sans titre",
    "Only the newest {count} saved queries are searched by their title": "Seules les {count} requêtes enregistrées les plus récentes sont recherchées par leur titre",
    "Stopped before every saved query was read": "Arrêtée avant que chaque requête enregistrée ait été lue",
    "Only the newest {count} saved queries are searched by their text": "Seules les {count} requêtes enregistrées les plus récentes sont recherchées par leur texte",
    "Saved query": "Requête enregistrée",
    "Saved query · {connection}": "Requête enregistrée · {connection}",
}
