# Feature Card: LINE Platform Adapter

## Problem

LINE dominates messaging in Thailand (~53 million monthly active users), Japan, and Taiwan. Since this bot already supports Thai language and serves an Afghan restaurant in Bangkok (Bang Chak), LINE is the single most impactful platform to add — most local customers use LINE, not Telegram.

---

## Goal

Add a LINE adapter so the existing bot experience (menu browsing, cart, ordering) works over LINE with zero changes to business logic. The adapter translates between our `core/types.py` abstractions and the LINE Messaging API.

---

## LINE Messaging API Overview

| Aspect | Detail |
|--------|--------|
| **API** | LINE Messaging API (v2) |
| **Auth** | Channel access token (long-lived or stateless) |
| **Inbound** | Webhook POST (message, postback, follow, unfollow events) |
| **Outbound** | REST API — `POST https://api.line.me/v2/bot/message/{reply,push}` |
| **Message types** | Text, image, video, audio, location, sticker, imagemap, template, **Flex Message** |
| **Pricing** | Free tier: 500 messages/month. Light: ~1,600/month. Standard: ~4,500/month. (Thailand pricing) |
| **Rate limits** | 100,000 requests/min for push, no limit on reply |

### Key Differences from Telegram

| Feature | Telegram | LINE |
|---------|----------|------|
| User identity | Integer `user_id` | String UID (`U` + 32 hex chars, e.g. `Uab12cd34...`) |
| Bot initiation | User sends `/start` | User taps "Add Friend" → `follow` event |
| Inline buttons | `InlineKeyboardButton` (callback_data) | **Postback action** (data field, max 300 chars) |
| Reply vs push | All messages are push | **Reply** (free, must use `replyToken` within 1 min) vs **Push** (costs quota) |
| Edit messages | `edit_message_text/media` | Not supported |
| Rich menus | No equivalent | **Rich Menu** — persistent bottom-of-screen tap grid (image-based) |
| Rich cards | No native | **Flex Message** — fully customizable card/carousel layout (JSON) |
| Image sending | `file_id` or upload | HTTPS URL (must be on public server, JPEG/PNG) |
| Commands | `/command` | No slash commands; users tap buttons or type free text |
| Stickers | Supported | First-class feature, LINE Sticker Store integration |
| Group behavior | Bot sees all messages | Bot only sees messages when @mentioned or in 1-on-1 |

---

## Proposed Design

### 1. Webhook server

LINE delivers events via webhook, same as WhatsApp. Share the `aiohttp` server.

```python
# adapters/line_adapter.py

from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncMessagingApi, Configuration, ReplyMessageRequest,
    PushMessageRequest, TextMessage, FlexMessage, ImageMessage,
)

class LineAdapter(PlatformAdapter):
    def __init__(self, channel_access_token: str, channel_secret: str):
        self.channel_secret = channel_secret
        config = Configuration(access_token=channel_access_token)
        self.api = AsyncMessagingApi(config)
        self.parser = WebhookParser(channel_secret)

    async def start(self):
        """Register webhook route on shared aiohttp app."""
        # Route: POST /webhook/line
        ...
```

### 2. Inbound event translation

LINE has multiple event types. The most relevant:

| LINE Event | Maps to |
|-----------|---------|
| `MessageEvent` (text) | `IncomingMessage(text=...)` |
| `MessageEvent` (image) | `IncomingMessage(photo_file_id=...)` |
| `PostbackEvent` | `IncomingMessage(callback_data=...)` |
| `FollowEvent` | `IncomingMessage(command="/start")` |
| `UnfollowEvent` | User blocked the bot — deactivate |

```python
async def _handle(self, request: web.Request) -> web.Response:
    body = await request.text()
    signature = request.headers.get("X-Line-Signature", "")

    try:
        events = self.parser.parse(body, signature)
    except InvalidSignatureError:
        return web.Response(status=403)

    for event in events:
        incoming = self._to_incoming(event)
        if incoming:
            # Reply token is only valid for 1 minute — must reply quickly
            await self._dispatch(incoming, reply_token=event.reply_token)

    return web.Response(status=200)

def _to_incoming(self, event) -> IncomingMessage | None:
    user = ChatUser(
        platform=Platform.LINE,
        platform_user_id=event.source.user_id,
    )

    if isinstance(event, FollowEvent):
        return IncomingMessage(user=user, command="/start", raw=event)

    if isinstance(event, MessageEvent):
        msg = event.message
        if isinstance(msg, TextMessageContent):
            text = msg.text
            # Map common inputs to commands
            command = None
            if text.lower() in ("เมนู", "menu", "start"):
                command = "/start"
            return IncomingMessage(user=user, text=text, command=command, raw=event)
        if isinstance(msg, ImageMessageContent):
            return IncomingMessage(user=user, photo_file_id=msg.id, raw=event)

    if isinstance(event, PostbackEvent):
        return IncomingMessage(user=user, callback_data=event.postback.data, raw=event)

    return None
```

