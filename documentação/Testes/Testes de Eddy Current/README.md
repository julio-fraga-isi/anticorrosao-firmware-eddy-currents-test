# 🔬 Banco de Ensaios por Correntes Parasitas Pulsadas (PECT Test Bench)

Este diretório contém a suíte completa de bancada experimental, módulos de aquisição em tempo real, inteligência artificial, gerenciadores de banco de dados, documentação técnica executiva e datasets de caracterização de sensores para **Ensaios por Correntes Parasitas Pulsadas (Pulsed Eddy Current Testing - PECT)**.

---

## 📂 Estrutura de Arquivos do Subdiretório

```
documentação/Testes/Testes de Eddy Current/
├── README.md (Este manual técnico do banco de ensaios)
├── eddy_current_plotter_gui.py (Entrypoint principal da Interface Gráfica PyQt5)
├── project_summary_notebooklm.md (Resumo técnico e executivo completo do projeto)
├── project_summary_notebooklm.pdf (Resumo executivo formatado e exportado em PDF)
├── analise_detalhada_dataset.md (Relatório de análise avançada do dataset de 14.000 amostras)
├── datasets/
│   ├── dataset_cupons_indutancia.csv (Base principal de calibração / 19 MB com colunas tau_us e auc_counts)
│   ├── dataset_cupons_indutancia_backup.csv (Backup de segurança)
│   ├── dataset_cupons_indutancia_original_dma.csv (Dados puros originais do DMA)
│   ├── testes_validacao_ia.csv (Log das matrizes de validação da IA)
│   └── caracterizacao_bobinas/ (10 arquivos CSV históricos migrados com 10.000 curvas e colunas tau_us / auc_counts)
├── gui/
│   ├── coil_manager.py (Gerenciador de caracterização de bobinas, varredura por Lift-Off e exportação CSV)
│   ├── dataset_manager.py (Gerenciador de cache em RAM com validação por mtime)
│   ├── utils.py (Função central de DSP para cálculo de Tau e AUC)
│   ├── floating_tooltip.py (Widget de tooltip flutuante e fixável Pinned com heightForWidth)
│   └── dialogs.py (Diálogos de navegação e filtros)
├── Executavel/
│   ├── run_app.bat (Script de inicialização rápida com auto-instalação de dependências no Windows)
│   └── eddy_current_plotter.spec (Especificação de compilação PyInstaller para .exe)
├── imagens/
│   ├── comparativo_curvas.png (Comparativo de atenuação temporal do sinal)
│   └── visualizacao_sinais_real.png (Sinais brutos digitalizados)
└── scripts/
    ├── analisador_curvas.py (Analisa propriedades geométricas e estatísticas de decaimento)
    ├── gerador_dataset_sintetico.py (Gera datasets simulados de curvas para testes)
    └── visualizar_curvas_comparativo.py (Gera visualizações comparativas de atenuação)
```

---

## ⚙️ 1. Interface Gráfica Principal (`eddy_current_plotter_gui.py`)

A interface foi desenvolvida em **PyQt5** e **PyQtGraph** para operação contínua a 10 Hz com baixíssima latência.

### 🚀 Como Executar
1. **Via Script no Windows (Recomendado):** Na pasta `Executavel/`, dê clique duplo no arquivo **`run_app.bat`**.
2. **Via Terminal:**
   ```bash
   pip install pyqt5 pyqtgraph numpy pyserial
   python eddy_current_plotter_gui.py
   ```

---

## 🧮 2. Processamento Digital de Sinais (DSP) & Formulação de $\tau$ e $\text{AUC}$

Para cada curva de 256 pontos do transiente de indutância $V(t)$, o software calcula:

1. **Detecção do Pico:** $i_{\text{peak}} = \arg\max(V)$ e isolamento da curva pós-pico.
2. **Subtração do Offset DC ($V_{\text{offset}}$):** Média dos últimos 10% de pontos da cauda:
   $$V_{\text{adj}}[k] = \max\left(0, \, V[k] - V_{\text{offset}}\right)$$
