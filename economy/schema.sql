CREATE TABLE IF NOT EXISTS economy_session (
    token_hash CHAR(64) PRIMARY KEY,
    penguin_id INTEGER NOT NULL REFERENCES penguin(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS economy_session_penguin_idx
    ON economy_session (penguin_id, expires_at);

CREATE TABLE IF NOT EXISTS economy_trade (
    id UUID PRIMARY KEY,
    status VARCHAR(16) NOT NULL CHECK (status IN ('invited', 'open', 'locked', 'complete', 'cancelled')),
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS economy_trade_participant (
    trade_id UUID NOT NULL REFERENCES economy_trade(id) ON DELETE CASCADE,
    penguin_id INTEGER NOT NULL REFERENCES penguin(id) ON DELETE CASCADE,
    side SMALLINT NOT NULL CHECK (side IN (0, 1)),
    coins INTEGER NOT NULL DEFAULT 0 CHECK (coins >= 0),
    ready BOOLEAN NOT NULL DEFAULT false,
    confirmed BOOLEAN NOT NULL DEFAULT false,
    active BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (trade_id, penguin_id),
    UNIQUE (trade_id, side)
);

CREATE UNIQUE INDEX IF NOT EXISTS economy_one_active_trade_per_penguin
    ON economy_trade_participant (penguin_id) WHERE active;

CREATE TABLE IF NOT EXISTS economy_trade_asset (
    trade_id UUID NOT NULL,
    penguin_id INTEGER NOT NULL,
    kind VARCHAR(16) NOT NULL CHECK (kind IN ('clothing', 'furniture')),
    asset_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    PRIMARY KEY (trade_id, penguin_id, kind, asset_id),
    FOREIGN KEY (trade_id, penguin_id)
        REFERENCES economy_trade_participant(trade_id, penguin_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS economy_bound_asset (
    kind VARCHAR(16) NOT NULL CHECK (kind IN ('clothing', 'furniture')),
    asset_id INTEGER NOT NULL,
    reason VARCHAR(120) NOT NULL DEFAULT 'This item cannot be traded.',
    PRIMARY KEY (kind, asset_id)
);

CREATE TABLE IF NOT EXISTS economy_trade_receipt (
    trade_id UUID PRIMARY KEY REFERENCES economy_trade(id) ON DELETE CASCADE,
    snapshot JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION economy_check_coin_reservation() RETURNS trigger AS $$
DECLARE
    reserved INTEGER;
BEGIN
    IF current_setting('economy.transfer', true) = 'on' THEN
        RETURN NEW;
    END IF;
    SELECT COALESCE(SUM(tp.coins), 0) INTO reserved
      FROM economy_trade_participant tp
      JOIN economy_trade t ON t.id = tp.trade_id
     WHERE tp.penguin_id = NEW.id
       AND tp.active
       AND t.status IN ('open', 'locked');
    IF NEW.coins < reserved THEN
        RAISE EXCEPTION 'coins are reserved in an active trade';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS economy_protect_reserved_coins ON penguin;
CREATE TRIGGER economy_protect_reserved_coins
BEFORE UPDATE OF coins ON penguin
FOR EACH ROW EXECUTE FUNCTION economy_check_coin_reservation();

CREATE OR REPLACE FUNCTION economy_check_clothing_reservation() RETURNS trigger AS $$
BEGIN
    IF current_setting('economy.transfer', true) = 'on' THEN
        RETURN OLD;
    END IF;
    IF EXISTS (
        SELECT 1
          FROM economy_trade_asset ta
          JOIN economy_trade_participant tp
            ON tp.trade_id = ta.trade_id AND tp.penguin_id = ta.penguin_id
          JOIN economy_trade t ON t.id = ta.trade_id
         WHERE ta.penguin_id = OLD.penguin_id
           AND ta.kind = 'clothing'
           AND ta.asset_id = OLD.item_id
           AND tp.active
           AND t.status IN ('open', 'locked')
    ) THEN
        RAISE EXCEPTION 'item is reserved in an active trade';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS economy_protect_reserved_clothing ON penguin_item;
CREATE TRIGGER economy_protect_reserved_clothing
BEFORE DELETE ON penguin_item
FOR EACH ROW EXECUTE FUNCTION economy_check_clothing_reservation();

CREATE OR REPLACE FUNCTION economy_check_furniture_reservation() RETURNS trigger AS $$
DECLARE
    reserved INTEGER;
    remaining INTEGER;
BEGIN
    IF current_setting('economy.transfer', true) = 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    SELECT COALESCE(SUM(ta.quantity), 0) INTO reserved
      FROM economy_trade_asset ta
      JOIN economy_trade_participant tp
        ON tp.trade_id = ta.trade_id AND tp.penguin_id = ta.penguin_id
      JOIN economy_trade t ON t.id = ta.trade_id
     WHERE ta.penguin_id = OLD.penguin_id
       AND ta.kind = 'furniture'
       AND ta.asset_id = OLD.furniture_id
       AND tp.active
       AND t.status IN ('open', 'locked');
    remaining := CASE WHEN TG_OP = 'DELETE' THEN 0 ELSE NEW.quantity END;
    IF remaining < reserved THEN
        RAISE EXCEPTION 'furniture is reserved in an active trade';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS economy_protect_reserved_furniture ON penguin_furniture;
CREATE TRIGGER economy_protect_reserved_furniture
BEFORE UPDATE OF quantity OR DELETE ON penguin_furniture
FOR EACH ROW EXECUTE FUNCTION economy_check_furniture_reservation();
