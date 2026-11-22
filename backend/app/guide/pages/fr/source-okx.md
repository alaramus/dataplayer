# OKX

Les données de marché publiques d'OKX : spot, contrats à terme USDT et USDC,
et contrats inversés, perpétuels et datés. Vous voyez la dernière journée et
les règles de chaque symbole, lisez ses bougies, ses transactions des trois
derniers mois et son carnet d'ordres sous forme de lignes, et suivez son
marché en direct. Rien n'est modifié sur OKX, et aucune clé n'est
nécessaire. Le fonctionnement général des connexions est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Spot, contrats USDT et USDC, contrats inversés, symboles par devise de cotation
- Les dernières 24 heures de chaque symbole : prix, variation, haut, bas, volume
- Les règles de chaque symbole : pas de prix et pas de quantité
- Les bougies d'un symbole de tout intervalle, d'une seconde à un mois
- Les transactions d'un symbole des trois derniers mois, par numéro ou date
- Le carnet d'ordres d'un symbole, achats et ventes avec leur cumul
- Le marché d'un symbole en direct : graphique, carnet et transactions
- Chacun d'eux téléchargé en fichier
- L'horloge d'OKX, sa maintenance et la part utilisée de chaque limite
- Les limites et les réponses d'OKX sur un tableau de bord
- Des symboles trouvés par nom ou par actif
- Les transactions ou bougies d'un symbole dans un pipeline, rien que le neuf
- Avec une clé : soldes, positions, ordres, transactions, dépôts, retraits

## Ce que vous pouvez modifier

- Rien : les données de marché sont seulement lues

## Connexion

La page **Connexion** de la fenêtre demande le **Point d'accès** :

- **OKX** — `www.okx.com`, et ses flux sur `ws.okx.com` ;
- **OKX Europe** — `eea.okx.com`, le service européen d'OKX : un marché à
  part, avec ses propres prix et transactions ;
- **Trading de démonstration** — le marché de démonstration d'OKX, avec ses
  propres prix.
- **OKX, avec une clé API**, **OKX Europe, avec une clé API** et **Trading de
  démonstration, avec une clé API** — les mêmes, et en plus le compte auquel
  la clé appartient. Ils demandent la clé, son secret et la phrase secrète
  choisie à sa création.

OKX ne sert pas certains pays, dont les États-Unis. Si la vérification dit
qu'OKX ne dessert pas cette adresse ou cette région, le serveur DataPlayer se
trouve dans l'un d'eux ; OKX Europe ne sert que l'Espace économique européen.

## Le catalogue

- **Bourse** d'abord : ce qu'OKX et cette connexion disent d'eux-mêmes.
- **Marchés** : un dossier par marché listant ses symboles. Une ligne ouvre
  aussitôt son graphique **Marché**.
- **Spot**, **Contrats à terme USDT et USDC** et **Contrats à terme
  inversés**. Les contrats réunissent les swaps perpétuels et les contrats
  datés d'OKX. Chaque marché contient **Tickers**, **Symboles** et un dossier
  par devise de cotation, la plus fournie d'abord.
- Une devise de cotation contient ses symboles, seulement ceux qui se
  négocient. Un perpétuel finit par `-SWAP`, comme `BTC-USDT-SWAP` ; un
  contrat daté par sa date, comme `BTC-USDT-261225`.
- Un symbole contient **Marché**, **Bougies** avec une série par intervalle,
  **Transactions** et **Carnet d'ordres**.

## Marché

**Marché**, le premier nœud de chaque symbole, ouvre un onglet qui bouge avec
le marché : la journée en haut, les bougies au-dessus de leur volume, le
carnet avec la profondeur de chaque niveau, et les transactions à mesure.

- Choisissez l'intervalle des bougies en haut ; faites défiler ou glissez le
  graphique pour remonter.
- Après le premier instant, tout vient des flux d'OKX, qui ne coûtent rien de
  ses limites. Plusieurs onglets d'un symbole les partagent.
- Si le réseau tombe, l'onglet le dit et revient de lui-même.

## Tables

- **Tickers** : une ligne par symbole, les plus actifs d'abord. Chaque
  colonne se trie et se filtre. Rafraîchi toutes les dix secondes. OKX ne
  donne pas de volume coté pour les contrats USDT et USDC : la colonne y
  manque, et les plus actifs sont ceux qui ont le plus de volume en monnaie.
- **Symboles** : une ligne par symbole avec ses règles. Les contrats ajoutent
  le type d'OKX — `SWAP` pour un perpétuel, `FUTURES` pour un daté —,
  l'échéance d'un contrat daté et sa date de cotation. Les contrats inversés
  ajoutent ce que vaut un contrat en USD.