3. **Área Sob a Curva ($\text{AUC}$ / ROC):** Soma de Riemann da energia acumulada no decaimento:
   $$\text{AUC} = \sum_{k=0}^{M-1} V_{\text{adj}}[k] \cdot \Delta t \quad [\text{Counts} \cdot \mu\text{s}]$$
4. **Constante de Tempo ($\tau$):** Ajuste linear por mínimos quadrados no espaço logarítmico ($\ln(V_{\text{adj}}) = B \cdot t + A$) nos **primeiros 30% das amostras** pós-pico:
   $$\tau = -\frac{1}{B} \quad [\mu\text{s}]$$

### 💡 Justificativa Bi-Exponencial & Integração com SciLab
Na física de difusão de PECT em aço A36, a resposta é bi-exponencial ($V(t) \approx A_1 e^{-t/\tau_1} + A_2 e^{-t/\tau_2} + V_{\text{offset}}$). O filtro dos primeiros 30% da descida isola o modo $\tau_1$ (efeito de pele e auto-indutância da bobina), garantindo alta repetibilidade e permitindo ao usuário comparar diretamente os resultados com o SciLab.

* **Função no Código:** [`gui/utils.py`](file:///c:/Users/AdmPDI/STM32CubeIDE/workspace3/anticorrosao-firmware-eddy-currents-test/documenta%C3%A7%C3%A3o/Testes/Testes%20de%20Eddy%20Current/gui/utils.py#L47-L85) (`calcular_tau_e_auc`).
* **Loop Live da GUI:** [`eddy_current_plotter_gui.py`](file:///c:/Users/AdmPDI/STM32CubeIDE/workspace3/anticorrosao-firmware-eddy-currents-test/documenta%C3%A7%C3%A3o/Testes/Testes%20de%20Eddy%20Current/eddy_current_plotter_gui.py#L3561-L3615) (`atualizar_graficos_sinal`).

---

## 📁 3. Módulo de Caracterização de Bobinas & Formato dos Arquivos CSV

O módulo gerencia a varredura por distância de Lift-Off (0.0 mm a 5.0 mm), bases físicas (`P`/`G`) e cadastro de bobinas (como a bobina `681`).

### 3.1. Nomenclatura Padrão dos Arquivos CSV
$$\text{\{ID\_BOBINA\}-\{BASE\}-\{DISTANCIA\}mm-\{ID\_AMOSTRA\}-\{COD\_MATERIAL\}-\{COD\_CLASSE\}-\{COD\_LOCAL\}-\{TIMESTAMP\}.csv}$$

### 3.2. Colunas `tau_us` e `auc_counts`
Todos os ensaios gravados (assim como os 10 arquivos históricos na pasta `datasets/caracterizacao_bobinas`) salvam os parâmetros precomputados em colunas dedicadas:

```csv
id_amostra;base;local;id_bobina;indutancia_uh;resistencia_ohm;diametro_mm;altura_mm;espiras;fio_awg;nucleo;distancia_mm;ajuste_manual_liftoff;material;classe;timestamp;dt_us;tau_us;auc_counts;p_0;p_1;...;p_255
001;P;Não Especificado;681;697.00;2.30;12.7;10.9;0;NA;FER;0.7;Não;Ar Livre;Ar Livre;2026-08-07 17:08:40;0.22674;6.5259;409522.93;61867;...
```

---

## 🔌 4. Protocolo de Comunicação Serial (MCU ➔ PC)

- **Taxa de Transmissão:** 921.600 bps via VCP USB.
- **Tamanho do Pacote:** **518 Bytes** (ou 522 bytes com alinhamento de cabeçalho).
- **Estrutura da Payload:**

| Offset (Bytes) | Tamanho (Bytes) | Formato | Descrição |
|---|---|---|---|
| `0` | `512` | `uint16_t[256]` | 256 Amostras brutas do decaimento $V(t)$ |
| `512` | `4` | `uint32_t` | Ciclos de CPU medidos pelo periférico DWT |
| `516` | `2` | `uint16_t` | Checksum **CRC-16-CCITT** (little-endian, init `0xFFFF`, poly `0x1021`) |

---

## 🧠 5. Caching em Memória RAM (`DatasetManager`) & Classificador IA

* **Cache Inteligente:** O [`gui/dataset_manager.py`](file:///c:/Users/AdmPDI/STM32CubeIDE/workspace3/anticorrosao-firmware-eddy-currents-test/documenta%C3%A7%C3%A3o/Testes/Testes%20de%20Eddy%20Current/gui/dataset_manager.py) mantém o arquivo de calibração de **19 MB** em memória RAM. O cache é validado por `os.stat().st_mtime` e `st_size`, evitando travamentos de disco durante a navegação.
* **Filtro de Ruído IQR:** Aplicação do critério Interquartile Range (IQR) para rejeição de amostras espúrias antes da classificação por Centroides e distância Euclidiana Ponderada.

---

## 📚 6. Publicações Científicas de Referência (Open Access & Download PDF)

1. 📄 **Ulapane, N., et al. (2017).** *Pulsed Eddy Current Sensing for Critical Pipe Condition Assessment.* MDPI Sensors, 17(10), 2208.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/17/10/2208) | ⬇️ [Download PDF](https://www.mdpi.com/1424-8220/17/10/2208/pdf)
2. 📄 **Ge, J., et al. (2020).** *Defect Classification Using Postpeak Value for Pulsed Eddy-Current Technique.* MDPI Sensors, 20(12), 3390.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/20/12/3390) | ⬇️ [Download PDF](https://www.mdpi.com/1424-8220/20/12/3390/pdf)
3. 📄 **Wang, H., et al. (2022).** *A Novel Pulsed Eddy Current Criterion for Non-Ferromagnetic Metal Thickness Quantifications under Large Liftoff.* MDPI Sensors, 22(2), 614.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/22/2/614) | ⬇️ [Download PDF](https://www.mdpi.com/1424-8220/22/2/614/pdf)
4. 📄 **Yu, X., et al. (2023).** *Time-Domain Numerical Simulation and Experimental Study on Pulsed Eddy Current Inspection of Tubing and Casing.* MDPI Sensors, 23(3), 1135.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/23/3/1135) | ⬇️ [Download PDF](https://www.mdpi.com/1424-8220/23/3/1135/pdf)
5. 📄 **Han, L., et al. (2024).** *Design and Study of Pulsed Eddy Current Sensor for Detecting Surface Defects in Small-Diameter Bars.* MDPI Sensors, 24(24), 8063.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/24/24/8063) | ⬇️ [Download PDF](https://www.mdpi.com/1424-8220/24/24/8063/pdf)
6. 📄 **Wang, Y., et al. (2024).** *Circumferential Crack Detection in Ultra-High-Pressure Tubular Reactors with Pulsed Eddy Current Testing.* MDPI Sensors, 24(20), 6599.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/24/20/6599) | ⬇️ [Download PDF](https://www.mdpi.com/1424-8220/24/20/6599/pdf)
7. 📄 **Ulapane, N., & Nguyen, L. (2019).** *Review of Pulsed-Eddy-Current Signal Feature-Extraction Methods for Conductive Ferromagnetic Material-Thickness Quantification.* MDPI Electronics, 8(5), 470.  
   🔗 [Artigo (MDPI Electronics)](https://www.mdpi.com/2079-9292/8/5/470) | ⬇️ [Download PDF](https://www.mdpi.com/2079-9292/8/5/470/pdf)
8. 📄 **Li, Y., et al. (2017).** *A Gradient-Field Pulsed Eddy Current Probe for Evaluation of Hidden Material Degradation in Conductive Structures Based on Lift-Off Invariance.* MDPI Sensors, 17(5), 943.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/17/5/943) | ⬇️ [Download PDF](https://www.mdpi.com/1424-8220/17/5/943/pdf)

---
*Manual técnico do banco de ensaios mantido em sincronia com o repositório principal.*
