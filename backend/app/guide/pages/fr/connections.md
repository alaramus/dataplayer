# Connexions

Une connexion est un moyen enregistré d'atteindre une source : une base de
données PostgreSQL, un serveur Redis, un dossier de vos propres fichiers ou un
serveur via SSH. Les catalogues, les tables, les consoles de requêtes, les
pipelines et les tableaux de bord passent tous par des connexions.

Chaque type de source a sa propre page : [Fichiers](source-file.md),
[PostgreSQL](source-postgres.md), [Redis](source-redis.md) et
[SSH](source-ssh.md).

## La liste des connexions

La colonne **Connexions** se trouve à gauche de l'espace **Données**. L'espace
**Pipelines** affiche la même liste.

- Appuyez sur le nom d'une connexion pour ouvrir son catalogue. Il s'ouvre dans
  la colonne à côté de la liste, sous la forme d'un onglet portant le nom de la
  connexion.
- Appuyez sur l'icône d'une connexion pour ouvrir sa fenêtre, où elle se
  modifie.
- **+** en tête de colonne ajoute une connexion.
- La loupe transforme l'en-tête en filtre par nom. **Échap** ou la croix le
  ferme.
- La flèche au bout de l'en-tête relit la liste.
- Le bouton en haut à gauche de l'écran réduit la colonne aux icônes et la
  rouvre à nouveau. La colonne étroite ouvre toujours les catalogues et garde
  **+**.

Un point sur chaque icône indique ce que la dernière vérification a donné :

- vert : la source a répondu ;
- rouge : la source n'a pas répondu, ou a refusé ;
- jaune : la connexion est désactivée ;
- gris : elle n'a pas encore été vérifiée.

Les connexions sont vérifiées tant que l'espace de travail est ouvert. La
fréquence se règle sur la page **Préférences**.

## Ajouter une connexion

1. Appuyez sur **+** en tête de **Connexions**. La fenêtre **Nouvelle
   connexion** s'ouvre.
2. Choisissez un type de source. Les types sont regroupés à gauche : **Bases de
   données SQL**, **Magasins clé-valeur**, **Fichiers et stockage**. Le champ de
   recherche trouve un type par son nom ou par ce qu'il sait faire.
3. Le panneau de droite indique ce qu'est le type, ce que vous pouvez voir et
   modifier à travers lui, et contient **Guide**, qui ouvre sa page de ce guide.
4. Appuyez sur **Créer une connexion**, ou double-cliquez sur le type. La
   fenêtre de connexion s'ouvre pour lui.
5. Remplissez les champs, appuyez sur **Tester la connexion**, puis sur **OK**
   pour enregistrer et fermer, ou sur **Appliquer** pour enregistrer et garder
   la fenêtre ouverte. **Retour** revient à la liste des types sans enregistrer.

Là où ce serveur peut exécuter des conteneurs, le panneau propose aussi de
démarrer un nouveau serveur de ce type sur cette machine : **Démarrer PostgreSQL
ici**, **Démarrer TimescaleDB ici**, **Démarrer Redis ici** ou **Démarrer un
serveur SSH ici**. La fenêtre qui s'ouvre demande **Comment** :

- automatiquement : le serveur est nommé pour vous, reçoit un mot de passe que
  personne n'a à choisir et arrive rempli de données d'exemple, pour qu'il y ait
  quelque chose à regarder ;
- avec vos propres choix : un nom, un utilisateur, une base de données, un port
  sur cette machine, et pour un serveur SSH si vous vous connectez avec un mot
  de passe ou avec l'une de vos clés SSH.

Dans les deux cas, la connexion est créée pour vous. La progression du démarrage
est indiquée par la cloche d'activité en bas à droite. Quand le serveur est
prêt, une fenêtre indique où l'atteindre depuis vos propres outils et son mot de
passe, une seule fois. Copiez alors le mot de passe si vous en avez besoin
ailleurs.

Un bouton grisé dit pourquoi lorsque vous le pointez : cette installation n'a
peut-être pas le droit d'exécuter des conteneurs du tout.

## La fenêtre de connexion

La fenêtre d'une connexion s'ouvre lorsque vous en ajoutez une ou que vous
appuyez sur son icône. Plusieurs peuvent être ouvertes à la fois, ce qui permet
d'en lire une pendant que vous en remplissez une autre. Fermer une fenêtre avec
des modifications non enregistrées demande d'abord confirmation.

- **Nom** est le nom sous lequel la connexion est listée. Il est obligatoire.
- **Couleur de l'onglet** colore les onglets de la connexion et sa ligne dans la
  liste.
- **Utilisée** désactive la connexion sans la supprimer. Une connexion
  désactivée garde ses paramètres, ne peut pas être ouverte et porte un point
  jaune.
