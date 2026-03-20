# Feature Card: WhatsApp Platform Adapter

## Problem

WhatsApp has ~2 billion monthly active users and dominates messaging in South/Southeast Asia, the Middle East, and Latin America — exactly the markets this restaurant bot serves (Afghan cuisine, multilingual with Arabic, Pashto, Farsi, Thai). Customers who don't use Telegram are unreachable today.

---

## Goal

Add a WhatsApp adapter so the existing bot experience (menu browsing, cart, ordering, admin panel) works over WhatsApp with zero changes to business logic. The adapter translates between our `core/types.py` abstractions and the WhatsApp Business API.

---

## WhatsApp Business API Overview

| Aspect | Detail |
|--------|--------|
| **API** | WhatsApp Business Platform (Cloud API, hosted by Meta) |
| **Auth** | Bearer token from Meta Business Suite |
| **Inbound** | Webhook POST to our server (messages, status updates) |
| **Outbound** | REST API (`POST /v17.0/{phone_number_id}/messages`) |
| **Message types** | Text, image, document, interactive (buttons/lists), template, location |
| **Pricing** | Free for user-initiated conversations (24h window). Business-initiated requires approved templates. |
| **Rate limits** | Tiered: 250 → 1K → 10K → 100K messages/day based on quality |

### Key Differences from Telegram

| Feature | Telegram | WhatsApp |
|---------|----------|----------|
| User identity | Integer `user_id` | Phone number (E.164: `+66812345678`) |
| Bot initiation | User sends `/start` | User sends any message (no commands) |
| Inline buttons | `InlineKeyboardButton` with callback_data (64 bytes) | Interactive message buttons (max 3) or list (max 10 sections × 10 rows) |
| Edit messages | `edit_message_text/media` | Not supported — must send new message |
| Callback responses | `answer_callback_query` (toast) | Webhook delivers button reply as new message |
| Image sending | `file_id` (cached) or upload | Media URL (HTTPS) or media ID (uploaded via API) |
| Commands | `/command` with BotFather | No concept of slash commands |
| Message format | HTML or Markdown | Limited formatting: `*bold*`, `_italic_`, `~strike~`, `` `code` `` |
| Conversation window | Unlimited | 24h from last user message (then template-only) |
| Typing indicator | `sendChatAction("typing")` | Not available in Cloud API |

---

## Proposed Design

### 1. Webhook server

The WhatsApp Cloud API delivers events via webhook. We need an HTTP server (already needed for LINE too). Use `aiohttp` or `fastapi` alongside aiogram's polling.

```python
# adapters/whatsapp_adapter.py

class WhatsAppAdapter(PlatformAdapter):
    def __init__(self, phone_number_id: str, access_token: str, verify_token: str, app_secret: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.verify_token = verify_token
        self.app_secret = app_secret
        self.api_base = f"https://graph.facebook.com/v17.0/{phone_number_id}"
        self._session: aiohttp.ClientSession | None = None

    async def start(self):
        """Start aiohttp webhook server."""
        self._session = aiohttp.ClientSession()
        app = web.Application()
        app.router.add_get("/webhook/whatsapp", self._verify)    # Meta verification challenge
        app.router.add_post("/webhook/whatsapp", self._handle)   # Inbound messages
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8080)
        await site.start()
```

### 2. Inbound message translation

```python
async def _handle(self, request: web.Request) -> web.Response:
    body = await request.json()
    # Validate signature with app_secret (HMAC-SHA256)
    if not self._verify_signature(request, body):
        return web.Response(status=403)

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for wa_msg in value.get("messages", []):
                incoming = self._to_incoming(wa_msg, value.get("contacts", []))
                await self._dispatch(incoming)

    return web.Response(status=200)  # Must return 200 quickly

def _to_incoming(self, wa_msg: dict, contacts: list[dict]) -> IncomingMessage:
    contact = contacts[0] if contacts else {}
    user = ChatUser(
        platform=Platform.WHATSAPP,
        platform_user_id=wa_msg["from"],             # phone number
        first_name=contact.get("profile", {}).get("name"),
    )

    text = None
    callback_data = None
    command = None

    if wa_msg["type"] == "text":
        text = wa_msg["text"]["body"]
        # Map common first messages to /start
        if text.lower() in ("hi", "hello", "start", "menu"):
            command = "/start"
    elif wa_msg["type"] == "interactive":
        # Button reply or list reply
        interactive = wa_msg["interactive"]
        if interactive["type"] == "button_reply":
            callback_data = interactive["button_reply"]["id"]
        elif interactive["type"] == "list_reply":
            callback_data = interactive["list_reply"]["id"]
    elif wa_msg["type"] == "image":
        # photo_file_id = WhatsApp media ID
        pass

    return IncomingMessage(
        user=user,
        text=text,
        command=command,
        callback_data=callback_data,
        raw=wa_msg,
    )
```

### 3. Outbound message translation

