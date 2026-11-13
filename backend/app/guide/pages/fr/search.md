# Recherche

Une seule recherche trouve ce que vous voyez dans DataPlayer : les connexions et ce qu'elles contiennent — tables,
fichiers, clés, topics —, et ce que l'application garde pour vous : requêtes enregistrées, pipelines, tableaux de
bord, chats, services, clés SSH, onglets ouverts et groupes d'onglets, types de sources et pages de ce guide.

## Le champ de recherche

Le champ de l'en-tête, **Tout rechercher**, ouvre la recherche. Ctrl+K (⌘K sur Mac) fait de même depuis partout,
sauf depuis un terminal.

- Les résultats apparaissent pendant la saisie, groupés : onglets ouverts, connexions, un groupe par connexion,
  favoris, pipelines, tableaux de bord, conversations, services, clés SSH, le guide, types de sources. **Meilleures correspondances** viennent en premier.
- Un nom correspond lorsqu'il contient chaque mot saisi, dans n'importe quel ordre, sans tenir compte de la casse. Un
  nom exact ou qui commence par votre premier mot est classé au-dessus d'un nom qui ne fait que contenir les mots.
- Pendant la saisie, les endroits lents ne sont pas interrogés. **Enter** cherche partout, en attendant chaque
  connexion aussi longtemps qu'il le faut.
- Chaque endroit indique ce qui lui est arrivé : rien trouvé, pas de réponse à temps, injoignable, désactivé, verrouillé.
  Certains proposent un geste — **Réessayer**, **Rechercher quand même**, **Déverrouiller la clé SSH**.
- **Demander à l'agent**, en fin de liste, ouvre un nouveau chat contenant vos mots, sans les envoyer.
- Un champ vide affiche les recherches récentes et ce que vous avez ouvert récemment.

Appuyer sur un résultat l'ouvre là où il se trouve : une table dans l'espace de travail, un pipeline dans
Pipelines, un chat dans l'espace IA, une page du guide dans la fenêtre du guide. **Afficher dans le catalogue** trouve plutôt
une table ou un fichier dans son catalogue.

## Chercher dans une connexion

Ouverte pendant qu'un catalogue a le focus, la recherche propose d'abord **Rechercher dans ‹connexion›** : la flèche droite
l'accepte, Backspace le retire. Le filtre du catalogue fait la même chose pour un niveau, et son bouton de recherche
pour tout ce qui se trouve en dessous.

## L'onglet Search

**Afficher tous les résultats**, ou Enter, ouvre l'onglet **Rechercher** dans la colonne de travail. Il contient toute la réponse et
la filtre par groupe, connexion, type et date de modification.

**Rechercher dans les fichiers** lit le texte de chaque fichier sous les connexions que vous cochez. Cela peut prendre des
minutes, ignore les fichiers binaires et ceux de plus de 8 Mo (1 Mo par SSH), et s'exécute en arrière-plan ; ce qui est
trouvé apparaît au fur et à mesure, et **Arrêter** conserve ce qui a été trouvé jusque-là.

## L'index de recherche

Une connexion avec beaucoup de noms répond lentement lorsqu'on l'interroge à chaque fois. Son propriétaire peut plutôt
garder une liste de ses noms sur ce serveur : **Index de recherche…** dans le menu d'actions du catalogue, l'outil **Index de recherche** sur la barre de gauche en bas, ou la page **Options** de la fenêtre de connexion.

- **Conserver une liste de noms pour la recherche** copie les noms de tables, clés, dossiers et fichiers dans la base de ce serveur,
  en texte brut, lus avec les identifiants du propriétaire. Le désactiver supprime la copie.
- **Nouvelle lecture dans** — 1 heure, 6 heures, 1 jour ou 1 semaine — indique à quel point la liste peut être ancienne
  avant que la recherche interroge la source. **Lire maintenant** la relit immédiatement.
- **Contenu des fichiers**, pour un dossier, conserve aussi le texte des fichiers qu'il contient, si bien qu'un mot à
  l'intérieur est trouvé sur Enter sans rouvrir les fichiers.
- Seul le propriétaire l'active ; une personne avec qui la connexion est partagée voit l'état.

Lorsque ce serveur fait tourner le modèle nécessaire, une liste conservée est aussi recherchée par le sens : sur Enter,
les lignes marquées **Par le sens** ajoutent ce que les seuls mots ont manqué.
