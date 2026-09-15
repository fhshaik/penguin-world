"""Create a local-only account from JSON on stdin; never log its password."""
import asyncio
import json
import os
import re
import sys

import asyncpg
import bcrypt

from houdini.crypto import Crypto


async def main():
    data = json.load(sys.stdin)
    name, password = data["name"], data["password"]
    if not re.fullmatch(r"[A-Za-z0-9 ]{4,12}", name):
        raise ValueError("Use 4-12 letters, numbers, or spaces for the name.")
    if len(password) < 10:
        raise ValueError("Use a password of at least 10 characters.")

    login_hash = Crypto.get_login_hash(Crypto.hash(password).upper(), "houdini")
    hashed = bcrypt.hashpw(login_hash.encode(), bcrypt.gensalt(12)).decode()
    connection = await asyncpg.connect(
        host="db",
        user=os.environ["POSTGRES_USER"],
        database=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        async with connection.transaction():
            penguin_id = await connection.fetchval(
                """INSERT INTO penguin
                (username,nickname,password,email,active,color,approval_en)
                VALUES ($1,$2,$3,$4,true,1,true) RETURNING id""",
                name.lower(),
                name,
                hashed,
                name.lower().replace(" ", "") + "@penguin.invalid",
            )
            await connection.execute(
                "INSERT INTO penguin_item (penguin_id,item_id) VALUES ($1,1)", penguin_id
            )
            await connection.execute(
                "INSERT INTO penguin_postcard (penguin_id,postcard_id) VALUES ($1,125)",
                penguin_id,
            )
        print("Created penguin: " + name)
    finally:
        await connection.close()


asyncio.run(main())
