# SQLite

Un fichier de base de données SQLite dans votre stockage personnel. Vous
parcourez ses tables et ses vues, lisez et modifiez leurs lignes page par page,
voyez comment une table est construite, lisez le DDL que le fichier garde pour
elle et exécutez du SQL dans une console. Le fonctionnement des connexions en
général est décrit sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Tables, vues et tables virtuelles, et leurs lignes triées et filtrées
- Les colonnes, clés, vérifications et index d'une table, et ses tables cibles
- Le DDL d'une relation, tel que le fichier le garde, avec index et déclencheurs
- Les résultats du SQL que vous écrivez, et le plan de SQLite pour une requête
- Toutes les lignes correspondantes, téléchargées dans un fichier
- Ce que le fichier dit de lui-même : sa structure, son intégrité, les clés
  rompues, les déclencheurs, et ce qu'offre le SQLite de ce serveur
- Où mène la clé étrangère d'une ligne, et ce qui pointe vers elle

## Ce que vous pouvez modifier

- Les données : cellules modifiées, blocs collés, lignes ajoutées et supprimées
- Les colonnes, index, clés uniques et clés étrangères
- De nouvelles tables, conçues objet par objet ou créées à partir de lignes
- Tables et vues : renommer, supprimer
- Des tables copiées avec leur structure, vers un autre fichier SQLite ou ici
- Le fichier entier, sauvegardé et restauré
- Les données et la structure, par du SQL dans la console

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Fichier de base de données** : le chemin du fichier dans votre stockage
  personnel, par exemple `data/shop.db`. Déposez d'abord le fichier là, via une
  connexion **Fichiers**. Un chemin hors de votre stockage est refusé.
- **Créer le fichier s'il n'existe pas** : cochez-le pour commencer avec une
  base vide. Sans lui, un fichier absent fait échouer la vérification, si bien
  qu'un chemin mal saisi ne laisse pas de fichier vide derrière lui. Le dossier
  doit déjà exister.

Un fichier de base que vous voyez déjà dans une connexion **Fichiers** peut
être connecté depuis là : **Connecter en SQLite** remplit cette fenêtre pour
vous.

Le fichier est rouvert à chaque requête, si bien qu'un fichier remplacé via
**Fichiers** est lu tel qu'il est maintenant.

Ce qu'une connexion au fichier ne peut pas faire, quoi que contienne le
fichier : ouvrir un second fichier (`ATTACH`, `VACUUM INTO`), charger une
extension ou atteindre quoi que ce soit d'autre sur le serveur. N'importe qui
peut téléverser un fichier, donc une vue ou un déclencheur qu'il contient ne
peut pas non plus appeler une fonction à effets de bord.

## Le catalogue

- Le premier niveau est `main`, l'unique schéma du fichier.
- Il contient ses tables, ses vues et ses tables virtuelles. Un clic ouvre
  leurs lignes dans un onglet.
- Les tables propres à SQLite (`sqlite_schema`, `sqlite_sequence`,
  `sqlite_stat1`) et celles qu'une table virtuelle tient pour elle-même, comme
  celles d'un index plein texte, sont marquées comme tables système.
- Une table n'indique à peu près combien de lignes elle contient qu'après un
  `ANALYZE` sur le fichier. Rien ne compte les lignes.
- **Détails** indique combien de colonnes, d'index et de contraintes compte une
  relation.
- **Afficher le DDL** montre l'instruction `CREATE TABLE` ou `CREATE VIEW` que
  garde le fichier, suivie des index et des déclencheurs de la table.
- Une table virtuelle faite avec un module que ce serveur n'a pas est listée,
  et le dit quand on l'ouvre.
- **Système**, après `main`, est une section de rapports (voir **Rapports**
  plus bas).
- La recherche de l'en-tête trouve les tables et les vues par leur nom et par
  leurs colonnes.

## Lire les lignes

Une table s'ouvre en grille, une page à la fois, triée et filtrée comme une
table PostgreSQL. Toutes les colonnes se trient. Ce qu'offre une colonne dépend
du type avec lequel elle a été déclarée : comparaisons pour les nombres, les
dates et le texte ; contient et commence par pour le texte ; vide ou non vide
pour toutes les colonnes.

- Les pages suivent la clé primaire, ou sinon l'ordre dans lequel les lignes
  ont été écrites (le `rowid`). Une vue vient dans l'ordre que SQLite renvoie.
- Un `%` ou un `_` saisi dans un filtre de texte est cherché tel quel. Les
  filtres de texte ignorent la casse des lettres latines.
- Une colonne déclarée sans type est filtrée comme du texte.

Comment les valeurs sont montrées :

- une valeur comme ce qu'elle est, quoi qu'en dise sa colonne : SQLite laisse
  une colonne `INTEGER` contenir du texte, et le texte est montré comme du
  texte ;
- les valeurs binaires en hexadécimal, comme `0x00FF`, dans toute colonne ;
- une colonne `BOOLEAN` comme `true` ou `false` là où elle contient 0 ou 1 ;
- un texte qui n'est pas de l'UTF-8 valide en hexadécimal, plutôt qu'avec des
  caractères qui n'y sont pas ;
