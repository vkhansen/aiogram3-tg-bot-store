# Feature Card: Multi-Platform Core Abstraction

## Problem

Every handler, keyboard builder, and menu processor is hard-wired to aiogram types (`Message`, `CallbackQuery`, `InlineKeyboardMarkup`, `InputMediaPhoto`). The bot logic (menu navigation, cart management, admin panel, localization) is solid — but it can only speak Telegram. To serve WhatsApp and LINE users we'd have to duplicate all that logic three times, then keep three copies in sync forever.

The coupling points are:

| Layer | Telegram-specific dependency |
|-------|------------------------------|
| **Handlers** | `aiogram.types.Message`, `CallbackQuery`, `Bot.send_photo` |
| **Keyboards** | `InlineKeyboardMarkup`, `InlineKeyboardButton`, `ReplyKeyboardMarkup` |
| **Media** | `InputMediaPhoto`, `FSInputFile`, Telegram `file_id` for images |
| **Callbacks** | `CallbackData` (aiogram's callback factory, 64-byte limit) |
| **Middleware** | `BaseMiddleware` tied to aiogram's dispatcher lifecycle |
| **Filters** | `ChatTypeFilter`, `IsAdmin` — check `message.chat.type`, `bot.my_admins_list` |
| **User identity** | `user_id` is a Telegram `BigInteger`; no platform qualifier |

---

## Goal

Introduce a **platform adapter layer** so that:

1. Business logic (menu, cart, admin, localization) is written once against **platform-neutral types**.
2. Each messaging platform (Telegram, WhatsApp, LINE) has a thin **adapter** that translates between the neutral types and the platform SDK.
3. Adding a fourth platform (e.g. Facebook Messenger, Discord) means writing one new adapter — zero changes to business logic.
4. The Telegram bot keeps working exactly as it does today throughout the migration.

---

## Approach Options

### Option A: Full abstraction — neutral message types + adapter per platform

Define our own `ChatMessage`, `ChatUser`, `ChatKeyboard`, etc. Each platform adapter converts SDK events into these types on the way in, and converts outbound neutral types back into SDK calls on the way out.

```
[Telegram SDK]  ──adapt──▸ ChatMessage ──▸ BusinessLogic ──▸ ChatReply ──adapt──▸ [Telegram SDK]
[WhatsApp API]  ──adapt──▸ ChatMessage ──▸ BusinessLogic ──▸ ChatReply ──adapt──▸ [WhatsApp API]
[LINE SDK]      ──adapt──▸ ChatMessage ──▸ BusinessLogic ──▸ ChatReply ──adapt──▸ [LINE SDK]
```

**Pros:** Clean separation. Business logic is 100% platform-agnostic. Testable without any SDK.
**Cons:** Largest upfront investment. Must model the union of all platform capabilities.

### Option B: Thin wrapper — keep aiogram internally, translate at the edges

Keep aiogram as the internal message bus. WhatsApp/LINE webhooks convert inbound events into synthetic aiogram `Update` objects, and a post-processor intercepts outbound Telegram API calls to redirect them to the correct platform.

**Pros:** Minimal changes to existing code. Leverages aiogram's router/FSM/middleware.
**Cons:** Leaky abstraction. WhatsApp and LINE capabilities that don't map to Telegram (e.g. LINE Flex Messages, WhatsApp list messages) are hard to express. Debugging synthetic aiogram objects is confusing.

### Option C: Shared service layer — handlers stay platform-specific, share ORM + business functions

Keep `handlers/` Telegram-specific. Add `handlers_whatsapp/` and `handlers_line/` directories. All three call the same ORM functions and a new `services/` layer for business logic (cart operations, menu rendering data, etc.).

**Pros:** Simplest to start. No abstraction layer needed. Each platform can use its richest features.
**Cons:** UI logic (message formatting, keyboard building) is duplicated 3x. Drift is inevitable.

---

## Recommendation: Option A (full abstraction) with incremental migration

Option A is the only approach that scales to 3+ platforms without duplicating UI logic. The cost is manageable because the existing codebase is small (~10 handler functions, ~6 keyboard builders, 1 menu processor).

**Migration strategy:** build the abstraction alongside aiogram first (Telegram-only), verify nothing breaks, then add WhatsApp and LINE adapters one at a time.

---

## Proposed Design

### 1. Platform-neutral message types

```python
# core/types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class Platform(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    LINE = "line"

@dataclass
class ChatUser:
    """Platform-agnostic user identity."""
    platform: Platform
    platform_user_id: str          # Telegram int → str, WhatsApp phone, LINE uid
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    lang: str = "en"

    @property
    def unified_id(self) -> str:
        """Globally unique: 'telegram:123456' / 'whatsapp:+66812345678'."""
        return f"{self.platform.value}:{self.platform_user_id}"

@dataclass
class IncomingMessage:
    """Normalized inbound event from any platform."""
    user: ChatUser
    text: str | None = None
    command: str | None = None        # e.g. "/start", "/admin"
    callback_data: str | None = None  # button press payload
    photo_file_id: str | None = None  # platform-native file ref
    raw: Any = None                   # original SDK object for escape hatch

@dataclass
class Button:
    text: str
    callback_data: str | None = None
    url: str | None = None

@dataclass
class Keyboard:
    """Platform-neutral button grid."""
    buttons: list[list[Button]]       # rows of buttons
    inline: bool = True               # inline vs reply keyboard

@dataclass
class OutgoingMessage:
    """What business logic wants to send back."""
    text: str | None = None
    image_url: str | None = None      # HTTPS URL (works on all platforms)
    image_file_id: str | None = None  # platform-specific cached ref
    keyboard: Keyboard | None = None
    edit_message: bool = False        # True → edit previous, False → send new
    toast: str | None = None          # short popup (Telegram: answer_callback_query)
```

### 2. Platform adapter interface

```python
# core/adapter.py

from abc import ABC, abstractmethod
from core.types import IncomingMessage, OutgoingMessage, ChatUser

class PlatformAdapter(ABC):
    """Contract every platform must fulfill."""

    @abstractmethod
    async def send(self, user: ChatUser, message: OutgoingMessage) -> None:
        """Deliver an outgoing message to the user on this platform."""

    @abstractmethod
    async def get_user_profile(self, platform_user_id: str) -> ChatUser:
        """Fetch user profile from the platform API."""

    @abstractmethod
    async def download_file(self, file_id: str) -> bytes:
        """Download media by platform file reference."""

    @abstractmethod
    async def start(self) -> None:
        """Start listening for events (polling or webhook)."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down."""
```

### 3. Router — dispatches normalized events to handlers

```python
# core/router.py

from core.types import IncomingMessage, OutgoingMessage

HandlerFunc = Callable[[IncomingMessage, AsyncSession, PlatformAdapter], Awaitable[OutgoingMessage | None]]

class Router:
    def __init__(self):
        self._command_handlers: dict[str, HandlerFunc] = {}
        self._callback_handlers: dict[str, HandlerFunc] = {}
        self._fallback: HandlerFunc | None = None

    def command(self, cmd: str):
        """Decorator: register a /command handler."""
        def decorator(func: HandlerFunc):
            self._command_handlers[cmd] = func
            return func
        return decorator

    def callback(self, prefix: str):
        """Decorator: register a callback-data handler."""
        def decorator(func: HandlerFunc):
            self._callback_handlers[prefix] = func
            return func
        return decorator

    async def dispatch(self, msg: IncomingMessage, session, adapter):
        if msg.command and msg.command in self._command_handlers:
            return await self._command_handlers[msg.command](msg, session, adapter)
        if msg.callback_data:
            prefix = msg.callback_data.split(":")[0]
            if prefix in self._callback_handlers:
                return await self._callback_handlers[prefix](msg, session, adapter)
        if self._fallback:
            return await self._fallback(msg, session, adapter)
```

### 4. User identity — multi-platform support in DB

```python
# database/models.py  (changes)

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(10))             # "telegram", "whatsapp", "line"
    platform_user_id: Mapped[str] = mapped_column(String(64))     # was BigInteger user_id
    first_name: Mapped[str | None] = mapped_column(String(150))
    last_name: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(13))
    lang: Mapped[str] = mapped_column(String(5), default="en")

    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_platform_user"),
    )
```

### 5. Image storage — platform-neutral

Currently images are stored as Telegram `file_id` strings. This won't work cross-platform.

**Strategy:** store images in local filesystem (or S3/object storage) and keep an HTTPS URL as the canonical reference. Each adapter can also cache a platform-specific file ID for performance.

```python
class ProductImage(Base):
    __tablename__ = "product_image"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(500))               # canonical HTTPS URL
    telegram_file_id: Mapped[str | None] = mapped_column(String(150))
    line_file_id: Mapped[str | None] = mapped_column(String(150))
    # WhatsApp uses URLs directly — no cache needed
```

### 6. Keyboard translation per platform

Each platform has different button capabilities:

| Feature | Telegram | WhatsApp | LINE |
|---------|----------|----------|------|
| Inline buttons with callback | Yes (64 bytes) | Yes (via interactive messages, 256 chars) | Yes (postback, 300 chars) |
| URL buttons | Yes | Yes (via CTA) | Yes (URI action) |
| Button grids | Up to 8 per row | Up to 3 per row, max 10 | Up to 3 per row in Flex |
| Reply keyboard | Yes | Yes (quick replies, max 13) | Yes (quick reply, max 13) |
| Rich cards / carousels | No native (use edit_media) | No | Yes (Flex Message carousel) |

The `PlatformAdapter.send()` implementation handles mapping `Keyboard` → platform-native format, respecting per-platform limits (truncating rows, splitting messages if needed).

### 7. Directory structure

```
telegrambot/
├── core/                           # NEW — platform-neutral layer
│   ├── __init__.py
│   ├── types.py                    # ChatUser, IncomingMessage, OutgoingMessage, Keyboard
│   ├── adapter.py                  # PlatformAdapter ABC
│   ├── router.py                   # Command/callback dispatcher
│   └── services/                   # Business logic (extracted from handlers)
│       ├── menu_service.py         # Menu/catalog operations
│       ├── cart_service.py         # Cart operations
│       ├── user_service.py         # User registration, lang prefs
│       └── admin_service.py        # Admin product CRUD
│
├── adapters/                       # NEW — one module per platform
│   ├── __init__.py
│   ├── telegram_adapter.py         # aiogram ↔ core types
│   ├── whatsapp_adapter.py         # WhatsApp Business API ↔ core types
│   └── line_adapter.py             # LINE Messaging API ↔ core types
│
├── handlers/                       # REFACTORED — now platform-neutral
│   ├── user_handlers.py            # /start, menu nav, cart (uses core types)
│   ├── admin_handlers.py           # Admin panel (uses core types)
│   └── menu_processing.py          # Menu content builder (returns OutgoingMessage)
│
├── database/                       # UPDATED — multi-platform user model
├── keyboards/                      # DEPRECATED → replaced by core/types.Keyboard
├── middlewares/                     # UPDATED → adapter-level middleware
├── lexicon/                        # UNCHANGED
├── filters/                        # DEPRECATED → logic moves to router/adapter
└── main.py                         # UPDATED → boots all enabled adapters
```

---

## Migration Plan

### Phase 1: Extract business logic (no platform changes)

Move business logic out of aiogram handlers into `core/services/`. Handlers become thin wrappers that call services and format responses. **Telegram keeps working identically.**

| Step | Action | Risk |
|------|--------|------|
| 1a | Create `core/types.py` with neutral types | None — new file |
| 1b | Create `core/services/` extracting logic from handlers | Low — refactor |
| 1c | Create `adapters/telegram_adapter.py` wrapping aiogram | Low — translation layer |
| 1d | Rewrite handlers to use neutral types, delegating to Telegram adapter | Medium — must not break existing flow |
| 1e | Run all existing tests, manual QA on Telegram | Verification |

### Phase 2: Multi-platform user model

| Step | Action | Risk |
|------|--------|------|
| 2a | Add `platform` + `platform_user_id` columns to User | Medium — migration |
| 2b | Migrate existing `user_id` (BigInteger) → `platform_user_id` (String) | Medium — data migration |
| 2c | Update ORM queries to filter by `(platform, platform_user_id)` | Low |
| 2d | Add `ProductImage` table, migrate away from bare `file_id` | Medium |

### Phase 3: Add WhatsApp adapter

See **FEATURE-platform-whatsapp.md**.

### Phase 4: Add LINE adapter

See **FEATURE-platform-line.md**.

---

## Files to Change

| File | Change |
|------|--------|
| `core/types.py` | **NEW** — Platform, ChatUser, IncomingMessage, OutgoingMessage, Button, Keyboard |
| `core/adapter.py` | **NEW** — PlatformAdapter ABC |
| `core/router.py` | **NEW** — neutral command/callback dispatcher |
| `core/services/menu_service.py` | **NEW** — extracted from `menu_processing.py` |
| `core/services/cart_service.py` | **NEW** — extracted from `user_private.py` cart logic |
| `core/services/user_service.py` | **NEW** — extracted from `user_private.py` user logic |
| `core/services/admin_service.py` | **NEW** — extracted from `admin_private.py` |
| `adapters/telegram_adapter.py` | **NEW** — aiogram ↔ core translation |
| `adapters/whatsapp_adapter.py` | **NEW** — WhatsApp Business API adapter |
| `adapters/line_adapter.py` | **NEW** — LINE Messaging API adapter |
| `database/models.py` | Add `platform` column, change `user_id` → `platform_user_id`, add `ProductImage` |
| `database/orm_query.py` | Update all user queries for multi-platform identity |
| `handlers/user_private.py` | Refactor to use core types + services |
| `handlers/admin_private.py` | Refactor to use core types + services |
| `handlers/menu_processing.py` | Refactor to return `OutgoingMessage` |
| `main.py` | Boot all enabled adapters |

---

## Key Design Decisions

1. **String `platform_user_id` not integer** — WhatsApp uses phone numbers, LINE uses 33-char UIDs. Strings accommodate all.
2. **HTTPS URLs as canonical image storage** — every platform can fetch an HTTPS URL. Platform-specific file IDs are optional caches.
3. **Escape hatch via `raw` field** — `IncomingMessage.raw` holds the original SDK object so platform-specific features are still accessible when needed.
4. **Gradual migration** — the Telegram adapter wraps existing aiogram code, so the bot works throughout the transition.
