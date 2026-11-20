# FTP

Un serveur joint en FTP ou FTPS. Vous parcourez ses dossiers à partir de
l'endroit choisi et travaillez avec ses fichiers comme avec les vôtres :
tableaux, SQL sur fichiers, visionneuses et recherche. La connexion se fait par
mot de passe ou de façon anonyme. Le fonctionnement général des connexions est
décrit sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Les dossiers et fichiers sous le dossier choisi
- Les tableaux des fichiers CSV, TSV, Excel et Parquet, et des journaux
- Documents, code, images, PDF, enregistrements et contenu des archives zip
- Les fichiers trouvés par nom ou par le texte qu'ils contiennent
- Du SQL exécuté sur les tableaux des fichiers

## Ce que vous pouvez modifier

- Les fichiers dans un éditeur de texte
- Les lignes et colonnes des fichiers CSV et TSV
- Fichiers et dossiers : créer, téléverser, renommer, supprimer, télécharger
- Archives : regrouper des fichiers en une, ou en extraire une
- Les fichiers copiés ou déplacés entre dossiers et connexions

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port** : 21, ou 990 pour le TLS implicite ;
- **Chiffrement** : **TLS, explicite** est ce que parlent la plupart des
  serveurs aujourd'hui, sur le port 21. **TLS, implicite** est l'ancien FTPS
  sur le port 990. **Aucun chiffrement** envoie le mot de passe tel que vous le
  tapez : ne le choisissez que pour un serveur qui n'offre rien d'autre ;
- **Vérifier le certificat** : à désactiver uniquement pour un serveur dont
  vous avez fait le certificat vous-même ;
- **Dossier** : où commence la navigation. Vide, c'est le dossier où le serveur
  vous place à la connexion ; `/` est le sommet du serveur ;
- **Authentification** : un **Utilisateur** et un **Mot de passe**, ou
  **Anonyme** pour un serveur public.

**URL** montre le serveur sous la forme `ftp://user@host/folder`, et `ftps://`
pour le TLS implicite. Une adresse collée remplit l'hôte, le port,
l'utilisateur et le dossier. Le mot de passe n'en fait jamais partie.

## Le catalogue et les fichiers

Une connexion FTP se parcourt comme une connexion [Fichiers](source-file.md) : le
même catalogue, la même recherche par nom et dans les fichiers, les mêmes
visionneuses et le même SQL sur fichiers. Les mêmes actions aussi : **Nouveau dossier**, **Nouveau fichier**,
**Téléverser des fichiers**, **Renommer**, **Supprimer**, **Télécharger**,
**Archiver**, **Extraire**, **Copier**, **Couper** et **Coller**.

En quoi un serveur FTP diffère d'un disque :

- Ce que vous pouvez lire et modifier dépend des droits du serveur lui-même.
- Un fichier dont le nom n'est pas en UTF-8 n'est pas affiché. Il reste sur le
  serveur.
- Certains serveurs ne donnent l'heure qu'à la minute près, ou seulement le
  jour pour les fichiers anciens, et aucun ne dit son fuseau horaire : les
  heures sont affichées en UTC.
- Un fichier de plus de 200 Mo ne s'ouvre pas comme tableau, classeur, archive
  ni en SQL : téléchargez-le. Texte, images, PDF et enregistrements s'ouvrent
  quelle que soit leur taille.
- Une recherche dans les fichiers ignore ceux de plus de 1 Mo et s'arrête après
  32 Mo au total, car chaque octet traverse le réseau.
- La copie fait passer chaque octet par DataPlayer, car FTP n'a pas de copie à
  lui : jusqu'à 200 Mo à la fois.
- Un fichier enregistré par-dessus un fichier modifié entre-temps est refusé
  plutôt qu'écrasé.
