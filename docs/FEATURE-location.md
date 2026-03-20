# Feature Card: Location & Delivery Address System

## Problem

The bot has no location handling. Customers cannot share a delivery address when placing an order, and the restaurant's pickup location is only mentioned as plain text in the "about" banner. The `request_location` support in `keyboards/reply.py` is unused, and the `MenuCallBack(menu_name="order")` button in the cart has no handler — so checkout doesn't exist yet.

This feature is a prerequisite for a working order flow.

---

## Goals

1. **Restaurant location** — show the restaurant's address and a Telegram venue/location message so customers know where to pick up.
2. **Customer delivery address** — let customers send their location (GPS pin or Google Maps URL) during checkout, along with optional delivery instructions. Latitude and longitude are **required** — plain text addresses without coordinates are not accepted.
3. **Saved addresses** — persist customer addresses so they can select from a list on future orders instead of re-entering every time.
4. **Admin visibility** — when an order is placed, the admin receives the customer's chosen address and instructions.

---

## Data Model

### New table: `DeliveryAddress`

```python
class DeliveryAddress(Base):
    __tablename__ = "delivery_address"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(100))          # user-given name, e.g. "Home", "Work"
    latitude: Mapped[float] = mapped_column(Float)            # REQUIRED — from GPS pin or Google Maps URL
    longitude: Mapped[float] = mapped_column(Float)           # REQUIRED — from GPS pin or Google Maps URL
    address_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # optional human-readable note
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)  # "ring twice", "gate code 4521"
    is_default: Mapped[bool] = mapped_column(default=False)
```

**Relationships:** `User` 1 → M `DeliveryAddress`

**Notes:**
- `latitude`/`longitude` are **required** — every delivery address must have coordinates. Users provide them via Telegram GPS share or a Google Maps URL.
- `address_text` is optional — a freeform note the user can add, but it is not a substitute for coordinates.
- `label` gives the address a short name for the selection list.
- `is_default` marks which address to pre-select during checkout.
- Addresses are linked to the `User` record via `user_id` (FK → `User.user_id`). The `User` row is auto-created (from Telegram `user_id`, `first_name`, `last_name`) the first time a customer adds a product to their cart. Once the user exists, all saved addresses are associated with that profile automatically — no separate registration step needed.

### New table: `RestaurantLocation`

```python
class RestaurantLocation(Base):
    __tablename__ = "restaurant_location"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))            # branch name, e.g. "Bang Chak Branch"
    address_text: Mapped[str] = mapped_column(Text)           # full street address
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(default=True)     # for soft-disable without deletion
```

**Why a table and not a config constant?** Allows admins to manage multiple branches from the bot in the future, and keeps the address editable without code changes.

### Extend future `Order` table (not yet implemented)

When the order system is built, each order should reference the delivery method and address:

```python
class Order(Base):
    # ... other fields ...
    delivery_method: Mapped[str]          # "delivery" | "pickup" | "dine_in"
    delivery_address_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_address.id"), nullable=True
    )                                      # null for pickup / dine-in
    delivery_instructions: Mapped[str | None]  # snapshot at order time
```

---

## User Flows

### Flow 1: Viewing the restaurant location (pickup info)

```
User taps [Delivery ⛵] or [About ℹ️]
  ↓
Bot shows the existing banner text (delivery options / about info)
  ↓
New button: [📍 Our Location]
  ↓
Bot sends a Telegram venue message:
  bot.send_venue(
      chat_id, latitude, longitude,
      title="Afghan Restaurant Bang Chak",
      address="123 Sukhumvit Rd, Bang Chak, Bangkok"
  )
```

**Why `send_venue` instead of `send_location`?** Venue includes a title and address string, which is more informative than a bare pin.

### Flow 2: Customer adds a delivery address during checkout

