# DuckDB

Un fichier de base de données DuckDB dans votre stockage personnel. Vous
parcourez ses schémas, tables et vues, lisez leurs lignes page par page, voyez
comment une table est construite et lisez le DDL que le fichier garde pour
elle.
Le fonctionnement général des connexions est décrit à la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Schémas, tables et vues, et leurs lignes triées et filtrées
- Colonnes, clés, contrôles et index d'une table, et les tables qu'elle cite
- Le DDL d'une relation, tel que le fichier le garde, avec ses index
- Listes, structs et maps, affichés en JSON
- Les résultats du SQL que vous écrivez, et le plan de DuckDB

## Ce que vous pouvez modifier

- Données des tables : cellules, blocs collés, lignes ajoutées ou supprimées
- Les données et la structure, par le SQL de la console

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Fichier de base de données** : le chemin du fichier dans votre stockage
  personnel, par exemple `data/shop.duckdb`. Déposez d'abord le fichier par une
  connexion **Fichiers**. Un chemin hors de votre stockage est refusé.
- **Créer le fichier s'il n'existe pas** : cochez-le pour commencer une base
  vide. Sans cela, un fichier absent échoue à la vérification, et un chemin mal
  saisi ne laisse pas de fichier vide derrière lui. Le dossier doit déjà
  exister.

Le fichier est ouvert à neuf pour chaque requête et refermé après, donc entre
deux requêtes votre propre DuckDB, un notebook ou un script peut l'ouvrir aussi.
Tant qu'un autre programme le tient ouvert, cette connexion dit que le fichier
est utilisé.

Un fichier écrit par un DuckDB plus récent que celui du serveur peut ne pas
s'ouvrir, et un fichier écrit par ce serveur, un DuckDB 2, peut ne pas s'ouvrir
dans DuckDB 1.

Ce qu'une connexion au fichier ne peut pas faire, quel que soit son contenu :
lire un fichier hors de votre stockage personnel, accéder au réseau, installer
ou charger une extension, ou déverser un gros tri sur le disque. Une vue du
fichier qui lit un fichier ailleurs est refusée à l'ouverture. Les fichiers de
votre stockage se nomment depuis sa racine avec `~/`, par exemple
`~/data/sales.parquet`.

## Le catalogue

- Le premier niveau est celui des schémas du fichier, dont `main`.
- Dans chacun se trouvent ses tables et vues. En cliquer une ouvre ses lignes
  dans un onglet.
- Une table indique à peu près combien de lignes elle contient, selon
  l'estimation de DuckDB, sans comptage.
- **Détails** indique combien de colonnes, d'index et de contraintes a une
  relation.
- **Voir le DDL** affiche l'instruction `CREATE TABLE` ou `CREATE VIEW` que
  garde le fichier, suivie des index de la table.
- DuckDB nomme lui-même les contraintes, par exemple `items_id_pkey`, même si
  l'instruction leur donnait un nom.

## Lire les lignes

Une table s'ouvre en grille, une page à la fois, triée et filtrée comme une
table PostgreSQL. Ce qu'une colonne propose dépend de son type : comparaisons
pour les nombres, dates et textes ; égal ou différent pour les UUID, énumérations
et intervalles ; contient et commence par pour le texte, le JSON, les listes et
les structs ; vide ou non vide pour toute colonne.

- Les pages suivent la clé primaire, sinon l'ordre dans lequel DuckDB garde les
  lignes. Une vue est dans l'ordre que DuckDB renvoie.
- Une liste, un struct ou une map ne peut pas être trié.
- Une valeur de filtre est lue par DuckDB comme le type de la colonne : une date
  comme `2026-01-02`, un instant avec son fuseau horaire, un décimal jusqu'au
  dernier chiffre. Une valeur que DuckDB ne peut pas lire ainsi est refusée.
- Un `%` ou un `_` saisi dans un filtre de texte est cherché tel quel. Les
  filtres de texte ignorent la casse.

Comment les valeurs sont affichées, telles que DuckDB les écrit :

