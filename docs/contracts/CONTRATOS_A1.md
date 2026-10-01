# Contratos da Fase A1 — núcleo do Forja KCM Intelligence

Este documento é o acordo entre os módulos. Quem implementa um módulo lê isto inteiro, lê `src/forja/domain/**`
(já pronto; **não alterar**), `src/forja/config/**` e `src/forja/infra/**` (já prontos; **não alterar**) e entrega
apenas os arquivos do seu bloco. Se precisar de mudança no domínio, **não faça**: registre o pedido na sua saída
e contorne. O integrador aplica.

## Regras que valem para todo módulo

- Read-only por construção. Nenhum método, rota, comando ou botão que altere o KCM. Driver só tem
  `connect/disconnect/read/health/capabilities` (a base `ReadOnlyDriverBase` recusa o resto na definição).
- PLC e SCADA não são fonte. Nada específico da GTEX em código (IP, register, assembly, KGR, bit, alarme, firmware,
  threshold). Valores vêm de `config/` e `knowledge/`; o desconhecido é o literal `UNKNOWN`.
- Textos para o usuário em português do Brasil (`*_pt`). Código interno (`BELT_LOAD_LOW`) nunca é título.
- `COMM_ERROR` = a tentativa atual falhou. `STALE` = o último valor ficou velho (estado derivado, por relógio
  monotônico, **nunca gravado como linha** no historian). Não confundir.
- Nunca interpolar. Buraco de leitura é `value=None` (GAP). Nunca ligar pontos sem leitura.
- Tempo: `datetime` com `tzinfo=UTC` em memória; no SQLite, `INTEGER` epoch ms UTC. Relógio só via a porta `Clock`
  (`forja.infra.clock.SystemClock` / `FakeClock`); proibido `time.time()`/`datetime.now()` direto no núcleo.
- Dados `SIMULATED` nunca entram em baseline, early warning estatístico ou casos como evidência de campo.
- Sem rede nos testes (só `127.0.0.1`). Sem `yaml.load`; só `yaml.safe_load` (já em `forja.config.loader`).
- Python 3.14 (`.venv\Scripts\python.exe`). Rodar: `.\.venv\Scripts\python.exe -m pytest tests/<seus testes> -q`.
  Lint: `.\.venv\Scripts\python.exe -m ruff check src tests` e `ruff format`. Tipos: `mypy` só no que você entregou.
- Nenhum módulo faz commit. Nenhum módulo mexe em arquivo de outro bloco. Nada sai da máquina.
- Pydantic v2 (`extra="forbid"`), `asyncio` para I/O, `sqlite3` da stdlib (sem ORM).

## Vocabulário já pronto (em `forja.domain`)

`Quality`, `worst()`, `EvidenceLevel`, `KnowledgeState`, `UNKNOWN`, `TAGS`/`get_tag()`, `EquipmentProfile`,
`CommunicationConfig`, `Mapping`/`MappingEntry`/`DataType`/`Endianness`/`Scale`, `Sample`, `SampleBatch`,
`ReadPlan`/`ReadBlock`/`RawFrame`/`RawBlock`, `ReadOnlyDriverBase`, `DriverHealth`, `DriverCapabilities`,
`DriverSupportState`, `ConnectionState`, `ReadTestStage`, `EquipmentRuntimeStatus`, `Event`, `EventContext`,
`WhatChangedItem`, `TimelinePoint`, `SourceRef`, `Severity`, `Diagnosis` (+ `DiagnosisSummary`, `EvidenceItem`,
`Hypothesis`, `NextCheck`, `Caveat`, `EvidenceSummary`, `MANDATORY_CAVEAT_PT`, `OFFICIAL_SECTIONS_PT`),
`AlarmCatalog`/`AlarmKey`/`AlarmDefinition`, `StopByCatalog`/`StopByClass`, portas `HistorianRepository`,
`EventRepository`, `DiagnosisRepository`, `Clock`, `EventBus` e tópicos `TOPIC_SAMPLES`, `TOPIC_CONNECTION`,
`TOPIC_EVENTS`, `TOPIC_DIAGNOSES`. Config: `forja.config.ConfigStore(paths).load_all()` com `.config`, `.profiles`,
`.mappings`, `.alarms`, `.stop_by`, `.mapping_for(id)`. Infra: `AsyncBus`, `SystemClock`, `FakeClock(advance)`.

