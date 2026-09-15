import hashlib
import json
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg
import bcrypt
from sanic import Sanic, response


ROOT = Path(__file__).parent
app = Sanic("PenguinEconomy")
app.static("/assets", str(ROOT / "static"))
login_attempts = defaultdict(deque)


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def login_hash(password):
    digest = hashlib.md5(password.encode()).hexdigest().upper()
    swapped = digest[16:32] + digest[0:16]
    key = swapped + os.environ.get("ECONOMY_AUTH_KEY", "houdini") + "Y(02.>'H}t\":E1"
    encrypted = hashlib.md5(key.encode()).hexdigest()
    return encrypted[16:32] + encrypted[0:16]


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def bearer(request):
    value = request.headers.get("authorization", "")
    if not value.startswith("Bearer "):
        raise ApiError("Sign in to use trading.", 401)
    return value[7:]


async def actor(request, connection=None):
    query = """SELECT p.id, p.username, p.nickname, p.coins
                 FROM economy_session s
                 JOIN penguin p ON p.id = s.penguin_id
                WHERE s.token_hash = $1 AND s.expires_at > now()"""
    digest = token_digest(bearer(request))
    if connection:
        row = await connection.fetchrow(query, digest)
    else:
        async with app.ctx.pool.acquire() as conn:
            row = await conn.fetchrow(query, digest)
    if not row:
        raise ApiError("Your trade session expired. Sign in again.", 401)
    return row


def serial(row):
    return dict(row) if row else None


async def inventory(connection, penguin_id):
    clothing = await connection.fetch(
        """SELECT i.id, i.name, i.type, i.cost,
                  CASE
                    WHEN i.type IN (1, 10) THEN 'Colors and award items cannot be traded.'
                    WHEN i.epf OR i.tour OR i.treasure THEN 'Special reward items cannot be traded.'
                    WHEN b.asset_id IS NOT NULL THEN b.reason
                    WHEN i.id = ANY(ARRAY[p.color,p.head,p.face,p.neck,p.body,p.hand,p.feet,p.photo,p.flag])
                      THEN 'Unequip this item before trading it.'
                    ELSE NULL
                  END AS blocked_reason
             FROM penguin_item pi
             JOIN item i ON i.id = pi.item_id
             JOIN penguin p ON p.id = pi.penguin_id
        LEFT JOIN economy_bound_asset b ON b.kind = 'clothing' AND b.asset_id = i.id
            WHERE pi.penguin_id = $1
            ORDER BY i.type, i.name, i.id""",
        penguin_id,
    )
    furniture = await connection.fetch(
        """SELECT f.id, f.name, f.cost, pf.quantity,
                  GREATEST(pf.quantity - COUNT(placed.*)::int, 0) AS available,
                  CASE WHEN b.asset_id IS NOT NULL THEN b.reason
                       WHEN pf.quantity - COUNT(placed.*)::int <= 0 THEN 'All copies are placed in an igloo.'
                       ELSE NULL END AS blocked_reason
             FROM penguin_furniture pf
             JOIN furniture f ON f.id = pf.furniture_id
        LEFT JOIN penguin_igloo_room pir ON pir.penguin_id = pf.penguin_id
        LEFT JOIN igloo_furniture placed
               ON placed.igloo_id = pir.id AND placed.furniture_id = pf.furniture_id
        LEFT JOIN economy_bound_asset b ON b.kind = 'furniture' AND b.asset_id = f.id
            WHERE pf.penguin_id = $1
            GROUP BY f.id, f.name, f.cost, pf.quantity, b.asset_id, b.reason
            ORDER BY f.name, f.id""",
        penguin_id,
    )
    return {
        "clothing": [dict(row) | {"kind": "clothing", "quantity": 1} for row in clothing],
        "furniture": [dict(row) | {"kind": "furniture"} for row in furniture],
    }


