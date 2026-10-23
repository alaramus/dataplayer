# Fichiers

Votre stockage personnel sur ce serveur : un dossier qui vous appartient et
auquel personne d'autre n'accède, sauf si vous partagez une connexion vers lui.
Vous parcourez les dossiers, ouvrez les fichiers dans la visionneuse qui leur
convient, les modifiez et faites entrer et sortir des fichiers. Le
fonctionnement général des connexions est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Dossiers et fichiers, et ce que chacun est : sa taille, ses dates, son format
- Tables dans des fichiers CSV, TSV, Excel et Parquet, et dans des journaux
- Documents, code, images, PDF, enregistrements et le contenu des archives zip
- Fichiers trouvés par leur nom ou par le texte qu'ils contiennent
- SQL exécuté sur des tables conservées dans des fichiers

## Ce que vous pouvez modifier

- Fichiers dans un éditeur de texte
- Les lignes et les colonnes des fichiers CSV et TSV
- Fichiers et dossiers : créer, téléverser, renommer, supprimer, télécharger
- Archives : regrouper des fichiers dans une seule, ou en extraire une
- Fichiers copiés ou déplacés entre dossiers et connexions

## Se connecter

Le seul champ est **Chemin** : le dossier de votre stockage personnel sur lequel
la connexion s'ouvre. `/` est la racine de votre stockage, `/reports/2026` un
dossier qu'il contient. Rien en dehors de votre stockage n'est accessible.

**Connecter un dossier**, dans le menu d'actions du catalogue sur un dossier,
crée une nouvelle connexion qui s'ouvre sur ce dossier.

## Le catalogue

- Le chemin du niveau où vous vous trouvez est affiché en haut. **Copier le
  chemin de ce niveau** le copie, sous la forme que prend le champ **Chemin**.
- **La racine de cette connexion** revient à l'endroit où la connexion s'ouvre.
- Le champ de filtre réduit le niveau par nom.
- Le bouton de recherche à côté cherche les mêmes mots dans tous les dossiers en
  dessous, par nom. Maintenez **Maj** en appuyant dessus pour chercher à
  l'intérieur des fichiers ; la première fois, il indique ce que cela coûte et
  demande confirmation. Une correspondance affiche la ligne où elle a été
  trouvée. **Retour au dossier** quitte les résultats.
- Appuyer sur un fichier l'ouvre dans un onglet. Appuyer sur un dossier, un
  classeur ou une archive zip y entre.
- **Détails**, dans le menu d'actions, dit ce qu'est un fichier ou un dossier :
  sa taille, ses dates, ses autorisations, ce en quoi il peut être ouvert, et ce
  que son format dit de lui-même (les colonnes d'un fichier Parquet, les feuilles
  d'un classeur, la durée d'un enregistrement, la taille d'une image).

## Ouvrir des fichiers

Un fichier s'ouvre dans la visionneuse qui lui convient. Là où il y a plus d'une
façon de l'ouvrir, les autres sont proposées au-dessus.

- **CSV et TSV** s'ouvrent comme des tables. Chaque colonne est du texte.
- **Classeurs Excel** (`.xlsx`, `.xlsm`) s'ouvrent sur leur première feuille
  visible. Les autres feuilles sont le long du bas de la grille, là où un tableur
  les place. Les formules montrent la valeur enregistrée en dernier dans le
  fichier.
- **Parquet** s'ouvre comme une table avec les types de colonnes que le fichier
  déclare.
- **JSON** et **JSON lines** s'ouvrent comme du texte, et **Afficher comme table**
  les transforme en lignes.
- **Journaux** (`.log`) s'ouvrent comme du texte, et **Afficher comme table**
  découpe chaque ligne en son heure, son niveau et son message.
- **Markdown** s'ouvre comme un document, avec une table des matières, du code,
  des formules, des graphiques et des diagrammes. **Exporter** l'enregistre comme
  page HTML ou l'imprime.
- **Texte et code** s'ouvrent dans l'éditeur avec coloration.
- **Images**, **PDF**, **audio** et **vidéo** s'ouvrent dans leurs propres
  visionneuses. Un PDF peut être recherché.
- Une **archive zip** s'ouvre comme un dossier, et les fichiers qu'elle contient
  s'ouvrent comme n'importe quel autre, en lecture seule.

Les tables issues de fichiers se lisent comme n'importe quelle table dans la
grille (voir [PostgreSQL](source-postgres.md) pour la grille elle-même), avec
deux différences : un fichier ne peut pas être trié, et un filtre ne correspond
qu'à une valeur exacte.

## Modifier

- Un fichier texte, JSON, JSON lines ou Markdown s'ouvre dans l'éditeur.
  **Enregistrer** le réécrit. Un fichier JSON doit rester valide pour être
  enregistré.
- Si le fichier a changé depuis que vous l'avez ouvert, l'enregistrement est
  refusé et rien n'est écrit. **Recharger le fichier** le relit.
- Les fichiers jusqu'à 4 Mo peuvent être modifiés. Un fichier plus gros s'ouvre
  en lecture seule et dit pourquoi.
- Dans une table CSV ou TSV, vous pouvez modifier des cellules, insérer des
  lignes, supprimer les lignes cochées, et ajouter, renommer ou supprimer des
  colonnes depuis **Structure**.

## Fichiers et dossiers

Le menu d'actions du catalogue propose, sur le niveau où vous vous trouvez ou
sur ce qui est coché :

- **Nouveau dossier**, **Nouveau fichier**, **Téléverser des fichiers**. Un
  téléversement indique quoi faire quand un nom est déjà pris : s'arrêter,
  remplacer le fichier, ou conserver les deux sous un nouveau nom ;
- **Renommer**, **Supprimer**. Il n'y a pas de corbeille : un fichier supprimé est
  perdu ;
- **Télécharger** : un fichier tel quel ; un dossier, ou plusieurs fichiers
  cochés, comme une seule archive zip ;
- **Archiver** : regrouper ce qui est coché dans un zip, tar, tar.gz, tar.bz2 ou
  tar.xz ;
- **Extraire** : extraire une archive ici, ou dans un dossier dédié ;
- **Copier** et **Couper**, puis **Coller** où vous les voulez. Cela fonctionne
  entre les dossiers d'une même connexion et entre connexions, y compris les
  serveurs SSH. Coller une table d'une base de données dans un dossier
  l'enregistre comme fichier CSV.

Une copie entre connexions s'exécute en arrière-plan. La cloche d'activité
montre sa progression et peut l'arrêter.

## SQL sur les fichiers

**Ouvrir comme requête** au-dessus d'une table, ou **Nouvelle requête** dans
**Requêtes** sur la barre latérale gauche, lance une console SQL sur cette
connexion. Une table est nommée par son chemin entre guillemets doubles, par
exemple `SELECT * FROM "sales/2026.csv"`. Les fichiers CSV, TSV, Parquet, JSON,
JSON lines et journaux peuvent être interrogés et joints ; les feuilles Excel ne
le peuvent pas encore. Rien de ce qu'une requête fait n'est réécrit dans les
fichiers.

## Limites

- L'éditeur contient des fichiers jusqu'à 4 Mo.
- Une recherche à l'intérieur des fichiers ignore les fichiers de plus de 8 Mo et
  s'arrête après avoir lu 256 Mo.
- Un dossier liste au plus 2000 entrées.
- Un fichier dans une archive est lu jusqu'à 32 Mo.
- Un téléchargement ou une archive contient au plus 10 000 fichiers et 2 Go.