Perfis-semente: `GTEX_PHA_PO_BASE` (simulador, cenário NORMAL_OPERATION), `EXEMPLO_BARRILHA` (BELTLOAD_LOW),
`EXEMPLO_KCM_03` (COMMUNICATION_FAILURE). Mapping do simulador: `simulator_wbf` (`sim:<tag>`).

---

## Bloco 1 — Drivers e normalização (dono: Sexta-feira)

Arquivos: `src/forja/drivers/{__init__,registry,support}.py`, `src/forja/drivers/simulator/{__init__,driver,physics_wbf,scenarios,controls}.py`,
`src/forja/normalization/{__init__,plan,decoder,normalizer,quality_policy}.py`,
testes em `tests/unit/test_simulator_*.py`, `tests/unit/test_decoder.py`, `tests/unit/test_normalizer.py`,
`tests/unit/test_registry.py`, `tests/contract/test_readonly_driver_contract.py`.

```python
# forja.drivers.registry
class DriverSupportInfo(BaseModel): name: str; state: DriverSupportState; library: str = ""; version: str = ""; reason_pt: str = ""
class DriverRegistry:
    def register(self, name: str, factory: Callable[[EquipmentProfile, Mapping, Clock], ReadOnlyDriverBase], probe: Callable[[], DriverSupportInfo]) -> None
    def create(self, profile: EquipmentProfile, mapping: Mapping, clock: Clock) -> ReadOnlyDriverBase   # UnsupportedDriver se nome desconhecido ou UNSUPPORTED
    def support(self) -> dict[str, DriverSupportInfo]
    def names(self) -> list[str]
def build_default_registry() -> DriverRegistry
# registra: "simulator" AVAILABLE; "modbus_tcp" e "ethernet_ip" UNSUPPORTED com reason_pt "Disponível na fase J/K; requer configuração de campo".
# create() para esses dois levanta UnsupportedDriver. NUNCA marcar AVAILABLE sem driver funcional.

# forja.drivers.simulator.scenarios
class Scenario(str, Enum): NORMAL_OPERATION, BELTLOAD_LOW, RATE_LOW, ENCODER_FAILURE, SFT_FAILURE, DRIVE_COMMAND_HIGH, INT_CHANNEL_DEGRADED, COMMUNICATION_FAILURE, STOP_NORMAL
# exatamente 9. SEM REFILL. Cada um com title_pt e description_pt (texto simples da spec §39-41).

# forja.drivers.simulator.controls
class SimulatorControls(BaseModel): equipment_id; scenario: Scenario; time_scale: float = 1.0; seed: int; overrides: dict[str, float] (sliders: setpoint, mass_flow, drive_command, rpm, belt_load, net_weight, int_channel_pct); scenario_started_mono_ns: int | None
class SimulatorControlRegistry: get(equipment_id) -> SimulatorControls; set_scenario(equipment_id, scenario, clock); set_overrides(...); clear_overrides(...)
SIMULATOR_CONTROLS = SimulatorControlRegistry()   # singleton de processo; a API usa isto, nunca o driver.

# forja.drivers.simulator.physics_wbf
class WbfModel: estado a partir de (scenario, t_elapsed_s, seed, refs: reference_values do perfil, overrides) -> dict[tag, float|int]
# Mass Flow ≈ Belt Load × Belt Speed (DM §8.1). Controlador simples: drive_command sobe quando belt_load cai para manter vazão.
# BELTLOAD_LOW: belt_load decai até ~45% da referência em ~60 s; drive_command sobe; mass_flow cai pouco (~2%); alarm_code 56, alarm_active 1 após persistência.
# ENCODER_FAILURE: machine_state RUN, drive_command > 0, rpm = 0 (a partir de t=20 s).
# RATE_LOW: mass_flow 15–25% abaixo do setpoint, drive_command no teto.
# SFT_FAILURE: sft_status raw muda (ex.: 0x00000181 -> 0x00000183 como valores SIMULADOS), net_weight ruidoso, alarm_code 8 (SIMULADO; catálogo marca HYPOTHESIS).
# DRIVE_COMMAND_HIGH: drive_command 88–96% com vazão ~setpoint.  INT_CHANNEL_DEGRADED: int_channel_pct cai de ~95 para ~40 (limiar SIMULATED, nunca limite do KCM).
# COMMUNICATION_FAILURE: read() levanta DriverTimeout (sem valores).  STOP_NORMAL: machine_state STOP, mass_flow 0, rpm 0, drive 0, stop_by "Stop Input" (código inteiro simulado, catálogo diz UNKNOWN).
# machine_state: 0 STOP, 1 RUN, 2 ALARM (codificação do SIMULADOR, documentada no código). Determinístico com seed; ruído pequeno.

# forja.drivers.simulator.driver
class SimulatorDriver(ReadOnlyDriverBase): name = "simulator"
#   read(plan) -> RawFrame com um RawBlock por bloco do plano; payload = dict[tag, valor] (já em unidade de engenharia); latency_ms pequena e determinística.
#   capabilities(): protocol "simulator", AVAILABLE, read_areas ("sim",).  health(): connected, last_ok_utc, consecutive_errors.

# forja.normalization.plan
class ReadPlanCompiler: compile(profile, mapping) -> ReadPlan   # simulator: 1 bloco "sim" com todas as readable_entries; modbus: coalescer contíguos por área (preparar, não precisa de driver); eip: 1 bloco por entrada.
# forja.normalization.decoder
def decode(words: Sequence[int] | bytes, datatype: DataType, endianness: Endianness) -> float | int | bool | bytes   # bitfield -> int; string -> bytes; levantar ValueError em tamanho errado
def encode(value, datatype, endianness) -> bytes    # para testes round-trip (hypothesis) e fakes
# forja.normalization.normalizer
class Normalizer: normalize(frame: RawFrame, profile, mapping, clock: Clock) -> SampleBatch
#   qualidade por entrada: entry.quality_for(driver); valid_min/valid_max fora da faixa -> BAD com reason_pt; raw preservado quando payload é bytes/words;
#   tag no plano sem valor no frame -> Sample COMM_ERROR (value None, reason_pt "sem leitura").
def comm_error_batch(profile, mapping, clock, reason_pt) -> SampleBatch   # usado pela aquisição quando read() falha
```

