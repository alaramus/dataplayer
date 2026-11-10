# Cassandra

Un cluster Apache Cassandra ou ScyllaDB, joint par CQL. Vous parcourez ses
keyspaces, lisez les tables et les vues matérialisées page par page, voyez
comment la clé d'une table est construite et lisez son DDL tel que le serveur
l'écrit. Les deux produits sont un seul type de connexion : le catalogue des
types montre une carte pour chacun, et la connexion dit lequel elle a joint.
Le fonctionnement général des connexions est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Keyspaces, tables et vues matérialisées
- Lignes page par page, filtrées par le serveur, valeurs telles que stockées
- Clé de partition, colonnes de clustering et index secondaires d'une table
- Le DDL d'une relation, tel que le serveur l'écrit
- Les tables virtuelles de Cassandra, comme `system_views`
- Les résultats du CQL que vous écrivez, dans la console ou dans cqlsh
- Nœuds, clients, tailles des tables, réglages et rôles du cluster
- Toutes les lignes correspondantes, téléchargées dans un fichier
- Clients, requêtes et taille du nœud, sur un tableau de bord

## Ce que vous pouvez modifier

- Données : modifier des cellules, coller des blocs, ajouter et supprimer
- Colonnes et index secondaires d'une table
- Nouvelles tables, conçues avec leur clé de partition et de clustering
- Keyspaces : créer et supprimer ; tables : vider et supprimer
- Tables copiées avec leur structure dans une autre connexion Cassandra
- Données et structure, par CQL dans la console, un changement à la fois

## Connexion

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port** du protocole natif, 9042 sauf configuration contraire
  du serveur ;
- **TLS**, avec le certificat du serveur vérifié par rapport à l'hôte ;
- **Authentification** : un utilisateur et un mot de passe, ou rien pour un
  serveur qui n'en vérifie pas. Un Cassandra ou un ScyllaDB neuf a souvent
  `cassandra` avec le mot de passe `cassandra` ;
- **Keyspace** : où s'ouvre le catalogue. Il peut rester vide ;
- **Cohérence** : combien de répliques répondent à une lecture et confirment
  une écriture. `LOCAL_ONE` sauf si vous en choisissez une autre.

Une chaîne de connexion comme `cassandra://ann@db.example.com:9042/shop`
collée dans **URL** remplit ces champs ; `scylla://` est lu aussi, `?ssl=true`
active TLS et `?consistency=LOCAL_QUORUM` choisit le niveau.

Chaque instruction va au nœud que vous nommez, même quand le cluster en a
d'autres : les adresses que les nœuds donnent d'eux-mêmes sont souvent
injoignables d'ici — derrière Docker, un NAT ou un tunnel SSH — et le nœud
nommé l'est. Ce nœud demande aux autres ce qu'il ne détient pas.

Cassandra 4.0 et ScyllaDB 5.4 et plus récents sont pris en charge. Un serveur
plus ancien est refusé à la vérification de la connexion, avec sa version.

## Le catalogue

- Le premier niveau est celui des keyspaces. Celui de la connexion vient en
  premier ; `system` et les keyspaces `system_…` appartiennent au serveur et
  sont marqués comme tels, de même que `audit` chez ScyllaDB.
- Dans un keyspace se trouvent ses tables et ses vues matérialisées. ScyllaDB
  garde un index secondaire dans une vue cachée ; elle n'est pas listée, et
  l'index apparaît sur sa table.
- Les colonnes d'une table disent lesquelles forment la clé de partition,
  lesquelles sont des colonnes de clustering, dans quel ordre, et lesquelles
  sont statiques.

## Lignes

- Les lignes arrivent dans l'ordre du serveur, page par page. Aucune colonne
  ne se trie : CQL n'ordonne les lignes qu'à l'intérieur d'une partition
  nommée en entier.
- Un filtre sur n'importe quelle colonne fonctionne. Sur une colonne hors de
  la clé, il fait lire toute la table au serveur, ce qui peut dépasser le délai
  sur une grande table.
- Les filtres comparent par égal, supérieur, inférieur, au moins, au plus et
  appartenance à une liste. ScyllaDB ajoute « commence par » et « contient »
  pour le texte ; `%` et `_` ne peuvent pas être cherchés, car son `LIKE` n'a
  pas d'échappement. Listes, ensembles, tables associatives, tuples, types
  définis par l'utilisateur, blobs, durées et compteurs ne sont pas filtrés.
- Les nombres arrivent tels que stockés, jusqu'au dernier chiffre d'un
  `varint` ou d'un `decimal`. Un horodatage est affiché en UTC. Listes,
  ensembles, tables associatives, tuples et types définis par l'utilisateur
  sont affichés en JSON ; une table associative dont les clés ne sont pas du
  texte, comme une liste de paires. Un blob est affiché en `0x` suivi
  d'hexadécimal.
