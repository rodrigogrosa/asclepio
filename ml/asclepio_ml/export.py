"""Etapa ``export`` — funde o adapter LoRA no modelo base e registra no Ollama.

1. ``merge_and_unload``: soma W + (B·A)·(alpha/r) em cada projeção → modelo "normal" (sem PEFT),
   salvo em safetensors + tokenizer em ``ml/models/asclepio-med/``.
2. ``Modelfile``: ``FROM ./`` (importação direta de safetensors pelo Ollama), system prompt do
   Asclépio, ``temperature 0.1`` e o *template* de chat do modelo base (ChatML para Qwen).
3. ``ollama create asclepio-med -f Modelfile``. Se a importação de safetensors falhar
   (arquitetura não suportada), convertemos para GGUF com o ``convert_hf_to_gguf.py`` do
   llama.cpp e usamos ``FROM ./asclepio-med.gguf``.
4. Verificação: ``ollama run asclepio-med "<pergunta>"``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from asclepio_ml.config import Config
from asclepio_ml.prompts import SYSTEM_PROMPT
from asclepio_ml.registry import read_registry, write_registry
from asclepio_ml.utils import log, write_json

VERIFY_QUESTION = "Qual o alvo de lactato na sepse segundo o protocolo?"

# Templates de chat no formato Go-template do Ollama, por família de modelo base.
CHAT_TEMPLATES: dict[str, str] = {
    # Qwen2 / Qwen2.5 (ChatML)
    "chatml": (
        "{{- if .System }}<|im_start|>system\n{{ .System }}<|im_end|>\n{{ end }}"
        '{{- range .Messages }}{{- if ne .Role "system" }}<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n{{ end }}{{- end }}'
        "<|im_start|>assistant\n"
    ),
    # Llama 3.x
    "llama3": (
        "{{- if .System }}<|start_header_id|>system<|end_header_id|>\n\n{{ .System }}<|eot_id|>{{ end }}"
        '{{- range .Messages }}{{- if ne .Role "system" }}<|start_header_id|>{{ .Role }}<|end_header_id|>\n\n{{ .Content }}<|eot_id|>{{ end }}{{- end }}'
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    ),
    # TinyLlama-Chat (formato Zephyr)
    "zephyr": (
        "{{- if .System }}<|system|>\n{{ .System }}</s>\n{{ end }}"
        '{{- range .Messages }}{{- if ne .Role "system" }}<|{{ .Role }}|>\n{{ .Content }}</s>\n{{ end }}{{- end }}'
        "<|assistant|>\n"
    ),
}
STOP_TOKENS: dict[str, list[str]] = {
    "chatml": ["<|im_start|>", "<|im_end|>", "<|endoftext|>"],
    "llama3": ["<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>"],
    "zephyr": ["</s>", "<|user|>", "<|system|>"],
}


def detect_family(base_model: str, model_type: str | None = None) -> str:
    name = (base_model or "").lower()
    mt = (model_type or "").lower()
    if "qwen" in name or mt.startswith("qwen"):
        return "chatml"
    if "tinyllama" in name or "zephyr" in name:
        return "zephyr"
    if "llama-3" in name or "llama3" in name or "llama_3" in name:
        return "llama3"
    if mt == "llama":
        return "llama3"
    return "chatml"


def render_modelfile(
    from_line: str,
    system_prompt: str = SYSTEM_PROMPT,
    family: str = "chatml",
    temperature: float = 0.1,
    num_ctx: int = 4096,
    num_predict: int = 512,
    base_model: str = "",
    run_id: str = "",
) -> str:
    tpl = CHAT_TEMPLATES[family]
    stops = "\n".join(f'PARAMETER stop "{s}"' for s in STOP_TOKENS[family])
    return (
        f"# Modelfile — Asclépio (asclepio-med)\n"
        f"# Gerado por `python -m asclepio_ml export` em {datetime.now():%Y-%m-%d %H:%M}\n"
        f"# Base: {base_model or 'n/d'} · run: {run_id or 'n/d'} · método: LoRA (adapter fundido)\n"
        f"FROM {from_line}\n\n"
        f'TEMPLATE """{tpl}"""\n\n'
        f'SYSTEM """{system_prompt}"""\n\n'
        f"PARAMETER temperature {temperature}\n"
        f"PARAMETER top_p 0.9\n"
        f"PARAMETER repeat_penalty 1.05\n"
        f"PARAMETER num_ctx {num_ctx}\n"
        f"PARAMETER num_predict {num_predict}\n"
        f"{stops}\n\n"
        f'LICENSE """Uso acadêmico — Tech Challenge FIAP (Fase 3). Modelo fine-tuned com dados fictícios/sintéticos; não é dispositivo médico e não substitui o julgamento profissional."""\n'
    )


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 1800) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"comando não encontrado: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def ollama_available() -> bool:
    return shutil.which("ollama") is not None and _run(["ollama", "list"], timeout=30)[0] == 0


def merge_adapter(
    base_model: str, adapter_dir: Path, out_dir: Path, save_dtype: str = "float16"
) -> dict[str, Any]:
    """Carrega base + adapter em CPU (fp32), funde e salva em safetensors (fp16 por padrão)."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    log(f"carregando base {base_model} + adapter {adapter_dir} (CPU, fp32) para fundir…")
    tok = AutoTokenizer.from_pretrained(
        str(adapter_dir) if (adapter_dir / "tokenizer_config.json").exists() else base_model
    )
    base = AutoModelForCausalLM.from_pretrained(base_model, dtype=torch.float32)
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    merged = model.merge_and_unload()
    merged.config.use_cache = True
    target_dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[
        save_dtype
    ]
    merged = merged.to(target_dtype)
    if out_dir.exists():
        for p in out_dir.glob("*.safetensors"):
            p.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(out_dir), safe_serialization=True)
    tok.save_pretrained(str(out_dir))
    _write_legacy_config_keys(out_dir)
    size_mb = sum(p.stat().st_size for p in out_dir.glob("*.safetensors")) / 1e6
    log(f"modelo fundido salvo em {out_dir} ({size_mb:.0f} MB, {save_dtype})")
    return {
        "merged_path": str(out_dir),
        "size_mb": round(size_mb, 1),
        "model_type": getattr(merged.config, "model_type", None),
    }


