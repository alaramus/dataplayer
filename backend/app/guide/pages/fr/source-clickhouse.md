# ClickHouse

Un serveur ClickHouse accessible par son interface HTTP. Vous parcourez ses
bases de données, lisez les tables et les vues page par page, voyez comment une
table est construite, lisez son DDL tel que le serveur le produit et exécutez
du SQL dans une console.
Le fonctionnement général des connexions est expliqué sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Bases de données, tables, vues et vues matérialisées
- Lignes triées et filtrées par le serveur, valeurs telles que stockées
- Colonnes, clés primaire et de tri, index de saut et contraintes
- DDL d'une relation, tel que le serveur le produit
- Taille, partitions et dernière écriture d'une table
- Résultats de votre SQL et plan d'exécution du serveur
- Chaque ligne correspondante, téléchargée dans un fichier
- Requêtes, mutations, fusions, tailles des tables, disques et paramètres
- Compteurs du serveur sur un tableau de bord

## Ce que vous pouvez modifier

- Données : cellules, blocs, insertion et suppression de lignes
- Colonnes et index de saut des tables MergeTree
- Nouvelles tables, conçues élément par élément ou créées à partir de lignes
- Bases de données : les créer et les supprimer
- Tables et vues : les renommer, déplacer dans une autre base ou supprimer
- Tables copiées avec leur structure vers une autre connexion ClickHouse
- Sauvegarde dans un fichier et restauration de la base de la connexion
- Données et structure en SQL, une modification par exécution

## Connexion

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port** de l'interface HTTP : 8123 ou 8443 avec TLS. Le port
  natif 9000 n'est pas celui à utiliser ;
- **TLS** : HTTPS avec vérification du certificat du serveur. ClickHouse Cloud
  l'exige ;
- **Authentification** : un utilisateur et un mot de passe, ou un utilisateur
  sans mot de passe. L'utilisateur est `default` si vous n'en indiquez pas un
  autre ;
- **Base de données** : celle qui s'affiche à l'ouverture du catalogue. Le
  champ peut rester vide. Le catalogue affiche tout de même chaque base visible
  par l'utilisateur.

Une chaîne de connexion telle que `clickhouse://ann@ch.example.com:8123/logs`,
collée dans **URL**, remplit ces champs. La forme `https://ch.example.com:8443`
est également reconnue, et `?secure=true` active TLS. Le mot de passe de la
chaîne collée est placé dans le champ du mot de passe puis retiré de la chaîne.

ClickHouse 23.8 et les versions ultérieures sont prises en charge. Une
connexion à un serveur plus ancien est refusée lors de la vérification, avec
indication de sa version. Un utilisateur dont le profil est `readonly = 1` ne
peut pas être utilisé : chaque lecture transmet ses propres paramètres, ce que
ce profil peut interdire.

## Catalogue

- Le premier niveau est celui des bases de données. Celle indiquée dans la
  connexion apparaît en premier ; `system` et `information_schema` appartiennent
  au serveur et sont signalées comme telles.
- Une base contient ses tables, vues et vues matérialisées. La table dans
  laquelle une vue matérialisée conserve ses lignes n'apparaît pas à côté : on
  la lit à travers cette vue.
- Pour ses tables MergeTree, le serveur indique le nombre de lignes et la
  taille de la table. Les autres moteurs ne fournissent pas ces informations.

## Lecture des lignes

- Les nombres sont affichés exactement comme ils sont stockés, jusqu'au dernier
  chiffre d'un `UInt256` ou d'un `Decimal`.
- Chaque instant est affiché en UTC avec `Z`, quel que soit le fuseau du champ.
  Une valeur de filtre sans décalage horaire est également interprétée en UTC.
- Les tableaux, maps et tuples sont affichés en JSON.
- Les colonnes de texte contenant des octets qui ne sont pas en UTF-8 affichent
  des caractères de remplacement.
- Aucune clé ClickHouse n'est unique. Une page de table est donc triée selon sa
  clé de tri, puis selon toutes les autres colonnes : la page suivante ne répète
  pas la dernière ligne. Une table dont le moteur lit des données externes —
  URL, fichier ou flux — ou qui ne se termine jamais, comme `system.numbers`,
  est lue dans l'ordre fourni par son moteur.