- **Bougies** : les plus récentes d'abord ; triez par **open_time** pour
  partir des plus anciennes, filtrez dessus pour choisir où la lecture
  commence et s'arrête. La bougie encore ouverte dit `closed` false. Jours et
  semaines s'ouvrent à minuit UTC.
- **Transactions** : les plus récentes d'abord. OKX numérote les transactions
  d'un symbole l'une après l'autre et les garde trois mois : filtrez sur
  **id** ou **time** pour choisir où regarder, et triez par **id** pour
  partir des plus anciennes.
- **Carnet d'ordres** : achats du meilleur au pire, puis ventes. Un filtre
  sur **level** choisit la profondeur, jusqu'à 400 ; 100 niveaux par défaut.
  Un filtre sur **side** garde un côté.
- **volume** est toujours dans l'actif de base et **quote_volume** dans la
  devise de cotation. OKX compte les contrats en contrats ; DataPlayer dit
  chacun en ce qu'il vaut. Sur les contrats inversés, la taille d'une
  transaction est en USD : la colonne s'y appelle **quote_quantity**, et la
  quantité du carnet y est aussi en USD.
- Prix et quantités sont des décimaux exacts, tels qu'OKX les écrit.

## Dans un pipeline

Les **Transactions** d'un symbole et chaque série de **Bougies** peuvent
commencer un lien de pipeline qui lit la suite : **Ajouter les nouveaux
messages à une table** ou **à une nouvelle table**, ou **Garder le dernier
par clé**. Chaque exécution ne lit que ce qui est venu depuis la précédente,
et un pipeline activé le porte en quelques secondes.

- DataPlayer garde où chaque lien s'est arrêté ; OKX non.
- **La première exécution lit** : **Seulement le nouveau** commence
  maintenant ; **Depuis le plus ancien disponible** commence par la dernière
  heure de transactions, ou le dernier jour de bougies.
- Une bougie est lue une fois close.
- Un lien qui n'a pas tourné depuis plus de trois mois trouve ses plus
  anciennes transactions effacées par OKX ; l'exécution dit combien ont été
  sautées.
- Une table que le lien crée a pour clé l'**id** de la transaction ou
  l'**open_time** de la bougie : rien n'arrive deux fois.

## Votre compte

Avec une clé, chaque marché contient **Compte** : **Soldes** du compte de
négociation, les mêmes dans chaque marché ; **Positions** pour les contrats ;
**Ordres ouverts** ; et en spot **Dépôts** et **Retraits**. Un symbole ajoute
**Mes ordres** des sept derniers jours et **Mes transactions** des trois
derniers. **Mes transactions** peuvent commencer un lien de pipeline, comme
**Transactions**.

- Créez la clé sur OKX avec la seule permission **Read**. Une clé qui peut
  aussi négocier ou retirer est acceptée et la vérification le dit :
  DataPlayer ne fait que lire, mais une clé en lecture seule est plus sûre.
- Si la clé est limitée à des adresses, ajoutez celle du serveur DataPlayer.
- **Clé API** dans **Bourse** dit ce qu'OKX permet à la clé.

## Bourse

- **Statut** : le point d'accès, si OKX annonce une maintenance de la
  négociation, et si chaque marché répond.
- **Horloge** : l'heure de chaque marché et son avance sur le serveur
  DataPlayer.
- **Limite de requêtes** : pour chaque sorte de requête déjà faite, ce qu'OKX
  permet dans sa fenêtre, ce qui a été utilisé, où DataPlayer s'arrête, et si
  des requêtes sont retenues.
- **Marchés** : combien de symboles se négocient, dans combien de devises de
  cotation, et quand la liste a été lue ; elle est relue après une heure.
- **Clé API** : si la clé est en lecture seule, si elle peut négocier ou
  retirer, et si elle est limitée à des adresses.

## Tableaux de bord et recherche

- Le tableau de bord **Connexion OKX** trace les requêtes de chaque sorte
  dans sa fenêtre face au seuil de DataPlayer, le temps de réponse d'OKX et
  si chaque marché répond. Les prix n'y sont pas : portez-les dans une table
  avec un pipeline et tracez-la.
- La recherche trouve les symboles par nom et par actif : `btc` trouve
  BTC-USDT et ETH-BTC, les noms d'abord. Une recherche dans une devise de
  cotation y reste. Les symboles peuvent être gardés pour la recherche
  globale.

## La limite de requêtes

OKX limite chaque sorte de requête à part : tant en deux secondes — 20 pour
les bougies, 20 pour les transactions, 40 pour le carnet. DataPlayer compte
ses propres requêtes et s'arrête à 40 % de chacune, sans jamais passer 80 %
de deux secondes quelconques ; une requête au-delà attend les deux secondes
suivantes au lieu d'échouer, si bien qu'un long téléchargement prend
quelques secondes de plus. Si OKX refuse quand même l'adresse, cette sorte de
requête attend deux secondes.
