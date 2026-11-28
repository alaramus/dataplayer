# Kubernetes

Un cluster Kubernetes, joint par son serveur d'API : n'importe quel cluster —
le vôtre, k3s, kind ou celui d'un cloud. Vous voyez ses espaces de noms et
chaque type d'objet qu'il sert, personnalisés compris, sous forme des tableaux
du cluster lui-même, ce que le cluster dit de chaque objet, les journaux d'un
pod et les rapports du cluster. Le fonctionnement général des connexions est
décrit à la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Les espaces de noms et chaque type d'objet qu'ils contiennent, groupés
- Les types hors espace de noms : nœuds, volumes, classes et autres
- Les ressources personnalisées, trouvées comme les types intégrés
- Les objets d'un type en tableau, comme `kubectl get`, triés et filtrés
- L'aperçu d'un objet : état, métadonnées, conditions et contenu
- Un objet en YAML ou en arbre JSON
- Les événements d'un objet et les pods qu'une charge ou un service choisit
- Les journaux d'un conteneur, du plus récent au plus ancien
- Le cluster : version, nœuds, pods par phase, événements, ressources d'API

## Ce que vous pouvez modifier

- Deployments, stateful sets et replica sets mis à l'échelle
- Deployments, stateful sets et daemon sets redémarrés, comme rollout restart
- Nœuds isolés, réintégrés et vidés, le vidage en job
- Cron jobs suspendus, repris et lancés maintenant
- Tout objet supprimé, après la simulation du cluster lui-même
- Le YAML d'un objet modifié là où il s'ouvre, et nouveaux objets en YAML

## Connexion

**Se connecter avec** choisit comment DataPlayer se connecte au cluster :

- **Un kubeconfig** : collez le fichier ou lisez-le depuis le disque avec le
  bouton à côté du champ. Les certificats et les clés doivent y figurer, et
  non être nommés comme fichiers ; `kubectl config view --minify --flatten`
  en écrit un ainsi. **Contexte** nomme le contexte à utiliser ; vide, c'est
  le contexte courant du fichier.
- **Un jeton** : l'adresse `https://` du **Serveur d'API**, son **Certificat
  de l'AC** et un **Jeton** bearer, celui d'un compte de service par exemple.
- **Un certificat client** : le serveur d'API, son AC, ainsi qu'un
  **Certificat client** et une **Clé client** que le cluster accepte. La clé
  ne doit pas être chiffrée.

Laissez **Certificat de l'AC** vide seulement pour un serveur dont le
certificat est signé par une autorité publique. Laissez **Espace de noms**
vide pour voir tous ceux que vous pouvez lister ; nommez-en un si votre compte
ne peut travailler que dans celui-ci.

Certains kubeconfig sont refusés, chacun avec sa raison :

- ceux qui se connectent en exécutant un programme — `gke-gcloud-auth-plugin`,
  `aws`, `kubelogin` et autres : DataPlayer n'exécute rien sur son serveur ;
- ceux qui nomment des fichiers au lieu d'en contenir les données ;
- ceux qui désactivent la vérification du certificat du serveur ;
- ceux qui se connectent par nom d'utilisateur et mot de passe, retirés de
  Kubernetes.

Ne choisissez un **Tunnel SSH** que si le serveur d'API n'est joignable que
depuis un autre réseau. Le cluster doit exécuter Kubernetes 1.27 ou plus
récent.

## Le catalogue

- **Cluster** contient les rapports du cluster, décrits plus bas.
- **Espaces de noms** liste chaque espace de noms, en commençant par **Tous
  les espaces de noms**, qui montre chaque type sur l'ensemble avec une
  colonne **Namespace**.
- Dans un espace de noms, ses types sont groupés : **Charges de travail**,
  **Réseau**, **Configuration**, **Stockage** et **Autres**. Autres contient
  chaque type que sert le cluster hors des plus connus, ressources
  personnalisées comprises, chacun nommé avec son groupe d'API.
- **Ressources du cluster** contient les types hors espace de noms, groupés de
  la même façon, avec **Cluster** pour les nœuds, les espaces de noms et les
  définitions.
- Un type s'ouvre en tableau dont les colonnes sont celles que `kubectl get`
  affiche pour lui, avec **Created** à la place de l'âge, pour pouvoir trier.
  Dans le catalogue, chaque objet affiche ses premières colonnes à côté de son
  nom, par exemple `1/1 · Running`. Au-delà de dix mille objets d'un type,
  rien n'est listé.

## Comment s'ouvre un objet

