"""Ce que les actions et les rapports TimescaleDB écrivent, en français (D226).

Les termes suivent le glossaire des écrans ; les noms de fonctions et d'options
propres à TimescaleDB restent inchangés.
"""

MESSAGES: dict[str, str] = {
    # Longueurs, telles qu'une prévisualisation les affiche.
    "{amount} second": "{amount} seconde",
    "{amount} seconds": "{amount} secondes",
    "{amount} minute": "{amount} minute",
    "{amount} minutes": "{amount} minutes",
    "{amount} hour": "{amount} heure",
    "{amount} hours": "{amount} heures",
    "{amount} day": "{amount} jour",
    "{amount} days": "{amount} jours",
    "{amount} week": "{amount} semaine",
    "{amount} weeks": "{amount} semaines",
    "{amount} month": "{amount} mois",
    "{amount} months": "{amount} mois",
    "{amount} year": "{amount} an",
    "{amount} years": "{amount} ans",
    "{amount} value": "{amount} valeur",
    "{amount} values": "{amount} valeurs",
    # Rapports.
    "Hypertables": "Hypertables",
    "Hypertable owners, dimension/chunk counts and compression configuration": (
        "Propriétaires des hypertables, nombre de dimensions et de chunks, "
        "configuration de la compression"
    ),
    "Continuous aggregates": "Agrégats continus",
    "Aggregate owners, source/materialization identities and configuration": (
        "Propriétaires des agrégats, identités de la source et de la matérialisation, configuration"
    ),
    "Chunks": "Chunks",
    "Chunk identities, primary-dimension boundaries and compression status": (
        "Identités des chunks, limites de la dimension principale et état de la compression"
    ),
    "Dimensions": "Dimensions",
    "Time, integer and space dimensions of each hypertable": (
        "Dimensions temporelles, entières et spatiales de chaque hypertable"
    ),
    "Policies and jobs": "Politiques et tâches",
    "Native TimescaleDB jobs, including policies and their schedules": (
        "Tâches natives de TimescaleDB, y compris les politiques et leurs planifications"
    ),
    "Job statistics": "Statistiques des tâches",
    "Recorded native job runs, outcomes and counters; unrun jobs may be absent": (
        "Exécutions natives enregistrées, résultats et compteurs ; les tâches jamais exécutées peuvent être absentes"
    ),
    "Detached chunks": "Chunks détachés",
    "Tables named like a chunk that no hypertable holds; Attach chunk takes one back": (
        "Tables nommées comme un chunk et rattachées à aucune hypertable ; "
        "« Attacher une table comme chunk » en récupère une"
    ),
    "This report cannot be inspected by this connection": "Cette connexion n'a pas le droit de consulter ce rapport",
    "The installed TimescaleDB lacks the public API for this view": (
        "Le TimescaleDB installé n'a pas l'API publique pour cette vue"
    ),
    # Détecter TimescaleDB.
    "TimescaleDB is not installed on this database": "TimescaleDB n'est pas installé sur cette base de données",
    "This source has no usable TimescaleDB API": "Cette source n'a pas d'API TimescaleDB utilisable",
    "This connection may not inspect installed extensions": (
        "Cette connexion n'a pas le droit de consulter les extensions installées"
    ),
    "Installed extensions could not be inspected": "Les extensions installées n'ont pas pu être consultées",
    "The installed TimescaleDB version could not be read": "La version installée de TimescaleDB n'a pas pu être lue",
    "TimescaleDB extension metadata could not be read": "Les métadonnées de l'extension TimescaleDB n'ont pas pu être lues",
    "This TimescaleDB major version is not supported": "Cette version majeure de TimescaleDB n'est pas prise en charge",
    "This connection may not inspect TimescaleDB metadata": "Cette connexion n'a pas le droit de consulter les métadonnées TimescaleDB",
    "TimescaleDB metadata could not be inspected": "Les métadonnées TimescaleDB n'ont pas pu être consultées",
    "The installed version lacks the supported inspection API": (
        "La version installée n'a pas l'API de consultation prise en charge"
    ),
    "TimescaleDB action vocabulary could not be inspected": "Les actions TimescaleDB disponibles n'ont pas pu être déterminées",
    "The TimescaleDB {routine} API is not usable by this connection": (
        "L'API TimescaleDB {routine} n'est pas utilisable par cette connexion"
    ),
    "The TimescaleDB {type} type is not usable by this connection": (
        "Le type TimescaleDB {type} n'est pas utilisable par cette connexion"
    ),
    "This connection may not lock TimescaleDB public metadata": (
        "Cette connexion n'a pas le droit de verrouiller les métadonnées publiques TimescaleDB"
    ),
    # Les faits TimescaleDB d'une relation.
    "TimescaleDB metadata no longer identifies this relation uniquely": (
        "Les métadonnées TimescaleDB n'identifient plus cette relation de façon unique"
    ),
    "TimescaleDB metadata inspection timed out": "Le délai de lecture des métadonnées TimescaleDB a été dépassé",
    "TimescaleDB metadata could not be inspected safely": "Les métadonnées TimescaleDB n'ont pas pu être consultées de façon sûre",
    "TimescaleDB size inspection timed out": "Le délai de détermination de la taille dans TimescaleDB a été dépassé",
    "TimescaleDB compression inspection timed out": "Le délai de lecture des statistiques de compression TimescaleDB a été dépassé",
    "TimescaleDB size could not be inspected safely": "La taille dans TimescaleDB n'a pas pu être déterminée de façon sûre",
    "TimescaleDB compression statistics could not be inspected safely": (
        "Les statistiques de compression TimescaleDB n'ont pas pu être lues de façon sûre"
    ),
    # Les tables qu'une action prend.
    "Choose one user hypertable": "Choisissez une hypertable utilisateur",
    "Choose one user continuous aggregate": "Choisissez un agrégat continu utilisateur",
    "Choose an owned hypertable": "Choisissez une hypertable dont vous êtes propriétaire",
    "Choose an owned hypertable with one time dimension": (
        "Choisissez une hypertable avec une dimension temporelle dont vous êtes propriétaire"
    ),
    "Choose an owned hypertable partitioned by time": (
        "Choisissez une hypertable partitionnée par le temps dont vous êtes propriétaire"
    ),
    "Choose an owned continuous aggregate": "Choisissez un agrégat continu dont vous êtes propriétaire",
    "Only timestamp and date dimensions are supported here": "Seules les dimensions de type timestamp et date sont prises en charge ici",
    "Only a hypertable with one range dimension is maintained here": (
        "Seules les hypertables avec une dimension de plage sont maintenues ici"
    ),
    "Only timestamp, date and integer dimensions are supported here": (
        "Seules les dimensions de type timestamp, date et entières sont prises en charge ici"
    ),
    "Only aggregates over timestamp and date dimensions are supported here": (
        "Seuls les agrégats sur des dimensions de type timestamp et date sont pris en charge ici"
    ),
    # Vérifier et appliquer un plan.
    "The operation plan changed; review it again": "Le plan de l'opération a changé ; vérifiez-le à nouveau",
    "Validation timed out; review the plan again": "Le délai de validation a été dépassé ; vérifiez le plan à nouveau",
    "The source changed or is busy; review the plan again": "La source a changé ou est occupée ; vérifiez le plan à nouveau",
    "The change could not be confirmed; reload the source before reviewing again": (
        "Le changement n'a pas pu être confirmé ; rechargez la source avant de vérifier à nouveau"
    ),
    "The change ran past its {seconds} seconds and was rolled back": (
        "Le changement a dépassé ses {seconds} secondes et a été annulé"
    ),
    "This connection may not make this change or lock its metadata": (
        "Cette connexion n'a pas le droit d'effectuer ce changement ni de verrouiller ses métadonnées"
    ),
    "The source refused the change": "La source a refusé le changement",
    "Runs in Activity, one such job per connection at a time; access is checked again before every chunk": (
        "S'exécute dans Activité, une telle tâche par connexion à la fois ; l'accès est vérifié à nouveau "
        "avant chaque chunk"
    ),
    "Runs in Activity, one such job per connection at a time; access is checked again before every unit": (
        "S'exécute dans Activité, une telle tâche par connexion à la fois ; l'accès est vérifié à nouveau "
        "avant chaque unité"
    ),
    # Lignes communes d'une prévisualisation.
    "Time dimension: {column}": "Dimension temporelle : {column}",
    "Unit": "Unité",
    "{chunk}: {start} to {end}": "{chunk} : de {start} à {end}",
    "…and {count} more": "…et {count} de plus",
    "Whole chunks from the earliest chunk to {end}": "Chunks entiers du plus ancien chunk à {end}",
    "Whole chunks from {start} to {end}": "Chunks entiers de {start} à {end}",
    "Give an instant with its time zone, such as 2026-01-15T00:00:00Z, or a whole number": (
        "Indiquez un instant avec son fuseau horaire, par exemple 2026-01-15T00:00:00Z, ou un nombre entier"
    ),
    "The number is outside the range of a bigint": "Le nombre est hors de la plage d'un bigint",
    "Both ends are instants, or both are numbers": "Les deux bornes sont des instants, ou les deux sont des nombres",
    "The range must start before it ends": "La plage doit commencer avant de se terminer",
    "The window must start before it ends": "La fenêtre doit commencer avant de se terminer",
    "Chunks ending at or before": "Chunks se terminant au plus tard",
    "With its time zone; only chunks lying entirely inside the window are chosen": (
        "Avec son fuseau horaire ; seuls les chunks entièrement compris dans la fenêtre sont choisis"
    ),
    "and starting at or after": "et commençant au plus tôt",
    "Leave empty for every earlier chunk": "Laisser vide pour tous les chunks antérieurs",
    # Intervalle des chunks.
    "Change chunk interval": "Modifier l'intervalle des chunks",
    "Review the interval plan before applying it": "Vérifiez le plan de l'intervalle avant de l'appliquer",
    "Future chunk interval changed; existing chunks were not repartitioned": (
        "L'intervalle des futurs chunks a été modifié ; les chunks existants n'ont pas été repartitionnés"
    ),
    "Change the future chunk interval for {target}": "Modifier l'intervalle des futurs chunks pour {target}",
    "Current interval: {interval}": "Intervalle actuel : {interval}",
    "Requested interval: {interval}": "Intervalle demandé : {interval}",
    "Only future chunks use the new interval; existing chunks are not repartitioned": (
        "Seuls les futurs chunks utilisent le nouvel intervalle ; les chunks existants ne sont pas repartitionnés"
    ),
    "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait": (
        "Verrouille brièvement les métadonnées TimescaleDB dans toute cette base de données ; "
        "la création de nouveaux chunks peut attendre"
    ),
    "TimescaleDB interval metadata could not be inspected safely": (
        "Les métadonnées d'intervalle TimescaleDB n'ont pas pu être lues de façon sûre"
    ),
    "TimescaleDB interval planning timed out": "Le délai de planification de l'intervalle TimescaleDB a été dépassé",
    "Calendar chunk intervals are not supported by this strategy": (
        "Les intervalles de chunks calendaires ne sont pas pris en charge par cette stratégie"
    ),
    "Date dimensions require whole days or weeks": "Les dimensions de type date exigent des jours ou des semaines entiers",
    "Interval validation timed out; review the plan again": "Le délai de validation de l'intervalle a été dépassé ; vérifiez le plan à nouveau",
    "This connection may not change the interval or lock its metadata": (
        "Cette connexion n'a pas le droit de modifier l'intervalle ni de verrouiller ses métadonnées"
    ),
    "The source refused the interval change": "La source a refusé la modification de l'intervalle",
    "The interval change could not be confirmed; reload the source before reviewing again": (
        "La modification de l'intervalle n'a pas pu être confirmée ; rechargez la source avant de vérifier à nouveau"
    ),
    # Politiques de rétention et de compression.
    "Set retention policy": "Définir la politique de rétention",
    "Remove retention policy": "Supprimer la politique de rétention",
    "Set compression policy": "Définir la politique de compression",
    "Remove compression policy": "Supprimer la politique de compression",
    "TimescaleDB will keep dropping old chunks by itself, even after this session ends. Set this policy?": (
        "TimescaleDB continuera de supprimer seul les anciens chunks, même après la fin de cette session. "
        "Définir cette politique ?"
    ),
    "Drop chunks older than": "Supprimer les chunks plus anciens que",
    "Compress chunks older than": "Compresser les chunks plus anciens que",
    "Set the retention policy for {target}": "Définir la politique de rétention pour {target}",
    "Remove the retention policy from {target}": "Supprimer la politique de rétention de {target}",
    "Set the compression policy for {target}": "Définir la politique de compression pour {target}",
    "Remove the compression policy from {target}": "Supprimer la politique de compression de {target}",
    "No retention policy exists yet": "Aucune politique de rétention n'existe encore",
    "No compression policy exists yet": "Aucune politique de compression n'existe encore",
    "older than {age}": "plus anciens que {age}",
    "created more than {age} ago": "créés il y a plus de {age}",
    "Removes job {job}, which drops chunks {chunks}": "Supprime la tâche {job}, qui supprime les chunks {chunks}",
    "Replaces job {job}, which drops chunks {chunks}": "Remplace la tâche {job}, qui supprime les chunks {chunks}",
    "Removes job {job}, which compresses chunks {chunks}": "Supprime la tâche {job}, qui compresse les chunks {chunks}",
    "Replaces job {job}, which compresses chunks {chunks}": "Remplace la tâche {job}, qui compresse les chunks {chunks}",
    "The current policy runs every {every}; its replacement uses TimescaleDB's default schedule": (
        "La politique actuelle s'exécute toutes les {every} ; son remplacement utilise la planification par défaut de TimescaleDB"
    ),
    "New policy: drop chunks older than {age}": "Nouvelle politique : supprimer les chunks plus anciens que {age}",
    "New policy: compress chunks older than {age}": "Nouvelle politique : compresser les chunks plus anciens que {age}",
    "TimescaleDB keeps dropping whole chunks older than this on its own schedule, after this session ends": (
        "TimescaleDB continue de supprimer les chunks entiers plus anciens que ce délai selon sa propre "
        "planification, après la fin de cette session"
    ),
    "TimescaleDB stops dropping old chunks automatically; chunks already dropped do not return": (
        "TimescaleDB cesse de supprimer automatiquement les anciens chunks ; les chunks déjà supprimés ne reviennent pas"
    ),
    "TimescaleDB keeps compressing chunks older than this on its own schedule; compressed chunks stay readable": (
        "TimescaleDB continue de compresser les chunks plus anciens que ce délai selon sa propre "
        "planification ; les chunks compressés restent lisibles"
    ),
    "TimescaleDB stops compressing chunks automatically; chunks already compressed stay compressed": (
        "TimescaleDB cesse de compresser automatiquement les chunks ; les chunks déjà compressés restent compressés"
    ),
    "Other policy changes made here in this database wait until it commits, and so may a policy run starting meanwhile": (
        "Les autres modifications de politique effectuées ici dans cette base de données attendent le commit, "
        "et une exécution de politique démarrant entre-temps peut de même attendre"
    ),
    "Review the retention policy plan before applying it": (
        "Vérifiez le plan de la politique de rétention avant de l'appliquer"
    ),
    "Review the compression policy plan before applying it": (
        "Vérifiez le plan de la politique de compression avant de l'appliquer"
    ),
    "Retention policy set: TimescaleDB drops chunks older than {age} on its own schedule": (
        "Politique de rétention définie : TimescaleDB supprime les chunks plus anciens que {age} selon sa propre planification"
    ),
    "Retention policy removed; TimescaleDB no longer drops old chunks automatically": (
        "Politique de rétention supprimée ; TimescaleDB ne supprime plus automatiquement les anciens chunks"
    ),
    "Compression policy set: TimescaleDB compresses chunks older than {age} on its own schedule": (
        "Politique de compression définie : TimescaleDB compresse les chunks plus anciens que {age} selon sa propre planification"
    ),
    "Compression policy removed; TimescaleDB no longer compresses chunks automatically": (
        "Politique de compression supprimée ; TimescaleDB ne compresse plus automatiquement les chunks"
    ),
    "This hypertable has several retention policy jobs; manage them with SQL": (
        "Cette hypertable a plusieurs tâches de politique de rétention ; gérez-les avec SQL"
    ),
    "This hypertable has several compression policy jobs; manage them with SQL": (
        "Cette hypertable a plusieurs tâches de politique de compression ; gérez-les avec SQL"
    ),
    "The existing retention policy could not be read safely; manage it with SQL": (
        "La politique de rétention existante n'a pas pu être lue de façon sûre ; gérez-la avec SQL"
    ),
    "The existing compression policy could not be read safely; manage it with SQL": (
        "La politique de compression existante n'a pas pu être lue de façon sûre ; gérez-la avec SQL"
    ),
    "TimescaleDB retention policy planning timed out": "Le délai de planification de la politique de rétention TimescaleDB a été dépassé",
    "TimescaleDB compression policy planning timed out": "Le délai de planification de la politique de compression TimescaleDB a été dépassé",
    "TimescaleDB retention policy metadata could not be inspected safely": (
        "Les métadonnées de la politique de rétention TimescaleDB n'ont pas pu être lues de façon sûre"
    ),
    "TimescaleDB compression policy metadata could not be inspected safely": (
        "Les métadonnées de la politique de compression TimescaleDB n'ont pas pu être lues de façon sûre"
    ),
    "Enable compression on this hypertable first": "Activez d'abord la compression sur cette hypertable",
    "This hypertable has no retention policy": "Cette hypertable n'a pas de politique de rétention",
    "This hypertable has no compression policy": "Cette hypertable n'a pas de politique de compression",
    "Date dimensions require whole days, weeks, months or years": (
        "Les dimensions de type date exigent des jours, des semaines, des mois ou des années entiers"
    ),
    "The existing retention policy is paused; remove it before setting a new one": (
        "La politique de rétention existante est en pause ; supprimez-la avant d'en définir une nouvelle"
    ),
    "The existing compression policy is paused; remove it before setting a new one": (
        "La politique de compression existante est en pause ; supprimez-la avant d'en définir une nouvelle"
    ),
    # Politiques d'actualisation des agrégats continus.
    "Set refresh policy": "Définir la politique d'actualisation",
    "Remove refresh policy": "Supprimer la politique d'actualisation",
    "Window starts": "Début de la fenêtre",
    "How long ago the refreshed window begins": "Depuis combien de temps commence la fenêtre actualisée",
    "Window ends": "Fin de la fenêtre",
    "How long ago it ends; more recent than the start": "Depuis combien de temps elle se termine ; plus récent que le début",
    "Refresh every": "Actualiser toutes les",
    "Set the refresh policy for {target}": "Définir la politique d'actualisation pour {target}",
    "Remove the refresh policy from {target}": "Supprimer la politique d'actualisation de {target}",
    "Source hypertable: {source}": "Hypertable source : {source}",
    "No refresh policy exists yet": "Aucune politique d'actualisation n'existe encore",
    "from the earliest data to the latest data": "des données les plus anciennes aux données les plus récentes",
    "from the earliest data to {end} ago": "des données les plus anciennes à il y a {end}",
    "from {start} ago to the latest data": "d'il y a {start} aux données les plus récentes",
    "from {start} ago to {end} ago": "d'il y a {start} à il y a {end}",
    "Removes job {job}, which refreshes {window} every {every}": (
        "Supprime la tâche {job}, qui actualise {window} toutes les {every}"
    ),
    "Replaces job {job}, which refreshes {window} every {every}": (
        "Remplace la tâche {job}, qui actualise {window} toutes les {every}"
    ),
    "New policy: refresh from {start} ago to {end} ago, every {every}": (
        "Nouvelle politique : actualiser d'il y a {start} à il y a {end}, toutes les {every}"
    ),
    "The source hypertable has no retention policy": "L'hypertable source n'a pas de politique de rétention",
    "The source drops chunks older than {age}; the window starts after that": (
        "La source supprime les chunks plus anciens que {age} ; la fenêtre commence après ce délai"
    ),
    "The source drops chunks {chunks}; check that it keeps the raw data this window refreshes": (
        "La source supprime les chunks {chunks} ; vérifiez qu'elle conserve les données brutes que cette fenêtre actualise"
    ),
    "TimescaleDB stops refreshing this aggregate automatically; its materialized rows stay as they are": (
        "TimescaleDB cesse d'actualiser automatiquement cet agrégat ; ses lignes matérialisées restent telles quelles"
    ),
    "TimescaleDB keeps refreshing this window on its own schedule, after this session ends": (
        "TimescaleDB continue d'actualiser cette fenêtre selon sa propre planification, "
        "après la fin de cette session"
    ),
    "This continuous aggregate has no refresh policy": "Cet agrégat continu n'a pas de politique d'actualisation",
    "Review the refresh policy plan before applying it": "Vérifiez le plan de la politique d'actualisation avant de l'appliquer",
    "Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule": (
        "Politique d'actualisation définie : TimescaleDB actualise cet agrégat selon sa propre planification"
    ),
    "Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically": (
        "Politique d'actualisation supprimée ; TimescaleDB n'actualise plus automatiquement cet agrégat"
    ),
    "The existing refresh policy is paused; remove it before setting a new one": (
        "La politique d'actualisation existante est en pause ; supprimez-la avant d'en définir une nouvelle"
    ),
    "TimescaleDB refresh policy planning timed out": "Le délai de planification de la politique d'actualisation TimescaleDB a été dépassé",
    "TimescaleDB refresh policy metadata could not be inspected safely": (
        "Les métadonnées de la politique d'actualisation TimescaleDB n'ont pas pu être lues de façon sûre"
    ),
    "This continuous aggregate has several refresh policy jobs; manage them with SQL": (
        "Cet agrégat continu a plusieurs tâches de politique d'actualisation ; gérez-les avec SQL"
    ),
    "The existing refresh policy could not be read safely; manage it with SQL": (
        "La politique d'actualisation existante n'a pas pu être lue de façon sûre ; gérez-la avec SQL"
    ),
    "Date dimensions require offsets in whole days, weeks, months or years": (
        "Les dimensions de type date exigent des décalages en jours, semaines, mois ou années entiers"
    ),
    "The window must start further back than it ends": "Le début de la fenêtre doit être plus ancien que sa fin",
    "The window reaches data the source's retention policy drops (older than {age}); refreshing there would remove aggregated rows": (
        "La fenêtre atteint des données que la politique de rétention de la source supprime (plus anciennes "
        "que {age}) ; une actualisation à cet endroit supprimerait des lignes agrégées"
    ),
    # Paramètres de compression.
    "Configure compression": "Configurer la compression",
    "Segment by": "Segmenter par",
    "One column per line; leave empty for none": "Une colonne par ligne ; laisser vide pour aucune",
    "Order by": "Trier par",
    "One column per line, optionally followed by ASC or DESC and NULLS FIRST or NULLS LAST; the time column is added descending when neither list names it": (
        "Une colonne par ligne, éventuellement suivie de ASC ou DESC et NULLS FIRST ou NULLS LAST ; la "
        "colonne de temps est ajoutée en ordre décroissant quand aucune liste ne la nomme"
    ),
    "TimescaleDB compression settings could not be inspected safely": (
        "Les paramètres de compression TimescaleDB n'ont pas pu être lus de façon sûre"
    ),
    "Change the compression settings of {target}": "Modifier les paramètres de compression de {target}",
    "Enable compression on {target}": "Activer la compression sur {target}",
    "Current segment by: {columns}": "Segmentation actuelle par : {columns}",
    "Current segment by: none": "Segmentation actuelle par : aucune",
    "Current order by: {columns}": "Tri actuel par : {columns}",
    "Current order by: none": "Tri actuel par : aucun",
    "Compression is not enabled yet": "La compression n'est pas encore activée",
    "New segment by: {columns}": "Nouvelle segmentation par : {columns}",
    "New segment by: none": "Nouvelle segmentation par : aucune",
    "New order by: {columns}": "Nouveau tri par : {columns}",
    "Already compressed chunks keep the settings they were compressed with": (
        "Les chunks déjà compressés conservent les paramètres avec lesquels ils ont été compressés"
    ),
    "TimescaleDB recommends segmenting or ordering by the unique column {column}": (
        "TimescaleDB recommande de segmenter ou de trier par la colonne unique {column}"
    ),
    "Review the compression settings plan before applying it": (
        "Vérifiez le plan des paramètres de compression avant de l'appliquer"
    ),
    "Compression settings changed; only chunks compressed from now on use them": (
        "Paramètres de compression modifiés ; seuls les chunks compressés à partir de maintenant les utilisent"
    ),
    "Compression enabled; chunks are compressed by a compression policy or on request": (
        "Compression activée ; les chunks sont compressés par une politique de compression ou à la demande"
    ),
    "Nothing is compressed now; chunks are compressed later by a compression policy or on request": (
        "Rien n'est compressé pour l'instant ; les chunks sont compressés plus tard par une politique de "
        "compression ou à la demande"
    ),
    "Only chunks compressed from now on use these settings; already compressed chunks keep theirs": (
        "Seuls les chunks compressés à partir de maintenant utilisent ces paramètres ; les chunks déjà "
        "compressés gardent les leurs"
    ),
    "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits": (
        "Verrouille cette hypertable en exclusivité pendant la modification des paramètres ; ses lectures et "
        "écritures attendent le commit"
    ),
    "Column \"{column}\" is listed more than once": "La colonne « {column} » est listée plus d'une fois",
    "List at most {count} segment-by columns": "Indiquez au plus {count} colonnes de segmentation",
    "List at most {count} order-by columns": "Indiquez au plus {count} colonnes de tri",
    "Each line names one column": "Chaque ligne nomme une colonne",
    "This hypertable has no column \"{column}\"": "Cette hypertable n'a pas de colonne « {column} »",
    "The current compression settings could not be read": "Les paramètres de compression actuels n'ont pas pu être lus",
    "TimescaleDB compression settings planning timed out": "Le délai de planification des paramètres de compression TimescaleDB a été dépassé",
    # Convertir une table.
    "Convert to hypertable": "Convertir en hypertable",
    "The table becomes a hypertable, which DataPlayer cannot turn back into an ordinary table. Convert it?": (
        "La table devient une hypertable, que DataPlayer ne pourra pas reconvertir en table ordinaire. "
        "La convertir ?"
    ),
    "Time column": "Colonne de temps",
    "A timestamp or date column of this table": "Une colonne de cette table de type timestamp ou date",
    "Chunk interval": "Intervalle des chunks",
    "The table could not be inspected safely for conversion": (
        "La table n'a pas pu être inspectée de façon sûre avant la conversion"
    ),
    "Convert {target} into a hypertable": "Convertir {target} en hypertable",
    "Time column: {column} ({type})": "Colonne de temps : {column} ({type})",
    "Chunk interval: {interval}": "Intervalle des chunks : {interval}",
    "The table is empty, and the conversion refuses if a row arrives before it runs": (
        "La table est vide, et la conversion échoue si une ligne arrive avant son exécution"
    ),
    "{column} becomes NOT NULL": "{column} devient NOT NULL",
    "{column} becomes NOT NULL; a row without a time makes the conversion fail and roll back": (
        "{column} devient NOT NULL ; une ligne sans temps fait échouer la conversion et l'annule"
    ),
    "An index on {column} alone already exists, so TimescaleDB adds none": (
        "Un index sur {column} seul existe déjà, donc TimescaleDB n'en ajoute aucun"
    ),
    "TimescaleDB adds an index on {column}, newest first": (
        "TimescaleDB ajoute un index sur {column}, du plus récent au plus ancien"
    ),
    "The table keeps its name and identity and becomes a hypertable; DataPlayer cannot turn it back into an ordinary table": (
        "La table conserve son nom et son identité et devient une hypertable ; DataPlayer ne peut pas la "
        "reconvertir en table ordinaire"
    ),
    "Locks this table exclusively for the conversion; its reads and writes wait until it commits": (
        "Verrouille cette table en exclusivité pour la conversion ; ses lectures et écritures attendent le commit"
    ),
    "Review the conversion plan before applying it": "Vérifiez le plan de conversion avant de l'appliquer",
    "Converted to a hypertable; rows added from now on are stored in chunks": (
        "Convertie en hypertable ; les lignes ajoutées à partir de maintenant sont stockées dans des chunks"
    ),
    "Choose an existing ordinary table": "Choisissez une table ordinaire existante",
    "This table is already a hypertable": "Cette table est déjà une hypertable",
    "Foreign keys between this table and a hypertable are not supported": (
        "Les clés étrangères entre cette table et une hypertable ne sont pas prises en charge"
    ),
    "This table has no timestamp or date column to partition by": (
        "Cette table n'a pas de colonne de type timestamp ou date servant au partitionnement"
    ),
    "This table has no timestamp, date or integer column to partition by": (
        "Cette table n'a pas de colonne de type timestamp, date ou entière servant au partitionnement"
    ),
    "This table is not empty; only empty tables are converted here": (
        "Cette table n'est pas vide ; seules les tables vides sont converties ici"
    ),
    "This table has too many indexes to inspect": "Cette table a trop d'index pour être inspectée",
    "The TimescaleDB conversion API is split across schemas": "L'API de conversion TimescaleDB est répartie sur plusieurs schémas",
    "TimescaleDB conversion planning timed out": "Le délai de planification de la conversion TimescaleDB a été dépassé",
    "Only the table's owner can convert it": "Seul le propriétaire de la table peut la convertir",
    "This connection may not read the table": "Cette connexion n'a pas le droit de lire la table",
    "Partitioned tables cannot become hypertables": "Les tables partitionnées ne peuvent pas devenir des hypertables",
    "Choose an ordinary table": "Choisissez une table ordinaire",
    "Tables with NO INHERIT constraints cannot become hypertables": (
        "Les tables avec des contraintes NO INHERIT ne peuvent pas devenir des hypertables"
    ),
    "Tables that use inheritance cannot become hypertables": (
        "Les tables qui utilisent l'héritage ne peuvent pas devenir des hypertables"
    ),
    "Only logged tables can become hypertables": "Seules les tables journalisées peuvent devenir des hypertables",
    "Tables with rules cannot become hypertables": "Les tables avec des règles ne peuvent pas devenir des hypertables",
    "Choose a column this table can be partitioned by: {choices}": (
        "Choisissez une colonne par laquelle cette table peut être partitionnée : {choices}"
    ),
    "Unique index \"{index}\" must include \"{column}\", which partitions the table": (
        "L'index unique « {index} » doit inclure « {column} », qui partitionne la table"
    ),
    "An integer or UUID column is converted from Hypertable settings": (
        "Une colonne entière ou de type UUID se convertit depuis les paramètres de l'hypertable"
    ),
    "Date columns require whole days or weeks": "Les colonnes de type date exigent des jours ou des semaines entiers",
    # Compresser et décompresser des chunks.
    "Compress chunks": "Compresser les chunks",
    "Decompress chunks": "Décompresser les chunks",
    "TimescaleDB chunk metadata could not be inspected safely": (
        "Les métadonnées des chunks TimescaleDB n'ont pas pu être lues de façon sûre"
    ),
    "TimescaleDB chunk metadata could not be read": "Les métadonnées des chunks TimescaleDB n'ont pas pu être lues",
    "TimescaleDB chunk planning timed out": "Le délai de planification de l'opération sur les chunks TimescaleDB a été dépassé",
    "Compress 1 chunk of {target} as a job": "Tâche : compresser un chunk de {target}",
    "Compress {count} chunks of {target} as a job": "Tâche : compresser {count} chunks de {target}",
    "Decompress 1 chunk of {target} as a job": "Tâche : décompresser un chunk de {target}",
    "Decompress {count} chunks of {target} as a job": "Tâche : décompresser {count} chunks de {target}",
    "Already compressed and left as they are: {count}": "Déjà compressés et laissés tels quels : {count}",
    "Already decompressed and left as they are: {count}": "Déjà décompressés et laissés tels quels : {count}",
    "Compressed chunks stay readable; queries and writes touching a chunk may wait while it is rewritten": (
        "Les chunks compressés restent lisibles ; les requêtes et les écritures touchant un chunk peuvent "
        "attendre pendant qu'il est réécrit"
    ),
    "Decompressed chunks take more space; a compression policy may compress them again on its own schedule": (
        "Les chunks décompressés prennent plus d'espace ; une politique de compression peut les recompresser "
        "selon sa propre planification"
    ),
    "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted": (
        "Chaque chunk est converti dans sa propre transaction ; une annulation conserve les chunks déjà convertis"
    ),
    "The hypertable could not be found; nothing was converted": "L'hypertable n'a pas été trouvée ; rien n'a été converti",
    "Every whole chunk inside this window is already compressed": "Tous les chunks entiers dans cette fenêtre sont déjà compressés",
    "No whole chunk inside this window is compressed": "Aucun chunk entier dans cette fenêtre n'est compressé",
    "No whole chunk lies inside this window": "Aucun chunk entier ne se trouve dans cette fenêtre",
    "More than {count} chunks lie inside this window; narrow it": (
        "Plus de {count} chunks se trouvent dans cette fenêtre ; réduisez-la"
    ),
    "This chunk is in use; nothing was converted": "Ce chunk est utilisé ; rien n'a été converti",
    "The source cancelled converting this chunk after its fifteen minutes; it was rolled back": (
        "La source a annulé la conversion de ce chunk après ses quinze minutes ; elle a été annulée"
    ),
    "This connection may not convert this chunk": "Cette connexion n'a pas le droit de convertir ce chunk",
    "The connection was lost while this chunk was being converted; its outcome is unknown": (
        "La connexion a été perdue pendant la conversion de ce chunk ; son résultat est inconnu"
    ),
    "The source could not be reached; nothing was converted": "La source n'a pas pu être jointe ; rien n'a été converti",
    "The hypertable could not be checked in time; nothing was converted": (
        "L'hypertable n'a pas pu être vérifiée à temps ; rien n'a été converti"
    ),
    "The hypertable could not be checked safely; nothing was converted": (
        "L'hypertable n'a pas pu être vérifiée de façon sûre ; rien n'a été converti"
    ),
    "The hypertable or its TimescaleDB API changed after review; nothing was converted": (
        "L'hypertable ou son API TimescaleDB a changé après la vérification ; rien n'a été converti"
    ),
    "This chunk is no longer part of the hypertable": "Ce chunk ne fait plus partie de l'hypertable",
    "The source could not be reached or prepared; nothing was converted": (
        "La source n'a pas pu être jointe ou préparée ; rien n'a été converti"
    ),
    "The source refused to convert this chunk": "La source a refusé de convertir ce chunk",
    # Maintenance des chunks.
    "Drop chunks": "Supprimer les chunks",
    "Drop these chunks and every row in them? This cannot be undone.": (
        "Supprimer ces chunks et toutes leurs lignes ? Cette action est irréversible."
    ),
    "Detach chunks": "Détacher les chunks",
    "Merge chunks": "Fusionner les chunks",
    "Merge chunks, reads going on": "Fusionner les chunks sans interrompre les lectures",
    "Move chunks to a tablespace": "Déplacer les chunks vers un espace de tables",
    "Reorder chunks by an index": "Réordonner les chunks par un index",
    "Split a chunk": "Scinder un chunk",
    "Attach a table as a chunk": "Attacher une table comme chunk",
    "Drop chunks…": "Supprimer les chunks…",
    "Move chunks to a tablespace…": "Déplacer les chunks vers un espace de tables…",
    "Reorder chunks by an index…": "Réordonner les chunks par un index…",
    "Detach chunks…": "Détacher les chunks…",
    "Merge chunks…": "Fusionner les chunks…",
    "Merge chunks, reads going on…": "Fusionner les chunks sans interrompre les lectures…",
    "Tablespace": "Espace de tables",
    "An existing tablespace this connection may create in": (
        "Un espace de tables existant dans lequel cette connexion peut créer"
    ),
    "Order rows by index": "Ordonner les lignes par index",
    "Leave empty for the index on the time column": "Laisser vide pour l'index sur la colonne de temps",
    "Index tablespace": "Espace de tables des index",
    "Leave empty to move the indexes with the chunk": "Laisser vide pour déplacer les index avec le chunk",
    "Index": "Index",
    "An index of this hypertable to order rows by": "Un index de cette hypertable selon lequel ordonner les lignes",
    "Split at": "Scinder à",
    "With its time zone; the chunk holding this instant is split at it": (
        "Avec son fuseau horaire ; le chunk contenant cet instant est scindé à ce point"
    ),
    "Schema of the table": "Schéma de la table",
    "Table": "Table",
    "A table with the hypertable's columns, such as a detached chunk": (
        "Une table avec les colonnes de l'hypertable, par exemple un chunk détaché"
    ),
    "Covering from": "Couvrant à partir de",
    "Until": "Jusqu'à",
    "Either a window or picked chunks, not both": "Soit une fenêtre, soit des chunks choisis, pas les deux",
    "Give where the window ends": "Indiquez où la fenêtre se termine",
    "With the chunk": "Avec le chunk",
    "The index on the time column": "L'index sur la colonne de temps",
    "A value of \"{column}\", the {type} column the hypertable is partitioned by": (
        "Une valeur de « {column} », la colonne de type {type} par laquelle l'hypertable est partitionnée"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; leave empty for every earlier chunk": (
        "Une valeur de « {column} », la colonne de type {type} par laquelle l'hypertable est partitionnée ; "
        "laisser vide pour tous les chunks antérieurs"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; the chunk holding it is split at it": (
        "Une valeur de « {column} », la colonne de type {type} par laquelle l'hypertable est partitionnée ; "
        "le chunk la contenant est scindé à ce point"
    ),
    "Drop 1 chunk of {target} as a job": "Tâche : supprimer un chunk de {target}",
    "Drop {count} chunks of {target} as a job": "Tâche : supprimer {count} chunks de {target}",
    "Move 1 chunk of {target} as a job": "Tâche : déplacer un chunk de {target}",
    "Move {count} chunks of {target} as a job": "Tâche : déplacer {count} chunks de {target}",
    "Reorder 1 chunk of {target} as a job": "Tâche : réordonner un chunk de {target}",
    "Reorder {count} chunks of {target} as a job": "Tâche : réordonner {count} chunks de {target}",
    "Detach 1 chunk of {target} as a job": "Tâche : détacher un chunk de {target}",
    "Detach {count} chunks of {target} as a job": "Tâche : détacher {count} chunks de {target}",
    "Merge {count} chunks of {target} into one as a job": "Tâche : fusionner {count} chunks de {target} en un seul",
    "Split {chunk} at {point} as a job": "Tâche : scinder {chunk} à {point}",
    "Attach {table} to {target} as a chunk as a job": "Tâche : attacher {table} à {target} comme chunk",
    "Exactly the chunks picked in the Chunks report, each read again by name": (
        "Exactement les chunks choisis dans le rapport « Chunks », chacun relu par son nom"
    ),
    "Left as they are, already in {tablespace}: {count}": "Laissés tels quels, déjà dans {tablespace} : {count}",
    "Left as they are, compressed, which reorder_chunk does not rewrite: {count}": (
        "Laissés tels quels, compressés, ce que reorder_chunk ne réécrit pas : {count}"
    ),
    "Left as they are, compressed; TimescaleDB detaches only uncompressed chunks: {count}": (
        "Laissés tels quels, compressés ; TimescaleDB ne détache que les chunks non compressés : {count}"
    ),
    "Left as they are: {count}": "Laissés tels quels : {count}",
    "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs": (
        "Chaque ligne de ces chunks est supprimée ; chaque chunk est supprimé par son nom, jamais selon un "
        "âge lu au moment de l'exécution de la tâche"
    ),
    "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; Detached chunks lists it, and Attach chunk brings it back": (
        "Chaque chunk devient une table ordinaire sous son propre nom et quitte les requêtes de "
        "l'hypertable ; « Chunks détachés » le liste, et « Attacher une table comme chunk » le récupère"
    ),
    "The chunks become one, covering their whole range; the table is locked while they merge": (
        "Les chunks n'en forment plus qu'un, couvrant toute leur plage ; la table est verrouillée pendant la fusion"
    ),
    "The chunks become one, covering their whole range; reads go on meanwhile, writes to them wait": (
        "Les chunks n'en forment plus qu'un, couvrant toute leur plage ; les lectures se poursuivent pendant "
        "ce temps, les écritures y attendent"
    ),
    "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile": (
        "Chaque chunk est copié dans l'espace de tables et l'ancienne copie supprimée ; les lectures et "
        "écritures dessus attendent pendant ce temps"
    ),
    "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile": (
        "Chaque chunk est réécrit dans l'ordre de l'index, ce qui accélère les lectures le long de celui-ci ; "
        "les lectures et écritures attendent pendant ce temps"
    ),
    "The chunk becomes two, divided at this point; the table is locked while it splits": (
        "Le chunk devient deux, divisé à ce point ; la table est verrouillée pendant la scission"
    ),
    "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit": (
        "Ses lignes rejoignent les requêtes de l'hypertable ; TimescaleDB refuse une table dont les colonnes "
        "ou les lignes ne correspondent pas"
    ),
    "The hypertable could not be found; nothing was changed": "L'hypertable n'a pas été trouvée ; rien n'a été modifié",
    "This hypertable is partitioned by the integer column \"{column}\"; give its values, not instants": (
        "Cette hypertable est partitionnée par la colonne entière « {column} » ; indiquez ses valeurs, pas des instants"
    ),
    "This hypertable is partitioned by time on \"{column}\"; give instants, not numbers": (
        "Cette hypertable est partitionnée par le temps sur « {column} » ; indiquez des instants, pas des nombres"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not merged here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Les chunks d'une hypertable partitionnée par hachage sur {columns} ne sont pas fusionnés ici : "
        "la partition à laquelle appartient un chunk n'est pas publique, le résultat n'a donc pas pu être "
        "vérifié au préalable"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not attached here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Les chunks d'une hypertable partitionnée par hachage sur {columns} ne sont pas attachés ici : "
        "la partition à laquelle appartient un chunk n'est pas publique, le résultat n'a donc pas pu être "
        "vérifié au préalable"
    ),
    "TimescaleDB splits no chunk of a hypertable partitioned by hash as well as by time": (
        "TimescaleDB ne scinde aucun chunk d'une hypertable partitionnée à la fois par hachage et par le temps"
    ),
    "Pick at least one chunk": "Choisissez au moins un chunk",
    "Pick at most {count} chunks at a time": "Choisissez au plus {count} chunks à la fois",
    "\"{name}\" is not a chunk of this hypertable any more": "« {name} » n'est plus un chunk de cette hypertable",
    "Tablespace \"{name}\" does not exist or this connection may not create in it": (
        "L'espace de tables « {name} » n'existe pas, ou cette connexion n'a pas le droit d'y créer"
    ),
    "This hypertable has no index \"{index}\"": "Cette hypertable n'a pas d'index « {index} »",
    "Every whole chunk inside this window is already in {tablespace}": "Tous les chunks entiers dans cette fenêtre sont déjà dans {tablespace}",
    "Every picked chunk is already in {tablespace}": "Tous les chunks choisis sont déjà dans {tablespace}",
    "Every whole chunk inside this window is compressed, which reorder_chunk does not rewrite": (
        "Tous les chunks entiers dans cette fenêtre sont compressés, ce que reorder_chunk ne réécrit pas"
    ),
    "Every picked chunk is compressed, which reorder_chunk does not rewrite": (
        "Tous les chunks choisis sont compressés, ce que reorder_chunk ne réécrit pas"
    ),
    "Every whole chunk inside this window is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Tous les chunks entiers dans cette fenêtre sont compressés ; TimescaleDB ne détache que les chunks non compressés"
    ),
    "Every picked chunk is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Tous les chunks choisis sont compressés ; TimescaleDB ne détache que les chunks non compressés"
    ),
    "Name an index: moving a chunk rewrites it in an index's order": (
        "Nommez un index : le déplacement d'un chunk le réécrit dans l'ordre d'un index"
    ),
    "A merge needs at least two chunks": "Une fusion nécessite au moins deux chunks",
    "Chunks \"{before}\" and \"{after}\" are not adjacent; choose chunks that touch": (
        "Les chunks « {before} » et « {after} » ne sont pas adjacents ; choisissez des chunks qui se touchent"
    ),
    "TimescaleDB {version} cannot merge compressed chunks; decompress them first": (
        "TimescaleDB {version} ne peut pas fusionner des chunks compressés ; décompressez-les d'abord"
    ),
    "No chunk holds this point strictly inside its range": "Aucun chunk ne contient ce point strictement à l'intérieur de sa plage",
    "There is no table \"{schema}\".\"{table}\"": "Il n'existe aucune table « {schema} ».« {table} »",
    "Only an ordinary table can become a chunk": "Seule une table ordinaire peut devenir un chunk",
    "Only the table's owner can attach it": "Seul le propriétaire de la table peut l'attacher",
    "A hypertable cannot become a chunk": "Une hypertable ne peut pas devenir un chunk",
    "This table is already a chunk": "Cette table est déjà un chunk",
    "A table that uses inheritance cannot become a chunk": "Une table qui utilise l'héritage ne peut pas devenir un chunk",
    "Chunk \"{name}\" already covers part of this range": "Le chunk « {name} » couvre déjà une partie de cette plage",
    "The range is empty once read in the column's type": "La plage est vide une fois lue dans le type de la colonne",
    "This chunk is in use; nothing was changed": "Ce chunk est utilisé ; rien n'a été modifié",
    "The source cancelled this unit after its fifteen minutes; it was rolled back": (
        "La source a annulé cette unité après ses quinze minutes ; elle a été annulée"
    ),
    "This connection may not change this chunk": "Cette connexion n'a pas le droit de modifier ce chunk",
    "The connection was lost while this unit was running; its outcome is unknown": (
        "La connexion a été perdue pendant l'exécution de cette unité ; son résultat est inconnu"
    ),
    "The hypertable could not be checked in time; nothing was changed": (
        "L'hypertable n'a pas pu être vérifiée à temps ; rien n'a été modifié"
    ),
    "The hypertable or its chunks changed after review; nothing was changed": (
        "L'hypertable ou ses chunks ont changé après la vérification ; rien n'a été modifié"
    ),
    "The hypertable could not be checked safely; nothing was changed": (
        "L'hypertable n'a pas pu être vérifiée de façon sûre ; rien n'a été modifié"
    ),
    "The source could not be reached; nothing was changed": "La source n'a pas pu être jointe ; rien n'a été modifié",
    "The table to attach is gone; nothing was changed": "La table à attacher a disparu ; rien n'a été modifié",
    "This chunk was compressed after review; it was left as it is": (
        "Ce chunk a été compressé après la vérification ; il a été laissé tel quel"
    ),
    "These chunks changed after review; nothing was merged": "Ces chunks ont changé après la vérification ; rien n'a été fusionné",
    "The index to order rows by is gone; nothing was changed": (
        "L'index selon lequel ordonner les lignes a disparu ; rien n'a été modifié"
    ),
    "The source could not be reached or prepared; nothing was changed": (
        "La source n'a pas pu être jointe ou préparée ; rien n'a été modifié"
    ),
    "The source refused this unit; nothing was changed": "La source a refusé cette unité ; rien n'a été modifié",
    "This is not offered over these rows": "Ceci n'est pas proposé sur ces lignes",
    "A chunk is named by its schema and its name": "Un chunk est nommé par son schéma et son nom",
    "The picked chunks belong to {count} hypertables; pick chunks of one": (
        "Les chunks choisis appartiennent à {count} hypertables ; choisissez les chunks d'une seule"
    ),
    "Some picked rows are not chunks any more; read the report again": (
        "Certaines lignes choisies ne sont plus des chunks ; relisez le rapport"
    ),
    # Saut de chunks.
    "Skip chunks by a column": "Sauter des chunks selon une colonne",
    "Stop skipping chunks by a column": "Arrêter de sauter des chunks selon une colonne",
    "Column": "Colonne",
    "An integer, date or timestamp column queries filter on": (
        "Une colonne entière, de type date ou timestamp sur laquelle les requêtes filtrent"
    ),
    "The hypertable could not be inspected safely": "L'hypertable n'a pas pu être inspectée de façon sûre",
    "TimescaleDB keeps ranges only of integer, date and timestamp columns, not of \"{column}\" ({type})": (
        "TimescaleDB ne conserve les plages que pour les colonnes entières et de type date et timestamp, "
        "pas pour « {column} » ({type})"
    ),
    "Planning chunk skipping timed out": "Le délai de planification du saut de chunks a été dépassé",
    "Chunks record the range of {column} as they are compressed, and a query filtering on it skips the chunks outside": (
        "Les chunks enregistrent la plage de {column} au fur et à mesure de leur compression, et une requête "
        "qui filtre dessus saute les chunks situés en dehors"
    ),
    "Chunks stop recording the range of {column}, if they did": (
        "Les chunks cessent d'enregistrer la plage de {column}, s'ils le faisaient"
    ),
    "Changes nothing if it already holds: TimescaleDB keeps which columns record ranges where this application does not read": (
        "Ne change rien si c'est déjà le cas : TimescaleDB conserve, là où cette application ne lit pas, "
        "quelles colonnes enregistrent des plages"
    ),
    "timescaledb.enable_chunk_skipping is off for this connection; queries use the ranges only in sessions that turn it on": (
        "timescaledb.enable_chunk_skipping est désactivé pour cette connexion ; les requêtes n'utilisent les "
        "plages que dans les sessions qui l'activent"
    ),
    "Skip chunks by {column} on {target}": "Sauter des chunks selon {column} sur {target}",
    "Stop skipping chunks by {column} on {target}": "Arrêter de sauter des chunks selon {column} sur {target}",
    "Review the chunk skipping plan before applying it": "Vérifiez le plan de saut de chunks avant de l'appliquer",
    "Chunk skipping turned on": "Saut de chunks activé",
    "Chunk skipping turned off": "Saut de chunks désactivé",
    # Paramètres de l'hypertable : lire l'hypertable.
    "Hypertable settings": "Paramètres de l'hypertable",
    "Reading the hypertable timed out": "Le délai de lecture de l'hypertable a été dépassé",
    "Job {job} drops chunks {chunks}, every {every}": "La tâche {job} supprime les chunks {chunks}, toutes les {every}",
    "Job {job} drops chunks {chunks}, every {every}; paused": (
        "La tâche {job} supprime les chunks {chunks}, toutes les {every} ; en pause"
    ),
    "Job {job} compresses chunks {chunks}, every {every}": "La tâche {job} compresse les chunks {chunks}, toutes les {every}",
    "Job {job} compresses chunks {chunks}, every {every}; paused": (
        "La tâche {job} compresse les chunks {chunks}, toutes les {every} ; en pause"
    ),
    "Job {job} reorders chunks by {index}": "La tâche {job} réordonne les chunks par {index}",
    "Job {job} reorders chunks by {index}; paused": "La tâche {job} réordonne les chunks par {index} ; en pause",
    "Job {job} reorders chunks by an index this editor cannot read": (
        "La tâche {job} réordonne les chunks par un index que cet éditeur ne peut pas lire"
    ),
    "Job {job} reorders chunks by an index this editor cannot read; paused": (
        "La tâche {job} réordonne les chunks par un index que cet éditeur ne peut pas lire ; en pause"
    ),
    "The current sparse indexes could not be read": "Les index creux actuels n'ont pas pu être lus",
    "This hypertable has a sparse index of a kind this editor does not know; manage it with SQL": (
        "Cette hypertable a un index creux d'un type que cet éditeur ne connaît pas ; gérez-le avec SQL"
    ),
    "The current columnstore settings could not be read": (
        "Les paramètres actuels du stockage en colonnes n'ont pas pu être lus"
    ),
    "This hypertable merges compressed chunks by a time interval; manage it with SQL": (
        "Cette hypertable fusionne les chunks compressés selon un intervalle de temps ; gérez cela avec SQL"
    ),
    "This hypertable has several compaction policy jobs; manage them with SQL": (
        "Cette hypertable a plusieurs tâches de politique de compactage ; gérez-les avec SQL"
    ),
    "This hypertable has several reorder policy jobs; manage them with SQL": (
        "Cette hypertable a plusieurs tâches de politique de réordonnancement ; gérez-les avec SQL"
    ),
    "The existing reorder policy could not be read safely; manage it with SQL": (
        "La politique de réordonnancement existante n'a pas pu être lue de façon sûre ; gérez-la avec SQL"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; it is edited here from 2.25": (
        "TimescaleDB {version} ne partitionne que partiellement par UUIDv7 ; cela s'édite ici à partir de la version 2.25"
    ),
    "Only timestamp, date, UUIDv7 and integer time dimensions are edited here": (
        "Seules les dimensions temporelles de type timestamp, date, UUIDv7 et entières sont éditées ici"
    ),
    "The current chunk interval could not be read": "L'intervalle des chunks actuel n'a pas pu être lu",
    "Only hash dimensions beside the time dimension are edited here": (
        "Seules les dimensions de hachage à côté de la dimension temporelle sont éditées ici"
    ),
    "The hypertable's chunks and tablespaces could not be read": (
        "Les chunks et les espaces de tables de l'hypertable n'ont pas pu être lus"
    ),
    "This connection may not create functions in schema \"{schema}\"": (
        "Cette connexion n'a pas le droit de créer des fonctions dans le schéma « {schema} »"
    ),
    "A function named \"{name}\" already exists; choose it from the list or another name": (
        "Une fonction nommée « {name} » existe déjà ; choisissez-la dans la liste ou un autre nom"
    ),
    "A chunk interval of an integer column is a number of its values": (
        "Un intervalle de chunks d'une colonne entière est un nombre de ses valeurs"
    ),
    "A chunk interval of a {type} column is at most {count}": (
        "Un intervalle de chunks d'une colonne de type {type} est au plus {count}"
    ),
    "A chunk interval is counted in minutes, hours, days or weeks": (
        "Un intervalle de chunks se compte en minutes, heures, jours ou semaines"
    ),
    # Paramètres de l'hypertable : planifier la modification.
    "Locks this hypertable exclusively while it changes; its reads and writes wait until it commits": (
        "Verrouille cette hypertable en exclusivité pendant le changement ; ses lectures et écritures attendent le commit"
    ),
    "Other changes to this hypertable's settings wait until it commits": (
        "Les autres modifications des paramètres de cette hypertable attendent le commit"
    ),
    "A chunk interval of this hypertable is counted in days or weeks": (
        "Un intervalle de chunks de cette hypertable se compte en jours ou semaines"
    ),
    "A chunk interval of this hypertable is counted in minutes or hours or days or weeks": (
        "Un intervalle de chunks de cette hypertable se compte en minutes, heures, jours ou semaines"
    ),
    "A chunk interval of this column is counted in days or weeks": (
        "Un intervalle de chunks de cette colonne se compte en jours ou semaines"
    ),
    "A chunk interval of this column is counted in minutes or hours or days or weeks": (
        "Un intervalle de chunks de cette colonne se compte en minutes, heures, jours ou semaines"
    ),
    "Column \"{column}\" has a type that cannot be used as a hash dimension": (
        "La colonne « {column} » a un type qui ne peut pas être utilisé comme dimension de hachage"
    ),
    "Column \"{column}\" has a type that cannot be used as a minmax sparse index": (
        "La colonne « {column} » a un type qui ne peut pas être utilisé comme index creux minmax"
    ),
    "Column \"{column}\" has a type that cannot be used as a segment column": (
        "La colonne « {column} » a un type qui ne peut pas être utilisé comme colonne de segmentation"
    ),
    "Column \"{column}\" has a type that cannot be used as an order column": (
        "La colonne « {column} » a un type qui ne peut pas être utilisé comme colonne de tri"
    ),
    "TimescaleDB cannot remove the hash dimension on \"{column}\"": (
        "TimescaleDB ne peut pas supprimer la dimension de hachage sur « {column} »"
    ),
    "A hash dimension can only be added while the hypertable holds no chunks": (
        "Une dimension de hachage ne peut être ajoutée que tant que l'hypertable ne contient aucun chunk"
    ),
    "The time column cannot also be a hash dimension": "La colonne de temps ne peut pas être aussi une dimension de hachage",
    "Unique key \"{key}\" must include \"{column}\" before it can be a hash dimension": (
        "La clé unique « {key} » doit inclure « {column} » avant de pouvoir être une dimension de hachage"
    ),
    "TimescaleDB {version} has no sparse indexes; they arrived in 2.22": (
        "TimescaleDB {version} n'a pas d'index creux ; ils sont arrivés dans la version 2.22"
    ),
    "Column \"{column}\" has the same sparse index twice": "La colonne « {column} » a deux fois le même index creux",
    "Sparse indexes need the order to be named; choose the columns to order by": (
        "Les index creux exigent que l'ordre soit nommé ; choisissez les colonnes de tri"
    ),
    "Column \"{column}\" is listed more than once in the columnstore settings": (
        "La colonne « {column} » est listée plus d'une fois dans les paramètres du stockage en colonnes"
    ),
    "The columnstore cannot be turned off while chunks are compressed; decompress them first": (
        "Le stockage en colonnes ne peut pas être désactivé tant que des chunks sont compressés ; décompressez-les d'abord"
    ),
    "TimescaleDB {version} cannot return a setting to its own choice; name the columns instead": (
        "TimescaleDB {version} ne peut pas rendre un paramètre à son propre choix ; nommez plutôt les colonnes"
    ),
    "Merging compressed chunks is set in time, which an integer column does not count in": (
        "La fusion des chunks compressés est exprimée en temps, une unité qu'une colonne entière ne compte pas"
    ),
    "A merge interval is counted in the units of the chunk interval": (
        "Un intervalle de fusion se compte dans les unités de l'intervalle des chunks"
    ),
    "The merge interval must be a whole multiple of the chunk interval, larger than it": (
        "L'intervalle de fusion doit être un multiple entier de l'intervalle des chunks, plus grand que celui-ci"
    ),
    "There is no retention policy to keep": "Il n'y a aucune politique de rétention à conserver",
    "There is no compression policy to keep": "Il n'y a aucune politique de compression à conserver",
    "The retention policy of an integer column is a number of its values": (
        "La politique de rétention d'une colonne entière est un nombre de ses valeurs"
    ),
    "The compression policy of an integer column is a number of its values": (
        "La politique de compression d'une colonne entière est un nombre de ses valeurs"
    ),
    "The retention policy of a {type} column is at most {count}": (
        "La politique de rétention d'une colonne de type {type} est au plus {count}"
    ),
    "The compression policy of a {type} column is at most {count}": (
        "La politique de compression d'une colonne de type {type} est au plus {count}"
    ),
    "The retention policy of a {type} column cannot count in plain numbers": (
        "La politique de rétention d'une colonne de type {type} ne peut pas se compter en nombres simples"
    ),
    "The compression policy of a {type} column cannot count in plain numbers": (
        "La politique de compression d'une colonne de type {type} ne peut pas se compter en nombres simples"
    ),
    "The retention policy of a {type} column cannot count in seconds": (
        "La politique de rétention d'une colonne de type {type} ne peut pas se compter en secondes"
    ),
    "The compression policy of a {type} column cannot count in seconds": (
        "La politique de compression d'une colonne de type {type} ne peut pas se compter en secondes"
    ),
    "The retention policy of a {type} column cannot count in minutes": (
        "La politique de rétention d'une colonne de type {type} ne peut pas se compter en minutes"
    ),
    "The compression policy of a {type} column cannot count in minutes": (
        "La politique de compression d'une colonne de type {type} ne peut pas se compter en minutes"
    ),
    "The retention policy of a {type} column cannot count in hours": (
        "La politique de rétention d'une colonne de type {type} ne peut pas se compter en heures"
    ),
    "The compression policy of a {type} column cannot count in hours": (
        "La politique de compression d'une colonne de type {type} ne peut pas se compter en heures"
    ),
    "The existing reorder policy is paused; remove it before setting a new one": (
        "La politique de réordonnancement existante est en pause ; supprimez-la avant d'en définir une nouvelle"
    ),
    "Only a hypertable partitioned by an integer column takes an integer_now function": (
        "Seule une hypertable partitionnée par une colonne entière accepte une fonction integer_now"
    ),
    "TimescaleDB cannot take an integer_now function away; keep it or choose another": (
        "TimescaleDB ne peut pas retirer une fonction integer_now ; conservez-la ou choisissez-en une autre"
    ),
    "There is no integer_now function to keep": "Il n'y a aucune fonction integer_now à conserver",
    "{function} is not a function TimescaleDB accepts as integer_now of a {type} column": (
        "TimescaleDB n'accepte pas {function} comme integer_now d'une colonne de type {type}"
    ),
    "A {type} column cannot hold the seconds since 1970": "Une colonne de type {type} ne peut pas contenir les secondes depuis 1970",
    "A {type} column cannot hold the milliseconds since 1970": (
        "Une colonne de type {type} ne peut pas contenir les millisecondes depuis 1970"
    ),
    "A {type} column cannot hold the microseconds since 1970": (
        "Une colonne de type {type} ne peut pas contenir les microsecondes depuis 1970"
    ),
    "TimescaleDB {version} has no compaction policy; it arrived in 2.29": (
        "TimescaleDB {version} n'a pas de politique de compactage ; elle est arrivée dans la version 2.29"
    ),
    "A compaction policy merges compressed chunks; turn the columnstore on": (
        "Une politique de compactage fusionne les chunks compressés ; activez le stockage en colonnes"
    ),
    "Remove the columnstore policy to turn the columnstore off": (
        "Supprimez la politique du stockage en colonnes pour désactiver le stockage en colonnes"
    ),
    "Remove the compaction policy to turn the columnstore off": (
        "Supprimez la politique de compactage pour désactiver le stockage en colonnes"
    ),
    "An age policy on an integer column needs an integer_now function to tell the current value": (
        "Une politique d'âge sur une colonne entière a besoin d'une fonction integer_now pour indiquer la valeur actuelle"
    ),
    "Choose the time column the table is partitioned by": "Choisissez la colonne de temps par laquelle la table est partitionnée",
    "Choose the chunk interval": "Choisissez l'intervalle des chunks",
    "TimescaleDB cannot change the time column of a hypertable": "TimescaleDB ne peut pas modifier la colonne de temps d'une hypertable",
    "Planning the hypertable change timed out": "Le délai de planification de la modification de l'hypertable a été dépassé",
    # Paramètres de l'hypertable : la prévisualisation.
    "TimescaleDB's choice for each chunk": "Le choix de TimescaleDB pour chaque chunk",
    "TimescaleDB's choice": "Le choix de TimescaleDB",
    "none": "aucun",
    "segment by {columns}": "segmentation par {columns}",
    "order by {columns}": "tri par {columns}",
    "sparse indexes {indexes}": "index creux {indexes}",
    "{kind} on {column}": "{kind} sur {column}",
    "no merging of chunks": "aucune fusion de chunks",
    "merge chunks into {length} as they are compressed": "fusionner les chunks en {length} au fur et à mesure de leur compression",
    "Turn the columnstore on: {changes}": "Activer le stockage en colonnes : {changes}",
    "Columnstore settings for chunks compressed from now on: {changes}": (
        "Paramètres du stockage en colonnes pour les chunks compressés à partir de maintenant : {changes}"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, and move its rows into chunks": (
        "Convertir la table en hypertable selon {column} ({type}), avec des chunks de {length}, et déplacer "
        "ses lignes dans des chunks"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, while it is empty": (
        "Convertir la table en hypertable selon {column} ({type}), avec des chunks de {length}, tant qu'elle est vide"
    ),
    "Remove the retention policy (job {job})": "Supprimer la politique de rétention (tâche {job})",
    "Remove the columnstore policy (job {job})": "Supprimer la politique du stockage en colonnes (tâche {job})",
    "Remove the reorder policy (job {job})": "Supprimer la politique de réordonnancement (tâche {job})",
    "Remove the compaction policy (job {job})": "Supprimer la politique de compactage (tâche {job})",
    "Add a retention policy: drop chunks older than {length}": (
        "Ajouter une politique de rétention : supprimer les chunks plus anciens que {length}"
    ),
    "Add a columnstore policy: compress chunks older than {length}": (
        "Ajouter une politique de stockage en colonnes : compresser les chunks plus anciens que {length}"
    ),
    "Add a compaction policy: merge small compressed chunks on TimescaleDB's schedule": (
        "Ajouter une politique de compactage : fusionner les petits chunks compressés selon la planification de TimescaleDB"
    ),
    "Add a reorder policy by index {index}": "Ajouter une politique de réordonnancement par index {index}",
    "New chunks cover {length}; existing chunks keep their range": (
        "Les nouveaux chunks couvrent {length} ; les chunks existants conservent leur plage"
    ),
    "Hash {column} into {partitions} partitions for new chunks": (
        "Hacher {column} en {partitions} partitions pour les nouveaux chunks"
    ),
    "Add a hash dimension on {column} with {partitions} partitions": (
        "Ajouter une dimension de hachage sur {column} avec {partitions} partitions"
    ),
    "Turn the columnstore off": "Désactiver le stockage en colonnes",
    "Place new chunks in tablespace {tablespace} too": "Placer aussi les nouveaux chunks dans l'espace de tables {tablespace}",
    "Stop placing new chunks in tablespace {tablespace}": (
        "Ne plus placer les nouveaux chunks dans l'espace de tables {tablespace}"
    ),
    "Create function {function} returning the seconds since 1970 as {type}": (
        "Créer la fonction {function} renvoyant les secondes depuis 1970 en {type}"
    ),
    "Create function {function} returning the milliseconds since 1970 as {type}": (
        "Créer la fonction {function} renvoyant les millisecondes depuis 1970 en {type}"
    ),
    "Create function {function} returning the microseconds since 1970 as {type}": (
        "Créer la fonction {function} renvoyant les microsecondes depuis 1970 en {type}"
    ),
    "Policies take the current value of the time column from {function}": (
        "Les politiques prennent la valeur actuelle de la colonne de temps dans {function}"
    ),
    "Moves about {count} rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Déplace environ {count} lignes dans des chunks comme tâche dans Activité ; la table est verrouillée "
        "en lecture et en écriture jusqu'à sa fin"
    ),
    "Moves an unknown number of rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Déplace un nombre inconnu de lignes dans des chunks comme tâche dans Activité ; la table est "
        "verrouillée en lecture et en écriture jusqu'à sa fin"
    ),
    "Rolled back whole if it fails, is cancelled or runs past {seconds} seconds; nothing is left half converted": (
        "Annulé entièrement s'il échoue, est annulé ou dépasse {seconds} secondes ; rien ne reste à moitié converti"
    ),
    "DataPlayer cannot turn a hypertable back into an ordinary table": (
        "DataPlayer ne peut pas reconvertir une hypertable en table ordinaire"
    ),
    "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, after this session ends": (
        "TimescaleDB continue de supprimer les chunks entiers au-delà de l'âge de rétention selon sa propre "
        "planification, après la fin de cette session"
    ),
    "{target} already matches these settings": "{target} correspond déjà à ces paramètres",
    "Change {target}": "Modifier {target}",
    "Review the hypertable plan before applying it": "Vérifiez le plan de l'hypertable avant de l'appliquer",
    "Moving rows into chunks runs as a job; start it from the plan": (
        "Le déplacement des lignes dans des chunks s'exécute comme tâche ; lancez-la depuis le plan"
    ),
    "Converted to a hypertable": "Convertie en hypertable",
    "Hypertable changed: 1 change applied": "Hypertable modifiée : une modification appliquée",
    "Hypertable changed: {count} changes applied": "Hypertable modifiée : {count} modifications appliquées",
    "This change is applied at once rather than as a job": "Cette modification est appliquée immédiatement, et non comme tâche",
    "The table could not be found; nothing was converted": "La table n'a pas été trouvée ; rien n'a été converti",
    "The table was renamed after review; nothing was converted": (
        "La table a été renommée après la vérification ; rien n'a été converti"
    ),
    # Une table conçue comme hypertable.
    "Hypertable": "Hypertable",
    "Columnstore": "Stockage en colonnes",
    "Retention policy": "Politique de rétention",
    "Columnstore policy": "Politique du stockage en colonnes",
    "Compaction policy": "Politique de compactage",
    "Reorder policy": "Politique de réordonnancement",
    "Integer now": "Integer now",
    "Function {name}": "Fonction {name}",
    "Hash dimension {column}": "Dimension de hachage {column}",
    "The segment list names a column that is not there": "La liste de segmentation nomme une colonne qui n'existe pas",
    "The order list names a column that is not there": "La liste de tri nomme une colonne qui n'existe pas",
    "The sparse index names a column that is not there": "L'index creux nomme une colonne qui n'existe pas",
    "The time dimension names a column that is not there": "La dimension temporelle nomme une colonne qui n'existe pas",
    "The hash dimension names a column that is not there": "La dimension de hachage nomme une colonne qui n'existe pas",
    "Choose the columns to segment by": "Choisissez les colonnes de segmentation",
    "Choose the columns to order by": "Choisissez les colonnes de tri",
    "Choose the columns of the sparse indexes": "Choisissez les colonnes des index creux",
    "The reorder policy names an index that is not there": "La politique de réordonnancement nomme un index qui n'existe pas",
    "The TimescaleDB API is split across schemas": "L'API TimescaleDB est répartie sur plusieurs schémas",
    "This setting cannot be made while the table is created": "Ce paramètre ne peut pas être défini au moment de la création de la table",
    "\"{column}\" cannot partition a hypertable; choose a timestamp or date column": (
        "« {column} » ne peut pas partitionner une hypertable ; choisissez une colonne de type timestamp ou date"
    ),
    "\"{column}\" partitions the hypertable, so it must have a value": (
        "« {column} » partitionne l'hypertable, elle doit donc avoir une valeur"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; choose a timestamp column": (
        "TimescaleDB {version} ne partitionne que partiellement par UUIDv7 ; choisissez une colonne de type timestamp"
    ),
}
