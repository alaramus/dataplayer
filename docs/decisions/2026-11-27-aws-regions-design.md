# AWS regions chosen, not typed

Asked for: wherever a connection window asks for a region, offer a choice
instead of a box to type in, the list asked of Amazon itself.

## D461. A region is chosen from what Amazon answers

Three kinds of field name an AWS region: an AWS cloud account's (where its
credentials are asked), the IAM variants of PostgreSQL, MySQL, Redis, Kafka and
MongoDB (D453), and S3's. Each says so with `x-ui-purpose: aws-region`, and the
form turns it into a choice once a list arrives.

**Where the list comes from.** `GET /cloud-accounts/regions`:

- With `account`, one of the person's AWS accounts: EC2's `DescribeRegions`
  through it, which answers the regions that account has enabled — an opt-in
  region it has not switched on is not offered.
- Without one, or when the account may not ask (EC2 refuses, the role cannot
  be assumed, it signs in as this server where that is no longer lent):
  Amazon's published IP ranges, `ip-ranges.amazonaws.com/ip-ranges.json`, the
  one list Amazon publishes without credentials. Its regions are read out and
  kept a day in the process.
- When Amazon does not answer at all: the regions botocore was shipped
  knowing, of the ordinary partitions (commercial, GovCloud, China, European
  Sovereign Cloud), so an offline server still offers a list.

Rejected: botocore's list alone. It is what the installed SDK knew, and the
first live answer already held a region it did not (`us-south-1`). Rejected
too: the SSM public parameters, which need credentials, and AWS's regional
services table, which is larger and says the same.

**Titles.** Neither answer says what a region is called; botocore does,
"Europe (Frankfurt)", in English as Amazon's console writes it. A region
botocore does not know is shown by its name alone.

**Never a refusal.** The list is a convenience: the route answers an empty
list rather than an error when the provider has none or fails, and the form
then keeps the box. A wrong key is found by the account's own Test.

**The cloud account's own form** asks the published list: the account is still
being written, and its settings on screen are not yet the stored ones.

**S3 keeps typing for other stores.** S3's field carries
`x-ui-typed-when: endpoint`: with an endpoint filled the store is MinIO, R2 or
another provider's, whose regions Amazon does not know ("auto" for R2), so the
box stays.

**What the form holds.** The empty choice comes first, the field's line under
it still saying what empty means. A region the connection holds and the list
does not — an opt-in region switched off since — stays as a choice of its own,
so opening the form does not change it.
