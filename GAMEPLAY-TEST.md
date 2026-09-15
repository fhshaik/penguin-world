# Graphical gameplay test — September 14, 2026

Tested using the bundled Windows Flash client with the local SetupTest account.

## Passed

- Entered the generated account credentials in the graphical login screen.
- Selected Blizzard and loaded the outdoor ski-hill room with the penguin visible.
- Advanced the first-time tutorial and opened the island map.
- Travelled through the map to Town; buildings and animations rendered.
- Clicked a destination and observed the penguin walk from the lower snow area to the town plaza.
- Opened the player card/inventory; it showed 500 coins and starter items.
- Equipped the red/white starter hat; it appeared on both the player card and room avatar.
- Confirmed the database saved head item 1285 and retained the 500-coin balance.
- Walked through the Clothes Shop entrance and loaded its interior.
- No game-server exceptions appeared during the test.

## Issues observed

The following HTTP requests returned 404:

- POST /social/autocomplete/v2/search/clientRules on the media host.
- POST /play//web_service/activate_player.php on the media host.

These did not block the tested login, movement, map, inventory, or room transitions. Chat functionality has not been verified; the bottom bar did not show a normal text entry field during this test. The activation request's effect beyond the tested active account is unknown.

## Not tested

Two-player synchronization, friend/VPN access, minigames, purchases, all clothing/media, and persistence across a full logout/restart. The equipped item was checked directly in the database, not by relogging.

The client remains open with SetupTest inside the Clothes Shop.
