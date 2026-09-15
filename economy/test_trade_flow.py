"""End-to-end smoke test for the direct-trade API.

Run inside the economy container. The test creates two temporary penguins, trades
base-game clothing, furniture, and coins, verifies reservations and final balances,
then removes every test record.
"""

import asyncio
import hashlib
import os
import secrets

import aiohttp
import asyncpg
import bcrypt


API = "http://127.0.0.1:3010"


def login_hash(password):
    digest = hashlib.md5(password.encode()).hexdigest().upper()
    swapped = digest[16:32] + digest[0:16]
    key = swapped + os.environ.get("ECONOMY_AUTH_KEY", "houdini") + "Y(02.>'H}t\":E1"
    encrypted = hashlib.md5(key.encode()).hexdigest()
    return encrypted[16:32] + encrypted[0:16]


async def call(session, method, path, token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with session.request(method, API + path, headers=headers, json=body) as result:
        payload = await result.json()
        if result.status >= 400:
            raise AssertionError(f"{method} {path} failed ({result.status}): {payload}")
        return payload


async def main():
    suffix = secrets.token_hex(3)
    names = [f"EconA{suffix}", f"EconB{suffix}"]
    password = secrets.token_urlsafe(18)
    pool = await asyncpg.create_pool(
        host=os.environ.get("POSTGRES_HOST", "db"),
        user=os.environ["POSTGRES_USER"],
        database=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    ids = []
    try:
        async with pool.acquire() as connection:
            item_ids = await connection.fetch(
                """SELECT id FROM item
                    WHERE type BETWEEN 2 AND 9 AND NOT epf AND NOT tour AND NOT treasure
                    ORDER BY id LIMIT 2"""
            )
            furniture_id = await connection.fetchval("SELECT id FROM furniture ORDER BY id LIMIT 1")
            assert len(item_ids) == 2 and furniture_id, "Base-game item data is missing"
            encoded = bcrypt.hashpw(login_hash(password).encode(), bcrypt.gensalt()).decode()
            for name in names:
                ids.append(await connection.fetchval(
                    """INSERT INTO penguin(username,nickname,password,email,active,coins,color)
                       VALUES($1,$1,$2,$3,true,1000,1) RETURNING id""",
                    name.lower(), encoded, f"{name}@example.invalid",
                ))
            await connection.execute(
                "INSERT INTO penguin_item(penguin_id,item_id) VALUES($1,$2),($3,$4)",
                ids[0], item_ids[0]["id"], ids[1], item_ids[1]["id"],
            )
            await connection.execute(
                "INSERT INTO penguin_furniture(penguin_id,furniture_id,quantity) VALUES($1,$2,2)",
                ids[0], furniture_id,
            )

        async with aiohttp.ClientSession() as session:
            tokens = []
            for name in names:
                result = await call(session, "POST", "/api/login", body={"username": name, "password": password})
                tokens.append(result["token"])
            invited = await call(session, "POST", "/api/trades/invite", tokens[0], {"target_id": ids[1]})
            trade_id = invited["trade"]["id"]
            await call(session, "POST", f"/api/trades/{trade_id}/accept", tokens[1])
            await call(session, "PUT", f"/api/trades/{trade_id}/offer", tokens[0], {
                "coins": 40,
                "assets": [
                    {"kind": "clothing", "id": item_ids[0]["id"], "quantity": 1},
                    {"kind": "furniture", "id": furniture_id, "quantity": 1},
                ],
            })
            await call(session, "PUT", f"/api/trades/{trade_id}/offer", tokens[1], {
                "coins": 15,
                "assets": [{"kind": "clothing", "id": item_ids[1]["id"], "quantity": 1}],
            })

            async with pool.acquire() as connection:
                try:
                    await connection.execute("UPDATE penguin SET coins=0 WHERE id=$1", ids[0])
                    raise AssertionError("Coin reservation did not block spending")
                except asyncpg.RaiseError:
                    pass
                try:
                    await connection.execute(
                        "DELETE FROM penguin_item WHERE penguin_id=$1 AND item_id=$2",
                        ids[0], item_ids[0]["id"],
                    )
                    raise AssertionError("Item reservation did not block deletion")
                except asyncpg.RaiseError:
                    pass

            first_ready = await call(session, "POST", f"/api/trades/{trade_id}/ready", tokens[0])
            assert any(p["ready"] for p in first_ready["trade"]["participants"])
            changed = await call(session, "PUT", f"/api/trades/{trade_id}/offer", tokens[1], {
                "coins": 20,
                "assets": [{"kind": "clothing", "id": item_ids[1]["id"], "quantity": 1}],
            })
            assert not any(p["ready"] for p in changed["trade"]["participants"]), "Offer edit must clear Ready"
            await call(session, "POST", f"/api/trades/{trade_id}/ready", tokens[0])
            locked = await call(session, "POST", f"/api/trades/{trade_id}/ready", tokens[1])
            assert locked["trade"]["status"] == "locked"
            await call(session, "POST", f"/api/trades/{trade_id}/confirm", tokens[0])
            complete = await call(session, "POST", f"/api/trades/{trade_id}/confirm", tokens[1])
            assert complete["trade"]["status"] == "complete"

        async with pool.acquire() as connection:
            balances = await connection.fetch("SELECT id,coins FROM penguin WHERE id=ANY($1::int[]) ORDER BY id", ids)
            assert {row["id"]: row["coins"] for row in balances} == {ids[0]: 980, ids[1]: 1020}
            assert await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM penguin_item WHERE penguin_id=$1 AND item_id=$2)",
                ids[1], item_ids[0]["id"],
            )
            assert await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM penguin_item WHERE penguin_id=$1 AND item_id=$2)",
                ids[0], item_ids[1]["id"],
            )
            assert await connection.fetchval(
                "SELECT quantity FROM penguin_furniture WHERE penguin_id=$1 AND furniture_id=$2",
                ids[1], furniture_id,
            ) == 1
            assert await connection.fetchval("SELECT EXISTS(SELECT 1 FROM economy_trade_receipt WHERE trade_id=$1)", trade_id)
        print("PASS: clothing, furniture, coins, reservations, Ready reset, dual confirmation, and receipt")
    finally:
        if ids:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("SELECT set_config('economy.transfer','on',true)")
                    await connection.execute("DELETE FROM penguin WHERE id=ANY($1::int[])", ids)
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
