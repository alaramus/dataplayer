# Préférences et votre compte

**Préférences**, dans le menu utilisateur en haut à droite, contient ce qui vous appartient plutôt qu'à une seule
connexion. **Se déconnecter** se trouve dans le même menu.

## Général

- **Langue** : la langue de toute l'interface. Elle est conservée avec votre compte et vous suit dans n'importe quel
  navigateur. Tant qu'aucune langue n'est choisie, celle du navigateur est utilisée.
- **Apparence** : un thème clair ou sombre, ou **Système**, qui suit le système d'exploitation. Conservé avec votre
  compte.
- **Voix de lecture** : la voix qui lit les messages à haute voix. Les voix appartiennent au navigateur, ce réglage est
  donc conservé dans ce navigateur.
- **Stockage personnel** : la part de vos propres fichiers sur ce serveur que vous utilisez, par rapport à la limite
  fixée par un administrateur.

## Connexions

**Fréquence de vérification des connexions** : chaque connexion est sondée selon ce planning pendant qu'un espace de travail
est ouvert, et le point à côté dans la liste indique le résultat de la dernière réponse. **Jamais** ne vérifie que
lorsque vous le demandez. Un serveur lent ou éloigné mérite d'être interrogé moins souvent.

## Clés SSH

Les clés avec lesquelles vos connexions SSH s'identifient. Davantage d'informations figurent sur la page [SSH](source-ssh.md).

- **Nouvelle clé** en crée une sur ce serveur, où elle reste. **Copier la clé publique** et ajoutez-la à `authorized_keys` sur
  les serveurs qu'elle doit ouvrir.
- **Importer** récupère une clé que vous possédez déjà.
- Une clé peut conserver sa phrase de passe, ne pas en avoir, ou la demander. Une clé qui la demande est **Verrouillée**
  jusqu'à ce que vous la **Déverrouiller** pendant 15 minutes, 1 heure ou 8 heures ; **La verrouiller maintenant** la verrouille à nouveau.
- Une clé utilisée par une connexion ne peut pas être supprimée tant que ces connexions n'en utilisent pas une autre.

## Visites guidées

La visite de bienvenue et de courtes visites de chaque partie de DataPlayer — une table lue autrement, un pipeline, les
tableaux de bord, l'agent. **Faire** en lance une, **Refaire** répète une visite déjà faite. Une visite crée pour elle-même
une base d'entraînement et la retire à la fin.

## Accès MCP

Les jetons avec lesquels un agent IA extérieur à DataPlayer, comme Claude Code, Cursor ou Codex, travaille avec vos
connexions. Leur création est décrite sur la page [L'agent IA](assistant.md).

## Administration

Un administrateur dispose en plus de **Administration** dans le menu utilisateur, avec **Utilisateurs** :

- **Nouvel utilisateur** crée un compte. Il attend un mot de passe : **Lien pour définir le mot de passe** fournit un lien à envoyer à la
  personne, qui fonctionne une fois et pendant une durée limitée. Le même lien réinitialise un mot de passe oublié.
- **Modifier ce compte** modifie le nom, si la personne **Peut se connecter**, si elle est **Administrateur**, et sa
  **Limite de stockage**.
- **Supprimer ce compte et tout ce qu'il possède** supprime la personne avec ses connexions et ses fichiers.

Un administrateur gère les comptes, pas les données des autres : il ne voit pas les connexions des autres personnes.
