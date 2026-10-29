## What I built and why

I decided to tackle Task C - Fullstack: Outbound webhooks because I thought it was the most interesting one, with a bit of both backend and frontend work, showing the full circle of triggering an event (I've used contract creation for that), sending that to the local test webhook and logging the delivery or failure in the UI. It was also a good exercise to think about synchronous versus asynchronous processing for event deliveries.


## Key implementation notes

I created two models:

- `WebhookEndpoint` for the webhook data. This model includes a secret generated on creation, and a unique constraint (`company`, `url`).
- `WebhookDelivery` for the event delivery data, whether it was successful or not, and the number of attempted deliveries. 

For both, I have used `DELIVERY_EVENT_TYPE_CHOICES`. Having different event types allows users to define specific destinations for specific event types.

Secrets are displayed in the UI once, on webhook creation. A secret is used to sign a request header (with `HMAC-SHA256`), the idea is for receivers to add that secret on their side and verify the signature to check that it is coming from YunoJuno servers. The secret is stored in plain text, because signing needs the original value (a hash wouldn't work here), so it must never be logged.

Deliveries are displayed in each webhook endpoint detail page. The API endpoint serves only the 50 most recent deliveries (I'd add pagination with more time).

Please check the implementation for additional details related to CRUD operations on webhooks, how they are displayed and how a test event is sent. The local webhook receiver does not check the webhook secret, so sending a test event to it should get received and registered without errors.

Events are identified by UUIDs. Receivers can use that UUID to implement dedupe in their own systems.

With regard to sync or async delivery, I've added an in-process `transaction.on_commit(lambda: publish_event(...))` to `ContractCreateSerializer.create` to trigger an event from the UI, and send that event to the local test webhook receiver http://localhost:8027/hook to check that everything works as expected. However, I have added that sync processing for illustrative purposes only. I haven't tried to manage delivery failures, retries and backoffs in the application, as that gets complicated and messy (retry state, backoff timers and crash recovery all living inside the web process), and in my opinion is the wrong approach. Instead, I think that having the delivery as a separate service, with the application publishing events to a queue and workers that report back via an API endpoint is a preferable design. Please check `WebhookDeliveryReportViewStub` for some initial ideas on that. It is only a stub: it has no implementation and no real authentication yet, and its docstring describes the contract I had in mind (idempotent reports per event, destination and attempt).

## Workflow

I have used Cursor with Opus 5.5 to plan, Sonnet 5.5 to implement, and GLM 5.3 Flash for quick questions and brainstorming. I have also reused two skills (for python/django and react/ts), slightly adapted after asking an agent to look at the existing code in the repo.

I decided not to create an initial plan for the whole implementation, and instead going step by step specifying what I wanted to achieve, reviewing and asking for changes for every new feature.

## Tests and known limitations

I added backend tests for the webhooks app (models, signing, payloads, delivery and the API views), plus frontend tests for the `DeveloperSettings` and `WebhookDetail` pages.

Things I know are missing or rough:

* No retries: each event gets a single attempt, and a failed one is just logged as a failed delivery.
* The `on_commit` publish runs inside the request, so a slow receiver slows down contract creation (deliveries have a 10 second timeout, and redirects are not followed). If the process dies after commit, the event is lost.
* Endpoint URLs are not restricted, so there is no protection against an admin pointing a webhook at an internal address (SSRF). I'd want an allowlist or a block on private IP ranges before this goes anywhere real.
* The deliveries list is capped at the 50 most recent, with no pagination.
* `WebhookDeliveryReportViewStub` is not implemented.
* Only contract creation is wired up to publish an event. The timesheet event types exist as choices, but nothing publishes them yet.

## Next steps

If I had more time, I'd add asynchronous processing of event deliveries. The app would publish events to a queue (e.g. RabbitMQ, or SQS via LocalStack) and workers would consume them, deliver to the endpoints, and report results back to the YunoJuno server, which would create the appropriate WebhookDelivery objects. To avoid losing events if the process dies after commit (which is a problem with the sync option I submitted for this exercise), I'd write the event to an outbox table in the same transaction and publish from there. This still leaves things to design for, such as duplicate deliveries and workers crashing mid-delivery. But retries, backoff and giving up (via a dead-letter queue) are handled by the broker rather than by custom code.
