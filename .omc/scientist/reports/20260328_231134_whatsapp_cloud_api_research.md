# WhatsApp Business Cloud API — Comprehensive Research Report
Generated: 2026-03-28 23:11:34

---

## Executive Summary

The WhatsApp Business Cloud API (Cloud API) is Meta's hosted messaging API that allows businesses to send and receive WhatsApp messages programmatically via the Graph API (`graph.facebook.com`). As of October 2025, the legacy On-Premises API is fully sunset and the Cloud API is the only supported path. Authentication uses Bearer tokens passed in HTTP headers. Webhooks use a two-phase GET verification + POST notification pattern. Pricing shifted to per-message in November 2024, with service messages free and marketing messages charged per-market rates.

---

## 1. API Overview

### What Is It?

The **WhatsApp Business Cloud API** (Cloud API) is a Meta-hosted implementation of the WhatsApp Business Platform. It allows businesses and developers to:
- Send and receive WhatsApp messages at scale
- Integrate with CRM, automation, and customer service systems
- Use message templates, interactive messages, and media
- Manage contacts and business profiles

The API is accessed via Meta's **Graph API** at:
```
https://graph.facebook.com/{version}/{endpoint}
```
Current supported version: **v21.0** (and v22.0 as of early 2025).

### Cloud API vs. On-Premises API

| Feature | Cloud API | On-Premises API |
|---|---|---|
| **Hosting** | Hosted by Meta | Self-hosted by business/BSP |
| **Infrastructure** | Zero server management | Requires dedicated servers + IT team |
| **Setup** | Fast — minutes via Meta App Dashboard | Slow — days to weeks |
| **Upgrades** | Automatic by Meta | Manual, business responsibility |
| **Throughput** | Up to 1,000 msg/sec | ~250 msg/sec max |
| **Uptime SLA** | 99.9% uptime, <5s p99 latency | Depends on your infra |
| **New Features** | All new features ship here first | Frozen at v2.53 (Jan 2024) |
| **Cost** | Pay per message only | Hosting + IT + per-message fees |
| **Status** | **Active — only supported option** | **Sunset October 23, 2025** |

> **Critical:** The On-Premises API client expired October 23, 2025 and can no longer send messages. All integrations must use Cloud API.

### Key Capabilities
- Text, image, video, audio, document, sticker, location, contact card messages
- Message templates (pre-approved for business-initiated conversations)
- Interactive messages (buttons, list menus)
- Reactions, replies
- Webhook-based delivery of incoming messages and status updates
- Media upload/download via separate Media API
- Business profile management
- Phone number registration and verification

---

## 2. Authentication

### Prerequisites
1. A **Meta Developer Account** (developers.facebook.com)
2. A **Meta App** (type: Business)
3. A **WhatsApp Business Account (WABA)**
4. A **Business Phone Number** registered in the WABA
5. Business verification via Meta Business Manager

### Token Types

There are three token types used with the Cloud API:

#### a) User Access Token
- Short-lived (expires in hours)
- Used only during initial development and testing in the App Dashboard
- **Not suitable for production**

#### b) System User Access Token (recommended for production)
- Long-lived token representing your business or automated service
- Created via **Meta Business Manager → System Users**
- Steps:
  1. Go to Business Settings → Users → System Users
  2. Create a System User (Admin role)
  3. Assign the WhatsApp app to that system user with appropriate permissions
  4. Generate token with scopes: `whatsapp_business_messaging`, `whatsapp_business_management`
- Token does not expire unless manually revoked
- Store securely (environment variable, secrets manager — never in code/DB)

#### c) Business Integration System User Access Token
- Used by **Tech Providers / ISVs** building on behalf of multiple client businesses
- Tied to Business Integration flow (OAuth-based onboarding)

### Using the Token in Requests

All API requests require the `Authorization` header:

```http
Authorization: Bearer {YOUR_ACCESS_TOKEN}
Content-Type: application/json
```

Or as a query parameter (less secure):
```
?access_token={YOUR_ACCESS_TOKEN}
```

### Required Identifiers
You also need these IDs for API calls:
- **`{phone_number_id}`** — The ID of your registered business phone number (NOT the phone number itself). Found in App Dashboard → WhatsApp → API Setup.
- **`{waba_id}`** — WhatsApp Business Account ID. Found in Business Manager.

---

## 3. Webhook Setup

Webhooks are how your server receives incoming messages, delivery receipts, and other notifications from WhatsApp.

### Requirements
- A publicly accessible HTTPS endpoint (valid TLS certificate; self-signed NOT supported)
- Must respond within **20 seconds** or Meta will retry
- Required app permissions:
  - `whatsapp_business_messaging` — for message webhooks
  - `whatsapp_business_management` — for other webhooks

### Step 1: Configure Webhook in App Dashboard

