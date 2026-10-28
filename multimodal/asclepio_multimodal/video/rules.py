"""Perfis de análise (fisioterapia, quarto, cirurgia): protocolos, limiares e regras que viram
``Finding``. Os limiares são heurísticas clínicas declaradas aqui (e gravadas em
``details["protocolo"]``), não valores aprendidos; mudar um protocolo é editar um dicionário.

Instrumental cirúrgico específico (pinça, bisturi, compressa) não existe nas 80 classes do COCO:
detectá-lo exigiria treinar o YOLOv8 num dataset próprio — fica como trabalho futuro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..schemas import Finding
from .detect import Amostra, Poligono
from .kinematics import Cinematica, _nanstat, amplitude, interpolar


# --- protocolos e perfis ----------------------------------------------------------------------
@dataclass(frozen=True)
class Protocolo:
    titulo: str
    unilateral: bool  # perna de apoio única: a assimetria E/D não se aplica
    flexao_min: float  # flexão do joelho esperada no ponto mais fundo (graus)
    tronco_max: float  # inclinação máxima do tronco em relação à vertical (graus)
    valgo_max: float = 10.0  # valgo dinâmico aceito (graus)
    assimetria_max: float = 15.0  # diferença E/D de flexão (%)
    cv_rom_max: float = 0.25  # variação (desvio/média) da amplitude entre repetições
    oscilacao_max: float = 0.5  # deslocamento lateral do quadril / comprimento do tronco


PROTOCOLOS: dict[str, Protocolo] = {
    "agachamento": Protocolo("Agachamento", False, flexao_min=70.0, tronco_max=50.0),
    "agachamento_unipodal": Protocolo(
        "Agachamento unipodal", True, flexao_min=40.0, tronco_max=30.0, oscilacao_max=0.4
    ),
}


@dataclass(frozen=True)
class Perfil:
    nome: str
    max_pessoas_pose: int  # quantas pessoas passam pelo OpenPose em cada quadro
    zonas: dict[str, Poligono] = field(default_factory=dict)  # áreas críticas padrão


PERFIS: dict[str, Perfil] = {
    "fisioterapia": Perfil("fisioterapia", 1),
    "quarto": Perfil("quarto", 2),
    # sem imagem real da sala cirúrgica o padrão é uma área central; a equipe redefine por polígono
    "cirurgia": Perfil(
        "cirurgia", 3, {"area_esteril": [(0.2, 0.15), (0.8, 0.15), (0.8, 0.95), (0.2, 0.95)]}
    ),
}

OBJETOS_PROIBIDOS = {
    "cell phone": "celular", "bottle": "garrafa", "cup": "copo", "wine glass": "taça",
    "sandwich": "alimento", "banana": "alimento", "apple": "alimento", "backpack": "mochila",
    "handbag": "bolsa",
}  # fmt: skip

# Quarto: parâmetros das regras (s, graus, comprimentos de tronco)
QUEDA = {
    "dy_min": 0.5, "janela_s": 2.0, "asp_min": 1.0, "tronco_min": 60.0, "altura_min": 0.5,
    "perm_s": 1.0,
}  # fmt: skip
# energia_max acima do ruído de pose medido no UR Fall (5º percentil de 0,1–0,25 tronco/s)
IMOBILIDADE = {"energia_max": 0.3, "min_s": 60.0}
AGITACAO = {"energia_min": 0.8, "desloc_max": 0.3, "min_s": 5.0}


def _achado(
    code: str, titulo: str, descricao: str, severidade: str, modalidade: str, score: float,
    t0: float | None, t1: float | None, evidence: dict[str, Any], recomendacao: str,
    t_quadro: float | None = None,
) -> Finding:  # fmt: skip
    ev = {k: _json(v) for k, v in evidence.items()}
    ev["t_quadro_s"] = round(float(t_quadro if t_quadro is not None else (t0 or 0.0)), 2)
    return Finding(
        code=code, title=titulo, description=descricao, severity=severidade,  # type: ignore[arg-type]
        modality=modalidade,  # type: ignore[arg-type]
        score=float(np.clip(score, 0, 1)), t_start=None if t0 is None else round(float(t0), 2),
        t_end=None if t1 is None else round(float(t1), 2), evidence=ev, recommendation=recomendacao,
    )  # fmt: skip


def _json(v: Any) -> Any:
    if isinstance(v, float | np.floating):
        return None if not np.isfinite(v) else round(float(v), 2)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, list | tuple):
        return [_json(x) for x in v]
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    return v


def _media_movel(x: np.ndarray, fps: float, vazio: float, janela_s: float = 2.0) -> np.ndarray:
    """Média móvel de ``janela_s`` (NaN vira ``vazio``): o balanço de um membro passa por
    instantes de velocidade zero a cada ciclo e não pode quebrar o trecho."""
    w = max(1, round(janela_s * fps))
    return np.convolve(np.nan_to_num(x, nan=vazio), np.ones(w) / w, mode="same")


def trechos(
    mascara: np.ndarray, t: np.ndarray, min_s: float, passo_s: float
) -> list[tuple[int, int]]:
    """Sequências contíguas de True com duração ≥ ``min_s`` (cada amostra vale ``passo_s``)."""
    saida, i, n = [], 0, len(mascara)
    while i < n:
        if not mascara[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and mascara[j + 1]:
            j += 1
        if t[j] - t[i] + passo_s >= min_s:
            saida.append((i, j))
        i = j + 1
    return saida


# --- fisioterapia -------------------------------------------------------------------------------
def regras_fisioterapia(
    c: Cinematica, p: Protocolo, reps: list[dict[str, Any]], segmentos: list[dict[str, Any]]
) -> tuple[list[Finding], list[dict[str, Any]]]:
    """Devolve (achados, detalhe por repetição)."""
    s = c.s
    frontal = c.vista == "frontal"
    por_rep = []
    for n, r in enumerate(reps, 1):
        a, b = r["i_ini"], r["i_fim"] + 1
        fd, fe = (
            180 - _nanstat(np.min, s["joelho_d"][a:b]),
            180 - _nanstat(np.min, s["joelho_e"][a:b]),
        )
        por_rep.append(
            {
                "n": n, "t_ini": r["t_ini"], "t_min": r["t_min"], "t_fim": r["t_fim"],
                "duracao_s": r["duracao_s"], "flexao_graus": 180 - r["min_graus"],
                "rom_graus": r["rom_graus"], "tronco_max_graus": _nanstat(np.max, s["tronco"][a:b]),
                "valgo_max_graus": max(
                    _nanstat(np.max, s["valgo_d"][a:b]), _nanstat(np.max, s["valgo_e"][a:b])
                ) if frontal else float("nan"),
                "assimetria_pct": 100 * abs(fd - fe) / max(fd, fe, 1e-6) if frontal and not p.unilateral else float("nan"),
                "oscilacao_lateral": amplitude(s["x_quadril"][a:b]) if frontal else float("nan"),
            }
        )  # fmt: skip
    f: list[Finding] = []
    if not reps:
        f.append(
            _achado(
                "video.sem_repeticoes", f"Nenhuma repetição de {p.titulo.lower()} identificada",
                "Não foi possível contar repetições do exercício: o corpo pode estar parcialmente "
                "fora do quadro ou o movimento é menor que o esperado.",
                "info", "video", 0.2, None, None,
                {"vista": c.vista, "quadros_validos_pct": 100 * float(np.isfinite(s["tronco"]).mean())},
                "Reposicione a câmera para enquadrar o corpo inteiro e repita a gravação.",
            )
        )  # fmt: skip
    else:
        f += _regras_reps(c, p, por_rep)
    f += _atipicos(segmentos, "video")
    return f, por_rep


def _intervalo(rs: list[dict[str, Any]]) -> tuple[float, float, float]:
    """Intervalo e instante-chave da repetição de pior valor (a primeira da lista)."""
    return rs[0]["t_ini"], rs[0]["t_fim"], rs[0]["t_min"]


def _regras_reps(c: Cinematica, p: Protocolo, reps: list[dict[str, Any]]) -> list[Finding]:
    f: list[Finding] = []
    nome = p.titulo.lower()
    flexoes = np.array([r["flexao_graus"] for r in reps])
    rasas = sorted(
        (r for r in reps if r["flexao_graus"] < p.flexao_min), key=lambda r: r["flexao_graus"]
    )
    if rasas:
        metade = len(rasas) >= len(reps) / 2
        t0, t1, tq = _intervalo(rasas)
        f.append(
            _achado(
                "video.amplitude_reduzida", f"Amplitude do {nome} abaixo do esperado",
                f"{len(rasas)} de {len(reps)} repetições ficaram abaixo da flexão de joelho esperada "
                f"({p.flexao_min:.0f}°); a menor foi {rasas[0]['flexao_graus']:.0f}°.",
                "atencao" if metade else "info", "video", 1 - rasas[0]["flexao_graus"] / p.flexao_min,
                t0, t1,
                {"flexao_mediana_graus": float(np.median(flexoes)), "limite_graus": p.flexao_min,
                 "repeticoes_afetadas": [r["n"] for r in rasas]},
                "Reforçar a descida controlada até a amplitude prescrita; se houver dor ou limitação, "
                "registrar e reavaliar a progressão da carga.", tq,
            )
        )  # fmt: skip
    for chave, code, titulo, limite, unid, msg, rec in (
        ("tronco_max_graus", "video.tronco_compensacao", f"Inclinação excessiva do tronco no {nome}",
         p.tronco_max, "°", "inclinação do tronco acima do limite — sinal de compensação",
         "Orientar postura do tronco e avaliar mobilidade de tornozelo/quadril e força de glúteos."),
        ("valgo_max_graus", "video.valgo_dinamico", f"Valgo dinâmico do joelho no {nome}",
         p.valgo_max, "°", "joelho se aproxima da linha média durante a descida",
         "Trabalhar controle de quadril (abdutores/rotadores) e alinhamento joelho-pé."),
        ("assimetria_pct", "video.assimetria", f"Assimetria entre os membros no {nome}",
         p.assimetria_max, "%", "diferença de flexão entre joelho direito e esquerdo",
         "Investigar dor, fraqueza ou limitação unilateral e corrigir o apoio de peso."),
        ("oscilacao_lateral", "video.perda_equilibrio", f"Oscilação lateral / perda de equilíbrio no {nome}",
         p.oscilacao_max, "× tronco", "deslocamento lateral do quadril acima do limite",
         "Reduzir a dificuldade (apoio de mão, menor amplitude) e treinar controle postural."),
    ):  # fmt: skip
        if chave == "oscilacao_lateral" and not p.unilateral:
            continue  # sem apoio único, a oscilação lateral não indica perda de equilíbrio
        ruins = sorted(
            (r for r in reps if np.isfinite(r[chave]) and r[chave] > limite),
            key=lambda r: -r[chave],
        )
        if not ruins:
            continue
        pior = ruins[0]
        t0, t1, tq = _intervalo(ruins)
        f.append(
            _achado(
                code, titulo,
                f"{len(ruins)} de {len(reps)} repetições: {msg} (pior: {pior[chave]:.1f}{unid}; "
                f"limite {limite:g}{unid}).",
                "atencao", "video", (pior[chave] - limite) / max(limite, 1e-6) + 0.3, t0, t1,
                {"maximo": pior[chave], "limite": limite, "repeticoes_afetadas": [r["n"] for r in ruins]},
                rec, tq,
            )
        )  # fmt: skip
    roms = np.array([r["rom_graus"] for r in reps])
    if len(reps) >= 3 and roms.mean() > 0 and roms.std() / roms.mean() > p.cv_rom_max:
        cv = float(roms.std() / roms.mean())
        outra = int(np.argmax(np.abs(roms - roms.mean())))
        f.append(
            _achado(
                "video.repeticoes_inconsistentes", f"Repetições inconsistentes no {nome}",
                f"A amplitude varia {100 * cv:.0f}% entre as repetições (limite {100 * p.cv_rom_max:.0f}%).",
                "atencao", "video", cv, reps[outra]["t_ini"], reps[outra]["t_fim"],
                {"cv_rom": cv, "limite": p.cv_rom_max, "rom_graus": roms.tolist()},
                "Padronizar o ritmo e a amplitude; fadiga ou perda de controle podem explicar a variação.",
                reps[outra]["t_min"],
            )
        )  # fmt: skip
    return f


def _atipicos(segmentos: list[dict[str, Any]], modalidade: str) -> list[Finding]:
    f = []
    for k, sg in enumerate(segmentos):
        z = sg["z"]
        f.append(
            _achado(
                "video.padrao_atipico", "Trecho atípico em relação ao padrão do próprio paciente",
                f"Entre {sg['t_ini']:.1f}s e {sg['t_fim']:.1f}s o movimento difere do restante da "
                f"sessão (z robusto {z:.1f}; característica: {sg['caracteristica']}).",
                "atencao" if z >= 6 and 0 < k < len(segmentos) - 1 else "info", modalidade,
                min(1.0, z / 10), sg["t_ini"], sg["t_fim"],
                {"z_robusto": z, "caracteristica": sg["caracteristica"]},
                "Rever o trecho no vídeo anotado; pode ser ajuste de posição, fadiga ou compensação.",
            )
        )  # fmt: skip
    return f


# --- quarto (internação) ---------------------------------------------------------------------
def detectar_quedas(
    t: np.ndarray, topo: np.ndarray, altura: np.ndarray, largura: np.ndarray, tronco: np.ndarray,
    *, dy_min: float = 0.5, janela_s: float = 1.0, asp_min: float = 1.0, tronco_min: float = 60.0,
    perm_s: float = 1.0, frac_min: float = 0.6, altura_min: float = 0.5,
) -> list[dict[str, Any]]:  # fmt: skip
    """Queda = descida brusca + postura deitada + permanência.

    ``topo``/``altura``/``largura``: topo, altura e largura (px) da caixa da pessoa principal
    (NaN sem detecção); ``tronco``: inclinação do tronco do OpenPose (NaN sem pose).
    Descida: o topo desce ≥ ``dy_min`` alturas-de-referência em ≤ ``janela_s``. Se as
    observações acabam antes de ``perm_s`` o evento sai com ``permanencia_confirmada=False``. Postura deitada:
    largura/altura ≥ ``asp_min`` ou tronco ≥ ``tronco_min`` em ≥ ``frac_min`` das amostras dos
    ``perm_s`` seguintes, sem a pessoa voltar a subir.
    """
    n = len(t)
    # lacunas de até 4 amostras a 5 fps (0,8 s + folga de ponto flutuante) são interpoladas
    topo, altura, largura = (interpolar(x, t, 0.85) for x in (topo, altura, largura))
    if n < 3 or not np.isfinite(altura).any():
        return []
    ref = float(np.nanpercentile(altura, 90))  # altura de pé: percentil alto da caixa
    # caixa minúscula (< 10% da área de uma pessoa de pé) é detecção espúria, não a pessoa
    espuria = altura * largura < 0.1 * ref * ref
    topo, altura, largura = (np.where(espuria, np.nan, x) for x in (topo, altura, largura))
    y = topo / ref
    # deitada: caixa mais larga que alta, tronco horizontal ou corpo colapsado a < ``altura_min``
    # da altura de pé (deitado de frente para a câmera a caixa fica "em pé", mas muito baixa)
    deitada = ((largura / altura) >= asp_min) | (tronco >= tronco_min) | (altura / ref < altura_min)
    deitada &= np.isfinite(y)
    eventos, i = [], 0
    while i < n - 1:
        if not np.isfinite(y[i]):
            i += 1
            continue
        fim = [j for j in range(i + 1, n) if t[j] - t[i] <= janela_s and np.isfinite(y[j])]
        if not fim:
            i += 1
            continue
        j = max(fim, key=lambda k: y[k])
        if y[j] - y[i] < dy_min:
            i += 1
            continue
        # observações a partir do fim da descida (inclusive: em vídeos cortados é a única)
        pos = [k for k in range(j, n) if t[k] - t[j] <= perm_s and np.isfinite(y[k])]
        if deitada[pos].mean() >= frac_min and (y[pos] >= y[j] - 0.25).all():
            confirmada = len(pos) >= 2 and t[pos[-1]] - t[j] >= perm_s * 0.8
            k = j
            while k + 1 < n and (deitada[k + 1] or not np.isfinite(y[k + 1])):
                k += 1
            eventos.append(
                {
                    "t_ini": float(t[i]), "t_queda": float(t[j]), "t_fim": float(t[k]),
                    "descida_alturas": float(y[j] - y[i]),
                    "velocidade_alturas_s": float((y[j] - y[i]) / max(t[j] - t[i], 1e-6)),
                    "aspecto_pos": _nanstat(np.median, (largura / altura)[pos]),
                    "tronco_pos_graus": _nanstat(np.median, tronco[pos]),
                    "permanencia_s": float(t[k] - t[j]),
                    "permanencia_confirmada": bool(confirmada),
                }
            )  # fmt: skip
            i = k + 1
        else:
            i = j + 1
    return eventos


def regras_quarto(
    c: Cinematica, amostras: list[Amostra], caixa: np.ndarray, zonas: dict[str, Poligono],
    dim: tuple[int, int],
) -> list[Finding]:  # fmt: skip
    """``caixa`` (T, 4): x1, y1, x2, y2 da pessoa principal (NaN sem detecção)."""
    t, s = c.t, c.s
    passo = 1 / c.fps
    f: list[Finding] = []
    for e in detectar_quedas(
        t, caixa[:, 1], caixa[:, 3] - caixa[:, 1], caixa[:, 2] - caixa[:, 0], s["tronco"], **QUEDA
    ):
        ok = e["permanencia_confirmada"]
        f.append(
            _achado(
                "video.queda", "Queda detectada" if ok else "Possível queda",
                f"Descida brusca ({e['descida_alturas']:.1f} alturas do corpo a "
                f"{e['velocidade_alturas_s']:.1f}/s) seguida de postura deitada por "
                f"{e['permanencia_s']:.1f}s"
                + ("." if ok else " (o vídeo termina antes de confirmar a permanência).")
                + " Possível queda do paciente.",
                "critico" if ok else "atencao", "mobilidade",
                (0.6 if ok else 0.4) + 0.4 * min(1.0, e["velocidade_alturas_s"] / 2),
                e["t_ini"], e["t_fim"], e,
                "Acionar a equipe de enfermagem imediatamente, avaliar o paciente no local e "
                "registrar o evento conforme o protocolo institucional de quedas.", e["t_queda"],
            )
        )  # fmt: skip
    presente = np.isfinite(caixa[:, 0])
    parado = presente & (_media_movel(s["energia"], c.fps, 9) < IMOBILIDADE["energia_max"])
    for a, b in trechos(parado, t, IMOBILIDADE["min_s"], passo):
        f.append(
            _achado(
                "video.imobilidade", "Imobilidade prolongada",
                f"Sem movimento relevante por {t[b] - t[a] + passo:.0f}s.", "atencao",
                "mobilidade", 0.5, t[a], t[b],
                {"duracao_s": t[b] - t[a] + passo, "limiar_energia": IMOBILIDADE["energia_max"]},
                "Verificar o paciente; considerar mudança de decúbito conforme o plano de cuidado.",
            )
        )  # fmt: skip
    agitado = (
        presente
        & (_media_movel(s["energia_rel"], c.fps, 0) >= AGITACAO["energia_min"])
        & (_media_movel(s["v_quadril"], c.fps, 9) < AGITACAO["desloc_max"])
    )
    for a, b in trechos(agitado, t, AGITACAO["min_s"], passo):
        f.append(
            _achado(
                "video.agitacao", "Agitação motora",
                f"Movimento intenso de membros sem deslocamento do corpo por {t[b] - t[a] + passo:.0f}s.",
                "atencao", "mobilidade", 0.5, t[a], t[b],
                {"energia_media": _nanstat(np.mean, s["energia_rel"][a : b + 1]),
                 "limiar": AGITACAO["energia_min"]},
                "Avaliar dor, desconforto, delirium ou necessidade de contenção segura/medicação.",
            )
        )  # fmt: skip
    f += _regras_leito(c, amostras, caixa, zonas, dim)
    return f


def _regras_leito(c, amostras, caixa, zonas, dim) -> list[Finding]:
    """Saída do leito e pessoa no chão — só existem quando a equipe define as zonas."""
    t, f = c.t, []
    deitada = (
        np.nan_to_num((caixa[:, 2] - caixa[:, 0]) / (caixa[:, 3] - caixa[:, 1]), nan=0)
        >= QUEDA["asp_min"]
    ) | (np.nan_to_num(c.s["tronco"], nan=0) >= QUEDA["tronco_min"])
    if "leito" in zonas:
        dentro = np.array(
            [bool(a.zonas.get("leito")) and _tem_pessoa(a.zonas["leito"]) for a in amostras]
        )
        presente = np.isfinite(caixa[:, 0])
        # esteve no leito por ≥ 2 s e depois aparece fora dele por ≥ 2 s
        for _a, b in trechos(dentro, t, 2.0, 1 / c.fps):
            fora = trechos(presente & ~dentro & (np.arange(len(t)) > b), t, 2.0, 1 / c.fps)
            if fora:
                f.append(
                    _achado(
                        "video.saida_leito", "Saída do leito",
                        f"A pessoa deixou a área do leito em {t[b]:.1f}s e permaneceu fora dela.",
                        "atencao", "mobilidade", 0.6, t[b], t[fora[0][1]],
                        {"saida_s": t[b]},
                        "Verificar se a saída foi acompanhada; avaliar risco de queda e necessidade "
                        "de auxílio para deambular.",
                    )
                )  # fmt: skip
                break
    if "chao" in zonas:
        no_chao = np.array([_tem_pessoa(a.zonas.get("chao", [])) for a in amostras]) & deitada
        for a, b in trechos(no_chao, t, 3.0, 1 / c.fps):
            f.append(
                _achado(
                    "video.pessoa_no_chao", "Pessoa deitada no chão",
                    f"Postura deitada na área do chão por {t[b] - t[a] + 1 / c.fps:.0f}s.",
                    "critico", "mobilidade", 0.9, t[a], t[b], {"duracao_s": t[b] - t[a]},
                    "Acionar a equipe e avaliar a pessoa imediatamente.",
                )
            )  # fmt: skip
    return f


def _tem_pessoa(dets) -> bool:
    return any(d.rotulo == "person" for d in dets)


# --- cirurgia ----------------------------------------------------------------------------------
def regras_cirurgia(
    c: Cinematica, amostras: list[Amostra], zonas: dict[str, Poligono], *, max_pessoas: int = 4,
    min_s: float = 2.0, zona: str = "area_esteril",
) -> list[Finding]:  # fmt: skip
    t, passo = c.t, 1 / c.fps
    if zona not in zonas:
        return []
    pessoas = np.array([sum(d.rotulo == "person" for d in a.zonas.get(zona, [])) for a in amostras])
    f: list[Finding] = []
    for a, b in trechos(pessoas > max_pessoas, t, min_s, passo):
        pico = int(pessoas[a : b + 1].max())
        f.append(
            _achado(
                "video.lotacao_area_critica", "Lotação acima do limite na área crítica",
                f"{pico} pessoas na área estéril (limite {max_pessoas}) por {t[b] - t[a] + passo:.0f}s.",
                "critico" if pico > max_pessoas + 2 else "atencao", "video", min(1.0, pico / (2 * max_pessoas)),
                t[a], t[b], {"pessoas_max": pico, "limite": max_pessoas},
                "Reduzir a circulação na área estéril para o mínimo necessário à equipe cirúrgica.",
                t[a + int(np.argmax(pessoas[a : b + 1]))],
            )
        )  # fmt: skip
    for rotulo, pt in OBJETOS_PROIBIDOS.items():
        presente = np.array(
            [any(d.rotulo == rotulo for d in a.zonas.get(zona, [])) for a in amostras]
        )
        for a, b in trechos(presente, t, 1.0, passo):
            f.append(
                _achado(
                    "video.objeto_nao_permitido", f"Objeto não permitido na área crítica: {pt}",
                    f"{pt.capitalize()} detectado dentro da área estéril por {t[b] - t[a] + passo:.0f}s.",
                    "atencao", "video", 0.6, t[a], t[b], {"objeto": rotulo, "objeto_pt": pt},
                    "Retirar o objeto da área estéril e conferir a técnica asséptica.",
                )
            )  # fmt: skip
    entradas = [i for i in range(1, len(t)) if pessoas[i] > 0 and pessoas[i - 1] == 0] + (
        [0] if len(t) and pessoas[0] > 0 else []
    )
    if entradas:
        entradas.sort()
        f.append(
            _achado(
                "video.entrada_zona_critica", "Entrada na área crítica",
                f"Pessoas entraram na área estéril {len(entradas)} vez(es); primeira em "
                f"{t[entradas[0]]:.1f}s.", "info", "video", 0.1, t[entradas[0]], t[entradas[-1]],
                {"entradas": len(entradas), "instantes_s": [t[i] for i in entradas]},
                "Conferir se as entradas correspondem à equipe cirúrgica escalada.",
            )
        )  # fmt: skip
    return f
