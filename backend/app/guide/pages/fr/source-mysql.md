# MySQL

Un serveur MySQL ou MariaDB. Vous parcourez ses bases de données, lisez les
tables et les vues page par page, voyez comment une table est construite, lisez
son DDL tel que le serveur l'écrit et exécutez du SQL dans une console. Le
fonctionnement des connexions en général est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Les bases de données, tables et vues, et leurs lignes triées et filtrées sur
  le serveur
- Les colonnes, clés, vérifications et index d'une table, et les tables
  auxquelles elle fait référence
- Où mène la clé étrangère d'une ligne, et ce qui pointe vers elle
- Le DDL d'une relation, tel que le serveur l'écrit
- La taille d'une table, quand elle a été créée et quand on y a écrit pour la
  dernière fois
- Les résultats du SQL que vous écrivez, et le plan du serveur pour une requête
- Toutes les lignes correspondantes, téléchargées dans un fichier
- Ce que fait le serveur : processus, variables, état, utilisateurs, routines,
  déclencheurs, événements et moteurs

## Ce que vous pouvez modifier

- Les données d'une table : modifier des cellules, coller des blocs, insérer et
  supprimer des lignes
- Les colonnes, index, clés uniques et clés étrangères
- De nouvelles tables, conçues objet par objet ou faites à partir de lignes
- Les données et la structure, par du SQL dans la console
- Ce qu'une autre connexion exécute : son instruction peut être arrêtée, ou la
  connexion fermée
- Les bases de données : les créer et les supprimer
- Les tables et les vues : renommer, déplacer une table vers une autre base de
  données, supprimer
- Des tables copiées avec leur structure vers une autre connexion MySQL ou
  MariaDB
- Des sauvegardes de la base de données de la connexion, et la base remise en
  place à partir de l'une d'elles

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port**, 3306 sauf indication contraire du serveur ;
- **Authentification** : un utilisateur et un mot de passe, ou un utilisateur
  sans mot de passe ;
- **Base de données** : là où s'ouvre le catalogue. Elle peut rester vide.
  Chaque base de données que l'utilisateur peut voir figure au catalogue dans
  tous les cas.

Une chaîne de connexion comme `mysql://ann@db.example.com:3306/sales` collée
dans **URL** remplit ces champs ; `mariadb://` se lit de la même façon. Un mot de
passe présent dans la chaîne collée passe dans le champ du mot de passe et
quitte la chaîne.

La connexion est chiffrée quand le serveur propose TLS, et reste en clair sinon.
Le certificat du serveur n'est pas vérifié.

MySQL 8.0.16 et plus récent et MariaDB 10.6 et plus récent sont pris en charge.
Un serveur plus ancien est refusé lors de la vérification de la connexion, avec
sa version indiquée.

## Le catalogue

- Le premier niveau, ce sont les bases de données. Celle que nomme la connexion
  vient en premier ; `mysql`, `information_schema`, `performance_schema` et
  `sys` appartiennent au serveur et sont marquées comme telles.
- Dans une base de données se trouvent ses tables et ses vues. Appuyer sur
  l'une ouvre ses lignes dans un onglet.
- Une table indique à peu près combien de lignes elle contient. Ce nombre est
  l'estimation du serveur, que MySQL peut garder jusqu'à un jour, et rien ne
  compte les lignes.
- **Détails** indique combien de colonnes, d'index et de contraintes compte une
  relation, sa taille, et quand elle a été créée et modifiée pour la dernière
  fois.
- **Afficher le DDL** montre l'instruction `CREATE TABLE` ou `CREATE VIEW` que
  donne le serveur lui-même.
- **Système**, après les bases de données, est une section de rapports que le
  serveur donne sur lui-même (voir **Rapports** plus bas).
- La recherche dans l'en-tête trouve les bases de données et les tables par leur
  nom, et les tables par leurs colonnes et par les commentaires sur elles et sur
  leurs colonnes.

## Lire les lignes

Une table s'ouvre dans une grille, page par page, triée et filtrée par le
serveur comme une table PostgreSQL. Ce qu'une colonne propose dépend de son
type : comparaisons pour les nombres, les dates et le texte ; « contient » et
« commence par » pour le texte ; égalité et « l'une d'une liste » pour les
énumérations ; vide ou non vide pour toute colonne.