1. Go to Meta App Dashboard → WhatsApp → Configuration
2. Set **Callback URL**: `https://yourdomain.com/webhook`
3. Set **Verify Token**: any string you choose (e.g., `my_secret_verify_token_123`)
4. Click **Verify and Save** — Meta will immediately send a GET verification request

### Step 2: Handle the Verification Request (GET)

When you click "Verify and Save", Meta sends a **GET request** to your callback URL with three query parameters:

| Parameter | Description |
|---|---|
| `hub.mode` | Always `"subscribe"` |
| `hub.verify_token` | The verify token you set in the dashboard |
| `hub.challenge` | A random integer string you must echo back |

**Your endpoint must:**
1. Check `hub.mode === "subscribe"`
2. Check `hub.verify_token` matches your configured token
3. Respond with HTTP 200 and the raw `hub.challenge` value as the body

```python
# Python / Flask example
from flask import Flask, request, jsonify
import os

app = Flask(__name__)
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200  # Echo challenge as plain text
    else:
        return "Forbidden", 403
```

```javascript
// Node.js / Express example
app.get("/webhook", (req, res) => {
    const mode = req.query["hub.mode"];
    const token = req.query["hub.verify_token"];
    const challenge = req.query["hub.challenge"];

    if (mode === "subscribe" && token === process.env.VERIFY_TOKEN) {
        res.status(200).send(challenge);
    } else {
        res.sendStatus(403);
    }
});
```

### Step 3: Subscribe to Webhook Fields

After verification, subscribe to the `messages` field (and optionally others) in the App Dashboard under Webhook Fields. Available fields include:
- `messages` — incoming messages and status updates
- `message_template_status_update` — template approval/rejection
- `account_update` — WABA changes
- `phone_number_quality_update` — phone number quality rating changes

### Step 4: Handle Incoming Notifications (POST)

Meta sends **POST requests** to your webhook for every incoming event. You must respond with HTTP 200 quickly (ideally within 1 second) — process the payload asynchronously.

---

## 4. Incoming Webhook Message Format

### Top-Level Structure

Every webhook notification follows this envelope:

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "WABA_ID",
      "changes": [
        {
          "field": "messages",
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "15550001234",
              "phone_number_id": "PHONE_NUMBER_ID"
            },
            "contacts": [
              {
                "profile": {
                  "name": "John Doe"
                },
                "wa_id": "15559998765"
              }
            ],
            "messages": [ /* message objects */ ],
            "statuses": [ /* status update objects (separate from messages) */ ]
          }
        }
      ]
    }
  ]
}
```

### Extracting Key Fields

```python
body = request.get_json()

# Safety checks
entry = body.get("entry", [{}])[0]
changes = entry.get("changes", [{}])[0]
value = changes.get("value", {})
messages = value.get("messages", [])

if messages:
    msg = messages[0]
    
    sender_phone = msg["from"]                    # e.g. "15559998765"
    message_id   = msg["id"]                      # e.g. "wamid.HBgN..."
    timestamp    = msg["timestamp"]               # Unix epoch string
    message_type = msg["type"]                    # "text", "image", "audio", etc.
    phone_number_id = value["metadata"]["phone_number_id"]
    sender_name  = value["contacts"][0]["profile"]["name"]
```

### Message Types and Their Payloads

#### Text Message
```json
{
  "from": "15559998765",
  "id": "wamid.HBgN...",
  "timestamp": "1704067200",
  "type": "text",
  "text": {
    "body": "Hello, I need help with my order"
  }
}
```

#### Image Message
```json
{
  "from": "15559998765",
  "id": "wamid.HBgN...",
  "timestamp": "1704067200",
  "type": "image",
  "image": {
    "id": "MEDIA_ID",
    "mime_type": "image/jpeg",
    "sha256": "HASH",
    "caption": "Optional caption text"
  }
}
```

#### Audio Message (voice note)
```json
{
  "from": "15559998765",
  "id": "wamid.HBgN...",
  "timestamp": "1704067200",
  "type": "audio",
  "audio": {
    "id": "MEDIA_ID",
    "mime_type": "audio/ogg; codecs=opus",
    "voice": true
  }
}
```

#### Video Message
```json
{
  "type": "video",
  "video": {
    "id": "MEDIA_ID",
    "mime_type": "video/mp4",
    "sha256": "HASH",
    "caption": "Optional caption"
  }
}
```

#### Document Message
```json
{
  "type": "document",
  "document": {
    "id": "MEDIA_ID",
    "mime_type": "application/pdf",
    "sha256": "HASH",
    "filename": "invoice.pdf",
    "caption": "Your invoice"
  }
}
```

#### Location Message
```json
{
  "type": "location",
  "location": {
    "latitude": 37.422,
    "longitude": -122.084,
    "name": "Googleplex",
    "address": "1600 Amphitheatre Parkway"
  }
}
```

#### Interactive Message (Button Reply)
```json
{
  "type": "interactive",
  "interactive": {
    "type": "button_reply",
    "button_reply": {
      "id": "BUTTON_ID",
      "title": "Yes, confirm"
    }
  }
}
```

#### Interactive Message (List Reply)
```json
{
  "type": "interactive",
  "interactive": {
    "type": "list_reply",
    "list_reply": {
      "id": "ROW_ID",
      "title": "Option 1",
      "description": "Description of option"
    }
  }
}
```

#### Status Update (delivery receipts — in `statuses` array, NOT `messages`)
```json
{
  "id": "wamid.HBgN...",
  "status": "sent",        // "sent" | "delivered" | "read" | "failed"
  "timestamp": "1704067200",
  "recipient_id": "15559998765",
  "conversation": {
    "id": "CONVERSATION_ID",
    "origin": { "type": "service" }
  },
  "pricing": {
    "billable": true,
    "pricing_model": "CBP",
    "category": "service"
  }
}
```

### Checking for Status vs. Message

```python
value = body["entry"][0]["changes"][0]["value"]