Testes mínimos (≥ 30): 9 cenários existem e REFILL não; determinismo por seed; BELTLOAD_LOW reduz belt_load e sobe drive_command; ENCODER_FAILURE rpm 0 com drive > 0; COMMUNICATION_FAILURE levanta DriverTimeout; decode/encode round-trip por datatype × 4 endianness (hypothesis); normalizer marca SIMULATED, BAD fora de faixa, COMM_ERROR em tag ausente; registry recusa classe com write e marca modbus/eip UNSUPPORTED; contrato: superfície pública de toda classe de driver registrada == `{name, connect, disconnect, read, health, capabilities}`; AST em `src/forja/drivers/**` sem nomes `write*`, `set_*`, `reset`, `tare`, `span`, `calib` (lista em `tests/contract/forbidden_tokens.py`).

---

## Bloco 2 — Historian e core store SQLite (dono: Karen)

Arquivos: `src/forja/historian/{__init__,sqlite,writer,queries,rollups,retention,backup,core_store,migrate}.py`,
`src/forja/historian/migrations/0001_historian.sql`, `src/forja/historian/migrations/0001_core.sql`,
testes em `tests/integration/test_historian_*.py`, `tests/integration/test_core_store.py`, `tests/integration/test_backup_restore.py`.

```python
# forja.historian.sqlite
class SqliteHistorian:   # implementa HistorianRepository
    def __init__(self, db_path: Path, config: HistorianConfig, clock: Clock) -> None
    async def open(self) -> None; async def close(self) -> None
    async def write(samples) -> None            # lote; store-on-change opcional (deadband por tag + amostra forçada a cada forced_sample_every_s); COMM_ERROR grava value NULL; STALE nunca é gravado (ignorar se vier)
    async def latest(equipment_id, tags=None) -> dict[str, Sample]
    async def range(equipment_id, tag, start, end, max_points=2000) -> Series   # escolhe raw | 1m | 1h pelo tamanho da janela e orçamento; buckets vazios -> value None (GAP); nunca interpola; quality do bucket = pior
    async def count(equipment_id=None) -> int
    async def log_comm(entry) -> None; async def comm_log(equipment_id, since, limit) -> list[CommLogEntry]
    async def run_rollups(self) -> dict[str, int]      # agg 1m a partir do bruto (minutos fechados, recalcula últimos 5), agg 1h a partir de 1m
    async def run_retention(self) -> dict[str, int]    # bruto > raw_retention_days (SIMULATED > raw_simulated_retention_days), agg_1m > rollup_1m_retention_days; nunca apaga bruto mais novo que a marca d'água de agregação
    async def stats(self) -> dict[str, Any]            # tamanho em bytes, linhas por tabela, última amostra
    async def backup(self, dest_dir: Path) -> Path     # Connection.backup() paginado; devolve caminho do arquivo
# Tabelas (STRICT, WAL, synchronous=NORMAL): samples(equipment_id TEXT, tag TEXT, ts_utc_ms INTEGER, value REAL NULL, quality INTEGER, source TEXT, raw BLOB NULL, PRIMARY KEY(equipment_id, tag, ts_utc_ms)) WITHOUT ROWID;
# samples_agg_1m / samples_agg_1h (equipment_id, tag, bucket_start_ms, n, n_good, n_comm_error, n_bad, min, max, avg, first, last, worst_quality) WITHOUT ROWID; comm_log; schema_migrations(version, name, applied_at_ms, checksum).
# Uma conexão escritora em thread dedicada (asyncio.to_thread ou thread própria com fila); leitores usam conexão própria read-only. PRAGMA foreign_keys=ON no core.

# forja.historian.core_store
class SqliteCoreStore:   # implementa EventRepository e DiagnosisRepository; guarda JSON validado (events_json, diagnoses_json) + colunas indexadas (equipment_id, start_ms, status, dedupe_key, type)
    def __init__(self, db_path: Path, clock: Clock) -> None
    async def open(self) -> None; async def close(self) -> None
    # EventRepository: save/get/list/find_open ; DiagnosisRepository: save/get_for_event/list
    async def audit(self, user: str, action: str, entity_type: str, entity_id: str, before: dict | None, after: dict | None, reason_pt: str = "") -> None   # append-only (triggers RAISE(ABORT) em UPDATE/DELETE)
    async def audit_list(self, limit: int = 200) -> list[dict]
# forja.historian.backup
async def backup_all(historian, core, paths: ForjaPaths, dest_dir: Path | None = None) -> BackupManifest   # core via VACUUM INTO, historian via backup API; manifest.json com sha256 e contagens; verificação PRAGMA integrity_check
async def restore_all(manifest_dir: Path, paths: ForjaPaths) -> None   # só com serviço parado; valida checksums antes
# forja.historian.migrate
def migrate(conn: sqlite3.Connection, migrations_dir: Path, kind: Literal["historian","core"]) -> list[str]   # só para frente; checksum; recusa versão maior que a do app
```

