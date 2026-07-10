# -*- coding: utf-8 -*-
"""
Interface Gráfica de Aquisição e Calibração (Eddy Currents)
Desenvolvido com PyQt5 e pyqtgraph para visualização em tempo real das curvas
de indutância, cálculo de constantes de tempo (Tau) e integração (AUC),
e gravação dos datasets experimentais.
"""

import sys
import os
import csv
import time
import numpy as np
from datetime import datetime
from collections import deque
import serial
import serial.tools.list_ports
import struct

from PyQt5 import QtCore, QtWidgets, QtGui
import pyqtgraph as pg

# Configurações do Gráfico de Tendência
MAX_TREND_POINTS = 200

def normalizar_nome_classe(classe_str):
    import unicodedata
    # Remove acentos e converte para minúsculas
    norm = "".join(c for c in unicodedata.normalize('NFD', classe_str) if unicodedata.category(c) != 'Mn').lower().strip()
    
    # Mapeia para a classe canônica
    if "saudavel" in norm:
        return "Saudável"
    elif "leve" in norm:
        return "Leve"
    elif "moderada" in norm:
        return "Moderada"
    elif "avancada" in norm:
        return "Avançada"
    elif "corr" in norm: # corroído, corroido, etc.
        return "Corroído"
    elif "ar" in norm or "livre" in norm or "vazio" in norm or "sem" in norm:
        return "Ar Livre"
    else:
        return classe_str.strip().capitalize()

class ExclusaoSeletivaDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        import os
        nome_arquivo = "Sem Arquivo"
        if parent and hasattr(parent, 'arquivo_csv'):
            nome_arquivo = os.path.basename(parent.arquivo_csv)
            
        self.setWindowTitle(f"Excluir Dados - {nome_arquivo}")
        self.setMinimumWidth(360)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e1e1e6;
            }
            QLabel {
                color: #a0a0b2;
                font-size: 10pt;
                font-weight: bold;
            }
            QComboBox {
                background-color: #2c2c2e;
                border: 1px solid #3a3a3c;
                border-radius: 4px;
                color: #e1e1e6;
                padding: 5px;
                min-height: 25px;
            }
            QPushButton {
                font-weight: bold;
                border-radius: 4px;
                padding: 8px;
                min-height: 30px;
            }
        """)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        lbl_info = QtWidgets.QLabel(f"Critérios de exclusão para o arquivo:\n➔ {nome_arquivo}")
        lbl_info.setStyleSheet("font-weight: bold; color: #f1c40f; margin-bottom: 10px; font-size: 10pt;")
        layout.addWidget(lbl_info)
        
        # Dropdown de Material
        layout.addWidget(QtWidgets.QLabel("Material:"))
        self.combo_material = QtWidgets.QComboBox()
        self.combo_material.addItems(["[Todos os Materiais]", "A36 Comum", "A36 GE", "A36 GF", "Ar Livre"])
        layout.addWidget(self.combo_material)
        
        # Dropdown de Classe
        layout.addWidget(QtWidgets.QLabel("Classe/Degradação:"))
        self.combo_classe = QtWidgets.QComboBox()
        self.combo_classe.addItems(["[Todas as Classes]", "Saudável", "Leve", "Moderada", "Avançada", "Corroído", "Ar Livre"])
        layout.addWidget(self.combo_classe)
        
        layout.addSpacing(15)
        
        # Botões
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_cancelar = QtWidgets.QPushButton("Cancelar")
        self.btn_cancelar.setStyleSheet("background-color: #3a3a3c; color: white;")
        self.btn_cancelar.clicked.connect(self.reject)
        
        self.btn_excluir = QtWidgets.QPushButton("Excluir Selecionados")
        self.btn_excluir.setStyleSheet("background-color: #c0392b; color: white;")
        self.btn_excluir.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_cancelar)
        btn_layout.addWidget(self.btn_excluir)
        layout.addLayout(btn_layout)

class CollapsibleGroupBox(QtWidgets.QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.layout_principal = QtWidgets.QVBoxLayout(self)
        self.layout_principal.setContentsMargins(0, 0, 0, 0)
        self.layout_principal.setSpacing(0)
        
        # Barra de Cabeçalho clicável (Widget customizado)
        self.header_widget = QtWidgets.QWidget()
        self.header_widget.setStyleSheet("""
            QWidget {
                background-color: #2c2c2e;
                border: 1px solid #3a3a3c;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
        """)
        header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(12, 8, 12, 8)
        
        # Título
        self.lbl_title = QtWidgets.QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 10pt; color: #e1e1e6; border: none; background: transparent;")
        header_layout.addWidget(self.lbl_title)
        
        # Spacer no meio
        header_layout.addStretch()
        
        # Ícone de seta
        self.lbl_arrow = QtWidgets.QLabel("▲")
        self.lbl_arrow.setStyleSheet("font-weight: bold; font-size: 10pt; color: #a0a0b2; border: none; background: transparent;")
        header_layout.addWidget(self.lbl_arrow)
        
        self.layout_principal.addWidget(self.header_widget)
        
        # Torna o cabeçalho clicável detectando o mousePressEvent
        self.header_widget.mousePressEvent = self.toggle_collapse
        self.expandido = True
        
        # Widget container para o conteúdo (inicialmente sem layout para evitar rejeição do Qt)
        self.content_container = QtWidgets.QGroupBox()
        self.content_container.setStyleSheet("""
            QGroupBox {
                background-color: #1e1e1f;
                border: 1px solid #3a3a3c;
                border-top: none;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                padding: 10px;
            }
        """)
        self.layout_principal.addWidget(self.content_container)
        
    def toggle_collapse(self, event):
        self.expandido = not self.expandido
        self.content_container.setVisible(self.expandido)
        self.lbl_arrow.setText("▲" if self.expandido else "▼")
        # Ajusta os cantos arredondados do cabeçalho se colapsado
        if self.expandido:
            self.header_widget.setStyleSheet("""
                QWidget {
                    background-color: #2c2c2e;
                    border: 1px solid #3a3a3c;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                }
            """)
        else:
            self.header_widget.setStyleSheet("""
                QWidget {
                    background-color: #2c2c2e;
                    border: 1px solid #3a3a3c;
                    border-radius: 6px;
                }
            """)
            
    def setLayout(self, layout):
        # Configura as margens e espaçamento padrão no layout do usuário
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.content_container.setLayout(layout)

class SerialWorker(QtCore.QThread):
    """Thread em segundo plano para comunicação serial sem travar a interface"""
    curva_recebida = QtCore.pyqtSignal(list)
    erro_serial = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.porta = None
        self.baud = 921600
        self.running = False
        self.trigger_requested = False
        self.modo_ets = False
        self.mutex = QtCore.QMutex()

    def set_modo_ets(self, enabled):
        self.mutex.lock()
        self.modo_ets = enabled
        self.mutex.unlock()

    def conectar(self, porta, baud=921600):
        self.porta = porta
        self.baud = baud
        self.running = True
        self.start()

    def desconectar(self):
        self.running = False
        self.wait()

    def disparar_leitura(self):
        self.mutex.lock()
        self.trigger_requested = True
        self.mutex.unlock()

    def run(self):
        try:
            ser = serial.Serial(self.porta, self.baud, timeout=1.0)
        except Exception as e:
            self.erro_serial.emit(str(e))
            return

        while self.running:
            disparar = False
            self.mutex.lock()
            if self.trigger_requested:
                disparar = True
                self.trigger_requested = False
            self.mutex.unlock()

            if disparar:
                try:
                    self.mutex.lock()
                    ets_mode = self.modo_ets
                    self.mutex.unlock()
                    
                    ser.reset_input_buffer()
                    ser.write(b'e' if ets_mode else b't') # Envia 'e' para ETS ou 't' para DMA
                    
                    # Busca pelo cabeçalho de sincronização [0xAA, 0x55, 0xAA, 0x55]
                    sync_state = 0
                    start_time = time.time()
                    while self.running and (time.time() - start_time < 0.5): # timeout de 500ms
                        b = ser.read(1)
                        if not b:
                            break
                        if sync_state == 0 and b == b'\xaa':
                            sync_state = 1
                        elif sync_state == 1 and b == b'\x55':
                            sync_state = 2
                        elif sync_state == 2 and b == b'\xaa':
                            sync_state = 3
                        elif sync_state == 3 and b == b'\x55':
                            # Sincronizado! Lê os 512 bytes de dados (256 uint16)
                            data = ser.read(512)
                            if len(data) == 512:
                                # '<256H' indica 256 inteiros de 16 bits sem sinal (little-endian)
                                valores = list(struct.unpack('<256H', data))
                                self.curva_recebida.emit(valores)
                            break
                        else:
                            sync_state = 0
                except Exception as e:
                    self.erro_serial.emit(str(e))
            self.msleep(10)
        ser.close()


class EddyCurrentPlotter(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        
        # Estado serial
        self.serial_thread = SerialWorker()
        self.serial_thread.curva_recebida.connect(self.processar_nova_curva)
        self.serial_thread.erro_serial.connect(self.tratar_erro_serial)
        
        # Parâmetros físicos
        self.dt_us = 0.00001  # Padrão calibrado: 10 MSPS (ADC a 96/80 MHz, 16-bit, oversampling desativado)
        self.arquivo_csv = "dataset_cupons_indutancia.csv"
        
        # Gerenciamento de materiais customizados
        self.arquivo_materiais_config = "materiais_customizados.txt"
        self.custom_materials = self.carregar_lista_materiais()
        self.todos_materiais = ["A36 Comum", "A36 GE", "A36 GF"] + self.custom_materials + ["Ar Livre"]
        self.radio_buttons_material = {}
        self.val_radio_buttons_material = {}
        self.filter_checkboxes_material = {}
        
        # Histórico de leituras (Deques para o gráfico de tendência em tempo real)
        self.trend_tau = deque(maxlen=MAX_TREND_POINTS)
        self.trend_auc = deque(maxlen=MAX_TREND_POINTS)
        self.trend_indices = deque(maxlen=MAX_TREND_POINTS)
        self.recent_curves = deque(maxlen=10)
        self.trend_counter = 0

        # Últimos valores calculados
        self.last_valores = None
        self.last_tau = 0.0
        self.last_auc = 0.0
        
        # Lista circular de pontos salvos (mantém apenas as últimas 1000 leituras na sessão)
        self.pontos_salvos = deque(maxlen=1000)

        # Inicializa o classificador inteligente baseado no dataset
        self.centroids = {}
        self.tau_std = 1.0
        self.auc_std = 1.0
        self.tau_mean = 0.0
        self.auc_mean = 0.0
        self.treinar_classificador()

        # Variáveis de Estado da Aba de Validação
        self.is_running_validation_test = False
        self.val_test_duration = 0  # em ms
        self.val_test_elapsed = 0   # em ms
        self.val_test_timer = QtCore.QTimer()
        self.val_test_timer.timeout.connect(self.ao_tick_ensaio_validacao)
        self.val_samples_captured = 0
        self.val_mat_matches = 0
        self.val_cls_matches = 0
        self.val_test_data = [] # Lista para armazenar estatísticas do ensaio corrente
        self.arquivo_csv_validacao = "testes_validacao_ia.csv"

        # Limites Y atuais para a escala adaptativa estável (com histerese de ruído)
        self.current_y_limit_bruto = None
        self.current_y_limit_decay = None

        # Estado de coleta sequencial automática de 10 disparos
        self.is_collecting_sequential = False
        self.sequential_collect_counter = 0

        # Inicializa a interface
        self.init_ui()
        
        # Configura o Timer para Auto-Trigger (Modo Contínuo)
        self.auto_trigger_timer = QtCore.QTimer()
        self.auto_trigger_timer.timeout.connect(self.solicitar_leitura_automatica)
        
        # Auto-detecta e conecta na inicialização
        self.auto_detectar_e_conectar()

    def init_ui(self):
        # Configuração da Janela Principal
        self.setWindowTitle("ISI Sensoriamento - Eddy Current Test Bench & Data Aquisition")
        self.resize(1350, 920)

        # Configurações de cores da biblioteca PyQtGraph
        pg.setConfigOptions(antialias=True)
        pg.setConfigOption("background", "#121214")
        pg.setConfigOption("foreground", "#e1e1e6")
        
        # Layout Principal com Abas (Tabs)
        outer_layout = QtWidgets.QVBoxLayout(self)
        self.tab_widget = QtWidgets.QTabWidget()
        outer_layout.addWidget(self.tab_widget)

        # Aba 1: Aquisição em Tempo Real
        self.tab_acq = QtWidgets.QWidget()
        self.tab_widget.addTab(self.tab_acq, "Aquisição em Tempo Real")
        tab_acq_layout = QtWidgets.QHBoxLayout(self.tab_acq)

        # =====================================================================
        # PAINEL LATERAL ESQUERDO: Controles e Configurações (Com Scroll Area)
        # =====================================================================
        panel_left = QtWidgets.QWidget()
        panel_left.setMaximumWidth(420)
        panel_left.setMinimumWidth(380)
        
        # Layout principal de panel_left que conterá apenas a scroll area
        panel_left_outer_layout = QtWidgets.QVBoxLayout(panel_left)
        panel_left_outer_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1e1e1e;
            }
            QScrollBar:vertical {
                border: none;
                background: #121214;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3a3a3c;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        
        scroll_content = QtWidgets.QWidget()
        scroll_content.setStyleSheet("background-color: #1e1e1e;")
        scroll_content_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(10, 10, 10, 10)
        scroll_content_layout.setSpacing(15)
        
        scroll_area.setWidget(scroll_content)
        panel_left_outer_layout.addWidget(scroll_area)

        # 1. Grupo Conectividade
        group_conn = CollapsibleGroupBox("Conectividade Serial")
        group_conn_layout = QtWidgets.QGridLayout()
        group_conn.setLayout(group_conn_layout)
        
        group_conn_layout.addWidget(QtWidgets.QLabel("Porta COM:"), 0, 0)
        self.combo_portas = QtWidgets.QComboBox()
        self.atualizar_portas_disponiveis()
        group_conn_layout.addWidget(self.combo_portas, 0, 1)
        
        self.btn_atualizar_portas = QtWidgets.QPushButton("Refresh")
        self.btn_atualizar_portas.clicked.connect(self.atualizar_portas_disponiveis)
        group_conn_layout.addWidget(self.btn_atualizar_portas, 0, 2)

        group_conn_layout.addWidget(QtWidgets.QLabel("Baud Rate:"), 1, 0)
        self.combo_baud = QtWidgets.QComboBox()
        self.combo_baud.addItems(["115200", "230400", "460800", "921600"])
        self.combo_baud.setCurrentText("921600")
        group_conn_layout.addWidget(self.combo_baud, 1, 1, 1, 2)

        self.btn_conectar = QtWidgets.QPushButton("Conectar")
        self.btn_conectar.clicked.connect(self.alternar_conexao)
        self.btn_conectar.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        group_conn_layout.addWidget(self.btn_conectar, 2, 0, 1, 3)

        self.lbl_status_conn = QtWidgets.QLabel("Status: Desconectado")
        self.lbl_status_conn.setStyleSheet("color: #e74c3c; font-weight: bold;")
        group_conn_layout.addWidget(self.lbl_status_conn, 3, 0, 1, 3)

        scroll_content_layout.addWidget(group_conn)

        # 2. Grupo de Aquisição de Sinais
        group_acq = CollapsibleGroupBox("Modo de Operação")
        group_acq_layout = QtWidgets.QVBoxLayout()
        group_acq.setLayout(group_acq_layout)

        self.btn_single_trigger = QtWidgets.QPushButton("Disparar Leitura Única")
        self.btn_single_trigger.clicked.connect(self.solicitar_leitura_manual)
        self.btn_single_trigger.setMinimumHeight(30)
        self.btn_single_trigger.setStyleSheet("font-weight: bold; background-color: #2980b9; color: white;")
        group_acq_layout.addWidget(self.btn_single_trigger)

        self.chk_auto_trigger = QtWidgets.QCheckBox("Modo Contínuo (Auto-Trigger)")
        self.chk_auto_trigger.stateChanged.connect(self.alternar_auto_trigger)
        group_acq_layout.addWidget(self.chk_auto_trigger)

        self.chk_ets = QtWidgets.QCheckBox("Modo ETS (Alta Velocidade / 8 MSPS)")
        self.chk_ets.stateChanged.connect(self.alternar_modo_ets)
        group_acq_layout.addWidget(self.chk_ets)

        # Campo para ajuste manual e visualização do tempo entre amostras (dt_us)
        layout_dt = QtWidgets.QHBoxLayout()
        lbl_dt = QtWidgets.QLabel("Intervalo dt (μs):")
        lbl_dt.setStyleSheet("color: #e1e1e6; font-size: 9pt;")
        layout_dt.addWidget(lbl_dt)
        
        self.spin_dt = QtWidgets.QDoubleSpinBox()
        self.spin_dt.setDecimals(5)
        self.spin_dt.setRange(0.00001, 10000.0)
        self.spin_dt.setSingleStep(0.1)
        self.spin_dt.setValue(self.dt_us)
        self.spin_dt.valueChanged.connect(self.atualizar_dt_us)
        self.spin_dt.setStyleSheet("color: white; background-color: #2e2e32; border: 1px solid #55555a; padding: 2px;")
        self.spin_dt.setMinimumHeight(28)
        layout_dt.addWidget(self.spin_dt)
        group_acq_layout.addLayout(layout_dt)

        scroll_content_layout.addWidget(group_acq)

        # 2.5. Grupo de Filtros e Processamento de Sinal
        group_filters = CollapsibleGroupBox("Filtros e Processamento de Sinal")
        group_filters_layout = QtWidgets.QGridLayout()
        group_filters.setLayout(group_filters_layout)
        
        # Filtro de Curva Bruta
        self.chk_filtrar_curva = QtWidgets.QCheckBox("Suavizar Transiente (Curva)")
        self.chk_filtrar_curva.setStyleSheet("color: #e1e1e6; font-size: 9pt; font-weight: bold;")
        self.chk_filtrar_curva.setChecked(False)
        self.chk_filtrar_curva.stateChanged.connect(lambda: self.treinar_classificador())
        group_filters_layout.addWidget(self.chk_filtrar_curva, 0, 0, 1, 2)
        
        group_filters_layout.addWidget(QtWidgets.QLabel("Janela da Curva (pts):"), 1, 0)
        self.spin_janela_curva = QtWidgets.QSpinBox()
        self.spin_janela_curva.setRange(1, 25)
        self.spin_janela_curva.setValue(5)
        self.spin_janela_curva.setStyleSheet("color: white; background-color: #2e2e32; border: 1px solid #55555a; padding: 2px;")
        self.spin_janela_curva.valueChanged.connect(lambda: self.treinar_classificador())
        group_filters_layout.addWidget(self.spin_janela_curva, 1, 1)
        
        self.chk_filtrar_IA = QtWidgets.QCheckBox("Treinar IA com Curvas Filtradas")
        self.chk_filtrar_IA.setStyleSheet("color: #a0a0b2; font-size: 8pt;")
        self.chk_filtrar_IA.setChecked(True)
        self.chk_filtrar_IA.stateChanged.connect(lambda: self.treinar_classificador())
        group_filters_layout.addWidget(self.chk_filtrar_IA, 2, 0, 1, 2)
        
        # Separador horizontal
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        line.setStyleSheet("background-color: #3a3a3c; margin: 4px 0px;")
        group_filters_layout.addWidget(line, 3, 0, 1, 2)
        
        # Filtro de Métricas
        self.chk_filtrar_metricas = QtWidgets.QCheckBox("Estabilizar Gráfico de Tendências")
        self.chk_filtrar_metricas.setStyleSheet("color: #e1e1e6; font-size: 9pt; font-weight: bold;")
        self.chk_filtrar_metricas.setChecked(True)
        group_filters_layout.addWidget(self.chk_filtrar_metricas, 4, 0, 1, 2)
        
        group_filters_layout.addWidget(QtWidgets.QLabel("Histórico do Gráfico (pts):"), 5, 0)
        self.spin_janela_metricas = QtWidgets.QSpinBox()
        self.spin_janela_metricas.setRange(2, 1000)
        self.spin_janela_metricas.setValue(10)
        self.spin_janela_metricas.setStyleSheet("color: white; background-color: #2e2e32; border: 1px solid #55555a; padding: 2px;")
        self.spin_janela_metricas.valueChanged.connect(self.atualizar_tamanho_janela_metricas)
        group_filters_layout.addWidget(self.spin_janela_metricas, 5, 1)
        
        self.chk_ia_usa_media_movel = QtWidgets.QCheckBox("Classificar IA com Média Móvel")
        self.chk_ia_usa_media_movel.setStyleSheet("color: #e1e1e6; font-size: 9pt; font-weight: bold;")
        self.chk_ia_usa_media_movel.setChecked(True)
        group_filters_layout.addWidget(self.chk_ia_usa_media_movel, 6, 0, 1, 2)
        
        group_filters_layout.addWidget(QtWidgets.QLabel("Janela da Média da IA:"), 7, 0)
        self.spin_janela_ia = QtWidgets.QSpinBox()
        self.spin_janela_ia.setRange(2, 100)
        self.spin_janela_ia.setValue(10)
        self.spin_janela_ia.setStyleSheet("color: white; background-color: #2e2e32; border: 1px solid #55555a; padding: 2px;")
        group_filters_layout.addWidget(self.spin_janela_ia, 7, 1)
        
        scroll_content_layout.addWidget(group_filters)

        # 3. Grupo de Registro e Rotulagem (Dataset com RadioButtons)
        group_record = CollapsibleGroupBox("Rotulagem e Gravação de Amostras")
        group_record_layout = QtWidgets.QGridLayout()
        group_record.setLayout(group_record_layout)

        group_record_layout.addWidget(QtWidgets.QLabel("ID / Nº Cupom:"), 0, 0)
        self.edit_id_amostra = QtWidgets.QLineEdit("0")
        group_record_layout.addWidget(self.edit_id_amostra, 0, 1)

        # Label de Material
        lbl_mat = QtWidgets.QLabel("Material:")
        lbl_mat.setStyleSheet("font-weight: bold; color: #a0a0b2;")
        group_record_layout.addWidget(lbl_mat, 1, 0)
        
        # Estilo premium para os radio buttons
        radio_stylesheet = """
            QRadioButton {
                color: #e1e1e6;
                font-size: 9pt;
                padding: 2px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
            }
            QRadioButton::indicator::unchecked {
                border: 1px solid #55555a;
                background-color: #2c2c2e;
            }
            QRadioButton::indicator::checked {
                border: 1px solid #2ecc71;
                background-color: #2ecc71;
            }
        """
        self.radio_stylesheet = radio_stylesheet
        self.group_mat = QtWidgets.QButtonGroup(self)

        # Grid para RadioButtons de Material (Dinâmico)
        self.widget_mat_radios = QtWidgets.QWidget()
        self.layout_mat_radios = QtWidgets.QGridLayout(self.widget_mat_radios)
        self.layout_mat_radios.setContentsMargins(0, 0, 0, 0)
        self.layout_mat_radios.setSpacing(6)
        
        # Container principal de Material (Aba 1)
        widget_mat_container = QtWidgets.QWidget()
        layout_mat_container = QtWidgets.QVBoxLayout(widget_mat_container)
        layout_mat_container.setContentsMargins(0, 5, 0, 5)
        layout_mat_container.setSpacing(8)
        layout_mat_container.addWidget(self.widget_mat_radios)
        
        # Controles para Adicionar/Remover material customizado
        layout_mat_controles = QtWidgets.QHBoxLayout()
        layout_mat_controles.setSpacing(4)
        
        self.edit_novo_material = QtWidgets.QLineEdit()
        self.edit_novo_material.setPlaceholderText("Novo Material...")
        self.edit_novo_material.setStyleSheet("background-color: #2e2e32; color: white; border: 1px solid #3a3a3c; border-radius: 4px; padding: 4px; font-size: 8pt;")
        self.edit_novo_material.setMaximumWidth(150)
        
        self.btn_add_material = QtWidgets.QPushButton("+ Add")
        self.btn_add_material.clicked.connect(self.adicionar_material_customizado)
        self.btn_add_material.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 8pt; border-radius: 4px; padding: 4px;")
        
        self.btn_del_material = QtWidgets.QPushButton("- Del")
        self.btn_del_material.clicked.connect(self.remover_material_selecionado)
        self.btn_del_material.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; font-size: 8pt; border-radius: 4px; padding: 4px;")
        
        layout_mat_controles.addWidget(self.edit_novo_material)
        layout_mat_controles.addWidget(self.btn_add_material)
        layout_mat_controles.addWidget(self.btn_del_material)
        layout_mat_container.addLayout(layout_mat_controles)
        
        group_record_layout.addWidget(widget_mat_container, 1, 1)

        # Label de Classe
        lbl_cls = QtWidgets.QLabel("Classe:")
        lbl_cls.setStyleSheet("font-weight: bold; color: #a0a0b2;")
        group_record_layout.addWidget(lbl_cls, 2, 0)
        
        # Grid para RadioButtons de Classe
        widget_cls_radios = QtWidgets.QWidget()
        layout_cls_radios = QtWidgets.QGridLayout(widget_cls_radios)
        layout_cls_radios.setContentsMargins(0, 5, 0, 5)
        layout_cls_radios.setSpacing(6)
        
        self.rad_cls_saudavel = QtWidgets.QRadioButton("Saudável")
        self.rad_cls_leve = QtWidgets.QRadioButton("Leve")
        self.rad_cls_moderada = QtWidgets.QRadioButton("Moderada")
        self.rad_cls_avancada = QtWidgets.QRadioButton("Avançada")
        self.rad_cls_corroido = QtWidgets.QRadioButton("Corroído")
        self.rad_cls_ar = QtWidgets.QRadioButton("Ar Livre")
        
        self.rad_cls_saudavel.setStyleSheet(radio_stylesheet)
        self.rad_cls_leve.setStyleSheet(radio_stylesheet)
        self.rad_cls_moderada.setStyleSheet(radio_stylesheet)
        self.rad_cls_avancada.setStyleSheet(radio_stylesheet)
        self.rad_cls_corroido.setStyleSheet(radio_stylesheet)
        self.rad_cls_ar.setStyleSheet(radio_stylesheet)
        
        self.group_cls = QtWidgets.QButtonGroup(self)
        self.group_cls.addButton(self.rad_cls_saudavel)
        self.group_cls.addButton(self.rad_cls_leve)
        self.group_cls.addButton(self.rad_cls_moderada)
        self.group_cls.addButton(self.rad_cls_avancada)
        self.group_cls.addButton(self.rad_cls_corroido)
        self.group_cls.addButton(self.rad_cls_ar)
        
        self.rad_cls_saudavel.setChecked(True)
        
        layout_cls_radios.addWidget(self.rad_cls_saudavel, 0, 0)
        layout_cls_radios.addWidget(self.rad_cls_leve, 0, 1)
        layout_cls_radios.addWidget(self.rad_cls_moderada, 1, 0)
        layout_cls_radios.addWidget(self.rad_cls_avancada, 1, 1)
        layout_cls_radios.addWidget(self.rad_cls_corroido, 2, 0)
        layout_cls_radios.addWidget(self.rad_cls_ar, 2, 1)
        
        group_record_layout.addWidget(widget_cls_radios, 2, 1)

        # Conecta eventos para coerência Ar Livre
        self.rad_cls_ar.toggled.connect(self.ao_toggle_ar_livre_classe)

        # Novo Checkbox para gravar Média Móvel da curva em vez do dado instantâneo
        self.chk_salvar_media_movel = QtWidgets.QCheckBox("Gravar Média Móvel (Filtro 10 amostras)")
        self.chk_salvar_media_movel.setStyleSheet("color: #e1e1e6; font-size: 9pt; font-weight: bold;")
        self.chk_salvar_media_movel.setChecked(True)
        group_record_layout.addWidget(self.chk_salvar_media_movel, 3, 0, 1, 2)

        self.btn_salvar_registro = QtWidgets.QPushButton("Gravar Medição no CSV")
        self.btn_salvar_registro.clicked.connect(self.salvar_dados_em_csv)
        self.btn_salvar_registro.setMinimumHeight(30)
        self.btn_salvar_registro.setStyleSheet("background-color: #f1c40f; color: black; font-weight: bold; font-size: 11pt;")
        group_record_layout.addWidget(self.btn_salvar_registro, 4, 0, 1, 2)

        # Layout horizontal para gravações múltiplas (10, 100, 1000)
        layout_multi_salvar = QtWidgets.QHBoxLayout()
        
        self.btn_salvar_10 = QtWidgets.QPushButton("Gravar 10")
        self.btn_salvar_10.clicked.connect(lambda: self.iniciar_coleta_sequencial(10))
        self.btn_salvar_10.setMinimumHeight(25)
        self.btn_salvar_10.setStyleSheet("background-color: #9b59b6; color: white; font-weight: bold; font-size: 10pt;")
        
        self.btn_salvar_100 = QtWidgets.QPushButton("Gravar 100")
        self.btn_salvar_100.clicked.connect(lambda: self.iniciar_coleta_sequencial(100))
        self.btn_salvar_100.setMinimumHeight(25)
        self.btn_salvar_100.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold; font-size: 10pt;")
        
        self.btn_salvar_1000 = QtWidgets.QPushButton("Gravar 1000")
        self.btn_salvar_1000.clicked.connect(lambda: self.iniciar_coleta_sequencial(1000))
        self.btn_salvar_1000.setMinimumHeight(25)
        self.btn_salvar_1000.setStyleSheet("background-color: #6c3483; color: white; font-weight: bold; font-size: 10pt;")
        
        layout_multi_salvar.addWidget(self.btn_salvar_10)
        layout_multi_salvar.addWidget(self.btn_salvar_100)
        layout_multi_salvar.addWidget(self.btn_salvar_1000)
        
        group_record_layout.addLayout(layout_multi_salvar, 5, 0, 1, 2)

        scroll_content_layout.addWidget(group_record)

        # 4. Painel de Status das Métricas (Display Grande)
        group_metrics = CollapsibleGroupBox("Métricas em Tempo Real")
        group_metrics_layout = QtWidgets.QGridLayout()
        group_metrics.setLayout(group_metrics_layout)

        lbl_tau_txt = QtWidgets.QLabel("Tau (\u03c4):")
        lbl_tau_txt.setStyleSheet("font-size: 11pt; color: #a0a0b2;")
        self.lbl_tau_val = QtWidgets.QLabel("0.00 \u03bcs")
        self.lbl_tau_val.setStyleSheet("font-size: 18pt; font-weight: bold; color: #2ecc71;")

        lbl_tau_ma_txt = QtWidgets.QLabel("Média Móvel \u03c4 (10):")
        lbl_tau_ma_txt.setStyleSheet("font-size: 9pt; color: #7f8c8d; font-style: italic;")
        self.lbl_tau_ma_val = QtWidgets.QLabel("0.00 \u03bcs")
        self.lbl_tau_ma_val.setStyleSheet("font-size: 14pt; font-weight: bold; color: #27ae60; font-style: italic;")

        lbl_auc_txt = QtWidgets.QLabel("AUC:")
        lbl_auc_txt.setStyleSheet("font-size: 11pt; color: #a0a0b2;")
        self.lbl_auc_val = QtWidgets.QLabel("0.0")
        self.lbl_auc_val.setStyleSheet("font-size: 18pt; font-weight: bold; color: #3498db;")

        lbl_auc_ma_txt = QtWidgets.QLabel("Média Móvel AUC:")
        lbl_auc_ma_txt.setStyleSheet("font-size: 9pt; color: #7f8c8d; font-style: italic;")
        self.lbl_auc_ma_val = QtWidgets.QLabel("0.0")
        self.lbl_auc_ma_val.setStyleSheet("font-size: 14pt; font-weight: bold; color: #2980b9; font-style: italic;")

        group_metrics_layout.addWidget(lbl_tau_txt, 0, 0)
        group_metrics_layout.addWidget(self.lbl_tau_val, 0, 1)
        group_metrics_layout.addWidget(lbl_tau_ma_txt, 1, 0)
        group_metrics_layout.addWidget(self.lbl_tau_ma_val, 1, 1)
        group_metrics_layout.addWidget(lbl_auc_txt, 2, 0)
        group_metrics_layout.addWidget(self.lbl_auc_val, 2, 1)
        group_metrics_layout.addWidget(lbl_auc_ma_txt, 3, 0)
        group_metrics_layout.addWidget(self.lbl_auc_ma_val, 3, 1)

        scroll_content_layout.addWidget(group_metrics)

        # 4.5. Painel de Classificação Inteligente em Tempo Real (IA)
        group_classif = CollapsibleGroupBox("Classificação do Cupom (IA)")
        group_classif_layout = QtWidgets.QGridLayout()
        group_classif.setLayout(group_classif_layout)
        
        lbl_cls_material_txt = QtWidgets.QLabel("Material Detectado:")
        lbl_cls_material_txt.setStyleSheet("font-size: 10pt; color: #a0a0b2;")
        self.lbl_cls_material_val = QtWidgets.QLabel("Desconhecido")
        self.lbl_cls_material_val.setStyleSheet("font-size: 11pt; font-weight: bold; color: #f1c40f;")
        
        lbl_cls_degrad_txt = QtWidgets.QLabel("Estado / Degradação:")
        lbl_cls_degrad_txt.setStyleSheet("font-size: 10pt; color: #a0a0b2;")
        self.lbl_cls_degrad_val = QtWidgets.QLabel("Aguardando Leitura")
        self.lbl_cls_degrad_val.setStyleSheet("font-size: 13pt; font-weight: bold; color: #7f8c8d;")
        
        lbl_cls_conf_txt = QtWidgets.QLabel("Confiança da IA:")
        lbl_cls_conf_txt.setStyleSheet("font-size: 9pt; color: #7f8c8d; font-style: italic;")
        self.lbl_cls_conf_val = QtWidgets.QLabel("0.0%")
        self.lbl_cls_conf_val.setStyleSheet("font-size: 10pt; font-weight: bold; color: #3498db; font-style: italic;")
        
        group_classif_layout.addWidget(lbl_cls_material_txt, 0, 0)
        group_classif_layout.addWidget(self.lbl_cls_material_val, 0, 1)
        group_classif_layout.addWidget(lbl_cls_degrad_txt, 1, 0)
        group_classif_layout.addWidget(self.lbl_cls_degrad_val, 1, 1)
        group_classif_layout.addWidget(lbl_cls_conf_txt, 2, 0)
        group_classif_layout.addWidget(self.lbl_cls_conf_val, 2, 1)
        
        scroll_content_layout.addWidget(group_classif)

        # 5. Grupo de Filtros de Visualização do Gráfico de Tendência
        group_view = CollapsibleGroupBox("Filtros do Gráfico de Tendência")
        group_view_layout = QtWidgets.QVBoxLayout()
        group_view.setLayout(group_view_layout)
        
        self.chk_show_tau = QtWidgets.QCheckBox("Mostrar Tendência de Tau (Verde)")
        self.chk_show_tau.setChecked(True)
        self.chk_show_tau.stateChanged.connect(self.atualizar_visibilidade_tendencias)
        group_view_layout.addWidget(self.chk_show_tau)
        
        self.chk_show_tau_ma = QtWidgets.QCheckBox("Mostrar Média Móvel de Tau (Verde Tracejado)")
        self.chk_show_tau_ma.setChecked(True)
        self.chk_show_tau_ma.stateChanged.connect(self.atualizar_visibilidade_tendencias)
        group_view_layout.addWidget(self.chk_show_tau_ma)
        
        self.chk_show_auc = QtWidgets.QCheckBox("Mostrar Tendência de AUC (Azul)")
        self.chk_show_auc.setChecked(True)
        self.chk_show_auc.stateChanged.connect(self.atualizar_visibilidade_tendencias)
        group_view_layout.addWidget(self.chk_show_auc)
        
        self.chk_show_auc_ma = QtWidgets.QCheckBox("Mostrar Média Móvel de AUC (Azul Tracejado)")
        self.chk_show_auc_ma.setChecked(True)
        self.chk_show_auc_ma.stateChanged.connect(self.atualizar_visibilidade_tendencias)
        group_view_layout.addWidget(self.chk_show_auc_ma)
        
        scroll_content_layout.addWidget(group_view)

        # 6. Lista de Registros Coletados na Sessão (com opção de limpar visualmente)
        layout_titulo_hist = QtWidgets.QHBoxLayout()
        lbl_titulo_hist = QtWidgets.QLabel("Histórico de Amostras Gravadas:")
        lbl_titulo_hist.setStyleSheet("font-weight: bold; color: #a0a0b2;")
        layout_titulo_hist.addWidget(lbl_titulo_hist)
        
        self.btn_limpar_historico_visual = QtWidgets.QPushButton("Limpar Visual")
        self.btn_limpar_historico_visual.clicked.connect(self.limpar_historico_visual)
        self.btn_limpar_historico_visual.setStyleSheet("background-color: #2c2c2e; color: #e1e1e6; font-size: 8pt; border: 1px solid #444; max-width: 90px; padding: 2px;")
        layout_titulo_hist.addWidget(self.btn_limpar_historico_visual)
        
        scroll_content_layout.addLayout(layout_titulo_hist)
        
        self.list_historico = QtWidgets.QTextEdit()
        self.list_historico.setReadOnly(True)
        self.list_historico.setStyleSheet("background-color: #1c1c1e; color: #e1e1e6; font-family: Consolas; font-size: 9pt;")
        self.list_historico.setMinimumHeight(150)
        scroll_content_layout.addWidget(self.list_historico)

        # 6. Botão para limpar a tela
        self.btn_limpar_dataset = QtWidgets.QPushButton("Excluir / Filtrar Dados CSV")
        self.btn_limpar_dataset.clicked.connect(self.excluir_csv_local)
        self.btn_limpar_dataset.setStyleSheet("background-color: #c0392b; color: white;")
        scroll_content_layout.addWidget(self.btn_limpar_dataset)

        tab_acq_layout.addWidget(panel_left)

        # =====================================================================
        # PAINEL DIREITO: Gráficos em Tempo Real (pyqtgraph)
        # =====================================================================
        self.win_plots = pg.GraphicsLayoutWidget()
        tab_acq_layout.addWidget(self.win_plots)

        # Subplot 1: Curva Bruta Completa do ADC
        self.plot_bruto = self.win_plots.addPlot(title="Sinal Bruto Completo do ADC (256 pontos)")
        self.plot_bruto.showGrid(x=True, y=True)
        self.plot_bruto.setLabel('left', 'Amplitude', 'Counts')
        self.plot_bruto.setLabel('bottom', 'Índice de Amostragem')
        self.plot_bruto.setYRange(0, 65535)
        self.curve_bruto = self.plot_bruto.plot(pen=pg.mkPen('#3498db', width=2))
        
        # Linhas de auxílio visual
        self.line_peak = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('#e74c3c', style=QtCore.Qt.DashLine))
        self.line_offset = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('#95a5a6', style=QtCore.Qt.DashLine))
        self.plot_bruto.addItem(self.line_peak)
        self.plot_bruto.addItem(self.line_offset)

        self.win_plots.nextRow()

        # Subplot 2: Decaimento Transiente Alinhado (Subtraído Offset)
        self.plot_decay = self.win_plots.addPlot(title="Transiente de Decaimento Alinhado (Delta Counts)")
        self.plot_decay.showGrid(x=True, y=True)
        self.plot_decay.setLabel('left', 'Delta Counts')
        self.plot_decay.setLabel('bottom', 'Tempo', 'us')
        self.plot_decay.setYRange(0, 50000)
        self.curve_decay = self.plot_decay.plot(pen=pg.mkPen('#2ecc71', width=2))

        self.win_plots.nextRow()

        # Subplot 3: Tendência Temporal de AUC e Tau
        self.plot_trend = self.win_plots.addPlot(title="Tendência de Leituras em Tempo Real (Modo Contínuo)")
        self.plot_trend.showGrid(x=True, y=True)
        self.plot_trend.setLabel('left', 'Tau (us)', color='#2ecc71')
        self.plot_trend.setLabel('bottom', 'Número de Leituras')
        self.curve_trend_tau = self.plot_trend.plot(pen=pg.mkPen('#2ecc71', width=2), name="Tau")
        
        # Curva de Média Móvel para Tau (Verde tracejado mais espesso)
        self.curve_trend_tau_ma = self.plot_trend.plot(
            pen=pg.mkPen('#2ecc71', width=3, style=QtCore.Qt.DashLine), 
            name="Tau MA"
        )
        
        # Eixo y secundário para AUC no mesmo gráfico
        self.trend_auc_axis = pg.ViewBox()
        self.plot_trend.scene().addItem(self.trend_auc_axis)
        self.plot_trend.getAxis('right').linkToView(self.trend_auc_axis)
        self.plot_trend.getAxis('right').setLabel('AUC (Counts.us)', color='#3498db')
        self.trend_auc_axis.setXLink(self.plot_trend.vb)
        self.curve_trend_auc = pg.PlotCurveItem(pen=pg.mkPen('#3498db', width=2), name="AUC")
        self.trend_auc_axis.addItem(self.curve_trend_auc)
        
        # Curva de Média Móvel para AUC (Azul tracejado mais espesso)
        self.curve_trend_auc_ma = pg.PlotCurveItem(
            pen=pg.mkPen('#3498db', width=3, style=QtCore.Qt.DashLine), 
            name="AUC MA"
        )
        self.trend_auc_axis.addItem(self.curve_trend_auc_ma)

        self.plot_trend.vb.sigResized.connect(self.ajustar_viewbox_secundaria)

        # =====================================================================
        # ABA 2: Análise Estatística (Offline)
        # =====================================================================
        self.tab_stats = QtWidgets.QWidget()
        self.tab_widget.addTab(self.tab_stats, "Análise Estatística (Offline)")
        tab_stats_layout = QtWidgets.QHBoxLayout(self.tab_stats)
        
        # Sub-painel Esquerdo: Botões e Relatório de Texto
        stats_left = QtWidgets.QWidget()
        stats_left.setMaximumWidth(420)
        stats_left_layout = QtWidgets.QVBoxLayout(stats_left)
        
        self.btn_run_analysis = QtWidgets.QPushButton("Executar Análise Estatística")
        self.btn_run_analysis.setMinimumHeight(50)
        self.btn_run_analysis.setStyleSheet("background-color: #9b59b6; color: white; font-weight: bold; font-size: 11pt;")
        self.btn_run_analysis.clicked.connect(self.rodar_analise_estatistica)
        stats_left_layout.addWidget(self.btn_run_analysis)
        
        stats_left_layout.addWidget(QtWidgets.QLabel("Relatório Estatístico (Console):"))
        self.txt_report_stats = QtWidgets.QTextEdit()
        self.txt_report_stats.setReadOnly(True)
        self.txt_report_stats.setStyleSheet("background-color: #1c1c1e; color: #e1e1e6; font-family: Consolas; font-size: 10pt;")
        stats_left_layout.addWidget(self.txt_report_stats)
        
        # Painel de Filtros de Exibição (Canto Inferior Esquerdo, acima das legendas)
        group_filters = QtWidgets.QGroupBox("Filtros de Exibição")
        group_filters_layout = QtWidgets.QGridLayout(group_filters)
        group_filters.setStyleSheet("""
            QGroupBox {
                border: 1px solid #3a3a3c;
                border-radius: 4px;
                margin-top: 12px;
                font-weight: bold;
                color: #e1e1e6;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
            }
            QCheckBox {
                font-size: 9pt;
                color: #e1e1e6;
            }
        """)

        # Filtros de Materiais (Dinâmico)
        group_filters_layout.addWidget(QtWidgets.QLabel("<b>Materiais:</b>"), 0, 0)
        self.widget_filter_materiais = QtWidgets.QWidget()
        self.layout_filter_materiais = QtWidgets.QVBoxLayout(self.widget_filter_materiais)
        self.layout_filter_materiais.setContentsMargins(0, 5, 0, 5)
        self.layout_filter_materiais.setSpacing(6)
        group_filters_layout.addWidget(self.widget_filter_materiais, 1, 0, 6, 1)

        # Filtros de Classes
        group_filters_layout.addWidget(QtWidgets.QLabel("<b>Classes:</b>"), 0, 1)
        self.chk_filter_saudavel = QtWidgets.QCheckBox("Saudável")
        self.chk_filter_saudavel.setChecked(True)
        self.chk_filter_leve = QtWidgets.QCheckBox("Leve")
        self.chk_filter_leve.setChecked(True)
        self.chk_filter_moderada = QtWidgets.QCheckBox("Moderada")
        self.chk_filter_moderada.setChecked(True)
        self.chk_filter_avancada = QtWidgets.QCheckBox("Avançada")
        self.chk_filter_avancada.setChecked(True)
        self.chk_filter_corroido = QtWidgets.QCheckBox("Corroído")
        self.chk_filter_corroido.setChecked(True)
        self.chk_filter_ar_cls = QtWidgets.QCheckBox("Ar Livre")
        self.chk_filter_ar_cls.setChecked(True)

        group_filters_layout.addWidget(self.chk_filter_saudavel, 1, 1)
        group_filters_layout.addWidget(self.chk_filter_leve, 2, 1)
        group_filters_layout.addWidget(self.chk_filter_moderada, 3, 1)
        group_filters_layout.addWidget(self.chk_filter_avancada, 4, 1)
        group_filters_layout.addWidget(self.chk_filter_corroido, 5, 1)
        group_filters_layout.addWidget(self.chk_filter_ar_cls, 6, 1)
        
        self.chk_filter_outliers = QtWidgets.QCheckBox("Remover Outliers (IQR)")
        self.chk_filter_outliers.setChecked(False)
        group_filters_layout.addWidget(self.chk_filter_outliers, 7, 0, 1, 2)

        # Conecta os sinais de mudança para atualizar os gráficos dinamicamente
        self.chk_filter_saudavel.stateChanged.connect(self.atualizar_graficos_estatisticos)
        self.chk_filter_leve.stateChanged.connect(self.atualizar_graficos_estatisticos)
        self.chk_filter_moderada.stateChanged.connect(self.atualizar_graficos_estatisticos)
        self.chk_filter_avancada.stateChanged.connect(self.atualizar_graficos_estatisticos)
        self.chk_filter_corroido.stateChanged.connect(self.atualizar_graficos_estatisticos)
        self.chk_filter_ar_cls.stateChanged.connect(self.atualizar_graficos_estatisticos)
        self.chk_filter_outliers.stateChanged.connect(self.atualizar_graficos_estatisticos)

        stats_left_layout.addWidget(group_filters)
        
        # Painel de Legenda / Índice dos Gráficos (Canto Inferior Esquerdo)
        group_legend = QtWidgets.QGroupBox("Legenda dos Gráficos (Índice)")
        group_legend_layout = QtWidgets.QGridLayout(group_legend)
        group_legend.setStyleSheet("""
            QGroupBox {
                border: 1px solid #3a3a3c;
                border-radius: 4px;
                margin-top: 12px;
                font-weight: bold;
                color: #e1e1e6;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
            }
            QLabel {
                font-size: 9pt;
            }
        """)

        # Seção de Formas / Materiais
        lbl_formas_header = QtWidgets.QLabel("<b>Formas (Materiais):</b>")
        group_legend_layout.addWidget(lbl_formas_header, 0, 0, 1, 2)
        
        lbl_comum = QtWidgets.QLabel("<span style='font-size: 12pt;'>⚪</span> A36 Comum (Círculo)")
        lbl_ge = QtWidgets.QLabel("<span style='font-size: 12pt;'>⏹️</span> A36 GE - Galv. Eletrolítico (Quadrado)")
        lbl_gf = QtWidgets.QLabel("<span style='font-size: 12pt;'>🔶</span> A36 GF - Galv. a Fogo (Losango)")
        
        group_legend_layout.addWidget(lbl_comum, 1, 0, 1, 2)
        group_legend_layout.addWidget(lbl_ge, 2, 0, 1, 2)
        group_legend_layout.addWidget(lbl_gf, 3, 0, 1, 2)
        
        # Divisor horizontal
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        line.setStyleSheet("background-color: #3a3a3c;")
        group_legend_layout.addWidget(line, 4, 0, 1, 2)
        
        # Seção de Cores / Classes
        lbl_cores_header = QtWidgets.QLabel("<b>Cores (Degradação):</b>")
        group_legend_layout.addWidget(lbl_cores_header, 5, 0, 1, 2)
        
        lbl_saudavel = QtWidgets.QLabel("<span style='color: #3498db; font-size: 12pt;'>●</span> Saudável")
        lbl_leve = QtWidgets.QLabel("<span style='color: #1abc9c; font-size: 12pt;'>●</span> Leve")
        lbl_moderada = QtWidgets.QLabel("<span style='color: #f1c40f; font-size: 12pt;'>●</span> Moderada")
        lbl_avancada = QtWidgets.QLabel("<span style='color: #e67e22; font-size: 12pt;'>●</span> Avançada")
        lbl_corroido = QtWidgets.QLabel("<span style='color: #e74c3c; font-size: 12pt;'>●</span> Corroído")
        
        group_legend_layout.addWidget(lbl_saudavel, 6, 0)
        group_legend_layout.addWidget(lbl_leve, 6, 1)
        group_legend_layout.addWidget(lbl_moderada, 7, 0)
        group_legend_layout.addWidget(lbl_avancada, 7, 1)
        group_legend_layout.addWidget(lbl_corroido, 8, 0, 1, 2)

        stats_left_layout.addWidget(group_legend)
        
        tab_stats_layout.addWidget(stats_left)
        
        # Sub-painel Direito: Gráficos Estatísticos usando pyqtgraph
        self.win_stats_plots = pg.GraphicsLayoutWidget()
        self.win_stats_plots.setStyleSheet("background-color: #121214; border: 1px solid #3a3a3c;")
        tab_stats_layout.addWidget(self.win_stats_plots, 1)

        # 1. Subplot Superior Esquerdo: Sinais Médios
        self.plot_stat_curves = self.win_stats_plots.addPlot(title="Sinais Médios de Decaimento (Média ± DP)")
        self.plot_stat_curves.addLegend(offset=(10, 10))
        self.plot_stat_curves.showGrid(x=True, y=True)
        self.plot_stat_curves.setLabel('left', 'Delta Counts')
        self.plot_stat_curves.setLabel('bottom', 'Tempo', 'us')

        # 2. Subplot Superior Direito: Distribuição de AUC
        self.plot_stat_auc = self.win_stats_plots.addPlot(title="Distribuição da Área sob a Curva (AUC)")
        self.plot_stat_auc.showGrid(x=True, y=True)
        self.plot_stat_auc.setLabel('left', 'AUC')
        self.plot_stat_auc.getAxis('bottom').setTicks([[(1.0, 'Saudável'), (2.0, 'Corroído')]])

        self.win_stats_plots.nextRow()

        # 3. Subplot Inferior Esquerdo: Distribuição de Tau
        self.plot_stat_tau = self.win_stats_plots.addPlot(title="Distribuição da Constante de Tempo (Tau)")
        self.plot_stat_tau.showGrid(x=True, y=True)
        self.plot_stat_tau.setLabel('left', 'Tau', 'us')
        self.plot_stat_tau.getAxis('bottom').setTicks([[(1.0, 'Saudável'), (2.0, 'Corroído')]])

        # 4. Subplot Inferior Direito: Espaço de Características
        self.plot_stat_scatter = self.win_stats_plots.addPlot(title="Espaço de Características: AUC vs Tau")
        self.plot_stat_scatter.showGrid(x=True, y=True)
        self.plot_stat_scatter.setLabel('left', 'AUC')
        self.plot_stat_scatter.setLabel('bottom', 'Tau', 'us')

        # Conecta o sinal de movimento do mouse para exibir tooltips dinâmicos nos pontos
        self.win_stats_plots.scene().sigMouseMoved.connect(self.ao_mover_mouse_estatistico)

        # Tooltip flutuante personalizado (QLabel) para sobrepor nos gráficos estatísticos
        self.tooltip_estatistico = QtWidgets.QLabel(self)
        self.tooltip_estatistico.setStyleSheet("""
            background-color: #2e2e32;
            color: #ffffff;
            border: 2px solid #55555a;
            border-radius: 5px;
            padding: 8px;
            font-size: 10pt;
            font-family: 'Segoe UI', Arial, sans-serif;
        """)
        self.tooltip_estatistico.setVisible(False)
        self.tooltip_estatistico.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        # =====================================================================
        # ABA 3: Ensaios de Validação (Acurácia da IA)
        # =====================================================================
        self.tab_validacao = QtWidgets.QWidget()
        self.tab_widget.addTab(self.tab_validacao, "Ensaios de Validação (IA)")
        tab_val_layout = QtWidgets.QHBoxLayout(self.tab_validacao)
        
        # Sub-painel Esquerdo: Configuração do Teste
        val_left = QtWidgets.QWidget()
        val_left.setMaximumWidth(420)
        val_left_layout = QtWidgets.QVBoxLayout(val_left)
        val_left_layout.setContentsMargins(0, 0, 0, 0)
        val_left_layout.setSpacing(10)
        
        # Scroll Area para o painel esquerdo da validação (assim como na Aba 1)
        val_scroll = QtWidgets.QScrollArea()
        val_scroll.setWidgetResizable(True)
        val_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        val_scroll_widget = QtWidgets.QWidget()
        val_scroll_widget.setStyleSheet("background-color: transparent;")
        val_scroll_layout = QtWidgets.QVBoxLayout(val_scroll_widget)
        val_scroll_layout.setContentsMargins(0, 0, 8, 0)
        val_scroll_layout.setSpacing(12)
        val_scroll.setWidget(val_scroll_widget)
        val_left_layout.addWidget(val_scroll)
        
        # Grupo 1: Dados Reais do Cupom
        group_val_cupom = QtWidgets.QGroupBox("Dados Reais do Cupom")
        group_val_cupom.setStyleSheet("""
            QGroupBox {
                border: 2px solid #3a3a3c;
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
                color: #f1c40f;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        val_cupom_layout = QtWidgets.QGridLayout(group_val_cupom)
        val_cupom_layout.setSpacing(8)
        
        # ID do Cupom
        lbl_val_id = QtWidgets.QLabel("Nº Cupom Real:")
        lbl_val_id.setStyleSheet("font-weight: bold; color: #a0a0b2;")
        self.edit_val_id = QtWidgets.QLineEdit()
        self.edit_val_id.setPlaceholderText("Ex: 101")
        self.edit_val_id.setStyleSheet("background-color: #2e2e32; color: white; border: 1px solid #3a3a3c; border-radius: 4px; padding: 4px;")
        val_cupom_layout.addWidget(lbl_val_id, 0, 0)
        val_cupom_layout.addWidget(self.edit_val_id, 0, 1)
        
        # Material Real (RadioButtons - Dinâmico)
        lbl_val_mat = QtWidgets.QLabel("Material Real:")
        lbl_val_mat.setStyleSheet("font-weight: bold; color: #a0a0b2;")
        val_cupom_layout.addWidget(lbl_val_mat, 1, 0)
        
        self.widget_val_mat_radios = QtWidgets.QWidget()
        self.layout_val_mat_radios = QtWidgets.QGridLayout(self.widget_val_mat_radios)
        self.layout_val_mat_radios.setContentsMargins(0, 5, 0, 5)
        self.layout_val_mat_radios.setSpacing(6)
        val_cupom_layout.addWidget(self.widget_val_mat_radios, 1, 1)
        self.group_val_mat = QtWidgets.QButtonGroup(self)
        
        # Classe Real (RadioButtons)
        lbl_val_cls = QtWidgets.QLabel("Classe Real:")
        lbl_val_cls.setStyleSheet("font-weight: bold; color: #a0a0b2;")
        val_cupom_layout.addWidget(lbl_val_cls, 2, 0)
        
        widget_val_cls_radios = QtWidgets.QWidget()
        layout_val_cls_radios = QtWidgets.QGridLayout(widget_val_cls_radios)
        layout_val_cls_radios.setContentsMargins(0, 5, 0, 5)
        layout_val_cls_radios.setSpacing(6)
        
        self.rad_val_cls_saudavel = QtWidgets.QRadioButton("Saudável")
        self.rad_val_cls_leve = QtWidgets.QRadioButton("Leve")
        self.rad_val_cls_moderada = QtWidgets.QRadioButton("Moderada")
        self.rad_val_cls_avancada = QtWidgets.QRadioButton("Avançada")
        self.rad_val_cls_corroido = QtWidgets.QRadioButton("Corroído")
        self.rad_val_cls_ar = QtWidgets.QRadioButton("Ar Livre")
        
        self.rad_val_cls_saudavel.setStyleSheet(radio_stylesheet)
        self.rad_val_cls_leve.setStyleSheet(radio_stylesheet)
        self.rad_val_cls_moderada.setStyleSheet(radio_stylesheet)
        self.rad_val_cls_avancada.setStyleSheet(radio_stylesheet)
        self.rad_val_cls_corroido.setStyleSheet(radio_stylesheet)
        self.rad_val_cls_ar.setStyleSheet(radio_stylesheet)
        
        self.group_val_cls = QtWidgets.QButtonGroup(self)
        self.group_val_cls.addButton(self.rad_val_cls_saudavel)
        self.group_val_cls.addButton(self.rad_val_cls_leve)
        self.group_val_cls.addButton(self.rad_val_cls_moderada)
        self.group_val_cls.addButton(self.rad_val_cls_avancada)
        self.group_val_cls.addButton(self.rad_val_cls_corroido)
        self.group_val_cls.addButton(self.rad_val_cls_ar)
        self.rad_val_cls_saudavel.setChecked(True)
        
        layout_val_cls_radios.addWidget(self.rad_val_cls_saudavel, 0, 0)
        layout_val_cls_radios.addWidget(self.rad_val_cls_leve, 0, 1)
        layout_val_cls_radios.addWidget(self.rad_val_cls_moderada, 1, 0)
        layout_val_cls_radios.addWidget(self.rad_val_cls_avancada, 1, 1)
        layout_val_cls_radios.addWidget(self.rad_val_cls_corroido, 2, 0)
        layout_val_cls_radios.addWidget(self.rad_val_cls_ar, 2, 1)
        val_cupom_layout.addWidget(widget_val_cls_radios, 2, 1)
        
        # Conecta eventos Ar Livre
        self.rad_val_cls_ar.toggled.connect(self.ao_toggle_ar_livre_val_classe)
        
        val_scroll_layout.addWidget(group_val_cupom)
        
        # Grupo 2: Configuração de Tempo
        group_val_tempo = QtWidgets.QGroupBox("Duração do Teste de Validação")
        group_val_tempo.setStyleSheet("""
            QGroupBox {
                border: 2px solid #3a3a3c;
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
                color: #9b59b6;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        val_tempo_layout = QtWidgets.QVBoxLayout(group_val_tempo)
        val_tempo_layout.setSpacing(8)
        
        self.combo_val_duracao = QtWidgets.QComboBox()
        self.combo_val_duracao.addItems(["Contínuo (Manual)", "1 segundo", "10 segundos", "30 segundos", "60 segundos"])
        self.combo_val_duracao.setStyleSheet("""
            QComboBox {
                background-color: #2e2e32;
                color: white;
                border: 1px solid #3a3a3c;
                border-radius: 4px;
                padding: 6px;
                font-size: 10pt;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        val_tempo_layout.addWidget(self.combo_val_duracao)
        val_scroll_layout.addWidget(group_val_tempo)
        
        # Grupo 3: Ações e Controles
        group_val_control = QtWidgets.QGroupBox("Controle do Teste")
        group_val_control.setStyleSheet("""
            QGroupBox {
                border: 2px solid #3a3a3c;
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
                color: #e74c3c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        val_control_layout = QtWidgets.QVBoxLayout(group_val_control)
        val_control_layout.setSpacing(10)
        
        self.btn_val_iniciar = QtWidgets.QPushButton("Iniciar Teste")
        self.btn_val_iniciar.clicked.connect(self.iniciar_ensaio_validacao)
        self.btn_val_iniciar.setMinimumHeight(45)
        self.btn_val_iniciar.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 11pt;")
        
        self.btn_val_finalizar = QtWidgets.QPushButton("Finalizar Teste")
        self.btn_val_finalizar.clicked.connect(self.finalizar_ensaio_validacao)
        self.btn_val_finalizar.setMinimumHeight(45)
        self.btn_val_finalizar.setEnabled(False)
        self.btn_val_finalizar.setStyleSheet("background-color: #7f8c8d; color: white; font-weight: bold; font-size: 11pt;")
        
        self.lbl_val_status = QtWidgets.QLabel("Status: Pronto")
        self.lbl_val_status.setStyleSheet("color: #e1e1e6; font-size: 10pt; font-weight: bold;")
        self.lbl_val_timer = QtWidgets.QLabel("Tempo Restante: -- s")
        self.lbl_val_timer.setStyleSheet("color: #a0a0b2; font-size: 10pt;")
        
        self.progress_val = QtWidgets.QProgressBar()
        self.progress_val.setValue(0)
        self.progress_val.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a3c;
                border-radius: 4px;
                text-align: center;
                background-color: #121214;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #9b59b6;
            }
        """)
        
        val_control_layout.addWidget(self.btn_val_iniciar)
        val_control_layout.addWidget(self.btn_val_finalizar)
        val_control_layout.addWidget(self.lbl_val_status)
        val_control_layout.addWidget(self.lbl_val_timer)
        val_control_layout.addWidget(self.progress_val)
        val_scroll_layout.addWidget(group_val_control)
        
        tab_val_layout.addWidget(val_left)
        
        # Sub-painel Direito: Tabela, Cards e Console
        val_right = QtWidgets.QWidget()
        val_right_layout = QtWidgets.QVBoxLayout(val_right)
        val_right_layout.setContentsMargins(0, 0, 0, 0)
        val_right_layout.setSpacing(12)
        
        # Cards Superiores de Acurácia (Layout Horizontal)
        layout_val_cards = QtWidgets.QHBoxLayout()
        
        self.card_val_capturas = QtWidgets.QWidget()
        self.card_val_capturas.setStyleSheet("background-color: #2e2e32; border: 1px solid #3a3a3c; border-radius: 6px;")
        layout_card1 = QtWidgets.QVBoxLayout(self.card_val_capturas)
        layout_card1.setContentsMargins(10, 8, 10, 8)
        lbl_c1_title = QtWidgets.QLabel("AMOSTRAS CAPTURADAS")
        lbl_c1_title.setStyleSheet("font-size: 8pt; color: #a0a0b2; font-weight: bold;")
        self.lbl_c1_val = QtWidgets.QLabel("0")
        self.lbl_c1_val.setStyleSheet("font-size: 16pt; color: #ffffff; font-weight: bold;")
        layout_card1.addWidget(lbl_c1_title)
        layout_card1.addWidget(self.lbl_c1_val)
        
        self.card_val_acuracia_mat = QtWidgets.QWidget()
        self.card_val_acuracia_mat.setStyleSheet("background-color: #2e2e32; border: 1px solid #3a3a3c; border-radius: 6px;")
        layout_card2 = QtWidgets.QVBoxLayout(self.card_val_acuracia_mat)
        layout_card2.setContentsMargins(10, 8, 10, 8)
        lbl_c2_title = QtWidgets.QLabel("ACURÁCIA MATERIAL")
        lbl_c2_title.setStyleSheet("font-size: 8pt; color: #a0a0b2; font-weight: bold;")
        self.lbl_c2_val = QtWidgets.QLabel("0.0%")
        self.lbl_c2_val.setStyleSheet("font-size: 16pt; color: #3498db; font-weight: bold;")
        layout_card2.addWidget(lbl_c2_title)
        layout_card2.addWidget(self.lbl_c2_val)
        
        self.card_val_acuracia_cls = QtWidgets.QWidget()
        self.card_val_acuracia_cls.setStyleSheet("background-color: #2e2e32; border: 1px solid #3a3a3c; border-radius: 6px;")
        layout_card3 = QtWidgets.QVBoxLayout(self.card_val_acuracia_cls)
        layout_card3.setContentsMargins(10, 8, 10, 8)
        lbl_c3_title = QtWidgets.QLabel("ACURÁCIA CLASSE")
        lbl_c3_title.setStyleSheet("font-size: 8pt; color: #a0a0b2; font-weight: bold;")
        self.lbl_c3_val = QtWidgets.QLabel("0.0%")
        self.lbl_c3_val.setStyleSheet("font-size: 16pt; color: #2ecc71; font-weight: bold;")
        layout_card3.addWidget(lbl_c3_title)
        layout_card3.addWidget(self.lbl_c3_val)
        
        layout_val_cards.addWidget(self.card_val_capturas)
        layout_val_cards.addWidget(self.card_val_acuracia_mat)
        layout_val_cards.addWidget(self.card_val_acuracia_cls)
        val_right_layout.addLayout(layout_val_cards)
        
        # Tabela Widget
        self.tbl_val_resultados = QtWidgets.QTableWidget()
        self.tbl_val_resultados.setColumnCount(9)
        self.tbl_val_resultados.setHorizontalHeaderLabels([
            "Amostra", "Tempo (s)", "Tau (μs)", "AUC", "Mat. Real", "Mat. Previsto", "Cls. Real", "Cls. Prevista", "Match?"
        ])
        self.tbl_val_resultados.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.tbl_val_resultados.setStyleSheet("""
            QTableWidget {
                background-color: #121214;
                color: #e1e1e6;
                gridline-color: #2e2e32;
                border: 1px solid #3a3a3c;
                font-size: 9pt;
            }
            QHeaderView::section {
                background-color: #2e2e32;
                color: #ffffff;
                padding: 4px;
                border: 1px solid #3a3a3c;
                font-weight: bold;
            }
        """)
        val_right_layout.addWidget(self.tbl_val_resultados, 2)
        
        # Console de Logs e Relatório Final
        self.console_val_relatorio = QtWidgets.QTextEdit()
        self.console_val_relatorio.setReadOnly(True)
        self.console_val_relatorio.setPlaceholderText("Console de Relatório de Ensaio...")
        self.console_val_relatorio.setStyleSheet("""
            QTextEdit {
                background-color: #0c0c0d;
                color: #00ff00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                border: 1px solid #3a3a3c;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        val_right_layout.addWidget(self.console_val_relatorio, 1)
        
        tab_val_layout.addWidget(val_right)
        
        # =====================================================================
        # ABA 4: Diagnóstico Físico & IA (Tempo Real)
        # =====================================================================
        self.tab_diag = QtWidgets.QWidget()
        self.tab_widget.addTab(self.tab_diag, "Diagnóstico Físico & IA (TR)")
        tab_diag_layout = QtWidgets.QHBoxLayout(self.tab_diag)
        
        # Sub-painel Esquerdo: Controles e Cards em Tempo Real
        diag_left = QtWidgets.QWidget()
        diag_left.setMaximumWidth(420)
        diag_left_layout = QtWidgets.QVBoxLayout(diag_left)
        diag_left_layout.setContentsMargins(0, 0, 0, 0)
        diag_left_layout.setSpacing(12)
        
        # Botão de Trigger Rápido
        self.btn_diag_trigger = QtWidgets.QPushButton("Iniciar Leitura Contínua")
        self.btn_diag_trigger.setMinimumHeight(50)
        self.btn_diag_trigger.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 11pt; border-radius: 4px;")
        self.btn_diag_trigger.clicked.connect(self.alternar_trigger_diagnostico)
        diag_left_layout.addWidget(self.btn_diag_trigger)
        
        # Card de Classificação em Tempo Real
        group_diag_status = QtWidgets.QGroupBox("Resultado IA em Tempo Real")
        group_diag_status.setStyleSheet("""
            QGroupBox {
                border: 2px solid #3a3a3c;
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
                color: #f1c40f;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        diag_status_layout = QtWidgets.QVBoxLayout(group_diag_status)
        diag_status_layout.setSpacing(10)
        
        # Labels de diagnóstico
        self.lbl_diag_material = QtWidgets.QLabel("Material: ---")
        self.lbl_diag_material.setStyleSheet("font-size: 13pt; font-weight: bold; color: white;")
        self.lbl_diag_classe = QtWidgets.QLabel("Classe: ---")
        self.lbl_diag_classe.setStyleSheet("font-size: 13pt; font-weight: bold; color: #7f8c8d;")
        self.lbl_diag_confianca = QtWidgets.QLabel("Confiança: ---")
        self.lbl_diag_confianca.setStyleSheet("font-size: 11pt; color: #a0a0b2;")
        
        diag_status_layout.addWidget(self.lbl_diag_material)
        diag_status_layout.addWidget(self.lbl_diag_classe)
        diag_status_layout.addWidget(self.lbl_diag_confianca)
        diag_left_layout.addWidget(group_diag_status)
        
        # Card de Métricas Físicas
        group_diag_metrics = QtWidgets.QGroupBox("Métricas Físicas do Sinal")
        group_diag_metrics.setStyleSheet("""
            QGroupBox {
                border: 2px solid #3a3a3c;
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
                color: #3498db;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        diag_metrics_layout = QtWidgets.QVBoxLayout(group_diag_metrics)
        diag_metrics_layout.setSpacing(10)
        
        self.lbl_diag_tau = QtWidgets.QLabel("Tau (\u03bcs): ---")
        self.lbl_diag_tau.setStyleSheet("font-size: 11pt; color: white;")
        self.lbl_diag_auc = QtWidgets.QLabel("AUC: ---")
        self.lbl_diag_auc.setStyleSheet("font-size: 11pt; color: white;")
        self.lbl_diag_r2 = QtWidgets.QLabel("R\u00b2: ---")
        self.lbl_diag_r2.setStyleSheet("font-size: 11pt; color: white;")
        
        diag_metrics_layout.addWidget(self.lbl_diag_tau)
        diag_metrics_layout.addWidget(self.lbl_diag_auc)
        diag_metrics_layout.addWidget(self.lbl_diag_r2)
        diag_left_layout.addWidget(group_diag_metrics)
        
        # Espaçador vertical para empurrar os widgets para o topo
        diag_left_layout.addStretch()
        tab_diag_layout.addWidget(diag_left)
        
        # Sub-painel Direito: Gráficos de Diagnóstico em Tempo Real
        self.win_diag_plots = pg.GraphicsLayoutWidget()
        self.win_diag_plots.setStyleSheet("background-color: #121214; border: 1px solid #3a3a3c;")
        tab_diag_layout.addWidget(self.win_diag_plots, 1)
        
        # Configurar subplots da aba de diagnóstico
        self.plot_diag_curves = self.win_diag_plots.addPlot(title="Decaimento Comparativo: Ativo vs. Banco de Dados")
        self.plot_diag_curves.addLegend(offset=(10, 10))
        self.plot_diag_curves.showGrid(x=True, y=True)
        self.plot_diag_curves.setLabel('left', 'Delta Counts')
        self.plot_diag_curves.setLabel('bottom', 'Tempo', 'us')
        
        self.plot_diag_auc = self.win_diag_plots.addPlot(title="Distribuição AUC com Indicador de Leitura")
        self.plot_diag_auc.showGrid(x=True, y=True)
        self.plot_diag_auc.setLabel('left', 'AUC')
        
        self.win_diag_plots.nextRow()
        
        self.plot_diag_tau = self.win_diag_plots.addPlot(title="Distribuição Tau com Indicador de Leitura")
        self.plot_diag_tau.showGrid(x=True, y=True)
        self.plot_diag_tau.setLabel('left', 'Tau', 'us')
        
        self.plot_diag_scatter = self.win_diag_plots.addPlot(title="Espaço de Características: Ativo vs. DB")
        self.plot_diag_scatter.showGrid(x=True, y=True)
        self.plot_diag_scatter.setLabel('left', 'AUC')
        self.plot_diag_scatter.setLabel('bottom', 'Tau', 'us')
        
        # Conecta sinal de mudança de aba para carregar/atualizar os gráficos da Aba 4
        self.tab_widget.currentChanged.connect(self.ao_mudar_aba)
        
        # Variáveis para armazenar referências das curvas de banco de dados plotadas na Aba 4
        self.diag_active_curve = None
        self.diag_active_scatter = None
        self.diag_active_auc_line = None
        self.diag_active_tau_line = None
        
        # Reconstrói a lista dinâmica de materiais no início
        self.atualizar_widgets_materiais()

    def ajustar_viewbox_secundaria(self):
        # Ajusta a escala da ViewBox secundária (AUC) para coincidir com o tamanho do gráfico
        self.trend_auc_axis.setGeometry(self.plot_trend.vb.sceneBoundingRect())
        self.trend_auc_axis.linkedViewChanged(self.plot_trend.vb, pg.ViewBox.XAxis)

    # =====================================================================
    # LÓGICA DA ABA 4: DIAGNÓSTICO EM TEMPO REAL
    # =====================================================================
    def ao_mudar_aba(self, index):
        # Se for a Aba 4 (Diagnóstico em Tempo Real), inicializa
        if index == 3:
            self.inicializar_graficos_diagnostico()
            
            # Sincroniza o botão de trigger da Aba 4 com o estado do auto_trigger
            if self.chk_auto_trigger.isChecked():
                self.btn_diag_trigger.setText("Pausar Diagnóstico")
                self.btn_diag_trigger.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; font-size: 11pt; border-radius: 4px;")
            else:
                self.btn_diag_trigger.setText("Iniciar Diagnóstico")
                self.btn_diag_trigger.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 11pt; border-radius: 4px;")

    def alternar_trigger_diagnostico(self):
        if not self.serial_thread.running:
            QtWidgets.QMessageBox.warning(self, "Sem Conexão", "Por favor, conecte a placa na porta serial primeiro!")
            return
            
        # Inverte o estado do Auto-Trigger
        novo_estado = not self.chk_auto_trigger.isChecked()
        self.chk_auto_trigger.setChecked(novo_estado)

    def inicializar_graficos_diagnostico(self):
        # Garante carregamento do banco de dados
        if not hasattr(self, 'amostras_estatisticas') or not self.amostras_estatisticas:
            self.rodar_analise_estatistica()
            
        if not hasattr(self, 'amostras_estatisticas') or not self.amostras_estatisticas:
            return

        # Limpa os plots
        self.plot_diag_curves.clear()
        self.plot_diag_auc.clear()
        self.plot_diag_tau.clear()
        self.plot_diag_scatter.clear()
        
        # Reseta os elementos ativos
        self.diag_active_curve = None
        self.diag_active_scatter = None
        self.diag_active_auc_line = None
        self.diag_active_tau_line = None
        
        # Ativa o auto-range
        self.plot_diag_curves.enableAutoRange(x=True, y=True)
        self.plot_diag_auc.enableAutoRange(x=True, y=True)
        self.plot_diag_tau.enableAutoRange(x=True, y=True)
        self.plot_diag_scatter.enableAutoRange(x=True, y=True)

        CLASSES_ORDEM = ["Saudável", "Leve", "Moderada", "Avançada", "Corroído", "Ar Livre"]
        CORES_CLASSES = {
            "Saudável": "#3498db",  # Azul
            "Leve": "#1abc9c",      # Ciano
            "Moderada": "#f1c40f",  # Amarelo
            "Avançada": "#e67e22",  # Laranja
            "Corroído": "#e74c3c",  # Vermelho
            "Ar Livre": "#9b59b6"   # Roxo
        }
        CORES_RGB = {
            "Saudável": (52, 152, 219),
            "Leve": (26, 188, 156),
            "Moderada": (241, 196, 15),
            "Avançada": (230, 126, 34),
            "Corroído": (231, 76, 60),
            "Ar Livre": (155, 89, 182)
        }
        SIMBOLOS_MATERIAIS = {
            "A36 Comum": "o",
            "A36 GE": "s",
            "A36 GF": "d"
        }

        # Filtra outliers caso a caixinha do IQR esteja marcada ou por padrão
        amostras_limpas = self.filtrar_outliers_iqr(self.amostras_estatisticas) if hasattr(self, 'filtrar_outliers_iqr') else self.amostras_estatisticas
        
        # Agrupa os dados
        dados_por_classe = {c: {"auc": [], "tau": [], "curvas": []} for c in CLASSES_ORDEM}
        for a in amostras_limpas:
            c = a["classe"]
            if c not in dados_por_classe:
                dados_por_classe[c] = {"auc": [], "tau": [], "curvas": []}
            dados_por_classe[c]["auc"].append(a["auc"])
            dados_por_classe[c]["tau"].append(a["tau"])
            dados_por_classe[c]["curvas"].append(a["curva"])

        # Determina a unidade de tempo do diagnóstico baseada no dt_us das amostras
        primeira_amostra = amostras_limpas[0] if amostras_limpas else None
        diag_dt = primeira_amostra["dt_us"] if (primeira_amostra and "dt_us" in primeira_amostra) else self.dt_us
        fator_diag, unid_diag = self.obter_unidade_tempo(diag_dt)

        # 1. Curvas médias de referência com escala dinâmica
        max_len = 150
        t = np.arange(max_len) * diag_dt * fator_diag
        self.plot_diag_curves.setLabel('bottom', 'Tempo', unid_diag)
        
        if hasattr(self.plot_diag_curves, 'legend') and self.plot_diag_curves.legend is not None:
            self.plot_diag_curves.legend.clear()
            
        for c in CLASSES_ORDEM:
            curvas = dados_por_classe.get(c, {}).get("curvas", [])
            if not curvas:
                continue
            
            ajustadas = []
            for cv in curvas:
                if len(cv) >= max_len:
                    ajustadas.append(cv[:max_len])
                else:
                    ajustadas.append(np.pad(cv, (0, max_len - len(cv)), 'constant'))
            mean = np.mean(np.array(ajustadas), axis=0)
            
            color = CORES_CLASSES.get(c, "#7f8c8d")
            self.plot_diag_curves.plot(
                t, mean, 
                pen=pg.mkPen(color, width=1.5, style=QtCore.Qt.DotLine), 
                name=f"Ref: {c}"
            )

        # 2. Scatter plot do banco de dados (nuvem de pontos semi-transparente)
        for c in CLASSES_ORDEM:
            curvas = dados_por_classe.get(c, {}).get("curvas", [])
            if not curvas:
                continue
                
            auc_list = dados_por_classe[c]["auc"]
            tau_list = dados_por_classe[c]["tau"]
            rgb = CORES_RGB.get(c, (127, 140, 141))
            
            amostras_classe = [a for a in amostras_limpas if a["classe"] == c]
            materiais_presentes = list(set([a["material"] for a in amostras_classe]))
            
            for mat_nome in materiais_presentes:
                simbolo = SIMBOLOS_MATERIAIS.get(mat_nome, "o")
                indices_mat = [i for i, a in enumerate(amostras_classe) if a["material"] == mat_nome]
                if not indices_mat:
                    continue
                
                tau_sub = [tau_list[i] * fator_diag for i in indices_mat]
                auc_sub = [auc_list[i] for i in indices_mat]
                
                self.plot_diag_scatter.plot(
                    tau_sub, auc_sub, pen=None, symbol=simbolo, symbolSize=6,
                    symbolBrush=pg.mkBrush(rgb[0], rgb[1], rgb[2], 80),
                    symbolPen=None
                )

        # 3. Distribuições de referência
        ticks = []
        x_val = 1.0
        posicoes_classes = {}
        for c in CLASSES_ORDEM:
            n_amostras = len(dados_por_classe.get(c, {}).get("auc", []))
            if n_amostras > 0:
                ticks.append((x_val, c.capitalize()))
                posicoes_classes[c] = x_val
                x_val += 1.0
                
        self.plot_diag_auc.getAxis('bottom').setTicks([ticks])
        self.plot_diag_tau.getAxis('bottom').setTicks([ticks])
        
        if posicoes_classes:
            self.plot_diag_auc.setXRange(0.5, max(1.5, x_val - 0.5))
            self.plot_diag_tau.setXRange(0.5, max(1.5, x_val - 0.5))
            
        for c, x in posicoes_classes.items():
            dados_auc = dados_por_classe[c]["auc"]
            dados_tau = dados_por_classe[c]["tau"]
            color = CORES_CLASSES.get(c, "#7f8c8d")
            
            m_a, s_a = np.mean(dados_auc), np.std(dados_auc)
            self.plot_diag_auc.plot([x, x], [m_a - s_a, m_a + s_a], pen=pg.mkPen(color, width=2))
            self.plot_diag_auc.plot([x - 0.15, x + 0.15], [m_a, m_a], pen=pg.mkPen('w', width=2))
            
            m_t, s_t = np.mean(dados_tau) * fator_diag, np.std(dados_tau) * fator_diag
            self.plot_diag_tau.plot([x, x], [m_t - s_t, m_t + s_t], pen=pg.mkPen(color, width=2))
            self.plot_diag_tau.plot([x - 0.15, x + 0.15], [m_t, m_t], pen=pg.mkPen('w', width=2))
            
        # Atualiza os eixos dos plots na Aba 4 com a unidade dinâmica correspondente
        self.plot_diag_tau.setLabel('left', 'Tau', unid_diag)
        self.plot_diag_scatter.setLabel('bottom', 'Tau', unid_diag)

    # =====================================================================
    # LÓGICA DE GERENCIAMENTO DE CONEXÃO
    # =====================================================================
    def atualizar_portas_disponiveis(self):
        self.combo_portas.clear()
        portas = [p.device for p in serial.tools.list_ports.comports()]
        self.combo_portas.addItems(portas)

    def auto_detectar_e_conectar(self):
        portas = list(serial.tools.list_ports.comports())
        porta_detectada = None
        for p in portas:
            desc = p.description.lower()
            if "stmicroelectronics" in desc or "stlink" in desc or "st-link" in desc:
                porta_detectada = p.device
                break
        
        if porta_detectada:
            index = self.combo_portas.findText(porta_detectada)
            if index != -1:
                self.combo_portas.setCurrentIndex(index)
            print(f"[INFO] Auto-conectar na porta: {porta_detectada}")
            self.alternar_conexao()

    def alternar_conexao(self):
        if not self.serial_thread.running:
            porta = self.combo_portas.currentText()
            baud = int(self.combo_baud.currentText())
            if not porta:
                QtWidgets.QMessageBox.warning(self, "Sem portas", "Nenhuma porta COM ativa encontrada!")
                return
            
            self.serial_thread.conectar(porta, baud)
            self.lbl_status_conn.setText(f"Status: Conectado ({porta} @ {baud} bps)")
            self.lbl_status_conn.setStyleSheet("color: #2ecc71; font-weight: bold;")
            self.btn_conectar.setText("Desconectar")
            self.btn_conectar.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        else:
            self.chk_auto_trigger.setChecked(False) # Desativa auto-trigger antes de desligar
            self.serial_thread.desconectar()
            self.lbl_status_conn.setText("Status: Desconectado")
            self.lbl_status_conn.setStyleSheet("color: #e74c3c; font-weight: bold;")
            self.btn_conectar.setText("Conectar")
            self.btn_conectar.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")

    def tratar_erro_serial(self, msg_erro):
        print(f"[ERRO SERIAL]: {msg_erro}")
        self.chk_auto_trigger.setChecked(False)
        if self.serial_thread.running:
            self.alternar_conexao()
        QtWidgets.QMessageBox.critical(self, "Erro de Conexão", f"Falha na comunicação serial:\n{msg_erro}")

    # =====================================================================
    # CONTROLE DE LEITURA E PRODUTO FÍSICO
    # =====================================================================
    def solicitar_leitura_manual(self):
        if not self.serial_thread.running:
            QtWidgets.QMessageBox.warning(self, "Sem conexão", "Conecte na porta serial antes de disparar!")
            return
        self.serial_thread.disparar_leitura()

    def solicitar_leitura_automatica(self):
        if self.serial_thread.running:
            self.serial_thread.disparar_leitura()

    def alternar_auto_trigger(self, state):
        if state == QtCore.Qt.Checked:
            if not self.serial_thread.running:
                QtWidgets.QMessageBox.warning(self, "Sem conexão", "Conecte na porta serial primeiro!")
                self.chk_auto_trigger.setChecked(False)
                return
            self.btn_single_trigger.setEnabled(False)
            self.auto_trigger_timer.start(30) # Disparos a cada 30 ms (máxima velocidade física permitida pela serial)
            if hasattr(self, 'btn_diag_trigger'):
                self.btn_diag_trigger.setText("Pausar Diagnóstico")
                self.btn_diag_trigger.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; font-size: 11pt; border-radius: 4px;")
        else:
            self.auto_trigger_timer.stop()
            self.btn_single_trigger.setEnabled(True)
            if hasattr(self, 'btn_diag_trigger'):
                self.btn_diag_trigger.setText("Iniciar Diagnóstico")
                self.btn_diag_trigger.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 11pt; border-radius: 4px;")

    def alternar_modo_ets(self, state):
        if state == QtCore.Qt.Checked:
            self.serial_thread.set_modo_ets(True)
            self.arquivo_csv = "dataset_cupons_indutancia_ets.csv"
            self.spin_dt.setValue(0.00001)
            self.plot_decay.setLabel('bottom', 'Tempo (Modo ETS)', 'us')
            print(f"[INFO] Modo ETS (Tempo Equivalente) ativado. Dataset: {self.arquivo_csv} | dt = 0.00001 us")
        else:
            self.serial_thread.set_modo_ets(False)
            self.arquivo_csv = "dataset_cupons_indutancia.csv"
            self.spin_dt.setValue(0.00001)
            self.plot_decay.setLabel('bottom', 'Tempo (Modo DMA)', 'us')
            print(f"[INFO] Modo DMA (Padrão) ativado. Dataset: {self.arquivo_csv} | dt = 0.00001 us")
            
        # Re-treina o classificador e atualiza a IA na hora com base no novo dataset
        self.treinar_classificador()

    def atualizar_dt_us(self, value):
        self.dt_us = value
        # Re-treina o classificador para recalcular as constantes no novo intervalo dt
        self.treinar_classificador()
        # Atualiza o rótulo do eixo X se não estiver em modo ETS para refletir a taxa real configurada
        if not self.chk_ets.isChecked():
            khz = 1000.0 / value if value > 0 else 0
            self.plot_decay.setLabel('bottom', f'Tempo (Modo DMA - {khz:.2f} kHz)', 'us')

    def atualizar_tamanho_janela_metricas(self, value):
        self.trend_tau = deque(list(self.trend_tau), maxlen=value)
        self.trend_auc = deque(list(self.trend_auc), maxlen=value)
        self.trend_indices = deque(list(self.trend_indices), maxlen=value)
        self.recent_curves = deque(list(self.recent_curves), maxlen=value)
        print(f"[INFO] Janela de estabilização de métricas atualizada para {value} amostras.")

    def suavizar_curva(self, valores, janela):
        if janela <= 1:
            return valores
        valores_arr = np.array(valores, dtype=float)
        ret = np.copy(valores_arr)
        meio = janela // 2
        for i in range(len(valores_arr)):
            start = max(0, i - meio)
            end = min(len(valores_arr), i + meio + 1)
            ret[i] = np.mean(valores_arr[start:end])
        return ret.tolist()

    def atualizar_visibilidade_tendencias(self):
        show_tau = self.chk_show_tau.isChecked()
        show_tau_ma = self.chk_show_tau_ma.isChecked()
        show_auc = self.chk_show_auc.isChecked()
        show_auc_ma = self.chk_show_auc_ma.isChecked()
        
        # Oculta/Exibe a linha de dados de Tau
        if show_tau:
            self.curve_trend_tau.setPen(pg.mkPen('#2ecc71', width=2))
        else:
            self.curve_trend_tau.setPen(pg.mkPen(None))
            
        # Oculta/Exibe a linha de Média Móvel de Tau
        if show_tau_ma:
            self.curve_trend_tau_ma.setPen(pg.mkPen('#2ecc71', width=2, style=QtCore.Qt.DashLine))
        else:
            self.curve_trend_tau_ma.setPen(pg.mkPen(None))
            
        # Oculta/Exibe a linha de dados de AUC
        if show_auc:
            self.curve_trend_auc.setPen(pg.mkPen('#3498db', width=2))
        else:
            self.curve_trend_auc.setPen(pg.mkPen(None))
            
        # Oculta/Exibe a linha de Média Móvel de AUC
        if show_auc_ma:
            self.curve_trend_auc_ma.setPen(pg.mkPen('#3498db', width=2, style=QtCore.Qt.DashLine))
        else:
            self.curve_trend_auc_ma.setPen(pg.mkPen(None))
        
        # Eixo Y esquerdo (Tau) visível se pelo menos um estiver marcado
        self.plot_trend.getAxis('left').setVisible(show_tau or show_tau_ma)
        # Eixo Y direito (AUC) visível se pelo menos um estiver marcado
        self.plot_trend.getAxis('right').setVisible(show_auc or show_auc_ma)

    # =====================================================================
    # ARQUITETURA DE CLASSIFICAÇÃO INTELIGENTE (IA - NEAREST CENTROID NORMALIZADO)
    # =====================================================================
    def treinar_classificador(self):
        self.centroids = {}
        if not os.path.exists(self.arquivo_csv):
            return
        
        conteudo_csv = None
        try:
            with open(self.arquivo_csv, "r", newline="", encoding="utf-8") as f:
                conteudo_csv = f.read()
        except UnicodeDecodeError:
            try:
                with open(self.arquivo_csv, "r", newline="", encoding="latin-1") as f:
                    conteudo_csv = f.read()
            except Exception:
                return
        except Exception:
            return

        import io
        try:
            f_string = io.StringIO(conteudo_csv)
            reader = csv.reader(f_string, delimiter=";")
            headers = next(reader)
            
            material_idx = headers.index("material") if "material" in headers else 1
            classe_idx = headers.index("classe") if "classe" in headers else 2
            dt_idx = headers.index("dt_us") if "dt_us" in headers else -1
            p_start_idx = headers.index("p_0") if "p_0" in headers else 4
            
            pontos = []
            
            for row in reader:
                if not row or len(row) < 260:
                    continue
                
                material = row[material_idx].strip()
                classe = normalizar_nome_classe(row[classe_idx])
                
                # Suporta arquivos mistos (com ou sem a coluna de dt_us)
                # Formato antigo tem 260 colunas, formato novo (com dt_us) tem 261 colunas
                if len(row) >= 261:
                    try:
                        row_dt = float(row[4].strip()) if row[4].strip() else self.dt_us
                    except ValueError:
                        row_dt = self.dt_us
                    p_start = 5
                else:
                    row_dt = self.dt_us
                    p_start = 4
                
                try:
                    curva = [int(val) for val in row[p_start:p_start+256]]
                except ValueError as ve:
                    print(f"[CLASSIFICADOR] Erro ao converter pontos da curva: {ve} | Linha: {row[:5]}")
                    continue
                
                # Se os filtros estiverem ativos na UI, aplica a suavização no dataset para simetria matemática
                if hasattr(self, 'chk_filtrar_curva') and hasattr(self, 'chk_filtrar_IA'):
                    if self.chk_filtrar_curva.isChecked() and self.chk_filtrar_IA.isChecked():
                        curva = self.suavizar_curva(curva, self.spin_janela_curva.value())
                
                peak_idx = np.argmax(curva)
                decay = np.array(curva[peak_idx:])
                n_final = max(5, int(len(decay) * 0.1))
                offset = np.mean(decay[-n_final:])
                decay_adj = np.clip(decay - offset, 1e-5, None)
                
                auc = np.sum(decay_adj) * row_dt
                n_fit = int(len(decay_adj) * 0.3)
                if n_fit < 3: n_fit = 3
                y_log = np.log(decay_adj[:n_fit])
                t_fit = np.arange(n_fit) * row_dt
                
                try:
                    B, A = np.polyfit(t_fit, y_log, 1)
                    tau = -1.0 / B if B != 0 else 0.0
                except Exception:
                    tau = 0.0
                
                if tau > 0:
                    pontos.append((material, classe, tau, auc))
                    
            if len(pontos) < 3:
                return
                
            # Agrupa pontos por material e classe para remoção de outliers usando IQR
            grupos = {}
            for mat, cls, tau, auc in pontos:
                key = (mat, cls)
                if key not in grupos:
                    grupos[key] = []
                grupos[key].append((tau, auc))
                
            pontos_filtrados = []
            for key, grupo in grupos.items():
                if len(grupo) < 4:
                    # Sem amostras suficientes para IQR confiável, mantém todas
                    for tau, auc in grupo:
                        pontos_filtrados.append((key[0], key[1], tau, auc))
                    continue
                    
                taus_grupo = [g[0] for g in grupo]
                aucs_grupo = [g[1] for g in grupo]
                
                # IQR para Tau
                q1_tau, q3_tau = np.percentile(taus_grupo, [25, 75])
                iqr_tau = q3_tau - q1_tau
                lim_inf_tau = q1_tau - 1.5 * iqr_tau
                lim_sup_tau = q3_tau + 1.5 * iqr_tau
                
                # IQR para AUC
                q1_auc, q3_auc = np.percentile(aucs_grupo, [25, 75])
                iqr_auc = q3_auc - q1_auc
                lim_inf_auc = q1_auc - 1.5 * iqr_auc
                lim_sup_auc = q3_auc + 1.5 * iqr_auc
                
                for tau, auc in grupo:
                    if (lim_inf_tau <= tau <= lim_sup_tau) and (lim_inf_auc <= auc <= lim_sup_auc):
                        pontos_filtrados.append((key[0], key[1], tau, auc))
                        
            if len(pontos_filtrados) < 3:
                # Fallback caso a filtragem remova pontos excessivos
                pontos_filtrados = pontos
                
            taus_limpos = [p[2] for p in pontos_filtrados]
            aucs_limpos = [p[3] for p in pontos_filtrados]
            
            self.tau_min = np.min(taus_limpos)
            self.tau_max = np.max(taus_limpos)
            self.auc_min = np.min(aucs_limpos)
            self.auc_max = np.max(aucs_limpos)
            
            self.tau_range = (self.tau_max - self.tau_min) if (self.tau_max - self.tau_min) > 0 else 1.0
            self.auc_range = (self.auc_max - self.auc_min) if (self.auc_max - self.auc_min) > 0 else 1.0
            
            # Recalcula centroides com os pontos limpos
            grupos_limpos = {}
            for mat, cls, tau, auc in pontos_filtrados:
                key = (mat, cls)
                if key not in grupos_limpos:
                    grupos_limpos[key] = []
                grupos_limpos[key].append((tau, auc))
                
            for key, vals in grupos_limpos.items():
                mean_tau = np.mean([v[0] for v in vals])
                mean_auc = np.mean([v[1] for v in vals])
                self.centroids[key] = (mean_tau, mean_auc)
                
            print(f"[CLASSIFICADOR] Treinado com {len(self.centroids)} classes a partir do CSV.")
        except Exception as e:
            print(f"[CLASSIFICADOR] Erro ao treinar: {e}")

    def classificar_leitura(self, tau, auc):
        if not hasattr(self, 'centroids') or not self.centroids:
            return "Sem Dados", "Sem Dados", 0.0
        
        melhor_mat = "Desconhecido"
        melhor_cls = "Desconhecido"
        menor_dist = float('inf')
        
        tau_norm = (tau - self.tau_min) / self.tau_range
        auc_norm = (auc - self.auc_min) / self.auc_range
        
        for (mat, cls), (c_tau, c_auc) in self.centroids.items():
            c_tau_norm = (c_tau - self.tau_min) / self.tau_range
            c_auc_norm = (c_auc - self.auc_min) / self.auc_range
            
            dist = np.sqrt((tau_norm - c_tau_norm)**2 + (auc_norm - c_auc_norm)**2)
            if dist < menor_dist:
                menor_dist = dist
                melhor_mat = mat
                melhor_cls = cls
                
        # Distância máxima no quadrado unitário é sqrt(2) ≈ 1.414.
        confianca = max(0.0, 100.0 * (1.0 - menor_dist / 1.414))
        return melhor_mat, melhor_cls, confianca

    # =====================================================================
    # PROCESSAMENTO MATEMÁTICO DOS DADOS
    # =====================================================================
    def obter_unidade_tempo(self, dt=None):
        # Determina o multiplicador e o sufixo de unidade com base no dt
        dt_val = dt if dt is not None else self.dt_us
        if dt_val < 0.001:  # Menor que 1 ns por amostra (0.001 us)
            return 1000000.0, "ps"
        elif dt_val < 1.0:  # Menor que 1 us por amostra (1.0 us)
            return 1000.0, "ns"
        else:
            return 1.0, "\u03bcs"

    def formatar_valor_tempo(self, valor_us):
        if valor_us is None:
            return "--- \u03bcs"
        abs_val = abs(valor_us)
        if abs_val == 0:
            return "0.00 \u03bcs"
        
        fator, unidade = self.obter_unidade_tempo(abs_val)
        casas = 1 if unidade == "ps" else 2
        return f"{valor_us * fator:.{casas}f} {unidade}"

    def processar_nova_curva(self, valores):
        # Se a suavização de transiente estiver ativa, aplica média móvel ponto a ponto na curva
        if self.chk_filtrar_curva.isChecked():
            valores_processados = self.suavizar_curva(valores, self.spin_janela_curva.value())
        else:
            valores_processados = valores

        self.last_valores = valores_processados
        self.recent_curves.append(valores_processados)
        
        # 1. Localiza o pico da curva para alinhar o transiente
        peak_idx = np.argmax(valores_processados)
        decay = np.array(valores_processados[peak_idx:])
        
        # 2. Estimar offset (últimos 10% da curva de decaimento)
        n_final = max(5, int(len(decay) * 0.1))
        offset = np.mean(decay[-n_final:])
        
        # 3. Calcula a Área sob a curva (AUC) com offset subtraído
        decay_adj = np.clip(decay - offset, 0, None)
        auc = np.sum(decay_adj) * self.dt_us
        
        # Ajusta dinamicamente a escala Y de forma estável com histerese (evita piscadas por ruído)
        max_val = max(valores_processados) if len(valores_processados) > 0 else 0
        if max_val > 0:
            # Sinal bruto
            target_limit_bruto = max_val * 1.15 + 5
            if self.current_y_limit_bruto is None:
                self.current_y_limit_bruto = target_limit_bruto
                self.plot_bruto.setYRange(0, self.current_y_limit_bruto)
            else:
                # Só atualiza a escala se houver mudança maior que 15% (evita trepidação visual)
                diff = abs(target_limit_bruto - self.current_y_limit_bruto) / self.current_y_limit_bruto
                if diff > 0.15:
                    self.current_y_limit_bruto = target_limit_bruto
                    self.plot_bruto.setYRange(0, self.current_y_limit_bruto)
            
            # Decaimento transiente (delta counts)
            max_decay = max(decay_adj) if len(decay_adj) > 0 else 0
            target_limit_decay = max_decay * 1.15 + 5
            if self.current_y_limit_decay is None:
                self.current_y_limit_decay = target_limit_decay
                self.plot_decay.setYRange(0, self.current_y_limit_decay)
            else:
                # Só atualiza se houver mudança maior que 15% (evita trepidação visual)
                diff_dec = abs(target_limit_decay - self.current_y_limit_decay) / self.current_y_limit_decay
                if diff_dec > 0.15:
                    self.current_y_limit_decay = target_limit_decay
                    self.plot_decay.setYRange(0, self.current_y_limit_decay)
        else:
            self.plot_bruto.setYRange(0, 270)
            self.plot_decay.setYRange(0, 270)
        
        # 4. Ajuste linear logarítmico para cálculo do tempo de decaimento (Tau)
        decay_log = np.clip(decay - offset, 1e-5, None)
        n_fit = int(len(decay_log) * 0.3) # primeiros 30% do decaimento
        y_log = np.log(decay_log[:n_fit])
        t_fit = np.arange(n_fit) * self.dt_us
        
        try:
            B, A = np.polyfit(t_fit, y_log, 1)
            tau = -1.0 / B if B != 0 else 0.0
        except Exception:
            tau = 0.0
            
        self.last_tau = tau
        self.last_auc = auc

        # 4.5. Classificação Inteligente em tempo real
        # Usa a média móvel configurável se estiver em modo contínuo e habilitado
        if self.chk_auto_trigger.isChecked() and self.chk_ia_usa_media_movel.isChecked() and len(self.trend_tau) >= 3:
            janela_val = min(len(self.trend_tau), self.spin_janela_ia.value())
            tau_para_classif = np.mean(list(self.trend_tau)[-janela_val:])
            auc_para_classif = np.mean(list(self.trend_auc)[-janela_val:])
        else:
            tau_para_classif = tau
            auc_para_classif = auc

        material_detectado, classe_detectada, confianca = self.classificar_leitura(tau_para_classif, auc_para_classif)
        self.lbl_cls_material_val.setText(material_detectado)
        self.lbl_cls_degrad_val.setText(classe_detectada)
        self.lbl_cls_conf_val.setText(f"{confianca:.1f}%")
        
        # Lógica de validação da IA (Aba 3)
        if hasattr(self, 'is_running_validation_test') and self.is_running_validation_test:
            self.processar_leitura_validacao(tau_para_classif, auc_para_classif, material_detectado, classe_detectada, confianca, valores_processados)
        
        # Define a cor do estado dependendo da classe detectada
        cor_classe = "#2ecc71" # Verde para saudável
        if classe_detectada == "Leve":
            cor_classe = "#27ae60"
        elif classe_detectada == "Moderada":
            cor_classe = "#f1c40f"
        elif classe_detectada == "Avançada":
            cor_classe = "#e67e22"
        elif classe_detectada == "Corroído":
            cor_classe = "#e74c3c"
        elif classe_detectada == "Ar Livre":
            cor_classe = "#9b59b6" # Roxo
        elif classe_detectada == "Sem Dados":
            cor_classe = "#7f8c8d"
            
        self.lbl_cls_degrad_val.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {cor_classe};")

        # 5. Atualiza os Displays de Texto e Valores na tela (Instantâneos)
        self.lbl_tau_val.setText(self.formatar_valor_tempo(tau))
        self.lbl_auc_val.setText(f"{auc:.1f}")

        # Se não estiver no modo contínuo, zera a exibição da média móvel
        if not self.chk_auto_trigger.isChecked():
            self.lbl_tau_ma_val.setText(self.formatar_valor_tempo(None))
            self.lbl_auc_ma_val.setText("---")

        # Lógica de coleta automatizada de 10 medições sequenciais
        if hasattr(self, 'is_collecting_sequential') and self.is_collecting_sequential:
            id_amostra = self.edit_id_amostra.text().strip()
            material, classe = self.obter_material_e_classe_selecionados()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if self.chk_salvar_media_movel.isChecked() and len(self.recent_curves) > 0:
                curva_para_salvar = np.mean(list(self.recent_curves), axis=0).round().astype(int).tolist()
            else:
                curva_para_salvar = valores_processados
                
            sucesso = self.registrar_linha_csv(id_amostra, material, classe, curva_para_salvar, timestamp, silent=True)
            if not sucesso:
                self.finalizar_coleta_sequencial(abortado=True)
                return
                
            self.sequential_collect_counter -= 1
            
            if self.sequential_collect_counter > 0:
                total = self.sequential_collect_total
                atual = total - self.sequential_collect_counter + 1
                self.active_save_btn.setText(f"({atual}/{total})")
                # Intervalo de 150 ms para estabilização física do hardware e comunicação serial
                QtCore.QTimer.singleShot(150, self.serial_thread.disparar_leitura)
            else:
                self.finalizar_coleta_sequencial(abortado=False)

        # 6. Atualiza os gráficos da Aba 1 (tempo real)
        self.curve_bruto.setData(valores_processados)
        self.line_peak.setValue(peak_idx)
        self.line_offset.setValue(offset)

        # Plot do decaimento com escala dinâmica de tempo
        fator_t, unid_t = self.obter_unidade_tempo()
        tempo_dec = np.arange(len(decay_adj)) * self.dt_us * fator_t
        self.curve_decay.setData(tempo_dec, decay_adj)
        self.plot_decay.setXRange(0, tempo_dec[-1])
        
        # Atualiza a legenda do eixo inferior com a unidade escalada correspondente
        khz = 1000.0 / self.dt_us if self.dt_us > 0 else 0.0
        modo_nome = "ETS" if not self.chk_auto_trigger.isChecked() else "DMA"
        self.plot_decay.setLabel('bottom', f'Tempo (Modo {modo_nome} - {khz:.2f} kHz)', unid_t)
        
        # 6.5. Atualiza os gráficos da Aba 4 (Diagnóstico em Tempo Real) se estiver ativa
        if self.tab_widget.currentIndex() == 3:
            self.lbl_diag_material.setText(f"Material: {material_detectado}")
            self.lbl_diag_classe.setText(f"Classe: {classe_detectada}")
            self.lbl_diag_confianca.setText(f"Confiança: {confianca:.1f}%")
            self.lbl_diag_tau.setText(f"Tau: {self.formatar_valor_tempo(tau)}")
            self.lbl_diag_auc.setText(f"AUC: {auc:.1f}")
            
            # Calcular R² para exibir nas métricas físicas
            try:
                y_pred = B * t_fit + A
                y_mean = np.mean(y_log)
                ss_tot = np.sum((y_log - y_mean) ** 2)
                ss_res = np.sum((y_log - y_pred) ** 2)
                r2_val = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            except Exception:
                r2_val = 0.0
            self.lbl_diag_r2.setText(f"R\u00b2: {r2_val:.4f}")
            
            # Define cores dos textos com base na classe
            cor_classe = "#2ecc71"
            if classe_detectada == "Leve": cor_classe = "#27ae60"
            elif classe_detectada == "Moderada": cor_classe = "#f1c40f"
            elif classe_detectada == "Avan\u00e7ada": cor_classe = "#e67e22"
            elif classe_detectada == "Corro\u00eddo": cor_classe = "#e74c3c"
            elif classe_detectada == "Ar Livre": cor_classe = "#9b59b6"
            elif classe_detectada == "Sem Dados": cor_classe = "#7f8c8d"
            self.lbl_diag_classe.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {cor_classe};")
            
            # Atualiza Curva Ativa Verde Neon
            if self.diag_active_curve is None:
                self.diag_active_curve = self.plot_diag_curves.plot(
                    tempo_dec, decay_adj, 
                    pen=pg.mkPen("#00ff00", width=3.5), 
                    name="Sinal Ativo"
                )
            else:
                self.diag_active_curve.setData(tempo_dec, decay_adj)
                
            # Atualiza Ponto Ativo no Scatter Plot (Estrela Amarela Grande com borda branca)
            tau_escalado = tau * fator_t
            if self.diag_active_scatter is None:
                self.diag_active_scatter = self.plot_diag_scatter.plot(
                    [tau_escalado], [auc], pen=None, symbol="star", symbolSize=16,
                    symbolBrush=pg.mkBrush("#f1c40f"), symbolPen=pg.mkPen("w", width=1.5)
                )
            else:
                self.diag_active_scatter.setData([tau_escalado], [auc])
                
            # Atualiza linhas indicadoras nas distribuições
            CLASSES_ORDEM = ["Saudável", "Leve", "Moderada", "Avançada", "Corroído", "Ar Livre"]
            pos_x = None
            x_val = 1.0
            for c in CLASSES_ORDEM:
                # Conta se há amostras no banco de dados para esta classe
                n_amostras = sum(1 for a in self.amostras_estatisticas if a["classe"] == c) if hasattr(self, 'amostras_estatisticas') else 0
                if n_amostras > 0:
                    if c.lower() == classe_detectada.lower():
                        pos_x = x_val
                        break
                    x_val += 1.0
            
            if pos_x is not None:
                if self.diag_active_auc_line is None:
                    self.diag_active_auc_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#f1c40f", width=1.5, style=QtCore.Qt.DashLine))
                    self.plot_diag_auc.addItem(self.diag_active_auc_line)
                self.diag_active_auc_line.setValue(auc)
                
                if self.diag_active_tau_line is None:
                    self.diag_active_tau_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#f1c40f", width=1.5, style=QtCore.Qt.DashLine))
                    self.plot_diag_tau.addItem(self.diag_active_tau_line)
                self.diag_active_tau_line.setValue(tau_escalado)
        
        # 7. Se estiver no modo contínuo, adiciona os dados nas deques de tendência
        if self.chk_auto_trigger.isChecked():
            self.trend_counter += 1
            self.trend_indices.append(self.trend_counter)
            self.trend_tau.append(tau)
            self.trend_auc.append(auc)
            
            # Calcula as médias móveis (janela de 10 amostras)
            ma_window = 10
            
            def calcular_ma(deque_vals):
                vals = list(deque_vals)
                ma = []
                for i in range(len(vals)):
                    start = max(0, i - ma_window + 1)
                    ma.append(np.mean(vals[start:i+1]))
                return ma

            ma_tau = calcular_ma(self.trend_tau)
            ma_auc = calcular_ma(self.trend_auc)
            
            # Atualiza os dados das tendências escalando o tempo dinamicamente
            fator_t, unid_t = self.obter_unidade_tempo()
            trend_tau_escalado = [v * fator_t for v in self.trend_tau]
            ma_tau_escalado = [v * fator_t for v in ma_tau]

            self.curve_trend_tau.setData(list(self.trend_indices), trend_tau_escalado)
            self.curve_trend_auc.setData(list(self.trend_indices), list(self.trend_auc))
            self.curve_trend_tau_ma.setData(list(self.trend_indices), ma_tau_escalado)
            self.curve_trend_auc_ma.setData(list(self.trend_indices), ma_auc)
            
            # Atualiza o rótulo do eixo Y esquerdo do gráfico de tendências
            self.plot_trend.setLabel('left', f'Tau ({unid_t})', color='#2ecc71')
            
            # Atualiza a exibição textual das Médias Móveis na tela
            if len(ma_tau) > 0:
                self.lbl_tau_ma_val.setText(self.formatar_valor_tempo(ma_tau[-1]))
            if len(ma_auc) > 0:
                self.lbl_auc_ma_val.setText(f"{ma_auc[-1]:.1f}")
            
            # Auto escala o eixo Y do gráfico de tendências de AUC na ViewBox secundária
            if len(self.trend_auc) > 0:
                min_auc, max_auc = min(self.trend_auc), max(self.trend_auc)
                padding = max(10, (max_auc - min_auc) * 0.1)
                self.trend_auc_axis.setYRange(min_auc - padding, max_auc + padding)

    # =====================================================================
    # SALVAR MEDIÇÃO NO ARQUIVO CSV
    # =====================================================================
    def registrar_linha_csv(self, id_amostra, material, classe, valores, timestamp, silent=False):
        linha_dados = [id_amostra, material, classe, timestamp, self.dt_us] + valores
        try:
            escrever_cabecalho = not os.path.exists(self.arquivo_csv)
            with open(self.arquivo_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                if escrever_cabecalho:
                    cabecalho = ["id_amostra", "material", "classe", "timestamp", "dt_us"] + [f"p_{i}" for i in range(256)]
                    writer.writerow(cabecalho)
                writer.writerow(linha_dados)
                
            if not silent:
                print(f"[SALVO] ID: {id_amostra} | Material: {material} | Classe: {classe} | Tau: {self.last_tau:.2f} | AUC: {self.last_auc:.1f}")
            
            # Adiciona ao histórico textual
            registro = {
                "id": id_amostra,
                "material": material,
                "classe": classe,
                "tau": self.last_tau,
                "auc": self.last_auc,
                "timestamp": timestamp
            }
            self.pontos_salvos.append(registro)
            self.atualizar_historico_texto()
            return True
        except PermissionError:
            if not silent:
                QtWidgets.QMessageBox.critical(
                    self, 
                    "Arquivo Bloqueado", 
                    f"Erro de permissão ao salvar no arquivo '{self.arquivo_csv}'!\n\nCertifique-se de que o arquivo não está aberto no Excel ou em outro visualizador."
                )
            return False

    def obter_material_e_classe_selecionados(self):
        # Material
        material = "A36 Comum"
        for mat_nome, rad in self.radio_buttons_material.items():
            if rad.isChecked():
                material = mat_nome
                break

        # Classe
        if self.rad_cls_saudavel.isChecked():
            classe = "Saudável"
        elif self.rad_cls_leve.isChecked():
            classe = "Leve"
        elif self.rad_cls_moderada.isChecked():
            classe = "Moderada"
        elif self.rad_cls_avancada.isChecked():
            classe = "Avançada"
        elif self.rad_cls_corroido.isChecked():
            classe = "Corroído"
        else:
            classe = "Ar Livre"
            
        return material, classe

    def ao_toggle_ar_livre_material(self, checked):
        if checked:
            self.rad_cls_ar.setChecked(True)
        else:
            if self.rad_cls_ar.isChecked():
                self.rad_cls_saudavel.setChecked(True)
                
    def ao_toggle_ar_livre_classe(self, checked):
        if checked:
            if "Ar Livre" in self.radio_buttons_material:
                self.radio_buttons_material["Ar Livre"].setChecked(True)
        else:
            if "Ar Livre" in self.radio_buttons_material and self.radio_buttons_material["Ar Livre"].isChecked():
                self.radio_buttons_material["A36 Comum"].setChecked(True)

    def salvar_dados_em_csv(self):
        if self.last_valores is None:
            QtWidgets.QMessageBox.warning(self, "Sem dados", "Colete uma curva válida antes de salvar!")
            return
            
        id_amostra = self.edit_id_amostra.text().strip()
        material, classe = self.obter_material_e_classe_selecionados()
        
        if not id_amostra:
            QtWidgets.QMessageBox.warning(self, "ID Vazio", "Por favor, digite o número/ID da amostra!")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if self.chk_salvar_media_movel.isChecked() and len(self.recent_curves) > 0:
            curva_para_salvar = np.mean(list(self.recent_curves), axis=0).round().astype(int).tolist()
        else:
            curva_para_salvar = self.last_valores
            
        if self.registrar_linha_csv(id_amostra, material, classe, curva_para_salvar, timestamp):
            QtWidgets.QMessageBox.information(self, "Salvo", f"Amostra {id_amostra} salva com sucesso!")
            self.treinar_classificador() # Re-treina com a amostra nova!
            
            # Incrementa o ID da amostra automaticamente para a próxima leitura
            try:
                proximo_id = int(id_amostra) + 1
                self.edit_id_amostra.setText(str(proximo_id))
            except ValueError:
                pass

    def iniciar_coleta_sequencial(self, n_amostras=10):
        if not self.serial_thread.running:
            QtWidgets.QMessageBox.warning(self, "Sem conexão", "Conecte na porta serial antes de iniciar a coleta!")
            return
            
        id_amostra = self.edit_id_amostra.text().strip()
        if not id_amostra:
            QtWidgets.QMessageBox.warning(self, "ID Vazio", "Por favor, digite o número/ID da amostra!")
            return
            
        # Inicia a sequência de disparos automáticos
        self.is_collecting_sequential = True
        self.sequential_collect_total = n_amostras
        self.sequential_collect_counter = n_amostras
        
        # Determina qual botão foi clicado para exibir o progresso e a cor
        if n_amostras == 10:
            self.active_save_btn = self.btn_salvar_10
            self.active_save_btn_color = "#9b59b6"
        elif n_amostras == 100:
            self.active_save_btn = self.btn_salvar_100
            self.active_save_btn_color = "#8e44ad"
        else:
            self.active_save_btn = self.btn_salvar_1000
            self.active_save_btn_color = "#6c3483"
            
        # Bloqueia botões de controle para evitar conflitos
        self.btn_salvar_registro.setEnabled(False)
        self.btn_salvar_10.setEnabled(False)
        self.btn_salvar_100.setEnabled(False)
        self.btn_salvar_1000.setEnabled(False)
        self.btn_single_trigger.setEnabled(False)
        self.chk_auto_trigger.setEnabled(False)
        
        # Mantém apenas o botão ativo habilitado visualmente para progresso
        self.active_save_btn.setEnabled(True)
        self.active_save_btn.setText(f"(1/{n_amostras})")
        self.active_save_btn.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")
        
        # Dispara o primeiro
        self.serial_thread.disparar_leitura()

    def finalizar_coleta_sequencial(self, abortado=False):
        self.is_collecting_sequential = False
        self.sequential_collect_counter = 0
        
        # Libera os botões de controle
        self.btn_salvar_registro.setEnabled(True)
        self.btn_salvar_10.setEnabled(True)
        self.btn_salvar_100.setEnabled(True)
        self.btn_salvar_1000.setEnabled(True)
        self.btn_single_trigger.setEnabled(True)
        self.chk_auto_trigger.setEnabled(True)
        
        # Restaura os textos e estilos originais
        self.btn_salvar_10.setText("Gravar 10")
        self.btn_salvar_10.setStyleSheet("background-color: #9b59b6; color: white; font-weight: bold; font-size: 10pt;")
        
        self.btn_salvar_100.setText("Gravar 100")
        self.btn_salvar_100.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold; font-size: 10pt;")
        
        self.btn_salvar_1000.setText("Gravar 1000")
        self.btn_salvar_1000.setStyleSheet("background-color: #6c3483; color: white; font-weight: bold; font-size: 10pt;")
        
        if abortado:
            QtWidgets.QMessageBox.critical(self, "Falha", "Coleta sequencial abortada devido a erro de escrita! Verifique se o CSV não está aberto no Excel.")
        else:
            id_amostra = self.edit_id_amostra.text().strip()
            # Incrementa o ID da amostra após o término das leituras
            try:
                proximo_id = int(id_amostra) + 1
                self.edit_id_amostra.setText(str(proximo_id))
            except ValueError:
                pass
            self.treinar_classificador() # Re-treina com o lote novo!
            QtWidgets.QMessageBox.information(self, "Sucesso", f"Coleta automatizada de {self.sequential_collect_total} medições concluída e salva!")

    def atualizar_historico_texto(self):
        linhas = []
        for i, r in enumerate(self.pontos_salvos, start=1):
            linhas.append(
                f"{i:02d} | ID: {r['id']:<3} | Mat: {r['material']:<9} | Classe: {r['classe']:<9} | "
                f"Tau: {r['tau']:.2f} \u03bcs | AUC: {r['auc']:.1f}"
            )
        self.list_historico.setPlainText("\n".join(linhas))

    def limpar_historico_visual(self):
        self.pontos_salvos.clear()
        self.list_historico.clear()

    def excluir_csv_local(self):
        if not os.path.exists(self.arquivo_csv):
            QtWidgets.QMessageBox.warning(self, "Aviso", "Nenhum arquivo CSV encontrado para gerenciar.")
            return
            
        dialog = ExclusaoSeletivaDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            mat_selecionado = dialog.combo_material.currentText()
            cls_selecionada = dialog.combo_classe.currentText()
            
            confirmacao = QtWidgets.QMessageBox.question(
                self,
                "Confirmar Exclusão",
                f"Tem certeza de que deseja excluir do arquivo:\n"
                f"➔ {os.path.basename(self.arquivo_csv)}\n\n"
                f"As amostras correspondentes a:\n"
                f"• Material: {mat_selecionado}\n"
                f"• Classe: {cls_selecionada}?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            
            if confirmacao != QtWidgets.QMessageBox.Yes:
                return
                
            linhas_preservadas = []
            linhas_excluidas_count = 0
            
            conteudo_csv = None
            try:
                with open(self.arquivo_csv, "r", newline="", encoding="utf-8") as f:
                    conteudo_csv = f.read()
            except UnicodeDecodeError:
                try:
                    with open(self.arquivo_csv, "r", newline="", encoding="latin-1") as f:
                        conteudo_csv = f.read()
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Erro", f"Erro ao ler arquivo: {e}")
                    return
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Erro", f"Erro ao ler arquivo: {e}")
                return
                
            import io
            f_string = io.StringIO(conteudo_csv)
            reader = csv.reader(f_string, delimiter=";")
            try:
                headers = next(reader)
                linhas_preservadas.append(headers)
                
                material_idx = headers.index("material") if "material" in headers else 1
                classe_idx = headers.index("classe") if "classe" in headers else 2
                
                for row in reader:
                    if not row:
                        continue
                    row_mat = row[material_idx].strip()
                    row_cls = row[classe_idx].strip()
                    
                    match_mat = (mat_selecionado == "[Todos os Materiais]" or row_mat.lower() == mat_selecionado.lower())
                    
                    # Trata classes de forma tolerante a acentos e maiúsculas
                    import unicodedata
                    def normalizar_str(s):
                        return "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()
                        
                    norm_cls_row = normalizar_str(row_cls)
                    norm_cls_sel = normalizar_str(cls_selecionada)
                    match_cls = (cls_selecionada == "[Todas as Classes]" or norm_cls_row == norm_cls_sel)
                    
                    if match_mat and match_cls:
                        linhas_excluidas_count += 1
                    else:
                        linhas_preservadas.append(row)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Erro", f"Erro ao processar conteúdo CSV: {e}")
                return
                
            # Se restou apenas o cabeçalho, remove o arquivo
            if len(linhas_preservadas) <= 1:
                try:
                    if os.path.exists(self.arquivo_csv):
                        os.remove(self.arquivo_csv)
                    self.pontos_salvos.clear()
                    self.list_historico.clear()
                    self.centroids = {}
                    self.lbl_cls_material_val.setText("Desconhecido")
                    self.lbl_cls_degrad_val.setText("Sem Dados")
                    self.lbl_cls_conf_val.setText("0.0%")
                    QtWidgets.QMessageBox.information(self, "Sucesso", "Todas as amostras foram removidas e o arquivo CSV foi excluído!")
                except PermissionError:
                    QtWidgets.QMessageBox.critical(self, "Erro", "Não foi possível gravar as alterações. O arquivo está aberto no Excel!")
            else:
                try:
                    with open(self.arquivo_csv, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=";")
                        writer.writerows(linhas_preservadas)
                        
                    self.pontos_salvos.clear()
                    self.list_historico.clear()
                    self.treinar_classificador()
                    QtWidgets.QMessageBox.information(
                        self, 
                        "Sucesso", 
                        f"Filtro aplicado com sucesso!\n\n"
                        f"• Amostras excluídas: {linhas_excluidas_count}\n"
                        f"• Amostras restantes no CSV: {len(linhas_preservadas) - 1}"
                    )
                except PermissionError:
                    QtWidgets.QMessageBox.critical(self, "Erro", "Não foi possível gravar as alterações. O arquivo está aberto no Excel!")

    def closeEvent(self, event):
        # Desconecta a serial antes de fechar a janela principal
        self.chk_auto_trigger.setChecked(False)
        self.serial_thread.desconectar()
        event.accept()

    def filtrar_outliers_iqr(self, amostras):
        grupos = {}
        for a in amostras:
            key = (a['material'], a['classe'])
            if key not in grupos:
                grupos[key] = []
            grupos[key].append(a)
            
        amostras_filtradas = []
        
        for key, grupo in grupos.items():
            if len(grupo) < 4:
                # Sem amostras suficientes para IQR confiável, mantém todas
                amostras_filtradas.extend(grupo)
                continue
                
            taus = [a['tau'] for a in grupo]
            aucs = [a['auc'] for a in grupo]
            
            # IQR para Tau
            q1_tau, q3_tau = np.percentile(taus, [25, 75])
            iqr_tau = q3_tau - q1_tau
            lim_inf_tau = q1_tau - 1.5 * iqr_tau
            lim_sup_tau = q3_tau + 1.5 * iqr_tau
            
            # IQR para AUC
            q1_auc, q3_auc = np.percentile(aucs, [25, 75])
            iqr_auc = q3_auc - q1_auc
            lim_inf_auc = q1_auc - 1.5 * iqr_auc
            lim_sup_auc = q3_auc + 1.5 * iqr_auc
            
            # Filtra
            for a in grupo:
                is_ok_tau = (lim_inf_tau <= a['tau'] <= lim_sup_tau)
                is_ok_auc = (lim_inf_auc <= a['auc'] <= lim_sup_auc)
                if is_ok_tau and is_ok_auc:
                    amostras_filtradas.append(a)
                    
        return amostras_filtradas

    def rodar_analise_estatistica(self):
        if not os.path.exists(self.arquivo_csv):
            QtWidgets.QMessageBox.warning(
                self, 
                "Dataset não encontrado", 
                f"O arquivo '{self.arquivo_csv}' não existe. Faça algumas medições na aba de aquisição primeiro!"
            )
            return

        # Tenta carregar o arquivo com UTF-8 e faz fallback para Latin-1 se falhar
        conteudo_csv = None
        try:
            with open(self.arquivo_csv, "r", newline="", encoding="utf-8") as f:
                conteudo_csv = f.read()
        except UnicodeDecodeError:
            try:
                with open(self.arquivo_csv, "r", newline="", encoding="latin-1") as f:
                    conteudo_csv = f.read()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Erro de Leitura", f"Erro ao ler arquivo CSV:\n{str(e)}")
                return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Leitura", f"Erro ao ler arquivo CSV:\n{str(e)}")
            return

        import io
        try:
            f_string = io.StringIO(conteudo_csv)
            reader = csv.reader(f_string, delimiter=";")
            headers = next(reader)
            
            # Identifica as colunas de interesse de forma robusta e dinâmica pelo cabeçalho
            id_idx = headers.index("id_amostra") if "id_amostra" in headers else 0
            material_idx = headers.index("material") if "material" in headers else 1
            classe_idx = headers.index("classe") if "classe" in headers else 2
            dt_idx = headers.index("dt_us") if "dt_us" in headers else -1
            p_start_idx = headers.index("p_0") if "p_0" in headers else 4
            
            self.amostras_estatisticas = [] # Limpa a lista anterior
            
            for row in reader:
                if not row or len(row) < 260:
                    continue
                
                id_amostra = row[id_idx].strip()
                material = row[material_idx].strip() if len(row) > material_idx else "A36 Comum"
                classe = normalizar_nome_classe(row[classe_idx])
                
                # Suporta arquivos mistos (com ou sem a coluna de dt_us)
                # Formato antigo tem 260 colunas, formato novo (com dt_us) tem 261 colunas
                if len(row) >= 261:
                    try:
                        row_dt = float(row[4].strip()) if row[4].strip() else self.dt_us
                    except ValueError:
                        row_dt = self.dt_us
                    p_start = 5
                else:
                    row_dt = self.dt_us
                    p_start = 4
                
                try:
                    curva = [int(val) for val in row[p_start:p_start+256]]
                except ValueError:
                    continue
                
                # Processamento matemático idêntico ao de aquisição em tempo real
                peak_idx = np.argmax(curva)
                decay = np.array(curva[peak_idx:])
                
                # Offset (últimos 10% da curva de decaimento)
                n_final = max(5, int(len(decay) * 0.1))
                offset = np.mean(decay[-n_final:])
                
                # AUC
                decay_adj = np.clip(decay - offset, 0, None)
                auc = np.sum(decay_adj) * row_dt
                
                # Tau
                decay_log = np.clip(decay - offset, 1e-5, None)
                n_fit = int(len(decay_log) * 0.3)
                y_log = np.log(decay_log[:n_fit])
                t_fit = np.arange(n_fit) * row_dt
                try:
                    B, A = np.polyfit(t_fit, y_log, 1)
                    tau = -1.0 / B if B != 0 else 0.0
                except Exception:
                    tau = 0.0

                # Cria a estrutura de amostra para armazenamento em memória
                amostra = {
                    "id": id_amostra,
                    "material": material,
                    "classe": classe,
                    "auc": auc,
                    "tau": tau,
                    "curva": decay_adj
                }
                self.amostras_estatisticas.append(amostra)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro de Leitura", f"Erro ao processar o arquivo CSV:\n{str(e)}")
            return

        # Plota os gráficos inicialmente considerando os filtros ativos
        self.atualizar_graficos_estatisticos()

    def atualizar_graficos_estatisticos(self, *args):
        # 1. Limpa os gráficos e relatórios anteriores
        self.plot_stat_curves.clear()
        self.plot_stat_auc.clear()
        self.plot_stat_tau.clear()
        self.plot_stat_scatter.clear()
        self.txt_report_stats.clear()
        
        self.plot_stat_curves.enableAutoRange(x=True, y=True)
        self.plot_stat_auc.enableAutoRange(x=True, y=True)
        self.plot_stat_tau.enableAutoRange(x=True, y=True)
        self.plot_stat_scatter.enableAutoRange(x=True, y=True)
        
        # Esconde o tooltip flutuante ao re-renderizar para evitar fantasmas
        if hasattr(self, 'tooltip_estatistico'):
            self.tooltip_estatistico.hide()
            
        if not hasattr(self, 'amostras_estatisticas') or not self.amostras_estatisticas:
            return

        # 2. Identifica quais filtros de Materiais e Classes estão ativos
        materiais_ativos = []
        for mat_nome, chk in self.filter_checkboxes_material.items():
            if chk.isChecked():
                materiais_ativos.append(mat_nome)
        
        classes_ativas = []
        if self.chk_filter_saudavel.isChecked(): classes_ativas.append("Saudável")
        if self.chk_filter_leve.isChecked(): classes_ativas.append("Leve")
        if self.chk_filter_moderada.isChecked(): classes_ativas.append("Moderada")
        if self.chk_filter_avancada.isChecked(): classes_ativas.append("Avançada")
        if self.chk_filter_corroido.isChecked(): classes_ativas.append("Corroído")
        if self.chk_filter_ar_cls.isChecked(): classes_ativas.append("Ar Livre")

        # 3. Filtra as amostras na memória
        self.amostras_filtradas = [
            a for a in self.amostras_estatisticas
            if a["material"] in materiais_ativos and a["classe"] in classes_ativas
        ]
        
        # Filtra outliers caso a caixinha esteja marcada
        if self.chk_filter_outliers.isChecked():
            self.amostras_filtradas = self.filtrar_outliers_iqr(self.amostras_filtradas)

        if not self.amostras_filtradas:
            self.txt_report_stats.setPlainText("Sem dados correspondentes aos filtros selecionados.")
            return

        # Classes na ordem correta de degradação e suas cores correspondentes
        CLASSES_ORDEM = ["Saudável", "Leve", "Moderada", "Avançada", "Corroído", "Ar Livre"]
        CORES_CLASSES = {
            "Saudável": "#3498db",  # Azul
            "Leve": "#1abc9c",      # Ciano/Verde Claro
            "Moderada": "#f1c40f",  # Amarelo
            "Avançada": "#e67e22",  # Laranja
            "Corroído": "#e74c3c",  # Vermelho
            "Ar Livre": "#9b59b6"   # Roxo
        }
        CORES_RGB = {
            "Saudável": (52, 152, 219),
            "Leve": (26, 188, 156),
            "Moderada": (241, 196, 15),
            "Avançada": (230, 126, 34),
            "Corroído": (231, 76, 60),
            "Ar Livre": (155, 89, 182)
        }

        # Agrupa os dados filtrados por classe (usado nos outros plots)
        dados_por_classe = {c: {"auc": [], "tau": [], "curvas": []} for c in CLASSES_ORDEM}
        for amostra in self.amostras_filtradas:
            classe = amostra["classe"]
            if classe not in dados_por_classe:
                dados_por_classe[classe] = {"auc": [], "tau": [], "curvas": []}
                CORES_CLASSES[classe] = "#7f8c8d"  # Cinza padrão
                CORES_RGB[classe] = (127, 140, 141)
                
            dados_por_classe[classe]["auc"].append(amostra["auc"])
            dados_por_classe[classe]["tau"].append(amostra["tau"])
            dados_por_classe[classe]["curvas"].append(amostra["curva"])

        # Agrupa os dados filtrados por combinação de material e classe (usado no Plot 1 e Relatório)
        dados_agrupados = {}
        for amostra in self.amostras_filtradas:
            mat = amostra["material"]
            cls = amostra["classe"]
            key = (mat, cls)
            if key not in dados_agrupados:
                dados_agrupados[key] = {"auc": [], "tau": [], "curvas": []}
            dados_agrupados[key]["auc"].append(amostra["auc"])
            dados_agrupados[key]["tau"].append(amostra["tau"])
            dados_agrupados[key]["curvas"].append(amostra["curva"])

        # 4. Gera o relatório estatístico formatado em texto para o console lateral (filtrado)
        report = []
        report.append("<h3>=== Resumo do Dataset (Filtrado) ===</h3>")
        
        # Ordenação das chaves por material, depois pela ordem lógica das classes
        chaves_ordenadas = sorted(
            list(dados_agrupados.keys()),
            key=lambda k: (k[0], CLASSES_ORDEM.index(k[1]) if k[1] in CLASSES_ORDEM else 99)
        )
        
        for mat, cls in chaves_ordenadas:
            n = len(dados_agrupados[(mat, cls)]["auc"])
            if n > 0:
                report.append(f"<b>{mat} - {cls}:</b> {n} amostras")
        report.append("<hr>")
        report.append("<h3>--- Estatísticas Comparativas ---</h3>")
        
        # Determina a unidade de tempo da estatística baseada no dt_us das amostras
        primeira_amostra = self.amostras_filtradas[0] if self.amostras_filtradas else None
        stat_dt = primeira_amostra["dt_us"] if (primeira_amostra and "dt_us" in primeira_amostra) else self.dt_us
        fator_stat, unid_stat = self.obter_unidade_tempo(stat_dt)

        for mat, cls in chaves_ordenadas:
            auc_list = dados_agrupados[(mat, cls)]["auc"]
            tau_list = dados_agrupados[(mat, cls)]["tau"]
            n = len(auc_list)
            if n > 0:
                mean_auc = np.mean(auc_list)
                std_auc = np.std(auc_list)
                mean_tau = np.mean(tau_list) * fator_stat
                std_tau = np.std(tau_list) * fator_stat
                casas = 1 if unid_stat == "ps" else 3
                report.append(f"<b>{mat} ({cls})</b>:")
                report.append(f"  * AUC média: {mean_auc:.1f} (&plusmn;{std_auc:.1f})")
                report.append(f"  * Tau médio: {mean_tau:.{casas}f} (&plusmn;{std_tau:.{casas}f}) {unid_stat}")
                report.append("")
        
        self.txt_report_stats.setHtml("<br>".join(report))

        # 5. Renderiza Plot 1: Curvas Médias de Decaimento com Bandas de DP
        max_len = 150
        def calcular_curva_media_e_std(curvas):
            if not curvas:
                return None, None
            ajustadas = []
            for c in curvas:
                if len(c) >= max_len:
                    ajustadas.append(c[:max_len])
                else:
                    ajustadas.append(np.pad(c, (0, max_len - len(c)), 'constant'))
            ajustadas = np.array(ajustadas)
            return np.mean(ajustadas, axis=0), np.std(ajustadas, axis=0)

        t = np.arange(max_len) * stat_dt * fator_stat
        self.plot_stat_curves.setLabel('bottom', 'Tempo', unid_stat)

        # Estilos de linha diferentes por material para diferenciar no gráfico
        ESTILOS_MATERIAIS = {
            "A36 Comum": QtCore.Qt.SolidLine,
            "A36 GE": QtCore.Qt.DashLine,
            "A36 GF": QtCore.Qt.DotLine,
            "Ar Livre": QtCore.Qt.SolidLine
        }

        # Limpa o LegendItem antes de adicionar os novos itens
        if hasattr(self.plot_stat_curves, 'legend') and self.plot_stat_curves.legend is not None:
            self.plot_stat_curves.legend.clear()

        for mat, cls in chaves_ordenadas:
            curvas = dados_agrupados[(mat, cls)]["curvas"]
            if not curvas:
                continue
            mean, std = calcular_curva_media_e_std(curvas)
            color = CORES_CLASSES.get(cls, "#7f8c8d")
            rgb = CORES_RGB.get(cls, (127, 140, 141))
            estilo = ESTILOS_MATERIAIS.get(mat, QtCore.Qt.SolidLine)
            
            nome_legenda = f"{mat} ({cls})"
            self.plot_stat_curves.plot(
                t, mean, 
                pen=pg.mkPen(color, width=3, style=estilo), 
                name=nome_legenda
            )
            
            # Sombreamento de DP
            y_min = np.clip(mean - std, 0, None)
            y_max = mean + std
            c_min = self.plot_stat_curves.plot(t, y_min, pen=pg.mkPen(None))
            c_max = self.plot_stat_curves.plot(t, y_max, pen=pg.mkPen(None))
            fill = pg.FillBetweenItem(c_min, c_max, brush=pg.mkBrush(rgb[0], rgb[1], rgb[2], 20))
            self.plot_stat_curves.addItem(fill)

        # 6. Renderiza Plots 2 e 3: Distribuições de AUC e Tau (Scatter Jittered + Média ± DP)
        ticks = []
        x_val = 1.0
        posicoes_classes = {}
        for c in list(dados_por_classe.keys()):
            # Verifica se há amostras pertencentes a esta classe nos dados filtrados
            n_amostras = sum(1 for a in self.amostras_filtradas if a["classe"] == c)
            if n_amostras > 0:
                ticks.append((x_val, c.capitalize()))
                posicoes_classes[c] = x_val
                x_val += 1.0
        
        self.plot_stat_auc.getAxis('bottom').setTicks([ticks])
        self.plot_stat_tau.getAxis('bottom').setTicks([ticks])

        SIMBOLOS_MATERIAIS = {
            "A36 Comum": "o",  # Círculo
            "A36 GE": "s",     # Quadrado
            "A36 GF": "d"      # Losango
        }

        for c, x in posicoes_classes.items():
            # Filtra apenas as amostras pertencentes a esta classe
            amostras_classe = [a for a in self.amostras_filtradas if a["classe"] == c]
            if not amostras_classe:
                continue
                
            dados_auc = [a["auc"] for a in amostras_classe]
            dados_tau = [a["tau"] for a in amostras_classe]
            color = CORES_CLASSES.get(c, "#7f8c8d")
            rgb = CORES_RGB.get(c, (127, 140, 141))
            
            # Gera o x_jitter para AUC e salva o valor exato em cada amostra
            x_jitter_auc = np.random.normal(x, 0.04, size=len(dados_auc))
            for idx_a, amostra in enumerate(amostras_classe):
                amostra["pos_x_auc_plot"] = x_jitter_auc[idx_a]
                
            # Plota cada material desta classe com seu símbolo correspondente
            materiais_presentes = list(set([a["material"] for a in amostras_classe]))
            for mat_nome in materiais_presentes:
                simbolo = SIMBOLOS_MATERIAIS.get(mat_nome, "o")
                indices_mat = [i for i, a in enumerate(amostras_classe) if a["material"] == mat_nome]
                if not indices_mat:
                    continue
                x_sub = x_jitter_auc[indices_mat]
                y_sub = np.array(dados_auc)[indices_mat]
                self.plot_stat_auc.plot(x_sub, y_sub, pen=None, symbol=simbolo, symbolSize=8, 
                                        symbolBrush=pg.mkBrush(rgb[0], rgb[1], rgb[2], 180), symbolPen=pg.mkPen('w', width=0.5))
            
            m_a, s_a = np.mean(dados_auc), np.std(dados_auc)
            self.plot_stat_auc.plot([x, x], [m_a - s_a, m_a + s_a], pen=pg.mkPen(color, width=3))
            self.plot_stat_auc.plot([x - 0.1, x + 0.1], [m_a, m_a], pen=pg.mkPen('w', width=3))
            
            # Gera o x_jitter para Tau e salva o valor exato em cada amostra
            x_jitter_tau = np.random.normal(x, 0.04, size=len(dados_tau))
            for idx_a, amostra in enumerate(amostras_classe):
                amostra["pos_x_tau_plot"] = x_jitter_tau[idx_a]
                
            # Plota cada material desta classe com seu símbolo correspondente
            materiais_presentes = list(set([a["material"] for a in amostras_classe]))
            for mat_nome in materiais_presentes:
                simbolo = SIMBOLOS_MATERIAIS.get(mat_nome, "o")
                indices_mat = [i for i, a in enumerate(amostras_classe) if a["material"] == mat_nome]
                if not indices_mat:
                    continue
                x_sub = x_jitter_tau[indices_mat]
                y_sub = np.array(dados_tau)[indices_mat]
                self.plot_stat_tau.plot(x_sub, y_sub, pen=None, symbol=simbolo, symbolSize=8, 
                                        symbolBrush=pg.mkBrush(rgb[0], rgb[1], rgb[2], 180), symbolPen=pg.mkPen('w', width=0.5))
            
            m_t, s_t = np.mean(dados_tau), np.std(dados_tau)
            self.plot_stat_tau.plot([x, x], [m_t - s_t, m_t + s_t], pen=pg.mkPen(color, width=3))
            self.plot_stat_tau.plot([x - 0.1, x + 0.1], [m_t, m_t], pen=pg.mkPen('w', width=3))
            
        if posicoes_classes:
            self.plot_stat_auc.setXRange(0.5, max(1.5, x_val - 0.5))
            self.plot_stat_tau.setXRange(0.5, max(1.5, x_val - 0.5))

        # 7. Renderiza Plot 4: Espaço de Características (AUC vs Tau)
        for c in list(dados_por_classe.keys()):
            amostras_classe = [a for a in self.amostras_filtradas if a["classe"] == c]
            if not amostras_classe:
                continue
            color = CORES_CLASSES.get(c, "#7f8c8d")
            rgb = CORES_RGB.get(c, (127, 140, 141))
            
            # Plota cada material desta classe com seu símbolo correspondente
            materiais_presentes = list(set([a["material"] for a in amostras_classe]))
            for mat_nome in materiais_presentes:
                simbolo = SIMBOLOS_MATERIAIS.get(mat_nome, "o")
                amostras_mat = [a for a in amostras_classe if a["material"] == mat_nome]
                if not amostras_mat:
                    continue
                tau_sub = [a["tau"] for a in amostras_mat]
                auc_sub = [a["auc"] for a in amostras_mat]
                self.plot_stat_scatter.plot(tau_sub, auc_sub, pen=None, symbol=simbolo, symbolSize=10,
                                            symbolBrush=pg.mkBrush(rgb[0], rgb[1], rgb[2], 200),
                                            symbolPen=pg.mkPen('w', width=0.5), name=f"{c.capitalize()} ({mat_nome})")

    def ao_mover_mouse_estatistico(self, pos):
        if not hasattr(self, 'amostras_filtradas') or not self.amostras_filtradas:
            return
            
        melhor_amostra = None
        menor_dist_pixel = 15.0  # Limite de 15 pixels para capturar o ponto
        
        for plot, tipo_grafico in [
            (self.plot_stat_scatter, "scatter"),
            (self.plot_stat_auc, "auc"),
            (self.plot_stat_tau, "tau")
        ]:
            vb = plot.vb
            if vb.sceneBoundingRect().contains(pos):
                mouse_point = vb.mapSceneToView(pos)
                
                for amostra in self.amostras_filtradas:
                    if tipo_grafico == "scatter":
                        x_pts, y_pts = amostra["tau"], amostra["auc"]
                    elif tipo_grafico == "auc":
                        x_pts = amostra.get("pos_x_auc_plot", 0.0)
                        y_pts = amostra["auc"]
                    elif tipo_grafico == "tau":
                        x_pts = amostra.get("pos_x_tau_plot", 0.0)
                        y_pts = amostra["tau"]
                    else:
                        continue
                        
                    p_point = vb.mapViewToScene(QtCore.QPointF(x_pts, y_pts))
                    dist_px = pg.Point(p_point - pos).length()
                    
                    if dist_px < menor_dist_pixel:
                        menor_dist_pixel = dist_px
                        melhor_amostra = amostra
                
                # Encontrou o viewbox sob o mouse, encerra a verificação dos outros plots
                break
                
        if melhor_amostra:
            tooltip_text = (
                f"🆔 <b>ID Cupom:</b> {melhor_amostra['id']}<br>"
                f"🛡️ <b>Mat:</b> {melhor_amostra['material']}<br>"
                f"📊 <b>Classe:</b> {melhor_amostra['classe'].capitalize()}<br>"
                f"⏱️ <b>Tau:</b> {melhor_amostra['tau']:.3f} &mu;s<br>"
                f"📐 <b>AUC:</b> {melhor_amostra['auc']:.1f}"
            )
            
            # Atualiza o texto (suporta rich text HTML)
            self.tooltip_estatistico.setText(tooltip_text)
            self.tooltip_estatistico.adjustSize()
            
            # Converte as coordenadas do evento da cena para coordenadas locais do GraphicsLayoutWidget
            widget_pos = self.win_stats_plots.mapFromScene(pos)
            # Converte de coordenadas do GraphicsLayoutWidget para coordenadas da janela principal (self)
            parent_pos = self.win_stats_plots.mapTo(self, widget_pos)
            
            # Move o balão ligeiramente deslocado do cursor
            self.tooltip_estatistico.move(parent_pos.x() + 15, parent_pos.y() + 15)
            
            if not self.tooltip_estatistico.isVisible():
                self.tooltip_estatistico.show()
                self.tooltip_estatistico.raise_()
        else:
            if self.tooltip_estatistico.isVisible():
                self.tooltip_estatistico.hide()

    def carregar_lista_materiais(self):
        if os.path.exists(self.arquivo_materiais_config):
            try:
                with open(self.arquivo_materiais_config, "r", encoding="utf-8") as f:
                    return [line.strip() for line in f if line.strip()]
            except Exception as e:
                print(f"[MATERIAIS] Erro ao ler materiais customizados: {e}")
        return []

    def salvar_lista_materiais(self):
        try:
            with open(self.arquivo_materiais_config, "w", encoding="utf-8") as f:
                for mat in self.custom_materials:
                    f.write(f"{mat}\n")
        except Exception as e:
            print(f"[MATERIAIS] Erro ao salvar materiais customizados: {e}")

    def adicionar_material_customizado(self):
        novo_nome = self.edit_novo_material.text().strip()
        if not novo_nome:
            QtWidgets.QMessageBox.warning(self, "Nome Vazio", "Por favor, insira o nome do novo material!")
            return
            
        if ";" in novo_nome or "\n" in novo_nome:
            QtWidgets.QMessageBox.warning(self, "Caracter Inválido", "O nome do material não pode conter ponto e vírgula ';' ou quebras de linha!")
            return
            
        if novo_nome in ["A36 Comum", "A36 GE", "A36 GF", "Ar Livre"] or novo_nome in self.custom_materials:
            QtWidgets.QMessageBox.warning(self, "Material Existente", f"O material '{novo_nome}' já existe na interface!")
            return
            
        self.custom_materials.append(novo_nome)
        self.salvar_lista_materiais()
        self.atualizar_widgets_materiais()
        self.edit_novo_material.clear()
        
        if novo_nome in self.radio_buttons_material:
            self.radio_buttons_material[novo_nome].setChecked(True)
            
        QtWidgets.QMessageBox.information(self, "Sucesso", f"Material '{novo_nome}' adicionado com sucesso!")

    def remover_material_selecionado(self):
        material_a_remover = self.obter_material_e_classe_selecionados()[0]
        if material_a_remover in ["A36 Comum", "A36 GE", "A36 GF", "Ar Livre"]:
            QtWidgets.QMessageBox.warning(self, "Ação Proibida", "Não é permitido excluir os materiais padrão do sistema.")
            return
            
        resposta = QtWidgets.QMessageBox.question(
            self, 
            "Excluir Material", 
            f"Tem certeza de que deseja excluir o material '{material_a_remover}'?\nEsta ação não removerá os dados antigos do CSV, mas o material não aparecerá mais nos controles da interface.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if resposta == QtWidgets.QMessageBox.Yes:
            if material_a_remover in self.custom_materials:
                self.custom_materials.remove(material_a_remover)
                self.salvar_lista_materiais()
                self.atualizar_widgets_materiais()
                self.radio_buttons_material["A36 Comum"].setChecked(True)
                QtWidgets.QMessageBox.information(self, "Sucesso", f"Material '{material_a_remover}' removido!")

    def atualizar_widgets_materiais(self):
        self.todos_materiais = ["A36 Comum", "A36 GE", "A36 GF"] + self.custom_materials + ["Ar Livre"]
        
        # --- ABA 1 (AQUISIÇÃO) ---
        while self.layout_mat_radios.count():
            child = self.layout_mat_radios.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        for btn in list(self.group_mat.buttons()):
            self.group_mat.removeButton(btn)
            
        self.radio_buttons_material.clear()
        
        for idx, mat_nome in enumerate(self.todos_materiais):
            rad = QtWidgets.QRadioButton(mat_nome)
            rad.setStyleSheet(self.radio_stylesheet)
            self.group_mat.addButton(rad)
            self.radio_buttons_material[mat_nome] = rad
            
            row = idx // 2
            col = idx % 2
            self.layout_mat_radios.addWidget(rad, row, col)
            
            if mat_nome == "Ar Livre":
                rad.toggled.connect(self.ao_toggle_ar_livre_material)
                
        if "A36 Comum" in self.radio_buttons_material:
            self.radio_buttons_material["A36 Comum"].setChecked(True)
            
        # --- ABA 2 (ESTATÍSTICA) ---
        if hasattr(self, 'layout_filter_materiais'):
            while self.layout_filter_materiais.count():
                child = self.layout_filter_materiais.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                    
            self.filter_checkboxes_material.clear()
            
            for mat_nome in self.todos_materiais:
                chk = QtWidgets.QCheckBox(mat_nome)
                chk.setChecked(True)
                chk.setStyleSheet("font-size: 9pt; color: #e1e1e6;")
                chk.stateChanged.connect(self.atualizar_graficos_estatisticos)
                self.filter_checkboxes_material[mat_nome] = chk
                self.layout_filter_materiais.addWidget(chk)
                
        # --- ABA 3 (VALIDAÇÃO) ---
        if hasattr(self, 'layout_val_mat_radios'):
            while self.layout_val_mat_radios.count():
                child = self.layout_val_mat_radios.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                    
            for btn in list(self.group_val_mat.buttons()):
                self.group_val_mat.removeButton(btn)
                
            self.val_radio_buttons_material.clear()
            
            for idx, mat_nome in enumerate(self.todos_materiais):
                rad = QtWidgets.QRadioButton(mat_nome)
                rad.setStyleSheet(self.radio_stylesheet)
                self.group_val_mat.addButton(rad)
                self.val_radio_buttons_material[mat_nome] = rad
                
                row = idx // 2
                col = idx % 2
                self.layout_val_mat_radios.addWidget(rad, row, col)
                
                if mat_nome == "Ar Livre":
                    rad.toggled.connect(self.ao_toggle_ar_livre_val_material)
                    
            if "A36 Comum" in self.val_radio_buttons_material:
                self.val_radio_buttons_material["A36 Comum"].setChecked(True)

    def ao_toggle_ar_livre_val_material(self, checked):
        if checked:
            self.rad_val_cls_ar.blockSignals(True)
            self.rad_val_cls_ar.setChecked(True)
            self.rad_val_cls_ar.blockSignals(False)

    def ao_toggle_ar_livre_val_classe(self, checked):
        if checked:
            if "Ar Livre" in self.val_radio_buttons_material:
                rad = self.val_radio_buttons_material["Ar Livre"]
                rad.blockSignals(True)
                rad.setChecked(True)
                rad.blockSignals(False)

    def obter_material_e_classe_validacao(self):
        material = "A36 Comum"
        for mat_nome, rad in self.val_radio_buttons_material.items():
            if rad.isChecked():
                material = mat_nome
                break
            
        if self.rad_val_cls_saudavel.isChecked():
            classe = "Saudável"
        elif self.rad_val_cls_leve.isChecked():
            classe = "Leve"
        elif self.rad_val_cls_moderada.isChecked():
            classe = "Moderada"
        elif self.rad_val_cls_avancada.isChecked():
            classe = "Avançada"
        elif self.rad_val_cls_corroido.isChecked():
            classe = "Corroído"
        else:
            classe = "Ar Livre"
        return material, classe

    def iniciar_ensaio_validacao(self):
        if not self.serial_thread.running:
            QtWidgets.QMessageBox.warning(self, "Sem conexão", "Conecte na porta serial antes de iniciar o teste de validação!")
            return
            
        id_amostra = self.edit_val_id.text().strip()
        if not id_amostra:
            QtWidgets.QMessageBox.warning(self, "ID Vazio", "Por favor, insira o ID do cupom para validação!")
            return
            
        opcao_tempo = self.combo_val_duracao.currentText()
        if opcao_tempo == "Contínuo (Manual)":
            self.val_test_duration = -1
        elif opcao_tempo == "1 segundo":
            self.val_test_duration = 1000
        elif opcao_tempo == "10 segundos":
            self.val_test_duration = 10000
        elif opcao_tempo == "30 segundos":
            self.val_test_duration = 30000
        elif opcao_tempo == "60 segundos":
            self.val_test_duration = 60000
            
        self.val_samples_captured = 0
        self.val_mat_matches = 0
        self.val_cls_matches = 0
        self.val_test_elapsed = 0
        self.val_test_data = []
        
        self.lbl_c1_val.setText("0")
        self.lbl_c2_val.setText("0.0%")
        self.lbl_c3_val.setText("0.0%")
        self.tbl_val_resultados.setRowCount(0)
        self.console_val_relatorio.clear()
        self.console_val_relatorio.append(">>> TESTE DE VALIDAÇÃO INICIADO <<<")
        
        self.btn_val_iniciar.setEnabled(False)
        self.btn_val_iniciar.setStyleSheet("background-color: #7f8c8d; color: white; font-weight: bold; font-size: 11pt;")
        self.btn_val_finalizar.setEnabled(True)
        self.btn_val_finalizar.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; font-size: 11pt;")
        
        self.edit_val_id.setEnabled(False)
        self.combo_val_duracao.setEnabled(False)
        for rad in self.val_radio_buttons_material.values():
            rad.setEnabled(False)
        self.rad_val_cls_saudavel.setEnabled(False)
        self.rad_val_cls_leve.setEnabled(False)
        self.rad_val_cls_moderada.setEnabled(False)
        self.rad_val_cls_avancada.setEnabled(False)
        self.rad_val_cls_corroido.setEnabled(False)
        self.rad_val_cls_ar.setEnabled(False)
        
        self.is_running_validation_test = True
        self.lbl_val_status.setText("Status: Executando...")
        self.lbl_val_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        
        if self.val_test_duration > 0:
            self.progress_val.setValue(0)
            self.lbl_val_timer.setText(f"Tempo Restante: {self.val_test_duration/1000:.1f} s")
            self.val_test_timer.start(100)
        else:
            self.progress_val.setValue(100)
            self.lbl_val_timer.setText("Duração: Manual (Contínuo)")
            
        if not self.chk_auto_trigger.isChecked():
            self.chk_auto_trigger.setChecked(True)

    def ao_tick_ensaio_validacao(self):
        if not self.is_running_validation_test:
            return
            
        self.val_test_elapsed += 100
        tempo_restante = max(0, self.val_test_duration - self.val_test_elapsed)
        self.lbl_val_timer.setText(f"Tempo Restante: {tempo_restante/1000:.1f} s")
        
        porcentagem = int((self.val_test_elapsed / self.val_test_duration) * 100)
        self.progress_val.setValue(porcentagem)
        
        if self.val_test_elapsed >= self.val_test_duration:
            self.val_test_timer.stop()
            self.finalizar_ensaio_validacao()

    def finalizar_ensaio_validacao(self):
        if not self.is_running_validation_test:
            return
            
        self.is_running_validation_test = False
        self.val_test_timer.stop()
        
        self.btn_val_iniciar.setEnabled(True)
        self.btn_val_iniciar.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 11pt;")
        self.btn_val_finalizar.setEnabled(False)
        self.btn_val_finalizar.setStyleSheet("background-color: #7f8c8d; color: white; font-weight: bold; font-size: 11pt;")
        
        self.edit_val_id.setEnabled(True)
        self.combo_val_duracao.setEnabled(True)
        for rad in self.val_radio_buttons_material.values():
            rad.setEnabled(True)
        self.rad_val_cls_saudavel.setEnabled(True)
        self.rad_val_cls_leve.setEnabled(True)
        self.rad_val_cls_moderada.setEnabled(True)
        self.rad_val_cls_avancada.setEnabled(True)
        self.rad_val_cls_corroido.setEnabled(True)
        self.rad_val_cls_ar.setEnabled(True)
        
        self.lbl_val_status.setText("Status: Finalizado")
        self.lbl_val_status.setStyleSheet("color: #f1c40f; font-weight: bold;")
        
        self.chk_auto_trigger.setChecked(False)
        self.gerar_relatorio_ensaio_validacao()

    def gerar_relatorio_ensaio_validacao(self):
        self.console_val_relatorio.append("\n==========================================")
        self.console_val_relatorio.append("   RELATÓRIO FINAL DE VALIDAÇÃO DA IA")
        self.console_val_relatorio.append("==========================================")
        
        id_amostra = self.edit_val_id.text().strip()
        mat_real, cls_real = self.obter_material_e_classe_validacao()
        self.console_val_relatorio.append(f"Cupom Identificado: {id_amostra}")
        self.console_val_relatorio.append(f"Material Real Alvo: {mat_real}")
        self.console_val_relatorio.append(f"Classe Real Alvo: {cls_real}")
        self.console_val_relatorio.append(f"Total de Amostras Lidas: {self.val_samples_captured}")
        
        if self.val_samples_captured == 0:
            self.console_val_relatorio.append("\n[AVISO] Nenhuma amostra foi capturada durante o ensaio.")
            return
            
        acc_mat = (self.val_mat_matches / self.val_samples_captured) * 100
        acc_cls = (self.val_cls_matches / self.val_samples_captured) * 100
        
        self.console_val_relatorio.append(f"\n--- Desempenho do Classificador (IA) ---")
        self.console_val_relatorio.append(f"* Acurácia de Material: {acc_mat:.1f}% ({self.val_mat_matches}/{self.val_samples_captured})")
        self.console_val_relatorio.append(f"* Acurácia de Classe: {acc_cls:.1f}% ({self.val_cls_matches}/{self.val_samples_captured})")
        
        taus = [d["tau"] for d in self.val_test_data if d["tau"] > 0]
        aucs = [d["auc"] for d in self.val_test_data]
        
        if taus:
            self.console_val_relatorio.append(f"\n--- Métricas Estatísticas do Ensaio ---")
            self.console_val_relatorio.append(f"* Tau Médio (μs): {np.mean(taus):.4f} (DP: {np.std(taus)*1000:.2f} ns)")
            self.console_val_relatorio.append(f"* AUC Média: {np.mean(aucs):.1f} (DP: {np.std(aucs):.1f})")
            
        self.console_val_relatorio.append("\n>>> Resultados salvos em 'testes_validacao_ia.csv' <<<")

    def processar_leitura_validacao(self, tau, auc, mat_prev, cls_prev, confianca, valores):
        self.val_samples_captured += 1
        
        id_amostra = self.edit_val_id.text().strip()
        mat_real, cls_real = self.obter_material_e_classe_validacao()
        
        mat_match = (mat_prev == mat_real)
        cls_match = (cls_prev == cls_real)
        
        if mat_match:
            self.val_mat_matches += 1
        if cls_match:
            self.val_cls_matches += 1
            
        self.val_test_data.append({
            "tau": tau,
            "auc": auc
        })
        
        self.lbl_c1_val.setText(str(self.val_samples_captured))
        acc_mat = (self.val_mat_matches / self.val_samples_captured) * 100
        acc_cls = (self.val_cls_matches / self.val_samples_captured) * 100
        self.lbl_c2_val.setText(f"{acc_mat:.1f}%")
        self.lbl_c3_val.setText(f"{acc_cls:.1f}%")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            escrever_cabecalho = not os.path.exists(self.arquivo_csv_validacao)
            with open(self.arquivo_csv_validacao, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                if escrever_cabecalho:
                    cabecalho = ["timestamp", "id_amostra", "material_real", "classe_real", 
                                 "tau_medido", "auc_medido", "material_previsto", "classe_prevista", 
                                 "confianca_prevista", "dt_us"] + [f"p_{i}" for i in range(256)]
                    writer.writerow(cabecalho)
                
                linha = [timestamp, id_amostra, mat_real, cls_real, 
                         f"{tau:.4f}", f"{auc:.1f}", mat_prev, cls_prev, 
                         f"{confianca:.1f}", f"{self.dt_us}"] + valores
                writer.writerow(linha)
        except Exception as e:
            print(f"[ERRO VALIDACAO] Falha ao gravar CSV: {e}")
            
        row_idx = self.tbl_val_resultados.rowCount()
        self.tbl_val_resultados.insertRow(row_idx)
        
        tempo_s = self.val_test_elapsed / 1000.0 if self.val_test_duration > 0 else (row_idx * 0.03)
        match_str = "SIM" if (mat_match and cls_match) else "NÃO"
        
        self.tbl_val_resultados.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(str(self.val_samples_captured)))
        self.tbl_val_resultados.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(f"{tempo_s:.1f}"))
        self.tbl_val_resultados.setItem(row_idx, 2, QtWidgets.QTableWidgetItem(f"{tau:.2f}"))
        self.tbl_val_resultados.setItem(row_idx, 3, QtWidgets.QTableWidgetItem(f"{auc:.1f}"))
        self.tbl_val_resultados.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(mat_real))
        self.tbl_val_resultados.setItem(row_idx, 5, QtWidgets.QTableWidgetItem(mat_prev))
        self.tbl_val_resultados.setItem(row_idx, 6, QtWidgets.QTableWidgetItem(cls_real))
        self.tbl_val_resultados.setItem(row_idx, 7, QtWidgets.QTableWidgetItem(cls_prev))
        
        match_item = QtWidgets.QTableWidgetItem(match_str)
        if match_str == "SIM":
            match_item.setBackground(QtGui.QColor(39, 174, 96, 60))
        else:
            match_item.setBackground(QtGui.QColor(192, 57, 43, 60))
        self.tbl_val_resultados.setItem(row_idx, 8, match_item)
        self.tbl_val_resultados.scrollToBottom()

    def resizeEvent(self, event):
        super().resizeEvent(event)


# =====================================================================
# INICIALIZAÇÃO DO APLICATIVO QT FUSION
# =====================================================================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    
    # Define o tema Fusion para a interface PyQt
    app.setStyle("Fusion")
    
    # Paleta de cores escura personalizada (Premium Dark Theme)
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 34))
    dark_palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(20, 20, 22))
    dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(42, 42, 48))
    dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(45, 45, 50))
    dark_palette.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(45, 45, 50))
    dark_palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    dark_palette.setColor(QtGui.QPalette.Link, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
    app.setPalette(dark_palette)

    # Força a estilização do QToolTip via folha de estilos para garantir visibilidade total do texto branco
    app.setStyleSheet("""
        QToolTip {
            color: #ffffff;
            background-color: #2e2e32;
            border: 1px solid #55555a;
            padding: 4px;
            font-size: 10pt;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
    """)

    plotter = EddyCurrentPlotter()
    plotter.show()
    sys.exit(app.exec_())
