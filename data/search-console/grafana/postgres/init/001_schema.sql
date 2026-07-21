CREATE TABLE IF NOT EXISTS search_console_daily (
    date date NOT NULL,
    snapshot_date date NOT NULL,
    clicks integer NOT NULL,
    impressions integer NOT NULL,
    ctr numeric NOT NULL,
    position numeric NOT NULL,
    PRIMARY KEY (date, snapshot_date)
);

CREATE TABLE IF NOT EXISTS search_console_queries (
    snapshot_date date NOT NULL,
    query text NOT NULL,
    clicks integer NOT NULL,
    impressions integer NOT NULL,
    ctr numeric NOT NULL,
    position numeric NOT NULL,
    PRIMARY KEY (snapshot_date, query)
);

CREATE TABLE IF NOT EXISTS search_console_pages (
    snapshot_date date NOT NULL,
    page text NOT NULL,
    clicks integer NOT NULL,
    impressions integer NOT NULL,
    ctr numeric NOT NULL,
    position numeric NOT NULL,
    PRIMARY KEY (snapshot_date, page)
);

CREATE TABLE IF NOT EXISTS search_console_countries (
    snapshot_date date NOT NULL,
    country text NOT NULL,
    clicks integer NOT NULL,
    impressions integer NOT NULL,
    ctr numeric NOT NULL,
    position numeric NOT NULL,
    PRIMARY KEY (snapshot_date, country)
);

CREATE TABLE IF NOT EXISTS search_console_devices (
    snapshot_date date NOT NULL,
    device text NOT NULL,
    clicks integer NOT NULL,
    impressions integer NOT NULL,
    ctr numeric NOT NULL,
    position numeric NOT NULL,
    PRIMARY KEY (snapshot_date, device)
);

CREATE TABLE IF NOT EXISTS search_console_search_appearance (
    snapshot_date date NOT NULL,
    search_appearance text NOT NULL,
    clicks integer NOT NULL,
    impressions integer NOT NULL,
    ctr numeric NOT NULL,
    position numeric NOT NULL,
    PRIMARY KEY (snapshot_date, search_appearance)
);