```
User taps [Order 📦] in cart
  ↓
Bot: "How would you like to receive your order?"
  [🚚 Delivery]  [🏪 Pickup]  [🍽 Dine-in]
  ↓

── If [Pickup] or [Dine-in]: ──
  Bot sends restaurant venue + confirms order (no address needed)

── If [Delivery]: ──
  ↓
Bot: "Choose a saved address or add a new one:"
  [🏠 Home — 45 Soi 12, Sukhumvit]     ← from DeliveryAddress table
  [🏢 Work — 88 Silom Rd]               ← from DeliveryAddress table
  [➕ New address]
  ↓

── If [➕ New address]: ──
  ↓
Bot: "Share your location using one of these methods:"
  Reply keyboard: [📍 Share Location]    ← uses request_location=True
  "Or paste a Google Maps link."
  ↓

── Option A: User shares GPS location ──
  Bot receives Message.location (lat/lng)
  Bot: "Got your pin. Please type a short label (e.g. Home, Work):"
  User: "Home"
  Bot: "Any delivery instructions? (type or send 'skip')"
  User: "Ring the bell twice, building B"
  → Save to DeliveryAddress(label="Home", lat=..., lng=..., instructions="Ring the bell twice, building B")

── Option B: User sends a Google Maps URL ──
  User: "https://maps.google.com/maps?q=13.7116,100.5948"
  Bot parses and validates URL → extracts lat/lng (see Validation section below)
  Bot: "Got it — location pinned. Please type a short label (e.g. Home, Work):"
  User: "Work"
  Bot: "Any delivery instructions? (type or send 'skip')"
  User: "skip"
  → Save to DeliveryAddress(label="Work", lat=13.7116, lng=100.5948)

── Option C: User sends something else (plain text, invalid URL) ──
  Bot: "Please share a GPS location or paste a valid Google Maps link. Text addresses are not accepted."
  (stays in same state, re-prompts)

  ↓
Bot: "Deliver to 🏠 Home — (13.7116, 100.5948)? [✅ Confirm] [✏️ Change]"
  ↓
[✅ Confirm] → proceed to order confirmation / payment
```

### Flow 3: Managing saved addresses

```
User sends /addresses  (or via a profile menu)
  ↓
Bot: "Your saved addresses:"
  1. 🏠 Home — 45 Soi 12, Sukhumvit  [⭐ Default]
  2. 🏢 Work — 88 Silom Rd
  [➕ Add]  [🗑 Remove]  [⭐ Set Default]
  ↓

[🗑 Remove] → paginated list, user selects → soft confirm → delete
[⭐ Set Default] → paginated list, user selects → mark is_default=True
[➕ Add] → same "new address" sub-flow from Flow 2
```

### Flow 4: Admin sees delivery info on incoming order

```
(When order system is implemented)

Admin receives notification:
  ─────────────────────
  🆕 New Order #47
  👤 John D. (@johndoe)
  📦 Delivery

  📍 45 Soi 12, Sukhumvit Road
  📝 "Ring the bell twice, building B"

  🛒 Items:
    Margherita × 2 — 500฿
    Coke × 1 — 60฿
  💰 Total: 1,060฿
  ─────────────────────
  [✅ Accept] [❌ Decline]
```

---

## FSM States

```python
class OrderCheckout(StatesGroup):
    delivery_method = State()       # waiting for delivery/pickup/dine-in selection
    select_address = State()        # choosing saved address or adding new
    new_address_location = State()  # waiting for GPS pin or Google Maps URL (lat/lng required)
    new_address_label = State()     # waiting for label text
    new_address_instructions = State()  # waiting for delivery instructions
    confirm = State()               # final confirmation before order is placed
```

---

## Google Maps URL Validation

When a user pastes a link instead of sharing a GPS pin, the bot must parse and validate it to extract coordinates. Only recognized Google Maps URL formats are accepted.

### Accepted URL formats

```
# Full URL with query param
https://www.google.com/maps?q=13.7116,100.5948
https://maps.google.com/maps?q=13.7116,100.5948

# Place URL with coordinates in path
https://www.google.com/maps/place/.../@13.7116,100.5948,17z/...

# Short link (requires following the redirect)
https://maps.app.goo.gl/AbCdEf12345

# Search URL with query
https://www.google.com/maps/search/?api=1&query=13.7116,100.5948
```

### Parsing & validation logic (`utils/location.py`)

Validation is a two-phase pipeline:

1. **Local parse** — extract coordinates from the URL structure (fast, no network).
2. **Remote verify** — HTTP HEAD the URL to confirm it's a live, reachable Google Maps page (catches typos, fabricated links, expired short URLs).

Both phases must pass. If either fails, the user is re-prompted.

