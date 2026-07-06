# Eddy Currents Test - Monitoramento de Corrosão com NUCLEO-H753ZI

Este repositório contém o projeto completo de desenvolvimento da bancada experimental de monitoramento de corrosão localizada utilizando ensaios de correntes parasitas (eddy currents). O sistema é composto por um firmware otimizado rodando em uma placa **STM32H753ZI (NUCLEO)** e uma interface gráfica em **Python (PyQt5)** para controle, aquisição de dados e inteligência artificial para classificação.

---

## 📁 Estrutura do Repositório

```
├── Core/                       # Código fonte do microcontrolador (Src, Inc, Startup)
├── Drivers/                    # Drivers de hardware HAL e CMSIS da STM32
├── .gitignore                  # Arquivos ignorados pelo Git
├── .project / .cproject        # Arquivos de projeto do STM32CubeIDE
├── anticorrosao-firmware-eddy-currents-test.ioc # Configuração STM32CubeMX
├── STM32H753ZITX_FLASH.ld      # Linker script para Flash
├── STM32H753ZITX_RAM.ld        # Linker script para RAM
├── eddy_current_plotter_gui.py # Aplicativo gráfico Python principal (PyQt5)
├── analisador_curvas.py        # Script auxiliar para análise local
├── coletor_dados_serial.py     # Coleta e depuração serial rápida
├── gerador_dataset_sintetico.py # Simulação de curvas sintéticas para testes
├── plotter_tempo_real.py       # Visualização simples em tempo real
└── visualizar_curvas_comparativo.py # Comparações offline de transientes
```

---

## ⚡ 1. Firmware STM32H753ZI

O firmware foi projetado no **STM32CubeIDE** com foco em altíssima velocidade e baixíssimo jitter para a medição física precisa dos transientes de decaimento ($\tau$ e Área sob a Curva - AUC):

*   **Amostragem em Tempo Equivalente (ETS):** Permite taxas de amostragem equivalentes de **40 MSPS** utilizando o contador de ciclos do hardware (**`DWT->CYCCNT`**) a 480 MHz com passos estáveis de 12 ciclos, permitindo medir transientes de alta frequência com precisão nanométrica.
*   **Mascaramento de Seção Crítica:** Desabilitação temporária de IRQs ao disparar a excitação e amostragem para erradicar jitter originário de outras rotinas.
*   **Alinhamento de Cache L1 (Cortex-M7):** Buffer de transmissão serial DMA dimensionado e alinhado a **544 bytes** (alinhado a 32 bytes) para evitar corrupção causada pelo D-Cache da arquitetura Cortex-M7.

---

## 🖥️ 2. Interface de Aquisição e IA (Python GUI)

O aplicativo Python fornece um ambiente interativo completo:

*   **Aba 1 (Aquisição de Sinais):** Auto-conexão serial na porta COM correspondente, exibição em tempo real do sinal transiente e gravação rotulada de amostras de calibração em arquivo CSV. Possui opção de gravar o transiente de média móvel filtrada (10 amostras).
*   **Gerenciador de Materiais Dinâmico:** Controle para adicionar ou excluir novos materiais de cupom em tempo real na interface, com persistência automática no arquivo `materiais_customizados.txt`.
*   **Aba 2 (Análise Estatística):** Visualização offline das curvas médias agrupadas por Material e Classe, cálculo automático de métricas de separabilidade estatística (Fischer Ratio) e remoção de outliers baseada no método IQR (Amplitude Interquartil).
*   **Aba 3 (Validação da IA):** Testes de validação experimental controlados por tempo (1s, 10s, 30s, 60s ou Manual), salvamento em banco de dados dedicado (`testes_validacao_ia.csv`) e relatórios automáticos de acurácia de classificação de materiais e classes de degradação.
*   **Inteligência Artificial (Classificador):** Algoritmo de classificação baseado em distância Euclidiana a Centroides Normalizados, permitindo a separação limpa das classes de corrosão sem confusão inter-materiais.

---

## 🚀 Como Executar

### Pré-requisitos
Certifique-se de ter o Python 3 instalado com as seguintes dependências:
```bash
pip install PyQt5 pyqtgraph numpy pyserial scipy
```

### Executando a GUI
1. Conecte a placa NUCLEO-H753ZI via cabo USB (ST-LINK).
2. Execute o script principal:
```bash
python eddy_current_plotter_gui.py
```
A interface tentará se conectar de forma automática à porta COM ativa.

---

## 🤝 Contribuições e Autoria
Desenvolvido em parceria com o **ISI Polímeros** para caracterização avançada de cupons metálicos sob degradação por corrosão localizada.
