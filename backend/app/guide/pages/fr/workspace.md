# L'espace de travail

L'espace **Données** sert à ouvrir les connexions et à lire leur contenu. Ce que sont les autres espaces
est indiqué sur [DataPlayer en un coup d'œil](overview.md).

## Trois colonnes

- **Connexions**, à gauche : chaque connexion qui vous appartient ou qui a été partagée avec vous.
  Un appui sur l'une ouvre son catalogue. Voir [Connexions](connections.md).
- **Catalogs**, au milieu : ce que contient chaque connexion ouverte, niveau par niveau. Le filtre en
  haut réduit le niveau par nom ; son bouton de recherche cherche un nom partout en dessous.
  **Dupliquer le catalogue à côté** ouvre une seconde copie du même catalogue.
- **Work**, à droite : les tables, fichiers, requêtes, structures et graphiques ouverts depuis un
  catalogue, chacun dans un onglet. Tant qu'elle est vide, elle indique quoi faire ensuite.

On redimensionne les colonnes en faisant glisser la ligne qui les sépare. La disposition que vous
laissez est celle que vous retrouvez.

## Onglets

- Un onglet se fait glisser comme un onglet de navigateur : déposé sur les onglets d'une autre colonne,
  il s'y joint ; déposé dans le corps d'une colonne, il divise cette colonne en deux. Un onglet ne peut
  aller que dans une colonne qui accepte son type.
- **Afficher dans le catalogue** trouve le nœud d'un onglet dans son catalogue.
- **Ouvrir dans une fenêtre** détache un onglet dans une fenêtre flottante, et **Ouvrir comme onglet** le remet en
  onglet.
- **Fermer les autres onglets**, un bouton en bout des onglets d'une colonne, ferme tous les autres onglets
  sauf celui qui est affiché.
- La marque à côté d'un bouton de rechargement indique **En direct** lorsque ce qui est affiché vient d'être
  lu depuis la source, et une horloge lorsqu'il s'agit d'une réponse conservée. Pointer dessus indique
  son âge.

Une partie de la disposition peut être mise de côté : elle quitte l'écran et attend sous forme de bouton
dans **Sections mises de côté**, en bas, qui la ramène.

## Groupes d'onglets

Les onglets ouverts dans Data et la disposition des colonnes peuvent être enregistrés sous un nom.

- **Enregistrer le groupe**, sur la barre de droite en haut, enregistre ce qui est ouvert maintenant.
- **Groupes d'onglets enregistrés**, à côté, les liste. Ouvrir un groupe remplace les onglets ouverts et demande
  d'abord confirmation.
- **Gérer le groupe** renomme un groupe, le supprime, ou le met à jour depuis la disposition actuelle.
  Supprimer un groupe ne ferme aucun onglet.

## Fenêtres flottantes

Les paramètres d'une connexion, les formulaires, les questions et les onglets détachés s'ouvrent dans
des fenêtres flottantes ; plusieurs peuvent être ouvertes à la fois. Rien dans DataPlayer ne bloque le
reste de l'écran.

- Une fenêtre se déplace par sa barre, se redimensionne par ses bords, et comporte **Réduire**,
  **Agrandir** et **Fermer la fenêtre**.
- Une fenêtre contenant un formulaire ne se ferme que par sa croix, pour qu'un appui sur Échap ne fasse
  jamais perdre ce qui a été saisi. Une question se ferme aussi avec Échap.
- Une fenêtre réduite attend dans **Fenêtres ouvertes**, en bas de l'écran.

## Deux connexions côte à côte

**Mettre en paire avec une autre connexion**, dans l'en-tête d'un catalogue, place les catalogues de deux connexions
dans une même fenêtre, pour déplacer des éléments entre elles : elle indique ce qui peut passer de l'une
à l'autre, et **Échanger les côtés** inverse le sens. **Oublier cette paire** ferme cette paire.

## Activité et notifications

La cloche d'activité, en bas à droite, ouvre **Activité**, en trois sections :

- **Vous attend** : ce qui attend votre réponse — une question d'un agent, une demande d'accès à votre
  connexion, une connexion qui ne répond plus, une tâche en échec ;
- **En cours** : ce que le serveur fait pour vous — copies, sauvegardes, exécutions de pipelines, démarrage
  de services, recherches dans les fichiers. Les travaux longs peuvent être mis en pause ou arrêtés ici,
  lorsque leur nature le permet ;
- **Récent** : ce qui s'est passé récemment. **Tout effacer** le vide.

Les notifications courtes apparaissent sous forme de cartes en bas à droite et vont dans **Récent**.
**Ne pas déranger** masque les cartes ; tout reste dans Activity.