- Cliquez sur un objet pour ouvrir son aperçu : type, espace de noms,
  création, propriétaires et état, puis ce pour quoi on lit ce type — le
  nœud, les adresses et les conteneurs d'un pod avec leurs images, états et
  redémarrages ; les réplicas souhaités, prêts et à jour d'un deployment ; le
  type, les adresses et les ports d'un service ; les versions et la capacité
  d'un nœud ; la classe et la taille d'une demande de volume — puis ses
  conditions, ses labels et ses annotations.
- L'en-tête de l'aperçu ouvre l'objet **En YAML** ou **En JSON** dans un
  onglet à part. Les champs où Kubernetes garde qui a modifié quoi sont
  omis.
- Ses pages s'ouvrent en tableaux dans des onglets à part : les
  **Événements** le concernant ; les **Pods** qu'un deployment, un stateful
  set, un daemon set, un replica set, un job ou un service choisit ; et les
  **Journaux** d'un pod, une page par conteneur : heure et texte, du plus
  récent au plus ancien, jusqu'à dix mille lignes, chacune coupée à 16 Ko.
- **Les valeurs d'un secret ne sont jamais affichées.** Son aperçu liste ses
  clés et leur taille, et son YAML et son JSON mettent une taille à la place
  de chaque valeur.

## La section Cluster

- **Vue d'ensemble** : la version, le serveur, le contexte, qui vous êtes pour
  le cluster, les nœuds prêts, les plateformes, le nombre d'espaces de noms et
  de pods dans chaque phase.
- **Nœuds** : l'état, les rôles, les versions, l'adresse, le système, le
  moteur, la capacité, ce qui est allouable et les taints de chaque nœud.
- **Événements** : ce que le cluster a enregistré récemment, du plus récent
  au plus ancien.
- **Ressources d'API** : chaque type que sert le cluster, son groupe, sa
  version, sa portée et ses verbes.

## Quand quelque chose est refusé

- Un serveur d'API injoignable, un certificat non approuvé, ou un jeton ou
  un certificat non accepté arrête toute la connexion, et chaque écran dit
  pourquoi.
- Les règles d'accès du cluster peuvent refuser une seule requête. C'est dit
  par **Le cluster ne permet pas à cette connexion** avec ce qui était
  demandé, par exemple `list secrets` ; le reste du cluster reste lisible.

## Modifier

Le menu au-dessus d'un objet et les icônes de l'en-tête de son aperçu
n'offrent que ce que le cluster permet à votre compte : une action que ses
règles d'accès refuseraient n'est pas proposée. Mettre à l'échelle,
redémarrer, isoler et suspendre demandent l'accès en écriture à la connexion ;
supprimer, vider et créer des objets demandent l'accès à la structure.

- **Mettre à l'échelle** demande le nombre de réplicas, l'actuel déjà rempli,
  et décrit le changement avant de le faire.
- **Redémarrer** remplace les pods d'une charge un par un, comme
  `kubectl rollout restart`.
- **Isoler** et **Réintégrer** empêchent ou permettent l'arrivée de nouveaux
  pods sur un nœud. **Vider** isole le nœud et évince ses pods un par un dans
  un job de l'**Activité** ; les pods de DaemonSet et statiques restent, un pod
  avec des données `emptyDir` attend la case qui dit que ces données sont
  perdues, et un budget de perturbation est attendu le nombre de secondes
  indiqué.
- **Suspendre**, **Reprendre** et **Lancer maintenant** agissent sur un cron
  job ; Lancer maintenant crée un job depuis son modèle, comme
  `kubectl create job --from`.
- **Supprimer** laisse d'abord le cluster simuler la suppression et dit ce qui
  possède l'objet et le recréera ; choisissez ce que devient ce qu'il possède.
- **En YAML** ouvre un objet pour le modifier. L'enregistrement ne le renvoie
  que si personne ne l'a modifié depuis son ouverture ; sinon relisez-le et
  modifiez-le de nouveau. Son type, son nom et son espace de noms restent
  inchangés. Un secret n'est pas modifié ici.
- **Nouveau depuis YAML**, sur un espace de noms ou un type, prend un ou
  plusieurs objets. Le cluster simule d'abord chacun et le formulaire montre ce
  qui serait créé ou modifié, ou pourquoi un objet est refusé ; ils sont
  ensuite appliqués dans l'ordre.

## Ce que Kubernetes n'a pas encore ici

- Un terminal dans un conteneur, des journaux à jour
- Les métriques sur un tableau de bord, la recherche, une base du cluster
- La connexion à Google Kubernetes Engine avec un compte Google Cloud
- Les valeurs d'un secret, montrées sur demande
