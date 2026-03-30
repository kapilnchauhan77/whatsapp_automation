# WhatsApp Message Acknowledgment Systems — Research Report
**Stage**: 4 — Best Practices & Patterns
**Date**: 2026-03-28

---

## 1. Read Receipts — Marking Messages as "Read"

### Endpoint

```
POST https://graph.facebook.com/v{API_VERSION}/{PHONE_NUMBER_ID}/messages
```

### Request Headers

```
Authorization: Bearer {ACCESS_TOKEN}
Content-Type: application/json
```

### Request Body

```json
{
  "messaging_product": "whatsapp",
  "status": "read",
  "message_id": "wamid.XXXXXXXXXXXXXXXX"
}
```

### Key Behaviors

- The `message_id` is the inbound message ID received in the webhook payload
  (`entry[0].changes[0].value.messages[0].id`)
- Marking a message as read also marks **all earlier messages** in the conversation as read
- The recipient sees two **blue checkmarks** on their message
- This is a best-effort call — failures should be logged but not block the main flow

### Node.js SDK Pattern

```javascript
async function markAsRead(wa, messageId) {
  await wa.messages.status({
    messaging_product: "whatsapp",
    status: "read",
    message_id: messageId,
  });
}

// In webhook callback:
if (body?.entry[0].changes[0].field === "messages" &&
    body.entry[0].changes[0].value.messages) {
  const msgId = body.entry[0].changes[0].value.messages[0].id;
  await markAsRead(wa, msgId);
}
```

### When to Mark as Read

- Send the `status: "read"` call **after** successfully enqueuing/processing
  the inbound message, not before
- Sending it immediately on receipt (before processing) can mislead users into
  thinking their message has been handled when it hasn't yet

---

## 2. The 24-Hour Customer Service Window Rule

### How It Works

| Scenario | Allowed Message Types |
|----------|-----------------------|
| User sent a message within the last 24 hours | Any free-form message (text, media, interactive, location, contacts) |
| More than 24 hours since user's last message | **Approved templates only** |
| Business-initiated (no prior user message) | **Approved templates only** |

### Window Lifecycle

1. User sends any message to your business number
2. A 24-hour clock starts
3. During this window: send any free-form messages freely (no Meta approval required)
4. If the user replies again: the clock **resets** to a fresh 24 hours from that reply
5. When the clock expires: API returns error **131047** if you attempt free-form

### Why This Matters for Acknowledgments

Acknowledgment auto-replies (e.g., "Thanks, we received your message") are
**always safe** because:
- The user just sent a message → the 24-hour window just opened
- Your reply is within that window by definition

For **follow-up messages** sent hours later, check whether the window is still open.

### Error When Window Expires

```
Error 131047: Re-engagement message
"More than 24 hours have passed since the recipient last replied."
Fix: Use an approved template message instead.
```

---

## 3. Message Templates — When Required vs. Free-Form

### Free-Form Messages (No Template Needed)

- Allowed **only within the 24-hour customer service window**
- Supported types: text (up to 4,096 chars), images (5 MB), video (16 MB),
  audio (16 MB), documents (100 MB), stickers, interactive buttons/lists,
  product displays, location, contacts
- **No Meta pre-approval required**
- WhatsApp will reject them if sent outside the window

### Template Messages (Pre-Approved Required)

- Required for **all business-initiated messages** outside the 24-hour window
- Must be submitted to Meta for approval before use
- Categories: Marketing, Utility, Authentication
- Can be sent at any time to opted-in users
- Once a user replies to a template, the 24-hour free-form window opens

### For Acknowledgment Auto-Replies Specifically

Since the user just triggered the webhook by sending a message, you are always
within the 24-hour window. **No template is needed for immediate acknowledgments.**

Template approval IS needed for:
- Proactive status updates sent hours after the last user message
- Follow-up messages sent when users have not messaged recently
- Marketing or notification campaigns

---

## 4. Idempotency — Handling Duplicate Webhook Deliveries

### Why Duplicates Happen

Meta delivers webhooks with **at-least-once** semantics. Duplicates occur due to:
- Network failures where the 200 OK response is lost in transit
- WhatsApp retrying after no acknowledgment (5–10 second timeout)
- Transient infrastructure issues on Meta's side
- Status changes generating multiple events per message (sent → delivered → read)

### Deduplication Pattern (Redis-Based)

```python
import redis
r = redis.Redis()

def handle_webhook(message_id: str, process_fn):
    key = f"whatsapp:processed:{message_id}"
    # SETNX: set if not exists, returns True only first time
    if not r.set(key, "1", nx=True, ex=3600):  # TTL: 1 hour
        # Already processed — skip silently
        return
    process_fn(message_id)
```

### Deduplication Pattern (Database-Based)

```python
# Use a unique constraint on message_id in your DB
try:
    db.execute(
        "INSERT INTO processed_messages (message_id, processed_at) VALUES (?, NOW())",
        [message_id]
    )
except UniqueConstraintError:
    return  # Already processed
```

### What to Deduplicate

- **Inbound messages**: key = `messages[].id` from webhook payload
- **Status updates**: key = `statuses[].id` (separate namespace from messages)
- **Do NOT** use the same key space for both

