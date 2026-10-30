"""Ce que dit le socket d'un terminal, en français (D226). Les termes suivent le glossaire de l'interface."""

MESSAGES: dict[str, str] = {
    "No such connection": "Cette connexion n'existe pas",
    "A terminal opens only on a connection of your own": "Un terminal ne s'ouvre que sur une connexion qui vous appartient",
    "This connection is switched off": "Cette connexion est désactivée",
    "This kind of connection has no terminal": "Ce type de connexion n'a pas de terminal",
    "The connection could not be opened": "La connexion n'a pas pu être ouverte",
    "Sign in again to open a terminal": "Reconnectez-vous pour ouvrir un terminal",
    "The settings of this connection are not valid": "Les paramètres de cette connexion ne sont pas valides",
    "You have {count} terminals open already; close one first": "Vous avez déjà {count} terminaux ouverts ; fermez-en un d'abord",
    "Say who you are first": "Dites d'abord qui vous êtes",
    "The first frame opens a terminal": "La première trame ouvre un terminal",
    "Frame not understood": "Trame non comprise",
    "This terminal is already open": "Ce terminal est déjà ouvert",
    "This server cannot start a console": "Ce serveur ne peut pas lancer de console",
}
