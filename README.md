# 🛡️ Monitoramento de Corrosão com NUCLEO-H753ZI & PECT (Pulsed Eddy Currents)

Plataforma experimental e industrial de alta precisão para **detecção, quantificação e classificação não destrutiva de corrosão e perda de espessura** em estruturas metálicas (aço A36 e hastes de aterramento) via **Ensaios por Correntes Parasitas Pulsadas (Pulsed Eddy Current Testing - PECT)**.

O repositório integra um firmware de tempo real embarcado em placa **STM32H753ZI (NUCLEO)** e uma suíte completa de bancada em **Python (PyQt5 / PyQtGraph)** com processamento digital de sinais (DSP), inteligência artificial para classificação e gerenciamento avançado de caracterização de sensores.

---

## 📁 Estrutura do Repositório

```
├── Application/                 # Lógica de aplicação do firmware STM32 (Inc/Src)
│   ├── Apps/                    # Aplicação principal (App_Anticorrosao)
│   ├── Config/                  # Configurações globais e de calibração (Config_App)
│   ├── Drivers/                 # Drivers de hardware de alto nível (ADC, DMA, GPIO, TIM, UART)
│   └── Services/                # Serviços de ensaio e protocolo serial (Srv_Ensaio)
├── Core/                        # Código gerado pelo STM32CubeMX (inicializações de periféricos)
├── Drivers/                     # Drivers de baixo nível HAL e CMSIS da STMicroelectronics
├── documentação/                # Manuais, especificações e banco de testes
│   ├── datasheets/              # Datasheet STM32H753ZI e manual da placa Nucleo
│   └── Testes/
│       └── Testes de Eddy Current/
│           ├── datasets/        # Bancos de dados de calibração (.csv) e caracterização de bobinas
│           ├── gui/             # Submódulos auxiliares da GUI (coil_manager, dataset_manager, utils)
│           ├── imagens/         # Gráficos e capturas de tela das bancadas
│           ├── eddy_current_plotter_gui.py  # Entrypoint principal da Interface Gráfica (PyQt5)
│           ├── project_summary_notebooklm.md # Resumo técnico e executivo completo do projeto
│           └── project_summary_notebooklm.pdf # Resumo técnico exportado em PDF
├── .gitignore                   # Arquivos ignorados pelo Git
├── .project / .cproject         # Arquivos de projeto do STM32CubeIDE
└── anticorrosao-firmware-eddy-currents-test.ioc # Configuração do STM32CubeMX
```

---

## ⚡ 1. Firmware Embarcado (STM32H753ZI)

O firmware foi desenvolvido no **STM32CubeIDE** focado em tempo real, jitter zero e alta integridade de transmissão:

* **Aquisição DMA de Ultra-Alta Velocidade:** Amostragem analógica de 256 pontos por pulso $V(t)$ via ADC e transferência direta para a UART por DMA, reduzindo a zero a carga da CPU.
* **Mascaramento de Seção Crítica:** Desabilitação temporária de interrupções durante o disparo do pulso e janela de leitura para erradicar qualquer jitter de tempo.
* **Mapeamento de Ciclos de CPU (DWT):** Contagem exata do tempo de execução utilizando o registrador Data Watchpoint and Trace (DWT) da arquitetura ARM Cortex-M7 a 480 MHz.
* **Protocolo Serial Binário com CRC-16-CCITT:** Transmissão segura a **921.600 bps** (pacotes binários de 518/522 bytes contendo dados ADC, ciclos DWT e checksum CRC-16 com polinômio `0x1021`).
* **Timeout no Parser Serial:** Proteção de **100 ms** para a recepção de bytes consecutivos de comando.

---

## 🧮 2. Processamento Digital de Sinais (DSP) e Equacionamento de $\tau$ e $\text{AUC}$

A suíte em Python realiza a extração de dois parâmetros físicos fundamentais para cada transiente $V(t)$:

### 2.1. Equacionamento Matemático
1. **Isolamento do Decaimento:** Localização do pico $i_{\text{peak}} = \arg\max(V)$ e seleção do vetor de atenuação pós-pico.
2. **Offset DC da Cauda ($V_{\text{offset}}$):** Subtração da média dos últimos 10% de amostras estabilizadas:
   $$V_{\text{adj}}[k] = \max\left(0, \, V[k] - V_{\text{offset}}\right)$$
