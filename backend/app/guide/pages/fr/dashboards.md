# Tableaux de bord

Un tableau de bord trace des métriques dans le temps : graphiques et tuiles sur une grille. Les métriques
viennent des agents que vous lancez sur vos machines et des connexions qui signalent leur propre état. Les
tableaux de bord se trouvent dans l'espace **Tableaux de bord**, en haut de la barre de gauche, sur l'interrupteur.

## Avant le premier tableau de bord

Les métriques sont conservées dans un stockage à part, une base TimescaleDB. Un administrateur la configure une
seule fois pour toute l'installation : l'espace Dashboards propose de la lancer ici ou de se connecter à une
existante. Jusque-là, les autres personnes sont informées qu'un administrateur la configure.

**Le stockage des métriques**, dans l'en-tête de la barre, appartient à l'administrateur : où se trouve le stockage,
ce qu'il occupe, combien de temps il garde les données et sa suppression. Les mesures brutes sont conservées
une semaine ; les moyennes sur cinq minutes et sur une heure le sont plus longtemps.

## D'où viennent les métriques

**Sources**, dans l'en-tête de la barre, ouvre une fenêtre à deux vues.

- **Agents** : un agent est un petit programme qui signale la machine sur laquelle il tourne, par exemple ses
  processeurs, sa mémoire et ses processus. Saisissez un **Nom de l'agent** et **Enregistrer** : la fenêtre affiche la
  clé de l'agent et un fichier Docker Compose qui le lance avec cette clé sur la machine à surveiller.
  **Hôtes** liste ce que vos agents signalent, avec le système, le matériel, la durée de fonctionnement de
  chacun et le moment où on l'a entendu pour la dernière fois. **Émettre une nouvelle clé** coupe l'ancienne clé ;
  supprimer un agent écarte désormais tout ce qu'il envoie.
- **Connexions** : une connexion PostgreSQL, MySQL ou Redis peut signaler ses propres compteurs. Son
  propriétaire active **Signalements** et choisit **Fréquence**, de toutes les 15 secondes à toutes les 5 minutes.
  Toute personne avec qui la connexion est partagée peut tracer ce qu'elle signale.

Ce qu'un agent envoie apparaît sur les graphiques ouverts en quelques secondes.

## Créer un tableau de bord

1. **Nouveau tableau de bord** dans l'en-tête de la barre. Il reçoit un nom par défaut ; renommez-le depuis son en-tête.
2. **Ajouter des widgets** ouvre les sources sous forme d'arbre. Cochez les séries à tracer et cliquez sur **Ajouter**.
   Sélectionner un hôte ou une connexion propose ses disposition prêtes à l'emploi — **Hôte Linux**,
   **Base de données PostgreSQL**, **Serveur MySQL**, **Serveur Redis** — et **Ajouter la disposition** en place une sous ce que le
   tableau de bord contient déjà.
3. Déplacez un widget par son en-tête, redimensionnez-le par son coin, double-cliquez sur son titre pour le
   renommer. La clé `processes` d'un hôte crée un tableau de ses processus, triable par CPU, mémoire ou PID.

Un tableau de bord est enregistré un instant après chaque modification. **Plage** choisit la durée retracée,
des 5 dernières minutes aux 30 derniers jours, et **Actualiser toutes les** la fréquence de relecture.

Un widget peut occuper tout le tableau de bord (**Remplir le tableau de bord avec ce widget**), ou être ouvert dans une
fenêtre qui reste lorsque vous revenez à Data.

## Partager un tableau de bord

**Partager ce tableau de bord** donne accès à une personne : **Peut consulter** ou **Peut modifier**. Elle le trouve sous **Partagés avec vous** dans la barre. Quiconque reçoit l'accès voit chaque série du tableau de bord, y compris les hôtes de
vos agents, et rien d'autre de vos données. Une personne qui ne peut que consulter peut choisir une autre durée
pour elle-même ; rien de ce qu'elle fait n'est enregistré.

La fenêtre contient aussi le lien du tableau de bord. Il ouvre le tableau de bord à quiconque a reçu l'accès, et
à personne d'autre.

## Limites

- Supprimer un tableau de bord supprime ses widgets ; les métriques restent.
- Un hôte qui redémarre sans cesse est listé sous **Vous attend** dans la cloche d'activité.