Testes mínimos (≥ 25): write/latest; range com buraco devolve GAP e `gap_count`; range escolhe 1m para 24 h; rollup 1m correto (n, avg, worst); retention apaga só o que passou do prazo (FakeClock) e preserva agregados; SIMULATED com retenção curta; store-on-change reduz linhas e força amostra a cada 60 s; STALE não é gravado; comm_log; core store save/get/list/find_open; audit append-only (UPDATE/DELETE levantam IntegrityError); backup → apagar → restore → mesmas contagens; migração idempotente e recusa downgrade.

---

## Bloco 3 — Aquisição, estado ao vivo e serviço (dono: Stark)

Arquivos: `src/forja/acquisition/{__init__,manager,loop,state,backoff,watchdog,live,test_read}.py`,
`src/forja/service/{__init__,container,runner}.py`,
testes em `tests/integration/test_acquisition_isolation.py`, `tests/unit/test_backoff.py`, `tests/unit/test_live_stale.py`, `tests/integration/test_watchdog.py`, `tests/integration/test_reload.py`, `tests/integration/test_read_test.py`.

```python
# forja.service.container
@dataclass
class Container: paths: ForjaPaths; store: ConfigStore; clock: Clock; bus: AsyncBus; registry: DriverRegistry; historian: HistorianRepository; events_repo: EventRepository; diagnoses_repo: DiagnosisRepository; manager: "EquipmentManager"; rule_engine: "RuleEngine"; diagnosis_engine: "DiagnosisEngine"; started_at_utc: datetime
# forja.service.runner
async def build_container(paths: ForjaPaths | None = None, clock: Clock | None = None) -> Container   # monta tudo: ConfigStore.load_all, SqliteHistorian.open, SqliteCoreStore.open, build_default_registry, RuleEngine, DiagnosisEngine, EquipmentManager; liga RuleEngine ao bus (TOPIC_SAMPLES -> eventos) e DiagnosisEngine (TOPIC_EVENTS OPEN -> diagnóstico salvo e publicado em TOPIC_DIAGNOSES); jobs periódicos (rollups a cada 60 s, retenção a cada 3600 s) com clock.sleep
async def start(container) -> None; async def stop(container, timeout_s: float = 10) -> None   # parada graciosa: para loops, flush, fecha bancos
# Os nomes RuleEngine/DiagnosisEngine vêm do Bloco 4: `forja.events.engine.RuleEngine(rules, alarms, stop_by, clock, pre_window_s, post_window_s, buffer_s)` com `async def on_batch(batch) -> list[EventTransition]`
# e `forja.diagnostics.engine.DiagnosisEngine(library, clock)` com `def diagnose(event: Event) -> Diagnosis`. Se o Bloco 4 ainda não existir ao testar, use stubs locais nos testes.

# forja.acquisition.manager
class EquipmentManager:
    def __init__(self, store: ConfigStore, registry: DriverRegistry, historian: HistorianRepository, bus: AsyncBus, clock: Clock) -> None
    async def start_all(self) -> None; async def stop_all(self, timeout_s: float = 5) -> None
    async def start(self, equipment_id) -> None; async def stop(self, equipment_id) -> None; async def reload(self, equipment_id) -> None   # recarrega perfil+mapping daquele equipamento sem tocar nos demais
    def status(self, equipment_id) -> EquipmentRuntimeStatus; def statuses(self) -> dict[str, EquipmentRuntimeStatus]
    def live(self, equipment_id) -> LiveSnapshot          # {tag: Sample} já com STALE aplicado + conexão + idade
    async def test_read(self, profile: EquipmentProfile, mapping: Mapping) -> ReadTestResult   # driver descartável; devolve estágios (ReadTestStage) e valores lidos; NUNCA escreve
# forja.acquisition.loop
class EquipmentLoop: task asyncio por equipamento: connect -> a cada poll_interval_s read(plan) -> Normalizer -> publish(TOPIC_SAMPLES, batch) + historian.write; exceção de driver -> comm_error_batch + ConnectionState.ERROR + backoff; nunca escapa; conta reconnects; publica ConnectionChanged em TOPIC_CONNECTION.
# forja.acquisition.live
class LiveState / StaleMonitor: guarda último Sample por tag; is_stale = (clock.monotonic_ns - último_ok_mono) > stale_after_s; ao expor, troca quality para STALE SEM alterar o valor nem o ts original (idade visível). Nunca grava STALE no historian.
# forja.acquisition.backoff
class Backoff: exponencial base 1 s, fator 2, teto 60 s, jitter ±20%, reset() ao conectar; next_delay() determinístico com random.Random(seed) injetável.
# forja.acquisition.watchdog
class Watchdog: a cada tick verifica último tick de cada loop; sem tick > 3 × poll_interval -> cancela e recria a task; restart_count++.
# forja.acquisition.test_read
class ReadTestResult(BaseModel): stages: list[tuple[ReadTestStage, datetime, str]]; final: ReadTestStage; values: dict[str, Sample]; latency_ms: float | None; error_pt: str | None
```

