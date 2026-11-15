# E-mail

Votre boîte aux lettres dans DataPlayer : dossiers, messages, réponses et
pièces jointes, dans un onglet à part plutôt qu’un catalogue. Le
fonctionnement général des connexions est décrit sur la page
[Connexions](connections.md).

## Ce que vous pouvez voir

- Les dossiers de la boîte, avec le nombre de messages et de non lus
- Les messages d’un dossier, les plus récents d’abord, cinquante à la fois
- Les messages trouvés par des mots de l’expéditeur, de l’objet ou du texte
- Un message : de qui, à qui, son texte et ses pièces jointes
- Les images du web dans un message, quand vous les demandez
- Un avis quand de nouveaux messages arrivent dans la boîte de réception

## Ce que vous pouvez modifier

- Nouveaux messages, réponses, réponses à tous et transferts avec leurs fichiers
- Messages marqués lus ou non lus
- Messages déplacés vers la corbeille, puis supprimés définitivement
- Pièces jointes enregistrées sur l’ordinateur ou dans votre dossier
- Brouillons enregistrés, terminés plus tard et envoyés
- Messages déplacés vers un autre dossier
- Fichiers de votre propre dossier joints à un message

## Connexion

La page **Connexion** demande l’**Adresse e-mail** et **Votre nom**,
l’**Identifiant** (vide pour l’adresse) et le **Mot de passe** — pour Gmail,
Yandex ou Mail.ru, un mot de passe d’application —, le **Serveur IMAP**, le
**Port IMAP** et la **Sécurité IMAP** (`tls` 993, `starttls` 143, `none`
seulement dans votre réseau), le **Serveur SMTP**, le **Port SMTP** et la
**Sécurité SMTP** (`tls` 465, `starttls` 587), la **Connexion SMTP** et s’il
faut **Garder une copie dans Envoyés** — désactivé pour Gmail, qui le fait
lui-même.

**Vérifier** nomme l’étape qui a échoué. Avec `starttls`, un serveur qui ne
chiffre pas est refusé au lieu de recevoir le mot de passe en clair.

## L’onglet Courrier

À gauche les dossiers, au milieu les messages, à droite le message ouvert. Un
message ouvert est marqué lu. Un message en page web s’affiche sans scripts,
les images du web seulement après **Afficher les images**. **Supprimer**
déplace vers la corbeille ; dans la corbeille, la suppression est définitive
après confirmation. Une pièce jointe peut être **Téléchargée** ou
**Enregistrée dans mon dossier** — sous `Mail/<adresse>/`, sans rien écraser
et dans la limite de votre stockage. Pièces jointes d’un nouveau message :
25 Mo au total.

## Qui peut l’ouvrir

Vous seul. Une personne avec qui la connexion est partagée la voit mais ne
peut pas ouvrir la boîte. La recherche en haut et l’agent ne lisent pas le
courrier.

## Nouveautés de cette boîte

Le catalogue propose trois cartes : **E-mail** pour tout serveur, et **Gmail** et **Outlook**, qui remplissent leurs serveurs. Gmail demande un mot de passe d’application ; Microsoft 365 et Outlook.com refusent le plus souvent un mot de passe en IMAP.

Tant que vous êtes connecté, la boîte de réception est relue environ une fois par minute ; les nouveaux messages s’annoncent avec **Ouvrir**. **Déplacer vers un dossier** déplace le message ouvert. **Depuis mon dossier** joint des fichiers de votre stockage. **Enregistrer le brouillon** range le message dans Brouillons ; **Modifier** le reprend.

## Ce que l’e-mail ne fait pas encore ici

- Annoncer les nouveaux messages d’autres dossiers que la boîte de réception
- Drapeaux, signatures, glisser un message sur un dossier
- Gmail et Microsoft 365 sans mot de passe d’application, Exchange sans IMAP, tunnel SSH
