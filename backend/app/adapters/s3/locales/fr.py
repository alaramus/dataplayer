"""What S3 writes, in French (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the editor, archives, search and copying between connections. Buckets are made and deleted here too. Signs in with an access key.": "Amazon S3 ou un stockage qui parle son API. Parcourez les buckets et les dossiers et travaillez avec les objets comme avec vos propres fichiers : tableaux, SQL sur fichiers, l'éditeur, les archives, la recherche et la copie entre connexions. Les buckets se créent et se suppriment ici aussi. Connexion par clé d'accès.",
    "The store's address, such as https://s3.example.com; empty for Amazon S3": "L'adresse du stockage, par exemple https://s3.example.com ; vide pour Amazon S3",
    "Region": "Région",
    "Empty is us-east-1": "Vide signifie us-east-1",
    "Access key": "Clé d'accès",
    "Bucket": "Bucket",
    "Empty shows every bucket this key may list": "Vide affiche tous les buckets que cette clé peut lister",
    "Where browsing starts inside the bucket": "Où la navigation commence dans le bucket",
    "Addressing": "Adressage",
    "Auto is virtual-hosted on Amazon S3 and path-style elsewhere": "Auto est virtual-hosted sur Amazon S3 et path-style ailleurs",
    "Verify the certificate": "Vérifier le certificat",
    "Off only for a store with a certificate of its own making": "À désactiver seulement pour un stockage au certificat fait maison",
    "The endpoint must be an http or https address": "Le point d'accès doit être une adresse http ou https",
    "A bucket is one name, without slashes": "Un bucket est un seul nom, sans barres obliques",
    "The folder must stay inside the bucket": "Le dossier doit rester dans le bucket",
    "A folder needs the bucket it is in": "Un dossier a besoin du bucket qui le contient",
    "The store does not know this access key": "Le stockage ne connaît pas cette clé d'accès",
    "The secret key does not match the access key": "La clé secrète ne correspond pas à la clé d'accès",
    "The store does not let this key do that": "Le stockage ne permet pas cela à cette clé",
    "There is no such bucket in this store": "Ce bucket n'existe pas dans ce stockage",
    "The bucket is in another region than this connection names": "Le bucket est dans une autre région que celle de cette connexion",
    "This object is archived and has to be restored first": "Cet objet est archivé et doit d'abord être restauré",
    "That is no longer in the store": "Ce n'est plus dans le stockage",
    "The store's certificate was not accepted": "Le certificat du stockage n'a pas été accepté",
    "The store did not answer in time": "Le stockage n'a pas répondu à temps",
    "Could not reach the store": "Impossible de joindre le stockage",
    "The store could not do that": "Le stockage n'a pas pu faire cela",
    "Only buckets are kept at the root of the store": "Seuls des buckets sont rangés à la racine du stockage",
    "{name} holds more than {count} objects; this store changes them one by one, so it is refused": "{name} contient plus de {count} objets ; ce stockage les modifie un par un, c'est donc refusé",
    "The store did not delete every object": "Le stockage n'a pas supprimé tous les objets",
    "A bucket is not renamed or copied as a whole": "Un bucket ne se renomme ni ne se copie en entier",
    "A bucket's name is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending with a letter or a digit": "Le nom d'un bucket compte 3 à 63 lettres minuscules, chiffres, points et tirets, et commence et finit par une lettre ou un chiffre",
    "{name} keeps old versions of its objects; empty it with a lifecycle rule, then delete it": "{name} conserve d'anciennes versions de ses objets ; videz-le par une règle de cycle de vie, puis supprimez-le",
}
