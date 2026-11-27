# Comptes cloud

Un compte cloud est le moyen par lequel une connexion atteint un cloud en
votre nom : pour obtenir un jeton qui ouvre une base de données, ou pour lire un
mot de passe conservé dans un coffre de secrets. Il vous appartient, comme une
clé SSH : une connexion le nomme, et la personne avec qui vous partagez la
connexion l’utilise sans le voir. Les comptes se trouvent dans les
**Préférences**, sous **Comptes cloud** ; la page **Options** de la fenêtre
d’une connexion a aussi un bouton **Nouveau compte**.

## Types

- **Amazon Web Services** : une **Clé d’accès** et sa **Clé secrète**, avec un
  **Jeton de session** pour des identifiants temporaires. Il peut endosser un
  **Rôle** — son ARN, un **ID externe**, le nom et la durée de la session.
- **Google Cloud** : un fichier de **Clé de compte de service** en JSON. Il
  peut agir en tant qu’un autre compte de service, si celui-ci le lui permet.
- **Microsoft Azure** : un **Principal de service** — locataire, ID client et
  secret client.
- **HashiCorp Vault** : son **Adresse**, un espace de noms et un certificat
  d’AC au besoin, et un **Jeton** ou le Role ID et le Secret ID d’un
  **AppRole**.

Les secrets sont conservés chiffrés et ne sont plus jamais affichés.
**Tester** fait l’appel inoffensif le moins coûteux que permet le compte et
dit qui s’est connecté.

## L’identité propre de ce serveur

Un compte peut aussi se connecter en tant que la machine où tourne DataPlayer :
la chaîne d’identifiants par défaut d’AWS, les Application Default Credentials
de Google, une identité managée d’Azure. N’importe qui pourrait emprunter cette
identité ; elle n’est donc proposée que là où l’installation le permet, et
alors seulement à un superutilisateur.

## Ce qu’une connexion en fait

Un jeton est émis pour chaque nouvelle connexion et gardé en mémoire seulement
jusqu’à peu avant son expiration ; rien de ce qui est émis n’est stocké. La
page de chaque source indique quels modes de connexion utilisent un compte :

- PostgreSQL et MySQL : AWS IAM (RDS), Google Cloud IAM (Cloud SQL), Microsoft
  Entra, un coffre de secrets, les identifiants dynamiques de Vault.
- Redis : AWS IAM (ElastiCache, MemoryDB), Microsoft Entra.
- MongoDB : AWS IAM (MONGODB-AWS), un coffre de secrets.
- Kafka : AWS IAM (MSK).
- S3 : un compte AWS au lieu d’une clé.

Un **Coffre de secrets** nomme le secret là où il est conservé : chez AWS par
son nom ou son ARN ; chez Google comme `projects/P/secrets/S`, ou par son seul
nom dans le projet du fichier de clé ; chez Azure comme `VAULT/NAME` ; dans
Vault comme `MOUNT/PATH`. Un secret en JSON est lu par ses clés `password` et
`username`, qui peuvent être renommées ; tout autre secret est le mot de passe
lui-même.

Un serveur qui vérifie les mots de passe auprès de LDAP, PAM, RADIUS ou Active
Directory n’a besoin d’aucun compte : pour DataPlayer, c’est un mot de passe.

## Limites

- Un compte garde son type ; créez-en un nouveau pour un autre cloud.
- Un compte utilisé par une connexion ne peut être supprimé ; le refus nomme
  les connexions.
- Un jeton qui expire pendant une longue sauvegarde ne l’arrête pas : la
  connexion qu’il a ouverte reste valide.
- Les outils de Kafka dans un terminal ne savent pas encore se connecter avec
  AWS IAM ou OIDC.