## Modification des lignes

- Dans une table MergeTree, vous pouvez modifier des cellules, coller des blocs,
  insérer et supprimer des lignes. Les tables Log, TinyLog, StripeLog, Memory,
  Buffer et Distributed acceptent uniquement les insertions. Les vues, les
  tables qui lisent des données externes et celles du serveur n'acceptent
  aucune modification.
- ClickHouse n'a pas de clé permettant de distinguer les lignes ; une ligne est
  donc retrouvée à partir de toutes ses valeurs. Pour un lecteur, les lignes
  identiques dans chaque valeur n'en forment qu'une : modifier l'une les modifie
  toutes, et en supprimer une les supprime toutes. Le nombre affiché après la
  suppression indique combien ont été supprimées.
- Une ligne qui ne diffère d'une autre que par une colonne flottante, Map ou
  JSON ne peut pas en être distinguée et n'est pas modifiée. Le motif est
  indiqué.
- Si quelqu'un a modifié une ligne après sa lecture, votre modification est
  refusée plutôt que d'écraser la sienne. Relisez la page et recommencez. Une
  modification faite au même instant n'est pas détectée : ClickHouse n'a pas de
  transaction qui retient la ligne.
- Les colonnes de la clé de tri, de la clé primaire ou de partition, les
  colonnes calculées, Map et JSON ne sont pas modifiables. ClickHouse choisit
  l'emplacement d'une ligne à partir de sa clé et ne peut pas la déplacer.
- Le serveur interprète une valeur selon le type de sa colonne et la refuse si
  elle n'y tient pas. Un bloc collé est accepté entièrement ou pas du tout, et
  les cellules incompatibles sont signalées. Les instants sont lus en UTC comme
  affichés ; les tableaux et tuples sont écrits dans le JSON affiché.
- Une table créée avec `enable_block_number_column` et
  `enable_block_offset_column` est modifiée par un `UPDATE` léger. Toute autre
  table est modifiée par une mutation qui réécrit les parties concernées : cela
  convient à quelques lignes, mais ralentit le collage de centaines de lignes.
- Une nouvelle ligne n'a pas d'identifiant avant que la page soit relue ; elle
  ne peut donc pas être modifiée immédiatement.

## Modification de la structure

- Les colonnes d'une table MergeTree peuvent être ajoutées, renommées ou
  supprimées, recevoir une valeur par défaut, devenir obligatoires ou
  facultatives et changer de type. Les index de saut peuvent être créés ou
  supprimés. Les autres moteurs et les vues ne sont pas modifiés.
- Les colonnes de la clé de tri, de la clé primaire ou de partition ne peuvent
  être ni supprimées, ni renommées, ni modifiées : ClickHouse choisit où garder
  une ligne selon sa clé.
- Avant un changement de type, le serveur compte les valeurs que le nouveau
  type ne peut pas contenir. Avant de rendre une colonne obligatoire, il compte
  les lignes sans valeur. Rien ne change tant qu'un de ces nombres dépasse
  zéro : ClickHouse convertit les lignes après le changement de colonne, et une
  conversion qui échoue rendrait la table illisible. Si elle échoue malgré tout,
  elle est arrêtée et l'ancien type est rétabli. Une valeur qui perdrait de
  l'information — `1.5` dans un entier — est comptée comme incompatible.
- Un changement de type réécrit toute la table sur le disque ; sa durée dépend
  donc de la taille de la table.
- Un index de saut peut être min-max, un ensemble de cent valeurs au maximum ou
  un filtre de Bloom, sur les colonnes choisies. Il est aussi construit sur les
  lignes déjà présentes. Il n'est jamais unique et la clé primaire ne peut pas
  être supprimée.
- ClickHouse n'a ni clés uniques ni clés étrangères à créer.

## Création d'une table

- **Créer une table** sur une base ouvre le concepteur de tables. Le plan,
  affiché avant l'exécution, est un seul `CREATE TABLE` d'une table MergeTree.
- La clé primaire devient la clé de tri : ClickHouse garde les lignes dans cet
  ordre et les retrouve ainsi, sans empêcher deux lignes d'avoir la même clé.
  Ses colonnes doivent contenir une valeur. Sans clé, les lignes sont gardées
  dans leur ordre d'arrivée.
