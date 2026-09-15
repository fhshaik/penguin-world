"""Create or refresh local trade-test accounts from JSON on stdin."""

import asyncio
import json
import os
import re
import sys

import asyncpg
import bcrypt

sys.path.insert(0, "/usr/src/houdini")
from houdini.crypto import Crypto


def password_hash(password):
    login_hash = Crypto.get_login_hash(Crypto.hash(password).upper(), "houdini")
    return bcrypt.hashpw(login_hash.encode(), bcrypt.gensalt(12)).decode()


async def upsert_penguin(connection, account, color):
    name = account["name"].strip()
    password = account["password"]
    if not re.fullmatch(r"[A-Za-z0-9 ]{4,12}", name):
        raise ValueError("Account names must contain 4-12 letters, numbers, or spaces.")
    if len(password) < 10:
        raise ValueError("Account passwords must contain at least 10 characters.")
    return await connection.fetchval(
        """INSERT INTO penguin
             (username,nickname,password,email,active,coins,color,
              approval_en,approval_pt,approval_fr,approval_es,approval_de,approval_ru)
           VALUES($1,$2,$3,$4,true,5000,$5,true,true,true,true,true,true)
           ON CONFLICT(username) DO UPDATE SET
             nickname=EXCLUDED.nickname,
             password=EXCLUDED.password,
             active=true,
             coins=GREATEST(penguin.coins,5000),
             approval_en=true,
             approval_pt=true,
             approval_fr=true,
             approval_es=true,
             approval_de=true,
             approval_ru=true
           RETURNING id""",
        name.lower(),
        name,
        password_hash(password),
        name.lower().replace(" ", "") + "@penguin.invalid",
        color,
    )


async def main():
    config = json.load(sys.stdin)
    accounts = [config["player"], config["buddy"]]
    connection = await asyncpg.connect(
        host="db",
        user=os.environ["POSTGRES_USER"],
        database=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        async with connection.transaction():
            colors = await connection.fetch("SELECT id FROM item WHERE type=1 ORDER BY id LIMIT 2")
            items = await connection.fetch(
                """SELECT id,name FROM item
                   WHERE type BETWEEN 2 AND 9 AND NOT epf AND NOT tour AND NOT treasure
                   ORDER BY id LIMIT 4"""
            )
            furniture = await connection.fetchrow("SELECT id,name FROM furniture ORDER BY id LIMIT 1")
            if len(colors) < 2 or len(items) < 4 or not furniture:
                raise RuntimeError("The base-game item catalog is incomplete.")

            ids = []
            for index, account in enumerate(accounts):
                penguin_id = await upsert_penguin(connection, account, colors[index]["id"])
                ids.append(penguin_id)
                await connection.execute(
                    "INSERT INTO penguin_item(penguin_id,item_id) VALUES($1,$2),($1,$3) ON CONFLICT DO NOTHING",
                    penguin_id,
                    items[index * 2]["id"],
                    items[index * 2 + 1]["id"],
                )
                await connection.execute(
                    """INSERT INTO penguin_furniture(penguin_id,furniture_id,quantity)
                       VALUES($1,$2,2)
                       ON CONFLICT(penguin_id,furniture_id) DO UPDATE
                       SET quantity=GREATEST(penguin_furniture.quantity,2)""",
                    penguin_id,
                    furniture["id"],
                )
                await connection.execute(
                    "INSERT INTO penguin_postcard(penguin_id,postcard_id) VALUES($1,125) ON CONFLICT DO NOTHING",
                    penguin_id,
                )

        print(f"Ready: {accounts[0]['name']} (ID {ids[0]}) and {accounts[1]['name']} (ID {ids[1]})")
        print("Seeded 5,000+ coins, two distinct clothing items each, and furniture.")
    finally:
        await connection.close()


asyncio.run(main())