### Event Ordering

WhatsApp does **not** guarantee event order. You may receive:
- `read` before `delivered` (safe to infer `delivered` happened implicitly)
- Older messages arriving after newer ones

Use the `timestamp` field from the webhook payload for actual ordering, not
arrival time.

---

## 5. Webhook Response — The 200 OK Requirement

### Critical Rule

**Return HTTP 200 OK immediately.** Meta enforces a strict **5–10 second timeout**.
If your endpoint takes longer or returns a non-200 status:

1. Meta considers the delivery failed
2. Meta **retries** the webhook (generating duplicates)
3. Retries use **exponential backoff**, can persist for **up to 7 days**
4. Burst retries can overwhelm your infrastructure (each sent message = up to 3
   status callbacks; 500 msg/s = 1,500+ webhooks/s)

### Correct Pattern

```python
# FastAPI example
@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    # 1. Validate signature FIRST (fast operation)
    payload = await request.body()
    validate_signature(request.headers.get("X-Hub-Signature-256"), payload)

    # 2. Parse payload
    data = await request.json()

    # 3. Enqueue for async processing (fast)
    background_tasks.add_task(process_webhook_async, data)

    # 4. Return 200 immediately — BEFORE processing
    return Response(status_code=200)
```

### Signature Validation

```python
import hmac, hashlib

def validate_signature(header_sig: str, payload: bytes):
    app_secret = os.environ["META_APP_SECRET"]
    expected = "sha256=" + hmac.new(
        app_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(header_sig, expected):
        raise HTTPException(status_code=401)
```

---

## 6. Async Processing Architecture

### Recommended Architecture

```
Webhook Endpoint (FastAPI/Flask)
    │
    ├── 1. Validate X-Hub-Signature-256     (sync, <1ms)
    ├── 2. Parse payload                    (sync, <1ms)
    ├── 3. Enqueue to message queue         (sync, <5ms)
    └── 4. Return HTTP 200                  (total: <10ms)

Message Queue (Redis Streams / RabbitMQ / SQS / Celery)
    │
    └── Worker Pool
            ├── Deduplication check (Redis SETNX)
            ├── Mark message as read (WhatsApp API call)
            ├── Send acknowledgment reply (WhatsApp API call)
            └── Business logic (DB writes, notifications, etc.)
```

### Why Async is Required

- WhatsApp API calls to send messages or mark as read can take 100ms–2s
- DB writes, downstream service calls take time
- All of this **must not happen in the webhook handler**
- The handler's only job: validate + enqueue + 200 OK

### Queue Technology Options

| Queue | Use Case |
|-------|----------|
| Celery + Redis | Python-native, simple setup, good for moderate scale |
| Redis Streams | Built-in consumer groups, persistent, low overhead |
| RabbitMQ | Complex routing, dead-letter queues, enterprise use |
| AWS SQS | Managed, auto-scaling, good for cloud deployments |

### Dead Letter Queue

Always configure a DLQ to capture messages that fail after N retries.
Inspect DLQ messages to diagnose systemic failures (expired tokens, rate limits, etc.).

---

## 7. Error Handling — Common Errors & Strategies

### Complete Error Reference

| Code | Title | Meaning | Handling Strategy |
|------|-------|---------|-------------------|
| **0** | AuthException | App user cannot be authenticated | Refresh access token immediately |
| **190** | Token Expired | Access token has expired | Rotate token; alert ops team |
| **10** | Permission Denied | Permission not granted or removed | Check app permissions in Meta dashboard |
| **4** | Too Many Calls | App-level rate limit hit | Exponential backoff; reduce request frequency |
| **80007** | WABA Rate Limit | WhatsApp Business Account rate limit | Back off; consult rate limits docs |
| **130429** | Throughput Limit | Cloud API message throughput exceeded | Implement token bucket; retry with backoff |
| **131048** | Spam Rate Limit | Message flagged as spam | Review message quality; monitor WABA health |
| **131056** | Pair Rate Limit | Too many msgs to same recipient in short period | Add per-recipient send throttling |
| **131047** | Re-engagement | >24h since last user reply | Switch to approved template |
| **131026** | Undeliverable | Recipient unreachable / blocked / outdated app | Do not retry immediately; log and alert |
| **131049** | Meta Chose Not to Deliver | Ecosystem health decision | Retry with increasing intervals |
| **131050** | User Opted Out | User stopped marketing messages | Remove from send list; respect opt-out |
| **131021** | Sender = Recipient | Sending to your own number | Fix routing logic |
| **131000** | Unknown Error | Generic failure | Retry; if persistent open support ticket |
| **131008** | Missing Parameter | Required field missing in request | Fix request construction |
| **132001** | Template Not Found | Template name/language wrong or not approved | Verify template name and approval status |
| **132015** | Template Paused | Low quality template paused | Edit template and resubmit |
| **132016** | Template Disabled | Permanently disabled (too many pauses) | Create new template |
| **1** | API Unknown | Invalid request or server error | Check Meta status page; verify request |
| **2** | API Service | Temporary downtime/overload | Check Meta status; retry after delay |

