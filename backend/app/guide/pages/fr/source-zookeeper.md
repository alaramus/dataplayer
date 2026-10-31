# ZooKeeper

Un serveur ZooKeeper. Vous parcourez son arbre de znodes, lisez les données d'un
znode avec son stat et son ACL, modifiez les données et parcourez page par page
les enfants d'un znode sous forme de lignes. Le fonctionnement général des
connexions est décrit sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- L'arbre des znodes, déplié là où vous êtes
- Les données d'un znode : JSON en arbre, texte en texte, le reste en hexa
- Le stat d'un znode : versions, zxid, enfants, session d'un éphémère
- L'ACL d'un znode : qui peut lire, écrire, créer, supprimer, administrer
- Les enfants d'un znode en lignes, page par page
- zkCli, connecté au serveur et au chemin racine, dans un terminal
- Les rapports du serveur : mode, compteurs, clients, watches, réglages
- Les compteurs du serveur sur un tableau de bord
- Les znodes trouvés par leur nom
- Tous les enfants d'un znode, téléchargés dans un fichier

## Ce que vous pouvez modifier

- Les données d'un znode, écrites entières par rapport à la version lue
- De nouveaux znodes, au sommet ou dans un autre, simples ou séquentiels
- Supprimer des znodes, seuls ou avec tout ce qu'ils contiennent
- L'ACL d'un znode, et celle de tout ce qui est en dessous
- Tout ce que zkCli peut changer, tapé dans son terminal

## Connexion

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port** d'un serveur de l'ensemble, 2181 s'il n'écoute pas
  ailleurs ;
- **Chemin racine** : tout est lu sous ce chemin comme s'il était le sommet, et
  rien au-dessus n'est accessible. Laissez vide pour l'arbre entier ;
- **TLS** : une connexion chiffrée, avec vérification du certificat du serveur ;
- **Authentification** : **Anonyme**, ou un utilisateur **Digest** et son mot
  de passe, ajoutés à la session à son ouverture.

Une chaîne de connexion comme `zk.example.com:2181/apps/billing`, collée dans
**URL**, remplit ces champs. Une liste de serveurs n'est pas prise en charge :
nommez-en un.

## Le catalogue

- L'arbre s'ouvre au sommet, ou au chemin racine. Un znode qui a des enfants a
  une flèche ; un clic sur son nom l'ouvre.
- Chaque znode indique la taille de ses données, son nombre d'enfants et s'il
  est éphémère.
- `/zookeeper` appartient au serveur et est marqué comme tel.
- Un niveau montre ses mille premiers enfants par nom. La table des enfants du
  znode au-dessus les parcourt tous.
- Un znode que cette connexion ne peut pas lire n'apparaît que par son nom,
  marqué **accès refusé**. ZooKeeper exige le droit de lecture même pour dire
  sa taille.

## Les données d'un znode

- Des données JSON jusqu'à 4 Ko s'ouvrent en arbre ; on peut aussi les ouvrir
  en texte.
- Les autres données s'ouvrent en texte dans un éditeur. Enregistrer les écrit
  entières.
- L'enregistrement n'a lieu que si personne n'a modifié le znode depuis son
  ouverture, et seulement s'il s'agit toujours du même znode, pas d'un znode
  supprimé puis recréé. S'il a changé, rechargez-le et refaites la modification.
- Le JSON reste du JSON : un enregistrement qui ne s'analyse pas est refusé.
- Les données qui ne sont pas du texte UTF-8 sont affichées en hexadécimal et ne
  sont pas modifiées ici.

## Les enfants en lignes

- Une ligne par enfant : son nom, le début de ses données, sa taille, sa
  version, son nombre d'enfants, ses dates de modification et de création, et la
  session d'un éphémère.
- Les lignes sont dans l'ordre des noms. Elles ne peuvent être ni triées ni
  filtrées : ZooKeeper n'a pas d'index pour cela.
- Les données de plus de 4 Ko ne sont pas lues pour la table et leur cellule est
  vide ; ouvrez le znode pour les lire.

## Le panneau des détails

Sélectionnez un znode dans l'arbre et choisissez **Détails** dans le menu du
catalogue.

- Le stat du znode : versions des données, des enfants et de l'ACL, zxid de sa
  création, de sa dernière modification et de celle de ses enfants, et son
  nombre d'enfants.
- La session à laquelle appartient un znode éphémère.
- Une ligne par entrée de son ACL : le schéma, l'id et ce qu'elle permet.

## La section Serveur

Au sommet de l'arbre, **Serveur** contient ce que le serveur dit de lui-même :
**Serveur** (version, mode, latence, connexions, nombre de znodes),
**Supervision** (chaque compteur), **Connexions** (chaque client), **Watches** et
**Configuration**. Les quatre premiers sont relus toutes les dix secondes.