if "messages" in value:
    # Incoming message from user
    handle_message(value["messages"][0])
elif "statuses" in value:
    # Delivery/read receipt for a message you sent
    handle_status(value["statuses"][0])
```

---

## 5. Sending Messages

### Endpoint

```
POST https://graph.facebook.com/v21.0/{phone_number_id}/messages
```

### Required Headers

```http
Authorization: Bearer {ACCESS_TOKEN}
Content-Type: application/json
```

### Text Message

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "15559998765",
  "type": "text",
  "text": {
    "body": "Hello! How can I help you today?",
    "preview_url": false
  }
}
```

### Template Message (for business-initiated conversations)

Templates must be pre-approved by Meta before use.

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "15559998765",
  "type": "template",
  "template": {
    "name": "hello_world",
    "language": {
      "code": "en_US"
    },
    "components": [
      {
        "type": "body",
        "parameters": [
          {
            "type": "text",
            "text": "John"
          }
        ]
      }
    ]
  }
}
```

### Image Message

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "15559998765",
  "type": "image",
  "image": {
    "link": "https://example.com/image.jpg",
    "caption": "Check this out!"
  }
}
```

### Interactive Button Message

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "15559998765",
  "type": "interactive",
  "interactive": {
    "type": "button",
    "body": {
      "text": "Would you like to confirm your order?"
    },
    "action": {
      "buttons": [
        {
          "type": "reply",
          "reply": { "id": "confirm_yes", "title": "Yes, confirm" }
        },
        {
          "type": "reply",
          "reply": { "id": "confirm_no", "title": "No, cancel" }
        }
      ]
    }
  }
}
```

### Reaction Message

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "15559998765",
  "type": "reaction",
  "reaction": {
    "message_id": "wamid.HBgN...",
    "emoji": "\uD83D\uDC4D"
  }
}
```

### Success Response

```json
{
  "messaging_product": "whatsapp",
  "contacts": [
    {
      "input": "15559998765",
      "wa_id": "15559998765"
    }
  ],
  "messages": [
    {
      "id": "wamid.HBgN...",
      "message_status": "accepted"
    }
  ]
}
```

`message_status` values:
- `accepted` — message queued for delivery
- `held_for_quality_assessment` — under review before sending
- `paused` — held due to quality rating issues

### cURL Example

```bash
curl -X POST \
  "https://graph.facebook.com/v21.0/PHONE_NUMBER_ID/messages" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "15559998765",
    "type": "text",
    "text": {"body": "Hello from Cloud API!"}
  }'
```

---

## 6. Rate Limits

### API-Level Rate Limits (Graph API)

| Condition | Limit |
|---|---|
| Default (any app, any WABA) | 200 requests/hour per app per WABA |
| Active WABA (≥1 registered phone number) | 5,000 requests/hour per app per WABA |

### Throughput (Messages Per Second — MPS)

| Tier | MPS | Notes |
|---|---|---|
| Default | 80 msg/sec | All new phone numbers start here |
| Upgraded | 1,000 msg/sec | Requires eligibility criteria (see below) |

**Burst allowance:** Up to 45 messages in a 6-second burst, but then you must wait out the equivalent time at normal rate.

**Eligibility for 1,000 MPS upgrade:**
- Phone number registered with Cloud API (not On-Premises)
- Medium or higher quality rating
- Can initiate conversations with unlimited unique users in 24h window
- Submit request via Meta Support

### Messaging Limits (Unique Users per 24h — Template Messages Only)

This applies to **business-initiated** template messages (not replies):

