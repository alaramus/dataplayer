# Bybit

Les données de marché publiques de Bybit : spot, contrats à terme USDT et
USDC, et contrats inversés. Vous voyez la dernière journée et les règles de
chaque symbole, lisez ses bougies, ses dernières transactions et son carnet
d'ordres sous forme de lignes, et suivez son marché en direct. Rien n'est
modifié sur Bybit, et aucune clé n'est nécessaire. Le fonctionnement général
des connexions est décrit sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Spot, contrats USDT et USDC, contrats inversés, symboles par devise de cotation
- Les dernières 24 heures de chaque symbole : prix, variation, haut, bas, volume
- Les règles de chaque symbole : pas de prix, pas de quantité, ordre minimal
- Les bougies d'un symbole de tout intervalle, d'une minute à un mois
- Les dernières transactions d'un symbole : 60 en spot, 1 000 en contrats
- Le carnet d'ordres d'un symbole, achats et ventes avec leur cumul
- Le marché d'un symbole en direct : graphique, carnet et transactions
- Chacun d'eux téléchargé en fichier
- L'horloge de Bybit et la part utilisée de la limite de requêtes
- La limite de requêtes et les réponses de Bybit sur un tableau de bord
- Des symboles trouvés par nom ou par actif
- Les transactions ou bougies d'un symbole dans un pipeline, rien que le neuf
- Avec une clé : soldes, positions, ordres, transactions, dépôts, retraits

## Ce que vous pouvez modifier

- Rien : les données de marché sont seulement lues

## Connexion

La page **Connexion** de la fenêtre demande le **Point d'accès** :

- **Bybit** — `api.bybit.com`, et ses flux sur `stream.bybit.com` ;
- **Bybit, via bytick.com** — le même service sous son second nom, pour un
  réseau qui n'atteint pas le premier ;
- **Testnet** — le réseau de test de Bybit, avec ses propres prix.
- **Bybit, avec une clé API** et **Testnet, avec une clé API** — les mêmes
  hôtes, et en plus le compte unifié auquel la clé appartient.

Bybit ne sert pas certains pays, dont les États-Unis. Si la vérification dit
que Bybit ne dessert pas cette région ou refuse cette adresse, le serveur
DataPlayer se trouve dans l'un d'eux, et un autre point d'accès n'y changera
rien.

## Le catalogue

- **Bourse** d'abord : ce que Bybit et cette connexion disent d'eux-mêmes.
- **Marchés** : un dossier par marché listant ses symboles. Une ligne ouvre
  aussitôt son graphique **Marché**.
- **Spot**, **Contrats à terme USDT et USDC** et **Contrats à terme
  inversés**. Chacun contient **Tickers**, **Symboles** et un dossier par
  devise de cotation, la plus fournie d'abord.
- Une devise de cotation contient ses symboles, seulement ceux qui se
  négocient. Les contrats datés portent leur échéance dans le nom, comme
  `BTCUSDT-27NOV26`.
- Un symbole contient **Marché**, **Bougies** avec une série par intervalle,
  **Transactions** et **Carnet d'ordres**.

## Marché

**Marché**, le premier nœud de chaque symbole, ouvre un onglet qui bouge avec
le marché : la journée en haut, les bougies au-dessus de leur volume, le
carnet avec la profondeur de chaque niveau, et les transactions à mesure.

- Choisissez l'intervalle des bougies en haut ; faites défiler ou glissez le
  graphique pour remonter.
- Après le premier instant, tout vient des flux de Bybit, qui ne coûtent rien
  de la limite de requêtes. Plusieurs onglets d'un symbole partagent un flux.
- Si le réseau tombe, l'onglet le dit et revient de lui-même.

## Tables

- **Tickers** : une ligne par symbole, les plus actifs en volume coté
  d'abord. Chaque colonne se trie et se filtre. Rafraîchi toutes les dix
  secondes.
- **Symboles** : une ligne par symbole avec ses règles. Les contrats ajoutent
  le type de contrat de Bybit, l'échéance d'un contrat daté et sa date de
  cotation.
- **Bougies** : les plus récentes d'abord ; triez par **open_time** pour
  partir des plus anciennes, filtrez dessus pour choisir où la lecture
  commence et s'arrête. La bougie encore ouverte dit `closed` false.
