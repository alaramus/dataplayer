# RabbitMQ

Un broker RabbitMQ. Vous voyez ses hôtes virtuels, files, streams et échanges,
combien de messages attendent et qui les prend, et lisez les messages d'un
stream en lignes. Le fonctionnement général des connexions est sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Les hôtes virtuels, et dans chacun ses files, streams et échanges
- Les messages qui attendent dans une file, et ceux pris sans être acquittés
- Qui consomme une file, et les messages entrants et sortants par seconde
- Ce qui est lié à quoi : les échanges d'une file, les files d'un échange
- Les messages d'un stream en lignes, récents d'abord, depuis un offset ou date
- Les champs des messages JSON, chacun dans sa propre colonne
- Les messages d'un stream ou les liaisons téléchargés en fichier
- Les rapports du broker : vue d'ensemble, nœuds, alarmes, connexions
- Messages par seconde et attente par file sur un tableau de bord
- Files, streams et échanges trouvés par nom
- rabbitmqadmin, configuré pour la connexion, dans un terminal

## Ce que vous pouvez modifier

- Des messages envoyés à un stream, un par un ou collés en lignes
- Un message publié vers un échange ou une file
- De nouvelles files, streams et échanges, et leur suppression
- Des liaisons créées et supprimées
- Une file purgée, ou un aperçu unique de ses messages
- Tout ce que rabbitmqadmin peut modifier, tapé dans le terminal

## Connexion

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port AMQP** : où le broker accepte AMQP, 5672 par défaut,
  5671 avec TLS ;
- **Adresse de gestion** : où répond son API de gestion. Vide signifie
  `http://`, l'hôte et le port 15672, ou `https://` avec TLS. RabbitMQ n'y
  répond que si son plugin de gestion est activé ; les images officielles
  `-management` l'ont ;
- **Utilisateur** et **Mot de passe** : un seul utilisateur RabbitMQ pour les
  deux ;
- **Adresse pour le navigateur** : où mène **Ouvrir la gestion** dans le menu
  du catalogue, quand votre navigateur atteint la page de gestion à une autre
  adresse que DataPlayer ; vide pour l'adresse de gestion ;
- **Hôte virtuel** : vide pour tous les hôtes virtuels que l'utilisateur peut
  voir, ou un nom, comme `/` ;
- **TLS** et **Certificat CA** : une connexion chiffrée, et l'autorité qui a
  signé le certificat du broker quand le système ne lui fait pas confiance.

Une chaîne de connexion `amqp://user:password@host:5672/vhost` remplit le
formulaire ; `amqps://` est TLS, et `%2F` dans le chemin est l'hôte virtuel `/`.

La vérification interroge d'abord l'API de gestion, puis AMQP. Quand seul AMQP
refuse — un hôte virtuel que l'utilisateur ne peut pas ouvrir, un port
injoignable — la connexion est tout de même enregistrée et dit pourquoi : le
catalogue fonctionne, les messages d'un stream non. Le tunnel SSH n'est pas
pris en charge.

## Le catalogue

- Avec plusieurs hôtes virtuels, le haut les liste ; avec un seul, ou un seul
  nommé dans la connexion, le haut est ses **Files**, **Streams** et
  **Échanges**.
- Une file indique son type (classic ou quorum), combien de messages attendent,
  combien sont pris sans être encore acquittés, et son nombre de consommateurs.
- Un stream indique combien de messages il conserve et qui le lit.
- Un échange indique son type : direct, topic, fanout ou headers. Vos échanges
  viennent d'abord, puis ceux que RabbitMQ crée dans chaque hôte virtuel ;
  l'échange par défaut, qui n'a pas de nom, est **(par défaut)**.
- Les nombres sont les mesures de RabbitMQ, prises toutes les quelques
  secondes : un nombre peut avoir un instant de retard.
- Un niveau montre les cinq cents premiers par nom.

## Une file et un échange

Une file garde un message jusqu'à ce qu'un consommateur le prenne, puis
l'oublie : ses messages ne sont donc pas affichés, les lire les retirerait.

- Une file s'ouvre sur ses liaisons : l'échange qui la dessert, la clé de
  routage et les arguments. Chaque file est liée à l'échange par défaut par
  son propre nom.
- Un échange s'ouvre sur ce vers quoi il route : la file ou l'échange, la clé
  de routage et les arguments.

## Les messages d'un stream

Un stream garde ses messages pendant sa rétention, comme un journal, et chacun
peut le lire depuis n'importe où sans rien retirer.

- Une ligne par message : son offset, son heure, l'échange et la clé de
  routage par lesquels il est arrivé, son type de contenu, ses en-têtes, ses
  autres propriétés et son corps.
- Quand les corps sont des objets JSON, chaque champ est aussi une colonne,
  nommée `body.` suivi du champ. Les champs viennent des deux cents messages
  les plus récents.
- Un corps qui n'est pas du texte est affiché en hexadécimal.
- Les plus récents d'abord. Triez par **offset** pour commencer par les plus
  anciens ; aucune autre colonne ne trie.
