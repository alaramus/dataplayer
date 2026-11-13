# Kafka

Un cluster Kafka. Vous voyez ses topics et ses groupes de consommateurs, lisez
les messages d'un topic en lignes et voyez le retard de chaque groupe. Le
fonctionnement général des connexions est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Les topics, les groupes de consommateurs et, à part, les topics de Kafka
- Les messages d'un topic en lignes, récents d'abord, depuis une date ou un offset
- Les champs des messages JSON, chacun dans sa colonne
- Chaque partition d'un topic : son leader, ses réplicas et ses offsets
- Les paramètres définis sur un topic
- La position de chaque groupe dans chaque partition, et son retard
- Les rapports du cluster : brokers, paramètres, partitions à surveiller
- Retard, messages par seconde et santé du cluster sur un tableau de bord
- Topics et groupes trouvés par leur nom
- Les messages d'un topic téléchargés dans un fichier
- Les outils propres à Kafka, configurés pour la connexion, dans un terminal

## Ce que vous pouvez modifier

- Envoyer des messages, un par un ou en collant des lignes
- De nouveaux topics, avec leurs partitions et leurs paramètres
- Supprimer des topics, modifier leurs paramètres, ajouter des partitions
- Supprimer les messages d'un topic, tous ou ceux d'avant une date
- Déplacer les positions d'un groupe au début, à la fin ou à une date
- Supprimer des groupes de consommateurs
- Tout ce que les outils de Kafka savent modifier, dans le terminal

## Connexion

La page **Connexion** de la fenêtre demande :

- **Brokers** : `host:port` d'un ou plusieurs brokers, séparés par des
  virgules. Un seul suffit : il indique à DataPlayer où sont les autres ;
- **TLS** : une connexion chiffrée, avec vérification des certificats des
  brokers ;
- **Certificat de l'AC** : l'autorité qui les a signés, en PEM, si le système
  ne lui fait pas déjà confiance ;
- **Authentification** : **Aucune**, ou un utilisateur et un mot de passe en
  **SASL PLAIN**, **SASL SCRAM-SHA-256** ou **SASL SCRAM-SHA-512**.

DataPlayer se connecte aux adresses que les brokers annoncent d'eux-mêmes ;
elles doivent être joignables depuis le serveur DataPlayer sous ces noms. Le
tunnel SSH n'est pas pris en charge.

## Le catalogue

- **Topics**, **Groupes de consommateurs** et **Topics internes** — ceux de
  Kafka, comme `__consumer_offsets`, dont le nom commence par un tiret bas.
- Un topic indique combien de partitions il a et combien de messages elles
  couvrent. Ce nombre est un maximum : les topics compactés ont des trous.
- Un groupe indique s'il est stable, en rééquilibrage ou sans consommateurs, et
  combien de consommateurs il a.
- Un niveau montre les mille premiers par nom.

## Les messages d'un topic

- Une ligne par message : partition, offset, date, clé, valeur et en-têtes.
- Quand les valeurs sont des objets JSON, chaque champ est aussi une colonne,
  nommée `value.` suivi du champ. Les champs viennent des deux cents messages
  les plus récents.
- Une clé ou une valeur qui n'est pas du texte s'affiche en hexadécimal.
- Les plus récents d'abord, toutes partitions confondues. Triez par
  **timestamp** pour commencer par les plus anciens ; aucune autre colonne ne
  trie.
- Filtrer par **partition**, **offset** ou **timestamp** choisit où la lecture
  commence et s'arrête : Kafka trouve lui-même cet endroit, quelle que soit la
  longueur du topic.
- Les filtres sur la clé, la valeur, les en-têtes et les champs parcourent les
  messages lus, jusqu'à cent mille par page.
- Une page remonte au plus dix mille messages depuis la fin. Pour remonter plus
  loin, filtrez par date ou par partition et offset.
- Lire un topic ne rejoint aucun groupe et ne déplace la position de personne.

## Envoyer des messages

- **+** au-dessus des lignes d'un topic ajoute un message. Remplissez ce dont
  vous avez besoin : tout peut rester vide.
- **partition** vide laisse Kafka choisir selon la clé ; **timestamp** vide
  vaut maintenant.
