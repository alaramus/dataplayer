"""What FTP writes, in French (D226).

The file side is the explorer's and words itself; these are the words of the
server, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "FTP": "FTP",
    "A server reached over FTP or FTPS. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search and copying between connections. Signs in with a password or anonymously.": "Un serveur joint en FTP ou FTPS. Parcourez ses dossiers à partir de l'endroit choisi et travaillez sur ses fichiers comme sur les vôtres : tableaux, SQL sur fichiers, éditeur, archives, recherche et copie entre connexions. Connexion par mot de passe ou anonyme.",
    "21, or 990 for implicit TLS": "21, ou 990 pour le TLS implicite",
    "Encryption": "Chiffrement",
    "TLS, explicit": "TLS, explicite",
    "TLS, implicit": "Aucun chiffrement",
    "No encryption": "TLS, implicite",
    "Off only for a server with a certificate of its own making": "À désactiver uniquement pour un serveur au certificat fait maison",
    "Where browsing starts; empty is the folder the server signs you into": "Où commence la navigation ; vide, c'est le dossier où le serveur vous place à la connexion",
    "The host is a name or an address, without a scheme or a path": "L'hôte est un nom ou une adresse, sans schéma ni chemin",
    "The folder is one line": "Le dossier tient sur une ligne",
    "The user is one line": "L'utilisateur tient sur une ligne",
    "A name with a line break in it cannot be sent to the server": "Un nom contenant un saut de ligne ne peut pas être envoyé au serveur",
    "Every connection to the server is busy": "Toutes les connexions au serveur sont occupées",
    "That is not an FTP address": "Ce n'est pas une adresse FTP",
    "The FTP connection has no host": "La connexion FTP n'a pas d'hôte",
    "The TLS connection to the server failed": "La connexion TLS au serveur a échoué",
    "The file is no longer on the server": "Le fichier n'est plus sur le serveur",
    "The server closed the connection": "Le serveur a fermé la connexion",
    "The server did not accept this user and password": "Le serveur n'a pas accepté cet utilisateur et ce mot de passe",
    "The server does not let anonymous users in": "Le serveur n'accepte pas les utilisateurs anonymes",
    "The server does not offer TLS; choose no encryption to sign in without it": "Le serveur ne propose pas TLS ; choisissez « Aucun chiffrement » pour vous connecter sans",
    "The server has too many connections open": "Le serveur a trop de connexions ouvertes",
    "The server is busy; try again": "Le serveur est occupé ; réessayez",
    "The server refused that": "Le serveur a refusé",
    "The server's certificate was not accepted": "Le certificat du serveur n'a pas été accepté",
    "The server's name could not be resolved": "Le nom du serveur n'a pas pu être résolu",
    "There is no such folder on the server": "Ce dossier n'existe pas sur le serveur",
}