```python
import re
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass

import aiohttp

# Patterns that match lat,lng in Google Maps URLs
COORD_IN_URL = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
COORD_IN_QUERY = re.compile(r"^(-?\d+\.\d+),(-?\d+\.\d+)$")
GMAPS_DOMAINS = {"google.com", "maps.google.com", "www.google.com", "maps.app.goo.gl", "goo.gl"}
VERIFY_TIMEOUT = aiohttp.ClientTimeout(total=5)


@dataclass
class LocationResult:
    lat: float
    lng: float


@dataclass
class LocationError:
    reason: str   # i18n key for the rejection message


async def validate_google_maps_url(text: str) -> LocationResult | LocationError:
    """
    Full validation pipeline for a Google Maps URL.
    Returns LocationResult on success, LocationError on failure.
    """
    text = text.strip()

    # ── Phase 0: Basic URL check ──
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return LocationError("invalid_location_input")

    domain = parsed.netloc.lower().removeprefix("www.")
    if not any(domain.endswith(d) for d in GMAPS_DOMAINS):
        return LocationError("not_google_maps_url")

    # ── Phase 1: Remote verify + resolve redirects ──
    try:
        async with aiohttp.ClientSession(timeout=VERIFY_TIMEOUT) as session:
            async with session.head(text, allow_redirects=True) as resp:
                if resp.status != 200:
                    return LocationError("url_not_reachable")
                # Use the final URL after redirects (resolves short links)
                final_url = str(resp.url)
    except (aiohttp.ClientError, TimeoutError):
        return LocationError("url_not_reachable")

    # ── Phase 2: Extract coordinates from final URL ──
    coords = _extract_coords(final_url)

    # If redirect changed the URL (short link), also try the original
    if coords is None and final_url != text:
        coords = _extract_coords(text)

    if coords is None:
        return LocationError("coords_not_found_in_url")

    lat, lng = coords
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return LocationError("coords_out_of_range")

    return LocationResult(lat=lat, lng=lng)


def _extract_coords(url: str) -> tuple[float, float] | None:
    """Extract (lat, lng) from a Google Maps URL string. No network calls."""
    parsed = urlparse(url)

    # Try: ?q=lat,lng or &query=lat,lng
    for param in ("q", "query"):
        values = parse_qs(parsed.query).get(param, [])
        for val in values:
            m = COORD_IN_QUERY.match(val.strip())
            if m:
                return (float(m.group(1)), float(m.group(2)))

    # Try: /@lat,lng,zoom in path
    m = COORD_IN_URL.search(parsed.path)
    if m:
        return (float(m.group(1)), float(m.group(2)))

    return None
```

### Validation rules

The handler in `new_address_location` state runs this pipeline and maps each `LocationError.reason` to a user-facing message. On any failure, the bot stays in the same FSM state and re-prompts.

| Phase | Check | `reason` key | User message |
|-------|-------|-------------|--------------|
| 0 | Message is not a location AND not a URL | `invalid_location_input` | "Please share a GPS location or paste a valid Google Maps link." |
| 0 | URL domain is not Google Maps | `not_google_maps_url` | "That doesn't look like a Google Maps link. Please send a google.com/maps URL." |
| 1 | HTTP HEAD returns non-200 or times out | `url_not_reachable` | "That link doesn't appear to be valid — couldn't reach it. Check the URL and try again." |
| 2 | URL is reachable but no lat/lng found in it | `coords_not_found_in_url` | "Couldn't read coordinates from that link. Try right-clicking a spot in Google Maps and copying the coordinates link." |
| 2 | Extracted coordinates outside valid range | `coords_out_of_range` | "Those coordinates don't look right. Please try again." |

### Retry behavior

```
User sends invalid input
  ↓
Bot: "{rejection message}"
     "Share your location or paste a Google Maps link."
  (FSM stays in new_address_location state)
  ↓
User can retry unlimited times, or tap [Cancel] to exit checkout
```

There is no retry limit — the user simply stays in the same state until they provide valid input or cancel. The `[Cancel]` inline button is always visible during the flow.

### Why verify remotely?

Local regex parsing alone cannot catch:
- **Fabricated URLs** — `https://www.google.com/maps?q=99.999,99.999` parses fine locally but isn't a real place link
- **Expired or broken short links** — `maps.app.goo.gl/XXXXX` where the short code no longer resolves
- **Typos in the URL** — `https://www.google.com/mapss/place/...` (extra 's') passes domain check but 404s
- **Copy-paste truncation** — user accidentally pastes a partial URL that still looks structurally valid

The HEAD request with a 5-second timeout adds minimal latency while catching all of these. It also resolves short links to their full URL in the same call, eliminating the need for a separate redirect-follow step.

---

## ORM Operations (new functions in `orm_query.py`)

```python
# --- Delivery Address ---
orm_add_delivery_address(session, user_id, label, address_text, lat, lng, instructions)
orm_get_user_addresses(session, user_id) -> list[DeliveryAddress]
orm_get_delivery_address(session, address_id) -> DeliveryAddress | None
orm_delete_delivery_address(session, address_id)
orm_set_default_address(session, user_id, address_id)

# --- Restaurant Location ---
orm_get_restaurant_locations(session) -> list[RestaurantLocation]
orm_add_restaurant_location(session, name, address_text, lat, lng)   # admin
orm_update_restaurant_location(session, location_id, data: dict)     # admin
orm_delete_restaurant_location(session, location_id)                 # admin
```

