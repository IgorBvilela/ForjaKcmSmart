"""Comandos de administração da instalação: init, backup create/verify/restore."""

from __future__ import annotations

from pathlib import Path

import pytest

from forja.tools.cli import main

pytestmark = pytest.mark.integration


def test_init_prepara_e_preserva(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    home = tmp_path / "ForjaKCM"
    assert main(["init", "--home", str(home)]) == 0
    assert (home / "config" / "forja.yaml").is_file()
    assert (home / "knowledge").is_dir()
    assert (home / "var" / "backups").is_dir()
    marker = home / "config" / "forja.yaml"
    marker.write_text(marker.read_text(encoding="utf-8") + "\n# ajuste local\n", encoding="utf-8")
    assert main(["init", "--home", str(home)]) == 0
    assert "# ajuste local" in marker.read_text(encoding="utf-8")
    assert "preservada" in capsys.readouterr().out


def test_backup_create_verify_e_restore(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    home = tmp_path / "ForjaKCM"
    assert main(["init", "--home", str(home)]) == 0
    dest = tmp_path / "copia"
    assert main(["backup", "create", "--home", str(home), "--dest", str(dest)]) == 0
    assert (dest / "manifest.json").is_file()
    assert main(["backup", "verify", str(dest)]) == 0
    assert "íntegro" in capsys.readouterr().out
    # restaurar sem confirmação explícita é recusado
    assert main(["backup", "restore", "--home", str(home), str(dest)]) == 1
    assert main(["backup", "restore", "--home", str(home), str(dest), "--sim"]) == 0
    assert (home / "var" / "forja_core.db").is_file()


def test_backup_corrompido_e_recusado_sem_tocar_nos_bancos(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "ForjaKCM"
    main(["init", "--home", str(home)])
    dest = tmp_path / "copia"
    main(["backup", "create", "--home", str(home), "--dest", str(dest)])
    db = next(dest.glob("forja_core_*.db"))
    db.write_bytes(db.read_bytes()[:-10] + b"corrompido")
    current = home / "var" / "forja_core.db"
    before = current.read_bytes()
    capsys.readouterr()

    assert main(["backup", "verify", str(dest)]) == 1
    assert main(["backup", "restore", "--home", str(home), str(dest), "--sim"]) == 1
    err = capsys.readouterr().err
    assert err.count("erro:") == 2
    assert "checksum" in err
    assert "Traceback" not in err
    assert current.read_bytes() == before


def test_backup_inexistente_vira_mensagem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["backup", "verify", str(tmp_path / "nao_existe")]) == 1
    assert "manifesto não encontrado" in capsys.readouterr().err


def test_restore_recusa_com_servico_rodando(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from forja.tools import admin

    home = tmp_path / "ForjaKCM"
    main(["init", "--home", str(home)])
    dest = tmp_path / "copia"
    main(["backup", "create", "--home", str(home), "--dest", str(dest)])
    monkeypatch.setattr(admin, "service_running", lambda: True)
    capsys.readouterr()
    assert main(["backup", "restore", "--home", str(home), str(dest), "--sim"]) == 1
    assert "em execução" in capsys.readouterr().err


def test_consulta_do_servico_nao_quebra_sem_servico_instalado() -> None:
    from forja.tools.admin import service_running

    assert service_running() in (True, False)


def test_restaurar_configuracao_guarda_a_atual_antes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "ForjaKCM"
    main(["init", "--home", str(home)])
    dest = tmp_path / "copia"
    main(["backup", "create", "--home", str(home), "--dest", str(dest)])
    cfg = home / "config" / "forja.yaml"
    original = cfg.read_text(encoding="utf-8")
    cfg.write_text(original + "\n# alteração depois do backup\n", encoding="utf-8")

    assert (
        main(["backup", "restore", "--home", str(home), str(dest), "--sim", "--configuracao"]) == 0
    )
    assert cfg.read_text(encoding="utf-8") == original
    safety = next((home / "var" / "backups").glob("antes_da_restauracao_*"))
    assert "# alteração depois do backup" in (safety / "config" / "forja.yaml").read_text(
        encoding="utf-8"
    )
    assert "Configuração restaurada" in capsys.readouterr().out
