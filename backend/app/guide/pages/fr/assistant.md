# L'agent IA

L'agent répond dans l'espace **IA** de l'interrupteur, en haut de la barre de gauche. Il travaille à travers
vos connexions comme vous le feriez : il les liste, trouve et lit des tables et des fichiers, exécute des
requêtes et des actions, ouvre des éléments dans l'espace Data, trace des graphiques — et lit ce guide pour
répondre à vos questions sur DataPlayer lui-même. Une modification qu'il veut faire vous est d'abord soumise.

## Avant le premier chat

L'agent fonctionne avec votre propre clé d'un fournisseur de modèles : Anthropic, OpenAI, Google, DeepSeek et
d'autres.

1. Ouvrez l'espace IA et **Préférences**.
2. Choisissez un modèle. L'icône de clé à côté ouvre la clé du fournisseur : collez-la, cliquez sur **Vérifier**,
   puis enregistrez. Une seule clé sert à tous les modèles de ce fournisseur.
3. Le modèle choisi dans les paramètres est celui avec lequel démarre un nouveau chat. Chaque chat peut en
   choisir un autre dans sa propre zone de saisie.

## Un chat

- **Nouvelle discussion** en démarre un. Écrivez dans **Envoyer un message à l'agent** puis cliquez sur **Envoyer** ; là où le navigateur
  peut écouter, le micro dicte à la place.
- Pendant que l'agent travaille, ses étapes s'affichent une à une : ce qu'il a lu, ce qu'il a exécuté, combien de
  temps cela a pris. **Arrêter** met fin à la réponse.
- Les réponses sont du texte mis en forme, avec des tableaux, des graphiques et des diagrammes. Chacun peut être
  copié ou lu à voix haute.
- Sélectionner des mots dans une réponse propose **Ajouter à la discussion**, qui les cite dans votre message suivant, et
  **Plus de détails**, qui demande à la discussion rapide de les expliquer.

## Ce que l'agent connaît

L'agent ne voit pas votre écran. Pour le diriger vers quelque chose, utilisez **Joindre des onglets ou des fichiers** :

- **Onglets de l'espace de travail…** : jusqu'à cinq onglets ouverts — une table, un catalogue, une requête, un résultat — pour
  le message suivant ;
- **Fichiers de l'ordinateur…** : des fichiers texte, et des images PNG, JPEG, WebP ou GIF pour un modèle qui lit les
  images.

Sans pièce jointe, il trouve les éléments par leur nom grâce à la recherche. Lorsque plusieurs connexions
correspondent à un nom, il demande laquelle.

## Modifications

**Modifications**, dans la zone de saisie, indique ce que l'agent peut modifier dans ce chat :

- **Lecture seule** : rien n'est modifié depuis ce chat ;
- **Demander avant les modifications**, mode dans lequel commence chaque chat : une modification attend votre réponse sur une
  carte avec **Allow once**, **Allow all changes in this chat** et **Autoriser toutes les modifications dans chaque discussion**. La carte
  montre ce qui changerait — les instructions, et ce qu'une suppression emporterait avec elle ;
- **Autoriser les modifications** : les modifications de ce chat s'exécutent sans demander ;
- **Laisser Jev décider** : Jev, un service distinct avec sa propre clé, décide avant chaque modification ;
- **Autoriser toutes les modifications dans chaque discussion** est un réglage de votre compte, et non du chat. Il se désactive à nouveau dans
  **Préférences**, sous **Confirmations**.

Un chat qui attend votre réponse est listé sous **Vous attend** dans la cloche d'activité. Une connexion réglée sur
**Lecture seule** pour les consoles n'est jamais modifiée, et un niveau d'accès que vous n'avez pas n'est jamais utilisé.

## Quelles connexions il peut lire

L'agent ne lit une connexion que si son propriétaire a activé **Autoriser l'envoi de données à des tiers** sur la page
**Autorisations** de la connexion : ce qu'il lit est envoyé au fournisseur du modèle. Sinon, l'agent ne voit que le nom
et le type de la connexion, rien d'autre. Le propriétaire peut l'autoriser depuis l'étape refusée ; une personne avec
qui la connexion est partagée est invitée à demander au propriétaire.