3. **Área Sob a Curva ($\text{AUC}$ / ROC):** Integração discreta da energia acumulada no sinal:
   $$\text{AUC} = \sum_{k=0}^{M-1} V_{\text{adj}}[k] \cdot \Delta t \quad [\text{Counts} \cdot \mu\text{s}]$$
4. **Constante de Tempo ($\tau$):** Regressão linear por mínimos quadrados no espaço logarítmico ($\ln(V_{\text{adj}}) = B \cdot t + A$) aplicada nos **primeiros 30% das amostras** pós-pico:
   $$\tau = -\frac{1}{B} \quad [\mu\text{s}]$$

### 2.2. Fundamentação Física Bi-Exponencial & Integração com SciLab
Devido à difusão magnética no aço A36 ($\nabla^2 \mathbf{H} = \mu \sigma \frac{\partial \mathbf{H}}{\partial t}$), a resposta real é bi-exponencial: $V(t) \approx A_1 e^{-t/\tau_1} + A_2 e^{-t/\tau_2} + V_{\text{offset}}$. O algoritmo ajusta $\tau_1$ (modo superficial de pele e indutância) na fase inicial, garantindo repetibilidade e permitindo comparação de dados com o SciLab.

### 2.3. Localização no Código Python
- Função Central: [`gui/utils.py`](file:///c:/Users/AdmPDI/STM32CubeIDE/workspace3/anticorrosao-firmware-eddy-currents-test/documenta%C3%A7%C3%A3o/Testes/Testes%20de%20Eddy%20Current/gui/utils.py#L47-L85) (Linhas 47–85)
- Loop de Osciloscópio Live: [`eddy_current_plotter_gui.py`](file:///c:/Users/AdmPDI/STM32CubeIDE/workspace3/anticorrosao-firmware-eddy-currents-test/documenta%C3%A7%C3%A3o/Testes/Testes%20de%20Eddy%20Current/eddy_current_plotter_gui.py#L3561-L3615) (Linhas 3561–3615)

---

## 🖥️ 3. Interface Gráfica e Módulos de Trabalho (Python PyQt5)

A interface gráfica é dividida em 5 abas operacionais:

1. **Aba 1: Transiente do Sinal $V(t)$**: Osciloscópio ao vivo a 10 Hz com FFT, derivadas $dV/dt$, envelope e janelamento.
2. **Aba 2: Espaço de Fase e Histórico**: Diagramas $V(t)$ vs $dV/dt$ e histórico dinâmico.
3. **Aba 3: Diagnóstico do Hardware**: Temperatura do MCU, ciclos DWT, taxa de perda de pacotes e status serial.
4. **Aba 4: Matriz de Validação & Acurácia**: Testes em lote de cupons com matriz de confusão e métricas da IA.
5. **Aba 5: Caracterização de Bobinas (Módulo 2)**:
   * **Sub-Aba 1 (Comparativos de Lift-Off)**: Matrizes de atenuação para espaçadores de 0.0 mm a 5.0 mm e suporte a bases `P`/`G`.
   * **Sub-Aba 2 (Monitoramento em Tempo Real do Sensor)**: Sinal Live verde neon, Média Móvel Selecionável (10, 50, 100 amostras) e relatório fixo sem oscilação de tela.
   * **Sub-Aba 3 (Análise Estatística)**: Distribuições estatísticas de $\tau$, $\text{AUC}$ e espaço de fase $(\tau, \text{AUC})$.

---

## 📁 4. Padronização de CSVs e Novas Colunas `tau_us` / `auc_counts`

Todos os ensaios de caracterização são salvos sob a nomenclatura padrão:
$$\text{\{ID\_BOBINA\}-\{BASE\}-\{DISTANCIA\}mm-\{ID\_AMOSTRA\}-\{COD\_MATERIAL\}-\{COD\_CLASSE\}-\{COD\_LOCAL\}-\{TIMESTAMP\}.csv}$$

### Estrutura do Arquivo CSV
As colunas calculadas **`tau_us`** e **`auc_counts`** são gravadas automaticamente em cada linha para cruzamento direto de dados com SciLab/MATLAB:

```csv
id_amostra;base;local;id_bobina;indutancia_uh;resistencia_ohm;diametro_mm;altura_mm;espiras;fio_awg;nucleo;distancia_mm;ajuste_manual_liftoff;material;classe;timestamp;dt_us;tau_us;auc_counts;p_0;...;p_255
001;P;Não Especificado;681;697.00;2.30;12.7;10.9;0;NA;FER;0.7;Não;Ar Livre;Ar Livre;2026-08-07 17:08:40;0.22674;6.5259;409522.93;61867;...
```

---

## 🧠 5. Inteligência Artificial e Caching de Alta Performance

* **Classificação por Centroides**: O par $(\tau, \text{AUC})$ é normalizado e classificado em 6 níveis de corrosão (`SA`, `LE`, `MO`, `AV`, `CO`, `AL`) via Distância Euclidiana Ponderada.
* **Filtro de Outliers IQR**: Remoção automática de ruído espúrio pelo critério Interquartile Range (IQR).
* **Mecanismo de Cache RAM (`DatasetManager`)**: Cache de alta velocidade validado por estatísticas de arquivo (`mtime` e `size`), eliminando travamentos na leitura do dataset de 19 MB.

---

## 🚀 6. Como Executar a Interface

### Opção 1: Via Script Automatizado (Windows)
Na pasta `documentação/Testes/Testes de Eddy Current/Executavel/`, dê um clique duplo em:
* **`run_app.bat`**

### Opção 2: Via Terminal (Código Fonte)
Com o Python 3 instalado:
```bash
pip install PyQt5 pyqtgraph numpy pyserial
python "documentação/Testes/Testes de Eddy Current/eddy_current_plotter_gui.py"
```

---

## 📚 7. Referências Bibliográficas Científicas (Open Access & PDF Direct)

1. 📄 **Ulapane, N., et al. (2017).** *Pulsed Eddy Current Sensing for Critical Pipe Condition Assessment.* MDPI Sensors, 17(10), 2208.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/17/10/2208) | ⬇️ [PDF Completo](https://www.mdpi.com/1424-8220/17/10/2208/pdf)
2. 📄 **Ge, J., et al. (2020).** *Defect Classification Using Postpeak Value for Pulsed Eddy-Current Technique.* MDPI Sensors, 20(12), 3390.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/20/12/3390) | ⬇️ [PDF Completo](https://www.mdpi.com/1424-8220/20/12/3390/pdf)
3. 📄 **Wang, H., et al. (2022).** *A Novel Pulsed Eddy Current Criterion for Non-Ferromagnetic Metal Thickness Quantifications under Large Liftoff.* MDPI Sensors, 22(2), 614.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/22/2/614) | ⬇️ [PDF Completo](https://www.mdpi.com/1424-8220/22/2/614/pdf)
4. 📄 **Yu, X., et al. (2023).** *Time-Domain Numerical Simulation and Experimental Study on Pulsed Eddy Current Inspection of Tubing and Casing.* MDPI Sensors, 23(3), 1135.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/23/3/1135) | ⬇️ [PDF Completo](https://www.mdpi.com/1424-8220/23/3/1135/pdf)
5. 📄 **Han, L., et al. (2024).** *Design and Study of Pulsed Eddy Current Sensor for Detecting Surface Defects in Small-Diameter Bars.* MDPI Sensors, 24(24), 8063.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/24/24/8063) | ⬇️ [PDF Completo](https://www.mdpi.com/1424-8220/24/24/8063/pdf)
6. 📄 **Wang, Y., et al. (2024).** *Circumferential Crack Detection in Ultra-High-Pressure Tubular Reactors with Pulsed Eddy Current Testing.* MDPI Sensors, 24(20), 6599.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/24/20/6599) | ⬇️ [PDF Completo](https://www.mdpi.com/1424-8220/24/20/6599/pdf)
7. 📄 **Ulapane, N., & Nguyen, L. (2019).** *Review of Pulsed-Eddy-Current Signal Feature-Extraction Methods for Conductive Ferromagnetic Material-Thickness Quantification.* MDPI Electronics, 8(5), 470.  
   🔗 [Artigo (MDPI Electronics)](https://www.mdpi.com/2079-9292/8/5/470) | ⬇️ [PDF Completo](https://www.mdpi.com/2079-9292/8/5/470/pdf)
8. 📄 **Li, Y., et al. (2017).** *A Gradient-Field Pulsed Eddy Current Probe for Evaluation of Hidden Material Degradation in Conductive Structures Based on Lift-Off Invariance.* MDPI Sensors, 17(5), 943.  
   🔗 [Artigo (MDPI Sensors)](https://www.mdpi.com/1424-8220/17/5/943) | ⬇️ [PDF Completo](https://www.mdpi.com/1424-8220/17/5/943/pdf)

---

## 🤝 Autoria & Parceria
Desenvolvido pelo **SENAI / ISI** para caracterização e inspeção de corrosão em estruturas metálicas utilizando ensaios não destrutivos avançados.
