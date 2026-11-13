# DataPlayer en un coup d'œil

DataPlayer relie les sources avec lesquelles vous travaillez — bases de données, stockage de
fichiers, files de messages, serveurs accessibles par SSH et d'autres — et vous permet de les lire
et de les modifier au même endroit. Cette page indique où se trouve chaque chose ; chaque partie a
sa propre page.

## Les quatre espaces

L'interrupteur en haut de la barre de gauche choisit ce qui occupe l'écran :

- **Données** : vos connexions, leurs catalogues et les tables, fichiers et requêtes ouverts depuis
  celles-ci. Voir [L'espace de travail](workspace.md) et [Connexions](connections.md).
- **Pipelines** : des connexions disposées sur un canevas, avec des liens qui copient des lignes et
  des fichiers d'une connexion à l'autre, à la main ou selon un planning. Voir
  [Pipelines](pipelines.md).
- **Tableaux de bord** : des métriques remontées par des agents et par vos connexions, tracées dans le
  temps. Voir [Tableaux de bord](dashboards.md).
- **IA** : des conversations avec l'agent, qui lit et modifie vos données par les mêmes connexions.
  Voir [L'agent IA](assistant.md).

Changer d'espace conserve ce qui était ouvert : revenir à **Données** retrouve les mêmes onglets.

## Autour de l'écran

- **L'en-tête** contient le champ de recherche, qui trouve les connexions, tables, fichiers, requêtes
  enregistrées, pipelines, tableaux de bord, conversations et pages de ce guide. Ctrl+K (⌘K sur Mac)
  place le curseur dans ce champ. Voir [Recherche](search.md).
- **Le menu utilisateur**, en haut à droite, ouvre **Préférences**, **Administration** pour un
  administrateur, et **Se déconnecter**. Voir [Préférences et votre compte](preferences.md).
- **Les barres** de chaque côté portent les outils sous forme d'icônes : l'interrupteur d'espace et
  **Discussion rapide** en haut à gauche ; **Services**, **Terminaux**, **Requêtes** et **Index de recherche** en bas à gauche ; l'enregistrement et l'ouverture des groupes d'onglets en haut à droite.
  Un outil se glisse vers un autre emplacement de sa barre ou vers une autre barre.
- **Le panneau du bas** s'ouvre pour **Services**, **Terminaux**, **Requêtes**, **Index de recherche**
  et, pour un administrateur, **Journaux**. Voir [Services et terminaux](services.md).
- **La cloche d'activité**, en bas à droite, ouvre **Activité** : ce qui attend votre réponse, ce qui
  tourne et ce qui s'est passé récemment.

## Où lire sur un sujet

- un type de source — sa page : [PostgreSQL](source-postgres.md),
  [MySQL et MariaDB](source-mysql.md), [SQLite](source-sqlite.md),
  [ClickHouse](source-clickhouse.md), [Cassandra et ScyllaDB](source-cassandra.md),
  [MongoDB](source-mongodb.md), [Redis](source-redis.md),
  [ZooKeeper](source-zookeeper.md), [Kafka](source-kafka.md),
  [RabbitMQ](source-rabbitmq.md), [Binance](source-binance.md),
  [Fichiers](source-file.md) et [SSH](source-ssh.md). La lecture et la modification des lignes, la
  modification de la structure, la console SQL et les rapports y sont décrites, pour cette source ;
- l'ajout, le partage et la configuration d'une connexion — [Connexions](connections.md) ;
- les colonnes, onglets, fenêtres et groupes d'onglets — [L'espace de travail](workspace.md) ;
- le déplacement de données selon un planning — [Pipelines](pipelines.md) ;
- les métriques et graphiques dans le temps — [Tableaux de bord](dashboards.md) ;
- l'agent, la discussion rapide et le raccordement d'un agent IA externe —
  [L'agent IA](assistant.md) ;
- les serveurs lancés ici, les terminaux et les sauvegardes —
  [Services et terminaux](services.md).
