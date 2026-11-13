# Pipelines

Un pipeline dispose vos connexions sur un canevas et trace des liens entre ce
qu'elles contiennent : les lignes d'une table copiées dans une autre table, une
table enregistrée en fichier CSV dans un dossier, un topic lu en continu dans une
table, etc. Activé, il tourne tout seul : un lien qui lit un topic, une file ou
un flux transporte ce qui arrive en quelques secondes, et les autres liens
s'exécutent selon la planification. Il peut aussi être exécuté une fois à la
main.

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

- Faites glisser une ligne d'une carte sur une ligne d'une autre. Pendant le
  glissement, chaque ligne où elle peut aller est teintée et dit ce que ferait
  un dépôt à cet endroit ; les autres sont estompées et disent pourquoi non.
  Déposée sur une ligne teintée, elle trace le lien.
- Un lien est tracé prêt à s'exécuter quand ses choix peuvent être devinés :
  une nouvelle table porte le nom de sa source avec toutes ses colonnes, les
  colonnes sont associées par nom, les clés viennent de la clé d'un topic. Son
  panneau change chacun d'eux.
- Un lien à qui il manque encore un choix est tracé dans la couleur
  d'avertissement et dit ce qu'il lui faut. La ligne sous le canevas le nomme,
  et **Choisir** l'ouvre.
- Les deux extrémités d'un lien doivent être dans des connexions différentes : à l'intérieur d'une même
  connexion, utilisez **Copier** et **Coller** dans son catalogue.

Sélectionner un lien ouvre son panneau sous le canevas : ce qu'il fait, un choix **Opération** lorsque
plusieurs conviennent, et ses propres réglages — un **Nom du fichier** et ce qu'il faut faire **Si le nom est pris** (**Arrêter et le signaler**, **Conserver les deux**, **Remplacer**), la table dans laquelle écrire et la façon dont
ses colonnes correspondent aux lignes, ou les colonnes de **Une nouvelle table**. Un lien qui écrit dans des clés de
Redis se règle sous **Clé et valeurs** : quelle colonne nomme chaque clé, ce qui la précède et combien de
temps elle vit.

Chaque lien reçoit un numéro dans l'ordre où il s'exécute. Un lien attend chaque lien qui écrit dans la carte
qu'il lit.

## Activer

**Activer**, dans l'en-tête, enregistre le pipeline et le démarre. Un lien qui
lit un topic, une file ou un flux s'exécute en continu : il transporte ce qui
arrive en quelques secondes. Tout autre lien s'exécute selon la planification.
**Désactiver** arrête les deux.

- Activer refuse avant que rien ne démarre quand il manque un choix à un lien,
  et ouvre ce lien ; quand des liens s'exécutent selon la planification et
  qu'aucune n'est définie, il ouvre **Planification…**.
- La ligne sous le canevas dit ce qui manque au pipeline ou ce qu'il fait : ce
  que fera l'activation, depuis combien de temps il est activé et quand il a
  transporté quelque chose pour la dernière fois, quand vient la prochaine
  exécution planifiée, ou quel lien échoue sans cesse.
- Un lien qui lit en continu peut s'exécuter selon la planification à la place :
  **Tant que le pipeline est activé** dans son panneau. **La première exécution
  lit** choisit **Depuis le plus ancien disponible** ou **Seulement ce qui est
  nouveau** ; ensuite, le lien continue à lire là où il s'est arrêté.
- Tant qu'il est activé, la cloche d'activité indique combien de messages ont
  été transportés, et un lien qui échoue sans cesse apparaît sous **Vous
  attend**. L'arrêter là désactive le pipeline.

## Exécuter une fois

- **Exécuter une fois maintenant**, dans le menu à côté d'**Activer**,
  enregistre le pipeline et exécute chaque lien une fois, l'un après l'autre.
  Il refuse avant toute exécution quand il manque encore un choix à un lien, et
  ouvre ce lien. Tant que le pipeline est activé, les liens qui s'exécutent en
  continu sont laissés de côté.
- Le premier lien qui échoue arrête l'exécution ; les liens qui suivent ne sont pas exécutés.
- Pendant l'exécution, chaque lien affiche **En attente**, **En cours**, **Terminé** ou **Échec**, et l'exécution
  apparaît dans la cloche d'activité, où elle peut être arrêtée. Arrêter termine le lien en cours ; ceux qui
  suivent ne sont pas exécutés.
- Ce qui circule par un lien s'exécute avec vos droits au moment présent. Une connexion que vous ne pouvez
  plus atteindre fait échouer son lien.

## Planning

**Planification…**, dans le menu à côté d'**Activer**, fixe quand les liens
planifiés s'exécutent tant que le pipeline est activé : soit **À intervalle
régulier** — un nombre de minutes, d'heures ou de jours —, soit **À des heures de
la journée**, les jours cochés. Les heures sont celles de l'horloge du navigateur
qui a enregistré la planification. La ligne sous le canevas indique la
prochaine exécution.

## Historique

**Historique**, dans le menu **⋯** de l'en-tête, liste chaque exécution, de la
plus récente à la plus ancienne : quand elle a commencé, à la main ou par la
planification, combien de temps elle a duré et ce qu'a fait chaque lien. Choisir
une exécution l'affiche sur le canevas ; **Retour à la dernière exécution**
revient.

## Limites

- 100 pipelines par personne, 50 cartes par pipeline, 100 lignes par carte, 200 liens par pipeline.
- Supprimer un pipeline supprime ses cartes et son historique. Rien ne change dans les connexions.
