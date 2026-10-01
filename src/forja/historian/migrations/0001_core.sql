-- 0001_core: tabelas do core store (forja_core.db).
--
-- Eventos e diagnosticos sao guardados como JSON validado pelo Pydantic (model_dump_json),
-- mais colunas indexadas para as consultas reais. O JSON e a fonte da verdade do objeto;
-- as colunas sao copia para indice. Tempo: INTEGER epoch ms UTC.
-- PRAGMA foreign_keys=ON e definido na abertura da conexao.

CREATE TABLE events (
    id           TEXT    NOT NULL,
    equipment_id TEXT    NOT NULL,
    type         TEXT    NOT NULL,
    status       TEXT    NOT NULL,
    severity     TEXT    NOT NULL,
    start_ms     INTEGER NOT NULL,
    end_ms       INTEGER,
    dedupe_key   TEXT    NOT NULL,
    rule_id      TEXT    NOT NULL,
    updated_ms   INTEGER NOT NULL,
    event_json   TEXT    NOT NULL,
    PRIMARY KEY (id)
) STRICT, WITHOUT ROWID;

CREATE INDEX events_eq_start ON events (equipment_id, start_ms DESC);
CREATE INDEX events_start ON events (start_ms DESC);
CREATE INDEX events_type ON events (type, start_ms DESC);
-- find_open: so eventos abertos (end_ms IS NULL); indice parcial fica pequeno.
CREATE INDEX events_open_dedupe ON events (equipment_id, dedupe_key) WHERE end_ms IS NULL;

CREATE TABLE diagnoses (
    diagnosis_id   TEXT    NOT NULL,
    event_id       TEXT    NOT NULL REFERENCES events (id) ON DELETE RESTRICT,
    equipment_id   TEXT    NOT NULL,
    generated_ms   INTEGER NOT NULL,
    schema_version TEXT    NOT NULL,
    engine_version TEXT    NOT NULL,
    diagnosis_json TEXT    NOT NULL,
    PRIMARY KEY (diagnosis_id)
) STRICT, WITHOUT ROWID;

CREATE INDEX diagnoses_event ON diagnoses (event_id, generated_ms DESC);
CREATE INDEX diagnoses_eq ON diagnoses (equipment_id, generated_ms DESC);

-- Trilha de auditoria: so INSERT. UPDATE/DELETE abortam por trigger.
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    ts_ms       INTEGER NOT NULL,
    user        TEXT    NOT NULL,
    action      TEXT    NOT NULL,
    entity_type TEXT    NOT NULL,
    entity_id   TEXT    NOT NULL,
    before_json TEXT,
    after_json  TEXT,
    reason_pt   TEXT    NOT NULL DEFAULT ''
) STRICT;

CREATE INDEX audit_log_ts ON audit_log (ts_ms DESC);
CREATE INDEX audit_log_entity ON audit_log (entity_type, entity_id, ts_ms DESC);

CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log e append-only: UPDATE recusado');
END;

CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log e append-only: DELETE recusado');
END;
