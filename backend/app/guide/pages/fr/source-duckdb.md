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

## Ce que DuckDB n'a pas encore ici

- Modifier les lignes, la console SQL, changer la structure, les actions du
  catalogue, télécharger toutes les lignes, les sauvegardes et la copie de
  tables. Ils viendront plus tard.
- Une table sans clé primaire restera en lecture seule même alors : DuckDB
  déplace une ligne quand elle est modifiée, et rien d'autre ne la désigne.
- Un fichier sur un serveur SSH, ou dans une autre connexion, ne peut pas être
  ouvert comme base de données.
