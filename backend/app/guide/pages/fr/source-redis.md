# Redis

Un serveur clé-valeur en mémoire. Vous parcourez ses clés sous forme d'arbre
construit à partir des deux-points de leurs noms, lisez ce que contient une clé
sous forme de lignes, écrivez des clés de tous les types et définissez ou
supprimez leur expiration. Le fonctionnement général des connexions est décrit
sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Chaque base de données du serveur, et ses clés sous forme d'arbre
- Ce que contient une clé, sous forme de lignes : champs, éléments de list,
  éléments de set, scores, entrées
- Le type d'une clé, sa taille et le temps qui lui reste à vivre
- Un dossier de hachages comme une seule table
- Les métriques du serveur sur les tableaux de bord

## Ce que vous pouvez modifier

- Les valeurs à l'intérieur d'une clé, une à la fois
- Des clés des six types : créer, remplacer, supprimer
- L'expiration d'une clé : la définir ou la supprimer
- Des tables décrites sur des dossiers de hachages
- Des clés enregistrées comme fichiers CSV

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port**, 6379 sauf indication contraire du serveur ;
- **Base de données** : celle sur laquelle le catalogue s'ouvre. Toutes les bases
  de données restent accessibles depuis le catalogue ;
- **Authentification** : un mot de passe, ou aucun.

Une chaîne de connexion telle que `redis://:secret@cache.example.com:6379/0`
collée dans **URL** remplit ces champs. Une adresse `rediss://`, qui nécessite
TLS, n'est pas encore prise en charge.

## Le catalogue

Le catalogue est un arbre.

- La commande en haut choisit la base de données. Elle indique combien de clés
  chacune contient. Le choix est mémorisé dans ce navigateur.
- Les clés sont regroupées selon les deux-points de leurs noms :
  `session:42:token` se trouve sous `session`, puis sous `42`. Appuyer sur un
  dossier l'ouvre sur place.
- Une clé indique son type, sa taille et, si elle expire, combien de temps il lui
  reste.
- Appuyer sur une clé l'ouvre dans un onglet. Appuyer sur une ligne la
  sélectionne, et le menu d'actions agit alors sur elle.
- Un espace de clés très grand est listé jusqu'à un plafond. Un dossier plus
  étroit montre ce qui se trouve au-delà.

## Lire une clé

Une clé s'ouvre sous forme de lignes. La forme dépend de son type :

- un **string** est une seule valeur ;
- un **hash** est des champs et des valeurs ;
- une **list** est des positions et des valeurs ;
- un **set** est des éléments ;
- un **sorted set** est des éléments et des scores ;
- un **stream** est des entrées.

Les lignes sont paginées comme n'importe quelle table dans la grille. Redis n'a
pas d'index sur les valeurs, donc rien ne peut être trié ni filtré.
**Télécharger** peut enregistrer chaque ligne comme fichier CSV.

## Modifier une clé

Avec un accès **Modifier les lignes**, les valeurs d'une clé se modifient dans sa
grille :

- double-cliquez sur une cellule pour modifier un champ de hash, un élément de
  list, un string ou un score ;
- **Insérer une ligne** ajoute un champ, un élément de list ou un élément de
  set ;
- cochez des lignes et **Supprimer les lignes sélectionnées** supprime des champs
  et des éléments.

Ce que chaque type autorise est montré par la grille elle-même. Un élément ne
peut pas être retiré du milieu d'une list, et un stream ne peut pas être modifié
du tout.

Si quelqu'un a modifié la valeur après que vous l'avez lue, votre modification
est refusée plutôt que d'écraser la sienne. Rechargez et réessayez.

## Écrire des clés

Sélectionnez un dossier ou une clé dans l'arbre et ouvrez le menu d'actions :

- **Nouvelle clé string**, **Nouvelle clé hash**, **Nouvelle clé list**,
  **Nouvelle clé set**, **Nouvelle clé sorted set**, **Nouvelle clé stream**. Le
  nom que vous saisissez est ajouté au dossier où vous vous trouvez, donc `one`
  écrit dans `cache:` devient `cache:one`. Une collection s'écrit un élément, ou
  un `name=value`, par ligne. Une expiration peut être définie tout de suite. Un
  nom déjà utilisé est refusé, sauf si vous choisissez de le remplacer ;
- **Supprimer** retire une clé, après avoir demandé confirmation ;
- **Définir l'expiration** donne une durée de vie à une clé, et **Supprimer
  l'expiration** la retire.

## Copier vers l'extérieur

**Copiez** une clé, un dossier ou une base de données dans le catalogue et
**collez**-la dans un dossier d'une connexion de fichiers ou SSH : chacune devient
un fichier CSV. Plusieurs éléments cochés sont copiés ensemble, un fichier
chacun. Vous pouvez aussi exporter toutes les lignes d'une clé, d'un dossier ou
d'une base de données en CSV.

## Métriques

Une connexion Redis peut rapporter ses propres compteurs aux tableaux de bord :
mémoire, clients, commandes, succès et échecs, clés expirées et évincées, trafic
réseau et clés par base de données. Le propriétaire l'active dans la fenêtre
**Sources** de l'espace **Tableaux de bord**, et choisit la fréquence. La
disposition prête à l'emploi s'appelle **Serveur Redis**.

## Ce que Redis n'a pas ici

- Il n'y a pas de console de commandes : Redis prend des commandes plutôt que des
  instructions, et une console pour elles serait un shell sur le serveur.
- Une clé qui expire alors que son onglet est ouvert reste à l'écran jusqu'à ce
  que l'onglet soit relu.
- Les valeurs sont affichées comme du texte. Une clé qui contient une image
  s'affiche sous forme de caractères illisibles.
