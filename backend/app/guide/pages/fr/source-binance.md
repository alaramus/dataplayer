# Binance

Les données de marché publiques de Binance : spot et contrats à terme
USDⓈ-M et COIN-M. Vous voyez la dernière journée et les règles de négociation de chaque
symbole, et lisez en lignes les bougies, les transactions et le carnet
d'ordres d'un symbole. Rien n'est modifié sur Binance, et aucune clé n'est
nécessaire. Le fonctionnement des connexions en général est décrit sur la
page [Connexions](connections.md).

## Ce que vous pouvez voir

- Le spot, les contrats USDⓈ-M et COIN-M, symboles par devise de cotation
- Les dernières 24 heures de chaque symbole : prix, variation, haut, bas, volume
- Les règles de chaque symbole : pas de prix, pas de quantité, ordre minimal
- Les bougies d'un symbole de tout intervalle, d'une seconde à un mois
- Les transactions d'un symbole, récentes d'abord, par id ou depuis une heure
- Le carnet d'ordres d'un symbole, achats et ventes avec leurs cumuls
- Chacun d'eux téléchargé en fichier
- L'état de Binance, son horloge et la part de la limite de requêtes utilisée
- La limite de requêtes et les réponses de Binance sur un tableau de bord
- Les symboles trouvés par nom ou par devise
- Les transactions ou bougies d'un symbole transportées par un pipeline

## Ce que vous pouvez modifier

- Rien : les données de marché sont seulement lues

## Connexion

La page **Connexion** de la fenêtre demande le **Point d'accès** :

- **Binance** — les hôtes principaux, `api.binance.com`, `fapi.binance.com` et
  `dapi.binance.com` ;
- **Binance, données de marché seulement** — le spot depuis
  `data-api.binance.vision`, qui ne sert que des données publiques et répond
  souvent quand l'hôte principal est chargé ;
- **Réseau de test** — le réseau de test de Binance, avec ses propres prix.

Binance refuse certains pays. Si la vérification dit que Binance ne sert pas
cette adresse, le serveur DataPlayer se trouve dans l'un d'eux, et un autre
point d'accès n'y changera rien.

## Le catalogue

- D'abord **Bourse** : ce que Binance et cette connexion disent d'eux-mêmes.
- **Spot**, **Contrats à terme USDⓈ-M** et **Contrats à terme COIN-M**.
  Chacun contient **Tickers**,
  **Symboles** et un dossier par devise de cotation — **USDT**, **USDC**,
  **BTC** et les autres —, celui qui a le plus de symboles en premier.
- Une devise de cotation contient ses symboles : seulement ceux qui se
  négocient maintenant.
- Un symbole contient **Bougies**, avec une série par intervalle,
  **Transactions** et **Carnet d'ordres**.

## Tables

- **Tickers** : une ligne par symbole, le plus actif en volume de cotation
  d'abord. Chaque colonne se trie et se filtre. Se rafraîchit toutes les dix
  secondes.
- **Symboles** : une ligne par symbole avec ses règles. Les contrats à terme
  ajoutent le type de contrat, sa date de livraison et sa date de cotation.
- **Bougies** : les plus récentes d'abord ; trier par **open_time** commence
  par les plus anciennes, et un filtre dessus choisit où la lecture commence
  et s'arrête. La bougie encore ouverte a `closed` à false.
- **Transactions** : les transactions agrégées de Binance, les plus récentes
  d'abord. Un filtre sur **id** ou **time** choisit où la lecture commence.
  Binance garde environ deux ans de transactions spot, et ne donne les
  transactions des contrats à terme que sur les deux derniers jours.
- **Carnet d'ordres** : les meilleurs achats d'abord, puis les meilleures
  ventes. Un filtre sur **level** choisit la profondeur, 100 niveaux par
  défaut. Un filtre sur **side** garde un seul côté.
- Une page de bougies ou de transactions va au plus à dix mille lignes de
  profondeur. Pour remonter plus loin, filtrez par heure.
- Les prix et les quantités sont des décimaux exacts, tels que Binance les
  écrit.
- **COIN-M** compte en contrats de 100 USD pour BTC et 10 USD pour les
  autres. Ses tickers et bougies donnent quand même **volume** dans l'actif
  de base et **quote_volume** en USD, comme tout marché ; **Symboles**
  ajoute **contract_size**. La **quantity** d'une transaction ou du carnet
  est en contrats.

## Dans un pipeline

Les **Transactions** d'un symbole et chaque série de **Bougies** peuvent être
le début d'un lien de pipeline qui lit à la suite : **Ajouter les nouveaux
messages à une table** ou **à une nouvelle table**, ou **Garder le plus
récent par clé**. Chaque exécution ne lit que ce qui est arrivé depuis la
précédente, et **Suivre** le transporte en quelques secondes.

- DataPlayer garde l'endroit où chaque lien s'est arrêté ; Binance non.
- **La première exécution lit** : **Seulement ce qui est nouveau** commence
  maintenant ; **Depuis le plus ancien disponible** commence par la dernière
  heure de transactions ou le dernier jour de bougies.
- Une bougie est lue une fois fermée.
- Une table créée par le lien a une clé sur l'**id** de la transaction ou
  l'**open_time** de la bougie, si bien que rien n'arrive deux fois.
- Les tickers, les symboles et le carnet d'ordres sont un instant, pas un
  historique : un lien les prend en entier à chaque exécution.

## Bourse

- **État** : le point d'accès, l'état propre de Binance — connu seulement sur
  le point d'accès principal — et si chaque marché répond.
- **Horloge** : l'heure de chaque marché et son avance sur le serveur
  DataPlayer. Les heures envoyées à Binance sont celles du serveur, un grand
  écart les décale.
- **Limite de requêtes** : ce que chaque marché permet par minute, ce que
  cette adresse a utilisé cette minute, où DataPlayer s'arrête et si Binance
  retient les requêtes.
- **Marchés** : combien de symboles se négocient, dans combien de devises de
  cotation, et quand la liste a été lue ; elle est relue au bout d'une heure.

## Tableaux de bord et recherche

- Le tableau de bord **Connexion Binance** trace le poids utilisé chaque
  minute face au seuil de DataPlayer, le temps de réponse de Binance et si
  chaque marché répond. Les prix n'y sont pas : transportez-les dans une table
  avec un pipeline et tracez-la.
- La recherche trouve les symboles par nom et par devise : `btc` trouve
  BTCUSDT et ETHBTC, les noms d'abord. Une recherche dans une devise de
  cotation s'y tient. Les symboles peuvent être gardés pour la recherche sur
  tout.

## La limite de requêtes

Binance compte ce que chaque adresse lui demande par minute et bloque une
adresse qui en demande trop. DataPlayer lit ce compte dans chaque réponse et
s'arrête à 80 % de la limite, en disant combien de secondes il reste dans la
minute. Si Binance bloque quand même l'adresse, rien n'est demandé avant la
fin du blocage.