async def load_trade(connection, trade_id, viewer_id=None, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    trade = await connection.fetchrow(
        "SELECT id, status, revision, created_at, updated_at, completed_at FROM economy_trade WHERE id=$1" + suffix,
        trade_id,
    )
    if not trade:
        raise ApiError("Trade not found.", 404)
    people = await connection.fetch(
        """SELECT tp.penguin_id, tp.side, tp.coins, tp.ready, tp.confirmed, tp.active,
                  p.username, p.nickname
             FROM economy_trade_participant tp JOIN penguin p ON p.id=tp.penguin_id
            WHERE tp.trade_id=$1 ORDER BY tp.side""",
        trade_id,
    )
    assets = await connection.fetch(
        """SELECT ta.penguin_id, ta.kind, ta.asset_id AS id, ta.quantity,
                  COALESCE(i.name, f.name) AS name
             FROM economy_trade_asset ta
        LEFT JOIN item i ON ta.kind='clothing' AND i.id=ta.asset_id
        LEFT JOIN furniture f ON ta.kind='furniture' AND f.id=ta.asset_id
            WHERE ta.trade_id=$1 ORDER BY ta.penguin_id, ta.kind, name""",
        trade_id,
    )
    grouped = defaultdict(list)
    for item in assets:
        grouped[item["penguin_id"]].append(dict(item))
    participants = []
    for person in people:
        result = dict(person)
        result["assets"] = grouped[person["penguin_id"]]
        result["is_me"] = person["penguin_id"] == viewer_id
        participants.append(result)
    result = dict(trade)
    result["id"] = str(result["id"])
    for key in ("created_at", "updated_at", "completed_at"):
        result[key] = result[key].isoformat() if result[key] else None
    result["participants"] = participants
    return result


async def current_trade(connection, penguin_id):
    trade_id = await connection.fetchval(
        "SELECT trade_id FROM economy_trade_participant WHERE penguin_id=$1 AND active",
        penguin_id,
    )
    return await load_trade(connection, trade_id, penguin_id) if trade_id else None


async def require_participant(connection, trade_id, penguin_id, lock=True):
    trade = await load_trade(connection, trade_id, penguin_id, lock=lock)
    person = next((p for p in trade["participants"] if p["penguin_id"] == penguin_id), None)
    if not person or not person["active"]:
        raise ApiError("You are not part of this active trade.", 403)
    return trade, person


@app.listener("before_server_start")
async def setup(application, _loop):
    application.ctx.pool = await asyncpg.create_pool(
        host=os.environ.get("POSTGRES_HOST", "db"),
        user=os.environ["POSTGRES_USER"],
        database=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        min_size=1,
        max_size=10,
    )
    async with application.ctx.pool.acquire() as connection:
        await connection.execute((ROOT / "schema.sql").read_text())
        await connection.execute("DELETE FROM economy_session WHERE expires_at <= now()")
        await connection.execute(
            """UPDATE economy_trade SET status='cancelled', updated_at=now()
                 WHERE status IN ('invited','open','locked') AND updated_at < now() - interval '30 minutes'"""
        )
        await connection.execute(
            """UPDATE economy_trade_participant SET active=false
                 WHERE active AND trade_id IN (SELECT id FROM economy_trade WHERE status='cancelled')"""
        )


@app.listener("after_server_stop")
async def shutdown(application, _loop):
    await application.ctx.pool.close()


@app.exception(ApiError)
async def api_error(_request, error):
    return response.json({"error": error.message}, status=error.status)


@app.exception(Exception)
async def unexpected_error(request, error):
    request.app.logger.exception("Unhandled economy error", exc_info=error)
    return response.json({"error": "The trade service encountered an unexpected error."}, status=500)


@app.get("/")
async def index(_request):
    return await response.file(str(ROOT / "static" / "index.html"))


@app.get("/health")
async def health(_request):
    async with app.ctx.pool.acquire() as connection:
        await connection.fetchval("SELECT 1")
    return response.json({"ok": True})


@app.post("/api/login")
async def login(request):
    now = time.monotonic()
    attempts = login_attempts[request.headers.get("x-real-ip", request.remote_addr)]
    while attempts and attempts[0] < now - 60:
        attempts.popleft()
    if len(attempts) >= 8:
        raise ApiError("Too many sign-in attempts. Wait one minute.", 429)
    attempts.append(now)
    body = request.json or {}
    username = str(body.get("username", "")).strip().lower()
    password = str(body.get("password", ""))
    async with app.ctx.pool.acquire() as connection:
        player = await connection.fetchrow(
            "SELECT id, username, nickname, password, coins FROM penguin WHERE lower(username)=$1 AND active",
            username,
        )
        valid = player and bcrypt.checkpw(login_hash(password).encode(), player["password"].encode())
        if not valid:
            raise ApiError("Invalid penguin name or password.", 401)
        attempts.clear()
        token = secrets.token_urlsafe(36)
        await connection.execute(
            "INSERT INTO economy_session(token_hash,penguin_id,expires_at) VALUES($1,$2,$3)",
            token_digest(token),
            player["id"],
            datetime.utcnow() + timedelta(hours=12),
        )
        return response.json({
            "token": token,
            "player": {key: player[key] for key in ("id", "username", "nickname", "coins")},
        })


@app.post("/api/logout")
async def logout(request):
    token = bearer(request)
    async with app.ctx.pool.acquire() as connection:
        await connection.execute("DELETE FROM economy_session WHERE token_hash=$1", token_digest(token))
    return response.json({"ok": True})


@app.get("/api/state")
async def state(request):
    async with app.ctx.pool.acquire() as connection:
        player = await actor(request, connection)
        players = await connection.fetch(
            """SELECT p.id, p.username, p.nickname,
                      EXISTS(SELECT 1 FROM economy_trade_participant tp WHERE tp.penguin_id=p.id AND tp.active) AS busy
                 FROM penguin p WHERE p.active AND p.id<>$1 ORDER BY lower(p.nickname) LIMIT 100""",
            player["id"],
        )
        return response.json({
            "player": serial(player),
            "players": [dict(row) for row in players],
            "inventory": await inventory(connection, player["id"]),
            "trade": await current_trade(connection, player["id"]),
        })


@app.post("/api/trades/invite")
async def invite(request):
    body = request.json or {}
    try:
        target_id = int(body.get("target_id", 0))
    except (TypeError, ValueError):
        raise ApiError("Choose a valid penguin to invite.")
    async with app.ctx.pool.acquire() as connection:
        player = await actor(request, connection)
        if target_id == player["id"]:
            raise ApiError("You cannot trade with yourself.")
        async with connection.transaction():
            locked = await connection.fetch(
                "SELECT id, nickname, active FROM penguin WHERE id=ANY($1::int[]) ORDER BY id FOR UPDATE",
                sorted([player["id"], target_id]),
            )
            if len(locked) != 2 or not all(row["active"] for row in locked):
                raise ApiError("That penguin is unavailable.", 404)
            if await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM economy_trade_participant WHERE penguin_id=ANY($1::int[]) AND active)",
                [player["id"], target_id],
            ):
                raise ApiError("One of you is already in a trade.", 409)
            trade_id = uuid.uuid4()
            await connection.execute("INSERT INTO economy_trade(id,status) VALUES($1,'invited')", trade_id)
            await connection.executemany(
                "INSERT INTO economy_trade_participant(trade_id,penguin_id,side) VALUES($1,$2,$3)",
                [(trade_id, player["id"], 0), (trade_id, target_id, 1)],
            )
        return response.json({"trade": await load_trade(connection, trade_id, player["id"])})


