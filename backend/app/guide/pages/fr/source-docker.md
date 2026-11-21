# Docker

Un démon Docker sur une autre machine, atteint par l'une de vos connexions
SSH. Vous voyez ses conteneurs, images, volumes et réseaux, ce que le démon
dit de chacun, les journaux et processus d'un conteneur, et les rapports du
démon lui-même. Le fonctionnement des connexions est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Les conteneurs, par projet Compose, en marche ou non
- Images, volumes et réseaux, et les conteneurs qui les utilisent
- Ce que le démon dit de chacun, sous forme d'arbre JSON
- Les journaux d'un conteneur, du plus récent, et ses processus
- Les couches d'une image et les instructions qui les ont créées
- Le moteur : versions, pilotes, CPU, mémoire, espace disque, événements

## Ce que vous pouvez modifier

- Conteneurs démarrés, arrêtés, redémarrés, en pause, sortis de pause ou tués
- Les conteneurs d'un projet Compose, tous à la fois
- Conteneurs, images, volumes et réseaux supprimés
- Conteneurs arrêtés, images, volumes et réseaux inutilisés nettoyés
- Nouveaux volumes et réseaux
- Images publiques tirées, et un conteneur enregistré dans une image

## Connexion

Le démon n'est jamais atteint directement. Créez d'abord une **connexion SSH**
vers la machine où il tourne ; la page **Connexion** d'une connexion Docker
demande ensuite :

- **Connexion SSH** : l'une de vos connexions SSH. Son compte doit pouvoir
  utiliser le socket du démon — sur la plupart des machines, il fait partie
  du groupe `docker` ;
- **Socket** : où le démon écoute sur cette machine. `/var/run/docker.sock`
  pour Docker, `/run/user/<uid>/docker.sock` pour Docker sans root. La carte
  **Podman** remplit `/run/podman/podman.sock` ; un Podman sans root utilise
  `/run/user/<uid>/podman/podman.sock`, et son socket doit être activé
  (`systemctl --user enable --now podman.socket`).

Le socket est transféré par la connexion SSH, comme une base de données est
atteinte par un tunnel SSH ; le serveur SSH doit le permettre
(`AllowStreamLocalForwarding`, activé par défaut). Si la vérification dit que
le socket n'a pas pu être ouvert, l'une de trois choses ne va pas, et OpenSSH
ne dit pas laquelle : rien n'écoute à ce chemin, le compte ne peut pas
l'utiliser, ou le transfert est désactivé.

Le démon doit parler l'API 1.41 ou plus récente (Docker 20.10 et après).

Le démon Docker de la machine où tourne DataPlayer lui-même n'est jamais
proposé : qui tient ce socket tient la machine.

## Le catalogue

- **Système** contient les rapports du démon, ci-dessous.
- **Conteneurs** contient un dossier par projet Compose, nommé d'après
  l'étiquette qu'écrit Compose, et **Hors projet** pour le reste. Chaque
  conteneur montre son état en un mot — en marche, sain, malade, démarrage,
  en pause, redémarrage, arrêté, en échec, créé ou mort — avec à côté le
  statut du démon, son image, son service Compose et ses ports publiés.
- **Images** liste chaque image par son id, étiquetée ou non, avec sa taille
  et le nombre de conteneurs qui l'utilisent.
- **Volumes** liste chaque volume par nom ; **Réseaux** chaque réseau, les
  trois de Docker d'abord, chacun marqué intégré, Compose ou utilisateur.
- Chacun de ces dossiers s'ouvre aussi comme un tableau, filtrable et triable
  par n'importe quelle colonne. Au-delà de dix mille d'un même type, rien
  n'est listé de plus.

## Comment s'ouvre un nœud

- Un conteneur, une image, un volume ou un réseau s'ouvre comme ce que le
  démon en dit, en arbre JSON. Celui d'un conteneur inclut son
  environnement, qui contient souvent des mots de passe : quiconque partage
  cette connexion avec vous le voit.
- Dans un conteneur : **Journaux** — l'heure, le flux (stdout ou stderr) et le
  texte de chaque ligne, du plus récent, jusqu'à dix mille lignes en arrière,
  une ligne coupée à 16 Ko — et **Processus**, ce qui y tourne maintenant. Un
  conteneur arrêté n'en a aucun.
- Dans une image : **Historique**, ses couches.
- Dans un volume ou un réseau : **Conteneurs**, ceux qui l'utilisent.

## La section Système

- **Moteur** : versions du démon, système d'exploitation, noyau, pilotes,
  CPU, mémoire et nombre de conteneurs et d'images, sous les noms du démon.
  Les miroirs de registre et les proxys sont omis : ils peuvent contenir des
  mots de passe.
- **Espace disque** : chaque image, conteneur, volume et entrée du cache de
  build avec sa taille, et si le supprimer libérerait de la place. Le démon
  mesure chaque volume pour répondre, cela peut prendre du temps.
- **Événements** : ce qui s'est passé dans la dernière heure, le plus récent
  d'abord.

## Quand quelque chose est refusé

- Un refus de la connexion SSH ou du socket arrête toute la connexion, et
  chaque écran dit pourquoi.
- Un démon derrière un plugin d'autorisation ou un proxy filtrant peut
  refuser une requête : c'est dit par **Le serveur Docker ne l'a pas permis**.

## Modifier

Sélectionnez un conteneur, le dossier d'un projet Compose ou un nœud et ouvrez
le menu du catalogue. Le cycle de vie d'un conteneur demande l'accès en
écriture ; supprimer, nettoyer, tirer, enregistrer et créer des volumes et des
réseaux demandent l'accès à la structure.

- **Démarrer**, **Arrêter**, **Redémarrer**, **Mettre en pause**,
  **Sortir de pause** et **Tuer** agissent sur les conteneurs sélectionnés, ou sur
  tous ceux d'un projet Compose sélectionné. Chacun dit d'abord ce qu'il fera
  et quels conteneurs le sont déjà. Arrêter et Redémarrer peuvent attendre
  quelques secondes avant de tuer ; Tuer envoie le signal choisi.
- **Supprimer le conteneur** refuse un conteneur en marche sans **Forcer**,
  et peut emporter ses volumes anonymes. **Supprimer l'image** nomme les
  conteneurs qui l'utilisent ; **Supprimer le volume** refuse un volume monté ;
  **Supprimer le réseau** refuse un réseau avec des conteneurs, et les trois de
  Docker.
- Dans **Conteneurs**, **Images**, **Volumes** et **Réseaux**, le nettoyage
  liste ce qui partira et, pour les images, la place libérée. Le démon nettoie
  ce qui est inutilisé au moment du clic, donc ce qui l'est devenu entre-temps
  part aussi.
- **Nouveau volume** et **Nouveau réseau** sont dans **Volumes** et
  **Réseaux**.
- **Tirer une image** dans **Images** et **Enregistrer dans une image** sur un
  conteneur tournent comme tâches dans **Activité**. Seules les images
  publiques se tirent : un registre qui demande une connexion n'est pas pris en
  charge.

## Ce que Docker n'a pas encore ici

- Un terminal dans un conteneur, et des journaux suivis en direct
- Des métriques sur un tableau de bord, et la recherche
- Un démon atteint par TLS plutôt que par SSH
- Les registres privés, et créer ou lancer de nouveaux conteneurs