- grands entiers et décimaux exactement ;
- un instant avec fuseau horaire en UTC ;
- les valeurs binaires en hexadécimal, comme `0xAA00` ;
- un intervalle comme `1 year 2 days 03:00:00` ;
- une liste, un struct, une map ou une union en JSON.

## Modifier les lignes

Avec l'accès **Modifier les lignes**, une table se modifie dans sa grille comme
une table PostgreSQL : double-cliquez sur une cellule, collez un bloc,
**Insérer une ligne**, cochez des lignes et **Supprimer les lignes
sélectionnées**.

- Une ligne est retrouvée par sa clé primaire. Une table sans clé accepte de
  nouvelles lignes et est sinon en lecture seule, car DuckDB déplace une ligne
  quand elle est modifiée et peut garder deux lignes identiques. Une vue est en
  lecture seule.
- Si quelqu'un a modifié une ligne après votre lecture, votre modification est
  refusée plutôt qu'écrite par-dessus la sienne. Rechargez et réessayez.
- Écrivez les valeurs comme la grille les montre : une date comme
  `2026-01-02`, un instant avec son fuseau horaire, le binaire comme `0x…`.
  DuckDB les lit selon le type de la colonne, et une valeur qu'il ne peut pas
  lire est refusée ; dans un bloc collé, les cellules refusées sont nommées et
  rien n'est écrit.
- Les listes, structs, maps et colonnes générées ne se modifient pas dans la
  grille ; changez-les avec du SQL dans la console.
- Une modification que refusent les clés, contrôles ou colonnes obligatoires de
  la table n'est pas faite, et la règle qui l'a refusée est indiquée.
- DuckDB ne peut pas modifier une clé ou une colonne unique d'une ligne à
  laquelle d'autres lignes font référence, même vers une valeur que personne
  n'a ; les autres colonnes de cette ligne se modifient.
- Une cellule d'une clé étrangère a une flèche qui ouvre la ligne qu'elle
  désigne, et **Ce qui pointe vers cette ligne** ouvre les lignes qui pointent
  ici.

## Console SQL

**Nouvelle requête** sous **Requêtes** dans la barre de gauche en lance une sur
la connexion, et **Ouvrir comme requête** au-dessus d'une table en lance une sur
cette table. Elle fonctionne comme la console PostgreSQL — lectures,
modifications validées aussitôt ou tenues dans une transaction **Manuel**,
**Expliquer**, complétion et mise en forme. DuckDB modifie la structure dans une
transaction, donc un `CREATE`, un `ALTER` ou un `DROP` fait partie de la
transaction qui l'entoure, et une suppression est d'abord essayée puis annulée
avant que la console vous pose la question.

- Les fichiers de votre stockage se lisent comme `~/…`, par exemple
  `SELECT * FROM '~/data/sales.parquet'`. Chargez-en un dans une table avec
  `INSERT INTO t SELECT * FROM '~/data/sales.csv'`.
- Les paramètres s'écrivent `$name`.
- Le schéma se choisit au-dessus de l'éditeur ; `USE` et `SET` ne sont pas
  exécutés.
- Non exécutés, chacun avec sa raison : `ATTACH`, `COPY`, `EXPORT` et
  `IMPORT DATABASE`, `INSTALL` et `LOAD`, `PREPARE`, et les secrets.
- Une instruction en échec dans une transaction maintenue y met fin : il ne
  reste que **Annuler**.
- Tant que vous maintenez une transaction, le fichier reste ouvert et aucun
  autre programme ne peut l'ouvrir.
- Dans une transaction maintenue, une suppression ne peut pas être essayée
  d'abord, faute de points de sauvegarde dans DuckDB ; exécutez-la en
  validation automatique.
- **Expliquer** montre le plan de DuckDB : ses opérateurs et les lignes qu'il
  prévoit.
- **Arrêter** et la limite de temps arrêtent une instruction là où elle en est.

## Ce que DuckDB n'a pas encore ici

- Changer la structure, les actions du catalogue, télécharger toutes les
  lignes, les sauvegardes et la copie de tables. Ils viendront plus tard.
- Un fichier sur un serveur SSH, ou dans une autre connexion, ne peut pas être
  ouvert comme base de données.