- **timestamp** est l'heure que l'émetteur a mise sur le message, vide s'il
  n'en a mis aucune. Le filtrer « à partir de » une date commence la lecture
  là où le stream lui-même a reçu cette date, au paquet de messages près.
- Filtrez par **offset** pour choisir où la lecture commence et s'arrête.
- Les filtres sur les autres colonnes parcourent les messages lus, jusqu'à
  cent mille pour une page.
- Une page atteint au plus dix mille messages depuis la fin. Pour remonter
  plus loin, filtrez par offset ou par date.
- Lire un stream n'en retire rien et ne déplace la place de personne.

## Le panneau de détails

Sélectionnez une file, un stream ou un échange et choisissez **Détails** dans
le menu du catalogue.

- Une file : son type, son état, les messages en attente et non acquittés, les
  messages entrants et sortants par seconde, son nœud et sa politique, chaque
  consommateur avec son canal et son prefetch, et les arguments de sa création.
- Un stream : ses messages, ses segments, les messages entrants par seconde,
  l'arrivée de son plus ancien message conservé, son leader et ses membres,
  ses consommateurs et arguments.
- Un échange : son type, s'il survit à un redémarrage, s'il est supprimé quand
  inutilisé ou s'il est interne, et ses messages entrants et sortants par
  seconde.

## Envoyer des messages à un stream

- **+** au-dessus des lignes d'un stream ajoute un message. Remplissez ce qu'il
  faut : tout peut rester vide. Il passe par l'échange par défaut, avec le nom
  du stream comme clé de routage.
- **body** est du texte ; `0x` suivi de chiffres hexadécimaux est envoyé comme
  ces octets. Laissez-le vide et remplissez les champs `body.` pour envoyer un
  objet JSON de ces champs.
- **headers** est un objet JSON, comme `{"source": "manual"}` ; **properties**
  est un objet JSON de ce qu'AMQP nomme : `message_id`, `correlation_id`,
  `reply_to`, `priority`, `expiration`, `type`, `app_id`, `delivery_mode`.
- Un **timestamp** vide n'en envoie aucun.
- Les lignes collées dans un stream sont envoyées comme messages. Si une valeur
  ne peut être lue, rien n'est envoyé et la cellule est indiquée.
- La nouvelle ligne n'a pas d'offset avant que la page soit relue : c'est le
  stream qui le donne.

## Modifier les files, streams et échanges

Cochez une file, un stream ou un échange, ou rien sur son niveau, et ouvrez le
menu du catalogue :

- **Nouvelle file**, **Nouveau stream**, **Nouvel échange** — chacun sur son
  niveau. Une file est classic ou quorum ; un stream garde les messages pendant
  une durée comme `7D` et jusqu'à une taille ; les arguments sont un
  `nom=valeur` par ligne, comme `x-max-length=10000`.
- **Publier** — un message vers un échange avec une clé de routage, ou vers
  une file. Un message que l'échange ne route vers aucune file est perdu, et la
  fenêtre le dit.
- **Lier** — depuis un échange vers la file cochée, ou depuis l'échange coché
  vers une file ou un échange, avec une clé de routage. **Délier** choisit une
  des liaisons du nœud coché.
- **Purger** — tous les messages prêts d'une file partent ; ceux que des
  consommateurs ont pris sans les acquitter restent chez eux.
- **Supprimer** — la fenêtre dit combien de messages et de liaisons partent.
  Les échanges propres à RabbitMQ ne sont pas supprimés.

## Jeter un œil

Les messages d'une file ne sont pas affichés à son ouverture : les lire les
prendrait. **Jeter un œil** en prend jusqu'à cent, les remet aussitôt et ouvre
ce qu'il a lu dans un onglet.

- Chaque message revient marqué **relivré**. Une file quorum compte l'aperçu
  dans sa limite de livraisons, au-delà de laquelle un message part en
  dead-letter ou est abandonné, et un consommateur peut recevoir les messages
  dans le désordre. La fenêtre demande avant de regarder.
- L'onglet est l'aperçu tel qu'il a été pris. Le parcourir ne relit pas la
  file ; pour un nouvel aperçu, recommencez.
- Un aperçu est conservé tant que DataPlayer tourne, et un moment après sa
  dernière ouverture.

## La section Broker

En haut du catalogue, **Broker** rassemble ce que le broker dit de lui-même :

- **Vue d'ensemble** — la version, le nombre de connexions, canaux, files,
  échanges et consommateurs, les messages prêts et non acquittés, et les
  messages par seconde en entrée et en sortie ;
- **Nœuds** — la mémoire de chaque nœud et sa limite, le disque libre et son
  seuil, les descripteurs de fichiers et la durée de fonctionnement ;
- **Alarmes** — un nœud à court de mémoire ou de disque. Tant qu'une alarme est
  levée, RabbitMQ bloque tous les émetteurs ; le rapport est vide quand tout va
  bien ;
- **Connexions** et **Canaux** — chaque client, son utilisateur et son hôte
  virtuel, ses canaux, consommateurs, prefetch et messages pris sans être
  acquittés ;