ZooKeeper n'y répond que si son réglage `4lw.commands.whitelist` les autorise ;
depuis ZooKeeper 3.5, seul `srvr` l'est par défaut. Un rapport auquel le serveur
ne répond pas montre une ligne nommant le mot à ajouter, par exemple
`4lw.commands.whitelist=srvr,mntr,cons,wchs,conf`.

Les mêmes compteurs peuvent être tracés sur un tableau de bord : la disposition
**Serveur ZooKeeper** montre paquets, znodes, latence, connexions, requêtes en
attente et watches. Elle a besoin que `mntr` soit autorisé.

## Trouver des znodes

Tapez dans le champ au-dessus de l'arbre et appuyez sur le bouton de recherche
pour parcourir les noms de tous les znodes sous le sommet, ou sous celui qui est
sélectionné. ZooKeeper n'a pas d'index des noms, la recherche parcourt donc
l'arbre ; elle s'arrête après cinquante mille znodes ou quand son temps est
écoulé, et le dit. Les niveaux que cette connexion ne peut pas lister sont
sautés, et la réponse dit que la recherche peut être incomplète. Les znodes
trouvés apparaissent à leur place dans l'arbre.

## Téléchargement

La table des enfants d'un znode se télécharge entière, dans l'ordre des noms. Un
rapport se télécharge aussi.

## Créer et supprimer des znodes

Sélectionnez un znode dans l'arbre et ouvrez le menu du catalogue.

- **Nouveau znode au sommet** en crée un au sommet de l'arbre ou du chemin
  racine. **Nouveau znode dedans** en crée un sous le znode sélectionné. Donnez
  un nom et, si vous voulez, ses données en texte. **Séquentiel** fait ajouter
  par ZooKeeper un numéro à dix chiffres au nom ; le znode créé s'ouvre. Les
  znodes éphémères ne sont pas proposés : il disparaîtrait aussitôt créé.
- **Supprimer** retire les znodes sélectionnés. Un znode qui a des enfants n'est
  pas supprimé.
- **Supprimer avec les enfants** dit d'abord combien de znodes partiront et
  nomme les premiers. Plus de dix mille ne sont pas supprimés d'ici ; utilisez
  `deleteall` dans zkCli. `/zookeeper` appartient au serveur et n'est pas
  supprimé.
- **Modifier l'ACL** s'ouvre avec l'ACL du znode, une entrée par ligne comme
  zkCli les écrit : `schéma:id:droits`, les droits étant des lettres de `cdrwa`
  — créer, supprimer, lire, écrire, administrer. Par exemple `world:anyone:r`
  laisse chacun lire et rien d'autre. **Aussi chaque znode en dessous**
  l'applique à tout le sous-arbre. Avant de l'appliquer, vous êtes averti si
  cette connexion ne pourrait plus modifier l'ACL.

## zkCli

**Terminal** sur une connexion ZooKeeper ouvre `zkCli`, le client fourni avec
ZooKeeper, connecté au serveur et au chemin racine de la connexion. Il tourne
dans un conteneur que le serveur démarre ; le serveur doit donc pouvoir lancer
des conteneurs, et cela ne passe pas par un tunnel SSH.

On ne peut pas donner à zkCli un mot de passe digest au démarrage : il ne
l'accepte que tapé comme commande. Sur une connexion avec un utilisateur
**Digest**, le terminal s'ouvre connecté mais non authentifié, et la première
ligne le dit. Tapez `addauth digest utilisateur:motdepasse` pour lire et
modifier les znodes dont l'ACL exige cet utilisateur. Le mot de passe n'est pas
saisi pour vous et DataPlayer ne l'affiche jamais.

## Un ZooKeeper à vous

**Services** peut démarrer un ZooKeeper sur cette machine, si ce serveur peut
lancer des conteneurs. Il ne demande pas de mot de passe — ZooKeeper n'en a pas
pour le serveur entier ; qui peut faire quoi, c'est l'ACL de chaque znode — et
n'est joignable que depuis cette machine. Il répond aux rapports ci-dessus, et
sa connexion est créée pour vous.

Il est livré avec un labo sous `/lab` : configuration en JSON, registre
d'instances de services, élection et file de znodes séquentiels, compteurs
stockés en octets, un verrou, et `/lab/private`, lisible seulement par
l'utilisateur digest `lab` avec le mot de passe `lab`. Une connexion Digest sous
cet utilisateur montre la différence.

## Ce que ZooKeeper n'a pas encore ici

- Surveiller un znode pour voir ses changements : actualisez à la main
- Copier des znodes vers une autre connexion, et les sauvegardes. ZooKeeper
  n'offre ni l'un ni l'autre par ses clients : ses sauvegardes sont les fichiers
  d'instantané sur le serveur lui-même.
