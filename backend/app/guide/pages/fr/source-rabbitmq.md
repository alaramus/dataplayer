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
- rabbitmqadmin, configuré pour la connexion, dans un terminal

## Ce que vous pouvez modifier

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