- **Politiques** — chaque politique, ce qu'elle cible et ce qu'elle définit.

Vue d'ensemble, Alarmes et Connexions se rafraîchissent toutes les dix
secondes. Une longue liste montre ses cinq cents premiers éléments et le dit.

## Tableaux de bord et recherche

- Le tableau de bord **Broker RabbitMQ** trace les messages par seconde, ce qui
  attend dans chaque file et ce qui est pris sans être acquitté, les connexions
  et les alarmes, pour les cent premières files par nom.
- La recherche de l'en-tête trouve files, streams et échanges par nom, dans
  chaque hôte virtuel que voit la connexion.

## Dans un pipeline

RabbitMQ peut se tenir au milieu d'un pipeline, comme un topic Kafka : un lien
y envoie des lignes, d'autres portent ce qui arrive dans des tables.

- **Ajouter des lignes** à un échange, une file ou un stream envoie chaque ligne
  comme un message. Chaque colonne qui n'est pas propre au message devient un
  champ d'un corps JSON sous son propre nom : une ligne de table ou une
  transaction Binance arrive comme `{"price": …, "qty": …}`, et les colonnes de
  même nom s'apparient d'elles-mêmes. Vers un échange, appariez une colonne avec
  **routing_key** : une ligne sans elle va où l'échange envoie une clé vide.
- **Ajouter les nouveaux messages à une table**, depuis un stream, ne lit que ce
  qui est arrivé depuis la dernière exécution du lien. L'endroit où il s'est
  arrêté est gardé par DataPlayer, par offset. **Ajouter les nouveaux messages à
  une nouvelle table** met une clé sur l'offset de la table créée : un message
  écrit deux fois est gardé une fois.
- Les mêmes liens depuis une file prennent ses messages en attente, comme tout
  consommateur : chaque bloc n'est acquitté qu'une fois écrit. Si une exécution
  échoue entre les deux, le bloc retourne dans la file et est repris, marqué
  relivré. Les autres consommateurs partagent les messages avec le lien ; donnez
  au lien une file à lui, liée à l'échange, pour les avoir tous.
- Les colonnes d'une file sont celles du message — son corps arrive entier — et
  **La première exécution lit** n'a pas de sens pour elle : elle prend toujours
  ce qui attend.
- **Suivre** porte ce qui arrive en quelques secondes, depuis un stream ou une
  file, comme depuis un topic.

## Téléchargements

**Télécharger** sur un stream enregistre les messages que sa page afficherait,
avec ses filtres et son ordre, jusqu'à dix mille. Une file ou un échange
télécharge ses liaisons.

## rabbitmqadmin

**Terminal** sur une connexion RabbitMQ ouvre bash avec `rabbitmqadmin`, le
client en ligne de commande de RabbitMQ pour l'API de gestion, déjà pointé sur
la connexion : son adresse, son utilisateur, son mot de passe et son hôte
virtuel. Tab complète ses commandes. Essayez :

- `rabbitmqadmin show overview` — le broker d'un coup d'œil
- `rabbitmqadmin list queues` — toutes les files avec leurs compteurs
- `rabbitmqadmin list exchanges` — les échanges
- `rabbitmqadmin -V NOM list queues` — un autre hôte virtuel

Il peut déclarer, supprimer et purger des files et des échanges, publier et
récupérer des messages et exporter les définitions ; ce qu'il modifie l'est
aussitôt sur le broker. Le terminal tourne dans un conteneur sur le serveur
DataPlayer : ce serveur doit avoir le droit de lancer des conteneurs, et
l'adresse de gestion doit être joignable depuis lui.

## Un RabbitMQ à vous

**Services** peut lancer un broker RabbitMQ sur cette machine, si ce serveur a
le droit de lancer des conteneurs. Son utilisateur est `dataplayer` et son mot
de passe est inventé pour vous, sauf si vous en donnez un ; sa connexion est
créée pour vous.

Demandez des données d'exemple pour obtenir un lab :

- `lab.orders` — un échange topic qui route `orders.new` et `orders.paid` ;
- `lab.billing` — une file classic liée à `orders.#`, soixante commandes en
  attente, ses rejets partant vers `lab.dead-letter` ;
- `lab.shipping` — une file quorum liée à `orders.paid`, qui ne contient donc
  que les commandes payées ;
- `lab.dead-letter` et `lab.dead` — un échange fanout et la file derrière lui ;
- `lab.alerts` et `lab.alerts.critical` — un échange headers et une file qui ne
  prend que les alertes dont le `level` est `critical` ;
- `lab.trades` — un stream de trois cents transactions JSON sur une journée et
  de quelques relevés de capteur en octets, affichés en hexadécimal.

Rien dans le lab ne consomme : chaque compteur reste où il a été laissé.

La ligne du service montre son port AMQP et le port de son API de gestion,
avec un lien vers la page de gestion. **Ouvrir la gestion** dans le menu de la
connexion ouvre la même page. DataPlayer joint lui-même le broker par le nom du
conteneur : les deux fonctionnent depuis cette machine.
