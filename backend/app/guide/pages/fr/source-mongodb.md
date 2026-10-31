# MongoDB

Un serveur MongoDB. Vous parcourez ses bases de données et ses collections et
lisez les documents page par page sous forme de lignes ; les champs d'une
collection sont déduits de ses documents. Le fonctionnement général des
connexions est décrit sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Bases de données, collections, vues et séries temporelles
- Les documents en lignes, triés et filtrés par le serveur
- Les champs des documents d'une collection et ses index
- La définition d'une collection : options, validateur et index, en JSON
- Chaque document entier, en JSON, page par page
- Le nombre de documents d'une collection et la place qu'elle occupe
- mongosh, connecté comme la connexion, dans un terminal
- Tous les documents correspondants, téléchargés dans un fichier
- Les opérations, connexions, utilisateurs et rôles du serveur
- Les compteurs du serveur, sur un tableau de bord

## Ce que vous pouvez modifier

- Documents : modifier des champs, coller des blocs, ajouter et supprimer
- Un champ dans chaque document : ajouter, supprimer, renommer, changer de type
- Index : simples et uniques, hachés, texte et géospatiaux
- Bases et collections : créer, renommer, déplacer, supprimer ; charger un CSV
- Une opération en cours : l'arrêter depuis son rapport
- Des collections copiées vers une autre connexion MongoDB avec leurs index
- La base de la connexion : sauvegardée dans un fichier et restaurée
- Tout ce que mongosh peut modifier, dans son terminal

## Connexion

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port** d'un serveur, 27017 sauf s'il écoute ailleurs ;
- **TLS** : une connexion chiffrée, avec vérification du certificat ;
- **Authentification** : un utilisateur et un mot de passe, ou aucune pour un
  serveur sans contrôle d'accès. La **Base de données d'authentification** est
  celle où l'utilisateur a été créé, `admin` sauf autre ;
- **Base de données** : où s'ouvre le catalogue. Elle peut rester vide.

Une chaîne de connexion comme `mongodb://ann@db.example.com:27017/shop` collée
dans **URL** remplit ces champs ; `?authSource=` et `?tls=true` sont lus aussi.

Le serveur nommé est celui auquel on parle. Un membre d'un replica set est lu
tel quel ; pour modifier des données, nommez le primaire. Une adresse
`mongodb+srv://` et une liste de serveurs ne sont pas prises en charge.
MongoDB 5.0 et plus récent est pris en charge.

## Catalogue

- Le premier niveau, ce sont les bases de données. Celle que nomme la
  connexion vient en premier, même vide ; `admin`, `local` et `config`
  appartiennent au serveur.
- Dans une base se trouvent ses collections et ses vues, avec leur nombre de
  documents et leur taille.

## Les documents en lignes

- Les colonnes d'une collection sont les champs de ses documents : ceux que
  déclare son validateur, puis ceux trouvés dans les cent premiers et les cent
  derniers documents. `_id` vient en premier. Un champ vu seulement ailleurs
  est montré sur sa page, sans tri ni filtre.
- Chaque colonne dit le type de ses valeurs ; un champ dont les documents
  divergent est mixte.
- Un ObjectId s'affiche en hexadécimal, une date en UTC avec `Z`, un objet ou
  un tableau en JSON tel que l'écrit `mongosh`.
- Un champ absent et un champ null donnent tous deux une cellule vide.
- Une valeur de filtre est lue comme le champ la contient ; un texte qui
  ressemble à une requête n'est que du texte.
- Sans tri de votre part, une page est ordonnée par `_id`.

## Modification des documents

- Une cellule est un champ d'un document ; ce que vous tapez est enregistré
  comme le champ contient ses valeurs, un objet ou un tableau en JSON.
- Un document modifié depuis la lecture de la page n'est pas écrasé : vous en
  êtes averti et la page est relue.
- `_id` ne peut pas être modifié. Vider une cellule enregistre null.
- Un bloc collé est vérifié en entier, puis écrit document par document ; un
  bloc de nouveaux documents entre en entier ou pas du tout.
- **Voir sous forme de documents** montre chaque document entier.

## Structure

Les colonnes d'une collection sont les champs de ses documents : l'écran de
structure modifie donc tous les documents à la fois. Un changement de type
compte d'abord les valeurs non convertibles et ne change rien s'il y en a. Un
index unique n'est pas créé si des valeurs se répètent.

## Actions du catalogue et section Server

- **Nouvelle base de données** demande aussi le nom de sa première collection.
- Une collection est renommée, déplacée vers une autre base ou supprimée ; une
  vue peut seulement être supprimée.
- **Charger depuis un CSV** crée une collection dont chaque valeur est du
  texte.
- La section **Server** contient Opérations, Connexions, Utilisateurs et
  Rôles ; **Arrêter l'opération** arrête ce qui est choisi dans Opérations.

## Copies, sauvegardes et serveur à soi

- **Copier des tables** copie des collections vers une autre connexion
  MongoDB, avec leurs options, chaque document et leurs index.
- Une sauvegarde est l'archive de `mongodump` ; la restauration utilise
  `mongorestore`. Pas à travers un tunnel SSH.
- **Services** peut lancer un MongoDB à vous et le remplir avec `demo_lab`.

## mongosh

**Ouvrir un terminal** sur une connexion MongoDB à vous lance `mongosh`,
connecté comme la connexion, dans un conteneur que ce serveur démarre ; pas à
travers un tunnel SSH. Fermer le terminal ou `exit` l'arrête.