- Les pages suivent la clé primaire. Une table sans clé primaire suit une clé
  unique sur des colonnes qui ne peuvent pas être vides, l'ordre dans lequel
  InnoDB garde une telle table. Une table sans l'une ni l'autre, et une vue,
  sont dans l'ordre que renvoie le serveur.
- Un `%` ou un `_` saisi dans un filtre de texte est cherché tel quel.
- **Télécharger** demande **Page actuelle** ou **Toutes les lignes
  correspondantes**. Chaque ligne est lue sur le serveur au fur et à mesure
  qu'elle est écrite dans le fichier, dans l'ordre de la page et avec ses
  filtres.

Comment les valeurs sont affichées :

- `DECIMAL` et les grands entiers non signés exactement tels qu'ils sont
  stockés ;
- `BIT` comme un nombre ;
- `TIMESTAMP` en UTC, avec `+00:00`. `DATETIME` tel qu'il a été écrit, sans
  fuseau horaire, puisqu'il n'en a pas ;
- `TIME` tel que MySQL l'écrit, ce qui peut être négatif ou dépasser 24 heures ;
- une date nulle comme `0000-00-00` telle que le serveur l'écrit ;
- la géométrie en texte, comme `POINT(1 2)` ;
- les colonnes binaires en hexadécimal, comme `0x00FF`.

## Modifier les lignes

Avec l'accès **Modifier les lignes**, une table se modifie dans sa grille comme
une table PostgreSQL : double-cliquer sur une cellule, coller un bloc,
**Insérer une ligne**, cocher des lignes et **Supprimer les lignes
sélectionnées**.

- Une ligne est retrouvée par sa clé primaire, ou par une clé unique sur des
  colonnes qui ne peuvent pas être vides. Une ligne d'une table sans l'une ni
  l'autre est retrouvée par toutes ses valeurs, et une seule ligne est modifiée
  à la fois : des lignes identiques en chaque valeur sont interchangeables. Deux
  lignes qui ne diffèrent que par une colonne à virgule flottante, JSON ou de
  géométrie ne peuvent pas être distinguées, et une modification de l'une est
  refusée pour cette raison.
- Si quelqu'un a modifié une ligne après que vous l'avez lue, dans n'importe
  quelle colonne, votre modification est refusée au lieu d'écraser la sienne.
  Rechargez et réessayez.
- Une valeur que la colonne ne peut pas contenir est refusée avant toute
  écriture, et les cellules qui contiennent de telles valeurs sont nommées. Rien
  d'un bloc collé n'arrive tant que tout ne peut pas arriver.
- Écrivez les valeurs comme la grille les montre : le binaire en `0x…`, la
  géométrie en WKT comme `POINT(1 2)`, un `TIMESTAMP` avec son décalage.
- Une cellule d'une clé étrangère porte une flèche qui ouvre la ligne qu'elle
  désigne, et **Ce qui pointe vers cette ligne** ouvre les lignes qui pointent
  ici, dans cette base de données ou une autre du serveur.

## Modifier la structure

**Structure** d'une table la modifie comme une table PostgreSQL : ajouter,
renommer et supprimer une colonne, définir ou retirer sa valeur par défaut,
exiger une valeur ou ne plus l'exiger, changer son type, ajouter et supprimer
des index, des clés uniques et des clés étrangères.

- Tout le reste d'une colonne — sa valeur par défaut, son commentaire, son jeu
  de caractères, AUTO_INCREMENT — est conservé quand son type ou sa nullabilité
  change.
- Une modification que les lignes contredisent déjà n'est pas faite, et le
  nombre est affiché : lignes sans valeur, valeurs qui se répètent, lignes qui
  ne pointent vers rien, valeurs que le nouveau type ne peut pas contenir. MySQL
  ne peut compter ces dernières qu'après avoir tenté la modification et été
  refusé ; rien n'est modifié dans un cas comme dans l'autre.
- Les types proposés sont ceux de MySQL : texte, texte long, entier, grand
  entier, décimal, virgule flottante, booléen en 0 ou 1, date, date et heure,
  horodatage, JSON, et un UUID en texte.
