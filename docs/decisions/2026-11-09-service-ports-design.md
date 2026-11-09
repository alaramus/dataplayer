# A service with more than one port, and a page to open from a connection

Decisions D333 and D334. Asked for after the RabbitMQ service (D332), whose
management API answered only inside DataPlayer: a template had one port, and
the user wants every port a service listens on reachable from their machine,
since other services with two or more ports will come. And a RabbitMQ
connection should open its management page in the browser from its menu.

## Several ports a template places (D333)

A template keeps its one main port — the one a connector is given as its
port, and the only one a person may ask for by number (D89) — and may name
more: each extra port has a key, the port inside the container and a title a
person reads. Every port is published on the loopback when the service is
published, and the runtime picks a free host port for each extra one; what it
picked is read back off the container with the main port, written on the
service row as a map from key to port, and shown on the service's row.

A connector option may be filled from an extra port: a value that names a key
and a scheme becomes `scheme://127.0.0.1:<published port>`, the address a
person's browser on this machine opens. It is empty when the service is not
published.

Rejected:

- one template per port — a service is one container, and its row, volume and
  life are one;
- naming the extra ports' host numbers in the request — the runtime picks, as
  it does for the main port when nobody names one, and a person who needs one
  number has the main port for it.

The map is a column of its own on the service row, added by a migration: the
schema changes by revisions from now on, since installations other than the
developer's exist.

## Opening a page from a connection (D334)

An action may open an address rather than change anything: it says so
(`opens_address`), the menu performs it without a form, and its result's
`open_url` is opened in a new browser tab. The tab is opened at the click and
pointed at the address when the answer comes, so a browser does not take it
for a pop-up.

RabbitMQ's **Open management** is such an action, on every level of its
catalog. Its address is the connection's new option **Address for the
browser**, or the management address when that is empty. A RabbitMQ started
here fills the option from its published management port, so the page opens
on the person's machine while the application keeps reaching the API by the
container's name. It needs read access only: it changes nothing.