### 3. Outbound message translation

LINE offers two sending modes:

- **Reply** — free, uses `reply_token` (valid 1 minute from event). Up to 5 messages per reply.
- **Push** — costs monthly quota, uses `user_id`. No token needed.

Strategy: always try reply first, fall back to push for async messages (e.g., order updates).

```python
async def send(self, user: ChatUser, message: OutgoingMessage,
               reply_token: str | None = None) -> None:
    line_messages = self._build_messages(message)

    if reply_token:
        await self.api.reply_message(ReplyMessageRequest(
            reply_token=reply_token,
            messages=line_messages,
        ))
    else:
        await self.api.push_message(PushMessageRequest(
            to=user.platform_user_id,
            messages=line_messages,
        ))
```

### 4. Flex Messages for rich product cards

LINE's killer feature is **Flex Messages** — fully customizable JSON-based card layouts. These are far richer than Telegram's `edit_media` approach. Use Flex for product display:

```python
def _build_product_flex(self, msg: OutgoingMessage) -> FlexMessage:
    """Convert OutgoingMessage with image + text + keyboard into a Flex card."""
    bubble = {
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": msg.image_url,
            "size": "full",
            "aspectRatio": "4:3",
            "aspectMode": "cover",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": msg.text or "", "wrap": True, "size": "md"},
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": self._buttons_to_flex_actions(msg.keyboard),
            "spacing": "sm",
        }
    }
    return FlexMessage(alt_text=msg.text or "Menu", contents=bubble)

def _buttons_to_flex_actions(self, keyboard: Keyboard | None) -> list[dict]:
    if not keyboard:
        return []
    actions = []
    for row in keyboard.buttons:
        for btn in row:
            if btn.url:
                actions.append({
                    "type": "button",
                    "action": {"type": "uri", "label": btn.text[:20], "uri": btn.url},
                    "style": "link",
                })
            elif btn.callback_data:
                actions.append({
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": btn.text[:20],
                        "data": btn.callback_data,  # max 300 chars
                        "displayText": btn.text,
                    },
                    "style": "primary",
                })
    return actions
```

### 5. Product carousel (multi-product browsing)

Instead of Telegram's one-product-at-a-time pagination, LINE can show a **carousel** of up to 12 Flex bubbles:

```python
def _build_carousel(self, products: list[OutgoingMessage]) -> FlexMessage:
    bubbles = [self._build_product_bubble(p) for p in products[:12]]
    return FlexMessage(
        alt_text="Product catalog",
        contents={"type": "carousel", "contents": bubbles},
    )
```

This is a significant UX improvement over Telegram — users see multiple products at once and swipe horizontally.

### 6. Rich Menu (persistent bottom menu)

LINE supports a **Rich Menu** — a persistent image-based tap grid at the bottom of the chat. This replaces Telegram's reply keyboard and slash commands.

```
┌─────────────┬─────────────┬─────────────┐
│   🍕 Menu   │  🛒 Cart    │  ℹ️ About   │
├─────────────┼─────────────┼─────────────┤
│  💰 Payment │  🚚 Delivery│  🌐 Language│
└─────────────┴─────────────┴─────────────┘
```

Set up via the LINE Messaging API at bot startup:

```python
async def _setup_rich_menu(self):
    """Create and set the default rich menu."""
    rich_menu = RichMenuRequest(
        size=RichMenuSize(width=2500, height=843),
        selected=True,
        name="Main Menu",
        chat_bar_text="Menu",
        areas=[
            RichMenuArea(
                bounds=RichMenuBounds(x=0, y=0, width=833, height=421),
                action=PostbackAction(data="menu:0:main:0:0", label="Menu"),
            ),
            RichMenuArea(
                bounds=RichMenuBounds(x=833, y=0, width=833, height=421),
                action=PostbackAction(data="menu:3:cart:0:0", label="Cart"),
            ),
            # ... 4 more areas
        ]
    )
    rich_menu_id = await self.api.create_rich_menu(rich_menu)
    # Upload rich menu image (pre-designed 2500x843 PNG)
    await self.api.set_rich_menu_image(rich_menu_id, ...)
    await self.api.set_default_rich_menu(rich_menu_id)
```