@app.post("/api/trades/<trade_id:uuid>/accept")
async def accept(request, trade_id):
    async with app.ctx.pool.acquire() as connection:
        player = await actor(request, connection)
        async with connection.transaction():
            trade, person = await require_participant(connection, trade_id, player["id"])
            if trade["status"] != "invited" or person["side"] != 1:
                raise ApiError("This invitation cannot be accepted.", 409)
            await connection.execute(
                "UPDATE economy_trade SET status='open', revision=revision+1, updated_at=now() WHERE id=$1",
                trade_id,
            )
        return response.json({"trade": await load_trade(connection, trade_id, player["id"])})


def normalize_assets(raw):
    merged = {}
    for value in raw or []:
        if not isinstance(value, dict):
            raise ApiError("The offer contains an invalid item.")
        try:
            kind = str(value.get("kind", ""))
            asset_id = int(value.get("id", 0))
            quantity = int(value.get("quantity", 1))
        except (TypeError, ValueError):
            raise ApiError("The offer contains an invalid item.")
        if kind not in ("clothing", "furniture") or asset_id <= 0 or quantity <= 0:
            raise ApiError("The offer contains an invalid item.")
        key = (kind, asset_id)
        merged[key] = merged.get(key, 0) + quantity
    if len(merged) > 24:
        raise ApiError("An offer can contain at most 24 different items.")
    return [(kind, asset_id, quantity) for (kind, asset_id), quantity in merged.items()]