- Les index sont en arbre B, plein texte (colonnes de texte seulement) ou
  spatiaux (une colonne de géométrie qui exige une valeur). MySQL nomme lui-même
  un nouvel index ou une nouvelle clé.
- Une clé unique et son index ne font qu'un dans MySQL ; supprimez-la en tant
  que clé.
- `SET DEFAULT` n'est pas proposé pour une clé étrangère : InnoDB ne l'exécute
  pas.

## Créer une table

**Créer une table** dans le menu d'actions d'une base de données ouvre le
concepteur de tables, comme pour PostgreSQL. Le plan est un seul `CREATE TABLE`
contenant chaque clé, vérification, clé étrangère et index, de sorte que la
table est créée entière ou pas du tout.

- Ce que MySQL n'a pas est signalé sur l'objet qui le demande, avant que vous
  puissiez relire le plan : une clé différable, des colonnes supplémentaires
  portées par un index, un index sur une partie des lignes, les valeurs nulles
  rangées en premier ou en dernier, une table non journalisée ou partitionnée.
- Une colonne d'identité est AUTO_INCREMENT : une par table, en tête d'une clé,
  avec une valeur de départ mais sans pas qui lui soit propre.
- Une clé primaire s'appelle toujours PRIMARY.
- Les lignes conservées en table, ou un fichier chargé dans une table, sont
  vérifiés par rapport aux types choisis avant la création de la table ; s'ils
  sont malgré tout refusés, la nouvelle table est de nouveau supprimée.

## Console SQL

**Nouvelle requête** sous **Requêtes** dans la barre latérale gauche en démarre
une sur la connexion, et **Ouvrir comme requête** au-dessus d'une table en
démarre une sur cette table. Elle fonctionne comme la console PostgreSQL —
lectures, modifications validées immédiatement ou gardées dans une transaction
**Manuel**, **Expliquer**, complétion et mise en forme — avec ces différences :

- La base de données choisie au-dessus de l'éditeur est celle par défaut, comme
  `USE` la rendrait ; une base de données à la fois.
- Les paramètres s'écrivent `:name`. Chaque valeur est envoyée en texte, donc un
  nombre dont le serveur a besoin en tant que nombre, comme après `LIMIT`, ne
  peut pas être un paramètre.
- Un changement de structure — `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME` —
  s'exécute seul. MySQL le valide immédiatement, avec tout ce qui le précède, il
  ne peut donc pas partager une exécution avec d'autres instructions, ni
  s'exécuter dans une transaction que vous tenez, ni être essayé d'abord. La
  console demande avant d'en exécuter un, et le dit.
- Une instruction qui échoue dans une transaction que vous tenez laisse la
  transaction ouverte ; un interblocage la termine.
- **Arrêter** et la limite de temps terminent une instruction par `KILL QUERY`.
- Les utilisateurs, les droits, les routines, les déclencheurs et les événements
  ne se modifient pas depuis la console. `LOAD DATA`, `SELECT … INTO OUTFILE` et
  `CALL` ne sont pas exécutés.

## Rapports

**Système** dans le catalogue contient huit rapports sur le serveur. Ils se
lisent comme des tables, et peuvent être triés, filtrés, téléchargés et
représentés en graphique. **Afficher l'instruction** montre le SQL qu'exécute un
rapport.

- **Processus** : les connexions ouvertes et ce que chacune exécute. Chaque ligne
  propose **Annuler la requête**, qui arrête l'instruction et garde la
  connexion, et **Arrêter**, qui ferme la connexion. Le rapport se relit tout
  seul toutes les cinq secondes.
- **Variables** : chaque paramètre global du serveur.
- **État** : les compteurs que le serveur tient depuis son démarrage. Il se
  relit tout seul toutes les dix secondes.
- **Utilisateurs** : les comptes autorisés à se connecter, et depuis quels
  hôtes. **Nouvel utilisateur** au-dessus des lignes en crée un : un nom, l'hôte
  d'où il peut se connecter (`%` pour n'importe où) et un mot de passe. Il ne
  reçoit rien, ou, si c'est coché, la lecture de la base de données de la
  connexion. Seul le propriétaire de la connexion dispose de cette commande.
- Les **Routines** et les **Déclencheurs** hors des bases de données du serveur
  lui-même, et les **Événements** que son planificateur exécute.