Testes mínimos (≥ 20): 3 simuladores (um em COMMUNICATION_FAILURE) rodando com FakeClock: os saudáveis mantêm samples; o falho mostra COMM_ERROR e, após stale_after_s, LiveState mostra STALE com valor antigo intacto; driver que levanta exceção a cada read por 100 ciclos não derruba os outros nem o processo; backoff cresce e respeita o teto; watchdog reinicia task travada e incrementa restart_count; reload troca cenário/mapping de um sem parar os outros; test_read devolve READ_OBTAINED com simulador e TIMEOUT com cenário COMMUNICATION_FAILURE; stop_all é gracioso.

---

## Bloco 4 — Eventos, diagnóstico e conhecimento (dono: Sexta-feira-2)

Arquivos: `src/forja/events/{__init__,rules,conditions,prewindow,engine,what_changed,memory_store}.py`,
`src/forja/diagnostics/{__init__,library,engine,translator,schema_v1}.py`,
sementes `config/rules/R-BELTLOAD-001.yaml`, `R-SPEED-001.yaml`, `R-RATE-001.yaml`, `R-DRIVE-001.yaml`, `R-COMM-001.yaml`, `R-STOP-001.yaml`,
`config/alarms/coperion_ktron__kcm__wbf__UNKNOWN.yaml` (56 = BELTLOAD LOW, FIELD_OBSERVED, source "foto da tela do KCM, GTEX, 09/2026"),
`config/alarms/coperion_ktron__kcm__UNKNOWN__UNKNOWN.yaml` (06, 07, 08, 09, 13, 16, 17, 39, 43, 44, 45, 46, 47 como HYPOTHESIS, source "referência técnica sem documento identificado"),
`config/stop_by/kcm_stop_by.yaml` (Board Reset, Loc Display, Ext Display, ALS Input, DginRunEna, Stop Input, MDU DrvEna, Zero SP, Emptying, Interlock, Calib, Tare, FeedFactBad, MDUInterlock, MDU Alarm — todos UNKNOWN; Calib/Tare com note_pt "candidato a PROCEDURE, decisão do chefe"),
`knowledge/diagnostics/{belt_load_low,speed_feedback,rate_low,drive_command_high,comm_degraded,sft_status,stop_normal}.yaml`,
`knowledge/cases/2026-09_gtex_pha_po_base_velocidade.yaml`, `knowledge/i18n/pt_BR.yaml`,
testes em `tests/unit/test_rules_*.py`, `tests/unit/test_what_changed.py`, `tests/unit/test_diagnosis_engine.py`, `tests/contract/test_diagnosis_schema_v1.py`, `tests/unit/test_alarm_catalog.py`, `tests/unit/test_stop_by.py`.

