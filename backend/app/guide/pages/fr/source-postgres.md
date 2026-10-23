# PostgreSQL

Une base de données relationnelle. Vous parcourez ses schémas, lisez les tables
page par page, modifiez les lignes et la structure, exécutez du SQL dans une
console et copiez des données dans les deux sens. Le fonctionnement général des
connexions est décrit sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Schémas, tables et vues, et leurs lignes triées et filtrées sur le serveur
- Les colonnes d'une table, ses clés et les tables vers lesquelles elle pointe
- Chaque ligne correspondante, téléchargée sous forme de fichier
- Ce que fait le serveur : processus, paramètres, rôles, extensions
- Les métriques du serveur sur les tableaux de bord

## Ce que vous pouvez modifier

- Les données et les colonnes des tables
- Tables et schémas : créer, renommer, déplacer, supprimer
- Un fichier CSV chargé dans une table
- Les rôles
- Une sauvegarde de toute la base de données
- Les hypertables TimescaleDB, la compression et la rétention, quand il est
  installé

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port**, 5432 sauf indication contraire du serveur ;
- **Authentification** : un utilisateur et un mot de passe, ou aucun mot de passe
  pour un serveur qui fait confiance à l'adresse depuis laquelle vous vous
  connectez ;
- **Base de données**, **Utilisateur** et **Mot de passe**.

Une chaîne de connexion telle que `postgresql://ann@db.example.com:5432/sales`
collée dans **URL** remplit ces champs. Un mot de passe présent dans la chaîne
collée va dans le champ du mot de passe et quitte la chaîne.

## Le catalogue

Appuyer sur la connexion ouvre son catalogue.

- La commande de schéma en haut choisit quels schémas sont listés. Plusieurs
  peuvent l'être ensemble ; la liste indique alors à quel schéma appartient
  chaque ligne. Le choix est mémorisé dans ce navigateur.
- Les lignes sont des tables, des tables partitionnées, des vues et des vues
  matérialisées. Appuyer sur l'une ouvre ses lignes dans un onglet.
- Le champ de filtre réduit le niveau par nom.
- **Système** est une section de rapports que le serveur donne sur lui-même (voir
  **Rapports** ci-dessous).
- Cocher des relations et choisir **Relations** dans le menu d'actions les
  dessine, elles et les clés entre elles, sous forme de diagramme.
- **Détails** dit comment une relation est stockée, à qui elle appartient,
  combien elle a de colonnes, d'index et de contraintes, sa taille sur le disque,
  et quand le serveur l'a mesurée pour la dernière fois.

Les tables des schémas `pg_` et de `information_schema` appartiennent au serveur.
Elles se lisent comme n'importe quelle autre table et ne sont jamais modifiées
depuis ici.

## Lire les lignes

Une table s'ouvre sous forme de grille, une page à la fois. La ligne de commandes
au-dessus est divisée en cinq groupes : **L'affichage**, **Lire comme**,
**Extraire**, **Modifier les lignes** et **Cet onglet**. Une commande qui ne peut
pas être utilisée ici reste à sa place, grisée, et indique pourquoi lorsque vous
la pointez.

- **Trier** : la flèche dans l'en-tête d'une colonne. Plusieurs colonnes peuvent
  être triées ensemble, dans l'ordre.
- **Filtre** : des conditions sur des colonnes, reliées par AND. Ce qu'une
  colonne propose dépend de son type : des comparaisons pour les nombres, les
  dates et le texte ; « contient » et « commence par » pour le texte ; l'égalité
  et « l'un d'une liste » pour les booléens, les UUID et les énumérations ;
  « vide » ou « non vide » pour chaque colonne.
- **Colonnes** : épingler une colonne à gauche, la masquer, changer l'ordre,
  faire glisser son bord pour la redimensionner, double-cliquer sur le bord pour
  l'ajuster.
- **Par page**, à côté du paginateur en bas : jusqu'à 500 lignes.
- **Actualiser automatiquement** relit la page toutes les 1 s à 5 min. Il attend
  pendant qu'une cellule est en cours de modification ou que des lignes sont
  cochées.
- Une cellule dont la colonne fait partie d'une clé étrangère porte une flèche.
  Appuyer dessus montre où elle mène, et choisir cette destination ouvre la ligne
  vers laquelle elle pointe.