- **key** et **value** sont du texte ; `0x` suivi de chiffres hexadécimaux est
  envoyé comme ces octets.
- Laissez **value** vide et remplissez les champs `value.` pour envoyer un
  objet JSON fait de ces champs.
- **headers** est un objet JSON de texte, par exemple `{"source": "manual"}`.
- Les lignes collées dans un topic sont envoyées comme messages. Si une valeur
  ne peut pas être lue, rien n'est envoyé et la cellule est indiquée.
- On n'écrit pas d'ici dans les topics propres à Kafka.

## Un groupe de consommateurs

- Une ligne par partition lue par le groupe : le topic, la partition, la
  position validée par le groupe, la fin de la partition et le retard entre les
  deux, avec le consommateur qui la lit. Les lignes se rafraîchissent toutes les
  dix secondes.

## Le panneau de détails

Sélectionnez un topic ou un groupe et choisissez **Détails** dans le menu du
catalogue.

- Un topic : son nombre de messages, une ligne par partition avec leader,
  réplicas, réplicas synchrones et offsets, et les paramètres définis sur le
  topic.
- Un groupe : son état, ses consommateurs, son retard total, le broker
  coordinateur, la stratégie d'affectation et les topics.

## Les outils de Kafka

**Terminal** sur une connexion Kafka ouvre les outils en ligne de commande de
Kafka, ceux de sa documentation, déjà dirigés vers la connexion : ses brokers,
son TLS et son utilisateur. Tapez un outil sans `--bootstrap-server` :

- `kafka-topics.sh --list` — les topics
- `kafka-console-consumer.sh --topic NAME --from-beginning` — lire un topic ;
  Ctrl+C l'arrête
- `kafka-consumer-groups.sh --describe --all-groups` — le retard de chaque groupe

Indiquez vous-même `--bootstrap-server` pour diriger un outil vers un autre
cluster. Le terminal tourne dans un conteneur sur le serveur DataPlayer : ce
serveur doit donc avoir le droit de lancer des conteneurs, et les brokers
doivent être joignables depuis lui.

## Modifier topics et groupes

Cochez un topic au niveau **Topics** et ouvrez le menu du catalogue :

- **Nouveau topic** — un nom, le nombre de partitions, un facteur de
  réplication (vide pour la valeur par défaut du broker) et des paramètres, un
  `name=value` par ligne.
- **Supprimer le topic** — la fenêtre indique combien de messages
  disparaissent et quels groupes lisent le topic.
- **Modifier les paramètres** — s'ouvre avec les paramètres propres au topic ;
  retirez une ligne pour rendre ce paramètre à la valeur par défaut du broker.
- **Ajouter des partitions** — on ne peut qu'en ajouter, jamais en retirer.
  Une clé peut ensuite tomber dans une autre partition.
- **Supprimer des messages** — tous, ou ceux d'avant une date. C'est
  irréversible.

Cochez un groupe au niveau **Groupes de consommateurs** pour **Déplacer les
positions** : au début, à la fin ou à une date, pour tous ses topics ou un
seul. Les positions ne se déplacent que lorsqu'aucun de ses consommateurs ne
tourne. La fenêtre montre chaque partition avant et après. **Supprimer le
groupe** retire un groupe et ses positions, là aussi seulement quand personne
n'y lit.

## La section Cluster

En haut du catalogue, **Cluster** réunit ce que le cluster dit de lui-même :
**Cluster** (son identifiant, le contrôleur, et le nombre de brokers, topics
et partitions), **Brokers**, **Paramètres du broker** (ceux qui diffèrent des
valeurs par défaut de Kafka) et **Partitions à surveiller** (vide quand tout
va bien). Le premier et le dernier se rafraîchissent toutes les dix secondes.

## Tableaux de bord, recherche et téléchargements

- Le tableau de bord **Cluster Kafka** trace le retard de chaque groupe, les
  messages par seconde de chaque topic et les partitions à surveiller, pour
  les cent premiers topics et groupes par nom.
- La recherche de l'en-tête trouve topics et groupes par leur nom.
- **Télécharger** sur un topic enregistre les messages que sa page
  montrerait, avec ses filtres et son ordre, jusqu'à dix mille depuis la fin de
  chaque partition. Un groupe télécharge toutes ses positions.