- **URL** est la chaîne de connexion composée à partir des champs. Le mot de
  passe n'en fait jamais partie. Collez une chaîne de connexion dedans et les
  champs sont remplis à partir d'elle. Le bouton de copie à côté copie la
  chaîne.
- **Tester la connexion** essaie de se connecter avec ce que le formulaire
  contient maintenant, enregistré ou non. La réponse apparaît dans une petite
  infobulle au-dessus du bouton.
- **Supprimer** supprime la connexion. Seul son propriétaire dispose du bouton,
  et il demande d'abord confirmation.

La fenêtre a au moins trois pages.

### Connexion

Comment atteindre la source. Les champs dépendent du type de source et sont
décrits sur sa page. Un choix sous **Authentification** change les champs
affichés.

### Options

**Conserver les réponses** détermine combien de temps un niveau de catalogue et
une page de lignes peuvent être réutilisés avant que la source soit relue.

- **Comme cette source le décide** est la valeur par défaut. Le libellé indique
  cette durée.
- **Ne jamais conserver les réponses** relit la source à chaque fois.
- **Conserver pendant …** définit une durée de votre choix, jusqu'à un jour.

Appuyer sur un bouton de rechargement relit toujours la source, quel que soit le
choix fait ici. Une petite marque à côté du bouton de rechargement indique **En
direct** tant que la réponse à l'écran vient d'être lue depuis la source, et
affiche une horloge dès qu'il s'agit d'une réponse conservée. Pointez dessus
pour voir son âge.

Une source qui ne conserve rien le dit, et le champ est désactivé.

### Autorisations

- **Consoles** détermine ce qu'une console de requêtes peut faire sur cette
  connexion : **Lecture seule**, **Demander avant d'écrire** (la valeur par
  défaut) ou **Écriture autorisée**. Cela s'applique à tous ceux avec qui la
  connexion est partagée.
- **Autoriser l'envoi de données à des tiers** détermine si les données lues via
  cette connexion peuvent être envoyées à un service externe, comme un
  fournisseur de modèle d'IA. C'est désactivé tant que vous ne l'activez pas.
- **Qui d'autre peut y accéder** liste les personnes avec qui la connexion est
  partagée et les demandes en attente de réponse. **Partager** la donne à
  quelqu'un.

## Partager une connexion

Une connexion appartient à la personne qui l'a créée. Le propriétaire peut
accorder à d'autres personnes l'un de trois niveaux :

- **Lire** : ouvrir le catalogue, lire les lignes, les télécharger et les
  représenter en graphique ;
- **Modifier les lignes** : modifier, ajouter et supprimer aussi des lignes ;
- **Modifier la structure** : modifier aussi les colonnes, les index, les clés
  et les tables.

Un niveau couvre toute la connexion, pas une seule table. Seul le propriétaire
peut supprimer la connexion, modifier ses paramètres, la sauvegarder ou la
partager davantage.

Une connexion partagée apparaît dans la liste de l'autre personne. Sa fenêtre
indique qui l'a partagée et à quel niveau, et ses champs ne peuvent pas être
modifiés.

Une table peut aussi être partagée sous forme de lien : **Partager cet
affichage** dans la ligne de commandes au-dessus d'une table crée un lien vers
cette table avec ses filtres et ses colonnes. Un lien ne donne aucun accès à lui
seul. Quelqu'un qui l'ouvre sans accès à la connexion peut le demander, et la
demande apparaît sur la page **Autorisations** du propriétaire et dans sa cloche
d'activité. Le propriétaire choisit le niveau en l'approuvant.

## Ouvrir un catalogue

Appuyer sur une connexion ouvre son catalogue : ce que la source contient,
niveau par niveau ou sous forme d'arbre, selon le type de source. Un catalogue a
sa propre ligne de commandes en haut et un menu d'actions sur ce qui est coché.
Les commandes dépendent du type de source et sont décrites sur sa page.

Éléments présents dans chaque catalogue :

- cocher un nœud puis ouvrir le menu d'actions agit sur ce qui est coché, ou sur
  le niveau où vous vous trouvez quand rien ne l'est ;
- **Détails** dit ce qu'est un nœud : sa taille, ses dates, ce en quoi il peut
  être ouvert ;
- **Copier** et **Couper** prennent des nœuds, et **Coller** les place là où
  vous vous trouvez, dans la même connexion ou dans une autre ;
- ouvrir un nœud l'ouvre dans un onglet à lui dans la colonne de travail, sous
  forme de lignes, de document, d'image, etc. ;
- le catalogue peut être dupliqué à côté de lui-même, ou mis en paire avec le
  catalogue d'une autre connexion dans une même fenêtre, pour déplacer des
  choses entre les deux.