- **Ce qui pointe vers cette ligne** liste les tables dont les clés pointent ici
  et ouvre les lignes correspondantes.
- **Lire cette ligne champ par champ**, dans le coin d'une ligne, montre une
  ligne sous forme de colonne de noms et de valeurs. Ses flèches passent à la
  ligne suivante et à la précédente.
- Une valeur JSON ou tableau s'ouvre entièrement dans une visionneuse quand vous
  double-cliquez dessus ; Maj + double-clic la modifie. **Copier la valeur
  complète** la copie.
- Cocher des cellules et appuyer sur Ctrl+C les copie comme texte séparé par des
  tabulations.

Les filtres, le tri et les colonnes d'une table sont mémorisés dans ce navigateur.

## La structure d'une table

**Structure** ouvre les colonnes, les clés, les index et les contraintes de la
table à côté de ses lignes.

Avec un accès **Modifier la structure**, vous pouvez :

- ajouter une colonne, la renommer, la supprimer, changer son type ;
- définir ou supprimer sa valeur par défaut, et autoriser ou interdire les
  valeurs vides. Interdire commence par compter les lignes vides et s'arrête s'il
  y en a ;
- ajouter ou supprimer un index ;
- ajouter ou supprimer une clé unique ou une clé étrangère.

**Afficher le DDL**, au-dessus des lignes, montre le SQL qui recréerait la table.
**Modèle en code**, dans le menu d'actions du catalogue, écrit un schéma ou une
table sous forme de modèle SQLAlchemy, de modèle Django ou de document DBML et le
télécharge.

## Modifier les lignes

Avec un accès **Modifier les lignes** :

- double-cliquez sur une cellule pour la modifier. **Définir SQL NULL** stocke une
  valeur vide, ce qui n'est pas la même chose qu'un texte vide ;
- **Insérer une ligne** ajoute une ligne à la fin de la page. Les colonnes avec
  une valeur par défaut peuvent être laissées telles quelles ;
- cochez des lignes entières et appuyez sur **Supprimer les lignes
  sélectionnées**. Toutes sont supprimées, ou aucune ;
- collez un bloc de cellules copiées dans une sélection avec **Coller dans la
  sélection**. Chaque valeur est d'abord vérifiée par rapport au type de sa
  colonne, et rien n'est écrit si l'une échoue.

Si quelqu'un a modifié une ligne après que vous l'avez lue, votre modification
est refusée plutôt que d'écraser la sienne. Rechargez et réessayez.

Les lignes ne peuvent être supprimées que d'une table dotée d'une clé primaire.
Les vues sont en lecture seule.

## Tables et schémas

Le menu d'actions du catalogue, sur un schéma ou sur des relations cochées,
propose :

- **Nouveau schéma**, **Renommer le schéma**, **Supprimer le schéma** ;
- **Créer une table** : concevoir les colonnes, les clés et les index, vérifier le
  SQL qui sera exécuté, puis la créer ;
- **Renommer**, **Déplacer vers le schéma**, **Supprimer**. Supprimer plusieurs
  relations d'un coup se fait en une étape : elles partent toutes, ou aucune.

Ce qu'une suppression emporterait est montré avant que vous confirmiez.

## Faire entrer et sortir des données

- **Charger depuis un CSV**, sur un schéma : téléverser un fichier CSV et en faire
  une table.
- **Importer des lignes**, au-dessus d'une table : choisir une table dans
  n'importe quelle connexion, associer ses colonnes à celles de cette table,
  prévisualiser, et copier les lignes dedans.
- **Conserver ces lignes comme nouvelle table ou fichier** copie les lignes à
  l'écran dans une nouvelle table d'une autre connexion, ou dans un fichier CSV
  d'un dossier.
- **Télécharger** demande **Page actuelle** ou **Toutes les lignes
  correspondantes**, et s'il faut télécharger le fichier ou **Enregistrer dans
  mes fichiers**.
- **Copier** des tables dans le catalogue et les **Coller** dans un schéma d'une
  autre connexion PostgreSQL : elles sont copiées avec leurs colonnes, leurs clés
  et leurs index. Il est demandé si les clés étrangères entre elles suivent.
- Coller des tables copiées dans un dossier d'une connexion de fichiers ou SSH
  enregistre chacune comme fichier CSV.

