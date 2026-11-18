# S3

Amazon S3, ou tout stockage qui parle son API. Vous parcourez les buckets et les
dossiers et travaillez avec les objets comme avec vos propres fichiers :
tableaux, SQL sur fichiers, visionneuses et recherche. La connexion se fait par
clé d'accès. Le fonctionnement des connexions en général est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Les buckets, et les dossiers et objets qu'ils contiennent
- Les tableaux des fichiers CSV, TSV, Excel et Parquet, et des journaux
- Documents, code, images, PDF, enregistrements et contenu des archives zip
- Les objets trouvés par nom, ou par le texte qu'ils contiennent
- Le SQL exécuté sur des tableaux rangés dans des objets

## Ce que vous pouvez modifier

- Les objets dans un éditeur de texte
- Les lignes et colonnes des fichiers CSV et TSV
- Objets et dossiers : créer, téléverser, renommer, supprimer, télécharger
- Archives : regrouper des objets en une, ou en décompresser une
- Les objets copiés ou déplacés entre dossiers et connexions
- Buckets : en créer un, ou en supprimer un avec son contenu

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Point d'accès** : l'adresse du stockage, par exemple
  `https://s3.example.com`. Vide signifie Amazon S3 ;
- **Région** : vide signifie `us-east-1` ;
- **Clé d'accès** et **Clé secrète** ;
- **Bucket** : vide affiche tous les buckets que la clé peut lister ;
- **Dossier** : où la navigation commence dans le bucket ;
- **Adressage** : « auto » est virtual-hosted sur Amazon S3 et path-style
  ailleurs, ce que tout stockage compatible accepte ;
- **Vérifier le certificat** : à désactiver seulement pour un stockage dont vous
  avez fait le certificat vous-même.

## Le catalogue et les objets

Une connexion S3 se parcourt comme une connexion [Fichiers](source-file.md) : le
même catalogue, la même recherche par nom et dans les fichiers, les mêmes
visionneuses et le même SQL sur fichiers. Les mêmes actions aussi : **Nouveau dossier**, **Nouveau fichier**,
**Téléverser des fichiers**, **Renommer**, **Supprimer**, **Télécharger**,
**Archiver**, **Extraire**, **Copier**, **Couper** et **Coller**.

En quoi un stockage diffère d'un disque :

- Un dossier est le début commun de clés, `reports/2026/`. Un dossier vide est
  un objet vide dont la clé se termine par `/`, ce que font aussi les consoles
  des fournisseurs.
- Une clé qui ne pourrait pas être un nom de fichier — avec une partie vide,
  `.` ou `..`, une barre oblique inverse ou un lecteur comme `C:` — n'est pas
  affichée. Elle reste dans le bucket.
- Un objet de plus de 200 Mo ne s'ouvre pas comme tableau, classeur, archive ni
  en SQL : téléchargez-le. Texte, images, PDF et enregistrements s'ouvrent quelle
  que soit leur taille.
- Une recherche dans les objets ignore ceux de plus de 1 Mo et s'arrête après
  32 Mo au total, car chaque octet traverse le réseau.
- Un objet dans une classe de stockage d'archive doit être restauré avant de
  pouvoir être lu.
- Renommer ou déplacer un dossier copie chaque objet qu'il contient puis
  supprime les anciens : le stockage ne sait pas renommer. Jusqu'à 10 000
  objets sont déplacés, copiés ou supprimés d'un coup ; un dossier plus grand
  est refusé.
- Un fichier modifié entre-temps n'est pas écrasé : l'enregistrement est
  refusé.

### Buckets

Quand **Bucket** est vide, le haut du catalogue liste les buckets.

- **Nouveau dossier** y crée un bucket, dans la région de la connexion. Son
  nom compte 3 à 63 lettres minuscules, chiffres, points et tirets, et commence
  et finit par une lettre ou un chiffre.
- **Supprimer** retire un bucket avec tout son contenu, jusqu'à 10 000 objets.
  Un bucket qui conserve d'anciennes versions de ses objets est refusé :
  videz-le d'abord par une règle de cycle de vie.
- Un bucket ne se renomme ni ne se copie, et aucun fichier n'est rangé à côté
  des buckets.
