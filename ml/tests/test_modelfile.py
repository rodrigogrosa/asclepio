from __future__ import annotations

from asclepio_ml.export import detect_family, render_modelfile
from asclepio_ml.prompts import SYSTEM_PROMPT


def test_render_modelfile_chatml():
    mf = render_modelfile(
        "./",
        SYSTEM_PROMPT,
        "chatml",
        temperature=0.1,
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        run_id="r1",
    )
    assert mf.startswith("# Modelfile")
    assert "\nFROM ./\n" in mf
    assert "PARAMETER temperature 0.1" in mf
    assert "<|im_start|>assistant" in mf and "<|im_end|>" in mf
    assert 'SYSTEM """' in mf and "Asclépio" in mf and "NUNCA prescreva" in mf
    assert 'PARAMETER stop "<|im_end|>"' in mf


def test_render_modelfile_gguf_and_families():
    mf = render_modelfile("./asclepio-med.gguf", family="llama3")
    assert "FROM ./asclepio-med.gguf" in mf and "<|eot_id|>" in mf
    assert detect_family("Qwen/Qwen2.5-0.5B-Instruct") == "chatml"
    assert detect_family("meta-llama/Llama-3.2-1B-Instruct") == "llama3"
    assert detect_family("TinyLlama/TinyLlama-1.1B-Chat-v1.0") == "zephyr"
    assert detect_family("x", "qwen2") == "chatml"