### 7. Reply token management

LINE reply tokens expire after 1 minute. The adapter must respond within that window:

```python
class LineAdapter(PlatformAdapter):
    def __init__(self, ...):
        ...
        self._pending_reply_tokens: dict[str, str] = {}  # user_id → reply_token

    async def _handle(self, request):
        ...
        for event in events:
            user_id = event.source.user_id
            self._pending_reply_tokens[user_id] = event.reply_token
            incoming = self._to_incoming(event)
            await self._dispatch(incoming)
            self._pending_reply_tokens.pop(user_id, None)

    async def send(self, user, message):
        reply_token = self._pending_reply_tokens.get(user.platform_user_id)
        ...
```

---

## Environment & Configuration

```env
# .env additions
LINE_CHANNEL_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxx
LINE_CHANNEL_SECRET=abcdef1234567890
WEBHOOK_BASE_URL=https://bot.example.com
```

---

## LINE Developer Console Setup

1. Create a **Messaging API channel** at `developers.line.biz`
2. Issue a long-lived channel access token
3. Set webhook URL: `{WEBHOOK_BASE_URL}/webhook/line`
4. Enable "Use webhook"
5. Disable "Auto-reply messages" and "Greeting messages" (bot handles these)
6. Add the bot as a friend using the QR code or LINE ID

---

## Platform-Specific Limitations & Workarounds

| Limitation | Workaround |
|-----------|-----------|
| No message editing | Send new messages (Flex cards replace previous context visually) |
| Reply token expires in 1 minute | Process events fast; fall back to push if token expired |
| Push messages cost quota | Prefer reply over push; batch notifications |
| Image URL must be HTTPS, public | Host images on server or use CDN/S3 |
| Button label max 20 chars | Truncate; use shorter i18n variants in `strings.py` |
| No slash commands | Map Thai/English keywords + Rich Menu taps to commands |
| Max 5 messages per reply | Combine content into Flex cards to stay under limit |
| Flex Message JSON complexity | Build helper functions that abstract the JSON structure |
| No callback answer/toast | Include confirmation in the next message body |

---

## UX Improvements Over Telegram (LINE-specific)

| Feature | Telegram UX | LINE UX |
|---------|-------------|---------|
| Product browsing | One product at a time, ◀ ▶ buttons | Flex carousel — swipe through multiple |
| Main navigation | Inline buttons on message | **Rich Menu** — persistent, always visible |
| Product card | Photo + plain text caption | Flex bubble — styled card with image, title, price, buttons |
| Cart summary | One item at a time, paginated | Flex bubble with all items listed |

---

## Files to Change

| File | Change |
|------|--------|
| `adapters/line_adapter.py` | **NEW** — full adapter implementation |
| `adapters/line_flex.py` | **NEW** — Flex Message builder helpers |
| `assets/rich_menu.png` | **NEW** — Rich Menu background image (2500×843) |
| `core/types.py` | Possibly add `carousel` field to `OutgoingMessage` for multi-card responses |
| `lexicon/strings.py` | Add shorter button labels (max 20 chars) for LINE |
| `main.py` | Conditionally boot LINE adapter alongside Telegram |
| `requirements.txt` | Add `line-bot-sdk>=3.0` |
| `.env.example` | Document LINE environment variables |

---

## Dependencies

```
line-bot-sdk>=3.0.0   # Official LINE SDK (async support in v3)
aiohttp>=3.9.0        # Shared webhook server (also used by WhatsApp adapter)
```

---

## Testing Strategy

| Test | Method |
|------|--------|
| Webhook signature validation | Unit test with known HMAC-SHA256 |
| Inbound event parsing (message, postback, follow) | Unit test with sample payloads from LINE docs |
| Flex Message generation | Unit test: `OutgoingMessage` → expected Flex JSON |
| Carousel building | Unit test: list of products → carousel with correct bubble count |
| Button label truncation | Unit test: labels >20 chars are truncated correctly |
| Reply vs push selection | Unit test: reply_token present → reply; absent → push |
| Rich Menu setup | Integration test against LINE sandbox |
| End-to-end | Manual test with LINE Official Account (free tier) |
