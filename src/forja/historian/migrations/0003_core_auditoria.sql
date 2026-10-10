-- 0003_core: cadeia de hash da trilha de auditoria (ADR 0014).
--
-- audit_chain: um elo por linha de audit_log gravada depois desta migração. O hash de cada elo é
-- sha256(hash do elo anterior + "|" + conteúdo canônico da linha). Alterar, apagar ou inserir
-- uma linha por fora do Forja (editando o arquivo do banco) quebra a conferência a partir dali.
-- Linhas anteriores a esta migração ficam fora da cadeia e são contadas à parte na conferência.
-- Append-only, como a própria trilha.

CREATE TABLE audit_chain (
    audit_id  INTEGER PRIMARY KEY REFERENCES audit_log (id) ON DELETE RESTRICT,
    prev_hash TEXT    NOT NULL,
    hash      TEXT    NOT NULL
) STRICT;

CREATE TRIGGER audit_chain_no_update
BEFORE UPDATE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain e append-only: UPDATE recusado');
END;

CREATE TRIGGER audit_chain_no_delete
BEFORE DELETE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain e append-only: DELETE recusado');
END;