- Une colonne qui peut être vide est `Nullable` ; une colonne tableau ou JSON
  contient toujours une valeur. Une colonne calculée l'est à l'écriture de la
  ligne.
- Maintenant, aujourd'hui et un UUID aléatoire peuvent remplir une valeur par
  défaut ou une colonne calculée.
- ClickHouse ne propose ni clé unique, ni clé étrangère, ni colonne d'identité,
  ni collation, ni partition par plage, liste ou hachage. Le concepteur le
  signale sur l'objet concerné.
- Une table créée à partir des lignes d'une page est une table MergeTree dont
  toutes les colonnes peuvent être vides. Si ses lignes sont refusées, la table
  n'est pas conservée.

## Section System

- Après les bases, **System** présente ce que le serveur dit de lui-même :
  **Processes**, **Mutations**, **Merges**, **Table sizes**, **Disks**,
  **Changed settings**, **Metrics** et **Users**. Ces rapports se trient, se
  filtrent et se parcourent par pages comme une table. Processes, Mutations,
  Merges et Metrics se relisent toutes les quelques secondes.
- Dans **Processes**, sélectionnez des requêtes et choisissez **Cancel query**
  pour les arrêter. Ce qu'une requête a déjà écrit reste écrit.
- Dans **Mutations**, **Stop mutation** arrête une modification qui réécrit les
  parties d'une table. Une mutation qui échoue constamment bloque les
  modifications suivantes de la table ; son erreur figure dans la dernière
  colonne. L'arrêter permet de modifier à nouveau la table.
- Toute la base `system` figure également dans le catalogue, pour consulter ce
  que ces rapports n'incluent pas.

## Recherche et téléchargement

- Le champ de recherche trouve les bases et les tables par nom, et les tables
  par nom de colonne, commentaire de colonne ou commentaire de table. `%` et
  `_` sont des caractères ordinaires.
- **Télécharger** exporte toutes les lignes correspondant aux filtres et au
  tri de la page, pas seulement celles de la page actuelle.

## Actions du catalogue

- **Nouvelle base de données** au niveau supérieur de la connexion.
- Sur une base : **Créer une table**, **Charger depuis un CSV**,
  **Supprimer la base de données** et **Modéliser en code**. La base n'est
  supprimée qu'après avoir vu son contenu et confirmé la suppression de tout.
- Sur une table ou une vue : **Renommer**, **Déplacer vers une base de données**,
  **Supprimer** et **Modéliser en code**. Avant la suppression, les vues
  matérialisées qui lisent la table et cesseraient de fonctionner sont
  indiquées. Les vues ordinaires ne le sont pas : le serveur ne conserve pas la
  liste des tables qu'une vue lit.
- Un fichier CSV devient une table dont les colonnes sont toutes textuelles et
  peuvent être vides.
- Le serveur refuse de supprimer une table qui dépasse sa limite, 50 Go sauf si
  son administrateur l'a modifiée, et en indique la raison.
- Rien ici ne peut être annulé : ClickHouse conserve chaque modification
  immédiatement.

## Copie de tables

**Copiez** des tables dans le catalogue et **collez-les** dans une base d'une
autre connexion ClickHouse ou de celle-ci. Elles arrivent avec leurs colonnes,
valeurs par défaut, colonnes calculées, codecs et commentaires, index de saut,
contraintes, moteur, clés et paramètres. La fenêtre demande les mêmes éléments
que pour PostgreSQL, affiche chaque instruction et n'en exécute aucune avant
**Copier**.

- Les tables de la famille MergeTree, ainsi que les moteurs Log et Memory, sont
  copiés. Les tables répliquées, les vues et les tables utilisant un fichier,
  une URL, un flux ou un autre serveur ne le sont pas ; la fenêtre en indique la
  raison.
- Les vues matérialisées qui lisent une table copiée restent sur place ; la
  fenêtre les indique.
- Les tables sont d'abord créées, puis les lignes sont copiées. Si la copie
  échoue ou est arrêtée, les tables créées sont supprimées.
- Rien ne bloque les tables pendant leur lecture : les lignes écrites entre-
  temps peuvent être copiées ou non.