- **Transactions** : seulement les plus récentes que Bybit donne — 60 en
  spot, 1 000 en contrats, moins d'une minute pour un symbole actif. Chaque
  colonne se trie et se filtre. Bybit ne donne pas de transactions plus
  anciennes.
- **Carnet d'ordres** : achats du meilleur au pire, puis ventes. Un filtre
  sur **level** choisit la profondeur, jusqu'à 1 000 ; 100 niveaux par
  défaut. Un filtre sur **side** garde un côté.
- **volume** est toujours dans l'actif de base et **quote_volume** dans la
  devise de cotation. Les contrats inversés comptent en USD, et DataPlayer
  met chacun à sa place.
- Prix et quantités sont des décimaux exacts, tels que Bybit les écrit.

## Dans un pipeline

Les **Transactions** d'un symbole et chaque série de **Bougies** peuvent
commencer un lien de pipeline qui lit la suite : **Ajouter les nouveaux
messages à une table** ou **à une nouvelle table**, ou **Garder le dernier
par clé**. Chaque exécution ne lit que ce qui est venu depuis la précédente,
et un pipeline activé le porte en quelques secondes.

- DataPlayer garde où chaque lien s'est arrêté ; Bybit non.
- **La première exécution lit** : **Seulement le nouveau** commence
  maintenant ; **Depuis le plus ancien disponible** commence par les
  transactions que Bybit donne encore, ou le dernier jour de bougies.
- Une bougie est lue une fois close.
- Bybit ne donne que ses transactions les plus récentes : un lien qui tourne
  moins souvent qu'un symbole actif ne fait mille transactions en manque, et
  l'exécution dit que des transactions ont été sautées. Activez le pipeline
  pour les porter à mesure.
- Une table que le lien crée a pour clé l'**id** de la transaction ou
  l'**open_time** de la bougie : rien n'arrive deux fois.

## Votre compte

Avec une clé, chaque marché contient **Compte** : **Soldes** du portefeuille
unifié, les mêmes dans chaque marché ; **Positions** pour les contrats ;
**Ordres ouverts** ; et en spot **Dépôts** et **Retraits** des trente derniers
jours. Un symbole ajoute **Mes ordres** et **Mes transactions** des sept
derniers jours. **Mes transactions** peuvent commencer un lien de pipeline,
comme **Transactions**.

- Créez la clé sur Bybit en lecture seule. Une clé qui peut aussi négocier ou
  déplacer de l'argent est acceptée et la vérification le dit : DataPlayer ne
  fait que lire, mais une clé en lecture seule est plus sûre.
- Si la clé est limitée à des adresses, ajoutez celle du serveur DataPlayer.
- **Clé API** dans **Bourse** dit ce que Bybit permet à la clé.
- Les retraits ne sont donnés qu'à la clé du compte principal.

## Bourse

- **Statut** : le point d'accès, et si chaque marché répond.
- **Horloge** : l'heure de chaque marché et son avance sur le serveur
  DataPlayer.
- **Limite de requêtes** : ce que Bybit permet à cette adresse en cinq
  secondes, ce qui a été utilisé, où DataPlayer s'arrête, et si des requêtes
  sont retenues.
- **Marchés** : combien de symboles se négocient, dans combien de devises de
  cotation, et quand la liste a été lue ; elle est relue après une heure.
- **Clé API** : si la clé est en lecture seule, ce que Bybit lui permet, et
  si elle est limitée à des adresses.

## Tableaux de bord et recherche

- Le tableau de bord **Connexion Bybit** trace les requêtes par tranche de
  cinq secondes face au seuil de DataPlayer, le temps de réponse de Bybit et
  si chaque marché répond. Les prix n'y sont pas : portez-les dans une table
  avec un pipeline et tracez-la.
- La recherche trouve les symboles par nom et par actif : `btc` trouve
  BTCUSDT et ETHBTC, les noms d'abord. Une recherche dans une devise de
  cotation y reste. Les symboles peuvent être gardés pour la recherche
  globale.

## La limite de requêtes

Bybit permet à une adresse 600 requêtes en cinq secondes sur tous ses
marchés, et bloque au moins dix minutes une adresse qui en demande plus.
DataPlayer compte ses propres requêtes et s'arrête à 240 en cinq secondes, en
disant combien attendre. Si Bybit bloque quand même l'adresse, rien n'est
demandé avant la fin du blocage.
