"""Ce que SSH écrit, en français (D226). Les termes suivent le glossaire de l'interface.

Le côté fichiers appartient à l'explorateur et parle de lui-même ; ces mots
concernent le serveur, sa clé et l'authentification.
"""

MESSAGES: dict[str, str] = {
    # La source et son formulaire de connexion.
    "SSH": "SSH",
    "A server reached over SSH. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search, and a terminal. Signs in with a password or one of your SSH keys, and only to the server whose key you confirmed.": "Un serveur accessible via SSH. Parcourez ses dossiers depuis l'endroit de votre choix et travaillez avec ses fichiers comme avec les vôtres : tables, SQL sur les fichiers, l'éditeur, les archives, la recherche et un terminal. La connexion se fait avec un mot de passe ou l'une de vos clés SSH, et uniquement vers le serveur dont vous avez confirmé la clé.",
    "Authentication": "Authentification",
    "Host": "Hôte",
    "Port": "Port",
    "User": "Utilisateur",
    "Folder": "Dossier",
    "Where browsing starts; empty is the user's home folder": "Où commence la navigation ; vide correspond au dossier personnel de l'utilisateur",
    "Server key": "Clé du serveur",
    "What this server proves itself with; fetch it and compare": "Ce avec quoi ce serveur prouve son identité ; récupérez-la et comparez",
    "Key": "Clé",
    "One of your SSH keys; its public half goes to the server": "L'une de vos clés SSH ; sa partie publique est envoyée au serveur",
    "Password": "Mot de passe",
    # Adresses.
    "The SSH connection has no host": "La connexion SSH n'a pas d'hôte",
    "That is not an SSH URL": "Ce n'est pas une URL SSH",
    "Enter the host first": "Saisissez d'abord l'hôte",
    # Clés.
    "This is not a server key this application can read": "Ce n'est pas une clé de serveur que cette application peut lire",
    "That passphrase does not open this key": "Cette phrase secrète n'ouvre pas cette clé",
    "This key is protected by a passphrase; enter it": "Cette clé est protégée par une phrase secrète ; saisissez-la",
    "This is not a private key this application can read": "Ce n'est pas une clé privée que cette application peut lire",
    # Connexion.
    "Connection successful": "Connexion réussie",
    "This connection signs in with a key, and none is at hand": "Cette connexion se connecte avec une clé, et aucune n'est disponible",
    "Fetch the server's key and confirm it before connecting": "Récupérez la clé du serveur et confirmez-la avant de vous connecter",
    "The server key of this connection cannot be read": "La clé du serveur de cette connexion ne peut pas être lue",
    "The SSH key could not be opened with its passphrase": "La clé SSH n'a pas pu être ouverte avec sa phrase secrète",
    "The server did not present a key": "Le serveur n'a présenté aucune clé",
    "The server presented a different key than the one this connection trusts. If it was reinstalled, fetch its key again and compare it": "Le serveur a présenté une clé différente de celle à laquelle cette connexion fait confiance. S'il a été réinstallé, récupérez sa clé à nouveau et comparez-la",
    "The server refused these credentials": "Le serveur a refusé ces identifiants",
    "That is no longer on the server": "Cela n'est plus présent sur le serveur",
    "The server does not let this user do that": "Le serveur n'autorise pas cet utilisateur à le faire",
    "The server could not do that": "Le serveur n'a pas pu le faire",
    "The server did not answer in time": "Le serveur n'a pas répondu à temps",
    "Could not reach the server": "Le serveur est injoignable",
    "Not a path below this folder: {path}": "Chemin non situé sous ce dossier : {path}",
    # Fichiers via SFTP.
    "Symbolic links are not downloaded": "Les liens symboliques ne sont pas téléchargés",
    "A folder holding a symbolic link is not copied here": "Un dossier contenant un lien symbolique n'est pas copié ici",
    "What came out": "Résultat",
    "The file is no longer open": "Le fichier n'est plus ouvert",
    "The file could not be read from the server": "Le fichier n'a pas pu être lu depuis le serveur",
    "The file could not be created on the server": "Le fichier n'a pas pu être créé sur le serveur",
    "The file could not be written on the server": "Le fichier n'a pas pu être écrit sur le serveur",
    "The file could not be put in place on the server": "Le fichier n'a pas pu être mis en place sur le serveur",
    # Le terminal.
    "The server did not open a shell for this account": "Le serveur n'a pas ouvert de shell pour ce compte",
}
