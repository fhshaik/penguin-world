# Penguin World project context

## Current scope

Penguin World is a private Club Penguin world for a small group of friends. It currently uses Solero Wand, Houdini, Dash, PostgreSQL, Redis, an nginx media server, and a bundled Electron/Flash client. Local graphical gameplay has been verified through login, joining Blizzard, room loading, walking, map travel, inventory display, equipping an item, and entering the Clothes Shop.

Friend access has not been enabled. Published ports remain bound to `127.0.0.1`. Tailscale is the intended private transport; database and Redis ports should never be exposed.

## Client direction

Keep the Flash client for the original island while it remains the fastest route to authentic gameplay. Large original features may later use Phaser 3 and TypeScript in a separate HTML5 client, joined through a short-lived server-issued handoff token. A full client migration is not currently planned.

The proposed procedurally generated area called The Wild is deliberately out of the current discussion and implementation scope.

## Economy and direct trading concept

The desired trade screen shows both players side by side. Each player can offer owned items, coins, or both.

The intended flow is:

1. One player invites another player to trade.
2. Each player adds or removes items and enters a coin amount.
3. Each presses Ready.
4. Changing either offer clears both Ready states.
5. When both are ready, both offers lock and each player sees a final review.
6. Each presses Confirm Trade.
7. The server revalidates ownership, balances, item eligibility, capacity, and the exact locked offer version.
8. The server transfers both sides in one database transaction and returns a receipt.

Items and coins are reserved while offered so they cannot be spent, equipped, placed, listed, or offered elsewhere. Disconnecting or failing any validation cancels the entire trade without a partial transfer.

Suggested item states are tradable, bound, and temporarily locked. Ordinary materials may stack. Rare or crafted items may eventually have unique owned-copy IDs, creator attribution, quality, and serial numbers. Direct friend trades should initially have no fee.

No trading implementation has been written yet.

## Public repository policy

The repository contains source and configuration examples only. Do not commit live `.env` files, account credentials, database backups, generated media archives, `node_modules`, or the Flash runtime DLL. Club Penguin names and artwork belong to Disney; upstream media submodules and locally downloaded assets are not covered by this repository's MIT license.
