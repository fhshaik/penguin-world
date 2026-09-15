# Base-game economy and direct trading

Penguin World includes an in-game Trading Post for exchanging the original game's wearable items, furniture, and coins. Click another penguin, open their player card, and press **TRADE**. The menu opens for that penguin; **F8** remains a keyboard shortcut for opening the general Trading Post.

## Trade flow

1. Both players sign in to the Trading Post with their game accounts.
2. One player invites the other, who accepts or declines.
3. Each player chooses items and enters a coin amount, then updates their offer.
4. Each player presses **Ready**. Any later offer change clears both Ready states.
5. When both players are ready, the offers lock for final review.
6. Each player presses **Confirm Trade**.
7. The server rechecks both offers and moves everything in one database transaction. If any check fails, nothing moves.

Direct trades have no fee. Offered coins and assets are reserved until the trade completes or is cancelled. A penguin can participate in only one active trade at a time.

## Base-game rules

- Ordinary unequipped clothing is tradable. A recipient cannot receive clothing they already own because the base game stores one copy of each wearable.
- Unplaced furniture copies are tradable up to the recipient's normal inventory limit.
- Penguin colors, award items, EPF items, tour rewards, treasure items, equipped clothing, and explicitly bound assets are blocked.
- This system does not include materials, crafting, generated item instances, marketplace listings, or The Wild.

Server owners can bind an additional asset without changing game data:

```sql
INSERT INTO economy_bound_asset(kind, asset_id, reason)
VALUES ('clothing', 1234, 'This event reward is account-bound.');
```

## Operation and security

The `economy` Docker service installs its additive PostgreSQL schema on startup and listens only inside the Docker network. nginx exposes it locally at `http://trade.localhost:8088`; the repository's default web port remains bound to `127.0.0.1`.

The original player-card interface is a compiled ActionScript 2 SWF. `build-client-patch.ps1` downloads the official portable JPEXS decompiler and Temurin Java runtime into ignored local folders, verifies the supported original `interface.swf`, injects the Trade action, recompiles it, and installs the local result. `world.ps1 play` runs this automatically when the patch is missing or stale. The public repository contains the patch source and builder, not Disney's compiled client.

Trading Post sessions expire after 12 hours. Raw passwords are never stored by the service. Receipts contain the final locked offer and stay in PostgreSQL for auditing. Old unfinished trades are cancelled when the service starts after 30 minutes of inactivity.

Run the end-to-end test against an active local stack:

```powershell
docker compose exec economy python /usr/src/economy/test_trade_flow.py
```

The test creates two temporary penguins, exercises item and coin reservations, changes an offer after Ready, confirms from both sides, verifies the transfer and receipt, and deletes its test data.
