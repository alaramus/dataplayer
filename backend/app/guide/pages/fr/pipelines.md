# Pipelines

Un pipeline dispose vos connexions sur un canevas et trace des liens entre ce qu'elles contiennent :
des lignes d'une table copiées dans une autre table, une table enregistrée en fichier CSV dans un
dossier, un topic lu dans une table, et ainsi de suite. Un pipeline s'exécute quand vous appuyez sur
**Exécuter**, selon un planning, ou — pour un lien qui lit un topic ou une file — en continu.

Les pipelines se trouvent dans l'espace **Pipelines** de l'interrupteur, en haut de la barre de gauche.
Un pipeline est à vous seul : il n'est pas partagé.

## Créer un pipeline

1. **Créer un pipeline**, ou **Nouveau** à côté du sélecteur de pipeline dans l'en-tête. Il reçoit un nom par
   défaut ; le crayon le renomme.
2. Faites glisser une connexion depuis la liste à gauche sur le canevas, ou appuyez dessus. Une fenêtre de
   son catalogue s'ouvre avec des coches.
3. Cochez ce que le pipeline prend dans la connexion — tables, fichiers, topics, clés — ou un lieu où
   les éléments arriveront : un schéma, un dossier, la racine de votre stockage. Les coches sont conservées
   quand vous descendez dans un autre niveau.
4. **Placer sur le canevas**. Ce qui a été coché devient une carte : la connexion dans son en-tête, et une
   ligne pour chaque élément coché.

Une connexion peut avoir plusieurs cartes. Une carte se déplace à la main. L'engrenage de son en-tête, ou un
double-clic, rouvre la fenêtre pour modifier ce qu'elle contient ; sa croix la retire du pipeline. La
connexion elle-même ne change pas.

Une carte dont la connexion a disparu, n'est plus partagée avec vous ou est désactivée est en pointillés et
le signale. Une table qui n'existe plus est barrée et marquée « not found ».

## Liens

- Faites glisser une ligne d'une carte sur une ligne d'une autre. Si quelque chose peut passer de l'une à
  l'autre, un lien est tracé ; sinon, la raison est indiquée.
- **Afficher les liens qui pourraient être tracés**, dans l'en-tête, trace en pointillés chaque lien possible entre les
  lignes du canevas, étiqueté par ce qu'il ferait. Appuyer sur un lien en pointillés le trace.
- Les deux extrémités d'un lien doivent être dans des connexions différentes : à l'intérieur d'une même
  connexion, utilisez **Copier** et **Coller** dans son catalogue.

Sélectionner un lien ouvre son panneau sous le canevas : ce qu'il fait, un choix **Opération** lorsque
plusieurs conviennent, et ses propres réglages — un **Nom du fichier** et ce qu'il faut faire **Si le nom est pris** (**Arrêter et le signaler**, **Conserver les deux**, **Remplacer**), la table dans laquelle écrire et la façon dont
ses colonnes correspondent aux lignes, ou les colonnes de **Une nouvelle table**. Un lien qui écrit dans des clés de
Redis se règle sous **Clé et valeurs** : quelle colonne nomme chaque clé, ce qui la précède et combien de
temps elle vit.

Chaque lien reçoit un numéro dans l'ordre où il s'exécute. Un lien attend chaque lien qui écrit dans la carte
qu'il lit.

## Exécution

- **Exécuter** enregistre le pipeline et exécute chaque lien l'un après l'autre. Il refuse de démarrer avant
  d'exécuter quoi que ce soit si un lien n'a pas encore de choix, et ouvre ce lien.
- Le premier lien qui échoue arrête l'exécution ; les liens qui suivent ne sont pas exécutés.
- Pendant l'exécution, chaque lien affiche **En attente**, **En cours**, **Terminé** ou **Échec**, et l'exécution
  apparaît dans la cloche d'activité, où elle peut être arrêtée. Arrêter termine le lien en cours ; ceux qui
  suivent ne sont pas exécutés.
- Ce qui circule par un lien s'exécute avec vos droits au moment présent. Une connexion que vous ne pouvez
  plus atteindre fait échouer son lien.

## Planning

L'horloge de l'en-tête ouvre **Planification** : **S'exécuter tout seul**, puis soit **À intervalle régulier** — un nombre de
minutes, d'heures ou de jours —, soit **À des heures de la journée**, aux jours cochés. Les heures sont celles de
l'horloge du navigateur qui a enregistré le planning. L'en-tête indique la prochaine exécution.

## Suivre un topic ou une file

Un lien qui lit un topic Kafka, un flux ou une file RabbitMQ, ou une autre source de messages, peut être
marqué **Suivre** dans son panneau. **La première exécution lit** choisit **Depuis le plus ancien disponible** ou **Seulement ce qui est nouveau** ; ensuite, le lien continue à lire là où il s'est arrêté.

Le commutateur **Suivre** de l'en-tête transporte alors ce qui arrive en quelques secondes, jusqu'à ce qu'on
le désactive. Pendant le suivi, la cloche d'activité indique le nombre de messages transportés, et un lien qui
échoue sans cesse est listé sous **Vous attend**.

## Historique

**Historique**, dans l'en-tête, liste chaque exécution, la plus récente en premier : quand elle a commencé, si
c'était à la main ou par le planning, combien de temps elle a duré et ce que chaque lien a fait. Choisir une
exécution l'affiche sur le canevas ; **Retour à la dernière exécution** revient à la dernière.

## Limites

- 100 pipelines par personne, 50 cartes par pipeline, 100 lignes par carte, 200 liens par pipeline.
- Supprimer un pipeline supprime ses cartes et son historique. Rien ne change dans les connexions.
