# Monitoramento de Corrosão com NUCLEO-H753ZI (Eddy Currents)

Este repositório contém o projeto completo de desenvolvimento da bancada experimental de monitoramento de corrosão localizada utilizando ensaios de correntes parasitas (eddy currents). O sistema é composto por um firmware otimizado rodando em uma placa **STM32H753ZI (NUCLEO)** e uma interface gráfica em **Python (PyQt5)** para controle, aquisição de dados e inteligência artificial para classificação.

---

## 📁 Estrutura do Repositório

O repositório está organizado da seguinte forma:

```
├── Application/                 # Lógica de aplicação do firmware (organizada em Inc/Src)
│   ├── Apps/                    # App principal de controle (App_Anticorrosao)
│   ├── Config/                  # Configurações globais e de calibração (Config_App)
│   ├── Drivers/                 # Drivers de hardware de alto nível (ADC, DMA, GPIO, TIM, UART)
│   └── Services/                # Serviços de ensaio e protocolo serial (Srv_Ensaio)
├── Core/                        # Código gerado pelo STM32CubeMX (inicializações básicas)
├── Drivers/                     # Drivers de baixo nível HAL e CMSIS da STMicroelectronics
├── documentação/                # Manuais, datasheets e banco de testes
│   ├── datasheets/              # PDF do microcontrolador H753 e manual da placa Nucleo
│   └── Testes/
│       └── Testes de Eddy Current/
│           ├── Executavel/      # Script de inicialização automática e especificações de build
│           ├── datasets/        # Bancos de dados de calibração e validação (.csv)
│           ├── gui/             # Submódulos auxiliares da interface (widgets, serial, cache, utils)
│           ├── imagens/         # Gráficos e capturas de tela dos testes
│           ├── scripts/         # Scripts adicionais de análise e simulação de dados
│           ├── eddy_current_plotter_gui.py # Interface gráfica PyQt5 (Entrypoint principal)
│           └── README.md        # Documentação detalhada dos testes de Eddy Current
├── .gitignore                   # Arquivos ignorados pelo controle de versão
├── .project / .cproject         # Arquivos de projeto do STM32CubeIDE
└── anticorrosao-firmware-eddy-currents-test.ioc # Configuração do STM32CubeMX
```

---

## ⚡ 1. Otimizações no Firmware (C / STM32H753ZI)

O firmware foi desenvolvido no **STM32CubeIDE** com foco em tempo real, jitter zero e segurança na transmissão de dados:

*   **Aquisição DMA de Alta Velocidade:** Transmissão automática de dados transientes do sensor ADC por DMA para a UART, minimizando a carga de processamento da CPU.
*   **Mascaramento de Seção Crítica:** Desabilitação controlada de interrupções no momento crítico de excitação e medição para erradicar jitter.
*   **Timeout no Parser UART:** Timeout de segurança de **100 ms** para a recepção de bytes consecutivos de comandos no firmware, evitando travamento ou bloqueio do parser serial.
*   **Segurança por CRC-16-CCITT:** Validação ativa de integridade baseada em checksum CRC-16 no protocolo de transmissão serial binário de **921.600 bps** (pacotes de **522 bytes** contendo dados brutas, tempo de ciclos de CPU DWT e o código CRC).

---

## 🖥️ 2. Interface de Aquisição, Caching e Classificação (Python GUI)

O aplicativo Python foi reestruturado e otimizado com as seguintes capacidades:

*   **Modularização Limpa:** A lógica da GUI foi separada em submódulos dentro da pasta `gui/` para facilitar a manutenção e legibilidade.
*   **Mecanismo de Cache de Dataset:** Implementação do `DatasetManager` que mantém o banco de dados CSV de **19 MB** em memória RAM. O cache é validado dinamicamente com base nas estatísticas do arquivo (`os.stat`). As escritas e exclusões atualizam o cache instantaneamente sem necessidade de parsing contínuo do disco, eliminando os travamentos anteriores de 2 a 3 segundos na interface.
*   **Rotas Dinâmicas Compatíveis com Standalone (.exe):** Resolução automática do diretório base (`sys.executable` ou `__file__`) permitindo que o executável compilado compartilhe a mesma pasta física de datasets e arquivos de calibração que o código-fonte.
*   **Classificador IA Integrado:** Algoritmo robusto baseado na distância Euclidiana a Centroides Normalizados, com filtro IQR (Interquartile Range) para remoção automática de ruído e outliers.

---

## 🚀 Como Executar a Interface

### Opção 1: Via Script Automatizado (Recomendado no Windows)
Na pasta `documentação/Testes/Testes de Eddy Current/Executavel/`, dê um clique duplo em:
*   **`run_app.bat`**

Este script verifica se o Python está no PATH, instala/atualiza de forma silenciosa todas as bibliotecas requeridas e inicia a GUI de maneira transparente.

### Opção 2: Via Terminal (Código Fonte)
Com o Python 3 instalado, navegue até a pasta da GUI e instale as dependências:
```bash
pip install PyQt5 pyqtgraph numpy pyserial
```
Execute o entrypoint principal:
```bash
python "documentação/Testes/Testes de Eddy Current/eddy_current_plotter_gui.py"
```

---

## 🤝 Autoria
Desenvolvido em parceria com o **ISI Polímeros** para caracterização de corrosão em cupons metálicos utilizando ensaios não destrutivos de correntes parasitas.