```python
# forja.events.rules
class Condition(BaseModel): tag: str; op: Literal["gt","lt","between","drop_pct_over_window","rise_pct_over_window","rate_of_change","equals","changed","quality_is","persists_for"]; value: float | str | None; value2: float | None; ref_tag: str | None; window_s: int | None; persist_s: int | None
class Rule(BaseModel): id: str (R-XXX-000); version: int; internal_code: str; title_pt: str; severity: Severity; conditions: list[Condition] (AND); allowed_qualities: list[Quality]; cooldown_s: int; close_when_clear_for_s: int; diagnosis_ref: str; sources: list[SourceRef]; summary_template_pt: str
def load_rules(dir_: Path) -> list[Rule]
# forja.events.engine
class RuleEngine:
    def __init__(self, rules, alarms: AlarmCatalog, stop_by: StopByCatalog, clock: Clock, pre_window_s=60, post_window_s=30, buffer_s=180) -> None
    async def on_batch(self, batch: SampleBatch) -> list[EventTransition]   # determinístico; só qualidades counts_for_rules; dedupe_key = f"{equipment_id}:{rule.id}"; OPEN com EventContext (pre_samples da janela, what_changed, timeline com 'o que mudou primeiro'); UPDATE enquanto persiste; CLOSE quando limpa por close_when_clear_for_s
    def open_events(self, equipment_id) -> list[Event]
    def alarm_lookup(self, profile: EquipmentProfile, code: str) -> AlarmLookup   # chave composta a partir do perfil (software_version UNKNOWN permitido)
# forja.events.what_changed
def compute_what_changed(pre: Sequence[Sample], now: dict[str, Sample], tags: Sequence[str]) -> tuple[WhatChangedItem, ...]   # before = mediana da janela pré; now = valor na detecção; delta_kind: pct para kg/h e kg/m, points para %, abs para rpm; ordenado por ts_start (primeira a sair do padrão = changed_first)
# forja.events.memory_store
class InMemoryEventRepository / InMemoryDiagnosisRepository   # para testes e CLI offline
# forja.diagnostics.library
class DiagnosisEntry(BaseModel): ref: str; internal_code: str; title_pt: str; text_pt: str; hypotheses: list[...]; next_checks: list[...]; sources: list[SourceRef]; caveats: list[str]
def load_library(dir_: Path) -> DiagnosisLibrary (get(ref))
# forja.diagnostics.engine
class DiagnosisEngine:
    def __init__(self, library: DiagnosisLibrary, clock: Clock) -> None
    def diagnose(self, event: Event) -> Diagnosis   # usa context.what_changed como O QUE MUDOU; evidência a partir das amostras; sempre inclui MANDATORY_CAVEAT_PT; evidence_summary via Diagnosis.build_evidence_summary; valida regra de não promoção
# forja.diagnostics.schema_v1
def diagnosis_json_schema() -> dict; def write_schema(path: Path) -> None   # gerar docs/contracts/diagnosis-v1.0.schema.json
```