Désactiver ce réglage plus tard retire de la suite des réponses du chat ce qui avait été lu depuis cette connexion.

## Chats, projets et archive

- La liste des chats a les chats **Épinglées** en haut et un filtre par nom.
- Un chat peut être épinglé, déplacé dans un projet, renommé et archivé.
- **Nouveau projet** regroupe des chats. Supprimer un projet demande si ses chats doivent revenir dans la liste ou
  aller dans l'archive.
- **Archives**, dans les paramètres, restaure les chats archivés ou les supprime définitivement.

## Choix du modèle par Jev

Au lieu d'un modèle, **Choisir avec Jev** laisse Jev en choisir un pour chaque réponse parmi les modèles dont vous
avez défini les clés. Votre demande est envoyée à TypeSafe, le fournisseur de Jev, pour faire ce choix. Il faut une
clé Jev, à définir dans les paramètres.

## Discussion rapide

**Discussion rapide**, en haut de la barre de gauche, ouvre une fenêtre pour une conversation simple avec un modèle, depuis
n'importe quel espace. Elle n'a pas d'outils et ne peut rien lire dans DataPlayer. Dans Chrome sur un ordinateur de
bureau, elle peut être servie par Gemini Nano, qui fonctionne sur votre ordinateur une fois que Chrome l'a téléchargé,
si bien que rien ne sort de la machine. Les discussions rapides apparaissent dans le même historique que les chats de
l'agent.

## Outils des serveurs MCP externes

L'agent peut aussi appeler les outils des serveurs MCP que vous ajoutez : un suivi de tickets, un wiki, un service
qui vous appartient.

1. Ouvrez l'espace IA et **Préférences**, puis **Ajouter un serveur** sous **Serveurs MCP externes**.
2. Donnez-lui un nom et son adresse Streamable HTTP, par exemple `https://mcp.example.com/mcp`. Un **Jeton Bearer**
   et des **Autres en-têtes** sont envoyés avec chaque requête ; une fois enregistrés, ils ne sont plus jamais affichés,
   et un champ vide conserve ce qui est défini.
3. **Outils** demande au serveur ce qu'il propose. Chaque outil indique **Lit** ou **Demande d'abord**, et peut être
   désactivé.

- Un outil qui ne dit pas qu'il ne fait que lire est traité comme une modification : il demande d'abord, avec les
  arguments qu'il enverrait ; un chat **Lecture seule** le refuse, et **Autoriser les modifications** le laisse s'exécuter.
- L'icône du serveur dans la zone de saisie active ou désactive chaque serveur pour ce chat.
- Un serveur qui ne répond pas est laissé de côté dans cette réponse ; le reste du chat continue.
- La liste n'appartient qu'à vous. Ce que l'agent transmet à un outil quitte DataPlayer, y compris les données lues
  depuis vos connexions.
- Une adresse de cette machine ou de son réseau privé est refusée, sauf si l'installation l'autorise.

## Un agent IA externe

Un agent extérieur à DataPlayer — Claude Code, Cursor, Codex et d'autres — peut travailler avec vos connexions par
l'adresse MCP de DataPlayer.

1. **Préférences**, depuis le menu utilisateur, puis **Accès MCP**.
2. **Nouveau jeton** : un nom, **Lecture seule** ou **Accès complet**, et la date d'expiration. **Lecture seule** lit les
   catalogues, les lignes et les requêtes et refuse toute modification ; **Accès complet** modifie les données et exécute
   des actions sans demander.
3. Copiez le jeton : il n'est affiché qu'une fois. La fenêtre indique aussi la ligne ou l'entrée de fichier qui
   configure le client choisi.

L'agent externe dispose des mêmes outils que celui-ci, ce guide compris, et ne lit que les connexions dont le
propriétaire autorise l'envoi de données à des tiers. **Révoquer ce jeton** le coupe à son prochain appel.

## Limites

- Une réponse fait au plus 50 appels d'outils ; au-delà, posez une question plus étroite.
- Une lecture renvoie au plus 20 lignes à la fois.
- Un message transporte un nombre limité de fichiers d'une taille limitée ; la zone de saisie indique la limite
  atteinte.
