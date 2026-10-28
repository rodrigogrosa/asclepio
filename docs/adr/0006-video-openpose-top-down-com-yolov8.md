# ADR-0006: Vídeo com OpenPose (pesos oficiais da CMU via OpenCV DNN) em modo top-down sobre o YOLOv8

- **Status**: aceito · **Data**: 2026-10-28 · **Fase**: 4

## Contexto
O edital pede análise de vídeos clínicos (fisioterapia ou cirurgia) com **OpenPose** para postura e
**YOLOv8** para objetos e áreas críticas, gerando relatórios de desvios. O OpenPose original é C++/Caffe
(compilação pesada, GPU) e o servidor da CMU com os pesos está fora do ar.

## Decisão
- **OpenPose COCO 18 pontos com os pesos oficiais** (`pose_iter_440000.caffemodel`, MD5
  `5156d31f…2939`, igual ao `getModels.sh` da CMU), executado pelo **OpenCV DNN** — sem compilar o
  OpenPose, roda em CPU no Mac, no Linux e no container. Espelho do arquivo conferido por SHA-256
  (`multimodal/asclepio_multimodal/assets.py`).
- **Top-down**: o **YOLOv8n** encontra as pessoas; o OpenPose estima a pose de cada recorte. Evita o
  agrupamento por PAF (multi-pessoa) e reaproveita a mesma passada do YOLO para objetos e zonas.
- **OpenCV < 5**: o OpenCV 5 removeu o importador Caffe; a dependência fica fixada em 4.x.
- Backend alternativo `POSE_BACKEND=yolov8-pose` (mais rápido) com mapeamento COCO 17 → 18.
- Regras clínicas por perfil (fisioterapia, quarto, cirurgia) **e** um detector não supervisionado
  sobre as features de movimento: o que foge do protocolo e o que foge do padrão do próprio paciente.

## Alternativas
- Compilar o OpenPose (C++/CUDA): inviável para quem vai rodar o projeto em casa.
- Só YOLOv8-pose ou MediaPipe: não atende literalmente "OpenPose" do edital — fica como opção.
- Treinar o YOLOv8 com instrumental cirúrgico: exige dataset rotulado; fica como trabalho futuro.

## Consequências
+ Modelos pedidos no edital, reprodutíveis, com checksum. + Sem GPU. − OpenPose em CPU custa
~0,35 s por quadro: a análise amostra 5 quadros/s (`VIDEO_SAMPLE_FPS`) e roda em segundo plano.
− Licença do OpenPose é acadêmica/não comercial e a do Ultralytics é AGPL-3.0: adequado ao projeto
acadêmico, a revisar em produção.
