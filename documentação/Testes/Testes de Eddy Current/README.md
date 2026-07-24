# Testes de Correntes Parasitas (Eddy Current Test Bench)

Este diretório contém a estrutura de dados, scripts de suporte e a documentação para o banco de ensaios e aquisição de curvas de indutância por correntes parasitas (Eddy Currents).

---

## 📂 Estrutura de Arquivos Organizada

Abaixo está o mapeamento dos arquivos deste subdiretório:

```
documentação/Testes/Testes de Eddy Current/
├── README.md (Este manual)
├── analise_detalhada_dataset.md (Relatório de análise avançada do dataset de 14.000 amostras)
├── datasets/
│   ├── dataset_cupons_indutancia.csv (Base principal de calibração / 19 MB)
│   ├── dataset_cupons_indutancia_backup.csv (Backup geral)
│   ├── dataset_cupons_indutancia_original_dma.csv (Dados puros originais do DMA)
│   ├── dataset_cupons_indutancia_original_ets.csv (Dados puros originais do ETS - depreciado)
│   └── dataset_cupons_indutancia_ets.csv (Registros experimentais de teste)
├── imagens/
│   ├── comparativo_curvas.png (Comparativo de atenuação temporal do sinal)
│   └── visualizacao_sinais_real.png (Sinais brutos digitalizados)
└── scripts/
    ├── analisador_curvas.py (Analisa propriedades geométricas e estatísticas de decaimento das curvas)
    ├── gerador_dataset_sintetico.py (Gera datasets simulados de curvas para testes do classificador)
    └── visualizar_curvas_comparativo.py (Gera visualizações comparativas das curvas salvas)
```

---

## 🖥️ Interface Gráfica Principal: `eddy_current_plotter_gui.py`

A interface gráfica de alta performance é executada a partir do arquivo raiz [eddy_current_plotter_gui.py](file:///c:/Users/AdmPDI/STM32CubeIDE/workspace3/anticorrosao-firmware-eddy-currents-test/eddy_current_plotter_gui.py). Ela utiliza **PyQt5** e **PyQtGraph** para plotagem estável em alta velocidade (10 Hz).

### ⚙️ Como Executar a GUI
Garante que as dependências do Python estejam instaladas no sistema:
```bash
pip install pyqt5 pyqtgraph pyserial numpy
```
Para executar o painel de controle e aquisição:
```bash
python eddy_current_plotter_gui.py
```

---

## 🔌 Especificação do Protocolo Serial (MCU ➔ PC)

A comunicação é feita via porta serial virtual (VCP) USB com taxa de **921.600 bps** utilizando transmissão direta por DMA.

### 📦 Estrutura do Pacote Binário (518 bytes)

Cada transiente de decaimento lido do sensor é enviado pelo STM32H7 para o computador como um bloco binário estruturado:

| Offset (Bytes) | Tamanho (Bytes) | Formato | Descrição |
|---|---|---|---|
| `0` | `512` | `uint16_t[256]` | Amostras brutas do sinal de indutância (decaimento do pulso) |
| `512` | `4` | `uint32_t` | Ciclos de CPU medidos pelo clock DWT (durabilidade temporal) |
| `516` | `2` | `uint16_t` | Checksum **CRC-16-CCITT** (little-endian) |

* **Validação CRC-16:** O checksum é calculado sobre a carga útil de 516 bytes (Payload de Dados + Ciclos de DWT) utilizando o polinômio padrão `0x1021` (Valor inicial `0xFFFF`). Caso haja divergência no cálculo no lado do PC, o pacote é descartado automaticamente pelo `SerialWorker` para evitar ruído ou dados corrompidos na exibição gráfica.

---

## 🧠 Classificador IA e Gerenciamento de Datasets

O software extrai duas características fundamentais da curva de decaimento para classificação do material e grau de degradação/corrosão:
1. **Tau ($\tau$):** Constante de tempo obtida através do ajuste linear de mínimos quadrados ($\ln(y)$ vs $t$) na região inicial do decaimento.
2. **AUC (Área Sob a Curva):** Integral do sinal ajustado pelo offset médio da cauda do transiente.

### 💾 Cache Dinâmico de CSV
Como a leitura direta do arquivo CSV de calibração de **19 MB** geraria latência excessiva no script (de 2 a 3 segundos de travamento), a interface utiliza o gerenciador de dados inteligente [dataset_manager.py](file:///c:/Users/AdmPDI/STM32CubeIDE/workspace3/anticorrosao-firmware-eddy-currents-test/gui/dataset_manager.py):
- O dataset é mantido em memória (RAM) após o primeiro parsing.
- O cache é monitorado dinamicamente utilizando a data de modificação (`mtime`) e tamanho do arquivo no disco.
- Ao salvar novas medições ou excluir cupons na interface, o arquivo é atualizado e o cache em memória é invalidado e recarregado instantaneamente.
- O classificador utiliza **IQR (Interquartile Range)** adaptativo para limpar dados espúrios e recalcular os centroides de calibração em tempo real.
