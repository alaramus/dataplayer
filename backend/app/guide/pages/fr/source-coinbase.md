# Coinbase Exchange

Les données de marché publiques de Coinbase Exchange : ses produits spot.
Vous voyez la dernière journée et les règles de chaque produit, lisez ses
bougies, toutes ses transactions depuis le début et son carnet d'ordres sous
forme de lignes, et suivez son marché en direct. Rien n'est modifié sur
Coinbase, et aucune clé n'est nécessaire. Le fonctionnement général des
connexions est décrit sur la page [Connexions](connections.md).

## Ce que vous pouvez voir

- Les produits spot par devise de cotation
- Les dernières 24 heures de chaque produit : prix, variation, haut, bas, volume
- Les règles de chaque produit : pas de prix, pas de quantité, ordre minimal
- Les bougies d'un produit : 1 et 5 minutes, 15 minutes, 1 et 6 heures, un jour
- Toutes les transactions d'un produit depuis sa cotation, par numéro
- Le carnet d'ordres d'un produit, achats et ventes avec leur cumul
- Le marché d'un produit en direct : graphique, carnet et transactions
- Chacun d'eux téléchargé en fichier
- L'horloge de Coinbase et la part utilisée de la limite de requêtes
- La limite de requêtes et les réponses de Coinbase sur un tableau de bord
- Des produits trouvés par nom ou par actif
- Les transactions ou bougies d'un produit dans un pipeline, rien que le neuf
- Avec une clé : soldes, ordres ouverts, vos ordres et transactions

## Ce que vous pouvez modifier

- Rien : les données de marché sont seulement lues

## Connexion

La page **Connexion** de la fenêtre demande le **Point d'accès** :

- **Coinbase Exchange** — `api.exchange.coinbase.com`, et son flux sur
  `ws-feed.exchange.coinbase.com` ;
- **Bac à sable** — le bac à sable public de Coinbase, avec ses propres prix.
- **Coinbase Exchange, avec une clé API** — la même chose, et votre compte
  Coinbase en plus. Elle demande le **nom** de la clé et sa **clé privée**,
  tels que la Coinbase Developer Platform les donne.

## Le catalogue

- **Bourse** d'abord : ce que Coinbase et cette connexion disent d'eux-mêmes.
- **Marchés** : un dossier listant tous les produits. Une ligne ouvre aussitôt
  son graphique **Marché**.
- **Spot** contient **Tickers**, **Symboles** et un dossier par devise de
  cotation, la plus fournie d'abord.
- Une devise de cotation contient ses produits, seulement ceux qui se
  négocient, comme `BTC-USD`.
- Un produit contient **Marché**, **Bougies** avec une série par intervalle,
  **Transactions** et **Carnet d'ordres**.

## Marché

**Marché**, le premier nœud de chaque produit, ouvre un onglet qui bouge avec
le marché : la journée en haut, les bougies au-dessus de leur volume, le
carnet avec la profondeur de chaque niveau, et les transactions à mesure.

- Choisissez l'intervalle des bougies en haut ; faites défiler ou glissez le
  graphique pour remonter.
- Après le premier instant, tout vient du flux de Coinbase, qui ne coûte rien
  de la limite de requêtes. Coinbase n'y envoie pas de bougies : DataPlayer
  trace la bougie encore ouverte à partir des transactions.
- Si le réseau tombe, l'onglet le dit et revient de lui-même.

## Tables

- **Tickers** : une ligne par produit, ceux au plus fort volume d'abord.
  Chaque colonne se trie et se filtre. Rafraîchi toutes les dix secondes.
  Coinbase ne donne le volume du jour que dans l'actif de base : il n'y a pas
  de **quote_volume**.
- **Symboles** : une ligne par produit avec ses règles.
- **Bougies** : les plus récentes d'abord ; triez par **open_time** pour
  partir des plus anciennes, filtrez dessus pour choisir où la lecture
  commence et s'arrête. La bougie encore ouverte dit `closed` false. Coinbase
  ne donne pas de bougie pour un intervalle sans transaction.
