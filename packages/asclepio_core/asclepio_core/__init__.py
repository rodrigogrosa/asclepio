"""asclepio_core — núcleo compartilhado entre backend (API) e pipeline de ML.

Módulos:
- anonymizer: detecção/anonimização de PII (LGPD) antes de qualquer dado chegar à LLM.
- clinical_rules: escores (qSOFA, NEWS2), valores críticos de exames, risco do paciente, gatilhos de protocolo.
- guardrails: política de atuação do assistente (entrada e saída) — nunca prescrever sem validação humana.
- knowledge: leitura e chunking da base de conhecimento (protocolos, FAQ, modelos de documentos).
- synthetic: geração determinística de pacientes/prontuários sintéticos (com PII fictícia para demonstrar anonimização).
"""

__version__ = "1.2.0"
