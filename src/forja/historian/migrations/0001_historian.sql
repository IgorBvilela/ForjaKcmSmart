-- 0001_historian: tabelas do historian (forja_historian.db).
--
-- Convencoes (ver forja.historian.queries):
--   * tempo: INTEGER epoch ms UTC;
--   * quality: INTEGER pelo mapa fixo QUALITY_CODE (quanto maior, pior; MAX() = pior do bucket);
--   * value NULL = sem valor (COMM_ERROR). STALE nunca vira linha.
--   * GAP = bucket sem linha. Nunca interpolado.
-- Nada aqui e especifico de equipamento: equipment_id e tag sao conteudo.
-- journal_mode/synchronous sao definidos na abertura da conexao (PRAGMA nao entra em transacao).

CREATE TABLE samples (
    equipment_id TEXT    NOT NULL,
    tag          TEXT    NOT NULL,
    ts_utc_ms    INTEGER NOT NULL,
    value        REAL,
    quality      INTEGER NOT NULL,
    source       TEXT    NOT NULL,
    raw          BLOB,
    reason_pt    TEXT,
    PRIMARY KEY (equipment_id, tag, ts_utc_ms)
) STRICT, WITHOUT ROWID;

-- Ultimo valor OBSERVADO por par (equipment_id, tag), atualizado em toda escrita,
-- mesmo quando o store-on-change nao grava linha em samples. Tambem e o registro
-- de pares conhecidos usado por rollups e retencao (evita varrer samples).
CREATE TABLE samples_latest (
    equipment_id TEXT    NOT NULL,
    tag          TEXT    NOT NULL,
    ts_utc_ms    INTEGER NOT NULL,
    value        REAL,
    quality      INTEGER NOT NULL,
    source       TEXT    NOT NULL,
    raw          BLOB,
    reason_pt    TEXT,
    PRIMARY KEY (equipment_id, tag)
) STRICT, WITHOUT ROWID;

-- Agregado por minuto fechado, calculado a partir de samples.
-- n_good = amostras com valor utilizavel (GOOD/SIMULATED/UNCERTAIN e value NOT NULL);
-- min/max/avg/first/last consideram so essas. worst_quality = MAX(quality).
CREATE TABLE samples_agg_1m (
    equipment_id    TEXT    NOT NULL,
    tag             TEXT    NOT NULL,
    bucket_start_ms INTEGER NOT NULL,
    n               INTEGER NOT NULL,
    n_good          INTEGER NOT NULL,
    n_comm_error    INTEGER NOT NULL,
    n_bad           INTEGER NOT NULL,
    min             REAL,
    max             REAL,
    avg             REAL,
    first           REAL,
    last            REAL,
    worst_quality   INTEGER NOT NULL,
    PRIMARY KEY (equipment_id, tag, bucket_start_ms)
) STRICT, WITHOUT ROWID;

-- Agregado por hora fechada, calculado a partir de samples_agg_1m (avg ponderado por n_good).
CREATE TABLE samples_agg_1h (
    equipment_id    TEXT    NOT NULL,
    tag             TEXT    NOT NULL,
    bucket_start_ms INTEGER NOT NULL,
    n               INTEGER NOT NULL,
    n_good          INTEGER NOT NULL,
    n_comm_error    INTEGER NOT NULL,
    n_bad           INTEGER NOT NULL,
    min             REAL,
    max             REAL,
    avg             REAL,
    first           REAL,
    last            REAL,
    worst_quality   INTEGER NOT NULL,
    PRIMARY KEY (equipment_id, tag, bucket_start_ms)
) STRICT, WITHOUT ROWID;

-- Log de comunicacao (conectou, caiu, timeout, reconectou...). detail_json = JSON texto.
CREATE TABLE comm_log (
    id           INTEGER PRIMARY KEY,
    ts_utc_ms    INTEGER NOT NULL,
    equipment_id TEXT    NOT NULL,
    level        TEXT    NOT NULL,
    kind         TEXT    NOT NULL,
    message_pt   TEXT    NOT NULL,
    detail_json  TEXT    NOT NULL DEFAULT '{}'
) STRICT;

CREATE INDEX comm_log_eq_ts ON comm_log (equipment_id, ts_utc_ms);
CREATE INDEX comm_log_ts ON comm_log (ts_utc_ms);

-- Marca d'agua dos rollups: inicio do primeiro bucket AINDA NAO consolidado.
-- A retencao nunca apaga bruto com ts >= watermark de agg_1m.
CREATE TABLE rollup_state (
    name         TEXT    NOT NULL,
    watermark_ms INTEGER NOT NULL,
    PRIMARY KEY (name)
) STRICT, WITHOUT ROWID;
