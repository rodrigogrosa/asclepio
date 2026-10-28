"""asclepio_multimodal — Fase 4: monitoramento contínuo do paciente com dados multimodais.

Módulos (todos devolvem os tipos de ``schemas``, para o backend persistir, alertar e fundir sem
conhecer o modelo por trás):

- video: OpenPose (postura) + YOLOv8 (pessoas, objetos e áreas críticas) → desvios do procedimento.
- audio: Azure Speech to Text + Azure Text Analytics (termos críticos, sentimento) + acústica da voz
  (Praat: jitter, shimmer, HNR, pausas) + eventos sonoros AudioSet (tosse, respiração).
- anomaly: detecção em tempo real em sinais vitais, prescrições e mobilidade na internação.
- fusion: fusão tardia das modalidades num risco único com as evidências de cada uma.

Imports pesados (torch, cv2, Azure SDK) ficam dentro dos submódulos: importar o pacote é barato.
"""

__version__ = "2.0.0"
