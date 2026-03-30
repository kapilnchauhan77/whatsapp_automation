# WhatsApp Business Cloud API — Setup & Configuration Research

**Research Stage:** 3  
**Date:** 2026-03-28  
**Sources:** Meta Developer Docs, LogRocket, Anjok Technologies, Notiqoo, WhatsApp Business Blog, SES, Dev.to

---

## 1. Meta Developer Account Setup

### Prerequisites
- A personal Facebook account (or managed Meta account)
- Registered as a Meta Developer at [developers.facebook.com](https://developers.facebook.com)

### Steps
1. Go to [developers.facebook.com](https://developers.facebook.com) and log in with your Facebook account.
2. Click **"My Apps"** → **"Create App"**.
3. When prompted for app type, select **"Other"**, then choose **"Business"**.
4. Give the app a name (e.g., `MyApp WhatsApp Bot`) and optionally link it to a Meta Business Manager account.
5. Click **"Create App"** to finalize.

### Add WhatsApp Product
1. In the App Dashboard left sidebar, click **"Add Product"**.
2. Find **WhatsApp** in the list and click **"Set Up"**.
3. You will be prompted to select or create a WhatsApp Business Account (WABA).

---

## 2. WhatsApp Business Account (WABA) Setup

### Option A: During App Creation (New WABA)
- When adding the WhatsApp product, choose **"Create a new WhatsApp Business Account"**.
- Provide a business display name and accept the terms of service.
- A WABA ID is generated and linked to your app.

### Option B: Link Existing WABA
- Under **WhatsApp → Configuration** in the App Dashboard, connect an existing verified Business Manager account.
- The WABA must belong to a Meta Business Manager account you administer.

### Meta Business Manager
- Required for production use, system user creation, and asset management.
- Access at [business.facebook.com](https://business.facebook.com).
- Business verification may be required before going live (uploading official business documents).

---

## 3. Phone Number Registration & Verification

### Test Phone Number (Development)
- When you add WhatsApp to your app, Meta **automatically provides a test business phone number** (also called the sandbox number).
- This test number has its own `PHONE_NUMBER_ID` — use this for development.
- **Limitation:** Cannot be used in production; can only send messages to up to **5 pre-verified recipient phone numbers** in test/development mode.
- No OTP or verification needed for the test number — it is pre-registered.

### Adding a Real Phone Number (Production)
1. In the App Dashboard, go to **WhatsApp → Phone Numbers → Add Phone Number**.
2. Enter the business display name and phone number.
3. Verify ownership via **OTP** (sent by SMS or voice call).
4. Once verified, the number is registered and assigned a `PHONE_NUMBER_ID`.
5. **Important:** A phone number used with the WhatsApp Business API **cannot simultaneously be used** on WhatsApp Messenger or WhatsApp Business App.

### Requirements for a Valid Business Number
- Must be a real, working phone number (mobile, landline, or VoIP capable of receiving SMS/calls).
- Must not already be registered on WhatsApp Messenger.
- The number becomes exclusively an API number once registered.

---

## 4. Test Mode & Development Sandbox

### Sandbox Recipient Limit
- In development/test mode, you can only send messages to **up to 5 pre-registered recipient phone numbers**.
- To add recipients: In the **WhatsApp API Setup** section, enter the phone number and verify via OTP.

### Test Phone Number Details
- Meta provides a test sender number with a `phone_number_id` visible in the dashboard.
- Use this `phone_number_id` in your API calls during development.
- The `hello_world` template message can be sent immediately without any template approval.

### Sending the First Test Message
```bash
curl -X POST \
  "https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" \
  -H "Authorization: Bearer {ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "{RECIPIENT_PHONE_NUMBER}",
    "type": "template",
    "template": {
      "name": "hello_world",
      "language": { "code": "en_US" }
    }
  }'
```

---

## 5. Access Tokens

### 5a. Temporary Access Token
- **Location:** App Dashboard → WhatsApp → API Setup → "Temporary access token" field
- **Expiry:** ~24 hours
- **Use:** Only for initial testing / sending the first hello_world message
- **NOT suitable for development or production**

### 5b. Permanent System User Access Token (Recommended)

#### Step-by-step:
1. Go to [Meta Business Settings](https://business.facebook.com/settings) → **Users** → **System Users**
2. Click **"Add"** → name the system user (e.g., `whatsapp-api-bot`) → set role to **Admin** → click **"Create System User"**
3. Select the new system user → click **"Add Assets"**
   - Under **Apps**: select your Meta app → enable **"Full Control"** (Manage App)
   - Under **WhatsApp Accounts**: select your WABA → enable **"Full Control"** (Manage WhatsApp Business Accounts)
   - Click **"Assign Assets"**
4. Click **"Generate Token"** on the system user row
5. Select your **App** from the dropdown
6. Set **Token Expiration** → choose **"Never"** for a non-expiring token
7. Select these **permissions/scopes**:
   - `whatsapp_business_messaging` ← required to send/receive messages
   - `whatsapp_business_management` ← required to manage phone numbers, templates, etc.
   - `business_management` ← recommended
   - `catalog_management` ← if using product catalogs
8. Click **"Generate Token"** — **copy and store immediately** (shown only once)

#### Token Usage in API Calls
```
Authorization: Bearer {SYSTEM_USER_ACCESS_TOKEN}
```

#### Security
- Never embed tokens in client-side code.
- Store as environment variables or use cloud secrets managers (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager).
- Treat like database credentials — anyone with the token has full API access.

---

## 6. Webhook Configuration

### Purpose
Webhooks are required to **receive** incoming messages, delivery receipts, read receipts, and status updates from WhatsApp.

### Requirements
- A publicly accessible **HTTPS endpoint** with a valid SSL certificate.
- Two HTTP handlers on your server:
  - `GET /webhook` → for Meta's verification handshake
  - `POST /webhook` → for receiving actual events

### Webhook Verification Flow (GET)
When you register a webhook URL in the dashboard, Meta sends a `GET` request with:
```
?hub.mode=subscribe
&hub.verify_token={YOUR_VERIFY_TOKEN}
&hub.challenge={RANDOM_STRING}
```
Your server must:
1. Check `hub.verify_token` matches your configured `VERIFY_TOKEN`
2. If match: respond with `hub.challenge` value (HTTP 200)
3. If no match: respond with HTTP 403

```python
# Python/Flask example
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == os.environ['VERIFY_TOKEN']:
        return challenge, 200
    return 'Forbidden', 403
```

```javascript
// Node.js/Express example
app.get('/webhook', (req, res) => {
  const mode = req.query['hub.mode'];
  const token = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];
  if (mode === 'subscribe' && token === process.env.VERIFY_TOKEN) {
    res.status(200).send(challenge);
  } else {
    res.sendStatus(403);
  }
});
```

### Webhook Payload Handling (POST)
```javascript
app.post('/webhook', (req, res) => {
  const body = req.body;
  if (body.object === 'whatsapp_business_account') {
    // process messages
    res.sendStatus(200);
  } else {
    res.sendStatus(404);
  }
});
```

### Registering Webhook in Meta Dashboard
1. App Dashboard → **WhatsApp** → **Configuration** → **Webhooks** section
2. Click **"Edit"**
3. **Callback URL:** Your public HTTPS endpoint (e.g., `https://abc123.ngrok.io/webhook`)
4. **Verify Token:** The secret string you defined in your app (matches `VERIFY_TOKEN` env var)
5. Click **"Verify and Save"** — Meta fires the GET verification request immediately
6. After verification, click **"Manage"** to subscribe to webhook fields:
   - `messages` ← required for receiving incoming messages
   - `message_deliveries` ← delivery confirmations
   - `message_reads` ← read receipts
   - `messaging_postbacks` ← button/interactive message responses
   - `message_status` ← general status updates

### HMAC Signature Verification (Security)
Every POST webhook request from Meta includes:
```
X-Hub-Signature-256: sha256={HMAC_HASH}
```
To validate:
```python
import hmac, hashlib

def verify_signature(payload_body: bytes, signature_header: str, app_secret: str) -> bool:
    expected = 'sha256=' + hmac.new(
        app_secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```
- `app_secret` comes from: App Dashboard → **Settings** → **Basic** → **App Secret**
- Always verify against the **raw request body** (before JSON parsing)

---

## 7. Required Permissions & Scopes

| Permission | Purpose |
|---|---|
| `whatsapp_business_messaging` | Send and receive messages via Cloud API |
| `whatsapp_business_management` | Manage phone numbers, templates, WABA settings |
| `business_management` | Access Business Manager resources |
| `catalog_management` | Use product catalogs in messages (optional) |

These are granted when generating the system user token (step 7 in Section 5b).

For **webhook subscriptions**, no additional OAuth scopes are needed — the app's page/business subscription covers it once the WABA is linked.

---

## 8. Environment Variables (.env)

### Complete .env Reference

```bash
# ─── WhatsApp Cloud API Core ───────────────────────────────────────────
# Access token (system user permanent token — never expires)
WHATSAPP_TOKEN=EAAxxxxxxxxxxxxxxx

# Phone Number ID (from Meta dashboard: WhatsApp > API Setup)
PHONE_NUMBER_ID=123456789012345

# WhatsApp Business Account ID (WABA ID)
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765

# ─── Webhook Security ──────────────────────────────────────────────────
# Your custom verify token — any random string you choose
VERIFY_TOKEN=my_super_secret_verify_token_2025

# App Secret (from App Dashboard > Settings > Basic > App Secret)
# Used for HMAC-SHA256 signature verification of incoming webhooks
APP_SECRET=abc123def456abc123def456abc123de

# ─── App Identification ────────────────────────────────────────────────
# Your Meta App ID (from App Dashboard)
APP_ID=1234567890123456

# ─── API Configuration ─────────────────────────────────────────────────
# Graph API version
GRAPH_API_VERSION=v21.0

# Base URL (usually not needed as env var, but useful)
WHATSAPP_API_URL=https://graph.facebook.com/v21.0

# ─── Server ────────────────────────────────────────────────────────────
PORT=3000
NODE_ENV=development
```

### Where to Find Each Value

| Variable | Location in Meta Dashboard |
|---|---|
| `WHATSAPP_TOKEN` | Business Settings → System Users → Generate Token |
| `PHONE_NUMBER_ID` | App Dashboard → WhatsApp → API Setup → Phone Number ID field |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | App Dashboard → WhatsApp → API Setup → WhatsApp Business Account ID |
| `VERIFY_TOKEN` | You define this — use any random secure string |
| `APP_SECRET` | App Dashboard → Settings → Basic → App Secret (click "Show") |
| `APP_ID` | App Dashboard → Settings → Basic → App ID (top of page) |

### Python-style .env (for python-dotenv / FastAPI)
```bash
WHATSAPP_TOKEN=EAAxxxxxxxxxxxxxxx
PHONE_NUMBER_ID=123456789012345
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765
VERIFY_TOKEN=my_secure_verify_token
APP_SECRET=abc123def456abc123def456abc123de
APP_ID=1234567890123456
GRAPH_API_VERSION=v21.0
PORT=8000
```

---

## 9. Ngrok / Local Tunneling for Development

### Why Needed
Meta's webhook system requires a **publicly accessible HTTPS URL**. During local development, your server runs on `localhost` which is not publicly reachable. A tunnel exposes your local port to the internet.

### Option A: ngrok (Most Common)

#### Installation
```bash
# macOS (Homebrew)
brew install ngrok/ngrok/ngrok

# Or download from https://ngrok.com/download
```

#### Sign Up & Auth Token
```bash
# Sign up at https://ngrok.com, get your auth token
ngrok config add-authtoken {YOUR_NGROK_AUTH_TOKEN}
```

#### Start Tunnel
```bash
# Expose port 3000 (or whatever your app runs on)
ngrok http 3000
```

Output looks like:
```
Forwarding  https://7b9b-102-219-204-54.ngrok.io -> http://localhost:3000
```

#### Use in Meta Dashboard
- Callback URL: `https://7b9b-102-219-204-54.ngrok.io/webhook`

#### Persistent/Static Domain (Paid ngrok or Free tier limit)
```bash
# Free tier gives 1 static domain
ngrok http --domain=your-static-domain.ngrok-free.app 3000
```

#### Important ngrok Notes
- Free tier generates a **new random URL on every restart** — re-register in Meta dashboard each time.
- Paid plans ($10/month+) provide static URLs — more practical for ongoing development.
- ngrok has a **WhatsApp-specific integration guide** at [ngrok.com/partners/whatsapp](https://ngrok.com/partners/whatsapp).

### Option B: Tunnelmole (Free Alternative)
```bash
# Install
curl -O https://install.tunnelmole.com/xD345/install && sudo bash install

# Expose port 3000
tmole 3000
```
Generates: `https://k8sctb-ip-1-2-3-4.tunnelmole.net`

### Option C: Cloudflare Tunnel (Free, Persistent)
```bash
# Install cloudflared
brew install cloudflare/cloudflare/cloudflared

# One-time setup
cloudflared tunnel login

# Run tunnel
cloudflared tunnel --url http://localhost:3000
```
Cloudflare provides a stable `*.trycloudflare.com` URL (free, no account needed for quick tunnels).

### Option D: Deploy to a Server (Staging/Production)
- Deploy to Heroku, Railway, Render, or a VPS
- Use your deployment URL directly as the webhook callback
- Add a `Procfile` (Heroku): `web: gunicorn wsgi:app`

---

## 10. Complete Setup Checklist

```
[ ] 1. Create Meta Developer account at developers.facebook.com
[ ] 2. Create a new Meta App (type: Business)
[ ] 3. Add WhatsApp product to the app
[ ] 4. Create or link a WhatsApp Business Account (WABA)
[ ] 5. Note the test phone number's PHONE_NUMBER_ID from API Setup
[ ] 6. Add up to 5 recipient test phone numbers (verify each by OTP)
[ ] 7. Create a System User in Business Settings → Users → System Users
[ ] 8. Assign app and WABA assets to the system user (Full Control)
[ ] 9. Generate a permanent token with whatsapp_business_messaging + whatsapp_business_management scopes
[ ] 10. Copy APP_SECRET from App Dashboard → Settings → Basic
[ ] 11. Create .env file with all variables (WHATSAPP_TOKEN, PHONE_NUMBER_ID, VERIFY_TOKEN, APP_SECRET, etc.)
[ ] 12. Build GET /webhook endpoint (verify token + return challenge)
[ ] 13. Build POST /webhook endpoint (receive messages)
[ ] 14. Start ngrok: `ngrok http 3000`
[ ] 15. Register ngrok HTTPS URL as webhook callback in Meta dashboard
[ ] 16. Subscribe to "messages" (and other desired) webhook fields
[ ] 17. Send test hello_world template message to verify end-to-end
[ ] 18. Test incoming message receipt via webhook
```

---

## 11. Graph API Endpoint Reference

```
Base URL:  https://graph.facebook.com/{API_VERSION}

Send message:         POST /{PHONE_NUMBER_ID}/messages
Get phone numbers:    GET /{WABA_ID}/phone_numbers
Get message templates:GET /{WABA_ID}/message_templates
Upload media:         POST /{PHONE_NUMBER_ID}/media
Get media URL:        GET /{MEDIA_ID}
Mark message read:    PUT /{PHONE_NUMBER_ID}/messages
```

### Current API Version
- As of 2025/2026: **v21.0** is current stable
- Meta deprecates old versions ~2 years after release
- Always pin your version in the URL

---

## Sources

- [WhatsApp Cloud API Get Started — Meta for Developers](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)
- [Using Authorization Tokens — Meta Developer Blog](https://developers.facebook.com/blog/post/2022/12/05/auth-tokens/)
- [Access Tokens Guide — Meta for Developers](https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/)
- [Set Up Webhooks — Meta for Developers](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks/)
- [Business Phone Numbers — Meta for Developers](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers)
- [Build eCommerce App with WhatsApp Cloud API — LogRocket Blog](https://blog.logrocket.com/build-ecommerce-app-whatsapp-cloud-api-node-js/)
- [WhatsApp Cloud API Step-by-Step Setup — Anjok Technologies](https://anjoktechnologies.in/blog/how-to-set-up-whatsapp-cloud-api-step-by-step-in-meta-developer-business-manager)
- [Permanent Access Token Guide — Anjok Technologies](https://anjoktechnologies.in/blog/-meta-whatsapp-cloud-api-permanent-access-token)
- [Generate Permanent Token — Notiqoo Docs](https://notiqoo.com/docs/notiqoo-pro/related-guides/how-to-generate-a-permanent-token-for-whatsapp-cloud-api/)
- [How to Test WhatsApp Webhooks Locally — Software Engineering Standard](https://softwareengineeringstandard.com/2025/08/31/whatsapp-webhook/)
- [Implementing Webhooks from WhatsApp Business Platform](https://business.whatsapp.com/blog/how-to-use-webhooks-from-whatsapp-business-api)
- [WhatsApp + ngrok Integration](https://ngrok.com/partners/whatsapp)
- [Webhook Configuration (Flask) — Dev.to](https://dev.to/koladev/building-a-web-service-whatsapp-cloud-api-flask-webhook-configuration-part-2-l1k)
- [Setup WhatsApp Business API 2025 — BotPenguin](https://botpenguin.com/blogs/setup-whatsapp-business-api)
- [WhatsApp Business Registration via Meta Cloud API — Medium](https://medium.com/@hamzas2401/how-i-registered-my-whatsapp-business-number-on-meta-b175a290a451)