- Sauter loin en avant lit les lignes intermédiaires, jusqu'à cent mille.
  Au-delà, avancez à partir d'une page déjà lue.
- La dernière page peut promettre une suite et se révéler vide : le serveur
  dit s'il pourrait y en avoir plus avant d'avoir regardé.

## Console CQL

**Nouvelle requête** sous **Requêtes** dans la barre de gauche en ouvre une sur
la connexion, et **Ouvrir comme requête** au-dessus d'une table en ouvre une
sur cette table. Elle fonctionne comme la console PostgreSQL — lectures,
modifications, complétion — avec ces différences :

- Le langage est CQL. Le keyspace choisi au-dessus de l'éditeur est celui des
  noms non qualifiés ; un `USE` le change pour le reste de cette exécution
  seulement.
- Il n'y a pas de transaction. **Lecture** n'exécute que des instructions qui
  lisent : `SELECT`, `DESCRIBE` et `LIST`. **Validation automatique** exécute
  tout, mais une instruction qui modifie des lignes ou la structure s'exécute
  seule, car Cassandra la conserve aussitôt et ne peut pas la reprendre. Des
  modifications qui doivent aboutir ensemble se mettent dans un seul
  `BEGIN BATCH … APPLY BATCH`, qui compte pour une instruction.
- Les paramètres sont ceux de CQL, `:name`. Le serveur dit le type de chacun,
  et la valeur est lue comme ce type ; une liste, un ensemble, une table
  associative, un tuple ou un type défini par l'utilisateur s'écrit en JSON.
  **SQL null** envoie null.
- `CONSISTENCY`, `TRACING`, `COPY`, `SOURCE`, `PAGING` et les autres commandes
  de cqlsh ne sont pas du CQL et sont refusées ici ; exécutez-les dans cqlsh.
- **Arrêter** cesse d'attendre la réponse. On ne peut pas demander au serveur
  d'arrêter une instruction, il la termine donc quand même.

## cqlsh

**Terminal** sur une connexion ouvre cqlsh, connecté comme la connexion, dans
le keyspace qu'elle nomme. Pour ScyllaDB aussi, c'est le cqlsh de Cassandra ;
les deux parlent CQL. Il tourne dans un conteneur sur ce serveur, donc l'hôte
doit être joignable depuis celui-ci, et une connexion par tunnel SSH n'a pas
encore de terminal.

## Modifier les lignes

- Dans une table, on modifie des cellules, colle des blocs, ajoute et supprime
  des lignes. Les vues matérialisées, les tables virtuelles et les keyspaces du
  serveur sont en lecture seule, comme une table de compteurs : un compteur
  n'accepte qu'une addition, que la console sait écrire.
- Une ligne est retrouvée par sa clé primaire. Les colonnes de la clé ne se
  modifient pas — elles décident où la ligne est conservée — et une nouvelle
  ligne a besoin d'une valeur pour chacune.
- Une ligne modifiée par quelqu'un après votre lecture de la page est refusée
  plutôt qu'écrasée. Relisez la page et refaites la modification. Une
  modification faite au même instant que la vôtre n'est pas détectée :
  Cassandra n'a pas de transaction pour tenir la ligne.
- Listes, ensembles, tables associatives, tuples et types définis par
  l'utilisateur s'écrivent dans le JSON où ils apparaissent ; une durée dans
  les unités de CQL, comme `1mo2d3h`.
- Une colonne statique garde une seule valeur pour toute la partition : la
  modifier sur une ligne la change sur toutes les lignes de cette partition.
- Ajouter une ligne refuse une clé déjà présente. Des lignes collées ou
  chargées en bloc remplacent une ligne de même clé, comme Cassandra écrit.
- Un collage est vérifié en entier avant toute écriture : une valeur que sa
  colonne ne peut pas recevoir, et rien ne change.

## Modifier la structure

- Les colonnes d'une table s'ajoutent et se suppriment. Une colonne de la clé
  primaire ne se supprime pas ; celle qu'un index ou une vue matérialisée lit,
  le serveur refuse aussi de la supprimer et dit pourquoi.
- Seule une colonne de la clé primaire peut être renommée : Cassandra ne
  renomme rien d'autre. Cassandra n'a ni valeur par défaut, ni colonne
  obligatoire hors de la clé, ni changement de type, donc aucun n'est proposé.
- Un index secondaire se crée sur une colonne et se supprime. Cassandra 5
  propose l'index attaché au stockage (SAI) et l'index classique, ScyllaDB son
  index global. Aucun n'est unique.
- Les vues matérialisées, les tables virtuelles et les keyspaces du serveur
  ne sont pas modifiés.

## Créer une table

- **Créer une table** sur un keyspace ouvre le concepteur de tables. Le plan
  est un `CREATE TABLE` et un `CREATE INDEX` par index, montrés avant
  l'exécution.
