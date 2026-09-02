API = "/api/v1"


def test_docs_hub_permissions(client, medico, auditor):
    assert (
        client.get(f"{API}/docs-hub", headers=medico).status_code == 403
    )  # perfil clínico não vê a central
    r = client.get(f"{API}/docs-hub", headers=auditor)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 15
    cats = {c["id"] for c in data["categories"]}
    assert {
        "relatorios",
        "processo",
        "arquitetura",
        "dados-ml",
        "seguranca-operacao",
        "diagramas",
    } <= cats


def test_docs_hub_read_and_download(client, admin):
    doc = client.get(f"{API}/docs-hub/relatorio-tecnico", headers=admin).json()
    assert doc["format"] == "md" and "Checklist de conformidade" in doc["content"]
    mmd = client.get(f"{API}/docs-hub/diagrama-fluxo", headers=admin).json()
    assert mmd["format"] == "mmd" and "human_review" in mmd["content"]
    d = client.get(f"{API}/docs-hub/evidencias/download", headers=admin)
    assert d.status_code == 200 and "attachment" in d.headers["content-disposition"]
    assert client.get(f"{API}/docs-hub/nao-existe", headers=admin).status_code == 404
    # PDF: sem leitura embutida, mas com download (quando existir)
    meta = next(
        x
        for c in client.get(f"{API}/docs-hub", headers=admin).json()["categories"]
        for x in c["documents"]
        if x["id"] == "relatorio-tecnico-pdf"
    )
    assert meta["readable"] is False


def test_docs_hub_inlines_images(client, admin):
    doc = client.get(f"{API}/docs-hub/fine-tuning", headers=admin).json()
    assert "data:image/png;base64," in doc["content"]  # gráficos de avaliação embutidos
