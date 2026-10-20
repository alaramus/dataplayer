# SSH

Un serveur que vous atteignez via SSH. Vous parcourez ses dossiers et travaillez
avec ses fichiers comme avec les vôtres : tables, SQL sur les fichiers, éditeur,
archives, recherche, copie entre connexions et terminal. La connexion se fait
avec un mot de passe ou l'une de vos clés SSH, et uniquement vers le serveur dont
vous avez confirmé la clé. Le fonctionnement général des connexions est décrit
sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Les dossiers et les fichiers du serveur, à partir de l'endroit que vous
  choisissez
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
- Tout le reste, depuis un terminal sur le serveur

## Se connecter

La page **Connexion** de la fenêtre demande :

- **Hôte** et **Port**, 22 sauf indication contraire du serveur ;
- **Utilisateur** : le compte avec lequel se connecter ;
- **Dossier** : l'endroit où commence la navigation. Vide correspond au dossier
  personnel du compte ;
- **Clé du serveur** : ce avec quoi le serveur prouve son identité (voir
  ci-dessous) ;
- **Authentification** : un mot de passe, ou **Clé**, l'une de vos clés SSH.

Une chaîne de connexion telle que `ssh://ann@files.example.com:22` collée dans
**URL** remplit l'hôte, le port et l'utilisateur. Un mot de passe n'en fait jamais
partie.

### La clé du serveur

Rien n'est envoyé à un serveur avant que vous ayez confirmé sa clé. C'est ce qui
empêche un mot de passe ou une clé de partir vers une machine qui ne fait que
prétendre être la vôtre.

1. Remplissez l'hôte et le port, puis appuyez sur **Récupérer depuis le
   serveur**.
2. L'empreinte du serveur est affichée. Comparez-la avec celle que
   l'administrateur du serveur vous donne, ou avec ce qu'affiche `ssh-keyscan`.
3. Appuyez sur **Faire confiance à cette clé**.

Un serveur qui présente ensuite une clé différente est refusé, avec une phrase
qui le dit. Si le serveur a été réinstallé, récupérez sa clé à nouveau, comparez,
et appuyez sur **Faire confiance à la nouvelle clé**. Seul le propriétaire de la
connexion peut le faire.

Un serveur démarré depuis **Démarrer un serveur SSH ici** fait confiance à la clé
qu'il a présentée en premier, parce que cette application l'a démarré.

### Clés SSH

Vos clés SSH se trouvent sur la page **Préférences**, à part des connexions, afin
qu'une seule clé serve à autant de connexions que vous en pointez vers elle.

- **Nouvelle clé** crée une clé sur ce serveur : ED25519, ou RSA pour les serveurs
  qui refusent ED25519. **Importer** prend une clé privée que vous collez ou
  choisissez comme fichier.
- **Copier la clé publique** copie la ligne à ajouter dans
  `~/.ssh/authorized_keys` sur le serveur. Elle se termine par `dataplayer`,
  pour que le propriétaire du serveur puisse dire de quelle ligne il s'agit.
- La partie privée d'une clé n'est plus jamais montrée, à personne.
- Une clé peut avoir une phrase secrète, conservée de l'une de trois façons :
  aucune ; stockée à côté de la clé ; ou demandée quand la clé est nécessaire et
  gardée 15 minutes, une heure ou huit heures. **La verrouiller maintenant**
  l'oublie plus tôt.
- Une clé verrouillée arrête ses connexions. Chaque écran qui lit la connexion
  propose alors **Déverrouiller la clé** à la place d'une erreur.
- Une clé utilisée par une connexion ne peut pas être supprimée. Faites d'abord
  pointer la connexion vers une autre clé.

## Le catalogue et les fichiers

Une connexion SSH se parcourt exactement comme une connexion
[Fichiers](source-file.md) : le même catalogue, la même recherche par nom et à
l'intérieur des fichiers, les mêmes visionneuses, le même éditeur, les mêmes
actions (**Nouveau dossier**, **Nouveau fichier**, **Téléverser des fichiers**,
**Renommer**, **Supprimer**, **Télécharger**, **Archiver**, **Extraire**,
**Copier**, **Couper**, **Coller**) et le même SQL sur les fichiers.

Rien de tout cela n'exécute de commande sur le serveur : tout passe par SFTP.

Différences avec vos propres fichiers :

- **Connecter un dossier** n'est pas proposé.
- Un fichier de plus de 200 Mo n'est pas ouvert comme table, classeur, archive ou
  en SQL : téléchargez-le à la place. Le texte, les images, les PDF et les
  enregistrements s'ouvrent quelle que soit leur taille.
- Une recherche à l'intérieur des fichiers ignore les fichiers de plus de 1 Mo et
  s'arrête après 32 Mo au total, parce que chaque octet traverse le réseau.

## Le terminal

**Terminaux**, sur la barre latérale gauche, ouvre un terminal dans le panneau en
bas de l'écran : le shell de connexion du compte de la connexion, sur le serveur.

- Seul le propriétaire de la connexion peut en ouvrir un. Les personnes avec qui
  la connexion est partagée ne le peuvent pas.
- Le shell démarre dans le dossier personnel du compte, pas dans le **Dossier** de
  la connexion.
- Fermer le terminal, fermer la page ou perdre le réseau met fin au shell. Il
  n'est pas rattaché à nouveau ; ouvrez-en un autre.
- Plusieurs terminaux peuvent être ouverts en même temps, jusqu'à huit. Passer à
  un autre outil dans le panneau les laisse fonctionner.