- les grands entiers exactement.

## Modifier les lignes

Avec l'accès **Modifier les lignes**, une table se modifie dans sa grille comme
une table PostgreSQL : double-cliquer sur une cellule, coller un bloc,
**Insérer une ligne**, cocher des lignes et **Supprimer les lignes
sélectionnées**. Les vues, les tables virtuelles et les tables propres à SQLite
sont en lecture seule, et une colonne générée est calculée plutôt qu'écrite.

- Une ligne est retrouvée par sa clé primaire, ou par son `rowid` quand la
  table n'en a pas.
- Si quelqu'un a modifié une ligne après que vous l'avez lue, dans n'importe
  quelle colonne, votre modification est refusée plutôt qu'écrite par-dessus la
  sienne. Rechargez et réessayez.
- Écrivez les valeurs comme la grille les montre : le binaire en `0x…` dans une
  colonne `BLOB`, `true` ou `false` dans une colonne `BOOLEAN`. Une colonne sans
  type garde un nombre comme un nombre. Ce que reçoit toute autre colonne,
  SQLite le stocke converti comme son type l'indique.
- Une table `STRICT` refuse une valeur du mauvais type avant que rien ne soit
  écrit, et les cellules qui contiennent de telles valeurs sont nommées. Rien
  d'un bloc collé n'arrive tant que tout ne peut pas arriver.
- Une modification que refusent les clés, les vérifications ou les colonnes
  obligatoires de la table n'est pas faite, et elle dit quelle règle l'a
  refusée. Les clés étrangères du fichier sont appliquées.
- Une cellule d'une clé étrangère porte une flèche qui ouvre la ligne vers
  laquelle elle pointe, et **Ce qui pointe vers cette ligne** ouvre les lignes
  qui pointent ici.

## Modifier la structure

**Structure** d'une table la modifie comme une table PostgreSQL : ajouter,
renommer et supprimer une colonne, définir ou retirer sa valeur par défaut,
exiger une valeur ou ne plus l'exiger, changer son type, ajouter et supprimer
des index, des clés uniques et des clés étrangères.

- SQLite lui-même ne sait qu'ajouter une colonne qui peut rester vide et en
  renommer une. Pour tout le reste, la table est reconstruite comme le décrit
  la documentation de SQLite : une nouvelle table, les lignes copiées avec leur
  `rowid`, l'ancienne remplacée, ses index et déclencheurs recréés. Ce que la
  modification ne touche pas — `AUTOINCREMENT`, `DEFERRABLE`, les commentaires
  — reste tel qu'il est écrit.
- Une modification que les lignes contredisent déjà n'est pas faite, et le
  nombre est montré : lignes sans valeur, valeurs qui se répètent, lignes qui
  ne pointent vers rien.
- Une colonne typée accepte n'importe quelle valeur dans SQLite, donc un
  changement de type n'est refusé que dans une table `STRICT`, avec le nombre
  de valeurs qu'elle ne peut pas contenir.
- Supprimer une colonne supprime les clés et les index qui portent sur elle.
  Une vérification ou une vue qui lit la colonne refuse la suppression, et dit
  laquelle.
- Les types proposés sont ceux de SQLite : texte, entier, virgule flottante,
  nombre, booléen, date, date et heure, JSON, UUID et binaire. Une table
  `STRICT` se voit proposer les siens : texte, entier, virgule flottante,
  binaire et toute valeur.
- SQLite construit une seule sorte d'index, un B-arbre, et nomme ce qu'il crée
  d'après la table et ses colonnes.

## Créer une table

**Créer une table** dans le menu d'actions de `main` ouvre le concepteur de
tables, comme pour PostgreSQL. Le plan est un `CREATE TABLE` et un
`CREATE INDEX` par index, exécutés ensemble : la table est créée entière ou pas
du tout.

- Une colonne d'identité est le numéro de ligne propre à SQLite : un entier qui
  est toute la clé primaire, écrit `INTEGER PRIMARY KEY AUTOINCREMENT`. Elle
  peut commencer n'importe où, compte de un en un et accepte une valeur que vous
  y écrivez.
- Ce que SQLite n'a pas est signalé sur l'objet qui le demande avant que vous
  puissiez examiner le plan : une table non journalisée ou partitionnée, une
  clé unique vérifiée à la validation, les valeurs nulles triées en premier ou
  en dernier, des colonnes supplémentaires portées par un index.
- SQLite a ce qui manque à MySQL : un index sur une partie des lignes, une clé
  étrangère vérifiée à la validation, `SET DEFAULT` et un index sur une
  expression.
- Les commentaires ne sont pas conservés ; le plan le dit.
- Les collations sont celles de SQLite : `BINARY`, `NOCASE` et `RTRIM`.
- Des lignes conservées comme table, ou un fichier chargé dans une table,
  arrivent avec la table en une fois.

## Rapports

**Système** dans le catalogue contient huit rapports. Ils se lisent comme des
tables et peuvent être triés, filtrés, téléchargés et mis en graphique.
**Afficher l'instruction** montre le SQL qu'exécute un rapport.

