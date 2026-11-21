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
- Des rapports : taille du fichier, séquences, types, macros, fonctions
- Toutes les lignes d'une table, d'une vue ou d'un rapport, téléchargées

## Ce que vous pouvez modifier

- Données des tables : cellules, blocs collés, lignes ajoutées ou supprimées
- Les colonnes, index et clés uniques
- De nouvelles tables, conçues objet par objet ou créées à partir de lignes
- Schémas créés et supprimés ; tables et vues renommées et supprimées
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

## Modifier la structure

**Structure** d'une table la modifie comme une table PostgreSQL : ajouter,
renommer et supprimer une colonne, définir ou retirer sa valeur par défaut,
exiger une valeur ou ne plus l'exiger, changer son type, ajouter et supprimer
des index, ajouter une clé unique.

- DuckDB fait chaque modification sur place, dans une transaction ; rien n'est
  reconstruit.
- Une modification que les lignes contredisent déjà n'est pas faite, et le
  nombre est affiché : lignes sans valeur, valeurs qui ne se convertiraient pas
  dans le nouveau type, valeurs qui se répètent.
- Une valeur par défaut est vérifiée selon le type de la colonne avant d'être
  définie.
- DuckDB ne peut pas ajouter de clé étrangère ni de contrôle à une table
  existante, ni supprimer l'une de ses contraintes, clé primaire comprise.
  Copiez plutôt la table dans une table conçue comme vous le voulez.
- Une table qui a son propre index, ou vers laquelle pointe la clé étrangère
  d'une autre table, n'accepte qu'une nouvelle colonne, une valeur par défaut
  et un nouvel index. Renommer, supprimer ou changer le type d'une colonne,
  exiger une valeur et ajouter une clé unique sont refusés.
- DuckDB renomme et supprime une colonne sans regarder les vues qui la lisent ;
  chaque vue est donc relue après la modification, et une vue que la
  modification casserait la refuse en se nommant.
- Ce que DuckDB refuse lui-même, comme supprimer une colonne couverte par un
  index, est dit avec les mots de DuckDB.
- Les types proposés sont ceux de DuckDB : texte, entiers de quatre tailles,
  virgule flottante, décimal, booléen, date, heure, date et heure avec ou sans
  fuseau horaire, intervalle, UUID, JSON et binaire.
- DuckDB construit un seul type d'index, un arbre radix adaptatif, nommé
  d'après la table et ses colonnes. DuckDB nomme lui-même les contraintes.

## Créer une table

**Créer une table** dans le menu d'actions d'un schéma ouvre le concepteur de
tables, comme pour PostgreSQL. Le plan est un `CREATE TABLE`, un `CREATE INDEX`
par index et les commentaires, exécutés ensemble : la table est créée entière
ou pas du tout.

- Une colonne d'identité est une séquence à elle, `<table>_<colonne>_seq`,
  créée avant la table, et la valeur par défaut de la colonne en prend la
  valeur suivante. Elle peut commencer n'importe où et avancer de n'importe
  quel pas. Elle accepte une valeur que vous y écrivez, elle ne peut donc pas
  être ALWAYS.
- Une colonne générée est calculée à chaque lecture ; une colonne demandée
  stockée est créée ainsi, avec un avertissement.
- Ce que DuckDB n'a pas est signalé sur l'objet qui le demande avant que vous
  puissiez relire le plan : une table non journalisée ou partitionnée, une clé
  étrangère qui se propage en cascade, met à null ou met une valeur par défaut,
  ou pointe vers un autre schéma, une clé vérifiée à la validation, un index
  sur une partie des lignes ou portant des colonnes supplémentaires.
- Une valeur par défaut est vérifiée selon le type de sa colonne pendant
  l'établissement du plan.
- Les noms de contraintes donnés ne sont pas conservés ; DuckDB nomme lui-même
  les contraintes.
- Les commentaires de la table et de ses colonnes sont conservés.
- Les collations sont celles de DuckDB : `NOCASE`, `NOACCENT` et `NFC`.
- Des lignes gardées comme table, ou un fichier chargé dans une table, arrivent
  avec la table d'un seul coup. Une valeur que DuckDB ne peut pas lire dans le
  type de sa colonne laisse la table non créée.

## Rapports

**Système** dans le catalogue contient cinq rapports. Ils se lisent comme des
tables et peuvent être triés, filtrés, téléchargés et tracés. **Afficher
l'instruction** montre le SQL qu'exécute un rapport.

- **Base de données** : la version de DuckDB, la taille du fichier, ses blocs
  utilisés et libres, et le journal d'écriture anticipée.
- **Séquences**, avec leur départ, leur pas et leurs bornes. Une identité créée
  par le concepteur de tables en est une.
- **Types** propres au fichier : enums, structs et autres noms pour un type.
- **Macros** : fonctions écrites en SQL et conservées dans le fichier, avec
  leurs paramètres et leur corps.
- **Fonctions** intégrées à DuckDB, et le nombre de signatures de chacune.
- Les réglages du moteur ne sont pas affichés : ils nomment des dossiers du
  serveur, et ils sont fixes ici.

## Actions du catalogue

- **Nouveau schéma** en haut de la connexion. **Supprimer le schéma** supprime
  tout schéma sauf `main` ; un schéma qui contient quelque chose demande
  **Supprimer aussi tout son contenu**, et la question compte ce qui part. Un
  schéma ne peut pas être renommé dans DuckDB.
- **Renommer** une table ou une vue. Chaque vue est ensuite relue, et une vue
  qui lisait l'ancien nom refuse le renommage et est nommée. DuckDB ne renomme
  pas une table qui a son propre index ou vers laquelle pointe la clé d'une
  autre table.
- Une table qui a sa propre clé étrangère n'est pas renommée : DuckDB garderait
  l'ancien nom dans la table qu'elle cite, qui ne pourrait alors ni supprimer
  ses lignes ni être supprimée.
- **Supprimer** une relation ou plusieurs ensemble. La suppression est d'abord
  essayée puis annulée, si bien que la question nomme les vues qui cesseraient
  de fonctionner. Une table vers laquelle pointe la clé d'une autre est
  refusée, sauf si cette autre est supprimée avec elle. Une séquence dont
  seules les tables supprimées tirent des valeurs, comme celle d'une identité,
  part avec elles.
- **Charger depuis un CSV** crée dans le schéma une table à partir d'un
  fichier, chaque colonne en `VARCHAR`.
- **Modèle en code** écrit un schéma ou une sélection pour un ORM ou un
  diagramme.
- Rien ne passe d'un schéma à l'autre : DuckDB ne le peut pas.

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

- La copie de tables et les sauvegardes. Elles viendront plus tard.
- Un fichier sur un serveur SSH, ou dans une autre connexion, ne peut pas être
  ouvert comme base de données.
