# Penguin World

## Verified locally

The Flash client reaches the login screen. On September 14, 2026, a protocol check successfully created a test account, authenticated with the login server and Blizzard, and joined a spawn room. Core graphical gameplay was subsequently tested: login, map travel, walking, inventory, equipping a hat, and entering the Clothes Shop passed. See GAMEPLAY-TEST.md for findings and untested areas.

## Start and play

Open PowerShell in this folder:

```powershell
.\world.ps1 start
.\world.ps1 play
```

Alternatively, double-click Play Penguin World.cmd after starting the server. The game needs the local Electron client and a compatible Pepper Flash runtime; those binary dependencies are deliberately excluded from the public repository. A normal browser cannot run this Flash game.

Click another penguin and press **TRADE** on their in-game player card to open the two-player Trading Post for that penguin. Both players sign in there with their game accounts. It supports base-game wearables, furniture, and coins; see [ECONOMY.md](ECONOMY.md) for its rules and confirmation flow.

On first play, the launcher builds the small player-card patch from your local original `interface.swf`. It downloads JPEXS and a portable Temurin Java runtime into ignored local folders, then keeps the original and generated client files out of Git.

Create your own account (4-12 letters, numbers, or spaces):

```powershell
.\create-penguin.ps1 -Name 'YourPenguin'
```

The script asks for a password locally and does not save it. Accounts are active immediately, with a blue penguin and the server's default coins. No real email address or email service is required. Existing accounts cannot be overwritten by this command.

A SetupTest account was created for verification. Its generated password is in local-accounts/SetupTest.json (ignored by Git). Use your own account for normal play.

For an in-game trade test, create an ignored `local-accounts/TradeTest.json` file containing `player` and `buddy` objects with `name` and `password` fields. Then run `./world.ps1 trade-test`. This creates or refreshes both accounts, gives each a small tradable inventory, and keeps the buddy online in Town. Stop it with `docker compose --profile testing stop trade_bot`.

## Controls

```powershell
.\world.ps1 status
.\world.ps1 logs
.\world.ps1 backup
.\world.ps1 stop
```

The start command launches database, Redis, login, English Blizzard world, account website, economy, and web/media services. Docker Desktop must be running. The PC must remain awake while hosting.

Game progress lives in Docker volume penguin-world_penguin_data, outside OneDrive. Never remove that volume to troubleshoot. Backups go to backups/. Keep the .env file and local-accounts/ private.

## Friend access: not enabled yet

All web/game ports are bound to 127.0.0.1. Database and Redis ports are not published. Tailscale is installed and connected on this PC, but friends cannot connect to the game yet.

Before enabling access, identify the friends/devices that should be allowed in Tailscale. Then restrict access to those peers, bind only the Tailscale address for web (8088), login (16112), and Blizzard (19875), and update game/media/client addresses together. A private-network connection alone does not make the current localhost client work remotely. Do not forward router ports or expose the database.

Friends will each need a compatible client and a penguin account. Mac clients require their own compatible runtime; the included client is for Windows.

## Remaining content checks

Core room, interface, and game media are present. Some clothing archive downloads were interrupted earlier; individual clothing assets and all minigames have not been verified. Card-Jitsu Snow is not started by the control script.

After downloading media, restart the web service with `docker compose restart web` to regenerate the local environment configuration. Downloaded archives can overwrite that configuration with original server addresses.
