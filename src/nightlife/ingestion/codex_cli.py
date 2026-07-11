# src/nightlife/ingestion/codex_cli.py
"""Plomberia compartilhada do codex CLI (spec E-1): invocacao headless com
imagem anexada + extracao do JSON da saida. Usado pelo CodexExtractor (flyer
1-evento) e pelo PostInterpreter (E-1). Nao reescreva as licoes de
Windows/seguranca abaixo — foram calibradas no smoke real."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_codex(image_path: Path, prompt: str) -> str:
    """Invoca o codex CLI em modo nao-interativo com a imagem anexada.

    Flags calibrados no smoke real (Task 5) — requisito: exec headless,
    imagem como input, resultado no stdout. Tres calibracoes necessarias:
    (1) no Windows o `codex` instalado via npm resolve para um shim
    `codex.CMD`, que subprocess.run nao consegue executar diretamente
    (WinError 2) sem `shell=True`; resolvemos o caminho completo via
    shutil.which e usamos shell so no Windows;
    (2) `-i/--image` aceita `FILE...` (multiplos valores) e por isso e
    "guloso": se o PROMPT vier depois de `-i <path>` na linha de comando,
    o parser do CLI engole o prompt como se fosse mais um arquivo de imagem;
    (3) com `shell=True` no Windows a lista de args e serializada numa unica
    string para o `cmd.exe /c`, cujo parser trunca a linha em quebras de
    linha literais — o PROMPT (multi-linha) nunca chegava inteiro ao codex.
    Por isso o PROMPT e enviado via stdin (`-` como posicional, doc do CLI:
    "instructions are read from stdin") em vez de argv, e soh o caminho da
    imagem (sem quebras de linha) trafega na linha de comando.

    SEGURANCA: com shell=True no Windows, um argumento com metacaractere de
    cmd.exe (& | %) e SEM espaco passa sem aspas e e interpretado pelo shell —
    um flyer baixado como "a&whoami&b.png" executaria comando arbitrario. O
    nome do arquivo vem de download/print (nao-confiavel; e a pasta que um
    monitor de IG futuro vai popular). Por isso a imagem e copiada para um
    nome CONTROLADO (sem metacaractere) num tempdir antes de ir para a linha
    de comando; o nome original nunca chega ao shell.
    """
    codex_bin = shutil.which("codex") or "codex"
    src = Path(image_path)
    suffix = src.suffix if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else ".png"
    with tempfile.TemporaryDirectory() as tmp:
        safe = Path(tmp) / f"flyer{suffix}"
        shutil.copyfile(src, safe)
        result = subprocess.run(
            [codex_bin, "exec", "--skip-git-repo-check", "-", "-i", str(safe)],
            input=prompt,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300, shell=(sys.platform == "win32"),
        )
    return result.stdout or ""


def extract_json(text: str) -> dict:
    # heuristica do 1o "{" ao ultimo "}": o CLI cerca o JSON de logs/preambulo.
    # Se o preambulo tiver seu proprio par de chaves, rfind pega o span errado
    # e a extracao falha (consome o retry) — aceito pra o esqueleto.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("nenhum objeto JSON na saida")
    return json.loads(text[start:end + 1])