- **Moteurs** : les moteurs de stockage que propose le serveur, et celui par
  défaut.

Un rapport ne montre que ce que l'utilisateur de la connexion peut voir : un
utilisateur sans le droit `PROCESS` ne voit que ses propres connexions, et
**Utilisateurs** est refusé à qui ne peut pas lire la base de données `mysql`.

## Actions du catalogue

- **Nouvelle base de données**, au sommet du catalogue.
- **Supprimer la base de données** demande d'abord. Une base de données qui
  contient quelque chose n'est supprimée qu'avec **Supprimer aussi tout son
  contenu** coché, et ce qu'elle contient est compté avant que vous ne
  confirmiez.
- **Renommer** une table ou une vue. Les clés étrangères qui pointent vers une
  table la suivent.
- **Déplacer vers une base de données** déplace une table. Une vue, et une table
  avec des déclencheurs, restent dans leur base de données.
- **Supprimer** une relation ou plusieurs ensemble. Une table à laquelle une
  table hors de la sélection fait référence n'est pas supprimée, et les tables
  qui y font référence sont nommées. Sur MySQL, les vues qui lisent une table
  supprimée sont nommées aussi.
- **Charger depuis un CSV** fait une table d'un fichier, chaque colonne en
  `TEXT`.
- **Modèle en code** écrit une base de données ou une sélection pour un ORM ou
  un diagramme.

Les changements de structure ne sont pas répétés d'abord, comme sur PostgreSQL :
MySQL les valide immédiatement.

## Copier des tables

**Copiez** des tables dans le catalogue et **Collez**-les dans une base de
données d'une autre connexion MySQL ou MariaDB, ou de celle-ci. Elles arrivent
avec leurs colonnes, clés, index, vérifications et options ; la fenêtre demande
les mêmes choses que sur PostgreSQL, montre chaque instruction et n'exécute rien
avant **Copier**.

- Les déclencheurs restent en arrière, nommés dans la fenêtre. Les vues et les
  tables partitionnées ne sont pas copiées ainsi.
- Les tables sont créées d'abord et les lignes arrivent ensuite. Si la copie
  échoue ou est arrêtée, les tables qu'elle a créées sont de nouveau supprimées.
- MariaDB utilise une collation que MySQL n'a pas, donc une table copiée de
  MariaDB vers MySQL peut être refusée ; la fenêtre dit quelle étape l'a
  refusée.

Les lignes collées dans une connexion d'un autre type suivent le chemin des
lignes de n'importe quelle table.

## Sauvegardes

**Sauvegardes**, dans le menu d'actions du catalogue, fonctionne comme sur
PostgreSQL, pour la base de données que nomme la connexion. Une connexion qui
ne nomme aucune base de données ne s'en voit pas proposer.

- La sauvegarde est un fichier SQL écrit par `mysqldump`, ou par `mariadb-dump`
  pour MariaDB, de la version même du serveur, avec les routines, les
  déclencheurs et les événements.
- **Restaurer** supprime et recrée chaque table, vue et routine que contient la
  sauvegarde. Une sauvegarde faite depuis MariaDB ne se restaure que dans
  MariaDB, et une faite depuis MySQL que dans MySQL.

## Tableaux de bord

Une connexion MySQL peut alimenter les tableaux de bord. La disposition
s'appelle **Serveur MySQL** : connexions, instructions, lignes, lectures du pool
de tampons, trafic réseau, requêtes lentes et connexions interrompues, et la
taille de la base de données de la connexion. Les compteurs sont ceux du serveur
entier : MySQL ne les tient pas par base de données.

## Un serveur à vous

**Nouvelle connexion** propose **Démarrer MySQL ici** et **Démarrer MariaDB
ici** : un serveur démarré sur cette machine, enregistré comme une connexion
qui se connecte en tant que son root. Avec des données d'exemple, il s'ouvre
sur `demo_lab` — organisations, personnes, projets, quelques centaines de tâches
et de mesures — avec de quoi montrer sur chaque écran : colonnes générées, JSON,
une table partitionnée, des clés plein texte et spatiales, une vue, un
déclencheur et une table sans clé.

## Ce que MySQL n'a pas encore ici

- Une base de données ne peut pas être renommée ; MySQL n'a aucun moyen de le
  faire.