Les lignes collées dans un autre type de connexion sont transférées comme
celles de n'importe quelle table.

## Sauvegardes

**Sauvegardes**, dans le menu d'actions du catalogue, fonctionne comme pour
PostgreSQL, pour la base indiquée par la connexion. Une connexion sans base
indiquée ne peut pas être sauvegardée.

- La sauvegarde est un seul fichier texte : l'instruction créant chaque table,
  vue et vue matérialisée, et les lignes de chaque table. Les tables d'autres
  moteurs, par exemple répliquées, sont signalées dans le fichier comme omises.
- Les tables sont lues l'une après l'autre, pas au même instant.
- **Restaurer** supprime et recrée chaque table et vue de la sauvegarde. Le
  contenu de la base absent de la sauvegarde est conservé. La restauration
  exige une base du même nom et la même version de ClickHouse ou une version
  plus récente.

## Tableaux de bord

Une connexion ClickHouse peut envoyer des données aux tableaux de bord. La
présentation **ClickHouse server** fournit les connexions et requêtes en cours,
les requêtes par seconde, les lignes lues, insérées et fusionnées, la mémoire,
le trafic réseau, les parties actives, les requêtes échouées et la taille de la
base de la connexion. Les compteurs couvrent tout le serveur.

## Votre propre serveur

**Nouvelle connexion** propose **Démarrer ClickHouse ici** : un serveur lancé
sur cette machine et enregistré comme connexion avec l'utilisateur `default`.
Cet utilisateur peut aussi gérer les utilisateurs et les droits. Avec les
données d'exemple, il ouvre `demo_lab` — organisations, personnes, projets et
leurs tâches, ainsi que deux cent mille vues de pages — avec des exemples pour
chaque écran : partitions, TTL, codecs et index de saut, ReplacingMergeTree et
SummingMergeTree, deux vues matérialisées alimentées par les pages consultées,
une vue et une table Log.

## Console SQL

**Nouvelle requête** sous **Requêtes** dans la barre latérale lance une requête
sur la connexion ; **Ouvrir comme requête** au-dessus d'une table en lance une
sur cette table. Elle fonctionne comme la console PostgreSQL — lectures,
modifications, **Explain**, complétion et formatage — avec ces différences :

- La base choisie au-dessus de l'éditeur est la base par défaut ; une seule à
  la fois.
- Il n'y a pas de transaction **Manuelle** et rien n'est essayé au préalable :
  ClickHouse conserve chaque modification immédiatement et ne peut pas revenir
  en arrière. Chaque instruction qui insère, supprime, modifie ou crée quelque
  chose s'exécute donc seule. Exécutez un script de modifications instruction
  par instruction ; les lectures peuvent être lancées ensemble.
- Une lecture utilise le paramètre serveur `readonly` ; le serveur refuse ainsi
  tout ce qui écrirait.
- `ALTER TABLE … DELETE` et `UPDATE` se terminent avant l'instruction, afin que
  la lecture suivante voie déjà les lignes modifiées.
- Les paramètres suivent la syntaxe ClickHouse, `{name:Type}`. Le serveur lit
  la valeur selon ce type et refuse celle qui ne convient pas ; **SQL null**
  envoie NULL vers un type `Nullable`. La valeur est lue comme avec `--param_`
  de clickhouse-client : une barre oblique inverse commence un échappement.
- `INSERT INTO t FORMAT JSONEachRow` suivi de ses lignes fonctionne, tout comme
  `SHOW`, `DESCRIBE`, `EXISTS`, `CHECK TABLE` et `EXPLAIN AST`, `SYNTAX`,
  `PIPELINE` et `ESTIMATE`. Un `EXPLAIN` simple est **Explain**.
- Ne sont pas exécutés : `SET` et `USE` — ajoutez plutôt `SETTINGS` à
  l'instruction et choisissez la base au-dessus de l'éditeur —, `SYSTEM`,
  `DETACH`, `ATTACH`, les utilisateurs, rôles, droits, fonctions et un `FORMAT`
  avec `SELECT`, car la console affiche elle-même le résultat.
- **Arrêter** et la limite de temps terminent une instruction avec `KILL QUERY`.
