"""Pacote de instalação do Windows: semente de produção, scripts e nomes do serviço coerentes."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from forja.api.deps import is_dev_mode
from forja.config.loader import load_forja_config
from forja.service.winservice import DISPLAY_NAME, SERVICE_NAME

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "packaging"
SCRIPTS = [
    PACKAGING / "install.ps1",
    PACKAGING / "uninstall.ps1",
    ROOT / "scripts" / "build_windows.ps1",
]


def _production_seed() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "production_seed", PACKAGING / "production_seed.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semente_do_pacote_nao_sai_em_modo_desenvolvimento(tmp_path: Path) -> None:
    seed = _production_seed()
    text = seed.production_config((ROOT / "config" / "forja.yaml").read_text(encoding="utf-8"))
    target = tmp_path / "forja.yaml"
    target.write_text(text, encoding="utf-8")
    config = load_forja_config(target)
    assert not is_dev_mode(config.edge.name)
    assert config.edge.bind_host == "127.0.0.1"
    source = load_forja_config(ROOT / "config" / "forja.yaml")
    assert config.model_dump(exclude={"edge"}) == source.model_dump(exclude={"edge"})


def test_semente_com_origem_inesperada_para_o_build() -> None:
    seed = _production_seed()
    with pytest.raises(ValueError, match="mudou"):
        seed.production_config('edge:\n  name: "Outro nome"\n')


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_powershell_tem_bom_utf8(script: Path) -> None:
    # Sem BOM, o Windows PowerShell 5.1 lê o arquivo como ANSI e quebra acentos e aspas.
    assert script.read_bytes().startswith(b"\xef\xbb\xbf")


def test_nome_do_servico_igual_no_instalador_e_no_codigo() -> None:
    install = (PACKAGING / "install.ps1").read_text(encoding="utf-8-sig")
    uninstall = (PACKAGING / "uninstall.ps1").read_text(encoding="utf-8-sig")
    for text in (install, uninstall):
        assert f"$ServiceName = '{SERVICE_NAME}'" in text
    assert f"$DisplayName = '{DISPLAY_NAME}'" in install


def test_instalador_so_fala_com_esta_maquina() -> None:
    # Sem regra de firewall, sem download, sem URL externa: só o /health local.
    for script in (PACKAGING / "install.ps1", PACKAGING / "uninstall.ps1"):
        text = script.read_text(encoding="utf-8-sig")
        for forbidden in ("New-NetFirewallRule", "netsh", "Invoke-RestMethod", "DownloadFile"):
            assert forbidden not in text, (script.name, forbidden)
        urls = re.findall(r"https?://[^\s\"'`]+", text)
        assert all(url.startswith("http://127.0.0.1") for url in urls), urls


def test_atualizacao_preserva_dados_por_construcao() -> None:
    install = (PACKAGING / "install.ps1").read_text(encoding="utf-8-sig")
    assert "backup', 'create'" in install
    assert "init', '--home'" in install
    # a pasta de dados nunca é removida pelo instalador
    assert not re.search(r"Remove-Item[^\n]*\$DataDir", install)


@pytest.mark.skipif(sys.platform != "win32", reason="parser do Windows PowerShell")
def test_scripts_powershell_sem_erro_de_sintaxe() -> None:
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("powershell.exe indisponível")
    paths = ",".join(f"'{p}'" for p in SCRIPTS)
    command = (
        f"foreach ($p in @({paths})) {{ $t = $null; $e = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$t, [ref]$e) "
        '| Out-Null; foreach ($x in $e) { "${p}:$($x.Extent.StartLineNumber): $($x.Message)" } }'
    )
    result = subprocess.run(  # noqa: S603 - comando fixo, sem entrada externa
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
