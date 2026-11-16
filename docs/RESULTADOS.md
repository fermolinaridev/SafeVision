# Resultados experimentais

## Qualidade da detecção

A avaliação usa as 200 imagens da validação oficial do **Ultralytics Construction-PPE de novembro de 2026**. Em ambos os modelos, as classes avaliadas são pessoa, capacete, colete, sem capacete e sem colete. As métricas de mAP usam IoU de 0,50 a 0,95 em incrementos de 0,05, AP interpolada em 101 pontos e predições a partir de confiança 0,01. Precisão, recall, F1 e matriz de confusão usam o limiar operacional de 0,35 e IoU de 0,50. A média é macro sobre as cinco classes.

| Modelo | Resolução | mAP@50 | mAP@50:95 | Precisão | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| YOLO26s IAAC | 640 | 0,6191 | 0,3841 | 0,7225 | 0,6125 | 0,6594 |
| YOLO26n ajustado | 640 | 0,7530 | 0,5303 | 0,9445 | 0,6768 | 0,7782 |
| YOLO26n ajustado | 416 | 0,6671 | 0,4756 | 0,9361 | 0,6163 | 0,7343 |

O ajuste partiu do YOLO26n pré-treinado em COCO e usou 720 imagens de treino, 80 de desenvolvimento, 16 épocas, resolução de treino 416, lote 8 e semente 713. A seleção do checkpoint usou o subconjunto de desenvolvimento. O checkpoint ajustado local está em `models/construction-ppe.pt` e tem SHA-256 `a3da1098b6e4f92715f8b592dd19f44a6057db819bddbb5e175726a795161895`. Os resultados por classe incluem falsos positivos, falsos negativos e a matriz de confusão com a classe de fundo. [Checkpoint inicial](../eval/baseline.json) · [Ajustado em 640](../eval/specialized.json) · [Ajustado em 416](../eval/specialized-416.json)

O modelo ajustado elevou o recall da classe explícita **sem capacete** de 14,53% para 44,13%. O recall de **sem colete** variou de 56,92% para 55,38%. Essas métricas avaliam caixas do detector. A regra de ocorrência também considera associação espacial e persistência no tempo.

### Condições de captura

| Recorte | Imagens | IAAC a 640, mAP@50:95 | Ajustado a 640, mAP@50:95 |
|---|---:|---:|---:|
| Luminância média abaixo de 90/255 | 14 | 0,4452 | 0,5864 |
| Mediana da área das pessoas abaixo de 4% da imagem | 49 | 0,2807 | 0,3450 |
| Visada elevada | 11 | 0,2970 | 0,3235 |
| Visada próxima ao nível dos olhos | 11 | 0,5890 | 0,8233 |
| Oclusão parcial | 11 | 0,3768 | 0,6715 |

Os três últimos recortes foram rotulados manualmente em uma amostra fixa e podem se sobrepor. Os recortes pequenos servem como diagnóstico. A frequência de falsos alarmes por hora e a taxa de duplicidade em campo precisam de vídeos anotados da operação alvo. No teste de integração, o clipe controlado com uma pessoa e uma ausência persistente de colete gerou uma ocorrência e uma evidência. [Lista de imagens por condição](../eval/conditions.csv)

## Desempenho

Apple M5, macOS ARM64, 16 GiB de RAM, Python 3.14.5, PyTorch 2.15.0 e ONNX Runtime 1.32.0. Cada linha usa 50 inferências após aquecimento em cinco imagens de exemplo. A latência inclui preprocessamento e retorno de caixas via Ultralytics. PyTorch usou dois threads, e ONNX Runtime usou o pool automático de até oito threads do Ultralytics. FPS é a taxa calculada a partir da latência média. RSS é o pico de memória residente do processo em MiB.