- **Fichier** : la taille et le nombre de pages, la taille du fichier, les
  pages libres, l'encodage, le mode de journal, l'auto-vacuum et les numéros de
  version que garde le fichier.
- **Intégrité** : la vérification rapide de chaque page par SQLite : `ok`, ou
  ce qui est endommagé. Elle lit tout le fichier, donc elle n'est lue qu'à
  l'ouverture.
- **Clés étrangères rompues** : les lignes dont la clé ne pointe vers rien,
  écrites par un programme qui ne les appliquait pas.
- **Déclencheurs**, avec leurs définitions.
- **Fonctions**, **Modules** et **Collations** qu'offre le SQLite de ce
  serveur, et les **Options de compilation** avec lesquelles il a été construit.

## Actions du catalogue

- **Renommer** une table ou une vue. Ce qui renvoie à une table la suit. Une
  vue est recréée sous le nouveau nom ; une vue qui la lit sous son ancien nom
  refuse le renommage et est nommée.
- **Supprimer** une relation ou plusieurs ensemble. La suppression est d'abord
  essayée puis annulée, si bien que la question montre ce qu'elle ferait : les
  déclencheurs qui partent avec, les tables qui pointent vers elle, les vues qui
  la lisent. Si une table qui pointe vers elle a encore des lignes et ne
  supprime pas en cascade, la suppression est refusée pour cette raison. Des
  tables qui pointent l'une vers l'autre peuvent être supprimées ensemble.
- **Charger depuis un CSV** crée dans `main` une table à partir d'un fichier,
  chaque colonne en `TEXT`.
- **Modèle en code** écrit `main` ou une sélection pour un ORM ou un diagramme.

## Copier des tables

**Copiez** des tables dans le catalogue et **Collez**-les dans `main` d'une
autre connexion SQLite, ou de celle-ci. Elles arrivent avec leurs colonnes
telles que le fichier les écrit, leurs clés, vérifications, index et options
comme `STRICT` ; la fenêtre demande les mêmes choses que pour PostgreSQL,
montre chaque instruction et n'exécute rien avant **Copier**.

- Les déclencheurs restent derrière, nommés dans la fenêtre. Les vues et les
  tables virtuelles ne sont pas copiées ainsi.
- Un index est nommé d'après la nouvelle table, car deux index d'un même
  fichier ne peuvent pas partager un nom.
- La copie est une seule transaction : les tables, leurs lignes et leurs index
  arrivent ensemble ou pas du tout. Une ligne dont la clé étrangère ne pointe
  vers rien dans la copie la fait échouer à la fin, et rien ne reste.

Les lignes collées dans une connexion d'un autre type suivent le chemin des
lignes de n'importe quelle table.

## Sauvegardes

**Sauvegardes**, dans le menu d'actions du catalogue, fonctionne comme pour
PostgreSQL, pour le fichier qu'ouvre la connexion.

- La sauvegarde est une copie du fichier faite par SQLite lui-même ; elle est
  donc entière même si quelqu'un écrit dans le fichier au même moment.
- **Restaurer** remplace tout le contenu du fichier par la sauvegarde. Un
  fichier qui n'est pas une base SQLite, ou que SQLite juge endommagé, est
  refusé avant que rien ne soit écrit.

## Console SQL

**Nouvelle requête** sous **Requêtes** dans la barre de gauche en lance une sur
la connexion, et **Ouvrir comme requête** au-dessus d'une table en lance une sur
cette table. Elle fonctionne comme la console PostgreSQL — lectures,
modifications validées aussitôt ou tenues dans une transaction **Manuel**,
**Expliquer**, complétion et mise en forme. SQLite modifie la structure dans une
transaction, donc un `CREATE`, un `ALTER` ou un `DROP` fait partie de la
transaction qui l'entoure, peut être tenu dans une transaction manuelle, et est
d'abord essayé puis annulé avant que la console vous pose la question.

- Le schéma est toujours `main`.
- Les paramètres s'écrivent `:name`.
- `ANALYZE`, `VACUUM` et `REINDEX` s'exécutent seuls, hors transaction.
- Un `PRAGMA` qui rapporte quelque chose, comme `PRAGMA table_info(items)` ou
  `PRAGMA integrity_check`, est une lecture. Un `PRAGMA` qui définit une valeur
  n'est pas exécuté.
- Les clés étrangères que déclare le fichier sont appliquées, ce que SQLite ne
  fait de lui-même que lorsqu'un programme le lui demande.
- Les déclencheurs ne se modifient pas depuis la console, et aucun autre
  fichier ne peut y être ouvert (`ATTACH`).
- **Expliquer** montre le plan de SQLite : une ligne par étape, sans coûts,
  puisque SQLite n'en donne pas.
- **Arrêter** et la limite de temps arrêtent une instruction là où elle en est.
- Une instruction en échec dans une transaction que vous tenez laisse la
  transaction ouverte.

## Ce que SQLite n'a pas encore ici

- Un fichier sur un serveur SSH, ou à l'intérieur d'une autre connexion, ne
  peut pas être ouvert comme base de données.