Conteúdo das regras (todas FORJA_RULE, thresholds relativos às referências do perfil ou SIMULATED; documentar que são regras Forja, não limites do KCM):
R-BELTLOAD-001 `BELT_LOAD_LOW` "Pouco material sobre a correia" ATTENTION: belt_load drop_pct_over_window ≥ 35% em 60 s AND drive_command rise ≥ 15 pontos AND machine_state == 1, persist 10 s.
R-SPEED-001 `SPEED_FEEDBACK_ANOMALY` "Leitura de velocidade inconsistente" ATTENTION: machine_state == 1 AND drive_command > 5 AND rpm < 1, persist 5 s.
R-RATE-001 `RATE_DEVIATION` "Vazão abaixo do esperado" ATTENTION: mass_flow < 0.9 × setpoint (ref_tag) por 30 s com machine_state == 1.
R-DRIVE-001 `DRIVE_COMMAND_HIGH` "Esforço do acionamento alto" ATTENTION: drive_command > 85 por 30 s.
R-COMM-001 `COMM_DEGRADED` "Comunicação degradada" ATTENTION: quality_is COMM_ERROR por 15 s.
R-STOP-001 `MACHINE_STOPPED` "Equipamento parado" INFO: machine_state changed para 0 (parada não é falha; classificar com StopByCatalog, default UNKNOWN).
Biblioteca de diagnóstico: textos da spec §39, §40, §81 e DM §18; hipóteses sempre "Comportamento compatível com..."; verificações em ordem (alimentação, frequência/sinal, cabo, conector, gap, interface/SIB, entrada, PICK UP TEETH) com `safety_pt` "Conforme procedimento da planta"; fontes: regra (FORJA_RULE), caso GTEX (FIELD_OBSERVED, causa UNKNOWN), opinião técnica. Nenhum nível acima do que a fonte sustenta.
Caso: `knowledge/cases/2026-09_gtex_pha_po_base_velocidade.yaml` com os fatos do DM §7 (FIELD_OBSERVED), `confirmed_cause: UNKNOWN`, medições (4,9 V, gap 0,125 mm) como observação do atendimento, nunca threshold.

Testes mínimos (≥ 35): cada condição; BELTLOAD_LOW abre evento com what_changed ordenado e `changed_first` em belt_load; evento não abre com qualidade COMM_ERROR; cooldown e close; pré-janela tem ≤ 60 s contíguos; diagnóstico das 7 seções na ordem oficial; schema_version "1.0"; golden JSON salvo em `tests/fixtures/diagnosis_golden_belt_load_low.json`; catálogo de alarme: 56 só casa com chave WBF; outra aplicação → não catalogado; stop_by Calib → UNKNOWN; nenhuma hipótese contém "causa"; i18n cobre todos os internal_code das regras.

---

## Bloco 5 — API, SSE e CLI (dono: Sexta-feira-3)

Arquivos: `src/forja/api/{__init__,app,errors,deps,sse}.py`, `src/forja/api/routers/{__init__,health,plant,equipments,history,events,diagnostics,simulator,communication,stream,ui}.py`,
`src/forja/tools/{__init__,cli}.py`, `src/forja/api/static/index.html` (página honesta: estado do Edge, lista de equipamentos com link para `/docs`; sem botão falso; sem CDN),
testes em `tests/integration/test_api_*.py`, `tests/contract/test_openapi_no_device_write.py`, `tests/contract/test_import_boundaries.py`, `tests/integration/test_cli_diagnose_json.py`.