| Modelo / runtime | Dispositivo | Resolução | Média (ms) | P95 (ms) | FPS | Pico RSS (MiB) |
|---|---|---:|---:|---:|---:|---:|
| IAAC / PyTorch | CPU | 640 | 52,09 | 54,87 | 19,20 | 554,80 |
| IAAC / ONNX Runtime | CPU | 640 | 46,74 | 56,41 | 21,40 | 676,23 |
| IAAC / PyTorch | GPU Apple MPS | 640 | 18,56 | 20,41 | 53,87 | 651,00 |
| Ajustado / PyTorch | CPU | 640 | 26,86 | 31,03 | 37,23 | 452,91 |
| Ajustado / ONNX Runtime | CPU | 640 | 18,29 | 24,54 | 54,69 | 527,98 |
| Ajustado / PyTorch | CPU | 416 | 13,21 | 14,62 | 75,71 | 410,22 |

O checkpoint ajustado a 416 prioriza a velocidade e apresentou mAP@50:95 de 0,4756. A 640, a versão ONNX reduziu a latência média do ajustado em 32%, com aumento de cerca de 75 MiB no pico de RSS. No Docker local, 15 requisições sequenciais de imagem após aquecimento apresentaram média de 280,67 ms ponta a ponta e 271,42 ms no estágio de inferência. O primeiro clipe de 12 s processado nativamente usou 60 frames em 5,039 s. O clipe controlado de 4,5 s processado pelo worker no Docker usou 23 frames em 4,334 s em uma execução aquecida. [Benchmark de inferência](../eval/benchmark.json) · [Medição HTTP](../eval/api-benchmark.json)

## Reproduzir

```bash
pip install -e '.[test,onnx]'
python scripts/fetch_model.py
mkdir -p data
curl -fL https://github.com/ultralytics/assets/releases/download/v0.0.0/construction-ppe.zip -o data/construction-ppe.zip
unzip -q data/construction-ppe.zip -d data
python -m scripts.train --dataset data/construction-ppe --archive data/construction-ppe.zip --epochs 16 --size 416 --device mps
cp runs/construction-ppe/weights/best.pt models/construction-ppe.pt
python -m scripts.evaluate models/construction-ppe.pt --dataset data/construction-ppe --output eval/reproducao.json --min-map 0.50
python -m scripts.benchmark models/construction-ppe.pt --export
python -m scripts.benchmark models/construction-ppe.onnx frontend/public/examples/*.jpg --samples 50
```

Para repetir o treino em outra plataforma, escolha `--device cpu` ou o índice de uma GPU CUDA disponível. O script confere o SHA-256 do arquivo do dataset. Use `--min-map 0.30` para uma checagem de regressão do checkpoint IAAC e `--min-map 0.50` para a versão ajustada a 640 neste conjunto.

O Docker e o Space usam o checkpoint público fixado como padrão, de modo que o build funciona a partir do código fonte. Para usar o checkpoint ajustado ou uma exportação ONNX em execução nativa, aponte `SAFEVISION_WEIGHTS` para o arquivo. A execução de ONNX exige o extra `onnx`, incluído na imagem Docker. Use `SAFEVISION_IMAGE_SIZE=640` com os arquivos ONNX exportados nos comandos acima.

Para usar o checkpoint ajustado com a instalação completa, acrescente um arquivo Compose com os volumes correspondentes e defina o caminho montado em `.env`:

```yaml
services:
  api:
    volumes: ["./models/construction-ppe.pt:/app/models/construction-ppe.pt:ro"]
  worker:
    volumes: ["./models/construction-ppe.pt:/app/models/construction-ppe.pt:ro"]
```

Defina `SAFEVISION_WEIGHTS=/app/models/construction-ppe.pt` e inicie com `docker compose -f compose.yaml -f seu-arquivo.yaml up -d`. A família completa de modelos e pesos derivados segue a licença AGPL-3.0 do Ultralytics. [Dataset e licença](https://docs.ultralytics.com/datasets/detect/construction-ppe/) · [Licença dos modelos YOLO](https://www.ultralytics.com/license)