```python
async def send(self, user: ChatUser, message: OutgoingMessage) -> None:
    to = user.platform_user_id  # phone number

    if message.toast:
        # WhatsApp has no toast — skip or send as text
        return

    if message.keyboard and message.keyboard.inline:
        await self._send_interactive(to, message)
    elif message.image_url:
        await self._send_image(to, message)
    else:
        await self._send_text(to, message)

async def _send_interactive(self, to: str, msg: OutgoingMessage):
    buttons = []
    for row in msg.keyboard.buttons:
        for btn in row:
            if len(buttons) < 3:  # WhatsApp max 3 buttons
                buttons.append({
                    "type": "reply",
                    "reply": {
                        "id": btn.callback_data or "",
                        "title": btn.text[:20],  # WhatsApp max 20 chars
                    }
                })

    # If more than 3 options, use list message instead
    if self._total_buttons(msg.keyboard) > 3:
        await self._send_list(to, msg)
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": msg.text or ""},
            "action": {"buttons": buttons},
        }
    }

    if msg.image_url:
        payload["interactive"]["header"] = {
            "type": "image",
            "image": {"link": msg.image_url}
        }

    await self._api_post("/messages", payload)

async def _send_list(self, to: str, msg: OutgoingMessage):
    """Use list message for menus with >3 options."""
    rows = []
    for row in msg.keyboard.buttons:
        for btn in row:
            rows.append({
                "id": btn.callback_data or "",
                "title": btn.text[:24],  # WhatsApp max 24 chars
                "description": "",
            })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": msg.text or "Choose an option"},
            "action": {
                "button": "View options",
                "sections": [{"title": "Menu", "rows": rows[:10]}],  # Max 10 rows
            }
        }
    }
    await self._api_post("/messages", payload)
```

### 4. Handling the 24-hour conversation window

WhatsApp only allows free-form messages within 24 hours of the user's last message. After that, only pre-approved **template messages** can be sent.

```python
# Track last user message timestamp per user
# In orm_query.py:
async def orm_update_last_interaction(session, platform, platform_user_id):
    """Update the timestamp of the user's last inbound message."""
    ...

# In WhatsApp adapter, before sending:
async def send(self, user: ChatUser, message: OutgoingMessage) -> None:
    if await self._outside_conversation_window(user):
        # Fall back to a template message or skip
        await self._send_template(user.platform_user_id, "order_update", ...)
        return
    # Normal send...
```

### 5. No message editing — adaptation strategy

Telegram's menu navigation uses `edit_media` to update a single message in-place. WhatsApp cannot edit messages. Strategy:

| Telegram behavior | WhatsApp adaptation |
|---|---|
| `edit_message_media` (menu navigation) | Send a new message. Optionally delete the old one (if within 1h). |
| `answer_callback_query` (toast) | Send a short text message, or skip. |
| Inline keyboard on existing message | Send new interactive message with buttons. |

```python
# In WhatsApp adapter:
async def send(self, user: ChatUser, message: OutgoingMessage) -> None:
    # Ignore edit_message flag — always send new
    # Optionally track last bot message ID and delete it for cleaner UX
    ...
```

### 6. Formatting translation

```python
def _to_whatsapp_format(self, html_text: str) -> str:
    """Convert bot's HTML formatting to WhatsApp markdown."""
    text = html_text
    text = re.sub(r"<b>(.*?)</b>", r"*\1*", text)
    text = re.sub(r"<i>(.*?)</i>", r"_\1_", text)
    text = re.sub(r"<s>(.*?)</s>", r"~\1~", text)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
    text = re.sub(r"<[^>]+>", "", text)  # strip remaining HTML tags
    return text
```

---

## Environment & Configuration

```env
# .env additions
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxxx
WHATSAPP_VERIFY_TOKEN=my-custom-verify-string
WHATSAPP_APP_SECRET=abcdef1234567890
WEBHOOK_BASE_URL=https://bot.example.com
```

---

## Webhook Setup (Meta Business Suite)

1. Create a Meta App at `developers.facebook.com`
2. Add the WhatsApp product
3. Configure webhook URL: `{WEBHOOK_BASE_URL}/webhook/whatsapp`
4. Subscribe to `messages` webhook field
5. Verify with the `WHATSAPP_VERIFY_TOKEN`
6. Generate a permanent access token (System User token recommended)

---

## Platform-Specific Limitations & Workarounds

| Limitation | Workaround |
|-----------|-----------|
| Max 3 inline buttons | Use list messages for menus with >3 options |
| Button title max 20 chars | Truncate with ellipsis, use shorter labels in `strings.py` |
| No slash commands | Map common greetings ("hi", "menu", "start") to `/start` |
| No message editing | Send new messages; optionally delete previous |
| 24h conversation window | Track timestamps; fall back to templates |
| No typing indicator | Skip `sendChatAction` in adapter |
| Image via URL only (no file_id cache) | Use `image_url` field (HTTPS); WhatsApp caches server-side |
| No HTML formatting | Convert HTML → WhatsApp markdown (`*bold*`, `_italic_`) |

---

## Files to Change

| File | Change |
|------|--------|
| `adapters/whatsapp_adapter.py` | **NEW** — full adapter implementation |
| `core/types.py` | Possibly add WhatsApp-specific fields if needed |
| `database/models.py` | Add `last_interaction` timestamp to User |
| `database/orm_query.py` | Add `orm_update_last_interaction()` |
| `lexicon/strings.py` | Add shorter button label variants (max 20 chars) for WhatsApp |
| `main.py` | Conditionally boot WhatsApp adapter alongside Telegram |
| `requirements.txt` | Add `aiohttp` (for webhook server) |
| `.env.example` | Document WhatsApp environment variables |

---

## Dependencies

```
aiohttp>=3.9.0       # Webhook server + HTTP client for WhatsApp API
```

`aiohttp` is also needed for the LINE adapter, so this is a shared dependency for the webhook infrastructure.

---

## Testing Strategy

| Test | Method |
|------|--------|
| Webhook signature validation | Unit test with known HMAC |
| Inbound message parsing | Unit test with sample webhook payloads from Meta docs |
| Outbound message formatting | Unit test: `OutgoingMessage` → expected API payload |
| Button overflow → list fallback | Unit test: keyboard with >3 buttons produces list message |
| HTML → WhatsApp format conversion | Unit test with all supported tags |
| 24h window enforcement | Unit test with mocked timestamps |
| End-to-end | Manual test with WhatsApp test number (Meta provides one free) |
