-- 0002_core: evidências de comunicação e de validação em campo (forja_core.db).
--
-- read_tests: cada TESTE SOMENTE LEITURA executado (sucesso ou falha), com o fingerprint da
-- configuração testada. A ativação da coleta de um driver real exige um teste bem-sucedido com o
-- mesmo fingerprint da configuração salva.
-- commissioning_*: sessão de comissionamento (cabeçalho editável enquanto aberta) e conferências
-- valor Forja x valor na tela do KCM. Conferência é evidência: só INSERT; correção = nova linha.
-- Tempo: INTEGER epoch ms UTC. JSON validado pelo domínio é a fonte da verdade do objeto.

CREATE TABLE read_tests (
    id           INTEGER PRIMARY KEY,
    equipment_id TEXT    NOT NULL,
    ts_ms        INTEGER NOT NULL,
    driver       TEXT    NOT NULL,
    final_stage  TEXT    NOT NULL,
    success      INTEGER NOT NULL CHECK (success IN (0, 1)),
    latency_ms   REAL,
    fingerprint  TEXT    NOT NULL,
    user         TEXT    NOT NULL DEFAULT '',
    result_json  TEXT    NOT NULL
) STRICT;

CREATE INDEX read_tests_eq ON read_tests (equipment_id, ts_ms DESC);

CREATE TRIGGER read_tests_no_update
BEFORE UPDATE ON read_tests
BEGIN
    SELECT RAISE(ABORT, 'read_tests e append-only: UPDATE recusado');
END;

CREATE TRIGGER read_tests_no_delete
BEFORE DELETE ON read_tests
BEGIN
    SELECT RAISE(ABORT, 'read_tests e append-only: DELETE recusado');
END;

CREATE TABLE commissioning_sessions (
    id           TEXT    NOT NULL,
    equipment_id TEXT    NOT NULL,
    created_ms   INTEGER NOT NULL,
    updated_ms   INTEGER NOT NULL,
    status       TEXT    NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    session_json TEXT    NOT NULL,
    PRIMARY KEY (id)
) STRICT, WITHOUT ROWID;

CREATE INDEX commissioning_sessions_eq ON commissioning_sessions (equipment_id, created_ms DESC);

-- Sessão encerrada não muda mais.
CREATE TRIGGER commissioning_sessions_closed_is_final
BEFORE UPDATE ON commissioning_sessions
WHEN OLD.status = 'CLOSED'
BEGIN
    SELECT RAISE(ABORT, 'sessao de comissionamento encerrada nao pode ser alterada');
END;

CREATE TRIGGER commissioning_sessions_no_delete
BEFORE DELETE ON commissioning_sessions
BEGIN
    SELECT RAISE(ABORT, 'sessao de comissionamento nao pode ser apagada');
END;

CREATE TABLE commissioning_checks (
    id         INTEGER PRIMARY KEY,
    session_id TEXT    NOT NULL REFERENCES commissioning_sessions (id) ON DELETE RESTRICT,
    ts_ms      INTEGER NOT NULL,
    tag        TEXT    NOT NULL,
    check_json TEXT    NOT NULL
) STRICT;

CREATE INDEX commissioning_checks_session ON commissioning_checks (session_id, ts_ms);

CREATE TRIGGER commissioning_checks_no_update
BEFORE UPDATE ON commissioning_checks
BEGIN
    SELECT RAISE(ABORT, 'commissioning_checks e append-only: UPDATE recusado');
END;

CREATE TRIGGER commissioning_checks_no_delete
BEFORE DELETE ON commissioning_checks
BEGIN
    SELECT RAISE(ABORT, 'commissioning_checks e append-only: DELETE recusado');
END;