```python
# forja.api.app
def create_app(container: Container) -> FastAPI   # título "Forja KCM Intelligence"; middleware: CSP "default-src 'self'; frame-ancestors 'none'", X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy no-referrer; sem CORSMiddleware; envelope de erro {"error":{"code","message_pt","details"}}; lifespan NÃO inicia aquisição (o runner inicia) — app só serve.
# Rotas (prefixo /api/v1; tudo JSON; listas com ?limit):
GET  /health                                   -> {"status":"ok","version"}
GET  /api/v1/system/about                      -> versão, read_only: true, data_source: "SIMULATED"|"EQUIPMENT"|"MIXED", uptime_s, python, sqlite
GET  /api/v1/system/health                     -> uptime, por equipamento EquipmentRuntimeStatus, historian stats, bus dropped, event engine (regras carregadas, eventos abertos)
GET  /api/v1/plant                             -> cards: por equipamento {id, name, application, is_example, state_pt (Normal|Atenção|Crítico|Sem comunicação|Parado|Desconhecido), connection, data_source, last_read_utc, last_event, active_anomaly_pt, mass_flow (valor+qualidade)}
GET  /api/v1/equipments ; GET /api/v1/equipments/{id} (perfil) ; GET /api/v1/equipments/{id}/status ; GET /api/v1/equipments/{id}/live (LiveSnapshot: tags com valor, unidade, qualidade, idade_s, label_pt, explanation_pt)
GET  /api/v1/equipments/{id}/history?tags=a,b&from=iso&to=iso&maxPoints=2000   -> {series:[Series]}  (GAP = null)
GET  /api/v1/equipments/{id}/events?limit ; GET /api/v1/events/{id} ; GET /api/v1/events/{id}/diagnosis (JSON v1.0; 404 se não houver) ; POST /api/v1/events/{id}/ack {user, note_pt} (auditado via core_store.audit)
GET  /api/v1/alarms/lookup?equipment_id&code   -> AlarmLookup com qualifier_pt
GET  /api/v1/communication/drivers             -> DriverSupportInfo por driver (nunca AVAILABLE falso) + estado por equipamento (NEEDS_CONFIGURATION quando ip/protocolo UNKNOWN)
POST /api/v1/communication/test-read {profile, mapping} -> ReadTestResult   # só leitura; driver UNSUPPORTED -> 409 com message_pt "Disponível após configuração de campo"
GET  /api/v1/simulator/{id} ; POST /api/v1/simulator/{id}/scenario {scenario} ; POST /api/v1/simulator/{id}/controls {overrides} ; DELETE /api/v1/simulator/{id}/controls   # 409 se driver do equipamento não for simulator
GET  /api/v1/stream?eq=ID(opcional)            -> SSE (sse-starlette): primeiro evento "snapshot" (plant + live de todos), depois "sample" (coalescido ≤ 2 Hz por equipamento), "event", "status", "heartbeat" a cada 5 s; id sequencial; Last-Event-ID com buffer de 60 s
GET  /                                         -> static/index.html ; GET /docs só em modo dev (config edge.name contém "desenvolvimento") 
# NÃO EXISTE rota com command|write|setpoint|run|stop|reset|tare|span|calib|feed no path. Toda rota mutante está na allowlist em tests/contract/test_openapi_no_device_write.py.

# forja.tools.cli  (argparse; entry point `forja`)
forja run [--host --port --home]        -> build_container + start + uvicorn programático (uvicorn.Server) no mesmo loop; Ctrl+C -> stop gracioso
forja diagnose --json --demo <SCENARIO> [--seconds 120] [--equipment GTEX_PHA_PO_BASE]  -> roda simulador offline com FakeClock avançando, RuleEngine, DiagnosisEngine; imprime SOMENTE o JSON v1.0 (mesmo objeto da API). Sem --json imprime texto em PT (7 seções) e nunca JSON.
forja diagnose --json --event-id <id>   -> lê do core store
forja config validate                   -> carrega ConfigStore e lista perfis/mappings/regras; código de saída ≠ 0 em erro
forja doctor                            -> python, sqlite, fts5, libs instaladas e versões, portas, pastas, relógio; sem rede
forja simulate --scenario X --seconds N -> imprime eventos abertos/fechados (texto)
```

Testes mínimos (≥ 30): todas as rotas GET com container de teste (3 simuladores, FakeClock, SQLite em tmp_path) via `httpx.ASGITransport`; `/plant` mostra "Sem comunicação" para EXEMPLO_KCM_03; `/live` expõe STALE com idade; simulator POST em equipamento não-simulador → 409; test-read com modbus_tcp → 409 honesto; stream entrega snapshot + heartbeat (ler 2 eventos e fechar); OpenAPI: nenhum path com verbo de comando, toda rota mutante na allowlist; `forja diagnose --json --demo BELTLOAD_LOW` valida contra `Diagnosis` e é igual ao da API para o mesmo evento; CLI sem --json não produz JSON; import boundaries: `pymodbus`/`pycomm3` só em `src/forja/drivers/*/_client.py` (hoje nenhum).

---

## Integração (depois dos blocos)

`.\.venv\Scripts\python.exe -m pytest -q` verde; `ruff check src tests` e `ruff format --check` limpos; `mypy src/forja/domain src/forja/drivers src/forja/normalization src/forja/acquisition` sem erro; `forja run` sobe em 127.0.0.1:8765 com 3 simuladores; `curl /api/v1/equipments/GTEX_PHA_PO_BASE/live` mostra SIMULATED; `forja diagnose --json --demo BELTLOAD_LOW` valida. Commit local por bloco integrado.