- **Transactions** : les plus récentes d'abord. Coinbase numérote les
  transactions d'un produit l'une après l'autre depuis la première et les
  garde toutes : filtrez sur **id** pour choisir où regarder, et triez par
  **id** pour partir de la toute première. Coinbase ne sait pas trouver une
  transaction par sa date : **time** ne se filtre pas.
- **Carnet d'ordres** : achats du meilleur au pire, puis ventes. Un filtre sur
  **level** choisit la profondeur, jusqu'à 1 000 ; 100 niveaux par défaut. Un
  filtre sur **side** garde un côté.
- **volume** est toujours dans l'actif de base. Prix et quantités sont des
  décimaux exacts, tels que Coinbase les écrit.

## Dans un pipeline

Les **Transactions** d'un produit et chaque série de **Bougies** peuvent
commencer un lien de pipeline qui lit la suite : **Ajouter les nouveaux
messages à une table** ou **à une nouvelle table**, ou **Garder le dernier
par clé**. Chaque exécution ne lit que ce qui est venu depuis la précédente,
et un pipeline activé le porte en quelques secondes.

- DataPlayer garde où chaque lien s'est arrêté ; Coinbase non.
- **La première exécution lit** : **Seulement le nouveau** commence
  maintenant ; **Depuis le plus ancien disponible** commence par le dernier
  millier de transactions, ou le dernier jour de bougies.
- Une bougie est lue une fois son intervalle terminé.
- Coinbase garde toutes les transactions : un lien resté longtemps à l'arrêt
  n'en manque aucune.
- Une table que le lien crée a pour clé l'**id** de la transaction ou
  l'**open_time** de la bougie : rien n'arrive deux fois.

## Votre compte

Avec une clé, **Spot** contient **Compte** : les **Soldes** de votre compte
Coinbase et les **Ordres ouverts**. Un produit ajoute **Mes ordres** et **Mes
transactions**. **Mes transactions** peuvent commencer un lien de pipeline,
comme **Transactions**.

- Créez la clé sur la Coinbase Developer Platform avec la seule permission
  **View** et l'algorithme de signature **ECDSA**. Une clé qui peut aussi
  négocier ou déplacer de l'argent est acceptée et la vérification le dit :
  DataPlayer ne fait que lire, mais une clé en lecture seule est plus sûre.
- Collez la clé privée entière, de `-----BEGIN` jusqu'à la fin.
- **Clé API** dans **Bourse** dit ce que Coinbase permet à la clé.

## Bourse

- **Statut** : le point d'accès, et si Coinbase répond.
- **Horloge** : l'heure de Coinbase et son avance sur le serveur DataPlayer.
- **Limite de requêtes** : ce que Coinbase permet à cette adresse en une
  seconde, ce qui a été utilisé, où DataPlayer s'arrête, et si des requêtes
  sont retenues.
- **Marchés** : combien de produits se négocient, dans combien de devises de
  cotation, et quand la liste a été lue ; elle est relue après une heure.
- **Clé API** : si la clé peut consulter, négocier ou déplacer de
  l'argent, et son portefeuille.

## Tableaux de bord et recherche

- Le tableau de bord **Connexion Coinbase** trace les requêtes de chaque
  seconde face au seuil de DataPlayer, le temps de réponse de Coinbase et s'il
  répond. Les prix n'y sont pas : portez-les dans une table avec un pipeline
  et tracez-la.
- La recherche trouve les produits par nom et par actif : `eth` trouve
  ETH-USD et ETH-BTC. Une recherche dans une devise de cotation y reste. Les
  produits peuvent être gardés pour la recherche globale.

## La limite de requêtes

Coinbase permet à une adresse dix requêtes publiques par seconde. DataPlayer
compte ses propres requêtes et s'arrête à quatre par seconde, sans jamais
passer huit dans une seconde quelconque ; une requête au-delà attend la
seconde suivante au lieu d'échouer, si bien qu'un long téléchargement prend
quelques secondes de plus. Si Coinbase refuse quand même l'adresse, les
requêtes attendent une seconde.