### Retry Strategy

```python
import asyncio
from typing import Optional

RETRYABLE_ERRORS = {4, 80007, 130429, 131048, 131049, 131000, 1, 2}
NON_RETRYABLE_ERRORS = {131026, 131050, 131021, 131047, 190}

async def send_with_retry(payload: dict, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = await whatsapp_api.send(payload)
            return response
        except WhatsAppAPIError as e:
            if e.code in NON_RETRYABLE_ERRORS:
                logger.warning(f"Non-retryable error {e.code}: {e.message}")
                raise  # Don't retry
            if e.code not in RETRYABLE_ERRORS:
                raise  # Unknown error — don't retry blindly
            wait = 2 ** attempt  # 1s, 2s, 4s
            await asyncio.sleep(wait)
    raise MaxRetriesExceeded()
```

---

## 8. Auto-Reply Message Content Best Practices

### Template Examples

**Immediate Acknowledgment (within 24-hour window — no template needed):**
```
"Thanks for reaching out! We've received your message and will get back
to you within [X hours/business hours]. Reference: #{ticket_id}"
```

**Out-of-hours acknowledgment:**
```
"Hi {name}, thanks for your message! Our team is currently offline
(business hours: Mon–Fri 9am–6pm). We'll reply first thing tomorrow."
```

**Queue/High-volume:**
```
"Your message is in our queue. We're experiencing high volume and will
respond within [X hours]. You can also check our FAQ at {url}."
```

### Content Guidelines

- **Be specific with timelines** — avoid "as soon as possible"; say "within 4 hours"
- **Set clear expectations** — confirm receipt and when to expect a real response
- **Provide alternatives** — link to FAQ, knowledge base, or self-service options
- **Personalize when possible** — include user name, ticket number
- **Keep it short** — 1–3 sentences maximum for acknowledgments
- **Avoid over-automation** — don't send acknowledgment if you can respond in <5 minutes

---

## 9. Summary — Implementation Checklist

### Webhook Handler (Must be < 10ms total)
- [ ] Validate `X-Hub-Signature-256` header (HMAC-SHA256)
- [ ] Parse payload
- [ ] Push to async queue
- [ ] Return HTTP 200 immediately

### Async Worker (After queue)
- [ ] Deduplicate using `message_id` + Redis SETNX (TTL: 1–4 hours)
- [ ] Mark message as read: `POST /{PHONE_NUMBER_ID}/messages` with `status: "read"`
- [ ] Send acknowledgment reply (free-form — within 24-hour window)
- [ ] Implement retry with exponential backoff for retryable errors (130429, 4, 2, 1)
- [ ] Do NOT retry non-retryable errors (131026, 131050, 131047)
- [ ] Log all raw payloads to durable storage before processing
- [ ] Monitor template status webhooks (`message_template_status_update`)

### Infrastructure
- [ ] Dead letter queue for failed messages after N retries
- [ ] Monitor WABA phone number quality (`phone_number_quality_update`)
- [ ] Alert on 401/403 errors (token expiry)
- [ ] Provision for up to 3x webhook volume vs. outbound message volume
- [ ] Store processed `message_id`s with TTL to handle Meta's 7-day retry window

---

## Sources

- [Read Receipts — Meta for Developers](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/mark-message-as-read/)
- [Messages Reference — Meta for Developers](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/)
- [WhatsApp Webhooks Best Practices — Hookdeck](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices)
- [Scalable Webhook Architecture — ChatArchitect](https://www.chatarchitect.com/news/building-a-scalable-webhook-architecture-for-custom-whatsapp-solutions)
- [Free-Form Messages — Infobip](https://www.infobip.com/docs/whatsapp/message-types-and-templates/free-form-messages)
- [24-Hour Conversation Window — ActiveCampaign](https://help.activecampaign.com/hc/en-us/articles/20679458055964-Understanding-the-24-hour-conversation-window-in-WhatsApp-messaging)
- [WhatsApp Cloud API Error Codes — WA Bridge](https://wabridge.com/help/whatsapp-cloud-api-error-codes)
- [All Meta Error Codes — Heltar](https://www.heltar.com/blogs/all-meta-error-codes-explained-along-with-complete-troubleshooting-guide-2025-cm69x5e0k000710xtwup66500)
- [Error 131026/131049 — Fyno](https://www.fyno.io/blog/top-reasons-why-your-whatsapp-messages-are-failing-or-error-code-131026-and-1026-cltwuhs510009uw10yerk1onq)
- [Webhook Idempotency — Medium/Neurobyte](https://medium.com/@kaushalsinh73/top-7-webhook-reliability-tricks-for-idempotency-a098f3ef5809)
- [WhatsApp Receive Webhook Guide — WASenderApi](https://wasenderapi.com/blog/how-to-receive-whatsapp-messages-via-webhook-the-ultimate-2025-guide)
- [WhatsApp Business API 24-hour Window — SMSMode](https://www.smsmode.com/en/whatsapp-business-api-customer-care-window-ou-templates-comment-les-utiliser/)
- [Node.js SDK Status Reference](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/messages/status/)