Les copies longues s'exécutent en arrière-plan. La cloche d'activité montre leur
progression et peut les arrêter.

## La console SQL

**Requêtes**, sur la barre latérale gauche, liste vos requêtes enregistrées et
lance une **Nouvelle requête** sur une connexion. **Ouvrir comme requête**
au-dessus d'une table en lance une sur cette table.

- **Exécuter** exécute la sélection, ou l'instruction sous le curseur. **Exécuter
  le script** exécute tout le texte.
- Les résultats sont affichés sous l'éditeur et peuvent être paginés, filtrés,
  triés, téléchargés et représentés en graphique.
- **Expliquer** montre le plan d'une instruction sans l'exécuter.
- Les modifications sont validées immédiatement, sauf si **Manuel** est activé.
  La console garde alors une transaction ouverte jusqu'à **Valider** ou
  **Annuler**.
- Le réglage **Consoles** de la connexion détermine si les modifications sont
  autorisées, demandées à chaque fois, ou refusées.
- Modifier la structure (tables, vues, index, schémas) est toujours demandé. Une
  modification destructrice est d'abord essayée dans une transaction, et on vous
  montre ce qu'elle ferait.
- L'éditeur complète les noms de schémas, de tables et de colonnes.
- Chaque exécution est conservée dans l'historique de la requête.

## Rapports

**Système** dans le catalogue contient six rapports sur le serveur. Ils se lisent
comme des tables et peuvent être triés, filtrés, téléchargés et représentés en
graphique.

- **Processus** : ce qui est connecté et ce que fait chaque connexion. Chaque
  ligne porte **Annuler la requête** et **Arrêter**. Le rapport se relit toutes
  les cinq secondes.
- **Paramètres** : la configuration du serveur.
- **Espaces de tables**, **Routines**.
- **Rôles** : les utilisateurs du serveur. **Nouveau rôle** au-dessus des lignes
  en crée un. Seul le propriétaire de la connexion en dispose.
- **Extensions** : ce qui peut être installé et ce qui l'est. Chaque ligne porte
  **Installer** ou **Retirer**.

## Sauvegardes

**Sauvegardes**, dans le menu d'actions du catalogue, liste les sauvegardes de
cette base de données conservées dans votre stockage personnel.

- **Copier cette base de données vers l'extérieur** en crée une nouvelle. Cela
  s'exécute en arrière-plan.
- **Restaurer** en remet une dans cette base de données. Elle remplace les objets
  que la sauvegarde contient, et demande d'abord confirmation.
- **Supprimer cette sauvegarde** en supprime une.

Seul le propriétaire de la connexion peut la sauvegarder. Le bouton est grisé
quand cette installation ne peut pas exécuter le programme de sauvegarde.

## TimescaleDB

Quand la base de données dispose de l'extension TimescaleDB, les hypertables et
les agrégats continus sont marqués dans le catalogue, et le menu d'actions d'une
hypertable propose :

- **Modifier l'intervalle des chunks**, **Configurer la compression** ;
- **Définir la politique de rétention**, **Définir la politique de compression**,
  **Définir la politique d'actualisation**, et la suppression de chacune ;
- **Compresser les chunks**, **Décompresser les chunks** ;
- **Convertir en hypertable**, sur une table ordinaire.

Le travail qui touche beaucoup de chunks est d'abord planifié et montré pour
vérification avant de s'exécuter. Il s'exécute ensuite en arrière-plan, et la
cloche d'activité montre où il en est et ce qui est arrivé à chaque chunk.

## Métriques

Une connexion PostgreSQL peut rapporter ses propres compteurs aux tableaux de
bord : sessions par état, transactions, lignes lues et écrites, blocs lus sur le
disque et en mémoire, conflits, interblocages et taille de la base de données. Le
propriétaire l'active dans la fenêtre **Sources** de l'espace **Tableaux de
bord**, et choisit la fréquence. La disposition prête à l'emploi s'appelle **Base
de données PostgreSQL**.

## Limites

- Une page de lignes contient au plus 500 lignes.
- Un bloc collé fait au plus 500 lignes et 2000 cellules.
- La suppression agit sur les lignes de la page où vous vous trouvez.
- Les filtres sont reliés par AND. Il n'y a pas de OR.