async def validate_offer(connection, trade, penguin_id, coins, assets):
    player = await connection.fetchrow(
        "SELECT id, coins, color, head, face, neck, body, hand, feet, photo, flag FROM penguin WHERE id=$1 FOR UPDATE",
        penguin_id,
    )
    if coins < 0 or coins > player["coins"]:
        raise ApiError("You do not have enough coins for that offer.")
    other_id = next(p["penguin_id"] for p in trade["participants"] if p["penguin_id"] != penguin_id)
    equipped = {player[key] for key in ("color", "head", "face", "neck", "body", "hand", "feet", "photo", "flag")}
    for kind, asset_id, quantity in assets:
        bound = await connection.fetchval(
            "SELECT reason FROM economy_bound_asset WHERE kind=$1 AND asset_id=$2", kind, asset_id
        )
        if bound:
            raise ApiError(bound)
        if kind == "clothing":
            item = await connection.fetchrow(
                """SELECT i.type, i.epf, i.tour, i.treasure,
                          EXISTS(SELECT 1 FROM penguin_item WHERE penguin_id=$1 AND item_id=i.id) AS owned,
                          EXISTS(SELECT 1 FROM penguin_item WHERE penguin_id=$2 AND item_id=i.id) AS other_owned
                     FROM item i WHERE i.id=$3""",
                penguin_id, other_id, asset_id,
            )
            if not item or not item["owned"]:
                raise ApiError("You no longer own one of the offered items.")
            if quantity != 1:
                raise ApiError("Base-game clothing cannot be stacked.")
            if item["type"] in (1, 10) or item["epf"] or item["tour"] or item["treasure"]:
                raise ApiError("That special item cannot be traded.")
            if asset_id in equipped:
                raise ApiError("Unequip that item before offering it.")
            if item["other_owned"]:
                raise ApiError("The other penguin already owns that clothing item.")
        else:
            furniture = await connection.fetchrow(
                """SELECT pf.quantity, f.max_quantity,
                          (SELECT COUNT(*) FROM penguin_igloo_room pir
                            JOIN igloo_furniture placed ON placed.igloo_id=pir.id
                           WHERE pir.penguin_id=$1 AND placed.furniture_id=$3) AS placed,
                          COALESCE((SELECT quantity FROM penguin_furniture WHERE penguin_id=$2 AND furniture_id=$3),0) AS other_quantity
                     FROM penguin_furniture pf JOIN furniture f ON f.id=pf.furniture_id
                    WHERE pf.penguin_id=$1 AND pf.furniture_id=$3""",
                penguin_id, other_id, asset_id,
            )
            if not furniture or furniture["quantity"] - furniture["placed"] < quantity:
                raise ApiError("You do not have that many unplaced copies of the furniture.")
            if furniture["other_quantity"] + quantity > furniture["max_quantity"]:
                raise ApiError("The other penguin cannot hold that many copies of the furniture.")


