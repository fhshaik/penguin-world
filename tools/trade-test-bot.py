"""Keep a local test penguin online in Town for player-card UI testing."""

import json
import os
import select
import socket
import sys
import time
from xml.etree import ElementTree as ET

sys.path.insert(0, "/usr/src/houdini")
from houdini.crypto import Crypto


def send(sock, message):
    sock.sendall(message.encode() + b"\0")


def receive(file):
    data = bytearray()
    while True:
        value = file.read(1)
        if not value:
            raise RuntimeError("The game server closed the connection.")
        if value == b"\0":
            return data.decode()
        data.extend(value)


def connect(host, port):
    sock = socket.create_connection((host, port), timeout=15)
    return sock, sock.makefile("rb")


def handshake(sock, file):
    send(sock, '<msg t="sys"><body action="verChk" r="0"><ver v="253" /></body></msg>')
    if "apiOK" not in receive(file):
        raise RuntimeError("Version handshake failed.")
    send(sock, '<msg t="sys"><body action="rndK" r="-1"></body></msg>')
    return ET.fromstring(receive(file)).find(".//k").text


def login(sock, username, password):
    send(
        sock,
        '<msg t="sys"><body action="login" r="0"><login z="w1"><nick><![CDATA['
        + username
        + "]]></nick><pword><![CDATA["
        + password
        + "]]></pword></login></body></msg>",
    )


def main():
    with open(sys.argv[1], encoding="utf-8") as source:
        account = json.load(source)["buddy"]
    username = account["name"].lower()
    password = account["password"]
    login_host = os.environ.get("GAME_LOGIN_HOST", "houdini_login")
    login_port = int(os.environ.get("GAME_LOGIN_PORT", "6112"))
    world_host = os.environ.get("GAME_WORLD_HOST", "houdini_blizzard")
    world_port = int(os.environ.get("GAME_WORLD_PORT", "19875"))

    sock, file = connect(login_host, login_port)
    key = handshake(sock, file)
    login(sock, username, Crypto.get_login_hash(Crypto.hash(password).upper(), key))
    reply = receive(file).split("%")
    if len(reply) < 6 or reply[2] != "l":
        raise RuntimeError("Login server rejected the test buddy.")
    raw, confirmation = reply[4], reply[5]
    sock.close()
    penguin_id, _, _, login_key, *_ = raw.split("|")

    sock, file = connect(world_host, world_port)
    key = handshake(sock, file)
    world_password = Crypto.encrypt_password(login_key + key) + login_key + "#" + confirmation
    login(sock, raw, world_password)
    if "%l%" not in receive(file):
        raise RuntimeError("World server rejected the test buddy.")
    send(sock, f"%xt%s%j#js%-1%{penguin_id}%{login_key}%")
    while "%jr%" not in receive(file):
        pass
    time.sleep(1)
    send(sock, "%xt%s%j#jr%-1%100%560%330%")
    while True:
        room_reply = receive(file)
        if "%jr%" in room_reply and "%100%" in room_reply:
            break

    sock.setblocking(False)
    last_heartbeat = time.monotonic()
    print(f"{account['name']} is online in Town (room 100).", flush=True)
    while True:
        readable, _, _ = select.select([sock], [], [], 5)
        if readable:
            chunk = sock.recv(65536)
            if not chunk:
                raise RuntimeError("World server disconnected the test buddy.")
        if time.monotonic() - last_heartbeat >= 59:
            send(sock, "%xt%s%u#h%-1%")
            last_heartbeat = time.monotonic()


if __name__ == "__main__":
    main()