---

## Keyboard Changes

### `keyboards/inline.py`

New callback data for checkout flow:

```python
class OrderCallBack(CallbackData, prefix="order"):
    action: str                          # "method", "select_addr", "new_addr", "confirm", "cancel"
    delivery_method: str | None = None   # "delivery", "pickup", "dine_in"
    address_id: int | None = None

class AddressCallBack(CallbackData, prefix="addr"):
    action: str                          # "list", "add", "delete", "set_default"
    address_id: int | None = None
```

### `keyboards/reply.py`

The existing `request_location` parameter is finally used:

```python
get_keyboard(
    "📍 Share Location",
    placeholder="Share location or paste a Google Maps link",
    request_location=0,  # first button triggers location share
    sizes=(1,),
)
```

---

## i18n Keys (add to `lexicon/strings.py`)

```python
# Delivery method selection
"choose_delivery_method"
"delivery_option"
"pickup_option"
"dine_in_option"

# Address management
"choose_address"
"add_new_address"
"send_location_prompt"            # "Share location or paste a Google Maps link"
"enter_address_label"
"enter_delivery_instructions"
"skip"
"address_saved"
"address_deleted"
"default_address_set"
"your_addresses"
"no_saved_addresses"

# Location validation errors
"invalid_location_input"          # "Please share a GPS location or paste a valid Google Maps link."
"not_google_maps_url"             # "That doesn't look like a Google Maps link."
"url_not_reachable"               # "That link doesn't appear to be valid — couldn't reach it."
"coords_not_found_in_url"         # "Couldn't read coordinates from that link."
"coords_out_of_range"             # "Those coordinates don't look right."

# Confirmation
"confirm_delivery_to"
"confirm_order"
"change_address"

# Restaurant location
"our_location"
"restaurant_venue_title"
```

---

## Handler Changes

| File | Change |
|------|--------|
| `handlers/user_private.py` | Add `OrderCheckout` FSM handlers: delivery method, address input (GPS pin or Google Maps URL), label, instructions, confirmation. Add `/addresses` command. |
| `handlers/menu_processing.py` | Wire up `menu_name="order"` at level 0 to start the checkout FSM. Add [📍 Our Location] button to the shipping/about banner response. |
| `handlers/admin_private.py` | Add restaurant location CRUD under `/admin` menu (new FSM `AddRestaurantLocation`). |
| `keyboards/inline.py` | Add `OrderCallBack`, `AddressCallBack` data classes and builder functions. |
| `keyboards/reply.py` | No changes needed — already supports `request_location`. |
| `database/models.py` | Add `DeliveryAddress` and `RestaurantLocation` models. |
| `database/orm_query.py` | Add address and restaurant location CRUD functions. |
| `utils/location.py` | **New file.** `parse_google_maps_url()` and `_validate_coords()` for extracting lat/lng from Google Maps URLs. |
| `common/texts_for_db.py` | Add seed data for default restaurant location. |
| `lexicon/strings.py` | Add all new i18n keys listed above. |

---

## Migration Notes

- Two new tables (`delivery_address`, `restaurant_location`) — no existing tables are altered.
- The `User` model is not changed; addresses are a separate related table.
- Since the dev environment drops and recreates the DB on startup (`on_startup` calls `drop_db()`), no Alembic migration is needed during development. For production, generate an Alembic migration before deploying.
- Seed a default restaurant location in `create_db()` alongside the existing category/banner seeding.

---

## Dependencies

- **Blocked by:** Nothing — can be built independently.
- **Blocks:** Order system (needs address selection during checkout), payment integration (needs order total + delivery info).
- **Related:** Localization feature (new strings need translations in all 6 languages).

---

## Scope Boundaries (what this feature does NOT do)

- **No geocoding / reverse geocoding** — we store raw coordinates but do not resolve them to a street address via a geocoding API. That can be added later to auto-fill `address_text`.
- **No delivery fee calculation** — fees based on distance are a separate feature.
- **No delivery radius validation** — we accept any location; radius restrictions can be layered on later.
- **No real-time delivery tracking** — out of scope.
- **No order persistence** — this card defines the address system and checkout flow, but the `Order` model itself should be designed in a separate feature card to keep scope focused.
