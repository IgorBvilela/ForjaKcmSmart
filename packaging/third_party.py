"""Gera TERCEIROS.txt: licenças das bibliotecas Python embutidas no executável.

Percorre as dependências de execução do pacote forja-kcm (sem extras de desenvolvimento) e junta,
para cada uma, nome, versão, licença declarada e o texto dos arquivos de licença distribuídos com
ela. Inclui a licença do próprio Python, que vai junto no executável. As licenças das fontes e
bibliotecas da interface ficam em forja/ui/dist/licenses.

Uso: python packaging/third_party.py CAMINHO_DE_SAIDA
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

ROOT_DISTRIBUTION = "forja-kcm"
LICENSE_PREFIXES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")


def runtime_distributions(root: str = ROOT_DISTRIBUTION) -> list[metadata.Distribution]:
    seen: dict[str, metadata.Distribution] = {}
    pending = [root]
    while pending:
        dist = metadata.distribution(pending.pop())
        key = dist.metadata["Name"].lower().replace("_", "-")
        if key in seen:
            continue
        seen[key] = dist
        for text in dist.requires or []:
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            pending.append(requirement.name)
    seen.pop(root, None)
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def declared_license(dist: metadata.Distribution) -> str:
    expression = dist.metadata.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        c.split("::")[-1].strip()
        for c in dist.metadata.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if classifiers:
        return ", ".join(classifiers)
    declared = (dist.metadata.get("License") or "").strip()
    return declared.splitlines()[0] if declared else "não declarada no pacote"


def license_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for file in dist.files or []:
        name = Path(str(file)).name.upper()
        if not name.startswith(LICENSE_PREFIXES) or ".dist-info" not in str(file):
            continue
        path = Path(str(dist.locate_file(file)))
        if path.is_file():
            texts.append((Path(str(file)).name, path.read_text(encoding="utf-8", errors="replace")))
    return texts


def render() -> str:
    parts = [
        "Componentes de terceiros embutidos no Forja KCM Intelligence",
        "=" * 64,
        "",
    ]
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    parts += [f"Python {sys.version.split()[0]} - PSF License", "-" * 64]
    if python_license.is_file():
        parts.append(python_license.read_text(encoding="utf-8", errors="replace").strip())
    parts.append("")
    for dist in runtime_distributions():
        name, version = dist.metadata["Name"], dist.version
        parts += [f"{name} {version} - {declared_license(dist)}", "-" * 64]
        texts = license_texts(dist)
        if not texts:
            parts.append("(o pacote não distribui arquivo de licença; ver licença declarada)")
        for file_name, text in texts:
            parts += [f"[{file_name}]", text.strip()]
        parts.append("")
    return "\n".join(parts) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    out = Path(argv[0])
    out.write_text(render(), encoding="utf-8")
    print(f"Avisos de terceiros em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