@app.put("/api/trades/<trade_id:uuid>/offer")
async def offer(request, trade_id):
    body = request.json or {}
    try:
        coins = int(body.get("coins", 0))
    except (TypeError, ValueError):
        raise ApiError("Enter a valid whole-number coin amount.")
    assets = normalize_assets(body.get("assets"))
    async with app.ctx.pool.acquire() as connection:
        player = await actor(request, connection)
        async with connection.transaction():
            trade, _person = await require_participant(connection, trade_id, player["id"])
            if trade["status"] != "open":
                raise ApiError("Offers can only change while the trade is open.", 409)
            await validate_offer(connection, trade, player["id"], coins, assets)
            await connection.execute(
                "UPDATE economy_trade_participant SET coins=$3 WHERE trade_id=$1 AND penguin_id=$2",
                trade_id, player["id"], coins,
            )
            await connection.execute("DELETE FROM economy_trade_asset WHERE trade_id=$1 AND penguin_id=$2", trade_id, player["id"])
            if assets:
                await connection.executemany(
                    "INSERT INTO economy_trade_asset(trade_id,penguin_id,kind,asset_id,quantity) VALUES($1,$2,$3,$4,$5)",
                    [(trade_id, player["id"], kind, asset_id, quantity) for kind, asset_id, quantity in assets],
                )
            await connection.execute("UPDATE economy_trade_participant SET ready=false, confirmed=false WHERE trade_id=$1", trade_id)
            await connection.execute("UPDATE economy_trade SET revision=revision+1, updated_at=now() WHERE id=$1", trade_id)
        return response.json({"trade": await load_trade(connection, trade_id, player["id"])})


@app.post("/api/trades/<trade_id:uuid>/ready")
async def ready(request, trade_id):
    async with app.ctx.pool.acquire() as connection:
        player = await actor(request, connection)
        async with connection.transaction():
            trade, _person = await require_participant(connection, trade_id, player["id"])
            if trade["status"] != "open":
                raise ApiError("This trade is not accepting Ready responses.", 409)
            await connection.execute(
                "UPDATE economy_trade_participant SET ready=true WHERE trade_id=$1 AND penguin_id=$2",
                trade_id, player["id"],
            )
            both = await connection.fetchval("SELECT bool_and(ready) FROM economy_trade_participant WHERE trade_id=$1", trade_id)
            if both:
                refreshed = await load_trade(connection, trade_id, player["id"])
                for participant in refreshed["participants"]:
                    assets = [(a["kind"], a["id"], a["quantity"]) for a in participant["assets"]]
                    await validate_offer(connection, refreshed, participant["penguin_id"], participant["coins"], assets)
                await connection.execute("UPDATE economy_trade SET status='locked', revision=revision+1, updated_at=now() WHERE id=$1", trade_id)
        return response.json({"trade": await load_trade(connection, trade_id, player["id"])})