| Tier | Unique Users in 24h |
|---|---|
| Tier 1 (new accounts) | 1,000 |
| Tier 2 | 10,000 |
| Tier 3 | 100,000 |
| Tier 4 (unlimited) | Unlimited |

Tiers upgrade automatically based on message volume and quality rating. Tier 4 (unlimited) is granted after demonstrating consistent high-quality messaging.

**Note:** Messaging limits apply only to template (business-initiated) messages. Reply messages within an open customer service window (24h after last user message) are **not subject** to messaging limits.

### Phone Number to User Rate Limit

A single phone number can send **1 message every 6 seconds to the same user** (≈ 10/min per recipient), preventing spam.

---

## 7. Pricing Model (as of November 2024)

### Overview

WhatsApp moved from **conversation-based pricing** to **per-message pricing** effective **November 1, 2024**.

Key changes:
- Charges applied when message is **delivered** (not sent)
- Rates vary by **market** (country of recipient) and **message category**
- Free entry points: 72-hour free window after user clicks a WhatsApp ad or FB Page CTA button

### Message Categories

| Category | Triggered By | Example Use Cases | Cost |
|---|---|---|---|
| **Marketing** | Business-initiated | Promotions, offers, abandoned cart reminders, newsletters | Paid (highest rate) |
| **Utility** | Business-initiated, triggered by user action | Order confirmations, shipping updates, appointment reminders | Paid (lower rate) |
| **Authentication** | Business-initiated | OTP/one-time passwords, verification codes | Paid (varies by market) |
| **Service** | User-initiated (reply within 24h window) | Customer support, answering inquiries | **Free** (as of Nov 1, 2024) |

### Free Messages

1. **Service messages**: All replies within the 24-hour customer service window are free
2. **Utility responses**: Utility template messages sent in direct response to a user message are free
3. **Click-to-WhatsApp**: 72-hour free window after user clicks a WhatsApp Ad or Facebook Page CTA button
4. **Free tier**: No monthly free conversation cap — free entry is based on categories above

### Pricing Rates (illustrative — exact rates vary by market)

Rates vary significantly by country. For example (approximate USD, may vary):

| Market | Marketing | Utility | Authentication |
|---|---|---|---|
| USA | ~$0.025/msg | ~$0.004/msg | ~$0.0135/msg |
| India | ~$0.0088/msg | ~$0.004/msg | ~$0.0019/msg |
| Brazil | ~$0.0625/msg | ~$0.008/msg | ~$0.019/msg |

*Always check the official Meta pricing page rate selector for current rates by market.*

### Volume Tiers (from July 2025)

Volume-based discounts available for utility and authentication messages — higher volume unlocks better per-message rates.

### Pricing Evolution Timeline

- **Pre-June 2023**: Per-conversation pricing, 1,000 free service conversations/month
- **June 2023**: Free tier removed from service conversations for most markets
- **November 1, 2024**: Per-message pricing; service messages become fully free
- **July 1, 2025**: Volume tiers introduced for utility/authentication; refined utility definitions

---

## 8. Key Integration Patterns

### Minimal Python Integration (FastAPI)

```python
import os
import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI()

VERIFY_TOKEN = os.environ["WHATSAPP_VERIFY_TOKEN"]
ACCESS_TOKEN = os.environ["WHATSAPP_ACCESS_TOKEN"]
PHONE_NUMBER_ID = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# --- Webhook verification ---
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=params["hub.challenge"], media_type="text/plain")
    return Response(status_code=403)

# --- Receive messages ---
@app.post("/webhook")
async def receive(request: Request):
    body = await request.json()
    try:
        value = body["entry"][0]["changes"][0]["value"]
        if "messages" in value:
            msg = value["messages"][0]
            sender = msg["from"]
            msg_type = msg["type"]
            if msg_type == "text":
                text = msg["text"]["body"]
                await send_message(sender, f"Echo: {text}")
    except (KeyError, IndexError):
        pass
    return Response(status_code=200)

# --- Send message ---
async def send_message(to: str, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{BASE_URL}/{PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"body": text}
            }
        )
```

---

## Limitations & Caveats

- Meta's documentation pages are JavaScript-rendered SPAs and cannot be fetched as static HTML — exact current field names should be verified against the live API reference at developers.facebook.com/docs/whatsapp/cloud-api/
- Pricing rates are market-specific and change regularly — always check the official pricing tool for current rates
- Webhook payloads may include additional fields not documented here; always use `.get()` with defaults for safe parsing
- Template messages require pre-approval (24-72 hours) before they can be sent
- Phone number can only be registered with ONE WABA at a time
- WhatsApp numbers used with the API cannot be used simultaneously with the WhatsApp mobile app

---

*Research compiled from Meta Developer Documentation, official WhatsApp Business Platform resources, and verified third-party technical sources. Report generated by Scientist Agent.*