def _write_legacy_config_keys(model_dir: Path) -> None:
    """Compatibilidade: transformers ≥ 5 grava ``rope_parameters.rope_theta`` e ``dtype``; os
    conversores do Ollama e do llama.cpp ainda leem ``rope_theta``/``torch_dtype`` no topo do
    config.json. Sem isso o Qwen2 é importado com rope_theta errado e gera texto degenerado."""
    cfg_path = model_dir / "config.json"
    if not cfg_path.exists():
        return
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    rp = cfg.get("rope_parameters") or {}
    changed = False
    if "rope_theta" not in cfg and rp.get("rope_theta") is not None:
        cfg["rope_theta"] = rp["rope_theta"]
        changed = True
    if "rope_scaling" not in cfg and rp.get("rope_type") not in (None, "default"):
        cfg["rope_scaling"] = {k: v for k, v in rp.items() if k != "rope_theta"}
        changed = True
    if "torch_dtype" not in cfg and cfg.get("dtype"):
        cfg["torch_dtype"] = cfg["dtype"]
        changed = True
    if changed:
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        log(
            "config.json: chaves legadas (rope_theta/torch_dtype) adicionadas para o conversor do Ollama"
        )


def convert_to_gguf(model_dir: Path, cache_dir: Path, outtype: str = "f16") -> Path:
    """Fallback: converte o diretório HF em GGUF usando o script oficial do llama.cpp."""
    repo = cache_dir / "llama.cpp"
    if not (repo / "convert_hf_to_gguf.py").exists():
        log("clonando llama.cpp (somente o script de conversão)…")
        code, out = _run(
            ["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(repo)],
            timeout=600,
        )
        if code != 0:
            raise RuntimeError(f"falha ao clonar llama.cpp: {out[-500:]}")
    gguf = model_dir / "asclepio-med.gguf"
    code, out = _run(
        [
            "uv",
            "run",
            "python",
            str(repo / "convert_hf_to_gguf.py"),
            str(model_dir),
            "--outfile",
            str(gguf),
            "--outtype",
            outtype,
        ],
        timeout=1800,
    )
    if code != 0 or not gguf.exists():
        raise RuntimeError(f"conversão GGUF falhou: {out[-1500:]}")
    log(f"GGUF gerado: {gguf} ({gguf.stat().st_size / 1e6:.0f} MB)")
    return gguf


def create_ollama_model(model_dir: Path, name: str) -> tuple[bool, str]:
    code, out = _run(["ollama", "create", name, "-f", "Modelfile"], cwd=model_dir, timeout=1800)
    return code == 0, out


def verify_ollama_model(
    name: str, question: str = VERIFY_QUESTION, base_url: str = "http://localhost:11434"
) -> tuple[bool, str, float]:
    """Pergunta de verificação via API HTTP (saída limpa, sem spinner do terminal); fallback: ``ollama run``."""
    t0 = time.time()
    try:
        import httpx

        r = httpx.post(
            f"{base_url}/api/chat",
            json={
                "model": name,
                "messages": [{"role": "user", "content": question}],
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=300,
        )
        r.raise_for_status()
        answer = str(r.json().get("message", {}).get("content", "")).strip()
        return bool(answer), answer, (time.time() - t0) * 1000
    except Exception:
        p = subprocess.run(
            ["ollama", "run", name, question],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        return (
            p.returncode == 0 and bool(p.stdout.strip()),
            p.stdout.strip(),
            (time.time() - t0) * 1000,
        )


def run_export(
    cfg: Config,
    run_id: str | None = None,
    base_model: str | None = None,
    output_dir: Path | None = None,
    ollama_name: str | None = None,
    create: bool = True,
    force_gguf: bool = False,
    verify: bool = True,
) -> dict[str, Any]:
    reg = read_registry(cfg.paths.registry) or {}
    base_model = base_model or reg.get("base_model") or cfg.base_model
    run_id = run_id or reg.get("run_id")
    if not run_id:
        raise FileNotFoundError(
            "Nenhum run encontrado em ml/registry.json — rode 'train' antes ou passe --run-id."
        )
    adapter_dir = cfg.paths.runs / run_id / "adapter"
    if not adapter_dir.exists() and reg.get("adapter_path"):
        adapter_dir = cfg.root / reg["adapter_path"]
    if not adapter_dir.exists():
        raise FileNotFoundError(f"adapter não encontrado: {adapter_dir}")
    ollama_name = ollama_name or str(cfg.export.get("ollama_model", "asclepio-med"))
    out_dir = output_dir or (cfg.paths.models / ollama_name)

    report: dict[str, Any] = {
        "run_id": run_id,
        "base_model": base_model,
        "adapter": str(adapter_dir),
        "ollama_model": ollama_name,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    report.update(merge_adapter(base_model, adapter_dir, out_dir))
    family = detect_family(base_model, report.get("model_type"))

    def write_modelfile(from_line: str) -> None:
        (out_dir / "Modelfile").write_text(
            render_modelfile(
                from_line,
                SYSTEM_PROMPT,
                family,
                float(cfg.export.get("temperature", 0.1)),
                int(cfg.export.get("num_ctx", 4096)),
                int(cfg.export.get("num_predict", 512)),
                base_model,
                run_id,
            ),
            encoding="utf-8",
        )

    write_modelfile("./")
    report["modelfile"] = str(out_dir / "Modelfile")
    report["chat_template_family"] = family
    report["export_method"] = "safetensors"

    if create:
        if not ollama_available():
            log(
                "[yellow]Ollama não encontrado/ativo — Modelfile gerado, mas o modelo não foi registrado.[/]"
            )
            report["ollama_created"] = False
            report["ollama_error"] = "ollama indisponível"
        else:
            ok, out = (
                (False, "forçado GGUF") if force_gguf else create_ollama_model(out_dir, ollama_name)
            )
            if not ok:
                log(
                    f"[yellow]Importação direta de safetensors falhou/ignorada: {out[-300:]}. Tentando GGUF…[/]"
                )
                try:
                    gguf = convert_to_gguf(out_dir, cfg.paths.cache)
                    write_modelfile(f"./{gguf.name}")
                    report["export_method"] = "gguf"
                    ok, out = create_ollama_model(out_dir, ollama_name)
                except Exception as exc:
                    ok, out = False, f"{out}\n--- fallback GGUF ---\n{exc}"
            report["ollama_created"] = ok
            if not ok:
                report["ollama_error"] = out[-2000:]
                log(f"[red]Falha ao criar '{ollama_name}' no Ollama.[/] {out[-500:]}")
            else:
                log(
                    f"[green]Modelo '{ollama_name}' criado no Ollama ({report['export_method']}).[/]"
                )
                if verify:
                    vok, answer, ms = verify_ollama_model(ollama_name)
                    report["verify"] = {
                        "ok": vok,
                        "question": VERIFY_QUESTION,
                        "answer": answer[:2000],
                        "latency_ms": round(ms),
                    }
                    log(
                        f"verificação ({ms / 1000:.1f}s): {answer[:300]}…"
                        if vok
                        else "[red]verificação falhou[/]"
                    )

    write_json(out_dir / "export_report.json", report)
    if reg:
        reg.update(
            {
                "merged_path": str(out_dir.relative_to(cfg.root))
                if out_dir.is_relative_to(cfg.root)
                else str(out_dir),
                "ollama_model": ollama_name,
                "exported_at": report["exported_at"],
                "export_method": report["export_method"],
                "ollama_created": report.get("ollama_created"),
            }
        )
        write_registry(cfg.paths.registry, reg)
    return report