- Une clé primaire est obligatoire. Sur la page d'options de la table, **Clé de
  partition** nomme les premières colonnes de la clé primaire qui décident sur
  quel nœud une ligne est conservée ; laissée vide, c'est la première colonne.
  Le reste de la clé primaire ordonne les lignes dans une partition.
- Le nom d'une table est fait de lettres, de chiffres et de soulignés ; celui
  d'une colonne peut être quelconque. Une colonne peut être une liste de son
  type, mais une liste et une durée ne peuvent pas être dans la clé.
- Clés uniques, clés étrangères, contrôles, valeurs par défaut, colonnes
  calculées, collations, partitionnement par plage, liste ou hachage et
  colonnes obligatoires hors de la clé n'existent pas en CQL ; le concepteur le
  dit sur l'objet qui en demande.

## La section « Cluster »

- Après les keyspaces, **Cluster** contient ce que le nœud dit du cluster :
  **Nœuds**, **Clients**, **Tailles des tables**, **Réglages** et **Rôles**.
  Ils se parcourent comme une table ; Clients se relit toutes les quelques
  secondes. Les tailles des tables sont l'estimation propre du nœud.
- Les keyspaces `system` figurent aussi dans le catalogue, pour tout ce que
  ces rapports omettent.

## Recherche et téléchargement

- Le champ de recherche trouve les keyspaces et les tables par leur nom, et les
  tables par le nom d'une colonne ou par leur commentaire.
- Le téléchargement prend toutes les lignes qui correspondent aux filtres
  d'une page, pas seulement la page.

## Actions du catalogue

- **Nouveau keyspace** en haut de la connexion, conservé dans le centre de
  données du nœud avec le nombre de répliques choisi.
- Sur un keyspace : **Créer une table** et **Supprimer le keyspace**. Un
  keyspace n'est supprimé qu'une fois que vous avez vu ce qu'il contient et
  coché la suppression de tout son contenu.
- Sur une table : **Vider**, qui supprime toutes les lignes et garde la
  table, et **Supprimer** ; sur une vue matérialisée, **Supprimer**. Une table
  est supprimée avec les vues matérialisées qui la lisent, et l'aperçu les
  nomme.
- Les tables et les keyspaces ne se renomment pas : CQL n'en a pas le moyen.

## Copier des tables

**Copiez** des tables dans le catalogue et **collez**-les dans un keyspace
d'une autre connexion Cassandra ou ScyllaDB, ou de celle-ci. Elles arrivent
avec leurs colonnes, leur clé de partition et de clustering et son ordre, leur
commentaire, leurs index secondaires et les types définis par l'utilisateur
qu'elles emploient ; la fenêtre montre chaque instruction et n'exécute rien
avant **Copier**.

- Les types absents du keyspace sont créés d'abord, puis la table, puis ses
  lignes, et seulement ensuite ses index.
- Une table de compteurs n'est pas copiée : un compteur ne s'écrit pas par
  `INSERT`. Les vues matérialisées ne sont pas copiées ; celle qui lit une table
  copiée est nommée dans la fenêtre.
- Si la copie échoue ou est arrêtée, les tables qu'elle a créées sont
  supprimées.
- Rien ne fige les tables pendant leur lecture : des lignes écrites entre-temps
  peuvent arriver ou non.

Des lignes collées dans un autre type de connexion suivent le chemin des
lignes de n'importe quelle table.

## Sauvegardes

Pas encore proposées pour Cassandra et ScyllaDB.

## Tableaux de bord

Une connexion Cassandra peut alimenter des tableaux de bord. La disposition est
**Nœud Cassandra** : clients, taille et partitions du keyspace de la connexion
selon l'estimation du nœud, et pour Cassandra requêtes, lectures, écritures et
compactages par seconde ainsi que le travail en attente. ScyllaDB garde ces
compteurs dans son propre point de supervision, que cette connexion ne lit pas.

## Un serveur à vous

**Nouvelle connexion** propose **Démarrer Apache Cassandra ici** sur la carte
Cassandra et **Démarrer ScyllaDB ici** sur la carte ScyllaDB : un nœud démarré
sur cette machine, enregistré comme connexion avec son superutilisateur
`cassandra` et un mot de passe inventé pour lui. Un nœud Cassandra met une ou
deux minutes à répondre et fixe lui-même son mot de passe dès qu'il répond.
Avec des données d'exemple, il s'ouvre sur `demo_lab` — des organisations et
leurs personnes, des projets et leurs tâches, vingt mille pages vues sur trente
jours et une table de compteurs de vues par page — avec de quoi remplir chaque
écran : une colonne statique, un type défini par l'utilisateur, des
collections, une durée, un index secondaire, une vue matérialisée et un ordre
de clustering du plus récent au plus ancien.
