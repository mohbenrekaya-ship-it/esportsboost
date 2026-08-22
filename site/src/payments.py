# -*- coding: utf-8 -*-
"""Stripe payment logic, shared by the local server and the Vercel functions.

Both `site/serve.py` (long-running preview/dev server) and the serverless
functions in `/api/*.py` are thin HTTP shells around the three `process_*`
handlers below — so the checkout, receipt-lookup and webhook logic lives in
exactly one place, and stays true to the project's rule of no third-party
packages: it talks to Stripe's REST API directly over urllib and verifies
webhook signatures with the stdlib hmac/hashlib.

Configuration is env-only, never committed:

    STRIPE_SECRET_KEY     required to take payment (use sk_test_… in dev)
    STRIPE_WEBHOOK_SECRET optional, enables /api/webhook signature checks
    PUBLIC_BASE_URL       optional success/cancel origin, else inferred
    ORDER_LOG             optional path for the fulfilment log (see note)

With no key set, `process_checkout`/`process_session` return a 503 so the
checkout page falls back to its local preview confirmation.

Note on persistence: the webhook appends fulfilled orders to ORDER_LOG. On a
serverless host (Vercel) the filesystem is read-only apart from /tmp, so that
write is best-effort — the durable signal there is the stderr log line, which
shows up in the function logs. A real deployment would swap this seam for a
database or a queue.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html import escape as _esc   # the confirmation mail's HTML part

import data as D  # noqa: E402  — the roster a named booster is resolved against
import pricing  # noqa: E402  — authoritative price, never trust the client

STRIPE_API = "https://api.stripe.com/v1"
MAX_BODY = 64 * 1024  # a checkout payload is tiny; cap it hard


def stripe_key():
    return os.environ.get("STRIPE_SECRET_KEY", "").strip()


def webhook_secret():
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()


def order_log_path():
    return os.environ.get("ORDER_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "orders.log")


class StripeError(Exception):
    pass


def stripe_call(path, params=None, method="POST", idempotency_key=None):
    """One authenticated call to Stripe's REST API. Returns parsed JSON.
    Raises StripeError with the message Stripe gave us on a 4xx/5xx.

    `idempotency_key` is passed through on writes: a double-clicked Pay button
    or a retried POST then resolves to the SAME Checkout Session instead of
    creating a second one for the same order."""
    url = STRIPE_API + path
    data = urllib.parse.urlencode(params or {}, doseq=True).encode() if params else None
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    auth = base64.b64encode((stripe_key() + ":").encode()).decode()
    req.add_header("Authorization", "Basic " + auth)
    if idempotency_key:
        req.add_header("Idempotency-Key", idempotency_key)
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode()).get("error", {})
            msg = err.get("message") or e.reason
        except Exception:
            msg = str(e.reason)
        raise StripeError(msg)


def new_order_id():
    return "ESB-" + base64.b32encode(os.urandom(4)).decode().rstrip("=")[:6]


def build_session(order, base_url):
    """Turn a validated order into Stripe Checkout Session params. The amount
    comes from pricing.quote() — the client-supplied total is ignored."""
    q = pricing.quote(order)
    if q["invalid"]:
        raise StripeError(q["summary"])

    # Charge exactly what the checkout page showed the customer. The browser
    # sends the total it displayed (`client_total`, in whole USD before currency
    # conversion); we recompute the price authoritatively above and REFUSE the
    # charge if the two disagree — so Stripe can never show an amount the buyer
    # didn't see, and a tampered client figure can't move the price either. The
    # amount charged is always the server's `q["total"]`; the client number is
    # only ever compared, never trusted as the price.
    shown = order.get("client_total")
    if isinstance(shown, (int, float)) and not isinstance(shown, bool):
        if int(shown) != q["total"]:
            sys.stderr.write(
                "[checkout] price mismatch: shown=%s server=%s order=%s\n"
                % (int(shown), q["total"], q["summary"]))
            raise StripeError(
                "The price updated since you configured this order. "
                "Please refresh the page and try again.")

    game = order.get("game", "")
    region = order.get("region", "")
    service = order.get("service", "") or "division"
    # A booster the customer named on the roster or a profile page. Resolved
    # against the real roster, never taken as written — the browser POSTs it,
    # and an unrecognised handle must not reach fulfilment as an assignment.
    # It carries no charge: there is no named-booster fee in quote(), so this
    # cannot move the amount and the profile page says so out loud.
    # Only a token the SERVER resolved reaches metadata — process_checkout()
    # has already checked it against the store, so a body carrying a made-up
    # token cannot get one burned (or credited) at fulfilment.
    bingo = str(order.get("bingo") or "")[:40] if order.get("offer_label") else ""
    named = str(order.get("booster") or "").strip()
    booster = named if any(b["handle"] == named for b in D.BOOSTERS) else ""
    order_id = new_order_id()
    name = "%s boost" % game
    # What the customer sees on the Stripe page: the climb (from → to) and the
    # mode (Solo/Duo) from q["summary"], plus the named booster when they chose
    # one. Region, promo and the rest still ride in metadata for fulfilment.
    desc = q["summary"]
    if booster:
        desc += " · with %s" % booster

    # Charge in the currency the customer was quoted in (USD/EUR), at the same
    # fixed rate app.js displayed — so the Stripe page shows the amount on the
    # button, not a raw-USD figure the buyer never saw. Server-side conversion
    # only; the client's number is never trusted for the amount.
    charge_cur, charge_amount = pricing.charge_for(q["total"], order.get("currency"))

    params = {
        "mode": "payment",
        "success_url": base_url + "/checkout/success.html?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": base_url + "/checkout.html?canceled=1",
        "client_reference_id": order_id,
        "line_items[0][quantity]": 1,
        "line_items[0][price_data][currency]": charge_cur,
        "line_items[0][price_data][unit_amount]": charge_amount,
        "line_items[0][price_data][product_data][name]": name,
        "line_items[0][price_data][product_data][description]": desc,
        # order details ride along so fulfilment (webhook) has what it needs
        "metadata[order_id]": order_id,
        "metadata[game]": game,
        "metadata[service]": service,
        "metadata[detail]": q["summary"][:490],
        # The climb and the queue as FIELDS, not as a sentence. `detail` is the
        # human summary and fulfilment used to recover the ranks by splitting it
        # on the arrow — which reads nothing at all on a wins/placements order,
        # whose summary has no arrow, so those orders reached the board with no
        # starting rank on them. The parse survives in order_row() as the
        # fallback for a Session created before these keys existed.
        "metadata[from]": str(order.get("from") or "")[:60],
        "metadata[to]": str(order.get("to") or "")[:60],
        "metadata[mode]": str(order.get("mode") or "")[:20],
        "metadata[region]": region,
        "metadata[booster]": booster,
        "metadata[hours]": (order.get("hours") or "")[:490],
        "metadata[notes]": (order.get("notes") or "")[:490],
        # The options the buyer actually ticked, as ids. Fulfilment could infer
        # the PAID ones from the amount, but not the free ones: a free-but-
        # optional add-on (data.py's `was_pct` — "Watch your booster play")
        # moves no money and would otherwise reach the board with nothing
        # recording that it was asked for. It is an obligation on whoever
        # claims the order, so it has to travel with the order.
        "metadata[addons]": ",".join(
            a for a in (order.get("addons") or [])
            # Filtered by queue with the same call quote() makes, so the
            # metadata can never name the other queue's option — fulfilment
            # would otherwise be told to honour something never charged for.
            if isinstance(a, str) and a in pricing.ADDON
            and D.addon_applies(pricing.ADDON[a], order.get("mode", "Solo")))[:490],
        "metadata[eta]": q["eta"],
        "metadata[currency]": charge_cur,
        "metadata[promo]": q["promo_code"],
        # The recovery token, so the webhook can burn it once the order is paid
        # and the same code can never be spent twice. Empty on a normal order.
        "metadata[cart]": str(order.get("cart") or "")[:40],
        # The mystery-discount token, burned by the webhook for the same reason.
        "metadata[bingo]": bingo,
        "metadata[discount]": str(q["discount"]),
        "metadata[subtotal]": str(q["subtotal"]),
    }
    # Product-specific configuration, resolved through pricing's own clamps so
    # the metadata names what was CHARGED for, never what the body asked for. A
    # unit count or a coach that only exists in the summary sentence cannot be
    # recorded, and the /ops row then states a figure nobody bought.
    if service in ("wins", "placements"):
        params["metadata[units]"] = str(pricing.unit_count(order))
        if service == "placements" and order.get("unranked"):
            params["metadata[unranked]"] = "1"
    elif service == "coaching":
        coach, pack = pricing.coach_pick(order)
        params["metadata[coach]"] = coach["name"][:60]
        # Deliberately NOT metadata[hours]: that key is the buyer's preferred
        # PLAY WINDOW, a different fact that also has to survive to fulfilment.
        params["metadata[coach_hours]"] = str(pack["hours"])
    email = order.get("email", "").strip()
    if email:
        params["customer_email"] = email
    return params, order_id, q


# ── HTTP-agnostic route handlers — return (status_code, json_dict) ──────────


def process_checkout(raw, base_url):
    """POST /api/checkout body → (status, payload). `raw` is the request body
    bytes; `base_url` is the public origin for Stripe's redirect URLs."""
    if not stripe_key():
        # Not configured — let the page fall back to its preview confirmation.
        return 503, {"error": "payments_not_configured"}
    try:
        order = json.loads((raw or b"").decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return 400, {"error": "Malformed request"}
    if not isinstance(order, dict):
        return 400, {"error": "Malformed request"}

    # ── the abandoned-cart recovery discount ─────────────────────────────
    # `pricing.quote()` reads `recovery_pct` straight out of this dict, and this
    # dict is the request body, so the client MUST NOT be able to set it — a
    # POST carrying {"recovery_pct": 0.99} would otherwise buy a $450 climb for
    # $4. It is stripped unconditionally here and re-derived from the token
    # alone, which is checked against the store (`carts.redeemable()`: unknown,
    # already spent or expired all resolve to no discount).
    order.pop("recovery_pct", None)
    order.pop("offer_label", None)
    cart_token = str(order.get("cart") or "")[:40]
    if cart_token:
        try:
            import carts
            row = carts.redeemable(cart_token)
            if row:
                order["recovery_pct"] = carts.RECOVERY_PCT
                order["promo"] = row["token"]
                order["offer_label"] = "Come back offer"
        except Exception:                                       # noqa: BLE001
            pass          # a store hiccup must not block a paying customer

    # ── the mystery discount ─────────────────────────────────────────────
    # The same seam, the same rule: the client sends a TOKEN and never a
    # percentage. It rides in its own field rather than reusing `cart` so the
    # two stores are never asked to resolve each other's codes, and it only wins
    # when it is worth more than a recovery token the buyer also happens to hold
    # — never-stack, best-wins, decided here rather than in the browser.
    bingo_token = str(order.get("bingo") or "")[:40]
    if bingo_token:
        try:
            import mystery
            row = mystery.redeemable(bingo_token)
            if row and (row.get("pct") or 0) > (order.get("recovery_pct") or 0):
                order["recovery_pct"] = row.get("pct") or mystery.OFFER_PCT
                order["promo"] = row["token"]
                # `label_for()`, never the OFFER_LABEL constant: a row revived by
                # the follow-up mail carries a different rate AND a different
                # name, and the browser already renders the store's own label
                # (GET /api/bingo returns it). Hard-coding the first-offer
                # wording here made the page say "Last-chance discount" while the
                # server called the same order a "Mystery discount".
                order["offer_label"] = mystery.label_for(row)
        except Exception:                                       # noqa: BLE001
            pass          # a store hiccup must not block a paying customer

    try:
        params, order_id, q = build_session(order, base_url)
        # Keyed on the order id we just minted, so a retry of THIS request
        # resolves to the same Session while a genuinely new order gets a new one.
        session = stripe_call("/checkout/sessions", params,
                              idempotency_key="esb-" + order_id)
    except StripeError as e:
        return 400, {"error": str(e)}
    return 200, {"url": session.get("url"), "order_id": order_id, "total": q["total"]}


def process_session(sid):
    """GET /api/session?id=cs_… → (status, receipt payload)."""
    if not stripe_key():
        return 503, {"error": "payments_not_configured"}
    if not sid or not sid.startswith("cs_"):
        return 400, {"error": "Missing session id"}
    try:
        s = stripe_call("/checkout/sessions/" + urllib.parse.quote(sid), method="GET")
    except StripeError as e:
        return 400, {"error": str(e)}
    md = s.get("metadata") or {}
    return 200, {
        "paid": s.get("payment_status") == "paid",
        "order_id": s.get("client_reference_id") or md.get("order_id"),
        "amount_total": s.get("amount_total"),
        "currency": s.get("currency"),
        "email": (s.get("customer_details") or {}).get("email"),
        "detail": md.get("detail"), "eta": md.get("eta"),
    }


def process_webhook(raw, sig_header):
    """POST /api/webhook → (status, payload). Verifies the Stripe signature and
    then fulfils checkout.session.completed.

    **This route fails CLOSED.** With no STRIPE_WEBHOOK_SECRET set it refuses
    everything rather than trusting the body: the endpoint is public, and an
    unverified `checkout.session.completed` is a free order — anyone who can
    reach the URL could inject a paid row for the most expensive climb on the
    board, with an address they control. An unconfigured secret is a deployment
    mistake, so it has to read as one instead of quietly opening the door.
    Set ESB_ALLOW_UNSIGNED_WEBHOOK=1 to replay unsigned events locally."""
    if not webhook_secret():
        if os.environ.get("ESB_ALLOW_UNSIGNED_WEBHOOK", "").strip() != "1":
            sys.stderr.write(
                "[webhook] refused: STRIPE_WEBHOOK_SECRET is not set\n")
            return 400, {"error": "webhook_not_configured"}
    elif not _verify_sig(raw, sig_header):
        return 400, {"error": "Bad signature"}
    try:
        event = json.loads((raw or b"").decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return 400, {"error": "Malformed event"}
    if event.get("type") == "checkout.session.completed":
        # Stripe retries until it gets a 200, so the same event arrives more
        # than once as a matter of course. The orders store already dedupes on
        # order_id; this keeps the log and the stderr line honest too.
        if _seen_event(event.get("id")):
            return 200, {"received": True, "duplicate": True}
        obj = event.get("data", {}).get("object", {})
        md = obj.get("metadata") or {}
        record = {
            "at": int(time.time()),
            "order_id": obj.get("client_reference_id") or md.get("order_id"),
            "amount_total": obj.get("amount_total"),
            "email": (obj.get("customer_details") or {}).get("email"),
            "detail": md.get("detail"), "game": md.get("game"),
            "region": md.get("region"), "notes": md.get("notes"),
        }
        # Fulfilment hook: in production this is where the order joins the
        # booster board. Here we log it — to a file when the FS is writable,
        # and always to stderr.
        try:
            with open(order_log_path(), "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass
        # Also record it into the orders store, so the /ops Orders tab shows real
        # fulfilments alongside (or instead of) the seeded placeholders. Every
        # field the checkout put in Stripe metadata rides along. Best-effort by
        # design — a store hiccup must never fail the webhook (Stripe would retry
        # a non-200 and we'd double-fulfil), so it is wrapped and swallowed.
        # Burn the recovery token, if this order came back from an abandoned-cart
        # mail. Two things depend on it: the code cannot be spent a second time,
        # and the sweep must never mail somebody who has already bought. Wrapped
        # for the same reason as the store write — a cart hiccup must not make us
        # answer non-200 and be re-delivered.
        try:
            if md.get("cart"):
                import carts
                carts.recover(md["cart"],
                              order_id=record.get("order_id") or "")
        except Exception as e:               # noqa: BLE001 — never break fulfilment
            sys.stderr.write("[cart] recover failed: %s\n" % e)
        # Same for a mystery-discount token: single-use means burned on payment,
        # or the code outlives the order it was minted for.
        try:
            if md.get("bingo"):
                import mystery
                mystery.redeem(md["bingo"], order_id=record.get("order_id") or "")
        except Exception as e:               # noqa: BLE001 — never break fulfilment
            sys.stderr.write("[bingo] redeem failed: %s\n" % e)
        try:
            _record_order(md, obj)
        except Exception as e:               # noqa: BLE001 — never break fulfilment
            sys.stderr.write("orders store write skipped: %s\n" % e)
        # The buyer's confirmation, and a copy to the support mailbox. Wrapped
        # for the same reason the store write is: a mail server having a bad
        # minute must not turn into a non-200, because Stripe answers a non-200
        # by redelivering the event and we would fulfil the order twice to send
        # one email. `mailer.send()` already swallows its own errors; this is
        # the belt for anything raised while composing.
        try:
            _send_order_mail(record, md, obj)
        except Exception as e:               # noqa: BLE001 — never break fulfilment
            sys.stderr.write("order mail skipped: %s\n" % e)
        sys.stderr.write("paid order → %s\n" % record.get("order_id"))
    return 200, {"received": True}


_SEEN_EVENTS = []
_SEEN_MAX = 512


def _seen_event(event_id):
    """True if this Stripe event id has already been fulfilled in this process.

    Deliberately in-memory and bounded: it is a de-duplicator for the retry
    burst that follows one delivery, not a durable ledger. The store's own
    order_id dedupe is what survives a restart."""
    if not event_id:
        return False
    if event_id in _SEEN_EVENTS:
        return True
    _SEEN_EVENTS.append(event_id)
    if len(_SEEN_EVENTS) > _SEEN_MAX:
        del _SEEN_EVENTS[:len(_SEEN_EVENTS) - _SEEN_MAX]
    return False


def order_row(md, obj):
    """A completed Stripe session's metadata → one orders-store row.

    **Every option the buyer paid for has to survive this function**, because it
    is the only thing that writes the order down: the confirmation mail states
    the add-ons from the same metadata, but the mail is not a record anybody can
    look up later, and whoever claims the order reads /ops. A row that drops the
    add-ons shows "No add-ons on this order" over an order that was charged a
    15% priority uplift — the operator is then told to deliver less than was
    bought, and a free-but-optional row (the screen share) has nothing at all
    recording that it was asked for.

    Pure by design — `_record_order` does the store write — so the round trip
    metadata → row → `orders.clean_order()` is testable without a store.
    """
    detail = md.get("detail") or ""
    # The climb, from its own metadata keys; the sentence-parse is the fallback
    # for a Checkout Session created before those keys shipped and paid after.
    frm, to = md.get("from") or "", md.get("to") or ""
    if not frm and "→" in detail:            # "Gold IV → Platinum II · Solo"
        climb = detail.split("·")[0]
        frm, _, to = climb.partition("→")
        frm, to = frm.strip(), to.strip()
    # "Piloted" is the store's own name for a solo order (data.py reads it as
    # solo, and the seeded rows use it) — so this normalises to that, rather
    # than putting a second word for one queue in the same column.
    mode = md.get("mode") or ""
    duo = mode == "Duo queue" or (not mode and "duo" in detail.lower())
    service = md.get("service") or "division"

    row = {
        "order_id": obj.get("client_reference_id") or md.get("order_id"),
        "at": int(time.time()),
        "status": "paid",
        "game": md.get("game", ""),
        "service": service,
        "from_rank": frm, "to_rank": to,
        "mode": "Duo queue" if duo else "Piloted",
        "region": md.get("region", ""),
        "currency": md.get("currency", "usd"),
        "booster": md.get("booster", ""),
        "promo": md.get("promo", ""),
        "eta": md.get("eta", ""),
        "email": (obj.get("customer_details") or {}).get("email", ""),
        "notes": md.get("notes", ""),
        # The options ticked, as ids — the comma-joined list build_session put
        # in metadata, already queue-filtered there. Unrecognised ids are
        # dropped by orders.clean_order(), so nothing here has to be trusted.
        "addons": [a for a in (md.get("addons") or "").split(",") if a.strip()],
        "subtotal": _cents_to_whole(md.get("subtotal")),
        "discount": _cents_to_whole(md.get("discount")),
        "total": _amount_whole(obj.get("amount_total")),
    }
    # The rest of the product. Without these a 5-win order is stored as a
    # 1-win one (clean_order clamps a missing count to UNIT_MIN) and a 10-hour
    # coaching booking as a 1-hour one — a wrong figure stated as fact, which
    # is worse than the blank the add-ons left.
    if service in ("wins", "placements"):
        row["units"] = md.get("units")
        if md.get("unranked"):
            row["unranked"] = 1
    elif service == "coaching":
        row["coach"] = md.get("coach", "")
        row["hours"] = md.get("coach_hours")
    return row


def _record_order(md, obj):
    """Write one fulfilled order into the store. Kept out of the webhook body so
    its import is lazy — the store module is only needed on the fulfilment path,
    not on every checkout/session call."""
    import orders  # noqa: E402 — lazy: only the webhook needs the store
    orders.append([order_row(md, obj)])


# ── the confirmation mail ──────────────────────────────────────────────────
# Two messages leave on a paid order: the buyer's receipt, and a copy to the
# support mailbox so the operator sees the order land without watching /ops.
# Both go through mailer.py, both are best-effort, and neither can fail the
# webhook — see the call site.
#
# What they may say is bounded by what this build can actually do:
#
#   · **No tracking link.** The site's own FAQ promises orders are tracked by an
#     emailed link, and that page does not exist yet — /demo.html renders one
#     invented fixture. A link here would open somebody else's demo order. When
#     a real per-order page ships, it goes in `_order_text`/`_order_html` and
#     that FAQ answer becomes true.
#   · **⚠ One operational commitment.** "We'll email you when a booster claims
#     it" is a promise ops has to keep — nothing in this codebase sends that
#     mail yet. It reads as the next thing to build, not as a claim about
#     today; if ops can't hold it, cut the line rather than soften it.
#   · Policy is linked, never restated. A refund window quoted in an email is a
#     number that cannot be corrected after it is sent.
# CAD is "C$", never a bare "$": this row states what the card was charged,
# and a Canadian buyer reading "$415" in their confirmation cannot tell
# whether they were billed 415 Canadian or 415 US dollars. Mirrored in
# ops.js CUR_SYM, i18n.js CUR_MARK and build.py's CURRENCIES icon —
# test_pricing.py asserts all four agree and cover pricing.CHARGE_RATES.
CURRENCY_SIGNS = {"usd": "$", "eur": "€", "gbp": "£", "cad": "C$"}


SITE_ORIGIN_FALLBACK = "https://esportsboost.com"


def site_origin():
    """The public origin for links in outbound mail. The webhook has no request
    to infer one from — Stripe called it, not the buyer — so this is env-only
    and falls back to the production domain rather than to a Host header.

    SITE_URL first, because that is the canonical origin the build writes every
    other URL against. A **localhost** value is skipped whichever variable holds
    it: PUBLIC_BASE_URL is routinely a dev origin, and a link to 127.0.0.1 in a
    customer's inbox is wrong in a way no environment makes right."""
    for name in ("SITE_URL", "PUBLIC_BASE_URL"):
        v = os.environ.get(name, "").strip().rstrip("/")
        if not v.startswith("http"):
            continue
        host = v.split("//", 1)[-1].split("/")[0].split(":")[0]
        if host in ("localhost", "127.0.0.1", "0.0.0.0"):
            continue
        return v
    return SITE_ORIGIN_FALLBACK


def _money(cents, currency):
    """Stripe's minor units as the buyer saw them. Never re-converted: this is
    the amount the card was actually charged, in the currency it was charged
    in."""
    try:
        amount = int(cents) / 100.0
    except (TypeError, ValueError):
        return ""
    cur = (currency or "usd").lower()
    sign = CURRENCY_SIGNS.get(cur)
    return (sign + "{:,.2f}".format(amount) if sign
            else "{:,.2f} {}".format(amount, cur.upper()))


def _addon_names(ids):
    """The ticked options as names, for the two order mails. Ids arrive as the
    comma-joined `metadata[addons]`; anything unrecognised is dropped rather
    than printed raw, so a stale id from an add-on the catalogue has retired
    never reaches a customer's inbox. Free options are named the same as paid
    ones — the booster claiming the order has to honour them either way."""
    out = []
    for aid in str(ids).split(","):
        a = pricing.ADDON.get(aid.strip())
        if a and a["label"] not in out:
            out.append(a["label"])
    return ", ".join(out)


def _order_rows(record, md):
    """The facts both messages state, in one place so they cannot disagree.
    Only rows with something in them survive."""
    rows = [
        ("Order", record.get("order_id") or ""),
        ("Game", md.get("game") or ""),
        ("Boost", md.get("detail") or ""),
        ("Region", md.get("region") or ""),
        ("Estimated", md.get("eta") or ""),
        ("Booster", md.get("booster") or ""),
        ("Options", _addon_names(md.get("addons") or "")),
        ("Paid", _money(record.get("amount_total"), md.get("currency"))),
        # "Notes", not "Your notes" — one row list feeds both messages, and the
        # operator's copy is not the buyer's.
        ("Notes", md.get("notes") or ""),
    ]
    return [(k, str(v)) for k, v in rows if str(v).strip()]


def _order_text(rows, origin):
    body = "\n".join("%-11s%s" % (k, v) for k, v in rows)
    return """Thanks — your payment went through and your order is on the board.

%s

What happens next
A verified booster claims it, and we email you when they do. Nothing about
your account changes before that.

Questions, or want to change something? Reply to this mail. Quoting the order
number puts it in front of whoever is handling it.

The guarantee, in full: %s/guarantee.html
eSports Boost
""" % (body, origin)


def _order_html(rows, origin):
    """The buyer's copy, as HTML. Every value is escaped: `detail`, `notes` and
    the rest arrive from Stripe metadata, which the browser filled in.

    Deliberately table-based with inline styles — an email client is not a
    browser, and half of them still drop <style> blocks."""
    cells = "".join(
        '<tr><td style="padding:6px 16px 6px 0;color:#6b6b76;font-size:13px;'
        'white-space:nowrap;vertical-align:top">%s</td>'
        '<td style="padding:6px 0;color:#16161a;font-size:14px;font-weight:600">%s</td></tr>'
        % (_esc(k), _esc(v)) for k, v in rows)
    return """<!doctype html><html><body style="margin:0;padding:24px;background:#f5f5f7;
 font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;
 background:#fff;border-radius:10px;border:1px solid #e4e4ea">
<tr><td style="padding:26px 26px 8px">
  <p style="margin:0 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;
   color:#ff4a1f;font-weight:700">Order confirmed</p>
  <h1 style="margin:0 0 14px;font-size:20px;color:#16161a">Your payment went through.</h1>
  <p style="margin:0 0 18px;font-size:14px;line-height:1.55;color:#4a4a55">
   Your order is on the board. A verified booster claims it, and we email you when
   they do — nothing about your account changes before that.</p>
  <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%%;
   border-top:1px solid #ececf1;border-bottom:1px solid #ececf1;margin:0 0 18px">%s</table>
  <p style="margin:0 0 18px;font-size:14px;line-height:1.55;color:#4a4a55">
   Questions, or want to change something? Just reply to this mail — quoting the
   order number puts it in front of whoever is handling it.</p>
  <p style="margin:0 0 22px"><a href="%s/guarantee.html"
   style="display:inline-block;padding:10px 16px;border-radius:6px;background:#ff4a1f;
   color:#fff;text-decoration:none;font-size:14px;font-weight:600">Read the guarantee</a></p>
</td></tr>
<tr><td style="padding:14px 26px 22px;border-top:1px solid #ececf1;font-size:12px;color:#8a8a95">
  eSports Boost · <a href="%s" style="color:#8a8a95">esportsboost.com</a>
</td></tr>
</table></body></html>""" % (cells, origin, origin)


def _send_order_mail(record, md, obj):
    """Send the buyer their confirmation and the support mailbox its copy.

    Silent and harmless when SMTP is not configured — the same degradation the
    rest of the payment seam has, so a preview deploy takes payments without
    pretending mail went out.
    """
    import mailer  # noqa: E402 — lazy: only the fulfilment path sends mail
    if not mailer.configured():
        return
    order_id = record.get("order_id") or ""
    rows = _order_rows(record, md)
    origin = site_origin()

    buyer = record.get("email") or (obj.get("customer_details") or {}).get("email") or ""
    if mailer.valid(buyer):
        ok, err = mailer.send(
            buyer, "Your order is confirmed — %s" % order_id,
            _order_text(rows, origin), html=_order_html(rows, origin))
        if not ok:
            sys.stderr.write("[mail] confirmation for %s failed: %s\n" % (order_id, err))

    # The operator's copy. Reply-To is the buyer, so answering the notification
    # answers the customer — the same property the support form's ticket has.
    op_rows = rows + [("Customer", buyer)] if buyer else rows
    mailer.send(
        mailer.support_addr(),
        "New paid order — %s%s" % (order_id, " · %s" % md.get("game") if md.get("game") else ""),
        "A payment cleared. The order is in the store and on the log.\n\n"
        + "\n".join("%-11s%s" % (k, v) for k, v in op_rows)
        + "\n\nReply to this mail to answer the customer.\n",
        reply_to=buyer)


def _cents_to_whole(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _amount_whole(cents):
    try:
        return round(int(cents) / 100)
    except (TypeError, ValueError):
        return 0


def _verify_sig(payload, header):
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    t, v1 = parts.get("t"), parts.get("v1")
    if not t or not v1:
        return False
    signed = ("%s." % t).encode() + (payload or b"")
    expected = hmac.new(webhook_secret().encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        return False
    # reject events older than 5 minutes (replay protection)
    try:
        return abs(time.time() - int(t)) <= 300
    except ValueError:
        return False


def base_url_from(get_header, fallback_host):
    """Build the public origin from request headers. Prefers PUBLIC_BASE_URL,
    then the forwarded proto + Host (Vercel sits behind TLS termination).

    The Host fallback is a convenience for local work, not a production path:
    `Host` is attacker-controlled, so without PUBLIC_BASE_URL a forged header
    puts an arbitrary origin into Stripe's success/cancel URLs. Set it in
    production — DEPLOY.md lists it as required, and this warns if it is not."""
    env = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    host = get_header("host") or fallback_host
    if host.split(":")[0] not in ("localhost", "127.0.0.1", "0.0.0.0"):
        sys.stderr.write(
            "[checkout] PUBLIC_BASE_URL is not set — falling back to the Host "
            "header (%s), which the caller controls. Set it.\n" % host)
    fwd = get_header("x-forwarded-proto")
    if fwd:
        proto = fwd.split(",")[0].strip()
    else:
        # No proxy header → a direct connection. The local dev server speaks
        # plain HTTP, so localhost must not be handed an https redirect or Stripe
        # sends the browser back to https://localhost → ERR_SSL_PROTOCOL_ERROR.
        # Any real host reached directly still defaults to https.
        proto = "http" if host.split(":")[0] in ("localhost", "127.0.0.1", "0.0.0.0") else "https"
    return "%s://%s" % (proto, host)
