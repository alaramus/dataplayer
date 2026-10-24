# A source type shown as a card per product

Decision D264. The catalog of new connections showed one card per source type.
`mysql` is one type for two products (D228), so a person running MariaDB had
to know to pick MySQL, and the card offered to start both servers (D244).

## What it does

A source type may declare **faces**: the cards the catalog shows for it, each
with a key, a title and the service templates it offers. `mysql` declares two,
MySQL and MariaDB. A type without faces is its own one card, as before.

- **Every card is the type.** Both open the existing form of `mysql`, save a
  connection of type `mysql`, and the server says which it is when the
  connection is checked (D228). There is no MariaDB type and no MariaDB
  driver, so nothing can be connected the wrong way.
- **Its own name and picture.** A card has its title and its logo — the logo
  keyed by the card in the client, as a type's is. The form a card opens starts
  with the card's name, so the MariaDB card opens a connection called
  MariaDB, and the window carries the card's picture.
- **Its own server.** A card offers only its templates: the MariaDB card
  offers to start MariaDB, the MySQL card MySQL (D244). A type of one card
  offers every template of the type, as before.
- **Counted and found as cards.** The category count is the number of cards.
  The search of source types (D202) matches a card's title as a name, so
  "maria" finds MariaDB as itself; a hit is still the type, and shows each of
  its cards.

## Where it lives

Faces are declared where the type is registered, and the list of types sends
them, translated: what a type is called is the server's (D13). The client
only expands a type into its cards and draws each one's logo.

Rejected: a second registered type for MariaDB. It would be a second form, a
second driver entry and a choice a person could get wrong, for a server the
connection identifies by itself.