async def complete_trade(connection, trade_id, viewer_id):
    trade = await load_trade(connection, trade_id, viewer_id)
    people = trade["participants"]
    ids = sorted(p["penguin_id"] for p in people)
    rows = await connection.fetch("SELECT id, coins FROM penguin WHERE id=ANY($1::int[]) ORDER BY id FOR UPDATE", ids)
    holdings = {row["id"]: {"coins": row["coins"]} for row in rows}
    if len(holdings) != 2:
        raise ApiError("A trade participant no longer exists.", 409)
    for person in people:
        assets = [(a["kind"], a["id"], a["quantity"]) for a in person["assets"]]
        await validate_offer(connection, trade, person["penguin_id"], person["coins"], assets)

    left, right = people
    await connection.execute("SELECT set_config('economy.transfer','on',true)")
    await connection.execute(
        "UPDATE penguin SET coins=coins-$2+$3 WHERE id=$1",
        left["penguin_id"], left["coins"], right["coins"],
    )
    await connection.execute(
        "UPDATE penguin SET coins=coins-$2+$3 WHERE id=$1",
        right["penguin_id"], right["coins"], left["coins"],
    )

    clothing_moves = []
    furniture_delta = defaultdict(int)
    for giver, receiver in ((left, right), (right, left)):
        for asset in giver["assets"]:
            if asset["kind"] == "clothing":
                clothing_moves.append((giver["penguin_id"], receiver["penguin_id"], asset["id"]))
            else:
                furniture_delta[(giver["penguin_id"], asset["id"])] -= asset["quantity"]
                furniture_delta[(receiver["penguin_id"], asset["id"])] += asset["quantity"]
    for giver_id, _receiver_id, item_id in clothing_moves:
        await connection.execute(
            """UPDATE penguin SET
                 head=CASE WHEN head=$2 THEN NULL ELSE head END,
                 face=CASE WHEN face=$2 THEN NULL ELSE face END,
                 neck=CASE WHEN neck=$2 THEN NULL ELSE neck END,
                 body=CASE WHEN body=$2 THEN NULL ELSE body END,
                 hand=CASE WHEN hand=$2 THEN NULL ELSE hand END,
                 feet=CASE WHEN feet=$2 THEN NULL ELSE feet END,
                 photo=CASE WHEN photo=$2 THEN NULL ELSE photo END,
                 flag=CASE WHEN flag=$2 THEN NULL ELSE flag END
               WHERE id=$1""",
            giver_id, item_id,
        )
        await connection.execute("DELETE FROM penguin_item WHERE penguin_id=$1 AND item_id=$2", giver_id, item_id)
    for _giver_id, receiver_id, item_id in clothing_moves:
        await connection.execute("INSERT INTO penguin_item(penguin_id,item_id) VALUES($1,$2)", receiver_id, item_id)
    for (penguin_id, furniture_id), delta in furniture_delta.items():
        current = await connection.fetchval(
            "SELECT quantity FROM penguin_furniture WHERE penguin_id=$1 AND furniture_id=$2",
            penguin_id, furniture_id,
        ) or 0
        quantity = current + delta
        if quantity < 0:
            raise ApiError("Furniture ownership changed before confirmation.", 409)
        if quantity == 0:
            await connection.execute("DELETE FROM penguin_furniture WHERE penguin_id=$1 AND furniture_id=$2", penguin_id, furniture_id)
        else:
            await connection.execute(
                """INSERT INTO penguin_furniture(penguin_id,furniture_id,quantity) VALUES($1,$2,$3)
                   ON CONFLICT(penguin_id,furniture_id) DO UPDATE SET quantity=EXCLUDED.quantity""",
                penguin_id, furniture_id, quantity,
            )
    snapshot = {"revision": trade["revision"], "participants": people}
    await connection.execute(
        "INSERT INTO economy_trade_receipt(trade_id,snapshot) VALUES($1,$2::jsonb)",
        trade_id, json.dumps(snapshot),
    )
    await connection.execute(
        "UPDATE economy_trade SET status='complete', completed_at=now(), updated_at=now() WHERE id=$1",
        trade_id,
    )
    await connection.execute("UPDATE economy_trade_participant SET active=false WHERE trade_id=$1", trade_id)


@app.post("/api/trades/<trade_id:uuid>/confirm")
async def confirm(request, trade_id):
    async with app.ctx.pool.acquire() as connection:
        player = await actor(request, connection)
        async with connection.transaction():
            trade, _person = await require_participant(connection, trade_id, player["id"])
            if trade["status"] != "locked":
                raise ApiError("Both players must be Ready before confirming.", 409)
            await connection.execute(
                "UPDATE economy_trade_participant SET confirmed=true WHERE trade_id=$1 AND penguin_id=$2",
                trade_id, player["id"],
            )
            both = await connection.fetchval("SELECT bool_and(confirmed) FROM economy_trade_participant WHERE trade_id=$1", trade_id)
            if both:
                await complete_trade(connection, trade_id, player["id"])
        return response.json({"trade": await load_trade(connection, trade_id, player["id"])})


@app.post("/api/trades/<trade_id:uuid>/cancel")
async def cancel(request, trade_id):
    async with app.ctx.pool.acquire() as connection:
        player = await actor(request, connection)
        async with connection.transaction():
            trade, _person = await require_participant(connection, trade_id, player["id"])
            if trade["status"] not in ("invited", "open", "locked"):
                raise ApiError("This trade has already ended.", 409)
            await connection.execute("UPDATE economy_trade SET status='cancelled', updated_at=now() WHERE id=$1", trade_id)
            await connection.execute("UPDATE economy_trade_participant SET active=false WHERE trade_id=$1", trade_id)
        return response.json({"trade": await load_trade(connection, trade_id, player["id"])})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("ECONOMY_PORT", "3010")), access_log=False)
