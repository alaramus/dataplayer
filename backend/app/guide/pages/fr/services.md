# Services et terminaux

DataPlayer peut lancer pour vous des serveurs de bases de données et d'autres sources sur la machine où il
tourne, et ouvrir des terminaux sur vos connexions. Les deux vivent dans le panneau au bas de l'écran, ouvert par
leurs outils sur la barre de gauche en bas.

## Lancer un serveur ici

Lorsque cette installation peut exécuter des conteneurs, le panneau d'un type de source dans **Nouvelle connexion** propose
**Démarrer … ici** — PostgreSQL, MySQL, Redis, un serveur SSH et d'autres. La manière dont il demande et ce que vous
obtenez est décrit sur la page [Connexions](connections.md). Le serveur tourne dans Docker sur cette machine, et sa
connexion est créée pour vous.

Un bouton grisé indique pourquoi lorsque vous pointez dessus : cette installation ne peut pas exécuter de conteneurs,
ou pas ce type.

## L'outil Services

**Services** liste les serveurs lancés ici pour vous, avec l'état de chacun et de son conteneur.

- **L'arrêter** arrête un serveur ; ce qui y est stocké reste. **Le démarrer** le relance.
- **Recommencer** supprime un serveur qui n'a pas démarré, ainsi que ses données, et réessaie.
- **Où il écoute** indique l'hôte, le port, l'utilisateur et la base pour l'atteindre depuis vos propres outils,
  ainsi qu'une chaîne de connexion. Son mot de passe n'est affiché qu'une fois, à la création du serveur, sauf si vous
  en avez saisi un vous-même.
- **Ce qu'il a affiché** affiche la sortie propre du serveur.
- **Retirer ce service** supprime le serveur et tout ce qui est stocké en lui. **Retirer aussi la connexion**
  supprime aussi sa connexion.

Démarrer, arrêter et supprimer s'exécutent en arrière-plan ; la cloche d'activité indique leur avancement.

## Terminaux

**Shells** ouvre un terminal sur l'une de vos connexions :

- sur une connexion SSH, un shell sur ce serveur ;
- sur une connexion à une base de données qui le propose, son propre programme client — `psql`, `mysql`, `cqlsh`,
  `zkCli`, les outils de Kafka, `rabbitmqadmin` et d'autres — connecté avec cette connexion. Il tourne dans un
  conteneur que ce serveur lance, et n'est donc proposé que là où les conteneurs sont autorisés. La page de chaque
  type de source indique ce qu'il ouvre.

Plusieurs terminaux peuvent être ouverts en même temps, chacun dans un onglet du panneau. Un terminal garde pour lui
toutes les touches, Ctrl+K compris. Fermer son onglet le termine.

Les terminaux ne s'ouvrent que sur les connexions qui vous appartiennent.

## Sauvegardes

Une base de données qui peut être copiée à l'extérieur a **Sauvegardes** dans le menu d'actions de son catalogue :
**Copier cette base de données vers l'extérieur** crée une sauvegarde, un fichier dans votre propre stockage ; **Restaurer** la réécrit en
remplaçant ce qu'elle contient ; supprimer retire le fichier. La page de chaque type de source indique si elle propose
des sauvegardes.

## Journaux

**Journaux**, sur la barre de gauche en bas d'un administrateur, lit le journal propre du serveur : filtré par niveau et par
processus, recherché par texte, par la référence qu'indique un message d'erreur ou par un chemin, et suivi au fil de sa
croissance.
