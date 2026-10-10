# Contratos da Fase N — Distribuição Windows

Complementa `CONTRATOS_A1.md`. Nada aqui fala com o KCM: instalar, atualizar, fazer backup e remover são operações locais.

## Pastas

| Pasta | Conteúdo | Quem troca |
|---|---|---|
| `C:\Program Files\ForjaKCM` (parâmetro `-InstallDir`) | Executável (`ForjaKCM.exe`), bibliotecas, interface compilada, migrações e a semente de configuração (`_internal\seed`). | A atualização troca a pasta inteira. |
| `C:\ProgramData\ForjaKCM` (parâmetro `-DataDir`) | `config\`, `knowledge\`, `var\` (bancos), `var\logs\`, `var\backups\`. | Ninguém apaga. `init` só acrescenta arquivo que falta. |

A pasta de dados não pode ficar dentro da pasta do programa (o instalador recusa).

## Resolução da pasta de dados (`forja.config.paths`)

Precedência: argumento `--home` > variável `FORJA_HOME` > padrão. Padrão no executável empacotado: `%ProgramData%\ForjaKCM`; em desenvolvimento: a raiz do repositório. Dentro dela: dados em `var` (ou `FORJA_DATA_DIR`), logs em `var\logs`, backups em `var\backups`.

O serviço recebe `FORJA_HOME=<DataDir>` no registro do serviço (`HKLM\SYSTEM\CurrentControlSet\Services\ForjaKCM\Environment`), então a pasta escolhida na instalação vale para o serviço sem depender do padrão.

## Linha de comando de administração

Mesmos comandos em `forja` (desenvolvimento) e `ForjaKCM.exe` (pacote):

| Comando | Efeito |
|---|---|
| `init [--home]` | Copia a semente (`config/`, `knowledge/`, sem `_history`) para a pasta de dados e cria `var`, `var\logs`, `var\backups`. Nunca sobrescreve arquivo existente. |
| `backup create [--home] [--dest]` | Backup consistente dos dois bancos com manifesto (sha256, integridade) — pode rodar com o Edge ligado. Padrão: `var\backups\backup_<UTC>`. |
| `backup verify PASTA` | Confere checksum e `integrity_check` de todos os arquivos do backup. |
| `backup restore PASTA --sim [--home]` | Substitui os bancos. Exige `--sim` e o serviço parado (consulta o gerenciador de serviços; arquivo em uso também é recusado). Valida tudo antes de tocar no destino. |
| `service run` | Ponto de entrada chamado pelo gerenciador de serviços. |
| `run [--home] [--port]` | Sobe o Edge no terminal (teste de bancada). |

Erros de domínio (backup ausente, corrompido, em uso) saem como `erro: <mensagem>` com código 1, sem rastreamento de pilha. Sem argumentos (duplo clique), o executável explica onde está a interface e espera Enter.

## Serviço do Windows (`forja.service.winservice`)

- Nome `ForjaKCM`, exibição "Forja KCM Intelligence", pywin32 `ServiceFramework` (ADR 0009).
- Início automático atrasado; conta `NT AUTHORITY\LocalService`; reinício após falha (1 min, 1 min, 5 min; contador zera em 24 h).
- `SvcStop` pede parada graciosa ao `EdgeRunner` (de outra thread): loops param, gravação pendente é descarregada, bancos fecham.
- Mensagens no Visualizador de Eventos (Aplicativo, fonte `ForjaKCM`); detalhe no `var\logs\forja.log`.
- Porta ocupada: o Edge usa a próxima livre (até 20 tentativas) e registra o aviso, para a coleta não parar por causa da interface.

## Instalador (`packaging\install.ps1`)

1. Confere o pacote, as pastas e os privilégios antes de mexer em qualquer coisa.
2. Atualização: para o serviço e cria backup dos bancos com a versão instalada. Backup falhou = nada é trocado e o serviço volta.
3. Troca do programa em etapas: cópia nova em `<pasta>.novo`, antiga renomeada para `<pasta>.anterior`, nova no lugar, antiga apagada. Pasta em uso falha antes de apagar qualquer coisa; falha na segunda etapa devolve a versão anterior.
4. Pasta de dados com permissão explícita: Administradores e SYSTEM controle total, LocalService modificar, Usuários leitura.
5. `init` (nunca sobrescreve), registro do serviço, ambiente `FORJA_HOME`, fonte de eventos, partida e espera do `/health` local (60 s).
6. Atalho `Forja KCM.url` (Área de Trabalho pública e Menu Iniciar) para `http://127.0.0.1:<edge.bind_port>/app`.

`-NoService` copia o programa e prepara os dados sem serviço nem atalho (bancada, sem administrador). Nenhum passo abre porta no firewall, baixa arquivo ou acessa endereço fora de `127.0.0.1`.

`packaging\uninstall.ps1`: para e remove o serviço, a fonte de eventos, os atalhos e a pasta do programa. Dados ficam, exceto com `-RemoveData` (pede para digitar APAGAR; recusa pasta que não tenha `config\forja.yaml`).

## Build (`scripts\build_windows.ps1`)

1. Interface: `npm ci` + `npm run build` (travado em `frontend\package-lock.json`; recusa URL remota no resultado).
2. Executável: PyInstaller em modo pasta (`packaging\forja.spec`), `PYTHONHASHSEED=0`, dependências de `requirements.lock.txt`.
3. Semente de produção: o `config\forja.yaml` do repositório sem o nome de desenvolvimento (`packaging\production_seed.py`), então o pacote nunca expõe `/docs`. Se a origem mudar de formato, o build para.
4. Teste do executável: `init` em pasta temporária, Edge numa porta livre, `/health` = ok, `/app` = 200, `/docs` = 404.
5. Pacote `build\release\ForjaKCM-<versão>-win64.zip`: programa, `install.ps1`, `uninstall.ps1`, `LEIA-ME.txt`, `TERCEIROS.txt` (licenças das bibliotecas Python e do Python), `SHA256SUMS.txt`.

O procedimento é reproduzível (entradas travadas e etapas fixas). O `.zip` não é idêntico bit a bit entre builds: datas de arquivo entram no compactado.

## Provas

- `tests/unit/test_install_layout.py`: precedência da pasta de dados, padrão do executável congelado, semente sem sobrescrever.
- `tests/integration/test_cli_admin.py`: `init`, backup criar/conferir/restaurar, backup corrompido e ausente viram mensagem, restauração recusada com serviço rodando.
- `tests/unit/test_packaging.py`: semente de produção sem modo desenvolvimento, scripts com BOM UTF-8 e sem erro de sintaxe no Windows PowerShell 5.1, nome do serviço igual no código e nos scripts, scripts sem URL externa nem regra de firewall, instalador sem remoção da pasta de dados.
- Verificado à mão no executável: instalação e atualização em bancada (`-NoService`, caminho com espaço), configuração local preservada, backup antes da troca, atualização recusada com o programa em uso (versão antiga intacta e respondendo), `SHA256SUMS.txt` conferido.
- Não verificado nesta máquina: registro e partida do serviço (exige administrador). Primeiro teste no PC da planta: `install.ps1`, reiniciar o Windows, conferir `/health` e a coleta.