## Un topic dans un pipeline

Un topic peut se trouver au milieu d'un pipeline : un lien y écrit, d'autres
portent ce qui arrive vers des tables.

- **Ajouter des lignes** dans un topic envoie les lignes comme messages.
- **Ajouter les nouveaux messages à une table** ne lit que ce qui est arrivé
  depuis la dernière exécution de ce lien. C'est la seule sortie d'un topic
  dans un pipeline : relire tout le topic à chaque exécution ajouterait de
  nouveau les mêmes lignes.
- Chacun de ces liens lit en tant que groupe de consommateurs propre, nommé
  `dataplayer-link-` suivi de l'id du lien, affiché dans le panneau du lien.
  Son retard figure au niveau **Groupes de consommateurs**.
- **La première exécution lit** choisit où commence la première exécution :
  au début du topic, ou seulement les messages arrivés après elle. Une fois
  que le groupe garde une position, le choix ne change rien ; pour relire,
  déplacez les positions du groupe.
- Chaque bloc de lignes est d'abord écrit, puis sa position conservée. Si une
  exécution échoue entre les deux, la suivante réécrit ce bloc : aucun
  message n'est perdu, et il arrive rarement en double.
- **Ajouter les nouveaux messages à une nouvelle table**, tiré vers un schéma
  plutôt qu'une table, crée la table à la première exécution — nom, colonnes
  et types choisis dans sa fenêtre — puis y ajoute. Si ses colonnes incluent
  partition et offset du topic, elle reçoit une clé sur eux là où la base le
  permet (PostgreSQL, MySQL, MariaDB, SQLite), et un message écrit deux fois
  n'est conservé qu'une fois. Une table supprimée ensuite n'est pas recréée :
  déplacez les positions du groupe au début pour tout lire dans une nouvelle.
- **Garder le plus récent par clé**, tiré vers une base ou un dossier Redis,
  garde la valeur la plus récente de chaque clé de message comme une clé à
  part, avec une durée de vie si vous le souhaitez ; voir la page Redis.
- Tant que le pipeline est activé, un lien qui lit un topic transporte ce qui
  arrive en quelques secondes plutôt qu'à la prochaine exécution ; **Tant que le
  pipeline est activé** dans son panneau le passe à la planification. Le
  pipeline regarde toutes les quelques secondes, continue après un redémarrage
  du serveur, et l'exécution unique laisse un tel lien de côté. Un lien qui
  échoue est réessayé un peu plus tard, les autres continuent.
- Les messages que Kafka a supprimés avant que le lien les lise sont comptés
  dans le résultat de l'exécution.
- Kafka oublie les positions d'un groupe après une semaine sans écriture ; un
  lien exécuté moins souvent recommence comme l'indique **La première
  exécution lit**.

## Un Kafka à vous

**Services** peut lancer un broker Kafka sur cette machine, si ce serveur a le
droit de lancer des conteneurs. Il ne demande aucun mot de passe — un broker
répond à quiconque l'atteint — et n'est joignable que depuis cette machine. Sa
connexion est créée pour vous.

Demandez des données d'exemple pour obtenir un laboratoire :

- `lab.orders` — trois cents commandes JSON sur une journée dans trois
  partitions, avec le client pour clé ;
- `lab.prices` — le dernier prix par symbole, un topic compacté ;
- `lab.events` — des lignes de texte avec en-têtes ;
- `lab.sensor` — des mesures stockées en octets, affichées en hexadécimal ;
- le groupe `lab-billing`, à mi-chemin de `lab.orders`, pour que son retard se
  voie.

Un broker indique à ses clients où il se trouve, et celui-ci donne l'adresse
qu'il a dans DataPlayer. Le catalogue, le terminal et les pipelines l'y
atteignent ; un outil sur votre propre ordinateur, seulement par le terminal.

## Ce que Kafka n'a pas encore ici

Copier des topics vers une autre connexion et les sauvegardes ne sont pas
proposés. Kafka copie avec MirrorMaker, un service qui reste en marche, et sa
sauvegarde, ce sont les fichiers journaux des brokers ; renvoyer chaque message
ne promettrait ni l'un ni l'autre.
