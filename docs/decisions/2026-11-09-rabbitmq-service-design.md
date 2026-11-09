# A RabbitMQ started here, and its lab

Decision D332. The fifth slice of the RabbitMQ source: a broker this server
starts on request, as Kafka's is (D311), and a lab to try the source on.

## The template

`rabbitmq:4.3.7-management`, the release the source is tested against and
whose `rabbitmqadmin` the terminal runs (D328). It asks for a password — a
broker with only `guest` refuses that user from anywhere but its own
loopback — made up by the server unless the requester names one, and a user
written here, `dataplayer`, given to the image as `RABBITMQ_DEFAULT_USER` and
`RABBITMQ_DEFAULT_PASS`. There is no unprotected shape.

The node's name is fixed to `rabbit@localhost`. RabbitMQ keeps its data under
the node's name, which is otherwise the container's hostname; a container made
again for the same volume would come up as a new node beside its own data.

## Two ports, one placed

A template has one container port, and RabbitMQ answers on two. AMQP, 5672, is
the template's port: published on the loopback for the person's own clients
and given to the connection as its host and port. The management API, 15672,
is not published. The application reaches a service by its container name on
the service network (D89), where every port of the container answers, and the
connection leaves its management address empty, which is `http://<host>:15672`
(D325). So the catalog, the reports, the actions and the terminal work, while
a tool on the person's own machine reaches AMQP only — the same kind of
deviation as Kafka's announced address.

Rejected: a second published port — the template, the placement, the service
row and its screen all speak of one port, and changing that for one image
reaches every other template.

## The lab

Asked for when the service is started, as every template's is, and written
out rather than generated so two demonstrations look the same:

- `lab.orders`, a topic exchange, routing `orders.new` and `orders.paid`;
- `lab.billing`, a classic queue bound to `orders.#`, sixty orders waiting,
  dead-lettering to `lab.dead-letter`;
- `lab.shipping`, a quorum queue bound to `orders.paid`, so it holds the paid
  ones only;
- `lab.dead-letter`, a fanout exchange, and `lab.dead`, the queue behind it;
- `lab.alerts`, a headers exchange, and `lab.alerts.critical` bound to it
  with `x-match=all` and `level=critical`, holding the critical alerts;
- `lab.trades`, a stream of three hundred JSON trades over one day and a few
  bodies that are bytes, so its page, its fields and its hex are seen.

Nothing in the lab consumes, so every count stays where the lab left it.
