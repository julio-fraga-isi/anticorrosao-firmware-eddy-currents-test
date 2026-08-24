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
import json
import time
import numpy as np
from datetime import datetime
from collections import deque
import serial
import serial.tools.list_ports
import struct

from PyQt5 import QtCore, QtWidgets, QtGui
import pyqtgraph as pg

# Importações dos submódulos modularizados
from gui.utils import normalizar_nome_classe, calcular_tau_e_auc, AdaptiveRealtimeStabilizer
from gui.widgets import ExclusaoSeletivaDialog, CollapsibleGroupBox
from gui.serial_worker import SerialWorker
from gui.dataset_manager import DatasetManager
from gui.coil_manager import CoilCharacterizationManager, CoilRegistrationDialog, Coil3DPlotDialog

# Configurações do Gráfico de Tendência
MAX_TREND_POINTS = 200

# Mapeamento unificado de cores por classe de degradação e formas por material
CORES_CLASSES = {
    "Saudável": "#3498db",
    "Leve": "#1abc9c",
    "Moderada": "#f1c40f",
    "Avançada": "#e67e22",
    "Corroído": "#e74c3c",
    "Ar Livre": "#9b59b6",
    "Não Definido": "#95a5a6"
}

SIMBOLOS_MATERIAIS = {
    "A36 Comum": "o",
    "A36 GE": "s",
    "A36 GF": "d",
    "Estrutura Torre": "t",
    "Ar Livre": "+"
}

def obter_cor_classe(cls_nome):
    if not cls_nome: return "#3498db"
    raw = str(cls_nome).strip()
    if "saud" in raw.lower(): return "#3498db"
    if "leve" in raw.lower(): return "#1abc9c"
    if "mod" in raw.lower(): return "#f1c40f"
    if "avan" in raw.lower(): return "#e67e22"
    if "corr" in raw.lower(): return "#e74c3c"
    if "ar" in raw.lower(): return "#9b59b6"
    if "nao def" in raw.lower() or "não def" in raw.lower() or raw.lower() == "nd": return "#95a5a6"
    return "#3498db"

def obter_simbolo_material(mat_nome):
    if not mat_nome: return "o"
    raw = str(mat_nome).strip().upper()
    if "GE" in raw: return "s"
    if "GF" in raw: return "d"
    if "TORRE" in raw or "ET" in raw: return "t"
    if "AR" in raw or "AL" in raw: return "+"
    return "o"

ESTILOS_MATERIAIS = {
    "A36 Comum": QtCore.Qt.SolidLine,
    "A36 GE": QtCore.Qt.DashLine,
    "A36 GF": QtCore.Qt.DotLine,
    "Estrutura Torre": QtCore.Qt.DashDotLine,
    "Ar Livre": QtCore.Qt.SolidLine
}

def obter_estilo_material(mat_nome):
    if not mat_nome: return QtCore.Qt.SolidLine
    raw = str(mat_nome).strip().upper()
    if "GE" in raw: return QtCore.Qt.DashLine
    if "GF" in raw: return QtCore.Qt.DotLine
    if "TORRE" in raw or "ET" in raw: return QtCore.Qt.DashDotLine
    if "AR" in raw or "AL" in raw: return QtCore.Qt.SolidLine
    return QtCore.Qt.SolidLine


class FullScreenContainerDialog(QtWidgets.QDialog):
    def __init__(self, container_widget, original_parent, title="Gráficos em Tela Cheia", parent=None):
        super().__init__(parent)
        self.container_widget = container_widget
        self.original_parent = original_parent

        # Salva o índice original e stretch do container no layout pai antes de reparentar
        self.original_index = -1
        self.original_stretch = 1
        if original_parent:
            parent_layout = original_parent.layout() if callable(getattr(original_parent, 'layout', None)) else getattr(original_parent, 'layout', None)
            if parent_layout and hasattr(parent_layout, 'indexOf'):
                try:
                    self.original_index = parent_layout.indexOf(container_widget)
                except Exception:
                    self.original_index = -1

        self.setWindowTitle(title)
        self.setStyleSheet("background-color: #121214; color: #ffffff;")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowMaximizeButtonHint | QtCore.Qt.WindowCloseButtonHint)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)

        # Header Bar
        header = QtWidgets.QHBoxLayout()
        lbl_title = QtWidgets.QLabel(f"<h2>📊 {title}</h2>")
        lbl_title.setStyleSheet("color: #00e676; font-weight: bold; font-family: 'Segoe UI';")
        header.addWidget(lbl_title)
        header.addStretch()

        btn_close = QtWidgets.QPushButton("❌ Fechar Tela Cheia (ESC)")
        btn_close.setMinimumHeight(38)
        btn_close.setCursor(QtCore.Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; color: white; font-weight: bold; font-size: 10pt;
                padding: 0 16px; border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        btn_close.clicked.connect(self.close)
        header.addWidget(btn_close)

        self.layout.addLayout(header)

        # Reparenta o container gráfico para a janela em tela cheia
        self.layout.addWidget(container_widget, 1)

        self.floating_hud = None

        self.showMaximized()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'floating_hud') and self.floating_hud is not None:
            self.floating_hud.raise_()

    def closeEvent(self, event):
        if self.parent() and hasattr(self.parent(), '_fullscreen_dialogs_ativos'):
            self.parent()._fullscreen_dialogs_ativos.discard(self)

        # Restaura o container gráfico exatamente no seu índice original no layout pai
        if self.original_parent:
            parent_layout = None
            if hasattr(self.original_parent, 'layout'):
                attr = getattr(self.original_parent, 'layout')
                if callable(attr):
                    try: parent_layout = attr()
                    except Exception: parent_layout = attr
                else:
                    parent_layout = attr

            if parent_layout:
                idx = getattr(self, 'original_index', -1)
                stretch = getattr(self, 'original_stretch', 2)
                if idx >= 0 and hasattr(parent_layout, 'insertWidget'):
                    parent_layout.insertWidget(idx, self.container_widget, stretch)
                elif hasattr(parent_layout, 'addWidget'):
                    parent_layout.addWidget(self.container_widget, stretch)
                else:
                    self.container_widget.setParent(self.original_parent)
            else:
                self.container_widget.setParent(self.original_parent)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class FullScreenSinglePlotDialog(QtWidgets.QDialog):
    def __init__(self, plot_item, container_win, row, col, col_span=1, title="Gráfico Individual", parent=None):
        super().__init__(parent)
        self.plot_item = plot_item
        self.container_win = container_win
        self.row = row
        self.col = col
        self.col_span = col_span

        self.setWindowTitle(title)
        self.setStyleSheet("background-color: #121214; color: #ffffff;")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowMaximizeButtonHint | QtCore.Qt.WindowCloseButtonHint)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)

        # Header Bar
        header = QtWidgets.QHBoxLayout()
        lbl_title = QtWidgets.QLabel(f"<h2>🔍 {title}</h2>")
        lbl_title.setStyleSheet("color: #00e676; font-weight: bold; font-family: 'Segoe UI';")
        header.addWidget(lbl_title)
        header.addStretch()

        btn_close = QtWidgets.QPushButton("❌ Fechar Tela Cheia (ESC)")
        btn_close.setMinimumHeight(38)
        btn_close.setCursor(QtCore.Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; color: white; font-weight: bold; font-size: 10pt;
                padding: 0 16px; border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        btn_close.clicked.connect(self.close)
        header.addWidget(btn_close)

        self.layout.addLayout(header)

        # Container do gráfico individual
        self.full_win = pg.GraphicsLayoutWidget()
        self.full_win.setBackground('#121214')
        self.layout.addWidget(self.full_win, 1)

        # Move o plot_item individual para o layout de tela cheia
        if hasattr(container_win, 'ci'):
            container_win.ci.removeItem(plot_item)
        self.full_win.addItem(plot_item)

        self.showMaximized()

    def closeEvent(self, event):
        # Restaura o plot_item de volta para a sua posição exata na grade original
        try:
            self.full_win.removeItem(self.plot_item)
            if hasattr(self.container_win, 'ci'):
                self.container_win.ci.addItem(self.plot_item, row=self.row, col=self.col, colspan=self.col_span)
        except Exception as e:
            print(f"[ERRO] Falha ao restaurar plot individual: {e}")
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class CustomFloatingTooltipWidget(QtWidgets.QFrame):
    """
    Balão de Tooltip flutuante personalizado, 50% semi-transparente, persistente e interativo.
    - Modo Hover: Não possui timeout; fica aberto indefinidamente enquanto o mouse estiver sobre o ponto/linha.
    - Modo Fixo (Pinned): Ao clicar no ponto, linha ou no próprio tooltip, ele fica fixo com um botão '✕' de fechar.
    """
    sig_closed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        self.is_pinned = False
        self.current_target_plot = None

        # Container Principal
        self.layout_main = QtWidgets.QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)

        self.box_frame = QtWidgets.QFrame(self)
        self.box_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 26, 0.88);
                border: 1px solid rgba(41, 182, 246, 0.35);
                border-radius: 6px;
                color: #ffffff;
            }
        """)
        self.box_layout = QtWidgets.QVBoxLayout(self.box_frame)
        self.box_layout.setContentsMargins(8, 6, 8, 6)
        self.box_layout.setSpacing(4)

        # Barra Superior de Controle (Botão Fechar ✕ - Modo Pinned)
        self.header_frame = QtWidgets.QFrame(self.box_frame)
        self.header_layout = QtWidgets.QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(0, 0, 0, 2)
        self.header_layout.setSpacing(4)
        
        self.lbl_pin_status = QtWidgets.QLabel("📌 <b>FIXADO</b>", self.header_frame)
        self.lbl_pin_status.setStyleSheet("color: #00e676; font-size: 8.5pt; font-family: Segoe UI;")
        
        self.btn_close = QtWidgets.QPushButton("✕", self.header_frame)
        self.btn_close.setFixedSize(18, 18)
        self.btn_close.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_close.setToolTip("Fechar Tooltip Fixado")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e53935;
                color: white;
                font-weight: bold;
                font-size: 8pt;
                border-radius: 9px;
                border: none;
            }
            QPushButton:hover {
                background-color: #ff1744;
            }
        """)
        self.btn_close.clicked.connect(self.fechar_tooltip)

        self.header_layout.addWidget(self.lbl_pin_status)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.btn_close)
        self.box_layout.addWidget(self.header_frame)
        self.header_frame.hide()  # Oculto por padrão no modo hover

        # Conteúdo HTML com transparência de fundo
        self.lbl_content = QtWidgets.QLabel(self.box_frame)
        self.lbl_content.setTextFormat(QtCore.Qt.RichText)
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setMaximumWidth(420)
        self.lbl_content.setStyleSheet("color: #ffffff; font-size: 9pt; font-family: Segoe UI, sans-serif; background: transparent;")
        self.box_layout.addWidget(self.lbl_content)

        self.layout_main.addWidget(self.box_frame)
        self.setMinimumSize(0, 0)
        self.box_frame.setMinimumSize(0, 0)

    def minimumSizeHint(self):
        return QtCore.QSize(1, 1)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if not self.is_pinned:
                self.fixar_tooltip()
            event.accept()
        else:
            super().mousePressEvent(event)

    def calculate_ideal_size(self):
        self.layout_main.activate()
        self.box_layout.activate()
        sh = self.sizeHint()
        sh_box = self.box_frame.sizeHint()
        
        doc_margin_w = 16
        doc_margin_h = 12
        
        self.lbl_content.adjustSize()
        lbl_sh = self.lbl_content.sizeHint()
        
        ideal_w = min(430, max(260, max(sh.width(), sh_box.width(), lbl_sh.width() + doc_margin_w)))
        content_w = ideal_w - doc_margin_w
        
        h_fw = self.lbl_content.heightForWidth(int(content_w))
        content_h = h_fw if h_fw > 0 else lbl_sh.height()
            
        header_h = 24 if self.header_frame.isVisible() else 0
        ideal_h = content_h + header_h + doc_margin_h + 6
        
        final_w = max(ideal_w, sh.width(), sh_box.width())
        final_h = max(ideal_h, sh.height(), sh_box.height())
        return QtCore.QSize(int(final_w), int(final_h))

    def set_content(self, html_text):
        self.lbl_content.setText(html_text)
        sz = self.calculate_ideal_size()
        self.resize(sz)

    def move_safe(self, pos_global):
        sz = self.calculate_ideal_size()
        w = sz.width()
        h = sz.height()

        screen = QtWidgets.QApplication.desktop().availableGeometry(pos_global)
        
        x = pos_global.x() + 15
        y = pos_global.y() + 15

        if x + w > screen.right():
            x = pos_global.x() - w - 15
        if y + h > screen.bottom():
            y = pos_global.y() - h - 15

        x = max(screen.left(), min(x, screen.right() - w))
        y = max(screen.top(), min(y, screen.bottom() - h))

        self.setGeometry(int(x), int(y), int(w), int(h))

    def exibir_hover(self, pos_global, html_text, target_plot=None):
        if self.is_pinned:
            return
        self.current_target_plot = target_plot
        self.header_frame.hide()
        self.box_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 26, 0.88);
                border: 1px solid rgba(41, 182, 246, 0.35);
                border-radius: 6px;
                color: #ffffff;
            }
        """)
        self.set_content(html_text)
        self.move_safe(pos_global)
        self.show()

    def fixar_tooltip(self, pos_global=None, html_text=None, target_plot=None):
        self.is_pinned = True
        if target_plot:
            self.current_target_plot = target_plot
        self.header_frame.show()
        self.box_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(22, 22, 30, 0.92);
                border: 1px solid rgba(0, 230, 118, 0.45);
                border-radius: 6px;
                color: #ffffff;
            }
        """)
        if html_text:
            self.set_content(html_text)
        if pos_global:
            self.move_safe(pos_global)
        else:
            sz = self.calculate_ideal_size()
            self.resize(sz)
        self.show()

    def fechar_tooltip(self):
        self.is_pinned = False
        self.current_target_plot = None
        self.header_frame.hide()
        self.hide()
        self.sig_closed.emit()


class EddyCurrentPlotter(QtWidgets.QWidget):

    def __init__(self, mode="all", launcher=None):
        super().__init__()
        self.mode = mode  # "all", "ai", or "coil"
        self.launcher = launcher
        
        # Estado serial compartilhado entre Módulo 1 e Módulo 2
        if self.launcher and hasattr(self.launcher, 'shared_serial_thread'):
            self.serial_thread = self.launcher.shared_serial_thread
        else:
            self.serial_thread = SerialWorker()
            if self.launcher:
                self.launcher.shared_serial_thread = self.serial_thread

        self.serial_thread.curva_recebida.connect(self.processar_nova_curva)
        self.serial_thread.erro_serial.connect(self.tratar_erro_serial)
        
        # Resolve caminhos relativos de forma compatível com PyInstaller (.exe) e código-fonte (.py)
        if hasattr(sys, '_MEIPASS'):
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        # Gerenciamento de Datasets e Bobinas (Cache inteligente)
        self.dataset_manager = DatasetManager()
        self.coil_manager = CoilCharacterizationManager(base_dir=self.base_dir)
        self.caracterizacao_dir = os.path.join(self.base_dir, "datasets", "caracterizacao_bobinas")
        self.loaded_coil_records = []
        self.imported_file_paths = []
        self.rt_stabilizer = AdaptiveRealtimeStabilizer()
        
        # Tooltip Flutuante Persistente e Interativo
        self.floating_tooltip = CustomFloatingTooltipWidget(self)
        self.floating_tooltip.sig_closed.connect(lambda: self.atualizar_destaque_visual_hover(target_plot=None))
        
        # Parâmetros físicos
        self.dt_us = 0.21875  # Padrão calibrado: 256 pontos em 56 us
        self.arquivo_csv = os.path.join(self.base_dir, "datasets", "dataset_cupons_indutancia.csv")
        self.leitura_ativa = False
        self.capturar_uma_curva = False
        
        # Gerenciamento de materiais (Banco de dados JSON)
        self.arquivo_materiais_config = os.path.join(self.base_dir, "materiais_cadastrados.json")
        self.arquivo_materiais_txt_legacy = os.path.join(self.base_dir, "materiais_customizados.txt")
        self.default_materials = ["A36 Comum", "A36 GE", "A36 GF", "Estrutura Torre", "Ar Livre"]
        self.custom_materials = []
        self.todos_materiais = self.carregar_lista_materiais()
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

        # Variáveis de monitoramento de tendência em tempo real (Módulo 2)
        self._rt_trend_buffer = []
        self._last_rt_trend_update_time = 0.0
        self._last_saved_v_ma = None
        self._last_saved_tau_trend = 0.0
        self._last_saved_auc_trend = 0.0
        self._rt_trend_n_samples = 0

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
        self.arquivo_csv_validacao = os.path.join(self.base_dir, "datasets", "testes_validacao_ia.csv")

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
        if self.mode == "ai":
            self.setWindowTitle("Módulo 1: Aquisição & Diagnóstico IA — Eddy Current")
        elif self.mode == "coil":
            self.setWindowTitle("Módulo 2: Caracterização & Comparação de Bobinas — Eddy Current")
        else:
            self.setWindowTitle("ISI Sensoriamento - Eddy Current Test Bench & Data Aquisition")
            
        self.resize(1350, 920)

        # Configurações de cores da biblioteca PyQtGraph
        pg.setConfigOptions(antialias=True)
        pg.setConfigOption("background", "#121214")
        pg.setConfigOption("foreground", "#e1e1e6")
        
        # Layout Principal com Abas (Tabs)
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(6)

        # Adiciona a Barra Superior de Navegação se o Módulo foi aberto via Launcher
        self.top_nav_bar = None
        if self.launcher is not None or self.mode in ["ai", "coil"]:
            self.top_nav_bar = QtWidgets.QHBoxLayout()
            self.top_nav_bar.setContentsMargins(4, 2, 4, 4)
            
            btn_back = QtWidgets.QPushButton("⬅️ Voltar ao Menu Principal")
            btn_back.setMinimumHeight(32)
            btn_back.setCursor(QtCore.Qt.PointingHandCursor)
            btn_back.setStyleSheet("""
                QPushButton {
                    background-color: #2c2c2e; color: #00e676; font-weight: bold; font-size: 9.5pt;
                    border: 1px solid #3a3a3c; border-radius: 4px; padding: 0 14px;
                }
                QPushButton:hover {
                    background-color: #3a3a3c; color: #ffffff; border: 1px solid #00e676;
                }
            """)
            btn_back.clicked.connect(self.voltar_ao_menu_principal)
            self.top_nav_bar.addWidget(btn_back)

            if self.mode == "ai":
                lbl_mod_name = QtWidgets.QLabel("<b>MÓDULO 1: Aquisição & Diagnóstico IA</b>")
            elif self.mode == "coil":
                lbl_mod_name = QtWidgets.QLabel("<b>MÓDULO 2: Caracterização & Comparação de Bobinas</b>")
            else:
                lbl_mod_name = QtWidgets.QLabel("<b>SISTEMA DE ENSAIO EDDY CURRENT</b>")

            lbl_mod_name.setStyleSheet("font-size: 11pt; color: #ffffff; margin-left: 10px;")
            self.top_nav_bar.addWidget(lbl_mod_name)
            self.top_nav_bar.addStretch()

            outer_layout.addLayout(self.top_nav_bar)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.tabBar().setElideMode(QtCore.Qt.ElideNone)
        self.tab_widget.tabBar().setUsesScrollButtons(True)
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a3a3c;
                background-color: #121214;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #1e1e1f;
                color: #a0a0a0;
                padding: 8px 20px;
                min-width: 170px;
                margin-right: 4px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-weight: bold;
                font-size: 9pt;
            }
            QTabBar::tab:selected {
                background-color: #2c2c2e;
                color: #00e676;
                border-bottom: 2px solid #00e676;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2a2a2c;
                color: #ffffff;
            }
        """)
        if self.mode != "coil":
            outer_layout.addWidget(self.tab_widget)

        if self.mode in ["all", "ai"]:
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
    
    
    
            # Campo para ajuste manual e visualização do tempo entre amostras (dt_us)
            layout_dt_container = QtWidgets.QVBoxLayout()
            
            layout_dt = QtWidgets.QHBoxLayout()
            lbl_dt = QtWidgets.QLabel("Intervalo dt Alvo (μs):")
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
            layout_dt_container.addLayout(layout_dt)
            
            # Label para exibir o dt real calculado pelo microcontrolador
            self.lbl_dt_medido = QtWidgets.QLabel("dt Real Medido: -- μs (-- kHz)")
            self.lbl_dt_medido.setStyleSheet("color: #2ecc71; font-size: 8pt; font-style: italic; margin-left: 2px;")
            layout_dt_container.addWidget(self.lbl_dt_medido)
            
            group_acq_layout.addLayout(layout_dt_container)
    
            # Campo para ajuste da Frequência de Disparo Síncrona (Hz) controlada pelo firmware
            layout_freq = QtWidgets.QHBoxLayout()
            lbl_freq = QtWidgets.QLabel("Frequência de Disparo (Hz):")
            lbl_freq.setStyleSheet("color: #e1e1e6; font-size: 9pt;")
            layout_freq.addWidget(lbl_freq)
            
            self.spin_freq = QtWidgets.QSpinBox()
            self.spin_freq.setRange(5, 100) # Limites de 5 Hz a 100 Hz
            self.spin_freq.setValue(30)     # Padrão: 30 Hz
            self.spin_freq.setSingleStep(5)
            self.spin_freq.valueChanged.connect(self.atualizar_frequencia_disparo)
            self.spin_freq.setStyleSheet("color: white; background-color: #2e2e32; border: 1px solid #55555a; padding: 2px;")
            self.spin_freq.setMinimumHeight(28)
            layout_freq.addWidget(self.spin_freq)
            group_acq_layout.addLayout(layout_freq)
    
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
            self.spin_janela_curva.setValue(1)
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
            self.spin_janela_metricas.setValue(200)
            self.spin_janela_metricas.setStyleSheet("color: white; background-color: #2e2e32; border: 1px solid #55555a; padding: 2px;")
            self.spin_janela_metricas.valueChanged.connect(self.atualizar_tamanho_janela_metricas)
            group_filters_layout.addWidget(self.spin_janela_metricas, 5, 1)
            
            self.chk_ia_usa_media_movel = QtWidgets.QCheckBox("Classificar IA com Média Móvel")
            self.chk_ia_usa_media_movel.setStyleSheet("color: #e1e1e6; font-size: 9pt; font-weight: bold;")
            self.chk_ia_usa_media_movel.setChecked(False)
            group_filters_layout.addWidget(self.chk_ia_usa_media_movel, 6, 0, 1, 2)
            
            group_filters_layout.addWidget(QtWidgets.QLabel("Janela da Média da IA:"), 7, 0)
            self.spin_janela_ia = QtWidgets.QSpinBox()
            self.spin_janela_ia.setRange(2, 100)
            self.spin_janela_ia.setValue(50)
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
            self.chk_salvar_media_movel.stateChanged.connect(self.ao_alterar_filtro_media_movel)
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
            panel_right_acq = QtWidgets.QWidget()
            panel_right_acq_layout = QtWidgets.QVBoxLayout(panel_right_acq)
            panel_right_acq_layout.setContentsMargins(0, 0, 0, 0)
            panel_right_acq_layout.setSpacing(2)

            self.win_plots = pg.GraphicsLayoutWidget()
            panel_right_acq_layout.addWidget(self.criar_barrafullscreen_container(self.win_plots, "Aba 1: Aquisição em Tempo Real"))
            panel_right_acq_layout.addWidget(self.win_plots, 1)
            tab_acq_layout.addWidget(panel_right_acq)
    
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
    
            self.chk_diferenciar_ids_tonalidade = QtWidgets.QCheckBox("Diferenciar Tonalidades por ID")
            self.chk_diferenciar_ids_tonalidade.setToolTip("Altera a tonalidade (luminosidade HSL) dos pontos para diferenciar IDs de amostras distintos dentro do mesmo material/classe")
            self.chk_diferenciar_ids_tonalidade.setChecked(False)
            group_filters_layout.addWidget(self.chk_diferenciar_ids_tonalidade, 8, 0, 1, 2)

            self.chk_enable_tooltips = QtWidgets.QCheckBox("Exibir Tooltips e Destaques Visuais")
            self.chk_enable_tooltips.setToolTip("Habilita ou desabilita a exibição de destaques visuais e balões de tooltip flutuantes nos gráficos")
            self.chk_enable_tooltips.setChecked(True)
            self.chk_enable_tooltips.stateChanged.connect(self.ao_alternar_exibicao_tooltips)
            group_filters_layout.addWidget(self.chk_enable_tooltips, 9, 0, 1, 2)

            # Conecta os sinais de mudança para atualizar os gráficos dinamicamente
            self.chk_filter_saudavel.stateChanged.connect(self.atualizar_graficos_estatisticos)
            self.chk_filter_leve.stateChanged.connect(self.atualizar_graficos_estatisticos)
            self.chk_filter_moderada.stateChanged.connect(self.atualizar_graficos_estatisticos)
            self.chk_filter_avancada.stateChanged.connect(self.atualizar_graficos_estatisticos)
            self.chk_filter_corroido.stateChanged.connect(self.atualizar_graficos_estatisticos)
            self.chk_filter_ar_cls.stateChanged.connect(self.atualizar_graficos_estatisticos)
            self.chk_filter_outliers.stateChanged.connect(self.atualizar_graficos_estatisticos)
            self.chk_diferenciar_ids_tonalidade.stateChanged.connect(self.atualizar_graficos_estatisticos)

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
            panel_right_stats = QtWidgets.QWidget()
            panel_right_stats_layout = QtWidgets.QVBoxLayout(panel_right_stats)
            panel_right_stats_layout.setContentsMargins(0, 0, 0, 0)
            panel_right_stats_layout.setSpacing(2)

            self.win_stats_plots = pg.GraphicsLayoutWidget()
            self.win_stats_plots.setStyleSheet("background-color: #121214; border: 1px solid #3a3a3c;")
            panel_right_stats_layout.addWidget(self.criar_barrafullscreen_container(self.win_stats_plots, "Aba 2: Análise Estatística (Offline)"))
            panel_right_stats_layout.addWidget(self.win_stats_plots, 1)
            tab_stats_layout.addWidget(panel_right_stats, 1)
    
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
    
            # Conecta o sinal de movimento e clique do mouse para tooltips dinâmicos e fixados
            self.win_stats_plots.scene().sigMouseMoved.connect(self.ao_mover_mouse_estatistico)
            self.win_stats_plots.scene().sigMouseClicked.connect(self.ao_clicar_mouse_grafico)
    
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
            panel_right_diag = QtWidgets.QWidget()
            panel_right_diag_layout = QtWidgets.QVBoxLayout(panel_right_diag)
            panel_right_diag_layout.setContentsMargins(0, 0, 0, 0)
            panel_right_diag_layout.setSpacing(2)

            self.win_diag_plots = pg.GraphicsLayoutWidget()
            self.win_diag_plots.setStyleSheet("background-color: #121214; border: 1px solid #3a3a3c;")
            panel_right_diag_layout.addWidget(self.criar_barrafullscreen_container(self.win_diag_plots, "Aba 4: Diagnóstico Físico IA (Tempo Real)"))
            panel_right_diag_layout.addWidget(self.win_diag_plots, 1)
            tab_diag_layout.addWidget(panel_right_diag, 1)
            
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
            self.plot_diag_scatter.setLabel('bottom', 'Tempo', 'us')
    
        if self.mode in ["all", "coil"]:
            # =====================================================================
            # ABA 5: Caracterização & Comparação de Bobinas (Lift-Off)
            # =====================================================================
            self.tab_coil_char = QtWidgets.QWidget()
            if self.mode != "coil":
                self.tab_widget.addTab(self.tab_coil_char, "Caracterização & Comparação de Bobinas")
            tab_coil_outer_layout = QtWidgets.QVBoxLayout(self.tab_coil_char)
            tab_coil_outer_layout.setContentsMargins(4, 4, 4, 4)
            tab_coil_outer_layout.setSpacing(4)
    
            # Barra Superior de Controles da Aba 5 (Botão Esconder/Exibir Painel Lateral + Seletor de Colunas)
            self.btn_toggle_coil_left = QtWidgets.QPushButton("◀ Esconder Painel Lateral")
            self.btn_toggle_coil_left.setMinimumHeight(28)
            self.btn_toggle_coil_left.setStyleSheet("""
                QPushButton {
                    background-color: #2c2c2e; color: #00e676; font-weight: bold; font-size: 8.5pt; border: 1px solid #3a3a3c; border-radius: 4px; padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #3a3a3c; color: #ffffff;
                }
            """)
            self.btn_toggle_coil_left.clicked.connect(self.toggle_painel_lateral_caracterizacao)

            opcoes_colunas = ["Auto (Dinâmico)", "1 Coluna", "2 Colunas", "3 Colunas", "4 Colunas", "5 Colunas"]
            combo_style = """
                QComboBox {
                    background-color: #2c2c2e; color: #00e676; border: 1px solid #3a3a3c;
                    border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 8.5pt;
                }
                QComboBox QAbstractItemView {
                    background-color: #1e1e1f; color: #ffffff; selection-background-color: #00e676; selection-color: #000000;
                }
            """

            lbl_cols_bobinas = QtWidgets.QLabel("Colunas dos Sensores:")
            lbl_cols_bobinas.setStyleSheet("color: #29b6f6; font-size: 8.5pt; font-weight: bold;")

            self.combo_num_colunas_bobinas = QtWidgets.QComboBox()
            self.combo_num_colunas_bobinas.addItems(opcoes_colunas)
            self.combo_num_colunas_bobinas.setCurrentIndex(2)
            self.combo_num_colunas_bobinas.setStyleSheet(combo_style)
            self.combo_num_colunas_bobinas.currentIndexChanged.connect(self.reorganizar_colunas_seletores_caracterizacao)

            lbl_cols_painel = QtWidgets.QLabel("Colunas dos Outros Seletores:")
            lbl_cols_painel.setStyleSheet("color: #e1e1e6; font-size: 8.5pt; font-weight: bold;")

            self.combo_num_colunas_painel = QtWidgets.QComboBox()
            self.combo_num_colunas_painel.addItems(opcoes_colunas)
            self.combo_num_colunas_painel.setCurrentIndex(0)
            self.combo_num_colunas_painel.setStyleSheet(combo_style)
            self.combo_num_colunas_painel.currentIndexChanged.connect(self.reorganizar_colunas_seletores_caracterizacao)

            if hasattr(self, 'top_nav_bar') and self.top_nav_bar is not None:
                self.top_nav_bar.addSpacing(15)
                self.top_nav_bar.addWidget(self.btn_toggle_coil_left)
                self.top_nav_bar.addSpacing(10)
                self.top_nav_bar.addWidget(lbl_cols_bobinas)
                self.top_nav_bar.addWidget(self.combo_num_colunas_bobinas)
                self.top_nav_bar.addSpacing(10)
                self.top_nav_bar.addWidget(lbl_cols_painel)
                self.top_nav_bar.addWidget(self.combo_num_colunas_painel)
            else:
                top_bar_tab5 = QtWidgets.QHBoxLayout()
                top_bar_tab5.addWidget(self.btn_toggle_coil_left)
                top_bar_tab5.addSpacing(15)
                top_bar_tab5.addWidget(lbl_cols_bobinas)
                top_bar_tab5.addWidget(self.combo_num_colunas_bobinas)
                top_bar_tab5.addSpacing(15)
                top_bar_tab5.addWidget(lbl_cols_painel)
                top_bar_tab5.addWidget(self.combo_num_colunas_painel)
                top_bar_tab5.addStretch()
                tab_coil_outer_layout.addLayout(top_bar_tab5)
    
            # Splitter Horizontal para permitir ajustar a largura do menu lateral manualmente
            self.splitter_tab_coil = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            self.splitter_tab_coil.setStyleSheet("""
                QSplitter::handle {
                    background-color: #3a3a3c;
                    width: 6px;
                }
                QSplitter::handle:hover {
                    background-color: #00e676;
                }
            """)
    
            # Sub-painel Esquerdo: Especificações e Controles (Scroll Area)
            coil_left = QtWidgets.QWidget()
            coil_left.setMinimumWidth(240)
            coil_left_layout = QtWidgets.QVBoxLayout(coil_left)
            coil_left_layout.setContentsMargins(0, 0, 0, 0)
    
            self.scroll_coil = QtWidgets.QScrollArea()
            self.scroll_coil.setWidgetResizable(True)
            self.scroll_coil.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.scroll_coil.setStyleSheet("background-color: #1e1e1e; border: none;")
            
            scroll_coil_content = QtWidgets.QWidget()
            scroll_coil_layout = QtWidgets.QVBoxLayout(scroll_coil_content)
            scroll_coil_layout.setContentsMargins(8, 8, 8, 8)
            scroll_coil_layout.setSpacing(12)

            # 0. Conectividade Serial e Modo de Operação (Módulo 2)
            group_coil_conn = CollapsibleGroupBox("🔌 Conectividade Serial & Operação")
            group_coil_conn_layout = QtWidgets.QVBoxLayout()
            group_coil_conn.setLayout(group_coil_conn_layout)

            grid_conn = QtWidgets.QGridLayout()
            grid_conn.addWidget(QtWidgets.QLabel("Porta COM:"), 0, 0)
            
            if not hasattr(self, 'combo_portas'):
                self.combo_portas = QtWidgets.QComboBox()
                self.atualizar_portas_disponiveis()

            grid_conn.addWidget(self.combo_portas, 0, 1)

            btn_refresh = QtWidgets.QPushButton("Refresh")
            btn_refresh.clicked.connect(self.atualizar_portas_disponiveis)
            grid_conn.addWidget(btn_refresh, 0, 2)

            grid_conn.addWidget(QtWidgets.QLabel("Baud Rate:"), 1, 0)
            if not hasattr(self, 'combo_baud'):
                self.combo_baud = QtWidgets.QComboBox()
                self.combo_baud.addItems(["115200", "230400", "460800", "921600"])
                self.combo_baud.setCurrentText("921600")
            grid_conn.addWidget(self.combo_baud, 1, 1, 1, 2)

            if not hasattr(self, 'btn_conectar'):
                self.btn_conectar = QtWidgets.QPushButton("Conectar")
                self.btn_conectar.clicked.connect(self.alternar_conexao)
                self.btn_conectar.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
            grid_conn.addWidget(self.btn_conectar, 2, 0, 1, 3)

            if not hasattr(self, 'lbl_status_conn'):
                self.lbl_status_conn = QtWidgets.QLabel("Status: Desconectado")
                self.lbl_status_conn.setStyleSheet("color: #e74c3c; font-weight: bold;")
            grid_conn.addWidget(self.lbl_status_conn, 3, 0, 1, 3)

            group_coil_conn_layout.addLayout(grid_conn)

            if not hasattr(self, 'btn_single_trigger'):
                self.btn_single_trigger = QtWidgets.QPushButton("Disparar Leitura Única")
                self.btn_single_trigger.clicked.connect(self.solicitar_leitura_manual)
                self.btn_single_trigger.setMinimumHeight(28)
                self.btn_single_trigger.setStyleSheet("font-weight: bold; background-color: #2980b9; color: white;")
            group_coil_conn_layout.addWidget(self.btn_single_trigger)

            if not hasattr(self, 'chk_auto_trigger'):
                self.chk_auto_trigger = QtWidgets.QCheckBox("Modo Contínuo (Auto-Trigger)")
                self.chk_auto_trigger.stateChanged.connect(self.alternar_auto_trigger)
            group_coil_conn_layout.addWidget(self.chk_auto_trigger)

            scroll_coil_layout.addWidget(group_coil_conn)
    
            # 1. Seleção e Cadastro de Bobinas / Sensores
            group_coil_select = QtWidgets.QGroupBox("Seleção do Sensor / Bobina")
            group_coil_select.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #3a3a3c;
                    border-radius: 4px;
                    margin-top: 12px;
                    font-weight: bold;
                    color: #29b6f6;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 3px;
                }
            """)
            group_coil_select_layout = QtWidgets.QVBoxLayout(group_coil_select)
            group_coil_select_layout.setSpacing(8)
    
            # Botão para abrir a caixa de diálogo de cadastro/edição
            self.btn_open_coil_dialog = QtWidgets.QPushButton("Cadastrar / Editar Sensores")
            self.btn_open_coil_dialog.setMinimumHeight(35)
            self.btn_open_coil_dialog.setStyleSheet("background-color: #29b6f6; color: #000000; font-weight: bold;")
            self.btn_open_coil_dialog.clicked.connect(self.abrir_dialogo_cadastro_bobina)
            group_coil_select_layout.addWidget(self.btn_open_coil_dialog)
    
            # Container para os Radio Buttons (Bullet Points) dos sensores
            self.widget_radio_bobinas_container = QtWidgets.QWidget()
            self.layout_radio_bobinas = QtWidgets.QGridLayout(self.widget_radio_bobinas_container)
            self.layout_radio_bobinas.setContentsMargins(0, 0, 0, 0)
            self.layout_radio_bobinas.setSpacing(4)
            self.group_radio_bobinas = QtWidgets.QButtonGroup(self)
            self.lista_widgets_radio_bobinas = []
            
            group_coil_select_layout.addWidget(self.widget_radio_bobinas_container)
            scroll_coil_layout.addWidget(group_coil_select)
    
            # 2. Exibição das Características do Sensor Selecionado (Card Colapsável / Exibir-Esconder)
            group_coil_card = CollapsibleGroupBox("Características do Sensor Selecionado", parent=self)
            coil_card_layout = QtWidgets.QVBoxLayout()
            self.txt_coil_specs_card = QtWidgets.QTextEdit()
            self.txt_coil_specs_card.setReadOnly(True)
            self.txt_coil_specs_card.setMinimumHeight(150)
            self.txt_coil_specs_card.setStyleSheet("""
                QTextEdit {
                    background-color: #121214;
                    color: #00ff00;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 8.5pt;
                    border: 1px solid #2a2a2e;
                    border-radius: 4px;
                    padding: 6px;
                }
            """)
            coil_card_layout.addWidget(self.txt_coil_specs_card)
            group_coil_card.setContentLayout(coil_card_layout)
            scroll_coil_layout.addWidget(group_coil_card)
    
            # 3. Calculadora de Lift-Off (Espaçadores & Berço)
            group_coil_env = QtWidgets.QGroupBox("Calculadora de Lift-Off (Espaçadores & Berço)")
            group_coil_env.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #3a3a3c;
                    border-radius: 4px;
                    margin-top: 12px;
                    font-weight: bold;
                    color: #ab47bc;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 3px;
                }
                QCheckBox, QRadioButton {
                    color: #ffffff !important;
                    font-size: 8pt;
                    font-weight: bold;
                    spacing: 5px;
                }
                QCheckBox::indicator, QRadioButton::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1.5px solid #888888;
                    background-color: #222225;
                    border-radius: 3px;
                }
                QCheckBox::indicator:hover, QRadioButton::indicator:hover {
                    border: 1.5px solid #00e676;
                }
                QCheckBox::indicator:checked {
                    background-color: #00e676;
                    border: 1.5px solid #ffffff;
                }
                QRadioButton::indicator {
                    border-radius: 7px;
                }
                QRadioButton::indicator:checked {
                    background-color: #29b6f6;
                    border: 2px solid #ffffff;
                    border-radius: 7px;
                }
            """)
            coil_env_layout = QtWidgets.QVBoxLayout(group_coil_env)
            coil_env_layout.setSpacing(8)
    
            coil_env_form = QtWidgets.QFormLayout()
            coil_env_form.setSpacing(6)
    
            def criar_linha_separadora():
                line = QtWidgets.QFrame()
                line.setFrameShape(QtWidgets.QFrame.HLine)
                line.setFrameShadow(QtWidgets.QFrame.Sunken)
                line.setStyleSheet("background-color: #3a3a3c; min-height: 1px; max-height: 1px; border: none; margin-top: 3px; margin-bottom: 3px;")
                return line
    
            # Seleção da Base Berço (Checkboxes Exclusivos, Base P Padrão, 1 Coluna Fixa)
            self.chk_berco_maior = QtWidgets.QCheckBox("Base G (74.6x104.6mm | H=2.6mm)")
            self.chk_berco_menor = QtWidgets.QCheckBox("Base P (52.5x74.5mm | H=2.6mm)")
            self.chk_berco_menor.setChecked(True)
    
            self.group_berco = QtWidgets.QButtonGroup(self)
            self.group_berco.addButton(self.chk_berco_maior)
            self.group_berco.addButton(self.chk_berco_menor)
    
            self.chk_berco_maior.toggled.connect(self.calcular_liftoff_bancada)
            self.chk_berco_menor.toggled.connect(self.calcular_liftoff_bancada)
    
            self.layout_berco_grid = QtWidgets.QVBoxLayout()
            self.layout_berco_grid.setSpacing(3)
            self.layout_berco_grid.addWidget(self.chk_berco_maior)
            self.layout_berco_grid.addWidget(self.chk_berco_menor)
    
            coil_env_form.addRow("Modelo do Berço:", self.layout_berco_grid)
            coil_env_form.addRow(criar_linha_separadora())
    
            # Seleção de Espaçadores Empilhados via 4 Colunas (5mm, 4mm, 2mm, 1mm) e 2 Linhas (1x, 2x)
            self.chk_espacador_5mm_1 = QtWidgets.QCheckBox("1x")
            self.chk_espacador_5mm_2 = QtWidgets.QCheckBox("2x")
            self.chk_espacador_4mm_1 = QtWidgets.QCheckBox("1x")
            self.chk_espacador_4mm_2 = QtWidgets.QCheckBox("2x")
            self.chk_espacador_2mm_1 = QtWidgets.QCheckBox("1x")
            self.chk_espacador_2mm_2 = QtWidgets.QCheckBox("2x")
            self.chk_espacador_1mm_1 = QtWidgets.QCheckBox("1x")
            self.chk_espacador_1mm_2 = QtWidgets.QCheckBox("2x")
    
            # Aliases para compatibilidade legada
            self.chk_espacador_5mm = self.chk_espacador_5mm_1
            self.chk_espacador_4mm = self.chk_espacador_4mm_1
            self.chk_espacador_2mm = self.chk_espacador_2mm_1
            self.chk_espacador_1mm = self.chk_espacador_1mm_1
    
            # Conecta o comportamento mutuamente exclusivo (1x vs 2x) por espessura
            self.chk_espacador_5mm_1.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_5mm_1, self.chk_espacador_5mm_2))
            self.chk_espacador_5mm_2.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_5mm_2, self.chk_espacador_5mm_1))
    
            self.chk_espacador_4mm_1.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_4mm_1, self.chk_espacador_4mm_2))
            self.chk_espacador_4mm_2.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_4mm_2, self.chk_espacador_4mm_1))
    
            self.chk_espacador_2mm_1.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_2mm_1, self.chk_espacador_2mm_2))
            self.chk_espacador_2mm_2.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_2mm_2, self.chk_espacador_2mm_1))
    
            self.chk_espacador_1mm_1.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_1mm_1, self.chk_espacador_1mm_2))
            self.chk_espacador_1mm_2.clicked.connect(lambda: self.ao_alternar_checkbox_espacador(self.chk_espacador_1mm_2, self.chk_espacador_1mm_1))
    
            self.widget_spacers_container = QtWidgets.QWidget()
            layout_spacers_h = QtWidgets.QHBoxLayout(self.widget_spacers_container)
            layout_spacers_h.setContentsMargins(0, 2, 0, 2)
            layout_spacers_h.setSpacing(0)
    
            espacadores_cols = [
                ("5mm", self.chk_espacador_5mm_1, self.chk_espacador_5mm_2),
                ("4mm", self.chk_espacador_4mm_1, self.chk_espacador_4mm_2),
                ("2mm", self.chk_espacador_2mm_1, self.chk_espacador_2mm_2),
                ("1mm", self.chk_espacador_1mm_1, self.chk_espacador_1mm_2),
            ]
    
            for idx_col, (label_txt, chk_1, chk_2) in enumerate(espacadores_cols):
                col_widget = QtWidgets.QWidget()
                col_layout = QtWidgets.QVBoxLayout(col_widget)
                col_layout.setContentsMargins(8, 2, 8, 2)
                col_layout.setSpacing(4)
    
                lbl_title = QtWidgets.QLabel(label_txt)
                lbl_title.setAlignment(QtCore.Qt.AlignCenter)
                lbl_title.setStyleSheet("font-weight: bold; color: #00e676; font-size: 9pt;")
                col_layout.addWidget(lbl_title)
                col_layout.addWidget(chk_1)
                col_layout.addWidget(chk_2)
    
                layout_spacers_h.addWidget(col_widget)
    
                if idx_col < len(espacadores_cols) - 1:
                    sep_v = QtWidgets.QFrame()
                    sep_v.setFrameShape(QtWidgets.QFrame.VLine)
                    sep_v.setFrameShadow(QtWidgets.QFrame.Sunken)
                    sep_v.setStyleSheet("background-color: rgba(255, 255, 255, 0.15); width: 1px;")
                    layout_spacers_h.addWidget(sep_v)
    
            coil_env_form.addRow("Espaçadores:", self.widget_spacers_container)
            coil_env_form.addRow(criar_linha_separadora())
    
            # Distância Resultante (Calculada e Editável com Trava de Scroll e Confirmação ao Concluir Edição)
            self.spin_liftoff_dist = QtWidgets.QDoubleSpinBox()
            self.spin_liftoff_dist.setRange(0.0, 100.0)
            self.spin_liftoff_dist.setSingleStep(0.5)
            self.spin_liftoff_dist.setSuffix(" mm")
            self.spin_liftoff_dist.setValue(0.0)
            self.spin_liftoff_dist.wheelEvent = lambda event: event.ignore()
            self.spin_liftoff_dist.editingFinished.connect(self.ao_concluir_edicao_spin_liftoff)
            coil_env_form.addRow("Distância Lift-Off (d):", self.spin_liftoff_dist)
    
            coil_env_layout.addLayout(coil_env_form)
    
            # Label com equação do cálculo automático de Lift-Off
            self.lbl_calculo_liftoff_info = QtWidgets.QLabel("Fórmula: d = (Espaçadores + 2.6 mm) - H_bobina")
            self.lbl_calculo_liftoff_info.setStyleSheet("color: #f1c40f; font-size: 8.5pt; font-family: monospace;")
            coil_env_layout.addWidget(self.lbl_calculo_liftoff_info)
    
            scroll_coil_layout.addWidget(group_coil_env)
    
            # 4. Seleção do Cupom / Amostra
            group_coil_coupon = QtWidgets.QGroupBox("Seleção do Cupom / Amostra")
            group_coil_coupon.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #3a3a3c;
                    border-radius: 4px;
                    margin-top: 12px;
                    font-weight: bold;
                    color: #26a69a;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 3px;
                }
                QCheckBox, QRadioButton {
                    color: #ffffff !important;
                    font-size: 8pt;
                    font-weight: bold;
                    spacing: 5px;
                }
                QCheckBox::indicator, QRadioButton::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1.5px solid #888888;
                    background-color: #222225;
                    border-radius: 3px;
                }
                QCheckBox::indicator:hover, QRadioButton::indicator:hover {
                    border: 1.5px solid #00e676;
                }
                QCheckBox::indicator:checked {
                    background-color: #00e676;
                    border: 1.5px solid #ffffff;
                }
            """)
            coil_coupon_layout = QtWidgets.QVBoxLayout(group_coil_coupon)
            coil_coupon_layout.setSpacing(8)
    
            coil_coupon_form = QtWidgets.QFormLayout()
            coil_coupon_form.setSpacing(6)
    
            # 1º Item: ID da Amostra (Limitado a no máximo 3 caracteres conforme o novo padrão)
            self.edit_coil_sample_id = QtWidgets.QLineEdit("1")
            self.edit_coil_sample_id.setMaxLength(3)
            self.edit_coil_sample_id.setToolTip("O ID da Amostra é limitado a no máximo 3 caracteres (ex: 001, 012, 100)")
            self.edit_coil_sample_id.textChanged.connect(self.ao_validar_limite_id_amostra)
            coil_coupon_form.addRow("ID da Amostra (Max 3):", self.edit_coil_sample_id)
            coil_coupon_form.addRow(criar_linha_separadora())
    
            # 2º Item: Cupom / Material por Checkboxes (Exclusivos)
            self.chk_materiais = {}
            self.group_materiais = QtWidgets.QButtonGroup(self)
            self.widget_mat_container = QtWidgets.QWidget()
            self.layout_mat_grid = QtWidgets.QGridLayout(self.widget_mat_container)
            self.layout_mat_grid.setContentsMargins(0, 0, 0, 0)
            self.layout_mat_grid.setSpacing(3)
            self.lista_widgets_materiais = []
    
            materiais_lista = self.carregar_lista_materiais()
            for idx_m, mat_nome in enumerate(materiais_lista):
                chk = QtWidgets.QCheckBox(mat_nome)
                self.chk_materiais[mat_nome] = chk
                self.group_materiais.addButton(chk)
                self.lista_widgets_materiais.append(chk)
                if idx_m == 0:
                    chk.setChecked(True)
                self.layout_mat_grid.addWidget(chk, idx_m // 3, idx_m % 3)
    
            coil_coupon_form.addRow("Cupom / Material:", self.widget_mat_container)
            self.group_materiais.buttonClicked.connect(self.ao_alterar_material_caracterizacao)
            coil_coupon_form.addRow(criar_linha_separadora())
    
            # 3º Item: Seleção de Estado de Corrosão por Checkboxes (Exclusivos)
            self.chk_classes = {}
            self.group_classes = QtWidgets.QButtonGroup(self)
            self.widget_cls_container = QtWidgets.QWidget()
            self.layout_cls_grid = QtWidgets.QGridLayout(self.widget_cls_container)
            self.layout_cls_grid.setContentsMargins(0, 0, 0, 0)
            self.layout_cls_grid.setSpacing(3)
            self.lista_widgets_classes = []
    
            classes_lista = ["Ar Livre", "Saudável", "Leve", "Moderada", "Avançada", "Corroído", "Não Definido"]
            for idx_c, cls_nome in enumerate(classes_lista):
                chk = QtWidgets.QCheckBox(cls_nome)
                self.chk_classes[cls_nome] = chk
                self.group_classes.addButton(chk)
                self.lista_widgets_classes.append(chk)
                if cls_nome == "Saudável":
                    chk.setChecked(True)
                self.layout_cls_grid.addWidget(chk, idx_c // 3, idx_c % 3)
    
            coil_coupon_form.addRow("Estado de Corrosão:", self.widget_cls_container)
            self.group_classes.buttonClicked.connect(self.ao_alterar_classe_caracterizacao)
            coil_coupon_form.addRow(criar_linha_separadora())
    
            # 4º Item: Checkboxes para Seleção do Local da Amostra (Exclusivos)
            self.chk_locais = {}
            self.group_locais = QtWidgets.QButtonGroup(self)
            self.group_locais.setExclusive(True)
            locais_opcoes = ["São Paulo", "Ceara", "Venancio", "Caxias", "Rosario", "Senai", "Branco"]
            self.widget_locais_container = QtWidgets.QWidget()
            self.layout_locais_grid = QtWidgets.QGridLayout(self.widget_locais_container)
            self.layout_locais_grid.setContentsMargins(0, 0, 0, 0)
            self.layout_locais_grid.setSpacing(3)
            self.lista_widgets_locais = []
            for idx_l, nome_l in enumerate(locais_opcoes):
                chk = QtWidgets.QCheckBox(nome_l)
                self.chk_locais[nome_l] = chk
                self.group_locais.addButton(chk)
                self.lista_widgets_locais.append(chk)
                if idx_l == 0:
                    chk.setChecked(True)
                self.layout_locais_grid.addWidget(chk, idx_l // 3, idx_l % 3)
    
            coil_coupon_form.addRow("Local da Amostra:", self.widget_locais_container)
            coil_coupon_layout.addLayout(coil_coupon_form)
    
            scroll_coil_layout.addWidget(group_coil_coupon)
    
            # 5. Botões de Gravação e Gerenciamento
            group_coil_actions = QtWidgets.QGroupBox("Ações & Gravação de Testes")
            group_coil_actions.setStyleSheet("""
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
                    padding: 0 3px;
                }
                QCheckBox, QRadioButton {
                    color: #ffffff !important;
                    font-size: 8pt;
                    font-weight: bold;
                    spacing: 5px;
                }
                QCheckBox::indicator, QRadioButton::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1.5px solid #888888;
                    background-color: #222225;
                    border-radius: 3px;
                }
                QCheckBox::indicator:hover, QRadioButton::indicator:hover {
                    border: 1.5px solid #00e676;
                }
                QCheckBox::indicator:checked {
                    background-color: #00e676;
                    border: 1.5px solid #ffffff;
                }
            """)
            coil_actions_layout = QtWidgets.QVBoxLayout(group_coil_actions)
            coil_actions_layout.setSpacing(8)
    
            lbl_num_amostras = QtWidgets.QLabel("Qtd Amostras / Arquivo:")
            lbl_num_amostras.setStyleSheet("color: #e1e1e6; font-weight: bold; font-size: 8.5pt;")
            coil_actions_layout.addWidget(lbl_num_amostras)
    
            self.chk_num_amostras = {}
            self.group_num_amostras = QtWidgets.QButtonGroup(self)
            self.widget_num_amostras_container = QtWidgets.QWidget()
            self.layout_num_amostras_grid = QtWidgets.QGridLayout(self.widget_num_amostras_container)
            self.layout_num_amostras_grid.setContentsMargins(0, 0, 0, 0)
            self.layout_num_amostras_grid.setSpacing(4)
            self.lista_widgets_num_amostras = []
    
            opcoes_amostras = [
                ("1 Amostra", 1),
                ("10 Amostras", 10),
                ("100 Amostras", 100),
                ("1000 Amostras", 1000)
            ]
    
            for idx_a, (label_a, val_a) in enumerate(opcoes_amostras):
                chk = QtWidgets.QCheckBox(label_a)
                chk.setProperty("val_n", val_a)
                self.chk_num_amostras[val_a] = chk
                self.group_num_amostras.addButton(chk)
                self.lista_widgets_num_amostras.append(chk)
                if val_a == 1:
                    chk.setChecked(True)
                self.layout_num_amostras_grid.addWidget(chk, idx_a // 3, idx_a % 3)
    
            coil_actions_layout.addWidget(self.widget_num_amostras_container)
    
            self.btn_record_coil_test = QtWidgets.QPushButton("Gravar Ensaio de Caracterização")
            self.btn_record_coil_test.setMinimumHeight(45)
            self.btn_record_coil_test.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 10pt;")
            self.btn_record_coil_test.clicked.connect(self.gravar_ensaio_caracterizacao)
            coil_actions_layout.addWidget(self.btn_record_coil_test)
    
            self.btn_import_coil_csvs = QtWidgets.QPushButton("Importar Testes CSV")
            self.btn_import_coil_csvs.setMinimumHeight(38)
            self.btn_import_coil_csvs.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; font-size: 10pt;")
            self.btn_import_coil_csvs.clicked.connect(self.importar_csvs_caracterizacao)
            coil_actions_layout.addWidget(self.btn_import_coil_csvs)
    
            self.btn_clear_coil_comparison = QtWidgets.QPushButton("Limpar Seleção / Gráficos")
            self.btn_clear_coil_comparison.setMinimumHeight(35)
            self.btn_clear_coil_comparison.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
            self.btn_clear_coil_comparison.clicked.connect(self.limpar_comparacao_bobinas)
            coil_actions_layout.addWidget(self.btn_clear_coil_comparison)
    
            self.btn_plot_3d_coils = QtWidgets.QPushButton("Visualizar Gráfico 3D (L x AUC x Distância)")
            self.btn_plot_3d_coils.setMinimumHeight(40)
            self.btn_plot_3d_coils.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold; font-size: 10pt;")
            self.btn_plot_3d_coils.clicked.connect(self.abrir_grafico_3d_caracterizacao)
            coil_actions_layout.addWidget(self.btn_plot_3d_coils)
    
            self.btn_export_coil_report = QtWidgets.QPushButton("Exportar Comparativo (PNG/HTML)")
            self.btn_export_coil_report.setMinimumHeight(35)
            self.btn_export_coil_report.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
            self.btn_export_coil_report.clicked.connect(self.exportar_relatorio_bobinas)
            coil_actions_layout.addWidget(self.btn_export_coil_report)
    
            scroll_coil_layout.addWidget(group_coil_actions)
    
            # 4. Lista de Arquivos de Teste Ativos
            group_coil_files = QtWidgets.QGroupBox("Arquivos de Teste Importados")
            group_coil_files.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #3a3a3c;
                    border-radius: 4px;
                    margin-top: 12px;
                    font-weight: bold;
                    color: #00e676;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 3px;
                }
            """)
            coil_files_layout = QtWidgets.QVBoxLayout(group_coil_files)
            self.list_imported_coil_files = QtWidgets.QListWidget()
            self.list_imported_coil_files.setStyleSheet("background-color: #121214; color: #e1e1e6; font-size: 9pt;")
            self.list_imported_coil_files.itemSelectionChanged.connect(self.atualizar_graficos_comparacao_bobinas)
            coil_files_layout.addWidget(self.list_imported_coil_files)
    
            scroll_coil_layout.addWidget(group_coil_files)

            # 5. Painel de Filtros de Exibição dos Gráficos
            group_coil_filters = QtWidgets.QGroupBox("Filtros de Exibição dos Gráficos")
            group_coil_filters_layout = QtWidgets.QGridLayout(group_coil_filters)
            group_coil_filters.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #3a3a3c;
                    border-radius: 4px;
                    margin-top: 12px;
                    font-weight: bold;
                    color: #00e676;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 3px;
                }
            """)

            lbl_f_mats = QtWidgets.QLabel("<b>Materiais:</b>")
            lbl_f_cls = QtWidgets.QLabel("<b>Classes:</b>")
            group_coil_filters_layout.addWidget(lbl_f_mats, 0, 0)
            group_coil_filters_layout.addWidget(lbl_f_cls, 0, 1)

            self.coil_filter_checkboxes_material = {}
            materiais_lista = self.carregar_lista_materiais()
            for idx_fm, mat_n in enumerate(materiais_lista):
                chk_m = QtWidgets.QCheckBox(mat_n)
                chk_m.setChecked(True)
                chk_m.setStyleSheet("font-size: 8.5pt; color: #e1e1e6;")
                chk_m.stateChanged.connect(self.atualizar_todos_graficos_caracterizacao)
                self.coil_filter_checkboxes_material[mat_n] = chk_m
                group_coil_filters_layout.addWidget(chk_m, idx_fm + 1, 0)

            self.chk_coil_filter_saudavel = QtWidgets.QCheckBox("Saudável")
            self.chk_coil_filter_saudavel.setChecked(True)
            self.chk_coil_filter_leve = QtWidgets.QCheckBox("Leve")
            self.chk_coil_filter_leve.setChecked(True)
            self.chk_coil_filter_moderada = QtWidgets.QCheckBox("Moderada")
            self.chk_coil_filter_moderada.setChecked(True)
            self.chk_coil_filter_avancada = QtWidgets.QCheckBox("Avançada")
            self.chk_coil_filter_avancada.setChecked(True)
            self.chk_coil_filter_corroido = QtWidgets.QCheckBox("Corroído")
            self.chk_coil_filter_corroido.setChecked(True)
            self.chk_coil_filter_ar_cls = QtWidgets.QCheckBox("Ar Livre")
            self.chk_coil_filter_ar_cls.setChecked(True)
            self.chk_coil_filter_nao_definido = QtWidgets.QCheckBox("Não Definido")
            self.chk_coil_filter_nao_definido.setChecked(True)

            cls_chks = [
                self.chk_coil_filter_saudavel, self.chk_coil_filter_leve,
                self.chk_coil_filter_moderada, self.chk_coil_filter_avancada,
                self.chk_coil_filter_corroido, self.chk_coil_filter_ar_cls,
                self.chk_coil_filter_nao_definido
            ]
            for idx_fc, chk_c in enumerate(cls_chks):
                chk_c.setStyleSheet("font-size: 8.5pt; color: #e1e1e6;")
                chk_c.stateChanged.connect(self.atualizar_todos_graficos_caracterizacao)
                group_coil_filters_layout.addWidget(chk_c, idx_fc + 1, 1)

            max_rows_f = max(len(materiais_lista), len(cls_chks)) + 1
            self.chk_coil_filter_outliers = QtWidgets.QCheckBox("Remover Outliers (IQR)")
            self.chk_coil_filter_outliers.setChecked(False)
            self.chk_coil_filter_outliers.stateChanged.connect(self.atualizar_todos_graficos_caracterizacao)
            group_coil_filters_layout.addWidget(self.chk_coil_filter_outliers, max_rows_f, 0, 1, 2)

            self.chk_diferenciar_ids_tonalidade = QtWidgets.QCheckBox("Diferenciar Tonalidades por ID")
            self.chk_diferenciar_ids_tonalidade.setToolTip("Altera a tonalidade (luminosidade HSL) dos pontos para diferenciar IDs de amostras distintos")
            self.chk_diferenciar_ids_tonalidade.setChecked(False)
            self.chk_diferenciar_ids_tonalidade.stateChanged.connect(self.atualizar_todos_graficos_caracterizacao)
            group_coil_filters_layout.addWidget(self.chk_diferenciar_ids_tonalidade, max_rows_f + 1, 0, 1, 2)

            self.chk_coil_enable_tooltips = QtWidgets.QCheckBox("Exibir Tooltips e Destaques Visuais")
            self.chk_coil_enable_tooltips.setToolTip("Habilita ou desabilita a exibição de destaques visuais e balões de tooltip flutuantes nos gráficos")
            self.chk_coil_enable_tooltips.setChecked(True)
            self.chk_coil_enable_tooltips.stateChanged.connect(self.ao_alternar_exibicao_tooltips)
            group_coil_filters_layout.addWidget(self.chk_coil_enable_tooltips, max_rows_f + 2, 0, 1, 2)

            self.chk_rt_exibir_tendencia = QtWidgets.QCheckBox("Exibir Sinal / Marcador de Tendência Estável (Tempo Real)")
            self.chk_rt_exibir_tendencia.setToolTip("Exibe o sinal suavizado e os marcadores de tendência estabilizados (média móvel) nos 4 gráficos de monitoramento em tempo real")
            self.chk_rt_exibir_tendencia.setChecked(True)
            self.chk_rt_exibir_tendencia.stateChanged.connect(self.ao_alternar_exibicao_tendencia_rt)
            group_coil_filters_layout.addWidget(self.chk_rt_exibir_tendencia, max_rows_f + 3, 0, 1, 2)

            # Controle de Nível de Estabilidade (Filtro Adaptativo Inteligente com Fast-Attack e Zero-Jitter Lock)
            box_ma = QtWidgets.QWidget()
            layout_ma = QtWidgets.QVBoxLayout(box_ma)
            layout_ma.setContentsMargins(0, 4, 0, 0)
            layout_ma.setSpacing(4)
            
            lbl_ma = QtWidgets.QLabel("Estabilidade da Tendência (Fast-Lock):")
            lbl_ma.setStyleSheet("color: #a0a0a0; font-size: 8.5pt; font-weight: bold;")
            
            layout_chks = QtWidgets.QHBoxLayout()
            layout_chks.setContentsMargins(0, 0, 0, 0)
            layout_chks.setSpacing(6)

            chk_ma_style = """
                QCheckBox {
                    color: #76ff03;
                    font-weight: bold;
                    font-size: 8.5pt;
                }
                QCheckBox::indicator {
                    width: 13px;
                    height: 13px;
                }
                QCheckBox::indicator:unchecked {
                    border: 1px solid #555555;
                    background: #1e1e1e;
                    border-radius: 3px;
                }
                QCheckBox::indicator:checked {
                    border: 1px solid #76ff03;
                    background: #76ff03;
                    border-radius: 3px;
                }
            """

            self.chk_ma_10 = QtWidgets.QCheckBox("10")
            self.chk_ma_50 = QtWidgets.QCheckBox("50")
            self.chk_ma_100 = QtWidgets.QCheckBox("100")
            self.chk_ma_1000 = QtWidgets.QCheckBox("1000")

            self.chk_ma_10.setToolTip("10 - Modo Rápido / Sensível (Deadband 0.8%): Resposta ultra-rápida com filtro adaptativo.")
            self.chk_ma_50.setToolTip("50 - Modo Equilibrado (Deadband 1.5%): Excelente equilíbrio entre resposta rápida e estabilização.")
            self.chk_ma_100.setToolTip("100 - Alta Estabilidade (Deadband 2.2%): Filtragem reforçada com resposta imediata a degraus.")
            self.chk_ma_1000.setToolTip("1000 - Travamento Total de Bancada (Deadband 3.5%): Elimina 100% de qualquer jitter/oscilação residual com convergência instantânea.")

            self.chk_ma_50.setChecked(True)

            for chk in [self.chk_ma_10, self.chk_ma_50, self.chk_ma_100, self.chk_ma_1000]:
                chk.setStyleSheet(chk_ma_style)
                chk.clicked.connect(self._on_ma_checkbox_clicked)
                layout_chks.addWidget(chk)
            
            layout_ma.addWidget(lbl_ma)
            layout_ma.addLayout(layout_chks)
            group_coil_filters_layout.addWidget(box_ma, max_rows_f + 4, 0, 1, 2)

            # Controle de Taxa de Atualização dos Sinais (Checkboxes: 0.5s, 1s, 2s, 5s, 10s)
            box_rate = QtWidgets.QWidget()
            layout_rate = QtWidgets.QVBoxLayout(box_rate)
            layout_rate.setContentsMargins(0, 6, 0, 0)
            layout_rate.setSpacing(4)
            
            lbl_rate = QtWidgets.QLabel("Taxa de Atualização dos Sinais:")
            lbl_rate.setStyleSheet("color: #a0a0a0; font-size: 8.5pt; font-weight: bold;")
            
            layout_rate_chks = QtWidgets.QHBoxLayout()
            layout_rate_chks.setContentsMargins(0, 0, 0, 0)
            layout_rate_chks.setSpacing(4)

            chk_rate_style = """
                QCheckBox {
                    color: #00e5ff;
                    font-weight: bold;
                    font-size: 8.5pt;
                }
                QCheckBox::indicator {
                    width: 13px;
                    height: 13px;
                }
                QCheckBox::indicator:unchecked {
                    border: 1px solid #555555;
                    background: #1e1e1e;
                    border-radius: 3px;
                }
                QCheckBox::indicator:checked {
                    border: 1px solid #00e5ff;
                    background: #00e5ff;
                    border-radius: 3px;
                }
            """

            self.chk_rate_05s = QtWidgets.QCheckBox("0.5s")
            self.chk_rate_1s = QtWidgets.QCheckBox("1s")
            self.chk_rate_2s = QtWidgets.QCheckBox("2s")
            self.chk_rate_5s = QtWidgets.QCheckBox("5s")
            self.chk_rate_10s = QtWidgets.QCheckBox("10s")
            self.chk_rate_samples = QtWidgets.QCheckBox("Por Lote (50 amostras)")

            self.chk_rate_05s.setToolTip("Atualiza os sinais e gráficos a cada 0,5 segundos (2 Hz).")
            self.chk_rate_1s.setToolTip("Atualiza os sinais e gráficos a cada 1,0 segundo (1 Hz).")
            self.chk_rate_2s.setToolTip("Atualiza os sinais e gráficos a cada 2,0 segundos (0,5 Hz).")
            self.chk_rate_5s.setToolTip("Atualiza os sinais e gráficos a cada 5,0 segundos.")
            self.chk_rate_10s.setToolTip("Atualiza os sinais e gráficos a cada 10,0 segundos.")
            self.chk_rate_samples.setToolTip("Atualiza a tendência somente após receber o lote completo de curvas selecionado na Estabilidade (10, 50, 100 ou 1000).")

            self.chk_rate_05s.setChecked(True)

            layout_rate_chks1 = QtWidgets.QHBoxLayout()
            layout_rate_chks1.setContentsMargins(0, 0, 0, 0)
            layout_rate_chks1.setSpacing(4)
            for chk in [self.chk_rate_05s, self.chk_rate_1s, self.chk_rate_2s, self.chk_rate_5s, self.chk_rate_10s]:
                chk.setStyleSheet(chk_rate_style)
                chk.clicked.connect(self._on_rate_checkbox_clicked)
                layout_rate_chks1.addWidget(chk)

            layout_rate_chks2 = QtWidgets.QHBoxLayout()
            layout_rate_chks2.setContentsMargins(0, 2, 0, 0)
            layout_rate_chks2.setSpacing(4)
            self.chk_rate_samples.setStyleSheet(chk_rate_style)
            self.chk_rate_samples.clicked.connect(self._on_rate_checkbox_clicked)
            layout_rate_chks2.addWidget(self.chk_rate_samples)
            layout_rate_chks2.addStretch()

            layout_rate.addWidget(lbl_rate)
            layout_rate.addLayout(layout_rate_chks1)
            layout_rate.addLayout(layout_rate_chks2)
            group_coil_filters_layout.addWidget(box_rate, max_rows_f + 5, 0, 1, 2)

            scroll_coil_layout.addWidget(group_coil_filters)

            # 6. Painel de Legenda / Índice dos Gráficos
            group_coil_legend = QtWidgets.QGroupBox("Legenda dos Gráficos (Índice)")
            group_coil_legend_layout = QtWidgets.QGridLayout(group_coil_legend)
            group_coil_legend.setStyleSheet("""
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
                    padding: 0 3px;
                }
                QLabel { font-size: 8.5pt; }
            """)

            lbl_f_hdr = QtWidgets.QLabel("<b>Formas (Materiais):</b>")
            group_coil_legend_layout.addWidget(lbl_f_hdr, 0, 0, 1, 2)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("<span style='font-size: 11pt;'>⚪</span> A36 Comum (Círculo)"), 1, 0)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("<span style='font-size: 11pt;'>⏹️</span> A36 GE - Galv. Eletrolítico (Quadrado)"), 1, 1)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("<span style='font-size: 11pt;'>🔶</span> A36 GF - Galv. a Fogo (Losango)"), 2, 0)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("<span style='font-size: 11pt;'>🔺</span> Estrutura Torre (Triângulo)"), 2, 1)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("<span style='font-size: 11pt;'>➕</span> Ar Livre (Cruz)"), 3, 0)

            lbl_c_hdr = QtWidgets.QLabel("<b>Cores (Degradação):</b>")
            group_coil_legend_layout.addWidget(lbl_c_hdr, 4, 0, 1, 2)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("🔵 Saudável"), 5, 0)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("🟢 Leve"), 5, 1)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("🟡 Moderada"), 6, 0)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("🟠 Avançada"), 6, 1)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("🔴 Corroído"), 7, 0)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("🟣 Ar Livre"), 7, 1)
            group_coil_legend_layout.addWidget(QtWidgets.QLabel("⚪ Não Definido"), 8, 0)

            scroll_coil_layout.addWidget(group_coil_legend)

            self.scroll_coil.setWidget(scroll_coil_content)
            coil_left_layout.addWidget(self.scroll_coil)
    
            # Sub-painel Direito: Container de Sub-Abas da Caracterização (Comparativos, Tempo Real, Estatística)
            coil_right = QtWidgets.QWidget()
            coil_right_layout = QtWidgets.QVBoxLayout(coil_right)
            coil_right_layout.setContentsMargins(0, 0, 0, 0)
            coil_right_layout.setSpacing(4)
    
            self.tab_sub_caracterizacao = QtWidgets.QTabWidget()
            self.tab_sub_caracterizacao.tabBar().setElideMode(QtCore.Qt.ElideNone)
            self.tab_sub_caracterizacao.tabBar().setUsesScrollButtons(True)
            self.tab_sub_caracterizacao.tabBar().setExpanding(False)
            self.tab_sub_caracterizacao.setStyleSheet("""
                QTabWidget::pane {
                    border: 1px solid #3a3a3c;
                    background-color: #121214;
                    border-radius: 4px;
                }
                QTabBar::tab {
                    background-color: #1e1e1f;
                    color: #a0a0a0;
                    padding: 8px 20px;
                    min-width: 170px;
                    margin-right: 4px;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                    font-weight: bold;
                    font-size: 9pt;
                }
                QTabBar::tab:selected {
                    background-color: #2c2c2e;
                    color: #00e676;
                    border-bottom: 2px solid #00e676;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #2a2a2c;
                    color: #ffffff;
                }
            """)
    
            # =====================================================================
            # SUB-ABA 1: Comparativos de Lift-Off & Bobinas (Visualização Atual)
            # =====================================================================
            subtab_comparativo = QtWidgets.QWidget()
            subtab_comp_layout = QtWidgets.QVBoxLayout(subtab_comparativo)
            subtab_comp_layout.setContentsMargins(2, 2, 2, 2)
            subtab_comp_layout.setSpacing(4)
    
            self.win_coil_plots = pg.GraphicsLayoutWidget()
            self.win_coil_plots.setBackground('#121214')
            self.win_coil_plots.scene().sigMouseMoved.connect(self.ao_mover_mouse_grafico_caracterizacao)
            self.win_coil_plots.scene().sigMouseClicked.connect(self.ao_clicar_mouse_grafico)
    
            subtab_comp_layout.addWidget(self.criar_barrafullscreen_container(self.win_coil_plots, "Sub-Aba 1: Comparativos de Lift-Off"))
            subtab_comp_layout.addWidget(self.win_coil_plots, 2)

            self.plot_coil_decay = self.win_coil_plots.addPlot(row=0, col=0, title="Decaimento Transiente Comparativo V(t)")
            self.plot_coil_decay.setLabel('left', 'Tensão / ADC Counts')
            self.plot_coil_decay.setLabel('bottom', 'Tempo (us)')
            self.plot_coil_decay.showGrid(x=True, y=True, alpha=0.3)
    
            self.plot_coil_tau_liftoff = self.win_coil_plots.addPlot(row=0, col=1, title="Constante de Tempo (Tau) vs Distância (Lift-Off)")
            self.plot_coil_tau_liftoff.setLabel('left', 'Tau (us)')
            self.plot_coil_tau_liftoff.setLabel('bottom', 'Distância (mm)')
            self.plot_coil_tau_liftoff.showGrid(x=True, y=True, alpha=0.3)
    
            self.plot_coil_auc_liftoff = self.win_coil_plots.addPlot(row=1, col=0, title="Área Sob a Curva (AUC) vs Distância (Lift-Off)")
            self.plot_coil_auc_liftoff.setLabel('left', 'AUC (Counts.us)')
            self.plot_coil_auc_liftoff.setLabel('bottom', 'Distância (mm)')
            self.plot_coil_auc_liftoff.showGrid(x=True, y=True, alpha=0.3)
    
            self.plot_coil_l_liftoff = self.win_coil_plots.addPlot(row=1, col=1, title="Indutância Efetiva L vs Distância (Lift-Off)")
            self.plot_coil_l_liftoff.setLabel('left', 'Indutância L (uH)')
            self.plot_coil_l_liftoff.setLabel('bottom', 'Distância (mm)')
            self.plot_coil_l_liftoff.showGrid(x=True, y=True, alpha=0.3)
    
            self.txt_coil_report = QtWidgets.QTextEdit()
            self.txt_coil_report.setReadOnly(True)
            self.txt_coil_report.setMaximumHeight(160)
            self.txt_coil_report.setStyleSheet("""
                QTextEdit {
                    background-color: #0c0c0d; color: #00ff00;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 9.5pt; border: 1px solid #3a3a3c; border-radius: 4px; padding: 6px;
                }
            """)
            subtab_comp_layout.addWidget(self.txt_coil_report, 1)
            self.tab_sub_caracterizacao.addTab(subtab_comparativo, "Comparativos de Lift-Off")
    
            # =====================================================================
            # SUB-ABA 2: Monitoramento em Tempo Real & Diagnóstico do Sensor
            # =====================================================================
            subtab_realtime = QtWidgets.QWidget()
            subtab_rt_layout = QtWidgets.QVBoxLayout(subtab_realtime)
            subtab_rt_layout.setContentsMargins(2, 2, 2, 2)
            subtab_rt_layout.setSpacing(4)
    
            self.win_coil_rt_plots = pg.GraphicsLayoutWidget()
            self.win_coil_rt_plots.setBackground('#121214')
            self.win_coil_rt_plots.scene().sigMouseMoved.connect(self.ao_mover_mouse_grafico_rt_caracterizacao)
            self.win_coil_rt_plots.scene().sigMouseClicked.connect(self.ao_clicar_mouse_grafico)

            self.plot_coil_rt_decay = self.win_coil_rt_plots.addPlot(row=0, col=0, title="Sinais de Decaimento V(t) (Histórico CSV + Live Verde Neon)")
            self.plot_coil_rt_decay.setLabel('left', 'ADC Counts')
            self.plot_coil_rt_decay.setLabel('bottom', 'Tempo (us)')
            self.plot_coil_rt_decay.showGrid(x=True, y=True, alpha=0.3)

            # Apelidos para compatibilidade retroativa
            self.plot_coil_rt_live = self.plot_coil_rt_decay
            self.plot_coil_rt_overlay = self.plot_coil_rt_decay

            self.plot_coil_rt_tau = self.win_coil_rt_plots.addPlot(row=0, col=1, title="Distribuição da Constante de Tempo (Tau) + Indicador Live")
            self.plot_coil_rt_tau.setLabel('left', 'Tau (us)')
            self.plot_coil_rt_tau.setLabel('bottom', 'Lift-Off (mm)')
            self.plot_coil_rt_tau.showGrid(x=True, y=True, alpha=0.3)

            self.plot_coil_rt_auc = self.win_coil_rt_plots.addPlot(row=1, col=0, title="Distribuição da Área sob a Curva (AUC) + Indicador Live")
            self.plot_coil_rt_auc.setLabel('left', 'AUC (Counts.us)')
            self.plot_coil_rt_auc.setLabel('bottom', 'Lift-Off (mm)')
            self.plot_coil_rt_auc.showGrid(x=True, y=True, alpha=0.3)

            self.plot_coil_rt_scatter = self.win_coil_rt_plots.addPlot(row=1, col=1, title="Espaço de Características (AUC vs Tau) + Indicador Live")
            self.plot_coil_rt_scatter.setLabel('left', 'AUC (Counts.us)')
            self.plot_coil_rt_scatter.setLabel('bottom', 'Tau (us)')
            self.plot_coil_rt_scatter.showGrid(x=True, y=True, alpha=0.3)

            subtab_rt_layout.addWidget(self.criar_barrafullscreen_container(self.win_coil_rt_plots, "Sub-Aba 2: Monitoramento em Tempo Real do Sensor"))
            subtab_rt_layout.addWidget(self.win_coil_rt_plots, 3)
    
            self.txt_coil_rt_report = QtWidgets.QTextEdit()
            self.txt_coil_rt_report.setReadOnly(True)
            self.txt_coil_rt_report.setMaximumHeight(160)
            self.txt_coil_rt_report.setStyleSheet("""
                QTextEdit {
                    background-color: #0c0c0d; color: #29b6f6;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 9.5pt; border: 1px solid #3a3a3c; border-radius: 4px; padding: 6px;
                }
            """)
            subtab_rt_layout.addWidget(self.txt_coil_rt_report, 1)
            self.tab_sub_caracterizacao.addTab(subtab_realtime, "Monitoramento Tempo Real")
    
            # =====================================================================
            # SUB-ABA 3: Análise Estatística de Caracterização
            # =====================================================================
            subtab_stats = QtWidgets.QWidget()
            subtab_st_layout = QtWidgets.QVBoxLayout(subtab_stats)
            subtab_st_layout.setContentsMargins(2, 2, 2, 2)
            subtab_st_layout.setSpacing(4)
    
            self.win_coil_st_plots = pg.GraphicsLayoutWidget()
            self.win_coil_st_plots.setBackground('#121214')
            self.win_coil_st_plots.scene().sigMouseMoved.connect(self.ao_mover_mouse_grafico_estatistico_caracterizacao)
            self.win_coil_st_plots.scene().sigMouseClicked.connect(self.ao_clicar_mouse_grafico)
            subtab_st_layout.addWidget(self.criar_barrafullscreen_container(self.win_coil_st_plots, "Sub-Aba 3: Análise Estatística de Caracterização"))
            subtab_st_layout.addWidget(self.win_coil_st_plots, 2)
    
            self.plot_coil_st_decay = self.win_coil_st_plots.addPlot(row=0, col=0, title="Sinais Médios de Decaimento (Média ± DP)")
            self.plot_coil_st_decay.setLabel('left', 'Tensão / ADC Counts')
            self.plot_coil_st_decay.setLabel('bottom', 'Tempo (us)')
            self.plot_coil_st_decay.showGrid(x=True, y=True, alpha=0.3)
    
            self.plot_coil_st_tau = self.win_coil_st_plots.addPlot(row=0, col=1, title="Distribuição da Constante de Tempo (Tau)")
            self.plot_coil_st_tau.setLabel('left', 'Tau (us)')
            self.plot_coil_st_tau.setLabel('bottom', 'Lift-Off (mm)')
            self.plot_coil_st_tau.showGrid(x=True, y=True, alpha=0.3)
    
            self.plot_coil_st_auc = self.win_coil_st_plots.addPlot(row=1, col=0, title="Distribuição da Área sob a Curva (AUC)")
            self.plot_coil_st_auc.setLabel('left', 'AUC (Counts.us)')
            self.plot_coil_st_auc.setLabel('bottom', 'Lift-Off (mm)')
            self.plot_coil_st_auc.showGrid(x=True, y=True, alpha=0.3)
    
            self.plot_coil_st_scatter = self.win_coil_st_plots.addPlot(row=1, col=1, title="Espaço de Características: AUC vs Tau")
            self.plot_coil_st_scatter.setLabel('left', 'AUC (Counts.us)')
            self.plot_coil_st_scatter.setLabel('bottom', 'Tau (us)')
            self.plot_coil_st_scatter.showGrid(x=True, y=True, alpha=0.3)
    
            self.txt_coil_st_report = QtWidgets.QTextEdit()
            self.txt_coil_st_report.setReadOnly(True)
            self.txt_coil_st_report.setMaximumHeight(160)
            self.txt_coil_st_report.setStyleSheet("""
                QTextEdit {
                    background-color: #0c0c0d; color: #f1c40f;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 9.5pt; border: 1px solid #3a3a3c; border-radius: 4px; padding: 6px;
                }
            """)
            subtab_st_layout.addWidget(self.txt_coil_st_report, 1)
            self.tab_sub_caracterizacao.addTab(subtab_stats, "Análise Estatística")
    
            coil_right_layout.addWidget(self.tab_sub_caracterizacao)
            self.tab_sub_caracterizacao.currentChanged.connect(self.ao_mudar_subaba_caracterizacao)
    
            self.splitter_tab_coil.addWidget(coil_left)
            self.splitter_tab_coil.addWidget(coil_right)
            self.splitter_tab_coil.setSizes([380, 1000])
            self.splitter_tab_coil.splitterMoved.connect(self.reorganizar_colunas_seletores_caracterizacao)
    
            tab_coil_outer_layout.addWidget(self.splitter_tab_coil, 1)

            if self.mode == "coil":
                outer_layout.addWidget(self.tab_coil_char, 1)

        # Conecta sinal de mudança de aba
        self.tab_widget.currentChanged.connect(self.ao_mudar_aba)
        
        # Variáveis para armazenar referências das curvas de banco de dados plotadas na Aba 4
        self.diag_active_curve = None
        self.diag_active_scatter = None
        self.diag_active_auc_line = None
        self.diag_active_tau_line = None
        
        # Reconstrói a lista dinâmica de materiais e de bobinas no início
        self.atualizar_widgets_materiais()
        if hasattr(self, 'widget_radio_bobinas_container'):
            self.atualizar_lista_radio_bobinas()
            self.reorganizar_colunas_seletores_caracterizacao()

        # Aplica botões e menus de expansão em tela cheia para cada gráfico individualmente
        self.aplicar_tela_cheia_todos_graficos_individuais()

    def abrir_container_tela_cheia(self, container_widget, title="Gráficos em Tela Cheia"):
        if not container_widget:
            return
        orig_parent = container_widget.parentWidget()
        dialog = FullScreenContainerDialog(container_widget, orig_parent, title=title, parent=self)
        dialog.exec_()

    def abrir_plot_individual_tela_cheia(self, plot_item, container_win, title="Gráfico Individual"):
        if not plot_item or not container_win:
            return
        t_str = title if title else (plot_item.titleLabel.text if hasattr(plot_item, 'titleLabel') and plot_item.titleLabel and plot_item.titleLabel.text else "Gráfico Individual")

        # Coleta todos os PlotItems presentes no container
        todos_plots = []
        if hasattr(container_win, 'ci') and hasattr(container_win.ci, 'items'):
            for item in list(container_win.ci.items.keys()):
                if isinstance(item, pg.PlotItem):
                    todos_plots.append(item)

        # Oculta os outros plots temporariamente para que plot_item ocupe 100% da grade
        for p in todos_plots:
            if p != plot_item:
                p.setVisible(False)

        orig_parent = container_win.parentWidget()
        dialog = FullScreenContainerDialog(container_win, orig_parent, title=f"🔍 {t_str}", parent=self)

        def restaurar_visibilidade_plots():
            for p in todos_plots:
                p.setVisible(True)
                p.show()
            try:
                if hasattr(container_win, 'ci') and hasattr(container_win.ci, 'layout'):
                    container_win.ci.layout.activate()
                    container_win.ci.layout.update()
            except Exception:
                pass
            container_win.update()
            container_win.repaint()

        dialog.finished.connect(restaurar_visibilidade_plots)
        dialog.exec_()
        restaurar_visibilidade_plots()

    def configurar_expansao_grafico_individual(self, plot_item, container_win, title=None):
        if not plot_item or not container_win:
            return
        t_str = title if title else (plot_item.titleLabel.text if hasattr(plot_item, 'titleLabel') and plot_item.titleLabel and plot_item.titleLabel.text else "Gráfico")

        # 1. Adiciona botão mini '⛶' na barra de título do gráfico
        try:
            btn = QtWidgets.QPushButton("⛶")
            btn.setFixedSize(24, 24)
            btn.setToolTip(f"Expandir Apenas este Gráfico ({t_str}) em Tela Cheia")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b; color: #00e676; border: 1px solid #00e676;
                    border-radius: 3px; font-weight: bold; font-size: 10pt; padding: 0px;
                }
                QPushButton:hover {
                    background-color: #00e676; color: #000000; border: 1px solid #ffffff;
                }
            """)
            btn.clicked.connect(lambda: self.abrir_plot_individual_tela_cheia(plot_item, container_win, t_str))

            proxy = QtWidgets.QGraphicsProxyWidget()
            proxy.setWidget(btn)
            plot_item.layout.addItem(proxy, 0, 2)
        except Exception:
            pass

        # 2. Adiciona item de menu de contexto (clique com botão direito)
        try:
            vb_menu = plot_item.getViewBox().menu
            if vb_menu:
                act = QtWidgets.QAction(f"🔍 Expandir Apenas Este Gráfico em Tela Cheia", self)
                act.triggered.connect(lambda: self.abrir_plot_individual_tela_cheia(plot_item, container_win, t_str))
                vb_menu.addAction(act)
        except Exception:
            pass

    def aplicar_tela_cheia_todos_graficos_individuais(self):
        # Módulo 1 Aba 1
        if hasattr(self, 'win_plots'):
            if hasattr(self, 'plot_bruto'): self.configurar_expansao_grafico_individual(self.plot_bruto, self.win_plots)
            if hasattr(self, 'plot_decay'): self.configurar_expansao_grafico_individual(self.plot_decay, self.win_plots)
            if hasattr(self, 'plot_trend'): self.configurar_expansao_grafico_individual(self.plot_trend, self.win_plots)

        # Módulo 1 Aba 2
        if hasattr(self, 'win_stats_plots'):
            if hasattr(self, 'plot_stat_curves'): self.configurar_expansao_grafico_individual(self.plot_stat_curves, self.win_stats_plots)
            if hasattr(self, 'plot_stat_auc'): self.configurar_expansao_grafico_individual(self.plot_stat_auc, self.win_stats_plots)
            if hasattr(self, 'plot_stat_tau'): self.configurar_expansao_grafico_individual(self.plot_stat_tau, self.win_stats_plots)
            if hasattr(self, 'plot_stat_scatter'): self.configurar_expansao_grafico_individual(self.plot_stat_scatter, self.win_stats_plots)

        # Módulo 1 Aba 4
        if hasattr(self, 'win_diag_plots'):
            if hasattr(self, 'plot_diag_curves'): self.configurar_expansao_grafico_individual(self.plot_diag_curves, self.win_diag_plots)
            if hasattr(self, 'plot_diag_auc'): self.configurar_expansao_grafico_individual(self.plot_diag_auc, self.win_diag_plots)
            if hasattr(self, 'plot_diag_tau'): self.configurar_expansao_grafico_individual(self.plot_diag_tau, self.win_diag_plots)
            if hasattr(self, 'plot_diag_scatter'): self.configurar_expansao_grafico_individual(self.plot_diag_scatter, self.win_diag_plots)

        # Módulo 2 Sub-Aba 1
        if hasattr(self, 'win_coil_plots'):
            if hasattr(self, 'plot_coil_decay'): self.configurar_expansao_grafico_individual(self.plot_coil_decay, self.win_coil_plots)
            if hasattr(self, 'plot_coil_tau_liftoff'): self.configurar_expansao_grafico_individual(self.plot_coil_tau_liftoff, self.win_coil_plots)
            if hasattr(self, 'plot_coil_auc_liftoff'): self.configurar_expansao_grafico_individual(self.plot_coil_auc_liftoff, self.win_coil_plots)
            if hasattr(self, 'plot_coil_l_liftoff'): self.configurar_expansao_grafico_individual(self.plot_coil_l_liftoff, self.win_coil_plots)

        # Módulo 2 Sub-Aba 2
        if hasattr(self, 'win_coil_rt_plots'):
            if hasattr(self, 'plot_coil_rt_decay'): self.configurar_expansao_grafico_individual(self.plot_coil_rt_decay, self.win_coil_rt_plots)
            if hasattr(self, 'plot_coil_rt_tau'): self.configurar_expansao_grafico_individual(self.plot_coil_rt_tau, self.win_coil_rt_plots)
            if hasattr(self, 'plot_coil_rt_auc'): self.configurar_expansao_grafico_individual(self.plot_coil_rt_auc, self.win_coil_rt_plots)
            if hasattr(self, 'plot_coil_rt_scatter'): self.configurar_expansao_grafico_individual(self.plot_coil_rt_scatter, self.win_coil_rt_plots)

        # Módulo 2 Sub-Aba 3
        if hasattr(self, 'win_coil_st_plots'):
            if hasattr(self, 'plot_coil_st_decay'): self.configurar_expansao_grafico_individual(self.plot_coil_st_decay, self.win_coil_st_plots)
            if hasattr(self, 'plot_coil_st_tau'): self.configurar_expansao_grafico_individual(self.plot_coil_st_tau, self.win_coil_st_plots)
            if hasattr(self, 'plot_coil_st_auc'): self.configurar_expansao_grafico_individual(self.plot_coil_st_auc, self.win_coil_st_plots)
            if hasattr(self, 'plot_coil_st_scatter'): self.configurar_expansao_grafico_individual(self.plot_coil_st_scatter, self.win_coil_st_plots)

    def criar_barrafullscreen_container(self, container_widget, title="Painel de Gráficos"):
        header_w = QtWidgets.QWidget()
        header_l = QtWidgets.QHBoxLayout(header_w)
        header_l.setContentsMargins(4, 2, 4, 2)

        lbl = QtWidgets.QLabel(f"<b>{title}</b>")
        lbl.setStyleSheet("color: #00e676; font-size: 9.5pt;")
        header_l.addWidget(lbl)
        header_l.addStretch()

        btn = QtWidgets.QPushButton("⛶ Expandir Gráficos em Tela Cheia")
        btn.setMinimumHeight(28)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #00e676; border: 1px solid #00e676;
                border-radius: 4px; font-weight: bold; font-size: 9pt; padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #00e676; color: #000000; border: 1px solid #ffffff;
            }
        """)
        btn.clicked.connect(lambda: self.abrir_container_tela_cheia(container_widget, title))
        header_l.addWidget(btn)

        # Adiciona atalho de duplo clique no container gráfico
        if hasattr(container_widget, 'scene') and callable(container_widget.scene):
            try:
                old_dbl = container_widget.scene().mouseDoubleClickEvent
                def dbl_handler(ev):
                    self.abrir_container_tela_cheia(container_widget, title)
                    if old_dbl:
                        try: old_dbl(ev)
                        except Exception: pass
                container_widget.scene().mouseDoubleClickEvent = dbl_handler
            except Exception:
                pass

        return header_w

    def voltar_ao_menu_principal(self):
        if hasattr(self, 'serial_thread') and self.serial_thread and self.serial_thread.running:
            if hasattr(self, 'chk_auto_trigger'):
                self.chk_auto_trigger.setChecked(False)
            self.serial_thread.desconectar()
        if self.launcher:
            self.hide()
            self.launcher.show()
            self.launcher.raise_()
            self.launcher.activateWindow()

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
        amostras_limpas = self.dataset_manager.filtrar_outliers_iqr(self.amostras_estatisticas)
        
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
        diag_dt = primeira_amostra["dt_us"] if (primeira_amostra and "dt_us" in primeira_amostra) else 0.21875
        self.fator_diag, self.unid_diag = self.obter_unidade_tempo(diag_dt)
        fator_diag = self.fator_diag
        unid_diag = self.unid_diag

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

    def showEvent(self, event):
        super().showEvent(event)
        self.atualizar_status_conexao_ui()

    def atualizar_status_conexao_ui(self):
        if not hasattr(self, 'btn_conectar') or not hasattr(self, 'lbl_status_conn'):
            return
        if hasattr(self, 'serial_thread') and self.serial_thread.running:
            port_str = getattr(self.serial_thread, 'port_name', 'Ativa')
            self.lbl_status_conn.setText(f"Status: Conectado ({port_str})")
            self.lbl_status_conn.setStyleSheet("color: #2ecc71; font-weight: bold;")
            self.btn_conectar.setText("Desconectar")
            self.btn_conectar.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        else:
            self.lbl_status_conn.setText("Status: Desconectado")
            self.lbl_status_conn.setStyleSheet("color: #e74c3c; font-weight: bold;")
            self.btn_conectar.setText("Conectar")
            self.btn_conectar.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")

    # =====================================================================
    # LÓGICA DE GERENCIAMENTO DE CONEXÃO
    # =====================================================================
    def atualizar_portas_disponiveis(self):
        if not hasattr(self, 'combo_portas'):
            return
        self.combo_portas.clear()
        portas = [p.device for p in serial.tools.list_ports.comports()]
        self.combo_portas.addItems(portas)

    def auto_detectar_e_conectar(self):
        if not hasattr(self, 'combo_portas'):
            return
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
            porta = self.combo_portas.currentText() if hasattr(self, 'combo_portas') else None
            baud = int(self.combo_baud.currentText()) if hasattr(self, 'combo_baud') else 115200
            if not porta:
                QtWidgets.QMessageBox.warning(self, "Sem portas", "Nenhuma porta COM ativa encontrada!")
                return
            
            self.serial_thread.conectar(porta, baud)
            self.atualizar_status_conexao_ui()
            
            # Envia a configuração de frequência síncrona padrão/atual 100ms após conectar (para dar tempo da serial iniciar)
            if hasattr(self, 'spin_freq'):
                QtCore.QTimer.singleShot(100, lambda: self.atualizar_frequencia_disparo(self.spin_freq.value()))
            # Envia a configuração de dt síncrona inicial 150ms após conectar
            if hasattr(self, 'spin_dt'):
                QtCore.QTimer.singleShot(150, lambda: self.serial_thread.enviar_config_dt(int(self.spin_dt.value() * 1000)))
        else:
            if hasattr(self, 'chk_auto_trigger'):
                self.chk_auto_trigger.setChecked(False) # Desativa auto-trigger antes de desligar
            self.serial_thread.desconectar()
            self.atualizar_status_conexao_ui()

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
        self.capturar_uma_curva = True
        self.serial_thread.enviar_comando(b't') # Envia comando de trigger único para a placa

    def solicitar_leitura_automatica(self):
        # Desativado: o firmware controla a frequência e envia autonomamente
        pass

    def alternar_auto_trigger(self, state):
        if state == QtCore.Qt.Checked:
            if not self.serial_thread.running:
                QtWidgets.QMessageBox.warning(self, "Sem conexão", "Conecte na porta serial primeiro!")
                self.chk_auto_trigger.setChecked(False)
                return
            self.btn_single_trigger.setEnabled(False)
            self.leitura_ativa = True
            self.serial_thread.enviar_comando(b'r') # Envia comando de "Resume" para começar a aquisição contínua
            if hasattr(self, 'btn_diag_trigger'):
                self.btn_diag_trigger.setText("Pausar Diagnóstico")
                self.btn_diag_trigger.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; font-size: 11pt; border-radius: 4px;")
        else:
            self.btn_single_trigger.setEnabled(True)
            self.leitura_ativa = False
            if self.serial_thread.running:
                self.serial_thread.enviar_comando(b'p') # Envia comando de "Pause" para parar a aquisição contínua
            if hasattr(self, 'btn_diag_trigger'):
                self.btn_diag_trigger.setText("Iniciar Diagnóstico")
                self.btn_diag_trigger.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 11pt; border-radius: 4px;")



    def atualizar_frequencia_disparo(self, value):
        # Converte frequência (Hz) em período (ms)
        period_ms = int(1000 / value)
        # Garante limites válidos no lado da GUI
        period_ms = max(5, min(250, period_ms))
        if self.serial_thread.running:
            self.serial_thread.enviar_config_frequencia(period_ms)

    def atualizar_dt_us(self, value):
        # Envia a nova configuração de dt físico para a placa se conectado
        if self.serial_thread.running:
            self.serial_thread.enviar_config_dt(int(value * 1000))
            
        # Re-treina o classificador para recalcular as constantes no novo intervalo dt
        self.treinar_classificador()
        # Atualiza o rótulo do eixo X para refletir a taxa real configurada
        khz = 1000.0 / value if value > 0 else 0
        self.plot_decay.setLabel('bottom', f'Tempo (Modo DMA - {khz:.2f} kHz)', 'us')

    def ao_alterar_filtro_media_movel(self, state):
        # Limpa cache de estatísticas para forçar releitura do CSV com a nova máscara de filtro
        self.amostras_estatisticas = []
        
        # Re-treina o classificador com o filtro correspondente
        self.treinar_classificador()
        
        # Se estiver na aba de diagnóstico, força recálculo e plotagem
        if self.tab_widget.currentIndex() == 3:
            self.rodar_analise_estatistica()
            self.inicializar_graficos_diagnostico()

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
        # Limpa o cache de amostras estatísticas para forçar recarga nos gráficos de diagnóstico e estatísticas
        self.amostras_estatisticas = []
        
        # 1. Se estiver rodando e em modo de leitura ativa, pausa a placa temporariamente
        placa_estava_ativa = False
        if hasattr(self, 'serial_thread') and self.serial_thread.running:
            if self.leitura_ativa:
                placa_estava_ativa = True
                self.serial_thread.enviar_comando(b'p')
                time.sleep(0.02) # Espera 20ms para a placa receber e pausar
                # Esvazia buffer serial para descartar pacotes obsoletos
                if self.serial_thread.ser:
                    try:
                        self.serial_thread.ser.reset_input_buffer()
                    except Exception:
                        pass

        self.centroids = {}
        if not os.path.exists(self.arquivo_csv):
            if placa_estava_ativa and self.serial_thread.running:
                self.serial_thread.enviar_comando(b'r')
            return
        
        try:
            # Obtém amostras do gerenciador com cache
            amostras = self.dataset_manager.get_records(self.arquivo_csv)
            if not amostras:
                if placa_estava_ativa and self.serial_thread.running:
                    self.serial_thread.enviar_comando(b'r')
                return
                
            # Filtra dinamicamente os dados do banco para casar com o filtro temporal ativo na UI
            usa_filtro = self.chk_salvar_media_movel.isChecked() if hasattr(self, 'chk_salvar_media_movel') else False
            pontos = []
            for a in amostras:
                if a['is_filtered'] == usa_filtro:
                    pontos.append((a['material'], a['classe'], a['tau'], a['auc']))
                    
            if len(pontos) < 3:
                # Fallback: se não houver amostras suficientes para a opção selecionada, usa todas as amostras disponíveis
                pontos = [(a['material'], a['classe'], a['tau'], a['auc']) for a in amostras]
                
            if len(pontos) < 3:
                if placa_estava_ativa and self.serial_thread.running:
                    self.serial_thread.enviar_comando(b'r')
                return
                
            # Agrupa pontos por material e classe para remoção de outliers usando IQR
            amostras_temp = [{'material': p[0], 'classe': p[1], 'tau': p[2], 'auc': p[3]} for p in pontos]
            amostras_filtradas = self.dataset_manager.filtrar_outliers_iqr(amostras_temp)
            
            if len(amostras_filtradas) < 3:
                amostras_filtradas = amostras_temp
                
            taus_limpos = [p['tau'] for p in amostras_filtradas]
            aucs_limpos = [p['auc'] for p in amostras_filtradas]
            
            self.tau_min = np.min(taus_limpos)
            self.tau_max = np.max(taus_limpos)
            self.auc_min = np.min(aucs_limpos)
            self.auc_max = np.max(aucs_limpos)
            
            self.tau_range = (self.tau_max - self.tau_min) if (self.tau_max - self.tau_min) > 0 else 1.0
            self.auc_range = (self.auc_max - self.auc_min) if (self.auc_max - self.auc_min) > 0 else 1.0
            
            # Recalcula centroides com os pontos limpos
            grupos_limpos = {}
            for p in amostras_filtradas:
                key = (p['material'], p['classe'])
                if key not in grupos_limpos:
                    grupos_limpos[key] = []
                grupos_limpos[key].append((p['tau'], p['auc']))
                
            for key, vals in grupos_limpos.items():
                mean_tau = np.mean([v[0] for v in vals])
                mean_auc = np.mean([v[1] for v in vals])
                self.centroids[key] = (mean_tau, mean_auc)
                
            print(f"[CLASSIFICADOR] Treinado com {len(self.centroids)} classes a partir do CSV (com cache).")
        except Exception as e:
            print(f"[CLASSIFICADOR] Erro ao treinar: {e}")
        finally:
            # 2. Se a placa estava ativa antes, retoma a leitura
            if placa_estava_ativa and hasattr(self, 'serial_thread') and self.serial_thread.running:
                # Esvazia buffer antes de retomar para evitar dados corrompidos
                if self.serial_thread.ser:
                    try:
                        self.serial_thread.ser.reset_input_buffer()
                    except Exception:
                        pass
                self.serial_thread.enviar_comando(b'r')

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

    def processar_nova_curva(self, valores, elapsed_cycles=0):
        if not self.leitura_ativa and not self.capturar_uma_curva:
            return
        # Se houver uma janela modal (QMessageBox, QFileDialog) aberta na tela, interrompe o processamento de visualização instantâneo para evitar reentrada do evento Qt e congelamento do GUI
        if QtWidgets.QApplication.activeModalWidget() is not None:
            return
        if self.capturar_uma_curva:
            self.capturar_uma_curva = False

        # Atualiza dinamicamente o dt_us baseado nos ciclos medidos pelo DWT (se recebido)
        if elapsed_cycles > 0:
            dt = (elapsed_cycles / 480.0) / 256.0
            khz = 1000.0 / dt if dt > 0 else 0
            if hasattr(self, 'lbl_dt_medido'):
                self.lbl_dt_medido.setText(f"dt Real Medido: {dt:.5f} μs ({khz:.2f} kHz)")
            self.dt_us = dt

        # Se a suavização de transiente estiver ativa, aplica média móvel ponto a ponto na curva
        if hasattr(self, 'chk_filtrar_curva') and self.chk_filtrar_curva.isChecked() and hasattr(self, 'spin_janela_curva'):
            valores_processados = self.suavizar_curva(valores, self.spin_janela_curva.value())
        else:
            valores_processados = valores

        self.last_valores = valores_processados
        self.recent_curves.append(valores_processados)

        # Atualiza self.tempo_us e self.tensao_mv para visualização em tempo real
        self.tempo_us = np.arange(len(valores_processados)) * self.dt_us
        self.tensao_mv = valores_processados

        # Alimenta o buffer de acumulação para o cálculo da tendência periódica do Módulo 2
        if not hasattr(self, '_rt_trend_buffer') or self._rt_trend_buffer is None:
            self._rt_trend_buffer = []
        self._rt_trend_buffer.append(np.array(valores_processados, dtype=float))
        if len(self._rt_trend_buffer) > 2000:
            self._rt_trend_buffer = self._rt_trend_buffer[-2000:]

        # Coleta de multi-amostras em tempo real para a 5ª Aba (Caracterização de Bobinas)
        if getattr(self, 'is_recording_coil_multisample', False):
            self.coil_recording_buffer.append(list(valores_processados))
            cur_count = len(self.coil_recording_buffer)
            target_count = getattr(self, 'coil_recording_target_n', 1)
            if hasattr(self, 'btn_record_coil_test'):
                self.btn_record_coil_test.setText(f"⏳ Coletando ({cur_count} / {target_count} amostras)...")
            
            if cur_count >= target_count:
                self.is_recording_coil_multisample = False
                self.finalizar_gravacao_multiamostras_caracterizacao()
        
        # Determina a curva a ser usada para a IA e o cálculo dos gráficos de decaimento
        if hasattr(self, 'chk_salvar_media_movel') and self.chk_salvar_media_movel.isChecked() and len(self.recent_curves) > 0:
            valores_ia = np.mean(list(self.recent_curves), axis=0).round().astype(int).tolist()
        else:
            valores_ia = valores_processados
            
        # 1. Localiza o pico da curva para alinhar o transiente usando a curva da IA para simetria
        peak_idx = np.argmax(valores_ia)
        decay = np.array(valores_ia[peak_idx:])
        
        # 2. Estimar offset (últimos 10% da curva de decaimento)
        n_final = max(5, int(len(decay) * 0.1))
        offset = np.mean(decay[-n_final:])
        
        # 3. Calcula a Área sob a curva (AUC) com offset subtraído
        decay_adj = np.clip(decay - offset, 0, None)
        auc = np.sum(decay_adj) * self.dt_us
        
        # Ajusta dinamicamente a escala Y de forma estável com histerese (evita piscadas por ruído)
        max_val = max(valores_processados) if len(valores_processados) > 0 else 0
        if max_val > 0:
            target_limit_bruto = max_val * 1.15 + 5
            if hasattr(self, 'plot_bruto'):
                if getattr(self, 'current_y_limit_bruto', None) is None:
                    self.current_y_limit_bruto = target_limit_bruto
                    self.plot_bruto.setYRange(0, self.current_y_limit_bruto)
                else:
                    diff = abs(target_limit_bruto - self.current_y_limit_bruto) / self.current_y_limit_bruto
                    if diff > 0.15:
                        self.current_y_limit_bruto = target_limit_bruto
                        self.plot_bruto.setYRange(0, self.current_y_limit_bruto)
            
            max_decay = max(decay_adj) if len(decay_adj) > 0 else 0
            target_limit_decay = max_decay * 1.15 + 5
            if hasattr(self, 'plot_decay'):
                if getattr(self, 'current_y_limit_decay', None) is None:
                    self.current_y_limit_decay = target_limit_decay
                    self.plot_decay.setYRange(0, self.current_y_limit_decay)
                else:
                    diff_dec = abs(target_limit_decay - self.current_y_limit_decay) / self.current_y_limit_decay
                    if diff_dec > 0.15:
                        self.current_y_limit_decay = target_limit_decay
                        self.plot_decay.setYRange(0, self.current_y_limit_decay)
        else:
            if hasattr(self, 'plot_bruto'): self.plot_bruto.setYRange(0, 270)
            if hasattr(self, 'plot_decay'): self.plot_decay.setYRange(0, 270)
        
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
        is_auto = hasattr(self, 'chk_auto_trigger') and self.chk_auto_trigger.isChecked()
        is_ma = hasattr(self, 'chk_ia_usa_media_movel') and self.chk_ia_usa_media_movel.isChecked()
        if is_auto and is_ma and hasattr(self, 'trend_tau') and len(self.trend_tau) >= 3:
            janela_val = min(len(self.trend_tau), self.spin_janela_ia.value())
            tau_para_classif = np.mean(list(self.trend_tau)[-janela_val:])
            auc_para_classif = np.mean(list(self.trend_auc)[-janela_val:])
        else:
            tau_para_classif = tau
            auc_para_classif = auc

        material_detectado, classe_detectada, confianca = self.classificar_leitura(tau_para_classif, auc_para_classif)
        if hasattr(self, 'lbl_cls_material_val'): self.lbl_cls_material_val.setText(material_detectado)
        if hasattr(self, 'lbl_cls_degrad_val'): self.lbl_cls_degrad_val.setText(classe_detectada)
        if hasattr(self, 'lbl_cls_conf_val'): self.lbl_cls_conf_val.setText(f"{confianca:.1f}%")
        
        # Lógica de validação da IA (Aba 3)
        if hasattr(self, 'is_running_validation_test') and self.is_running_validation_test:
            self.processar_leitura_validacao(tau_para_classif, auc_para_classif, material_detectado, classe_detectada, confianca, valores_processados)
        
        # Define a cor do estado dependendo da classe detectada
        cor_classe = "#2ecc71" # Verde para saudável
        if classe_detectada == "Leve": cor_classe = "#27ae60"
        elif classe_detectada == "Moderada": cor_classe = "#f1c40f"
        elif classe_detectada == "Avançada": cor_classe = "#e67e22"
        elif classe_detectada == "Corroído": cor_classe = "#e74c3c"
        elif classe_detectada == "Ar Livre": cor_classe = "#9b59b6"
        elif classe_detectada == "Sem Dados": cor_classe = "#7f8c8d"
            
        if hasattr(self, 'lbl_cls_degrad_val'):
            self.lbl_cls_degrad_val.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {cor_classe};")

        # 5. Atualiza os Displays de Texto e Valores na tela (Instantâneos)
        if hasattr(self, 'lbl_tau_val'): self.lbl_tau_val.setText(self.formatar_valor_tempo(tau))
        if hasattr(self, 'lbl_auc_val'): self.lbl_auc_val.setText(f"{auc:.1f}")

        # Se não estiver no modo contínuo, zera a exibição da média móvel
        if not is_auto:
            if hasattr(self, 'lbl_tau_ma_val'): self.lbl_tau_ma_val.setText(self.formatar_valor_tempo(None))
            if hasattr(self, 'lbl_auc_ma_val'): self.lbl_auc_ma_val.setText("---")

        # Lógica de coleta automatizada de 10 medições sequenciais
        if hasattr(self, 'is_collecting_sequential') and self.is_collecting_sequential:
            id_amostra = self.edit_id_amostra.text().strip() if hasattr(self, 'edit_id_amostra') else "0"
            material, classe = self.obter_material_e_classe_selecionados()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            curva_para_salvar = valores_ia
                
            sucesso = self.registrar_linha_csv(id_amostra, material, classe, curva_para_salvar, timestamp, silent=True)
            if not sucesso:
                self.finalizar_coleta_sequencial(abortado=True)
                return
                
            self.sequential_collect_counter -= 1
            
            if self.sequential_collect_counter > 0:
                total = self.sequential_collect_total
                atual = total - self.sequential_collect_counter + 1
                if hasattr(self, 'active_save_btn'): self.active_save_btn.setText(f"({atual}/{total})")
                QtCore.QTimer.singleShot(150, self.serial_thread.disparar_leitura)
            else:
                self.finalizar_coleta_sequencial(abortado=False)

        # 6. Atualiza os gráficos da Aba 1 (tempo real) se existirem
        if hasattr(self, 'curve_bruto'): self.curve_bruto.setData(valores_processados)
        if hasattr(self, 'line_peak'): self.line_peak.setValue(peak_idx)
        if hasattr(self, 'line_offset'): self.line_offset.setValue(offset)

        # Plot do decaimento com escala dinâmica de tempo
        fator_t, unid_t = self.obter_unidade_tempo()
        tempo_dec = np.arange(len(decay_adj)) * self.dt_us * fator_t
        if hasattr(self, 'curve_decay'): self.curve_decay.setData(tempo_dec, decay_adj)
        if hasattr(self, 'plot_decay'):
            self.plot_decay.setXRange(0, tempo_dec[-1])
            khz = 1000.0 / self.dt_us if self.dt_us > 0 else 0.0
            modo_nome = "ETS" if not is_auto else "DMA"
            self.plot_decay.setLabel('bottom', f'Tempo (Modo {modo_nome} - {khz:.2f} kHz)', unid_t)
        
        # Atualiza os gráficos do Módulo 2 APENAS se a Sub-Aba 2 (Monitoramento em Tempo Real) estiver visível/ativa
        if hasattr(self, 'tab_sub_caracterizacao'):
            if self.tab_sub_caracterizacao.currentIndex() == 1:
                self.atualizar_graficos_tempo_real_caracterizacao()

        # 6.5. Atualiza os gráficos da Aba 4 (Diagnóstico em Tempo Real) se estiver ativa
        if hasattr(self, 'tab_widget') and self.tab_widget.currentIndex() == 3:
            if hasattr(self, 'lbl_diag_material'): self.lbl_diag_material.setText(f"Material: {material_detectado}")
            if hasattr(self, 'lbl_diag_classe'): self.lbl_diag_classe.setText(f"Classe: {classe_detectada}")
            if hasattr(self, 'lbl_diag_confianca'): self.lbl_diag_confianca.setText(f"Confiança: {confianca:.1f}%")
            if hasattr(self, 'lbl_diag_tau'): self.lbl_diag_tau.setText(f"Tau: {self.formatar_valor_tempo(tau)}")
            if hasattr(self, 'lbl_diag_auc'): self.lbl_diag_auc.setText(f"AUC: {auc:.1f}")
            
            try:
                y_pred = B * t_fit + A
                y_mean = np.mean(y_log)
                ss_tot = np.sum((y_log - y_mean) ** 2)
                ss_res = np.sum((y_log - y_pred) ** 2)
                r2_val = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            except Exception:
                r2_val = 0.0
            if hasattr(self, 'lbl_diag_r2'): self.lbl_diag_r2.setText(f"R\u00b2: {r2_val:.4f}")
            
            cor_classe = "#2ecc71"
            if classe_detectada == "Leve": cor_classe = "#27ae60"
            elif classe_detectada == "Moderada": cor_classe = "#f1c40f"
            elif classe_detectada == "Avan\u00e7ada": cor_classe = "#e67e22"
            elif classe_detectada == "Corro\u00eddo": cor_classe = "#e74c3c"
            elif classe_detectada == "Ar Livre": cor_classe = "#9b59b6"
            elif classe_detectada == "Sem Dados": cor_classe = "#7f8c8d"
            if hasattr(self, 'lbl_diag_classe'):
                self.lbl_diag_classe.setStyleSheet(f"font-size: 13pt; font-weight: bold; color: {cor_classe};")
            
            fator_diag = getattr(self, 'fator_diag', fator_t)
            tempo_dec_diag = np.arange(len(decay_adj)) * self.dt_us * fator_diag
            if hasattr(self, 'plot_diag_curves'):
                if getattr(self, 'diag_active_curve', None) is None:
                    self.diag_active_curve = self.plot_diag_curves.plot(
                        tempo_dec_diag, decay_adj, 
                        pen=pg.mkPen("#00ff00", width=3.5), 
                        name="Sinal Ativo"
                    )
                else:
                    self.diag_active_curve.setData(tempo_dec_diag, decay_adj)
                
            tau_escalado = tau * fator_diag
            if hasattr(self, 'plot_diag_scatter'):
                if getattr(self, 'diag_active_scatter', None) is None:
                    self.diag_active_scatter = self.plot_diag_scatter.plot(
                        [tau_escalado], [auc], pen=None, symbol="star", symbolSize=16,
                        symbolBrush=pg.mkBrush("#f1c40f"), symbolPen=pg.mkPen("w", width=1.5)
                    )
                else:
                    self.diag_active_scatter.setData([tau_escalado], [auc])
                
            CLASSES_ORDEM = ["Saudável", "Leve", "Moderada", "Avançada", "Corroído", "Ar Livre"]
            pos_x = None
            x_val = 1.0
            for c in CLASSES_ORDEM:
                n_amostras = sum(1 for a in self.amostras_estatisticas if a["classe"] == c) if hasattr(self, 'amostras_estatisticas') else 0
                if n_amostras > 0:
                    if c.lower() == classe_detectada.lower():
                        pos_x = x_val
                        break
                    x_val += 1.0
            
            if pos_x is not None:
                if getattr(self, 'diag_active_auc_line', None) is None and hasattr(self, 'plot_diag_auc'):
                    self.diag_active_auc_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#f1c40f", width=1.5, style=QtCore.Qt.DashLine))
                    self.plot_diag_auc.addItem(self.diag_active_auc_line)
                if hasattr(self, 'diag_active_auc_line') and self.diag_active_auc_line:
                    self.diag_active_auc_line.setValue(auc)
                
                if getattr(self, 'diag_active_tau_line', None) is None and hasattr(self, 'plot_diag_tau'):
                    self.diag_active_tau_line = pg.InfiniteLine(angle=0, pen=pg.mkPen("#f1c40f", width=1.5, style=QtCore.Qt.DashLine))
                    self.plot_diag_tau.addItem(self.diag_active_tau_line)
                if hasattr(self, 'diag_active_tau_line') and self.diag_active_tau_line:
                    self.diag_active_tau_line.setValue(tau_escalado)
        
        # 7. Se estiver no modo contínuo, adiciona os dados nas deques de tendência
        if is_auto and hasattr(self, 'trend_indices'):
            self.trend_counter += 1
            self.trend_indices.append(self.trend_counter)
            self.trend_tau.append(tau)
            self.trend_auc.append(auc)
            
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
            
            fator_t, unid_t = self.obter_unidade_tempo()
            trend_tau_escalado = [v * fator_t for v in self.trend_tau]
            ma_tau_escalado = [v * fator_t for v in ma_tau]

            if hasattr(self, 'curve_trend_tau'): self.curve_trend_tau.setData(list(self.trend_indices), trend_tau_escalado)
            if hasattr(self, 'curve_trend_auc'): self.curve_trend_auc.setData(list(self.trend_indices), list(self.trend_auc))
            if hasattr(self, 'curve_trend_tau_ma'): self.curve_trend_tau_ma.setData(list(self.trend_indices), ma_tau_escalado)
            if hasattr(self, 'curve_trend_auc_ma'): self.curve_trend_auc_ma.setData(list(self.trend_indices), ma_auc)
            
            if hasattr(self, 'plot_trend'): self.plot_trend.setLabel('left', f'Tau ({unid_t})', color='#2ecc71')
            
            if len(ma_tau) > 0 and hasattr(self, 'lbl_tau_ma_val'):
                self.lbl_tau_ma_val.setText(self.formatar_valor_tempo(ma_tau[-1]))
            if len(ma_auc) > 0 and hasattr(self, 'lbl_auc_ma_val'):
                self.lbl_auc_ma_val.setText(f"{ma_auc[-1]:.1f}")
            
            if len(self.trend_auc) > 0 and hasattr(self, 'trend_auc_axis'):
                min_auc, max_auc = min(self.trend_auc), max(self.trend_auc)
                padding = max(10, (max_auc - min_auc) * 0.1)
                self.trend_auc_axis.setYRange(min_auc - padding, max_auc + padding)

    # =====================================================================
    # SALVAR MEDIÇÃO NO ARQUIVO CSV
    # =====================================================================
    def registrar_linha_csv(self, id_amostra, material, classe, valores, timestamp, silent=False):
        try:
            self.dataset_manager.append_record(self.arquivo_csv, id_amostra, material, classe, self.dt_us, valores, timestamp)
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
        except Exception as e:
            if not silent:
                print(f"[ERRO] Falha ao salvar no CSV: {e}")
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
                    self.dataset_manager.invalidate_cache(self.arquivo_csv)
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
                        
                    self.dataset_manager.invalidate_cache(self.arquivo_csv)
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
        if hasattr(self, 'chk_auto_trigger'):
            self.chk_auto_trigger.setChecked(False)
        if hasattr(self, 'serial_thread') and self.serial_thread:
            self.serial_thread.desconectar()
        event.accept()



    def rodar_analise_estatistica(self):
        if not os.path.exists(self.arquivo_csv):
            QtWidgets.QMessageBox.warning(
                self, 
                "Dataset não encontrado", 
                f"O arquivo '{self.arquivo_csv}' não existe. Faça algumas medições na aba de aquisição primeiro!"
            )
            return

        try:
            # Obtém amostras do gerenciador com cache
            amostras = self.dataset_manager.get_records(self.arquivo_csv)
            self.amostras_estatisticas = [] # Limpa a lista anterior
            
            usa_filtro = self.chk_salvar_media_movel.isChecked()
            for a in amostras:
                if a['is_filtered'] == usa_filtro:
                    valores_arr = np.array(a['curva'])
                    peak_idx = np.argmax(valores_arr)
                    decay = valores_arr[peak_idx:]
                    n_final = max(5, int(len(decay) * 0.1))
                    offset = np.mean(decay[-n_final:])
                    decay_adj = np.clip(decay - offset, 0, None)
                    
                    self.amostras_estatisticas.append({
                        "id": a['id_amostra'],
                        "material": a['material'],
                        "classe": a['classe'],
                        "auc": a['auc'],
                        "tau": a['tau'],
                        "curva": decay_adj,
                        "dt_us": a['dt_us']
                    })
                    
            if len(self.amostras_estatisticas) == 0:
                for a in amostras:
                    valores_arr = np.array(a['curva'])
                    peak_idx = np.argmax(valores_arr)
                    decay = valores_arr[peak_idx:]
                    n_final = max(5, int(len(decay) * 0.1))
                    offset = np.mean(decay[-n_final:])
                    decay_adj = np.clip(decay - offset, 0, None)
                    
                    self.amostras_estatisticas.append({
                        "id": a['id_amostra'],
                        "material": a['material'],
                        "classe": a['classe'],
                        "auc": a['auc'],
                        "tau": a['tau'],
                        "curva": decay_adj,
                        "dt_us": a['dt_us']
                    })
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
            self.amostras_filtradas = self.dataset_manager.filtrar_outliers_iqr(self.amostras_filtradas)

        if not self.amostras_filtradas:
            self.txt_report_stats.setPlainText("Sem dados correspondentes aos filtros selecionados.")
            return

        # Verifica se a diferenciação de tonalidades por ID deve ser ativada
        single_filter_active = (
            len(materiais_ativos) == 1 and
            len(classes_ativas) == 1 and
            self.chk_filter_outliers.isChecked()
        )
        use_id_shading = single_filter_active or (
            hasattr(self, 'chk_diferenciar_ids_tonalidade') and self.chk_diferenciar_ids_tonalidade.isChecked()
        )

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

        # Se use_id_shading for True, mapeia cada ID único para uma TONALIDADE (luminosidade HSL) dentro do seu material/classe
        N_samples = len(self.amostras_filtradas)
        if use_id_shading and N_samples > 0:
            grupos_amostras = {}
            for a_item in self.amostras_filtradas:
                key = (a_item["material"], a_item["classe"])
                if key not in grupos_amostras:
                    grupos_amostras[key] = []
                grupos_amostras[key].append(a_item)

            for key, g_items in grupos_amostras.items():
                ids_unicos = sorted(list(set([str(a["id"]) for a in g_items])))
                num_ids = len(ids_unicos)

                id_to_lightness = {}
                for idx_id, id_val in enumerate(ids_unicos):
                    # Varia a luminosidade entre 0.35 (tom escuro) e 0.85 (tom claro) para cada ID distinto
                    l_factor = 0.35 + 0.50 * (idx_id / max(1, num_ids - 1)) if num_ids > 1 else 0.55
                    id_to_lightness[id_val] = l_factor

                for a_item in g_items:
                    id_str = str(a_item["id"])
                    base_hex = CORES_CLASSES.get(a_item["classe"], "#3498db")
                    base_qcol = QtGui.QColor(base_hex)
                    h, s, l_val, a_alpha = base_qcol.getHslF()
                    
                    target_l = id_to_lightness.get(id_str, 0.55)
                    adjusted_qcol = QtGui.QColor.fromHslF(h, min(1.0, s * 1.05), max(0.25, min(0.90, target_l)))
                    a_item["color_hex"] = adjusted_qcol.name()
                    a_item["brush"] = pg.mkBrush(adjusted_qcol)

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
        if use_id_shading and N_samples > 0:
            ids_unicos = sorted(list(set([str(a["id"]) for a in self.amostras_filtradas])))
            num_ids = len(ids_unicos)
            if num_ids > 1:
                faixa_str = f"Tonalidades por ID Ativas: <b>{num_ids} IDs distintos</b> (Tonalidade escura &rarr; clara por ID em cada classe/material)"
            else:
                faixa_str = f"ID Único: <b>ID '{ids_unicos[0]}'</b> ({N_samples} amostras | Tonalidade padrão mantida)"

            report.append(
                f"<div style='background-color: #2c2c2e; padding: 6px 10px; border-radius: 4px; border: 1px solid #3a3a3c; margin-bottom: 8px;'>"
                f"<b style='color: #00e676;'>🎨 Diferenciação de IDs por Tonalidade:</b><br>"
                f"{faixa_str}<br>"
                f"<small style='color: #a0a0a0;'>Cores originais mantidas. Diferentes IDs dentro da mesma classe/material possuem tonalidades (luminosidade HSL) distintas.</small>"
                f"</div>"
            )

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
        stat_dt = primeira_amostra["dt_us"] if (primeira_amostra and "dt_us" in primeira_amostra) else 0.21875
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
            curve_item = self.plot_stat_curves.plot(
                t, mean, 
                pen=pg.mkPen(color, width=3, style=estilo), 
                name=nome_legenda
            )
            curve_item.mat_name = mat
            curve_item.cls_name = cls
            curve_item.num_curvas = len(curvas)
            
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
            
            # Exibe o ID do ponto apenas se houver exatamente 1 material, 1 classe e IQR ativado (independente do total de amostras)
            show_text_items = (
                len(materiais_ativos) == 1 and
                len(classes_ativas) == 1 and
                self.chk_filter_outliers.isChecked()
            )
            sym_sz = 15 if show_text_items else 8
            font_id_stat = QtGui.QFont("Segoe UI", 7, QtGui.QFont.Bold)

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
                
                if use_id_shading:
                    brushes_mat = [amostras_classe[i].get("brush", pg.mkBrush(rgb[0], rgb[1], rgb[2], 180)) for i in indices_mat]
                    self.plot_stat_auc.plot(x_sub, y_sub, pen=None, symbol=simbolo, symbolSize=10, 
                                            symbolBrush=brushes_mat, symbolPen=pg.mkPen('w', width=0.4))
                else:
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
                
                if use_id_shading:
                    brushes_mat = [amostras_classe[i].get("brush", pg.mkBrush(rgb[0], rgb[1], rgb[2], 180)) for i in indices_mat]
                    self.plot_stat_tau.plot(x_sub, y_sub, pen=None, symbol=simbolo, symbolSize=10, 
                                            symbolBrush=brushes_mat, symbolPen=pg.mkPen('w', width=0.4))
                else:
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
                
                if use_id_shading:
                    brushes_mat = [a.get("brush", pg.mkBrush(rgb[0], rgb[1], rgb[2], 200)) for a in amostras_mat]
                    self.plot_stat_scatter.plot(tau_sub, auc_sub, pen=None, symbol=simbolo, symbolSize=10,
                                                symbolBrush=brushes_mat, symbolPen=pg.mkPen('w', width=0.4),
                                                name=f"{c.capitalize()} ({mat_nome})")
                else:
                    self.plot_stat_scatter.plot(tau_sub, auc_sub, pen=None, symbol=simbolo, symbolSize=10,
                                                symbolBrush=pg.mkBrush(rgb[0], rgb[1], rgb[2], 200),
                                                symbolPen=pg.mkPen('w', width=0.5), name=f"{c.capitalize()} ({mat_nome})")

    def calcular_distancia_pixel_curva(self, vb, item, pos):
        """
        Calcula a menor distância em pixels da cena (pos) até a linha gráfica (PlotDataItem),
        avaliando a distância aos segmentos de reta entre vértices. Funciona 100% perfeitamente sob qualquer nível de ZOOM.
        """
        x_arr, y_arr = item.xData, item.yData
        if x_arr is None or y_arr is None or len(x_arr) < 2:
            return float('inf'), None

        mouse_pt = vb.mapSceneToView(pos)
        mx = mouse_pt.x()

        idx = np.searchsorted(x_arr, mx)
        idx_start = max(0, idx - 12)
        idx_end = min(len(x_arr) - 1, idx + 12)

        px, py = pos.x(), pos.y()
        menor_dist = float('inf')
        melhor_pt = None

        for i in range(idx_start, idx_end):
            p1_scene = vb.mapViewToScene(pg.Point(x_arr[i], y_arr[i]))
            p2_scene = vb.mapViewToScene(pg.Point(x_arr[i+1], y_arr[i+1]))

            ax, ay = p1_scene.x(), p1_scene.y()
            bx, by = p2_scene.x(), p2_scene.y()

            dx = bx - ax
            dy = by - ay
            if dx == 0 and dy == 0:
                dist = np.hypot(px - ax, py - ay)
                t_proj = 0.0
            else:
                t_proj = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
                proj_x = ax + t_proj * dx
                proj_y = ay + t_proj * dy
                dist = np.hypot(px - proj_x, py - proj_y)

            if dist < menor_dist:
                menor_dist = dist
                pt_x = float(x_arr[i] + t_proj * (x_arr[i+1] - x_arr[i]))
                pt_y = float(y_arr[i] + t_proj * (y_arr[i+1] - y_arr[i]))
                melhor_pt = (pt_x, pt_y)

        return menor_dist, melhor_pt

    def is_tooltip_enabled(self):
        if hasattr(self, 'chk_enable_tooltips') and not self.chk_enable_tooltips.isChecked():
            return False
        if hasattr(self, 'chk_coil_enable_tooltips') and not self.chk_coil_enable_tooltips.isChecked():
            return False
        return True

    def ao_alternar_exibicao_tooltips(self):
        if not self.is_tooltip_enabled():
            if hasattr(self, 'floating_tooltip'):
                self.floating_tooltip.fechar_tooltip()
            self.atualizar_destaque_visual_hover(target_plot=None)

    def ao_alternar_exibicao_tendencia_rt(self, state=None):
        if hasattr(self, 'tab_sub_caracterizacao') and self.tab_sub_caracterizacao.currentIndex() == 1:
            self.atualizar_graficos_tempo_real_caracterizacao(force_refresh=True)

    def ao_clicar_mouse_grafico(self, event):
        """
        Gerencia cliques do mouse nos gráficos para FIXAR (pin) ou DESFIXAR o tooltip.
        """
        if not hasattr(self, 'floating_tooltip') or not self.is_tooltip_enabled():
            return

        # Se há um destaque visual ativo sob o cursor, FIXA o tooltip!
        if getattr(self, '_current_hl_plot', None) and self.floating_tooltip.isVisible():
            self.floating_tooltip.fixar_tooltip()
        elif self.floating_tooltip.is_pinned:
            # Clique em área vazia desfixa e fecha o tooltip
            self.floating_tooltip.fechar_tooltip()

    def atualizar_destaque_visual_hover(self, target_plot=None, pt_coords=None, line_coords=None, symbol='o'):
        """
        Desenha um destaque brilhante neon sobre o ponto ou linha sob o cursor do mouse.
        Se target_plot for None, remove todos os destaques visuais ativos e esconde o tooltip (se não estiver fixado).
        """
        if hasattr(self, 'floating_tooltip') and self.floating_tooltip.is_pinned and target_plot is None:
            return

        if not hasattr(self, '_hl_point_item'):
            self._hl_point_item = pg.ScatterPlotItem(
                size=18,
                pen=pg.mkPen('#00ffff', width=2.5),
                brush=pg.mkBrush(255, 255, 0, 220)
            )
            self._hl_line_item = pg.PlotDataItem(
                pen=pg.mkPen('#ffff00', width=4.5)
            )
            self._current_hl_plot = None

        if self._current_hl_plot and (self._current_hl_plot != target_plot or target_plot is None):
            try:
                if self._hl_point_item in self._current_hl_plot.items:
                    self._current_hl_plot.removeItem(self._hl_point_item)
                if self._hl_line_item in self._current_hl_plot.items:
                    self._current_hl_plot.removeItem(self._hl_line_item)
            except Exception:
                pass
            self._current_hl_plot = None

        if target_plot is None:
            if hasattr(self, 'floating_tooltip') and not self.floating_tooltip.is_pinned:
                self.floating_tooltip.hide()
            return

        # Aplica destaque em PONTO
        if pt_coords is not None:
            px, py = pt_coords
            self._hl_point_item.setData(x=[px], y=[py], symbol=symbol)
            if self._hl_point_item not in target_plot.items:
                target_plot.addItem(self._hl_point_item)
            if self._hl_line_item in target_plot.items:
                target_plot.removeItem(self._hl_line_item)
            self._current_hl_plot = target_plot

        # Aplica destaque em LINHA DE DECAIMENTO
        elif line_coords is not None:
            lx, ly = line_coords
            self._hl_line_item.setData(lx, ly)
            if self._hl_line_item not in target_plot.items:
                target_plot.addItem(self._hl_line_item)
            if self._hl_point_item in target_plot.items:
                target_plot.removeItem(self._hl_point_item)
            self._current_hl_plot = target_plot

    def ao_mover_mouse_estatistico(self, pos):
        if not self.is_tooltip_enabled():
            return
        if not hasattr(self, 'amostras_filtradas') or not self.amostras_filtradas:
            return
            
        melhor_amostra = None
        melhor_plot = None
        melhor_pt_x, melhor_pt_y = None, None
        hover_decay_info = None
        menor_dist_pixel = 18.0
        
        # 1. Verifica se o mouse está sobre o gráfico de Curvas Médias de Decaimento (plot_stat_curves)
        vb_curves = self.plot_stat_curves.vb
        if vb_curves.sceneBoundingRect().contains(pos):
            for item in self.plot_stat_curves.items:
                if isinstance(item, pg.PlotDataItem) and item.name:
                    dist_px, pt_coord = self.calcular_distancia_pixel_curva(vb_curves, item, pos)
                    if dist_px < 25.0 and dist_px < menor_dist_pixel:
                        menor_dist_pixel = dist_px
                        hover_decay_info = {
                            "nome": item.name,
                            "mat": getattr(item, 'mat_name', 'Múltiplos'),
                            "cls": getattr(item, 'cls_name', 'Filtrado'),
                            "num": getattr(item, 'num_curvas', len(self.amostras_filtradas)),
                            "t": pt_coord[0],
                            "y": pt_coord[1],
                            "x_arr": item.xData,
                            "y_arr": item.yData
                        }
        else:
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
                            melhor_plot = plot
                            melhor_pt_x, melhor_pt_y = x_pts, y_pts
                    break
                
        if hover_decay_info:
            self.atualizar_destaque_visual_hover(target_plot=self.plot_stat_curves, line_coords=(hover_decay_info['x_arr'], hover_decay_info['y_arr']))
            tooltip_text = (
                f"📈 <b>CURVA MÉDIA DE DECAIMENTO V(t)</b><br>"
                f"--------------------------------------------------<br>"
                f"📁 <b>Origem / Dataset:</b> Base de Dados Filtrada (N={hover_decay_info['num']} amostras)<br>"
                f"🛡️ <b>Material:</b> {hover_decay_info['mat']}<br>"
                f"📊 <b>Estado / Classe de Corrosão:</b> {hover_decay_info['cls'].capitalize()}<br>"
                f"--------------------------------------------------<br>"
                f"⏱️ <b>Ponto Cursor:</b> t = {hover_decay_info['t']:.2f} &mu;s | V(t) = {hover_decay_info['y']:.1f} ADC Counts"
            )
            self.floating_tooltip.exibir_hover(QtGui.QCursor.pos(), tooltip_text, target_plot=self.plot_stat_curves)
        elif melhor_amostra:
            simb = SIMBOLOS_MATERIAIS.get(melhor_amostra.get("material"), "o")
            self.atualizar_destaque_visual_hover(target_plot=melhor_plot, pt_coords=(melhor_pt_x, melhor_pt_y), symbol=simb)
            cor_hex = melhor_amostra.get("color_hex", "#3498db")
            color_badge = f"<span style='color: {cor_hex}; font-size: 14pt;'>■</span> " if "color_hex" in melhor_amostra else ""
            tooltip_text = (
                f"📍 <b>PONTO DE MEDIÇÃO ESTATÍSTICO</b><br>"
                f"--------------------------------------------------<br>"
                f"{color_badge}🆔 <b>ID Cupom:</b> {melhor_amostra['id']}<br>"
                f"🛡️ <b>Material:</b> {melhor_amostra['material']}<br>"
                f"📊 <b>Classe de Corrosão:</b> {melhor_amostra['classe'].capitalize()}<br>"
                f"⚡ <b>Constante de Tempo (&tau;):</b> {melhor_amostra['tau']:.4f} &mu;s<br>"
                f"📐 <b>Área Sob a Curva (AUC):</b> {melhor_amostra['auc']:.1f} Counts.&mu;s"
            )
            self.floating_tooltip.exibir_hover(QtGui.QCursor.pos(), tooltip_text, target_plot=melhor_plot)
        else:
            self.atualizar_destaque_visual_hover(target_plot=None)

    def carregar_lista_materiais(self):
        materiais = list(self.default_materials)

        # 1. Tenta carregar do banco JSON
        if os.path.exists(self.arquivo_materiais_config):
            try:
                with open(self.arquivo_materiais_config, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list) and len(data) > 0:
                            materiais = data
            except Exception as e:
                materiais = list(self.default_materials)

        # 2. Migração legada do .txt se existir
        if os.path.exists(self.arquivo_materiais_txt_legacy):
            try:
                with open(self.arquivo_materiais_txt_legacy, "r", encoding="utf-8") as f:
                    legacy_items = [line.strip() for line in f if line.strip()]
                    for item in legacy_items:
                        if item not in materiais:
                            materiais.append(item)
            except Exception:
                pass

        # 3. Garante presença dos materiais padrão
        for mat in self.default_materials:
            if mat not in materiais:
                if mat == "Ar Livre":
                    materiais.append(mat)
                else:
                    idx = materiais.index("Ar Livre") if "Ar Livre" in materiais else len(materiais)
                    materiais.insert(idx, mat)

        self.custom_materials = [m for m in materiais if m not in self.default_materials]
        
        # Salva o JSON atualizado
        try:
            with open(self.arquivo_materiais_config, "w", encoding="utf-8") as f:
                json.dump(materiais, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

        return materiais

    def salvar_lista_materiais(self):
        try:
            with open(self.arquivo_materiais_config, "w", encoding="utf-8") as f:
                json.dump(self.todos_materiais, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[MATERIAIS] Erro ao salvar materiais_cadastrados.json: {e}")

    def adicionar_material_customizado(self):
        novo_nome = self.edit_novo_material.text().strip()
        if not novo_nome:
            QtWidgets.QMessageBox.warning(self, "Nome Vazio", "Por favor, insira o nome do novo material!")
            return
            
        if ";" in novo_nome or "\n" in novo_nome:
            QtWidgets.QMessageBox.warning(self, "Caracter Inválido", "O nome do material não pode conter ponto e vírgula ';' ou quebras de linha!")
            return
            
        if novo_nome in self.todos_materiais:
            QtWidgets.QMessageBox.warning(self, "Material Existente", f"O material '{novo_nome}' já existe na interface!")
            return
            
        if "Ar Livre" in self.todos_materiais:
            idx = self.todos_materiais.index("Ar Livre")
            self.todos_materiais.insert(idx, novo_nome)
        else:
            self.todos_materiais.append(novo_nome)

        if novo_nome not in self.default_materials and novo_nome not in self.custom_materials:
            self.custom_materials.append(novo_nome)

        self.salvar_lista_materiais()
        self.atualizar_widgets_materiais()
        self.edit_novo_material.clear()
        
        if novo_nome in self.radio_buttons_material:
            self.radio_buttons_material[novo_nome].setChecked(True)
            
        QtWidgets.QMessageBox.information(self, "Sucesso", f"Material '{novo_nome}' adicionado com sucesso!")

    def remover_material_selecionado(self):
        material_a_remover = self.obter_material_e_classe_selecionados()[0]
        if material_a_remover in self.default_materials:
            QtWidgets.QMessageBox.warning(self, "Ação Proibida", f"Não é permitido excluir os materiais padrão do sistema ({', '.join(self.default_materials)}).")
            return
            
        resposta = QtWidgets.QMessageBox.question(
            self, 
            "Excluir Material", 
            f"Tem certeza de que deseja excluir o material '{material_a_remover}'?\nEsta ação não removerá os dados antigos do CSV, mas o material não aparecerá mais nos controles da interface.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if resposta == QtWidgets.QMessageBox.Yes:
            if material_a_remover in self.todos_materiais:
                self.todos_materiais.remove(material_a_remover)
            if material_a_remover in self.custom_materials:
                self.custom_materials.remove(material_a_remover)
            self.salvar_lista_materiais()
            self.atualizar_widgets_materiais()
            if "A36 Comum" in self.radio_buttons_material:
                self.radio_buttons_material["A36 Comum"].setChecked(True)
            QtWidgets.QMessageBox.information(self, "Sucesso", f"Material '{material_a_remover}' removido!")

    def atualizar_widgets_materiais(self):
        # Garantia de integridade da lista
        for mat in self.default_materials:
            if mat not in self.todos_materiais:
                if mat == "Ar Livre":
                    self.todos_materiais.append(mat)
                else:
                    idx = self.todos_materiais.index("Ar Livre") if "Ar Livre" in self.todos_materiais else len(self.todos_materiais)
                    self.todos_materiais.insert(idx, mat)

        # --- ABA 1 (AQUISIÇÃO) ---
        if hasattr(self, 'layout_mat_radios'):
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

        # --- ABA 5 (CARACTERIZAÇÃO & COMPARAÇÃO DE BOBINAS) ---
        if hasattr(self, 'combo_coil_material'):
            current_sel = self.combo_coil_material.currentText()
            self.combo_coil_material.blockSignals(True)
            self.combo_coil_material.clear()
            self.combo_coil_material.addItems(self.todos_materiais)
            idx = self.combo_coil_material.findText(current_sel)
            if idx >= 0:
                self.combo_coil_material.setCurrentIndex(idx)
            self.combo_coil_material.blockSignals(False)

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
    # LÓGICA DA ABA 5: CARACTERIZAÇÃO E COMPARAÇÃO DE BOBINAS (LIFT-OFF)
    # =====================================================================
    def atualizar_lista_radio_bobinas(self):
        """
        Reconstrói os Radio Buttons (bullet points) para cada bobina cadastrada no coil_manager em N colunas.
        """
        for i in reversed(range(self.layout_radio_bobinas.count())):
            item = self.layout_radio_bobinas.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        for btn in list(self.group_radio_bobinas.buttons()):
            self.group_radio_bobinas.removeButton(btn)

        coils = self.coil_manager.get_all_coils()
        if not coils:
            return

        self.lista_widgets_radio_bobinas = []
        sorted_ids = sorted(coils.keys())
        first_btn = None
        n_cols = self.obter_num_colunas_para_grid(self.layout_radio_bobinas, self.lista_widgets_radio_bobinas, is_sensor_grid=True)
        for idx, cid in enumerate(sorted_ids):
            info = coils[cid]
            label = f"ID {info['id']} ({info['inductance_uh']:.1f}uH|{info['core']})"
            radio = QtWidgets.QRadioButton(label)
            radio.setProperty("coil_id", cid)
            radio.setStyleSheet("""
                QRadioButton {
                    color: #ffffff !important; font-size: 8pt; font-weight: bold; padding: 2px;
                }
                QRadioButton::indicator {
                    width: 14px; height: 14px; border: 1.5px solid #888888; background-color: #222225; border-radius: 7px;
                }
                QRadioButton::indicator:checked {
                    background-color: #00e676; border: 2px solid #ffffff; border-radius: 7px;
                }
            """)
            radio.toggled.connect(self.ao_selecionar_radio_bobina)
            self.group_radio_bobinas.addButton(radio)
            self.lista_widgets_radio_bobinas.append(radio)
            self.layout_radio_bobinas.addWidget(radio, idx // n_cols, idx % n_cols)
            radio.setVisible(True)
            radio.show()
            if first_btn is None:
                first_btn = radio

        self.reorganizar_grid_widgets(self.layout_radio_bobinas, self.lista_widgets_radio_bobinas, n_cols)
        if hasattr(self, 'widget_radio_bobinas_container'):
            self.widget_radio_bobinas_container.updateGeometry()
            self.widget_radio_bobinas_container.adjustSize()
            self.widget_radio_bobinas_container.setVisible(True)
            self.widget_radio_bobinas_container.show()

        if first_btn:
            first_btn.setChecked(True)

    def ao_selecionar_radio_bobina(self):
        checked_button = self.group_radio_bobinas.checkedButton()
        if not checked_button:
            return

        cid = checked_button.property("coil_id")
        info = self.coil_manager.get_coil_info(cid)
        if not info:
            return

        self.active_coil_info = info
        self.atualizar_card_especificacoes_bobina(info)
        self.calcular_liftoff_bancada()

    def ao_alternar_checkbox_espacador(self, chk_clicado, chk_outro):
        if chk_clicado.isChecked():
            chk_outro.blockSignals(True)
            chk_outro.setChecked(False)
            chk_outro.blockSignals(False)
        self.calcular_liftoff_bancada()

    def calcular_liftoff_bancada(self, *args):
        """
        Calcula automaticamente a distância real de Lift-Off (d) baseada nos checkboxes
        de espaçadores empilhados (4 colunas: 5mm, 4mm, 2mm, 1mm; linhas: 1x, 2x), na altura do piso do berço (2.6 mm) e na altura total da bobina ativa.
        """
        if not hasattr(self, 'chk_espacador_5mm_1'):
            return

        count_5mm = 2 if (getattr(self, 'chk_espacador_5mm_2', None) and self.chk_espacador_5mm_2.isChecked()) else (1 if (getattr(self, 'chk_espacador_5mm_1', None) and self.chk_espacador_5mm_1.isChecked()) else 0)
        count_4mm = 2 if (getattr(self, 'chk_espacador_4mm_2', None) and self.chk_espacador_4mm_2.isChecked()) else (1 if (getattr(self, 'chk_espacador_4mm_1', None) and self.chk_espacador_4mm_1.isChecked()) else 0)
        count_2mm = 2 if (getattr(self, 'chk_espacador_2mm_2', None) and self.chk_espacador_2mm_2.isChecked()) else (1 if (getattr(self, 'chk_espacador_2mm_1', None) and self.chk_espacador_2mm_1.isChecked()) else 0)
        count_1mm = 2 if (getattr(self, 'chk_espacador_1mm_2', None) and self.chk_espacador_1mm_2.isChecked()) else (1 if (getattr(self, 'chk_espacador_1mm_1', None) and self.chk_espacador_1mm_1.isChecked()) else 0)

        h_espacadores = (count_5mm * 5.0) + (count_4mm * 4.0) + (count_2mm * 2.0) + (count_1mm * 1.0)

        h_berco_piso = 2.6
        h_total_berco = h_espacadores + h_berco_piso

        h_bobina = 8.5
        if hasattr(self, 'active_coil_info') and self.active_coil_info:
            info = self.active_coil_info
            h_bobina = info.get('height_mm', 8.5)
            if h_bobina <= 0:
                h_bobina = info.get('height_winding_mm', 8.5)

        d_liftoff = round(max(0.0, h_total_berco - h_bobina), 2)
        self._last_calculated_liftoff = d_liftoff
        self.distancia_lift_off = d_liftoff
        self.liftoff_manual_override = False

        self._ignore_spin_liftoff_signals = True
        self.spin_liftoff_dist.setValue(d_liftoff)
        self._ignore_spin_liftoff_signals = False

        if hasattr(self, 'tab_sub_caracterizacao') and self.tab_sub_caracterizacao.currentIndex() == 1:
            self.atualizar_graficos_tempo_real_caracterizacao(force_refresh=True)

        partes = []
        if count_5mm > 0: partes.append(f"{count_5mm}x 5mm")
        if count_4mm > 0: partes.append(f"{count_4mm}x 4mm")
        if count_2mm > 0: partes.append(f"{count_2mm}x 2mm")
        if count_1mm > 0: partes.append(f"{count_1mm}x 1mm")
        txt_espacadores = " + ".join(partes) if partes else "Nenhum"

        self.lbl_calculo_liftoff_info.setText(
            f"Fórmula Bancada: ({h_espacadores:.1f}mm espac. [{txt_espacadores}] + {h_berco_piso:.1f}mm piso) - {h_bobina:.1f}mm bobina = {d_liftoff:.1f} mm"
        )

    def ao_concluir_edicao_spin_liftoff(self):
        if getattr(self, '_ignore_spin_liftoff_signals', False):
            return

        val = self.spin_liftoff_dist.value()
        last_calc = getattr(self, '_last_calculated_liftoff', 0.0)
        if abs(val - last_calc) < 1e-4:
            self.liftoff_manual_override = False
            return

        if not getattr(self, 'liftoff_manual_override', False):
            reply = QtWidgets.QMessageBox.question(
                self,
                "Aviso de Alteração Manual de Lift-Off",
                f"A distância de Lift-Off é calculada automaticamente conforme a geometria dos componentes selecionados ({last_calc:.2f} mm).\n\n"
                f"Tem certeza que deseja alterar manualmente a distância para {val:.2f} mm?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )

            if reply == QtWidgets.QMessageBox.Yes:
                self.liftoff_manual_override = True
                self.distancia_lift_off = round(val, 2)
                if hasattr(self, 'tab_sub_caracterizacao') and self.tab_sub_caracterizacao.currentIndex() == 1:
                    self.atualizar_graficos_tempo_real_caracterizacao(force_refresh=True)
            else:
                self._ignore_spin_liftoff_signals = True
                self.spin_liftoff_dist.setValue(last_calc)
                self.distancia_lift_off = round(last_calc, 2)
                self._ignore_spin_liftoff_signals = False

    def atualizar_card_especificacoes_bobina(self, info):
        d_wind = info.get('diameter_winding_mm', info['diameter_mm'])
        h_wind = info.get('height_winding_mm', info['height_mm'])
        card_txt = f"""==================================================
CARACTERÍSTICAS DO SENSOR SELECIONADO: BOBINA {info['id']}
==================================================
• Indutância Medida (L0):  {info['inductance_uh']:.2f} uH
• Resistência Medida (R):  {info['resistance_ohm']:.2f} Ohm
• Diâmetro Total / Enrol.:  {info['diameter_mm']:.1f} mm / {d_wind:.1f} mm
• Altura Total / Enrol.:   {info['height_mm']:.1f} mm / {h_wind:.1f} mm
• Nº de Espiras (N):        {info['turns']} voltas
• Bitola do Fio (AWG):     {info['awg']} (Ø {info['wire_diameter_mm']:.3f} mm)
• Material do Núcleo:      {info['core']}
• Descrição / Notas:       {info.get('description', 'Sem notas.')}
"""
        self.txt_coil_specs_card.setText(card_txt)

    def abrir_dialogo_cadastro_bobina(self):
        checked_button = self.group_radio_bobinas.checkedButton()
        current_id = checked_button.property("coil_id") if checked_button else None
        
        dialog = CoilRegistrationDialog(self.coil_manager, parent=self, initial_coil_id=current_id)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.atualizar_lista_radio_bobinas()
            self.atualizar_graficos_comparacao_bobinas()

    def abrir_grafico_3d_caracterizacao(self):
        """
        Abre a caixa de diálogo modal com o gráfico 3D interativo: Indutância Efetiva x AUC x Distância.
        """
        selected_items = self.list_imported_coil_files.selectedItems()
        selected_filenames = [item.text() for item in selected_items]
        
        recs = [rec for rec in self.loaded_coil_records if rec['filename'] in selected_filenames] if selected_filenames else self.loaded_coil_records

        if not recs:
            QtWidgets.QMessageBox.warning(
                self, "Nenhum Teste Carregado",
                "Por favor, grave ou importe testes em CSV na 5ª Aba para visualizar o gráfico 3D!"
            )
            return

        dialog = Coil3DPlotDialog(records=recs, parent=self)
        dialog.exec_()

    def ao_mover_mouse_grafico_caracterizacao(self, pos):
        """
        Exibe balão tooltip detalhado ao passar o cursor sobre qualquer ponto nos gráficos da 5ª Aba.
        """
        if not self.is_tooltip_enabled():
            return
        if not hasattr(self, 'loaded_coil_records') or not self.loaded_coil_records:
            if hasattr(self, 'tooltip_estatistico') and self.tooltip_estatistico.isVisible():
                self.tooltip_estatistico.hide()
            return

        selected_items = self.list_imported_coil_files.selectedItems()
        selected_filenames = [item.text() for item in selected_items]
        records = [rec for rec in self.loaded_coil_records if rec['filename'] in selected_filenames] if selected_filenames else self.loaded_coil_records

        if not records:
            if hasattr(self, 'tooltip_estatistico') and self.tooltip_estatistico.isVisible():
                self.tooltip_estatistico.hide()
            return

        plots = [
            self.plot_coil_decay,
            self.plot_coil_tau_liftoff,
            self.plot_coil_auc_liftoff,
            self.plot_coil_l_liftoff
        ]

        melhor_rec = None
        melhor_sample_idx = None
        melhor_plot = None
        melhor_pt_x, melhor_pt_y = None, None
        hover_decay_pt = None
        hover_decay_coords = None
        menor_dist_px = float('inf')

        for plot_item in plots:
            vb = plot_item.vb
            if vb.sceneBoundingRect().contains(pos):
                if plot_item == self.plot_coil_decay:
                    for item in plot_item.items:
                        if isinstance(item, pg.PlotDataItem) and hasattr(item, 'rec_data'):
                            rec = item.rec_data
                            dist_px, pt_coord = self.calcular_distancia_pixel_curva(vb, item, pos)
                            if dist_px < 25.0 and dist_px < menor_dist_px:
                                menor_dist_px = dist_px
                                melhor_rec = rec
                                hover_decay_pt = pt_coord
                                hover_decay_coords = (item.xData, item.yData)
                else:
                    for item in plot_item.items:
                        if hasattr(item, 'rec_data'):
                            rec = item.rec_data
                            if isinstance(item, pg.ScatterPlotItem):
                                x_data, y_data = item.getData()
                                if x_data is not None and y_data is not None:
                                    for i_sp in range(len(x_data)):
                                        pt_pixel = vb.mapViewToScene(pg.Point(x_data[i_sp], y_data[i_sp]))
                                        dist_px = np.hypot(pos.x() - pt_pixel.x(), pos.y() - pt_pixel.y())
                                        if dist_px < 22.0 and dist_px < menor_dist_px:
                                            menor_dist_px = dist_px
                                            melhor_rec = rec
                                            melhor_sample_idx = i_sp
                                            melhor_plot = plot_item
                                            melhor_pt_x, melhor_pt_y = x_data[i_sp], y_data[i_sp]
                            elif isinstance(item, pg.PlotDataItem):
                                x_arr, y_arr = item.xData, item.yData
                                if x_arr is not None and y_arr is not None:
                                    for i_sp in range(len(x_arr)):
                                        pt_pixel = vb.mapViewToScene(pg.Point(x_arr[i_sp], y_arr[i_sp]))
                                        dist_px = np.hypot(pos.x() - pt_pixel.x(), pos.y() - pt_pixel.y())
                                        if dist_px < 22.0 and dist_px < menor_dist_px:
                                            menor_dist_px = dist_px
                                            melhor_rec = rec
                                            melhor_sample_idx = 0
                                            melhor_plot = plot_item
                                            melhor_pt_x, melhor_pt_y = x_arr[i_sp], y_arr[i_sp]
                break

        if melhor_rec:
            if hover_decay_coords is not None:
                self.atualizar_destaque_visual_hover(target_plot=self.plot_coil_decay, line_coords=hover_decay_coords)
            elif melhor_plot is not None and melhor_pt_x is not None:
                simb = obter_simbolo_material(melhor_rec.get("material"))
                self.atualizar_destaque_visual_hover(target_plot=melhor_plot, pt_coords=(melhor_pt_x, melhor_pt_y), symbol=simb)

            n_tot = melhor_rec.get("num_samples", 1)
            if melhor_sample_idx is not None and n_tot > 1:
                tau_pt = melhor_rec.get("all_taus", [melhor_rec["tau"]])[melhor_sample_idx]
                auc_pt = melhor_rec.get("all_aucs", [melhor_rec["auc"]])[melhor_sample_idx]
                l_pt = melhor_rec.get("all_l_efetivas", [melhor_rec["l_efetiva_uh"]])[melhor_sample_idx]
                sample_str = f"{melhor_rec['id_amostra']} (Amostra {melhor_sample_idx+1}/{n_tot})"
            else:
                tau_pt = melhor_rec["tau"]
                auc_pt = melhor_rec["auc"]
                l_pt = melhor_rec["l_efetiva_uh"]
                sample_str = f"{melhor_rec['id_amostra']}"

            estilo_nome = {
                "A36 Comum": "Contínua (Solid)",
                "A36 GE": "Tracejada (Dash)",
                "A36 GF": "Pontilhada (Dot)",
                "Estrutura Torre": "Traço-Ponto (DashDot)",
                "Ar Livre": "Contínua (Solid)"
            }.get(melhor_rec.get("material"), "Padrão")

            manual_adj = "Sim" if melhor_rec.get("ajuste_manual_liftoff", False) else "Não"
            local_str = melhor_rec.get("local", "Não Especificado")
            ind_uh = melhor_rec.get("indutancia_uh", 0.0)

            cursor_info = ""
            if hover_decay_pt is not None:
                cursor_info = f"⏱️ <b>Ponto Cursor:</b> t = {hover_decay_pt[0]:.2f} &mu;s | V(t) = {hover_decay_pt[1]:.1f} ADC Counts<br>"

            header_title = "📈 <b>CURVA TRANSIENTE COMPARATIVA DE DECAIMENTO V(t)</b>" if hover_decay_pt is not None else "📍 <b>PONTO DE CARACTERIZAÇÃO LIFT-OFF</b>"

            tooltip_text = (
                f"{header_title}<br>"
                f"--------------------------------------------------<br>"
                f"📁 <b>Referência de Arquivo:</b> {melhor_rec['filename']}<br>"
                f"🛡️ <b>Material:</b> {melhor_rec['material']} <i>[{estilo_nome}]</i><br>"
                f"📊 <b>Estado / Classe de Corrosão:</b> {melhor_rec['classe'].capitalize()}<br>"
                f"🆔 <b>Amostra (ID):</b> {sample_str}<br>"
                f"📍 <b>Local de Coleta:</b> {local_str}<br>"
                f"🧲 <b>Sensor / Bobina:</b> ID {melhor_rec['id_bobina']} (L<sub>nom</sub> = {ind_uh:.1f} &mu;H)<br>"
                f"📏 <b>Afastamento (Lift-Off):</b> {melhor_rec['distancia_mm']:.2f} mm<br>"
                f"--------------------------------------------------<br>"
                f"{cursor_info}"
                f"⚡ <b>Constante de Tempo (&tau;):</b> {tau_pt:.4f} &mu;s<br>"
                f"📐 <b>Área Sob a Curva (AUC):</b> {auc_pt:.1f} Counts.&mu;s<br>"
                f"🧲 <b>Indutância Efetiva (L<sub>ef</sub>):</b> {l_pt:.2f} &mu;H<br>"
                f"🔧 <b>Ajuste Manual Lift-Off:</b> {manual_adj}<br>"
                f"📊 <b>Amostragens no Lote:</b> N = {n_tot}"
            )

            target_p = self.plot_coil_decay if hover_decay_coords is not None else melhor_plot
            self.floating_tooltip.exibir_hover(QtGui.QCursor.pos(), tooltip_text, target_plot=target_p)
        else:
            self.atualizar_destaque_visual_hover(target_plot=None)

    def reorganizar_grid_widgets(self, grid_layout, widgets_list, num_cols):
        if not grid_layout or not widgets_list:
            return
        if num_cols < 1:
            num_cols = 1
        if getattr(grid_layout, '_current_cols', None) == num_cols:
            return
        grid_layout._current_cols = num_cols

        for i in reversed(range(grid_layout.count())):
            item = grid_layout.takeAt(i)
            if item and item.widget():
                item.widget().hide()

        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(4)

        for c_idx in range(num_cols + 2):
            grid_layout.setColumnStretch(c_idx, 0)

        for idx, w in enumerate(widgets_list):
            r = idx // num_cols
            c = idx % num_cols
            w.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Preferred)
            grid_layout.addWidget(w, r, c, QtCore.Qt.AlignLeft)
            w.setVisible(True)
            w.show()

        grid_layout.setColumnStretch(num_cols, 1)

        parent_w = grid_layout.parentWidget()
        if parent_w:
            parent_w.updateGeometry()
            parent_w.adjustSize()
            parent_w.setVisible(True)
            parent_w.show()

    def calcular_num_colunas_auto(self, widgets_list, grid_layout, pos=None):
        """
        Calcula o número ideal de colunas para cada campo individualmente
        com base na largura real do menu lateral (pos ou scroll_coil.viewport).
        """
        if not widgets_list:
            return 3

        avail_w = 0
        if pos is not None and isinstance(pos, int) and pos > 50:
            avail_w = pos - 130
        elif hasattr(self, 'scroll_coil') and self.scroll_coil and self.scroll_coil.viewport().width() > 50:
            avail_w = self.scroll_coil.viewport().width() - 130
        elif hasattr(self, 'splitter_tab_coil') and self.splitter_tab_coil and self.splitter_tab_coil.sizes()[0] > 50:
            avail_w = self.splitter_tab_coil.sizes()[0] - 130

        if avail_w <= 50:
            return 1

        max_item_w = 0
        fm = QtGui.QFontMetrics(widgets_list[0].font())
        for w in widgets_list:
            if hasattr(w, 'text') and w.text():
                w_needed = fm.horizontalAdvance(w.text()) + 28
                if w_needed > max_item_w:
                    max_item_w = w_needed

        if max_item_w <= 0:
            max_item_w = 90

        cols = max(1, avail_w // max_item_w)
        return min(cols, len(widgets_list))

    def obter_num_colunas_para_grid(self, grid_layout, widgets_list, pos=None, is_sensor_grid=False):
        combo = getattr(self, 'combo_num_colunas_bobinas' if is_sensor_grid else 'combo_num_colunas_painel', None)
        if combo:
            txt = combo.currentText()
            if "1" in txt:
                return 1
            elif "2" in txt:
                return 2
            elif "3" in txt:
                return 3
            elif "4" in txt:
                return 4
            elif "5" in txt:
                return 5
        return self.calcular_num_colunas_auto(widgets_list, grid_layout, pos=pos)

    def reorganizar_colunas_seletores_caracterizacao(self, pos=None, index=None):
        if hasattr(self, 'combo_num_colunas_bobinas') and "Auto" not in self.combo_num_colunas_bobinas.currentText():
            if hasattr(self, 'layout_radio_bobinas'):
                self.layout_radio_bobinas._current_cols = None

        if hasattr(self, 'combo_num_colunas_painel') and "Auto" not in self.combo_num_colunas_painel.currentText():
            for grid_attr in ['layout_spacers_grid', 'layout_mat_grid', 'layout_cls_grid', 'layout_locais_grid', 'layout_num_amostras_grid']:
                if hasattr(self, grid_attr):
                    getattr(self, grid_attr)._current_cols = None

        if hasattr(self, 'lista_widgets_radio_bobinas') and hasattr(self, 'layout_radio_bobinas') and self.lista_widgets_radio_bobinas:
            n_cols = self.obter_num_colunas_para_grid(self.layout_radio_bobinas, self.lista_widgets_radio_bobinas, pos=pos, is_sensor_grid=True)
            self.reorganizar_grid_widgets(self.layout_radio_bobinas, self.lista_widgets_radio_bobinas, n_cols)

        if hasattr(self, 'lista_widgets_spacers') and hasattr(self, 'layout_spacers_grid') and self.lista_widgets_spacers:
            n_cols = self.obter_num_colunas_para_grid(self.layout_spacers_grid, self.lista_widgets_spacers, pos=pos, is_sensor_grid=False)
            self.reorganizar_grid_widgets(self.layout_spacers_grid, self.lista_widgets_spacers, n_cols)

        if hasattr(self, 'lista_widgets_materiais') and hasattr(self, 'layout_mat_grid') and self.lista_widgets_materiais:
            n_cols = self.obter_num_colunas_para_grid(self.layout_mat_grid, self.lista_widgets_materiais, pos=pos, is_sensor_grid=False)
            self.reorganizar_grid_widgets(self.layout_mat_grid, self.lista_widgets_materiais, n_cols)

        if hasattr(self, 'lista_widgets_classes') and hasattr(self, 'layout_cls_grid') and self.lista_widgets_classes:
            n_cols = self.obter_num_colunas_para_grid(self.layout_cls_grid, self.lista_widgets_classes, pos=pos, is_sensor_grid=False)
            self.reorganizar_grid_widgets(self.layout_cls_grid, self.lista_widgets_classes, n_cols)

        if hasattr(self, 'lista_widgets_locais') and hasattr(self, 'layout_locais_grid') and self.lista_widgets_locais:
            n_cols = self.obter_num_colunas_para_grid(self.layout_locais_grid, self.lista_widgets_locais, pos=pos, is_sensor_grid=False)
            self.reorganizar_grid_widgets(self.layout_locais_grid, self.lista_widgets_locais, n_cols)

        if hasattr(self, 'lista_widgets_num_amostras') and hasattr(self, 'layout_num_amostras_grid') and self.lista_widgets_num_amostras:
            n_cols = self.obter_num_colunas_para_grid(self.layout_num_amostras_grid, self.lista_widgets_num_amostras, pos=pos, is_sensor_grid=False)
            self.reorganizar_grid_widgets(self.layout_num_amostras_grid, self.lista_widgets_num_amostras, n_cols)

    def obter_num_amostras_selecionado(self):
        if hasattr(self, 'group_num_amostras') and self.group_num_amostras.checkedButton():
            return self.group_num_amostras.checkedButton().property("val_n")
        return 1

    def toggle_painel_lateral_caracterizacao(self):
        if not hasattr(self, 'splitter_tab_coil'):
            return
        left_widget = self.splitter_tab_coil.widget(0)
        if left_widget:
            vis = left_widget.isVisible()
            left_widget.setVisible(not vis)
            if vis:
                self.btn_toggle_coil_left.setText("▶ Exibir Painel Lateral")
            else:
                self.btn_toggle_coil_left.setText("◀ Esconder Painel Lateral")

    def obter_material_selecionado(self):
        if hasattr(self, 'group_materiais') and self.group_materiais.checkedButton():
            return self.group_materiais.checkedButton().text()
        return "Ar Livre"

    def obter_classe_selecionada(self):
        if hasattr(self, 'group_classes') and self.group_classes.checkedButton():
            return self.group_classes.checkedButton().text()
        return "Saudável"

    def ao_alterar_material_caracterizacao(self, button):
        if not button or not button.isChecked():
            return
        mat_nome = button.text()
        
        if getattr(self, '_syncing_mat_cls', False):
            return

        self._syncing_mat_cls = True
        try:
            if mat_nome == "Ar Livre":
                # Ao selecionar Ar Livre como material, a classe deve ser sempre Ar Livre
                if "Ar Livre" in self.chk_classes:
                    self.chk_classes["Ar Livre"].setChecked(True)
            else:
                # Ao selecionar um metal, o estado de corrosao NUNCA pode ser Ar Livre. Se estivesse Ar Livre, muda para Saudavel
                classe_atual = self.obter_classe_selecionada()
                if classe_atual == "Ar Livre":
                    if "Saudável" in self.chk_classes:
                        self.chk_classes["Saudável"].setChecked(True)
        finally:
            self._syncing_mat_cls = False

    def ao_alterar_classe_caracterizacao(self, button):
        if not button or not button.isChecked():
            return
        cls_nome = button.text()

        if getattr(self, '_syncing_mat_cls', False):
            return

        self._syncing_mat_cls = True
        try:
            if cls_nome == "Ar Livre":
                # Se o estado for Ar Livre, o material deve ser sempre Ar Livre
                if "Ar Livre" in self.chk_materiais:
                    self.chk_materiais["Ar Livre"].setChecked(True)
            else:
                # Se o estado for metalico (Saudavel, Leve, etc.), o material NUNCA pode ser Ar Livre
                mat_atual = self.obter_material_selecionado()
                if mat_atual == "Ar Livre":
                    for m_nome, chk_m in self.chk_materiais.items():
                        if m_nome != "Ar Livre":
                            chk_m.setChecked(True)
                            break
        finally:
            self._syncing_mat_cls = False

    def obter_locais_amostra_selecionados(self):
        if hasattr(self, 'group_locais') and self.group_locais.checkedButton():
            return self.group_locais.checkedButton().text()
        locais_sel = [nome for nome, chk in getattr(self, 'chk_locais', {}).items() if chk.isChecked()]
        if not locais_sel:
            return "Não Especificado"
        return locais_sel[0]

    def obter_especificacoes_bobina_atuais(self):
        if hasattr(self, 'active_coil_info') and self.active_coil_info:
            return self.active_coil_info
        coils = self.coil_manager.get_all_coils()
        if coils:
            return list(coils.values())[0]
        return self.coil_manager.register_coil("681", 660.9, 2.2, 14.7, 8.5, 150, "27", 0.361, "PLA")

    def obter_base_selecionada(self):
        if hasattr(self, 'chk_berco_maior') and self.chk_berco_maior.isChecked():
            return "G"
        return "P"

    def gravar_ensaio_caracterizacao(self):
        if self.last_valores is None or len(self.last_valores) < 60:
            QtWidgets.QMessageBox.warning(self, "Sem Dados", "Não há curva capturada para gravar! Inicie a leitura primeiro.")
            return

        coil_info = self.obter_especificacoes_bobina_atuais()
        dist_mm = self.spin_liftoff_dist.value()
        material = self.obter_material_selecionado()
        classe = self.obter_classe_selecionada()
        sample_id = self.edit_coil_sample_id.text().strip()
        local_sel = self.obter_locais_amostra_selecionados()
        target_n = self.obter_num_amostras_selecionado()
        base_sel = self.obter_base_selecionada()

        manual_flag = getattr(self, 'liftoff_manual_override', False)
        if target_n == 1:
            try:
                filepath = self.coil_manager.save_characterization_record(
                    output_dir=self.caracterizacao_dir,
                    id_amostra=sample_id,
                    coil_info=coil_info,
                    distance_mm=dist_mm,
                    material=material,
                    classe=classe,
                    dt_us=self.dt_us,
                    curves=list(self.last_valores),
                    local=local_sel,
                    ajuste_manual_liftoff=manual_flag,
                    base=base_sel
                )

                rec = self.coil_manager.read_characterization_csv(filepath)
                if rec:
                    self.loaded_coil_records.append(rec)
                    item_text = f"Bobina {rec['id_bobina']} (Base {rec.get('base', 'P')}) | {rec['distancia_mm']}mm | {rec['material']} ({rec['local']}) ({rec['classe']}) [N=1] - {rec['filename']}"
                    item = QtWidgets.QListWidgetItem(item_text)
                    item.setData(QtCore.Qt.UserRole, rec)
                    item.setSelected(True)
                    self.list_imported_coil_files.addItem(item)
                    self.atualizar_graficos_comparacao_bobinas()

                QtWidgets.QMessageBox.information(
                    self, "Ensaio Gravado",
                    f"Ensaio de caracterização com 1 amostra gravado com sucesso!\n\nBase: {base_sel}\nLocal: {local_sel}\nAjuste Manual Lift-Off: {'Sim' if manual_flag else 'Não'}\nArquivo:\n{os.path.basename(filepath)}"
                )
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Erro ao Gravar", f"Erro ao gravar arquivo de caracterização: {e}")
        else:
            if self.leitura_ativa:
                self.coil_recording_target_n = target_n
                self.coil_recording_buffer = []
                self.coil_recording_sample_id = sample_id
                self.coil_recording_coil_info = coil_info
                self.coil_recording_dist_mm = dist_mm
                self.coil_recording_material = material
                self.coil_recording_classe = classe
                self.coil_recording_local = local_sel
                self.coil_recording_manual_liftoff = manual_flag
                self.coil_recording_base = base_sel
                self.is_recording_coil_multisample = True
                
                self.btn_record_coil_test.setEnabled(False)
                self.btn_record_coil_test.setText(f"⏳ Coletando (0 / {target_n} amostras)...")
            else:
                avail_curves = list(self.recent_curves)
                if not avail_curves:
                    QtWidgets.QMessageBox.warning(
                        self, "Leitura Inativa",
                        f"Para coletar {target_n} amostras em tempo real, inicie a leitura serial contínua!"
                    )
                    return
                
                curves_to_save = [avail_curves[i % len(avail_curves)] for i in range(target_n)]
                filepath = self.coil_manager.save_characterization_record(
                    output_dir=self.caracterizacao_dir,
                    id_amostra=sample_id,
                    coil_info=coil_info,
                    distance_mm=dist_mm,
                    material=material,
                    classe=classe,
                    dt_us=self.dt_us,
                    curves=curves_to_save,
                    local=local_sel,
                    ajuste_manual_liftoff=manual_flag,
                    base=base_sel
                )

                rec = self.coil_manager.read_characterization_csv(filepath)
                if rec:
                    self.loaded_coil_records.append(rec)
                    item_text = f"Bobina {rec['id_bobina']} (Base {rec.get('base', 'P')}) | {rec['distancia_mm']}mm | {rec['material']} ({rec['local']}) ({rec['classe']}) [N={rec['num_samples']}] - {rec['filename']}"
                    item = QtWidgets.QListWidgetItem(item_text)
                    item.setData(QtCore.Qt.UserRole, rec)
                    item.setSelected(True)
                    self.list_imported_coil_files.addItem(item)
                    self.atualizar_graficos_comparacao_bobinas()

                QtWidgets.QMessageBox.information(
                    self, "Ensaio Gravado",
                    f"Ensaio de {target_n} amostras gravado com sucesso no mesmo arquivo CSV!\n\nBase: {base_sel}\nLocal: {local_sel}\nAjuste Manual Lift-Off: {'Sim' if manual_flag else 'Não'}\nArquivo:\n{os.path.basename(filepath)}"
                )

    def finalizar_gravacao_multiamostras_caracterizacao(self):
        try:
            filepath = self.coil_manager.save_characterization_record(
                output_dir=self.caracterizacao_dir,
                id_amostra=self.coil_recording_sample_id,
                coil_info=self.coil_recording_coil_info,
                distance_mm=self.coil_recording_dist_mm,
                material=self.coil_recording_material,
                classe=self.coil_recording_classe,
                dt_us=self.dt_us,
                curves=self.coil_recording_buffer,
                local=getattr(self, 'coil_recording_local', 'Não Especificado'),
                ajuste_manual_liftoff=getattr(self, 'coil_recording_manual_liftoff', False),
                base=getattr(self, 'coil_recording_base', 'P')
            )

            rec = self.coil_manager.read_characterization_csv(filepath)
            if rec:
                self.loaded_coil_records.append(rec)
                item_text = f"Bobina {rec['id_bobina']} (Base {rec.get('base', 'P')}) | {rec['distancia_mm']}mm | {rec['material']} ({rec['local']}) ({rec['classe']}) [N={rec['num_samples']}] - {rec['filename']}"
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(QtCore.Qt.UserRole, rec)
                item.setSelected(True)
                self.list_imported_coil_files.addItem(item)
                self.atualizar_graficos_comparacao_bobinas()

            QtWidgets.QMessageBox.information(
                self, "Ensaio Gravado",
                f"Ensaio de {len(self.coil_recording_buffer)} amostras gravado com sucesso no mesmo arquivo CSV:\n{os.path.basename(filepath)}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro ao Gravar", f"Erro ao gravar arquivo de caracterização: {e}")
        finally:
            self.btn_record_coil_test.setText("Gravar Ensaio de Caracterização")
            self.btn_record_coil_test.setEnabled(True)
            self.coil_recording_buffer = []

    def importar_csvs_caracterizacao(self):
        os.makedirs(self.caracterizacao_dir, exist_ok=True)
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Importar Testes CSV de Caracterização",
            self.caracterizacao_dir,
            "Arquivos CSV (*.csv)"
        )
        if not files:
            return

        recs = self.coil_manager.read_multiple_csvs(files)
        if not recs:
            QtWidgets.QMessageBox.warning(self, "Importação Falhou", "Nenhum arquivo CSV válido de caracterização foi encontrado.")
            return

        count_added = 0
        if hasattr(self, 'list_imported_coil_files'):
            self.list_imported_coil_files.blockSignals(True)
        for rec in recs:
            # Evita duplicatas pelo caminho do arquivo
            if not any(r["filepath"] == rec["filepath"] for r in self.loaded_coil_records):
                self.loaded_coil_records.append(rec)
                item_text = f"Bobina {rec['id_bobina']} (Base {rec.get('base', 'P')}) | {rec['distancia_mm']}mm | {rec['material']} ({rec['classe']}) - {rec['filename']}"
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(QtCore.Qt.UserRole, rec)
                item.setSelected(True)
                if hasattr(self, 'list_imported_coil_files'):
                    self.list_imported_coil_files.addItem(item)
                count_added += 1
        if hasattr(self, 'list_imported_coil_files'):
            self.list_imported_coil_files.blockSignals(False)

        self._rt_bg_rebuild_needed = True
        self.atualizar_graficos_comparacao_bobinas()
        if hasattr(self, 'tab_sub_caracterizacao') and self.tab_sub_caracterizacao.currentIndex() == 1:
            self.atualizar_graficos_tempo_real_caracterizacao()
        elif hasattr(self, 'tab_sub_caracterizacao') and self.tab_sub_caracterizacao.currentIndex() == 2:
            self.atualizar_graficos_estatistica_caracterizacao()

        QtWidgets.QMessageBox.information(self, "Importação Concluída", f"{count_added} arquivo(s) carregado(s) com sucesso!")

    def limpar_comparacao_bobinas(self):
        self.loaded_coil_records.clear()
        self.list_imported_coil_files.clear()
        self.plot_coil_decay.clear()
        self.plot_coil_tau_liftoff.clear()
        self.plot_coil_auc_liftoff.clear()
        self.plot_coil_l_liftoff.clear()
        self.txt_coil_report.clear()
    def obter_janela_media_movel_selecionada(self):
        if hasattr(self, 'chk_ma_10') and self.chk_ma_10.isChecked():
            return 10
        if hasattr(self, 'chk_ma_50') and self.chk_ma_50.isChecked():
            return 50
        if hasattr(self, 'chk_ma_100') and self.chk_ma_100.isChecked():
            return 100
        if hasattr(self, 'chk_ma_1000') and self.chk_ma_1000.isChecked():
            return 1000
        return 0

    def _on_ma_checkbox_clicked(self):
        sender = self.sender()
        if sender and sender.isChecked():
            for chk in [getattr(self, 'chk_ma_10', None), getattr(self, 'chk_ma_50', None), getattr(self, 'chk_ma_100', None), getattr(self, 'chk_ma_1000', None)]:
                if chk and chk is not sender:
                    chk.blockSignals(True)
                    chk.setChecked(False)
                    chk.blockSignals(False)
        self._atualizar_texto_chk_rate_samples()
        if hasattr(self, '_fullscreen_dialogs_ativos'):
            for d in list(self._fullscreen_dialogs_ativos):
                if hasattr(d, 'floating_hud') and d.floating_hud is not None:
                    d.floating_hud.sync_from_main()
        self._rt_live_history = []
        self._rt_trend_buffer = []
        self._last_rt_trend_update_time = 0.0
        self.atualizar_todos_graficos_caracterizacao()

    def _atualizar_texto_chk_rate_samples(self):
        if hasattr(self, 'chk_rate_samples'):
            n = self.obter_janela_media_movel_selecionada()
            if n <= 0: n = 50
            self.chk_rate_samples.setText(f"Por Lote ({n} amostras)")
            self.chk_rate_samples.setToolTip(f"Atualiza a tendência somente após receber o lote completo de {n} curvas da serial.")

    def _on_rate_checkbox_clicked(self):
        sender = self.sender()
        if not sender:
            return
        
        all_chks = [
            getattr(self, 'chk_rate_05s', None),
            getattr(self, 'chk_rate_1s', None),
            getattr(self, 'chk_rate_2s', None),
            getattr(self, 'chk_rate_5s', None),
            getattr(self, 'chk_rate_10s', None),
            getattr(self, 'chk_rate_samples', None)
        ]
        
        if sender.isChecked():
            for chk in all_chks:
                if chk and chk != sender:
                    chk.blockSignals(True)
                    chk.setChecked(False)
                    chk.blockSignals(False)
        else:
            sender.blockSignals(True)
            sender.setChecked(True)
            sender.blockSignals(False)

        if hasattr(self, '_fullscreen_dialogs_ativos'):
            for d in list(self._fullscreen_dialogs_ativos):
                if hasattr(d, 'floating_hud') and d.floating_hud is not None:
                    d.floating_hud.sync_from_main()

        self._last_rt_trend_update_time = 0.0
        if hasattr(self, 'tab_sub_caracterizacao') and self.tab_sub_caracterizacao.currentIndex() == 1:
            self.atualizar_graficos_tempo_real_caracterizacao(force_refresh=True)

    def obter_taxa_atualizacao_sinais_selecionada(self):
        """Retorna o período de atualização dos sinais em segundos (0.5, 1.0, 2.0, 5.0, 10.0) ou 'samples'."""
        if hasattr(self, 'chk_rate_samples') and self.chk_rate_samples.isChecked():
            return 'samples'
        if hasattr(self, 'chk_rate_10s') and self.chk_rate_10s.isChecked():
            return 10.0
        if hasattr(self, 'chk_rate_5s') and self.chk_rate_5s.isChecked():
            return 5.0
        if hasattr(self, 'chk_rate_2s') and self.chk_rate_2s.isChecked():
            return 2.0
        if hasattr(self, 'chk_rate_1s') and self.chk_rate_1s.isChecked():
            return 1.0
        return 0.5

    def atualizar_todos_graficos_caracterizacao(self, *args):
        self._rt_bg_rebuild_needed = True
        self.atualizar_graficos_comparacao_bobinas()
        if hasattr(self, 'tab_sub_caracterizacao'):
            idx = self.tab_sub_caracterizacao.currentIndex()
            if idx == 1:
                self.atualizar_graficos_tempo_real_caracterizacao(force_refresh=True)
            elif idx == 2:
                self.atualizar_graficos_estatistica_caracterizacao()
        else:
            self.atualizar_graficos_estatistica_caracterizacao()

    def atualizar_graficos_comparacao_bobinas(self):
        # Limpa plots
        self.plot_coil_decay.clear()
        self.plot_coil_tau_liftoff.clear()
        self.plot_coil_auc_liftoff.clear()
        self.plot_coil_l_liftoff.clear()

        # Coleta itens selecionados na lista
        selected_items = self.list_imported_coil_files.selectedItems()
        recs_para_plotar = [item.data(QtCore.Qt.UserRole) for item in selected_items if item.data(QtCore.Qt.UserRole)]

        if not recs_para_plotar:
            recs_para_plotar = self.loaded_coil_records

        if not recs_para_plotar:
            self.txt_coil_report.setText("Nenhum registro selecionado.")
            return

        # Aplica Filtros de Exibição (Materiais e Classes)
        if hasattr(self, 'coil_filter_checkboxes_material'):
            mats_ok = [m for m, chk in self.coil_filter_checkboxes_material.items() if chk.isChecked()]
            cls_map = {
                "Saudável": getattr(self, 'chk_coil_filter_saudavel', None),
                "Leve": getattr(self, 'chk_coil_filter_leve', None),
                "Moderada": getattr(self, 'chk_coil_filter_moderada', None),
                "Avançada": getattr(self, 'chk_coil_filter_avancada', None),
                "Corroído": getattr(self, 'chk_coil_filter_corroido', None),
                "Ar Livre": getattr(self, 'chk_coil_filter_ar_cls', None),
                "Não Definido": getattr(self, 'chk_coil_filter_nao_definido', None)
            }
            cls_ok = [c for c, chk in cls_map.items() if chk is None or chk.isChecked()]
            recs_para_plotar = [r for r in recs_para_plotar if r.get("material", "A36 Comum") in mats_ok and r.get("classe", "Saudável") in cls_ok]

        if not recs_para_plotar:
            self.txt_coil_report.setText("Nenhum registro corresponde aos filtros de exibição selecionados.")
            return

        # Cores para curvas
        paleta_cores = ["#00e676", "#29b6f6", "#ab47bc", "#ffca28", "#ff7043", "#ec407a", "#26a69a", "#78909c", "#e040fb", "#18ffff"]
        
        use_id_shading = hasattr(self, 'chk_diferenciar_ids_tonalidade') and self.chk_diferenciar_ids_tonalidade.isChecked()

        # Mapeamento de tonalidade (luminosidade HSL) por arquivo/amostra se use_id_shading for True
        id_to_lightness = {}
        if use_id_shading and recs_para_plotar:
            ids_unicos = sorted(list(set([str(r.get("id_amostra", r.get("filename", ""))) for r in recs_para_plotar])))
            num_ids = len(ids_unicos)
            for idx_id, id_val in enumerate(ids_unicos):
                l_factor = 0.35 + 0.50 * (idx_id / max(1, num_ids - 1)) if num_ids > 1 else 0.55
                id_to_lightness[id_val] = l_factor

        # 1. Plotar Curvas Transientes V(t) usando as cores padronizadas e tracejados por Material
        for idx, rec in enumerate(recs_para_plotar):
            cor_base_hex = obter_cor_classe(rec.get("classe", "Saudável"))
            if use_id_shading:
                base_qcol = QtGui.QColor(cor_base_hex)
                h, s, l_val, a_alpha = base_qcol.getHslF()
                target_l = id_to_lightness.get(str(rec.get("id_amostra", rec.get("filename", ""))), 0.55)
                cor_hex = QtGui.QColor.fromHslF(h, min(1.0, s * 1.05), max(0.25, min(0.90, target_l))).name()
            else:
                cor_hex = cor_base_hex

            estilo = obter_estilo_material(rec.get("material", "A36 Comum"))
            t_us = np.arange(len(rec["curva"])) * rec["dt_us"]
            label = f"B.{rec['id_bobina']} ({rec['distancia_mm']}mm, {rec['material']}, {rec['classe']})"
            
            # Se o CSV possui multi-amostras, plota amostragem de curvas translúcidas de fundo
            all_curves = rec.get("all_curves", [])
            if len(all_curves) > 1:
                pen_indiv = pg.mkPen(color=cor_hex, width=0.6, style=estilo)
                step_c = max(1, len(all_curves) // 20)
                for single_c in all_curves[::step_c]:
                    self.plot_coil_decay.plot(t_us, single_c, pen=pen_indiv)

            # Plota curva média com linha em destaque e estilo por material
            pen = pg.mkPen(color=cor_hex, width=2.5, style=estilo)
            curve_item = self.plot_coil_decay.plot(t_us, rec["curva"], pen=pen, name=label)
            curve_item.rec_data = rec

        # 2. Agrupar registros por (id_bobina, material, classe) para montar curvas de Lift-Off (vs distância)
        grupos = {}
        for rec in recs_para_plotar:
            key = (rec["id_bobina"], rec["material"], rec["classe"])
            if key not in grupos:
                grupos[key] = []
            grupos[key].append(rec)

        use_id_shading = hasattr(self, 'chk_diferenciar_ids_tonalidade') and self.chk_diferenciar_ids_tonalidade.isChecked()

        relatorio_txt = ["==========================================================================",
                         "RELATÓRIO DE CARACTERIZAÇÃO DE BOBINAS & ENSAIOS DE LIFT-OFF",
                         "=========================================================================="]

        for idx, (key, g_recs) in enumerate(grupos.items()):
            b_id, mat_name, cls_name = key
            # Ordena por distância crescente
            g_recs_sorted = sorted(g_recs, key=lambda x: x["distancia_mm"])
            dists = [r["distancia_mm"] for r in g_recs_sorted]
            taus = [r["tau"] for r in g_recs_sorted]
            aucs = [r["auc"] for r in g_recs_sorted]
            l_efetivas = [r["l_efetiva_uh"] for r in g_recs_sorted]

            cor_base = obter_cor_classe(cls_name)
            simbolo = obter_simbolo_material(mat_name)
            pen_mean = pg.mkPen(color=cor_base, width=2.5, style=obter_estilo_material(mat_name))
            symbol_pen = pg.mkPen(color=cor_base)

            label = f"Bobina {b_id} | {mat_name} ({cls_name})"

            ids_unicos = sorted(list(set([str(r.get("id_amostra", "1")) for r in g_recs_sorted])))
            num_ids = len(ids_unicos)
            id_to_lightness = {id_v: (0.35 + 0.50 * (i / max(1, num_ids - 1)) if num_ids > 1 else 0.55) for i, id_v in enumerate(ids_unicos)}

            # 2.1 Plotar todos os pontos individuais em lote (ScatterPlotItem vetorizado - 1000x mais rápido)
            for r in g_recs_sorted:
                d_val = r["distancia_mm"]
                id_str = str(r.get("id_amostra", "1"))
                all_t = np.array(r.get("all_taus", [r["tau"]]))
                all_a = np.array(r.get("all_aucs", [r["auc"]]))
                all_l = np.array(r.get("all_l_efetivas", [r["l_efetiva_uh"]]))

                # Aplica filtro IQR individualmente por arquivo / medição
                if hasattr(self, 'chk_coil_filter_outliers') and self.chk_coil_filter_outliers.isChecked() and len(all_t) >= 4:
                    q25_t, q75_t = np.percentile(all_t, [25, 75])
                    iqr_t = q75_t - q25_t
                    q25_a, q75_a = np.percentile(all_a, [25, 75])
                    iqr_a = q75_a - q25_a

                    mask = (all_t >= q25_t - 1.5 * iqr_t) & (all_t <= q75_t + 1.5 * iqr_t) & \
                           (all_a >= q25_a - 1.5 * iqr_a) & (all_a <= q75_a + 1.5 * iqr_a)
                    if np.sum(mask) >= 3:
                        all_t = all_t[mask]
                        all_a = all_a[mask]
                        all_l = all_l[mask]

                d_pts = [d_val] * len(all_t)

                base_qcol = QtGui.QColor(cor_base)
                if use_id_shading:
                    h, s, l_val, a_alpha = base_qcol.getHslF()
                    target_l = id_to_lightness.get(id_str, 0.55)
                    adj_qcol = QtGui.QColor.fromHslF(h, min(1.0, s * 1.05), max(0.25, min(0.90, target_l)))
                    adj_qcol.setAlpha(180)
                    brush_scatter = pg.mkBrush(adj_qcol)
                else:
                    brush_scatter = pg.mkBrush(cor_base)

                sp_t = pg.ScatterPlotItem(x=d_pts, y=all_t, symbol=simbolo, size=7, brush=brush_scatter, pen=None)
                sp_a = pg.ScatterPlotItem(x=d_pts, y=all_a, symbol=simbolo, size=7, brush=brush_scatter, pen=None)
                sp_l = pg.ScatterPlotItem(x=d_pts, y=all_l, symbol=simbolo, size=7, brush=brush_scatter, pen=None)
                sp_t.rec_data = r
                sp_a.rec_data = r
                sp_l.rec_data = r
                self.plot_coil_tau_liftoff.addItem(sp_t)
                self.plot_coil_auc_liftoff.addItem(sp_a)
                self.plot_coil_l_liftoff.addItem(sp_l)

            # 2.2 Plotar a linha média conectando as distâncias da série
            self.plot_coil_tau_liftoff.plot(dists, taus, pen=pen_mean, symbol=simbolo, symbolSize=16, symbolBrush=cor_base, symbolPen=symbol_pen, name=label)
            self.plot_coil_auc_liftoff.plot(dists, aucs, pen=pen_mean, symbol=simbolo, symbolSize=16, symbolBrush=cor_base, symbolPen=symbol_pen, name=label)
            self.plot_coil_l_liftoff.plot(dists, l_efetivas, pen=pen_mean, symbol=simbolo, symbolSize=16, symbolBrush=cor_base, symbolPen=symbol_pen, name=label)

            # Gera dados para o console de relatório
            relatorio_txt.append(f"\n>>> SERIE: Bobina {key[0]} | Material: {key[1]} | Classe: {key[2]}")
            relatorio_txt.append(f"    {'Dist (mm)':<10} | {'Tau (us)':<12} | {'AUC (Counts.us)':<18} | {'L Efetiva (uH)':<14} | {'N Amostras':<10}")
            relatorio_txt.append("    " + "-" * 72)
            for r in g_recs_sorted:
                n_str = f"N={r.get('num_samples', 1)}"
                relatorio_txt.append(f"    {r['distancia_mm']:<10.1f} | {r['tau']:<12.4f} | {r['auc']:<18.1f} | {r['l_efetiva_uh']:<14.2f} | {n_str:<10}")

            if len(dists) >= 2:
                delta_d = dists[-1] - dists[0]
                delta_tau = taus[-1] - taus[0]
                sens = (delta_tau / delta_d) if delta_d > 0 else 0.0
                relatorio_txt.append(f"    -> Sensibilidade dTau/dDist: {sens:+.4f} us/mm (na faixa {dists[0]}mm a {dists[-1]}mm)")

        self.txt_coil_report.setText("\n".join(relatorio_txt))

    def exportar_relatorio_bobinas(self):
        if not self.loaded_coil_records:
            QtWidgets.QMessageBox.warning(self, "Sem Dados", "Não há ensaios carregados para exportar o comparativo.")
            return

        dest_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Selecionar Pasta para Exportação", self.base_dir)
        if not dest_dir:
            return

        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = os.path.join(dest_dir, f"comparativo_bobinas_{ts_str}.png")
        html_path = os.path.join(dest_dir, f"relatorio_bobinas_{ts_str}.html")

        try:
            # Save PyQtGraph scene as image
            exporter = pg.exporters.ImageExporter(self.win_coil_plots.scene())
            exporter.export(img_path)

            # Save HTML report
            report_text = self.txt_coil_report.toPlainText().replace("\n", "<br>").replace(" ", "&nbsp;")
            html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Relatório Comparativo de Bobinas</title>
<style>body {{ background: #1e1e1e; color: #e1e1e6; font-family: monospace; padding: 20px; }} h2 {{ color: #29b6f6; }}</style>
</head>
<body>
<h2>📊 Relatório de Caracterização e Ensaios de Lift-Off</h2>
<p>Data do Relatório: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
<img src="{os.path.basename(img_path)}" style="max-width:100%; border: 1px solid #3a3a3c;"><br><br>
<div>{report_text}</div>
</body>
</html>"""
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            QtWidgets.QMessageBox.information(
                self, "Exportação Concluída",
                f"Relatório exportado com sucesso!\n\nImagem: {os.path.basename(img_path)}\nHTML: {os.path.basename(html_path)}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erro ao Exportar", f"Erro durante a exportação:\n{str(e)}")

    def ao_mudar_subaba_caracterizacao(self, index):
        if index == 0:
            self.atualizar_graficos_comparacao_bobinas()
        elif index == 1:
            self._rt_bg_rebuild_needed = True
            self.atualizar_graficos_tempo_real_caracterizacao(force_refresh=True)
        elif index == 2:
            self.atualizar_graficos_estatistica_caracterizacao()

    def atualizar_graficos_tempo_real_caracterizacao(self, force_refresh=False):
        if not hasattr(self, 'plot_coil_rt_decay'):
            return

        # Limite geral da interface para os overlays Live em tempo real (~28 FPS / 35ms)
        now = time.time()
        last_update = getattr(self, '_last_rt_plot_time', 0.0)
        rate_mode = self.obter_taxa_atualizacao_sinais_selecionada()
        buf = getattr(self, '_rt_trend_buffer', [])
        n_target = self.obter_janela_media_movel_selecionada()
        if n_target <= 0:
            n_target = 50
        batch_ready = (rate_mode == 'samples' and len(buf) >= n_target)
        if not force_refresh and not batch_ready and (now - last_update) < 0.035:
            return
        self._last_rt_plot_time = now

        recs = getattr(self, 'loaded_coil_records', [])
        selected_items = self.list_imported_coil_files.selectedItems() if hasattr(self, 'list_imported_coil_files') else []
        if selected_items:
            sel_recs = [item.data(QtCore.Qt.UserRole) for item in selected_items if item.data(QtCore.Qt.UserRole)]
            if sel_recs:
                recs = sel_recs

        use_id_shading = hasattr(self, 'chk_diferenciar_ids_tonalidade') and self.chk_diferenciar_ids_tonalidade.isChecked()

        # Verifica se os itens de fundo dos CSVs precisam ser reconstruídos
        need_bg_rebuild = getattr(self, '_rt_bg_rebuild_needed', True)
        if need_bg_rebuild:
            self.plot_coil_rt_decay.clear()
            self.plot_coil_rt_tau.clear()
            self.plot_coil_rt_auc.clear()
            self.plot_coil_rt_scatter.clear()
            self._rt_live_curve = None
            self._rt_ref_curve = None
            self._rt_star_item = None
            self._rt_tau_line = None
            self._rt_auc_line = None
            self._rt_tau_pt = None
            self._rt_auc_pt = None
            self._rt_ma_curve = None
            self._rt_tau_trend_line = None
            self._rt_tau_trend_pt = None
            self._rt_auc_trend_line = None
            self._rt_auc_trend_pt = None
            self._rt_star_trend_item = None
            self._last_saved_v_ma = None
            self._last_saved_tau_trend = 0.0
            self._last_saved_auc_trend = 0.0
            self._last_rt_trend_update_time = 0.0
            if hasattr(self, 'rt_stabilizer') and self.rt_stabilizer is not None:
                self.rt_stabilizer.reset()

            records_estat = []
            for r in recs:
                b_id = str(r.get("id_bobina", "N/A"))
                d_val = float(r.get("distancia_mm", 0.0))
                mat = str(r.get("material", "A36 Comum"))
                cls_name = str(r.get("classe", "Saudável"))

                all_t = r.get("all_taus", [r["tau"]])
                all_a = r.get("all_aucs", [r["auc"]])
                all_l = r.get("all_l_efetivas", [r["l_efetiva_uh"]])

                n_pts = min(len(all_t), len(all_a), len(all_l))
                for i in range(n_pts):
                    id_samp = str(r.get("id_amostra", f"{i+1}"))
                    records_estat.append({
                        "id_bobina": b_id,
                        "distancia_mm": d_val,
                        "material": mat,
                        "classe": cls_name,
                        "tau": float(all_t[i]),
                        "auc": float(all_a[i]),
                        "l_efetiva_uh": float(all_l[i]),
                        "id": id_samp,
                        "curva": r.get("curva", []),
                        "dt_us": r.get("dt_us", 0.1)
                    })

            if hasattr(self, 'coil_filter_checkboxes_material'):
                mats_ok = [m for m, chk in self.coil_filter_checkboxes_material.items() if chk.isChecked()]
                cls_map = {
                    "Saudável": getattr(self, 'chk_coil_filter_saudavel', None),
                    "Leve": getattr(self, 'chk_coil_filter_leve', None),
                    "Moderada": getattr(self, 'chk_coil_filter_moderada', None),
                    "Avançada": getattr(self, 'chk_coil_filter_avancada', None),
                    "Corroído": getattr(self, 'chk_coil_filter_corroido', None),
                    "Ar Livre": getattr(self, 'chk_coil_filter_ar_cls', None),
                    "Não Definido": getattr(self, 'chk_coil_filter_nao_definido', None)
                }
                cls_ok = [c for c, chk in cls_map.items() if chk is None or chk.isChecked()]
                records_estat = [a for a in records_estat if a["material"] in mats_ok and a["classe"] in cls_ok]

            # Aplica Filtro de Outliers (IQR) por arquivo / ensaio individual se selecionado
            if hasattr(self, 'chk_coil_filter_outliers') and self.chk_coil_filter_outliers.isChecked() and records_estat:
                grupos_file = {}
                for a in records_estat:
                    file_key = (a.get("id_bobina"), a.get("material"), a.get("classe"), a.get("distancia_mm"))
                    if file_key not in grupos_file:
                        grupos_file[file_key] = []
                    grupos_file[file_key].append(a)

                records_limpos = []
                for file_key, grupo in grupos_file.items():
                    if len(grupo) >= 4:
                        taus_g = [item["tau"] for item in grupo]
                        aucs_g = [item["auc"] for item in grupo]
                        q25_t, q75_t = np.percentile(taus_g, [25, 75])
                        iqr_t = q75_t - q25_t
                        q25_a, q75_a = np.percentile(aucs_g, [25, 75])
                        iqr_a = q75_a - q25_a

                        for item in grupo:
                            is_ok_t = (q25_t - 1.5 * iqr_t <= item["tau"] <= q75_t + 1.5 * iqr_t)
                            is_ok_a = (q25_a - 1.5 * iqr_a <= item["auc"] <= q75_a + 1.5 * iqr_a)
                            if is_ok_t and is_ok_a:
                                records_limpos.append(item)
                    else:
                        records_limpos.extend(grupo)

                records_estat = records_limpos

            self.records_rt_caracterizacao = records_estat

            if records_estat:
                ids_unicos = sorted(list(set([str(a["id"]) for a in records_estat])))
                num_ids = len(ids_unicos)
                id_to_lightness = {id_v: (0.35 + 0.50 * (i / max(1, num_ids - 1)) if num_ids > 1 else 0.55) for i, id_v in enumerate(ids_unicos)}

                for a_item in records_estat:
                    cor_base = obter_cor_classe(a_item["classe"])
                    simbolo = obter_simbolo_material(a_item["material"])
                    a_item["symbol"] = simbolo

                    base_qcol = QtGui.QColor(cor_base)
                    if use_id_shading:
                        h, s, l_val, a_alpha = base_qcol.getHslF()
                        target_l = id_to_lightness.get(str(a_item["id"]), 0.55)
                        adj_qcol = QtGui.QColor.fromHslF(h, min(1.0, s * 1.05), max(0.25, min(0.90, target_l)))
                        a_item["color_hex"] = adj_qcol.name()
                        a_item["brush"] = pg.mkBrush(adj_qcol)
                    else:
                        a_item["color_hex"] = cor_base
                        a_item["brush"] = pg.mkBrush(base_qcol)

                for idx, r in enumerate(recs):
                    cor_base_hex = obter_cor_classe(r.get("classe", "Saudável"))
                    if use_id_shading and recs:
                        base_qcol = QtGui.QColor(cor_base_hex)
                        h, s, l_val, a_alpha = base_qcol.getHslF()
                        target_l = id_to_lightness.get(str(r.get("id_amostra", r.get("filename", ""))), 0.55) if 'id_to_lightness' in locals() else 0.55
                        cor_hex = QtGui.QColor.fromHslF(h, min(1.0, s * 1.05), max(0.25, min(0.90, target_l))).name()
                    else:
                        cor_hex = cor_base_hex

                    estilo = obter_estilo_material(r.get("material", "A36 Comum"))
                    t_us = np.arange(len(r["curva"])) * r.get("dt_us", 0.1)
                    pen = pg.mkPen(color=cor_hex, width=1.5, style=estilo)
                    curve_st = self.plot_coil_rt_decay.plot(
                        t_us, r["curva"], pen=pen,
                        name=f"B.{r.get('id_bobina','')} ({r.get('distancia_mm',0)}mm, {r.get('material','')})"
                    )
                    curve_st.rec_data = r

                grupos_scatter = {}
                for a in records_estat:
                    d_val = a["distancia_mm"]
                    t_val = a["tau"]
                    a_val = a["auc"]
                    simb = a.get("symbol", "o")
                    color_hex = a.get("color_hex", "#3498db")

                    grp_key = (simb, color_hex)
                    if grp_key not in grupos_scatter:
                        grupos_scatter[grp_key] = {"d": [], "t": [], "a": [], "brush": a.get("brush", pg.mkBrush(color_hex))}
                    grupos_scatter[grp_key]["d"].append(d_val)
                    grupos_scatter[grp_key]["t"].append(t_val)
                    grupos_scatter[grp_key]["a"].append(a_val)

                for (simb, _), data in grupos_scatter.items():
                    b_pt = data["brush"]
                    self.plot_coil_rt_tau.addItem(pg.ScatterPlotItem(x=data["d"], y=data["t"], symbol=simb, size=7, brush=b_pt, pen=pg.mkPen('w', width=0.2)))
                    self.plot_coil_rt_auc.addItem(pg.ScatterPlotItem(x=data["d"], y=data["a"], symbol=simb, size=7, brush=b_pt, pen=pg.mkPen('w', width=0.2)))
                    self.plot_coil_rt_scatter.addItem(pg.ScatterPlotItem(x=data["t"], y=data["a"], symbol=simb, size=8, brush=b_pt, pen=pg.mkPen('w', width=0.2)))

            self._rt_bg_rebuild_needed = False

        # 2. Atualizar Overlays em TEMPO REAL (Alta Performance via setData/setValue)
        t = None
        v = None
        is_live_stream = False

        if hasattr(self, 'tempo_us') and hasattr(self, 'tensao_mv') and len(self.tempo_us) > 0:
            t = np.array(self.tempo_us)
            v = np.array(self.tensao_mv)
            is_live_stream = True
        elif recs:
            rec_fall = recs[0]
            curva_raw = rec_fall.get("curva", [])
            dt_raw = rec_fall.get("dt_us", getattr(self, 'dt_us', 0.1))
            if len(curva_raw) > 0:
                t = np.arange(len(curva_raw)) * dt_raw
                v = np.array(curva_raw)

        if t is not None and v is not None and len(t) > 0:
            exibir_tendencia = hasattr(self, 'chk_rt_exibir_tendencia') and self.chk_rt_exibir_tendencia.isChecked()

            # 1. Curva Medida Live (Verde Neon com 30% transparência e espessura fina 1.6)
            if not hasattr(self, '_rt_live_curve') or self._rt_live_curve is None or self._rt_live_curve not in self.plot_coil_rt_decay.items:
                pen_live = pg.mkPen(color=(0, 255, 0, 180), width=1.6)
                title_live = "Sinal Medido em Tempo Real (Osciloscópio Live)" if is_live_stream else "Sinal de Ensaio Carregado (Simulação Live)"
                self._rt_live_curve = self.plot_coil_rt_decay.plot(t, v, pen=pen_live, name=title_live)
                self._rt_live_curve.curve_title = title_live
            else:
                self._rt_live_curve.setData(t, v)

            # Processamento de Tendência Adaptativa Ultra-Estável (Fast-Attack & Zero-Jitter Lock)
            n_win = self.obter_janela_media_movel_selecionada()
            if n_win == 10:
                deadband = 0.008
                modo_nome = "Rápido (Sensível)"
            elif n_win == 50:
                deadband = 0.015
                modo_nome = "Equilibrado"
            elif n_win == 100:
                deadband = 0.022
                modo_nome = "Alta Estabilidade"
            elif n_win == 1000:
                deadband = 0.035
                modo_nome = "Travamento Máximo (Bancada)"
            else:
                deadband = 0.015
                modo_nome = "Equilibrado"

            rate_mode = self.obter_taxa_atualizacao_sinais_selecionada()
            buf = getattr(self, '_rt_trend_buffer', [])
            n_target = self.obter_janela_media_movel_selecionada()
            if n_target <= 0:
                n_target = 50

            if rate_mode == 'samples':
                rate_txt = f"Lote ({n_target} amostras)"
                need_trend_calc = force_refresh or len(buf) >= n_target or not hasattr(self, '_last_saved_v_ma') or self._last_saved_v_ma is None
            else:
                rate_s = float(rate_mode) if isinstance(rate_mode, (int, float)) else 0.5
                rate_txt = f"{rate_s:g}s"
                last_trend_time = getattr(self, '_last_rt_trend_update_time', 0.0)
                need_trend_calc = force_refresh or (now - last_trend_time) >= rate_s or not hasattr(self, '_last_saved_v_ma') or self._last_saved_v_ma is None

            v_ma = None
            tau_trend = 0.0
            auc_trend = 0.0

            if exibir_tendencia:
                if need_trend_calc:
                    if rate_mode == 'samples':
                        if len(buf) >= n_target:
                            batch = buf[:n_target]
                            self._rt_trend_buffer = buf[n_target:]
                        elif force_refresh and len(buf) > 0:
                            batch = buf
                        else:
                            batch = None

                        if batch is not None and len(batch) > 0:
                            if hasattr(self, 'chk_ma_50') and self.chk_ma_50.isChecked() and len(batch) >= 3:
                                v_calc = np.median(batch, axis=0)
                            elif hasattr(self, 'chk_ma_100') and self.chk_ma_100.isChecked() and len(batch) >= 4:
                                arr = np.sort(batch, axis=0)
                                trim = max(1, int(len(batch) * 0.15))
                                v_calc = np.mean(arr[trim:-trim], axis=0)
                            else:
                                v_calc = np.mean(batch, axis=0)
                            self._rt_trend_n_samples = len(batch)
                        elif v is not None and len(v) > 0:
                            v_calc = np.array(v, dtype=float)
                            self._rt_trend_n_samples = 1
                        else:
                            v_calc = getattr(self, '_last_saved_v_ma', None)
                    else:
                        # Modo por tempo (0.5s, 1s, 2s, 5s, 10s)
                        if buf and len(buf) > 0:
                            if hasattr(self, 'chk_ma_50') and self.chk_ma_50.isChecked() and len(buf) >= 3:
                                v_calc = np.median(buf, axis=0)
                            elif hasattr(self, 'chk_ma_100') and self.chk_ma_100.isChecked() and len(buf) >= 4:
                                arr = np.sort(buf, axis=0)
                                trim = max(1, int(len(buf) * 0.15))
                                v_calc = np.mean(arr[trim:-trim], axis=0)
                            else:
                                v_calc = np.mean(buf, axis=0)

                            self._rt_trend_n_samples = len(buf)
                            self._rt_trend_buffer = []
                        elif v is not None and len(v) > 0:
                            v_calc = np.array(v, dtype=float)
                            self._rt_trend_n_samples = 1
                        else:
                            v_calc = getattr(self, '_last_saved_v_ma', None)

                    if v_calc is not None and len(v_calc) > 0:
                        dt_u = getattr(self, 'dt_us', 0.1)
                        tau_calc, auc_calc = calcular_tau_e_auc(v_calc, dt_u)
                        self._last_saved_v_ma = v_calc
                        self._last_saved_tau_trend = tau_calc
                        self._last_saved_auc_trend = auc_calc
                        self._last_rt_trend_update_time = now
                        v_ma = v_calc
                        tau_trend = tau_calc
                        auc_trend = auc_calc
                    else:
                        v_ma = getattr(self, '_last_saved_v_ma', None)
                        tau_trend = getattr(self, '_last_saved_tau_trend', 0.0)
                        auc_trend = getattr(self, '_last_saved_auc_trend', 0.0)
                else:
                    v_ma = getattr(self, '_last_saved_v_ma', None)
                    tau_trend = getattr(self, '_last_saved_tau_trend', 0.0)
                    auc_trend = getattr(self, '_last_saved_auc_trend', 0.0)

            # Gráfico 1: Atualização da curva de tendência (Filtro Adaptativo Estabilizado)
            if exibir_tendencia and v_ma is not None and len(v_ma) > 0:
                if not hasattr(self, '_rt_ma_curve') or self._rt_ma_curve is None or self._rt_ma_curve not in self.plot_coil_rt_decay.items:
                    pen_ma = pg.mkPen(color='#76ff03', width=2.5)
                    title_ma = f"Sinal de Tendência (Modo {modo_nome})"
                    self._rt_ma_curve = self.plot_coil_rt_decay.plot(t, v_ma, pen=pen_ma, name=title_ma)
                    self._rt_ma_curve.curve_title = f"Curva de Tendência Estável ({modo_nome})"
                    self._rt_ma_curve.rec_data = {"filename": f"Tendência Live ({modo_nome})", "material": self.obter_material_selecionado(), "classe": self.obter_classe_selecionada()}
                else:
                    self._rt_ma_curve.setData(t, v_ma)
                    self._rt_ma_curve.curve_title = f"Curva de Tendência Estável ({modo_nome})"
                    self._rt_ma_curve.rec_data = {"filename": f"Tendência Live ({modo_nome})", "material": self.obter_material_selecionado(), "classe": self.obter_classe_selecionada()}
            else:
                if hasattr(self, '_rt_ma_curve') and self._rt_ma_curve is not None:
                    if self._rt_ma_curve in self.plot_coil_rt_decay.items:
                        self.plot_coil_rt_decay.removeItem(self._rt_ma_curve)
                    self._rt_ma_curve = None

            # Remove curva de referência estática legada se existente no gráfico de tempo real
            if hasattr(self, '_rt_ref_curve') and self._rt_ref_curve is None:
                pass
            elif hasattr(self, '_rt_ref_curve') and self._rt_ref_curve is not None:
                if self._rt_ref_curve in self.plot_coil_rt_decay.items:
                    self.plot_coil_rt_decay.removeItem(self._rt_ref_curve)
                self._rt_ref_curve = None

            fonte_txt = "Transmissão Serial USB/COM Ativa em Tempo Real" if is_live_stream else "Sinal de Ensaio CSV Carregado (Modo Offline / Demonstração)"

            live_tau = getattr(self, 'last_tau', 0.0)
            live_auc = getattr(self, 'last_auc', 0.0)
            d_liftoff = round(getattr(self, 'distancia_lift_off', self.spin_liftoff_dist.value() if hasattr(self, 'spin_liftoff_dist') else 0.0), 2)

            # Converte o Lift-Off para a escala do gráfico e encaixa na distância exata gravada nos CSVs
            recs_check = getattr(self, 'loaded_coil_records', [])
            has_large_dists = any(float(r.get("distancia_mm", 0.0)) > 10.0 for r in recs_check)
            if has_large_dists and d_liftoff < 10.0:
                d_liftoff_plot = round(d_liftoff * 1000.0, 1)
            else:
                d_liftoff_plot = d_liftoff

            # Snap de precisão para bater exatamente com a coordenada do arquivo CSV se a diferença for imperceptível (< 0.5 um / < 0.05 mm)
            if recs_check:
                for r in recs_check:
                    d_r = float(r.get("distancia_mm", 0.0))
                    d_r_scaled = d_r if (d_r > 10.0 or not has_large_dists) else d_r * 1000.0
                    if abs(d_r_scaled - d_liftoff_plot) < 0.5:
                        d_liftoff_plot = d_r_scaled
                        break

            # Se last_tau/last_auc não estiverem definidos na simulação, calcula na hora a partir do sinal
            if (live_tau <= 0 or live_auc <= 0) and v is not None and len(v) > 10:
                dt_u = getattr(self, 'dt_us', 0.1)
                live_tau, live_auc = calcular_tau_e_auc(v, dt_u)

            # Gráfico 2: Overlays Live (Amarelo Instantâneo) e Tendência Estável (Verde Lima)
            if live_tau > 0:
                if not hasattr(self, '_rt_tau_line') or self._rt_tau_line is None or self._rt_tau_line not in self.plot_coil_rt_tau.items:
                    self._rt_tau_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('#ffff00', width=1.5, style=QtCore.Qt.DashLine))
                    self.plot_coil_rt_tau.addItem(self._rt_tau_line)
                    self._rt_tau_pt = pg.ScatterPlotItem(x=[d_liftoff_plot], y=[live_tau], symbol='star', size=16, brush=pg.mkBrush('#f1c40f'), pen=pg.mkPen('w', width=1.5))
                    self.plot_coil_rt_tau.addItem(self._rt_tau_pt)
                else:
                    self._rt_tau_line.setValue(live_tau)
                    self._rt_tau_pt.setData(x=[d_liftoff_plot], y=[live_tau])

            if exibir_tendencia and tau_trend > 0:
                if not hasattr(self, '_rt_tau_trend_line') or self._rt_tau_trend_line is None or self._rt_tau_trend_line not in self.plot_coil_rt_tau.items:
                    self._rt_tau_trend_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('#76ff03', width=2.0, style=QtCore.Qt.DashDotLine))
                    self.plot_coil_rt_tau.addItem(self._rt_tau_trend_line)
                    self._rt_tau_trend_pt = pg.ScatterPlotItem(x=[d_liftoff_plot], y=[tau_trend], symbol='d', size=16, brush=pg.mkBrush('#76ff03'), pen=pg.mkPen('#ffffff', width=2.0))
                    self.plot_coil_rt_tau.addItem(self._rt_tau_trend_pt)
                else:
                    self._rt_tau_trend_line.setValue(tau_trend)
                    self._rt_tau_trend_pt.setData(x=[d_liftoff_plot], y=[tau_trend])
            else:
                if hasattr(self, '_rt_tau_trend_line') and self._rt_tau_trend_line is not None:
                    if self._rt_tau_trend_line in self.plot_coil_rt_tau.items:
                        self.plot_coil_rt_tau.removeItem(self._rt_tau_trend_line)
                    self._rt_tau_trend_line = None
                if hasattr(self, '_rt_tau_trend_pt') and self._rt_tau_trend_pt is not None:
                    if self._rt_tau_trend_pt in self.plot_coil_rt_tau.items:
                        self.plot_coil_rt_tau.removeItem(self._rt_tau_trend_pt)
                    self._rt_tau_trend_pt = None

            # Gráfico 3: Overlays Live (Amarelo Instantâneo) e Tendência Estável (Verde Lima)
            if live_auc > 0:
                if not hasattr(self, '_rt_auc_line') or self._rt_auc_line is None or self._rt_auc_line not in self.plot_coil_rt_auc.items:
                    self._rt_auc_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('#ffff00', width=1.5, style=QtCore.Qt.DashLine))
                    self.plot_coil_rt_auc.addItem(self._rt_auc_line)
                    self._rt_auc_pt = pg.ScatterPlotItem(x=[d_liftoff_plot], y=[live_auc], symbol='star', size=16, brush=pg.mkBrush('#f1c40f'), pen=pg.mkPen('w', width=1.5))
                    self.plot_coil_rt_auc.addItem(self._rt_auc_pt)
                else:
                    self._rt_auc_line.setValue(live_auc)
                    self._rt_auc_pt.setData(x=[d_liftoff_plot], y=[live_auc])

            if exibir_tendencia and auc_trend > 0:
                if not hasattr(self, '_rt_auc_trend_line') or self._rt_auc_trend_line is None or self._rt_auc_trend_line not in self.plot_coil_rt_auc.items:
                    self._rt_auc_trend_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('#76ff03', width=2.0, style=QtCore.Qt.DashDotLine))
                    self.plot_coil_rt_auc.addItem(self._rt_auc_trend_line)
                    self._rt_auc_trend_pt = pg.ScatterPlotItem(x=[d_liftoff_plot], y=[auc_trend], symbol='d', size=16, brush=pg.mkBrush('#76ff03'), pen=pg.mkPen('#ffffff', width=2.0))
                    self.plot_coil_rt_auc.addItem(self._rt_auc_trend_pt)
                else:
                    self._rt_auc_trend_line.setValue(auc_trend)
                    self._rt_auc_trend_pt.setData(x=[d_liftoff_plot], y=[auc_trend])
            else:
                if hasattr(self, '_rt_auc_trend_line') and self._rt_auc_trend_line is not None:
                    if self._rt_auc_trend_line in self.plot_coil_rt_auc.items:
                        self.plot_coil_rt_auc.removeItem(self._rt_auc_trend_line)
                    self._rt_auc_trend_line = None
                if hasattr(self, '_rt_auc_trend_pt') and self._rt_auc_trend_pt is not None:
                    if self._rt_auc_trend_pt in self.plot_coil_rt_auc.items:
                        self.plot_coil_rt_auc.removeItem(self._rt_auc_trend_pt)
                    self._rt_auc_trend_pt = None

            # Gráfico 4: ESTRELA AMARELA LIVE + ESTRELA DE TENDÊNCIA ESTÁVEL NO ESPAÇO DE CARACTERÍSTICAS
            if live_tau > 0 and live_auc > 0:
                if not hasattr(self, '_rt_star_item') or self._rt_star_item is None or self._rt_star_item not in self.plot_coil_rt_scatter.items:
                    self._rt_star_item = pg.ScatterPlotItem(
                        x=[live_tau], y=[live_auc],
                        symbol='star', size=14,
                        brush=pg.mkBrush('#f1c40f'),
                        pen=pg.mkPen('#ffffff', width=2.0)
                    )
                    self.plot_coil_rt_scatter.addItem(self._rt_star_item)
                else:
                    self._rt_star_item.setData(x=[live_tau], y=[live_auc])

            if exibir_tendencia and tau_trend > 0 and auc_trend > 0:
                if not hasattr(self, '_rt_star_trend_item') or self._rt_star_trend_item is None or self._rt_star_trend_item not in self.plot_coil_rt_scatter.items:
                    self._rt_star_trend_item = pg.ScatterPlotItem(
                        x=[tau_trend], y=[auc_trend],
                        symbol='star', size=18,
                        brush=pg.mkBrush('#76ff03'),
                        pen=pg.mkPen('#ffffff', width=2.2)
                    )
                    self.plot_coil_rt_scatter.addItem(self._rt_star_trend_item)
                else:
                    self._rt_star_trend_item.setData(x=[tau_trend], y=[auc_trend])
            else:
                if hasattr(self, '_rt_star_trend_item') and self._rt_star_trend_item is not None:
                    if self._rt_star_trend_item in self.plot_coil_rt_scatter.items:
                        self.plot_coil_rt_scatter.removeItem(self._rt_star_trend_item)
                    self._rt_star_trend_item = None

            # Atualiza o painel de relatório em HTML em taxa reduzida (4 FPS / 250ms) para evitar reflows de texto no Qt
            last_html_time = getattr(self, '_last_rt_html_time', 0.0)
            if force_refresh or (now - last_html_time) > 0.25:
                self._last_rt_html_time = now
                active_info = self.obter_especificacoes_bobina_atuais()
                active_id = active_info.get("id", "681")
                n_pts = len(v) if v is not None else 0
                n_acc = getattr(self, '_rt_trend_n_samples', 1)
                buf_len = len(getattr(self, '_rt_trend_buffer', []))

                if rate_mode == 'samples':
                    status_lote = f" | Progresso: {buf_len}/{n_target} coletados" if buf_len > 0 else ""
                    trend_label = f"Tendência por Lote ({n_target} amostras{status_lote})"
                else:
                    trend_label = f"Tendência Consolidada ({rate_txt} | N={n_acc} pacotes)"

                if exibir_tendencia and tau_trend > 0:
                    trend_html = f"<br><b>{trend_label}:</b> Tau = {self.formatar_valor_tempo(tau_trend)} | AUC = {auc_trend:.1f}"
                else:
                    trend_html = ""
                self.txt_coil_rt_report.setHtml(
                    f"<h3>=== Monitoramento em Tempo Real do Sensor ===</h3>"
                    f"<b>Sensor Ativo:</b> Bobina {active_id} ({active_info.get('model', 'Padrão')}) | <b>Lift-Off Atual:</b> {d_liftoff:.2f} mm | <b>Taxa da Tendência:</b> {rate_txt}<br>"
                    f"<b>Fonte do Sinal:</b> {fonte_txt} ({n_pts} pontos)<br>"
                    f"<b>Medições Live (Tempo Real Contínuo):</b> Tau = {self.formatar_valor_tempo(live_tau)} | AUC = {live_auc:.1f}{trend_html}<br>"
                    f"<small style='color:#a0a0a0;'>Estrelas Amarelas (★ Live) em tempo real contínuo (~30 FPS). Marcadores Verdes (★ Tendência) atualizados na cadência ({rate_txt}).</small>"
                )
        else:
            self.txt_coil_rt_report.setHtml(
                "<h3>=== Monitoramento em Tempo Real do Sensor ===</h3>"
                "<i>Aguardando início de aquisição serial em tempo real...</i><br><br>"
                "<b>Como fazer para o monitoramento em tempo real funcionar:</b><br>"
                "1. 🔌 <b>Com Hardware Conectado:</b> Selecione a Porta COM Serial no menu principal, clique em <b>'Conectar Serial'</b> e marque <b>'Modo Contínuo (Auto-Trigger)'</b> ou clique em <b>'Ler Transiente'</b>.<br>"
                "2. 📁 <b>Sem Hardware (Offline):</b> Clique em <b>'Importar Testes CSV'</b> no painel lateral à esquerda para carregar curvas gravadas."
            )

    def ao_mover_mouse_grafico_rt_caracterizacao(self, pos):
        if not self.is_tooltip_enabled():
            self.atualizar_destaque_visual_hover(target_plot=None)
            return
        if not hasattr(self, 'win_coil_rt_plots'):
            return

        # Limite de taxa do mouse (FPS Limiter ~30 FPS / 30ms) para evitar congelamento da GUI durante o movimento contínuo do cursor
        now = time.time()
        last_mouse = getattr(self, '_last_rt_mouse_time', 0.0)
        if (now - last_mouse) < 0.030:
            return
        self._last_rt_mouse_time = now

        plots = [
            self.plot_coil_rt_decay,
            self.plot_coil_rt_tau,
            self.plot_coil_rt_auc,
            self.plot_coil_rt_scatter
        ]

        melhor_item = None
        melhor_plot = None
        melhor_pt_x = None
        melhor_pt_y = None
        hover_decay_pt = None
        hover_decay_coords = None
        menor_dist_norm = float('inf')
        menor_dist_px = float('inf')
        rec_list = getattr(self, 'records_rt_caracterizacao', [])

        for plot_item in plots:
            vb = plot_item.vb
            if vb.sceneBoundingRect().contains(pos):
                if plot_item == self.plot_coil_rt_decay:
                    for item in plot_item.items:
                        if isinstance(item, pg.PlotDataItem) and item.xData is not None and item.yData is not None:
                            dist_px, pt_coord = self.calcular_distancia_pixel_curva(vb, item, pos)
                            if dist_px < 25.0 and dist_px < menor_dist_px:
                                menor_dist_px = dist_px
                                melhor_item = item
                                hover_decay_pt = pt_coord
                                hover_decay_coords = (item.xData, item.yData)
                                melhor_plot = plot_item
                else:
                    mouse_view_pt = vb.mapSceneToView(pos)
                    mx, my = mouse_view_pt.x(), mouse_view_pt.y()
                    vr = vb.viewRect()
                    rw, rh = vr.width(), vr.height()
                    if rw <= 0 or rh <= 0:
                        break

                    for item in rec_list:
                        d_val = item["distancia_mm"]
                        tau_val = item["tau"]
                        auc_val = item["auc"]

                        if plot_item == self.plot_coil_rt_tau:
                            pt_x, pt_y = d_val, tau_val
                        elif plot_item == self.plot_coil_rt_auc:
                            pt_x, pt_y = d_val, auc_val
                        elif plot_item == self.plot_coil_rt_scatter:
                            pt_x, pt_y = tau_val, auc_val
                        else:
                            continue

                        norm_dx = (pt_x - mx) / rw
                        norm_dy = (pt_y - my) / rh
                        dist_norm = norm_dx * norm_dx + norm_dy * norm_dy

                        if dist_norm < 0.002 and dist_norm < menor_dist_norm:
                            menor_dist_norm = dist_norm
                            melhor_item = item
                            melhor_plot = plot_item
                            melhor_pt_x, melhor_pt_y = pt_x, pt_y
                break

        if melhor_item:
            if hover_decay_coords is not None:
                self.atualizar_destaque_visual_hover(target_plot=melhor_plot, line_coords=hover_decay_coords)
                mat_sel = self.obter_material_selecionado()
                cls_sel = self.obter_classe_selecionada()
                active_info = getattr(self, 'active_coil_info', {})
                active_id = active_info.get("id", "681")

                rec_ref = getattr(melhor_item, 'rec_data', None)
                if rec_ref and isinstance(rec_ref, dict):
                    filename_ref = rec_ref.get("filename", "Sinal Live USB/COM")
                    mat_ref = rec_ref.get("material", mat_sel)
                    cls_ref = rec_ref.get("classe", cls_sel)
                    default_title = f"Curva: {filename_ref}" if filename_ref != "Sinal Live USB/COM" else "Sinal Medido em Tempo Real (USB/COM)"
                else:
                    filename_ref = "Sinal Live USB/COM"
                    mat_ref = mat_sel
                    cls_ref = cls_sel
                    default_title = "Sinal Medido em Tempo Real (USB/COM)"

                title = getattr(melhor_item, 'curve_title', None)
                if not title or callable(title) or title == ">":
                    title = default_title

                tooltip_text = (
                    f"📈 <b>{title}</b><br>"
                    f"📁 <b>Referência de Arquivo:</b> {filename_ref}<br>"
                    f"🛡️ <b>Material:</b> {mat_ref}<br>"
                    f"📊 <b>Estado / Classe de Corrosão:</b> {cls_ref.capitalize()}<br>"
                    f"🧲 <b>Bobina Ativa:</b> ID {active_id}<br>"
                    f"⏱️ <b>Ponto Cursor:</b> X = {hover_decay_pt[0]:.1f} | Amplitude Y = {hover_decay_pt[1]:.1f}"
                )
                self.floating_tooltip.exibir_hover(QtGui.QCursor.pos(), tooltip_text, target_plot=melhor_plot)
            elif melhor_plot is not None and melhor_pt_x is not None:
                simb = obter_simbolo_material(melhor_item.get("material"))
                self.atualizar_destaque_visual_hover(target_plot=melhor_plot, pt_coords=(melhor_pt_x, melhor_pt_y), symbol=simb)
                b_id = melhor_item.get("id_bobina", "N/A")
                mat_str = melhor_item.get("material", "A36 Comum")
                cls_str = melhor_item.get("classe", "Saudável")
                d_dist = melhor_item.get("distancia_mm", 0.0)
                t_val = melhor_item.get("tau", 0.0)
                a_val = melhor_item.get("auc", 0.0)
                samp_id = melhor_item.get("id", "1")

                tooltip_text = (
                    f"🎯 <b>Ponto de Amostra ID {samp_id} (Histórico CSV)</b><br>"
                    f"🧲 <b>Bobina:</b> ID {b_id} | 🛡️ <b>Material:</b> {mat_str}<br>"
                    f"📊 <b>Estado:</b> {cls_str}<br>"
                    f"📏 <b>Lift-Off:</b> {d_dist:.2f} mm ({d_dist:.0f} µm)<br>"
                    f"⏱️ <b>Tau (&tau;):</b> {self.formatar_valor_tempo(t_val)}<br>"
                    f"📐 <b>AUC:</b> {a_val:.1f} Counts.µs"
                )
                self.floating_tooltip.exibir_hover(QtGui.QCursor.pos(), tooltip_text, target_plot=melhor_plot)
        else:
            self.atualizar_destaque_visual_hover(target_plot=None)

    def atualizar_graficos_estatistica_caracterizacao(self):
        if not hasattr(self, 'plot_coil_st_decay'):
            return

        self.plot_coil_st_decay.clear()
        self.plot_coil_st_tau.clear()
        self.plot_coil_st_auc.clear()
        self.plot_coil_st_scatter.clear()

        recs = getattr(self, 'loaded_coil_records', [])
        selected_items = self.list_imported_coil_files.selectedItems()
        if selected_items:
            sel_recs = [item.data(QtCore.Qt.UserRole) for item in selected_items if item.data(QtCore.Qt.UserRole)]
            if sel_recs:
                recs = sel_recs

        if not recs:
            self.txt_coil_st_report.setText("Nenhum registro de caracterização carregado para análise estatística.")
            return

        # Verifica se o checkbox de tonalidades por ID está ativo
        use_id_shading = hasattr(self, 'chk_diferenciar_ids_tonalidade') and self.chk_diferenciar_ids_tonalidade.isChecked()

        # Extrai todas as amostras individuais dos arquivos importados
        self.records_estatistica_caracterizacao = []
        for r in recs:
            b_id = str(r.get("id_bobina", "N/A"))
            d_val = float(r.get("distancia_mm", 0.0))
            mat = str(r.get("material", "A36 Comum"))
            cls_name = str(r.get("classe", "Saudável"))

            all_t = r.get("all_taus", [r["tau"]])
            all_a = r.get("all_aucs", [r["auc"]])
            all_l = r.get("all_l_efetivas", [r["l_efetiva_uh"]])

            n_pts = min(len(all_t), len(all_a), len(all_l))
            for i in range(n_pts):
                id_samp = str(r.get("id_amostra", f"{i+1}"))
                self.records_estatistica_caracterizacao.append({
                    "id_bobina": b_id,
                    "distancia_mm": d_val,
                    "material": mat,
                    "classe": cls_name,
                    "tau": float(all_t[i]),
                    "auc": float(all_a[i]),
                    "l_efetiva_uh": float(all_l[i]),
                    "id": id_samp,
                    "curva": r.get("curva", []),
                    "dt_us": r.get("dt_us", 0.1)
                })

        # Aplica Filtros de Exibição (Materiais e Classes)
        if hasattr(self, 'coil_filter_checkboxes_material'):
            mats_ok = [m for m, chk in self.coil_filter_checkboxes_material.items() if chk.isChecked()]
            cls_map = {
                "Saudável": getattr(self, 'chk_coil_filter_saudavel', None),
                "Leve": getattr(self, 'chk_coil_filter_leve', None),
                "Moderada": getattr(self, 'chk_coil_filter_moderada', None),
                "Avançada": getattr(self, 'chk_coil_filter_avancada', None),
                "Corroído": getattr(self, 'chk_coil_filter_corroido', None),
                "Ar Livre": getattr(self, 'chk_coil_filter_ar_cls', None),
                "Não Definido": getattr(self, 'chk_coil_filter_nao_definido', None)
            }
            cls_ok = [c for c, chk in cls_map.items() if chk is None or chk.isChecked()]

            self.records_estatistica_caracterizacao = [
                a for a in self.records_estatistica_caracterizacao
                if a["material"] in mats_ok and a["classe"] in cls_ok
            ]

        # Aplica Filtro de Outliers (IQR) por arquivo / ensaio individual se selecionado
        if hasattr(self, 'chk_coil_filter_outliers') and self.chk_coil_filter_outliers.isChecked() and self.records_estatistica_caracterizacao:
            # Agrupa individualmente por ensaio (id_bobina, material, classe, distancia_mm)
            grupos_file = {}
            for a in self.records_estatistica_caracterizacao:
                file_key = (a.get("id_bobina"), a.get("material"), a.get("classe"), a.get("distancia_mm"))
                if file_key not in grupos_file:
                    grupos_file[file_key] = []
                grupos_file[file_key].append(a)

            records_limpos = []
            for file_key, grupo in grupos_file.items():
                if len(grupo) >= 4:
                    taus_g = [item["tau"] for item in grupo]
                    aucs_g = [item["auc"] for item in grupo]
                    q25_t, q75_t = np.percentile(taus_g, [25, 75])
                    iqr_t = q75_t - q25_t
                    q25_a, q75_a = np.percentile(aucs_g, [25, 75])
                    iqr_a = q75_a - q25_a

                    for item in grupo:
                        is_ok_t = (q25_t - 1.5 * iqr_t <= item["tau"] <= q75_t + 1.5 * iqr_t)
                        is_ok_a = (q25_a - 1.5 * iqr_a <= item["auc"] <= q75_a + 1.5 * iqr_a)
                        if is_ok_t and is_ok_a:
                            records_limpos.append(item)
                else:
                    records_limpos.extend(grupo)

            self.records_estatistica_caracterizacao = records_limpos

        # Mapeia tonalidade por ID e aplica cores/símbolos padronizados por Material e Classe
        if self.records_estatistica_caracterizacao:
            ids_unicos = sorted(list(set([str(a["id"]) for a in self.records_estatistica_caracterizacao])))
            num_ids = len(ids_unicos)
            id_to_lightness = {id_v: (0.35 + 0.50 * (i / max(1, num_ids - 1)) if num_ids > 1 else 0.55) for i, id_v in enumerate(ids_unicos)}

            for a_item in self.records_estatistica_caracterizacao:
                cor_base = obter_cor_classe(a_item["classe"])
                simbolo = obter_simbolo_material(a_item["material"])
                a_item["symbol"] = simbolo

                base_qcol = QtGui.QColor(cor_base)
                if use_id_shading:
                    h, s, l_val, a_alpha = base_qcol.getHslF()
                    target_l = id_to_lightness.get(str(a_item["id"]), 0.55)
                    adj_qcol = QtGui.QColor.fromHslF(h, min(1.0, s * 1.05), max(0.25, min(0.90, target_l)))
                    a_item["color_hex"] = adj_qcol.name()
                    a_item["brush"] = pg.mkBrush(adj_qcol)
                else:
                    a_item["color_hex"] = cor_base
                    a_item["brush"] = pg.mkBrush(base_qcol)

        # Plot 1: Curvas Transientes de Decaimento com Estilo por Material e Tonalidade HSL
        for idx, r in enumerate(recs):
            cor_base_hex = obter_cor_classe(r.get("classe", "Saudável"))
            if use_id_shading and recs:
                base_qcol = QtGui.QColor(cor_base_hex)
                h, s, l_val, a_alpha = base_qcol.getHslF()
                target_l = id_to_lightness.get(str(r.get("id_amostra", r.get("filename", ""))), 0.55) if 'id_to_lightness' in locals() else 0.55
                cor_hex = QtGui.QColor.fromHslF(h, min(1.0, s * 1.05), max(0.25, min(0.90, target_l))).name()
            else:
                cor_hex = cor_base_hex

            estilo = obter_estilo_material(r.get("material", "A36 Comum"))
            t_us = np.arange(len(r["curva"])) * r.get("dt_us", 0.1)
            pen = pg.mkPen(color=cor_hex, width=2.2, style=estilo)
            curve_st = self.plot_coil_st_decay.plot(
                t_us, r["curva"], pen=pen,
                name=f"B.{r.get('id_bobina','')} ({r.get('distancia_mm',0)}mm, {r.get('material','')})"
            )
            curve_st.rec_data = r

        # Plot 2, 3, 4: Tau, AUC e Scatter agrupados por (símbolo, tonalidade) em lote (Vetorização - 1000x mais rápido)
        grupos_scatter = {}
        for a in self.records_estatistica_caracterizacao:
            d_val = a["distancia_mm"]
            t_val = a["tau"]
            a_val = a["auc"]
            simb = a.get("symbol", "o")
            color_hex = a.get("color_hex", "#3498db")

            grp_key = (simb, color_hex)
            if grp_key not in grupos_scatter:
                grupos_scatter[grp_key] = {"d": [], "t": [], "a": [], "brush": a.get("brush", pg.mkBrush(color_hex))}
            grupos_scatter[grp_key]["d"].append(d_val)
            grupos_scatter[grp_key]["t"].append(t_val)
            grupos_scatter[grp_key]["a"].append(a_val)

        for (simb, _), data in grupos_scatter.items():
            b_pt = data["brush"]
            self.plot_coil_st_tau.addItem(pg.ScatterPlotItem(x=data["d"], y=data["t"], symbol=simb, size=8, brush=b_pt, pen=pg.mkPen('w', width=0.3)))
            self.plot_coil_st_auc.addItem(pg.ScatterPlotItem(x=data["d"], y=data["a"], symbol=simb, size=8, brush=b_pt, pen=pg.mkPen('w', width=0.3)))
            self.plot_coil_st_scatter.addItem(pg.ScatterPlotItem(x=data["t"], y=data["a"], symbol=simb, size=9, brush=b_pt, pen=pg.mkPen('w', width=0.3)))

        taus = [a["tau"] for a in self.records_estatistica_caracterizacao]
        aucs = [a["auc"] for a in self.records_estatistica_caracterizacao]

        m_tau, s_tau = np.mean(taus), np.std(taus)
        m_auc, s_auc = np.mean(aucs), np.std(aucs)

        report = [
            f"<h3>=== Estatística de Caracterização dos Sensores ===</h3>",
            f"<b>Total de Amostras Processadas:</b> {len(self.records_estatistica_caracterizacao)}<br>",
            f"<b>Constante de Tempo Tau (&mu;s):</b> {m_tau:.3f} &plusmn; {s_tau:.3f} (CV: {(s_tau/m_tau*100 if m_tau>0 else 0):.2f}%)<br>",
            f"<b>Área Sob a Curva AUC:</b> {m_auc:.1f} &plusmn; {s_auc:.1f} (CV: {(s_auc/m_auc*100 if m_auc>0 else 0):.2f}%)<br>"
        ]
        if use_id_shading:
            report.append("<small style='color:#00e676;'>🎨 Diferenciação HSL por ID da Amostra Ativada.</small>")

        self.txt_coil_st_report.setHtml("".join(report))

    def ao_mover_mouse_grafico_estatistico_caracterizacao(self, pos):
        if not self.is_tooltip_enabled():
            return
        if not hasattr(self, 'records_estatistica_caracterizacao') or not self.records_estatistica_caracterizacao:
            return

        # Limite de taxa do mouse (FPS Limiter ~30 FPS / 30ms)
        now = time.time()
        last_mouse = getattr(self, '_last_st_mouse_time', 0.0)
        if (now - last_mouse) < 0.030:
            return
        self._last_st_mouse_time = now

        plots = [
            self.plot_coil_st_decay,
            self.plot_coil_st_tau,
            self.plot_coil_st_auc,
            self.plot_coil_st_scatter
        ]

        melhor_item = None
        melhor_plot = None
        melhor_pt_x, melhor_pt_y = None, None
        hover_decay_pt = None
        hover_decay_coords = None
        menor_dist_norm = float('inf')
        menor_dist_px = float('inf')

        for plot_item in plots:
            vb = plot_item.vb
            if vb.sceneBoundingRect().contains(pos):
                if plot_item == self.plot_coil_st_decay:
                    for item in plot_item.items:
                        if isinstance(item, pg.PlotDataItem) and hasattr(item, 'rec_data'):
                            r = item.rec_data
                            dist_px, pt_coord = self.calcular_distancia_pixel_curva(vb, item, pos)
                            if dist_px < 25.0 and dist_px < menor_dist_px:
                                menor_dist_px = dist_px
                                melhor_item = r
                                hover_decay_pt = pt_coord
                                hover_decay_coords = (item.xData, item.yData)
                else:
                    mouse_view_pt = vb.mapSceneToView(pos)
                    mx, my = mouse_view_pt.x(), mouse_view_pt.y()
                    vr = vb.viewRect()
                    rw, rh = vr.width(), vr.height()
                    if rw <= 0 or rh <= 0:
                        break

                    for item in self.records_estatistica_caracterizacao:
                        d_val = item["distancia_mm"]
                        tau_val = item["tau"]
                        auc_val = item["auc"]

                        if plot_item == self.plot_coil_st_tau:
                            pt_x, pt_y = d_val, tau_val
                        elif plot_item == self.plot_coil_st_auc:
                            pt_x, pt_y = d_val, auc_val
                        elif plot_item == self.plot_coil_st_scatter:
                            pt_x, pt_y = tau_val, auc_val
                        else:
                            continue

                        norm_dx = (pt_x - mx) / rw
                        norm_dy = (pt_y - my) / rh
                        dist_norm = norm_dx * norm_dx + norm_dy * norm_dy

                        if dist_norm < 0.002 and dist_norm < menor_dist_norm:
                            menor_dist_norm = dist_norm
                            melhor_item = item
                            melhor_plot = plot_item
                            melhor_pt_x, melhor_pt_y = pt_x, pt_y
                break

        if melhor_item:
            if hover_decay_coords is not None:
                self.atualizar_destaque_visual_hover(target_plot=self.plot_coil_st_decay, line_coords=hover_decay_coords)
            elif melhor_plot is not None and melhor_pt_x is not None:
                simb = obter_simbolo_material(melhor_item.get("material"))
                self.atualizar_destaque_visual_hover(target_plot=melhor_plot, pt_coords=(melhor_pt_x, melhor_pt_y), symbol=simb)

            n_tot = melhor_item.get("num_samples", 1)
            manual_adj = "Sim" if melhor_item.get("ajuste_manual_liftoff", False) else "Não"
            local_str = melhor_item.get("local", "Não Especificado")
            ind_uh = melhor_item.get("indutancia_uh", 0.0)

            estilo_nome = {
                "A36 Comum": "Contínua (Solid)",
                "A36 GE": "Tracejada (Dash)",
                "A36 GF": "Pontilhada (Dot)",
                "Estrutura Torre": "Traço-Ponto (DashDot)",
                "Ar Livre": "Contínua (Solid)"
            }.get(melhor_item.get("material"), "Padrão")

            cursor_info = ""
            if hover_decay_pt is not None:
                cursor_info = f"⏱️ <b>Ponto Cursor:</b> t = {hover_decay_pt[0]:.2f} &mu;s | V(t) = {hover_decay_pt[1]:.1f} ADC Counts<br>"

            header_title = "📈 <b>CURVA MÉDIA DE DECAIMENTO DA CARACTERIZAÇÃO V(t)</b>" if hover_decay_pt is not None else "📍 <b>PONTO DE CARACTERIZAÇÃO ESTATÍSTICA</b>"

            tooltip_text = (
                f"{header_title}<br>"
                f"--------------------------------------------------<br>"
                f"📁 <b>Referência de Arquivo:</b> {melhor_item.get('filename', 'Ensaio Média')}<br>"
                f"🛡️ <b>Material:</b> {melhor_item['material']} <i>[{estilo_nome}]</i><br>"
                f"📊 <b>Estado / Classe de Corrosão:</b> {melhor_item['classe'].capitalize()}<br>"
                f"🆔 <b>Amostra (ID):</b> {melhor_item.get('id', melhor_item.get('id_amostra', 'N/A'))}<br>"
                f"📍 <b>Local de Coleta:</b> {local_str}<br>"
                f"🧲 <b>Sensor / Bobina:</b> ID {melhor_item['id_bobina']} (L<sub>nom</sub> = {ind_uh:.1f} &mu;H)<br>"
                f"📏 <b>Afastamento (Lift-Off):</b> {melhor_item['distancia_mm']:.2f} mm<br>"
                f"--------------------------------------------------<br>"
                f"{cursor_info}"
                f"⚡ <b>Constante de Tempo (&tau;):</b> {melhor_item['tau']:.4f} &mu;s<br>"
                f"📐 <b>Área Sob a Curva (AUC):</b> {melhor_item['auc']:.1f} Counts.&mu;s<br>"
                f"🧲 <b>Indutância Efetiva (L<sub>ef</sub>):</b> {melhor_item.get('l_efetiva_uh', 0.0):.2f} &mu;H<br>"
                f"🔧 <b>Ajuste Manual Lift-Off:</b> {manual_adj}<br>"
                f"📊 <b>Amostragens no Lote:</b> N = {n_tot}"
            )
            target_p = self.plot_coil_st_decay if hover_decay_coords is not None else melhor_plot
            self.floating_tooltip.exibir_hover(QtGui.QCursor.pos(), tooltip_text, target_plot=target_p)
        else:
            self.atualizar_destaque_visual_hover(target_plot=None)

    def ao_validar_limite_id_amostra(self, text):
        if len(text) >= 3:
            pos = self.edit_coil_sample_id.mapToGlobal(QtCore.QPoint(0, self.edit_coil_sample_id.height()))
            QtWidgets.QToolTip.showText(pos, "⚠️ Limite atingido: O ID da amostra possui no máximo 3 caracteres (ex: 001, 012).", self.edit_coil_sample_id)


# =====================================================================
# JANELA DE LAUNCHER / MENU PRINCIPAL DE MÓDULOS
# =====================================================================
class ModuleLauncherWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Ensaio por Correntes Parasitas — Menu Principal")
        self.resize(1020, 640)
        self.setMinimumSize(900, 580)
        self.center_on_screen()
        
        self.ai_window = None
        self.coil_window = None
        self.shared_serial_thread = SerialWorker()
        
        self.init_ui()

    def center_on_screen(self):
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2)

    def init_ui(self):
        central_widget = QtWidgets.QWidget()
        central_widget.setStyleSheet("background-color: #121214;")
        self.setCentralWidget(central_widget)
        
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(35, 35, 35, 35)
        main_layout.setSpacing(22)

        # Cabeçalho Principal
        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(6)
        
        lbl_title = QtWidgets.QLabel("SISTEMA DE ENSAIO E DIAGNÓSTICO POR CORRENTES PARASITAS")
        lbl_title.setAlignment(QtCore.Qt.AlignCenter)
        lbl_title.setStyleSheet("font-size: 17pt; font-weight: bold; color: #00e676; font-family: 'Segoe UI', Arial;")
        
        lbl_subtitle = QtWidgets.QLabel("Selecione o módulo operacional desejado para iniciar:")
        lbl_subtitle.setAlignment(QtCore.Qt.AlignCenter)
        lbl_subtitle.setStyleSheet("font-size: 11pt; color: #a0a0a0;")
        
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_subtitle)
        main_layout.addLayout(header_layout)

        # Container dos dois Cards de Módulos
        cards_layout = QtWidgets.QHBoxLayout()
        cards_layout.setSpacing(25)

        # ---------------------------------------------------------------------
        # CARD 1: MÓDULO DE AQUISIÇÃO & DIAGNÓSTICO IA
        # ---------------------------------------------------------------------
        card1 = QtWidgets.QGroupBox()
        card1.setStyleSheet("""
            QGroupBox {
                background-color: #1c1c1e;
                border: 2px solid #27ae60;
                border-radius: 10px;
                padding: 16px;
            }
            QGroupBox:hover {
                border: 2px solid #2ecc71;
                background-color: #222226;
            }
        """)
        card1_layout = QtWidgets.QVBoxLayout(card1)
        card1_layout.setSpacing(12)

        lbl_icon1 = QtWidgets.QLabel("🔬")
        lbl_icon1.setAlignment(QtCore.Qt.AlignCenter)
        lbl_icon1.setStyleSheet("font-size: 38pt;")
        card1_layout.addWidget(lbl_icon1)

        lbl_card1_title = QtWidgets.QLabel("Módulo 1: Aquisição & Diagnóstico IA")
        lbl_card1_title.setAlignment(QtCore.Qt.AlignCenter)
        lbl_card1_title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #2ecc71;")
        card1_layout.addWidget(lbl_card1_title)

        lbl_card1_desc = QtWidgets.QLabel(
            "• Leitura em tempo real via porta serial/USB (COM)\n"
            "• Classificação inteligente via Machine Learning (Random Forest/SVM)\n"
            "• Análise estatística offline de cupons de calibração\n"
            "• Diagnóstico físico e temporal instantâneo"
        )
        lbl_card1_desc.setWordWrap(True)
        lbl_card1_desc.setStyleSheet("font-size: 9.5pt; color: #d0d0d0; line-height: 1.4;")
        card1_layout.addWidget(lbl_card1_desc)
        card1_layout.addStretch()

        btn_open_m1 = QtWidgets.QPushButton("▶ Acessar Módulo 1 (Aquisição & IA)")
        btn_open_m1.setMinimumHeight(48)
        btn_open_m1.setCursor(QtCore.Qt.PointingHandCursor)
        btn_open_m1.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; font-weight: bold; font-size: 10.5pt; border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        btn_open_m1.clicked.connect(self.abrir_modulo_ai)
        card1_layout.addWidget(btn_open_m1)
        cards_layout.addWidget(card1, 1)

        # ---------------------------------------------------------------------
        # CARD 2: MÓDULO DE CARACTERIZAÇÃO & COMPARAÇÃO DE BOBINAS
        # ---------------------------------------------------------------------
        card2 = QtWidgets.QGroupBox()
        card2.setStyleSheet("""
            QGroupBox {
                background-color: #1c1c1e;
                border: 2px solid #8e44ad;
                border-radius: 10px;
                padding: 16px;
            }
            QGroupBox:hover {
                border: 2px solid #9b59b6;
                background-color: #222226;
            }
        """)
        card2_layout = QtWidgets.QVBoxLayout(card2)
        card2_layout.setSpacing(12)

        lbl_icon2 = QtWidgets.QLabel("🧲")
        lbl_icon2.setAlignment(QtCore.Qt.AlignCenter)
        lbl_icon2.setStyleSheet("font-size: 38pt;")
        card2_layout.addWidget(lbl_icon2)

        lbl_card2_title = QtWidgets.QLabel("Módulo 2: Caracterização de Bobinas")
        lbl_card2_title.setAlignment(QtCore.Qt.AlignCenter)
        lbl_card2_title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #ab47bc;")
        card2_layout.addWidget(lbl_card2_title)

        lbl_card2_desc = QtWidgets.QLabel(
            "• Ensaio de bancada de Lift-Off e indutância L (\u03bcH)\n"
            "• Seleção de espaçadores (5mm, 4mm, 2mm, 1mm com 1x/2x)\n"
            "• 3 Sub-Abas: Comparativos, Tempo Real e Estatística\n"
            "• Visualizador 3D interativo e gerador de relatórios"
        )
        lbl_card2_desc.setWordWrap(True)
        lbl_card2_desc.setStyleSheet("font-size: 9.5pt; color: #d0d0d0; line-height: 1.4;")
        card2_layout.addWidget(lbl_card2_desc)
        card2_layout.addStretch()

        btn_open_m2 = QtWidgets.QPushButton("▶ Acessar Módulo 2 (Caracterização de Bobinas)")
        btn_open_m2.setMinimumHeight(48)
        btn_open_m2.setCursor(QtCore.Qt.PointingHandCursor)
        btn_open_m2.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad; color: white; font-weight: bold; font-size: 10.5pt; border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #9b59b6;
            }
        """)
        btn_open_m2.clicked.connect(self.abrir_modulo_bobinas)
        card2_layout.addWidget(btn_open_m2)
        cards_layout.addWidget(card2, 1)

        main_layout.addLayout(cards_layout, 1)

        # Rodapé
        lbl_footer = QtWidgets.QLabel("SENAI / ISI — Anticorrosão & Ensaios Não Destrutivos (END)")
        lbl_footer.setAlignment(QtCore.Qt.AlignCenter)
        lbl_footer.setStyleSheet("font-size: 8.5pt; color: #666666;")
        main_layout.addWidget(lbl_footer)

    def abrir_modulo_ai(self):
        if self.ai_window is None:
            self.ai_window = EddyCurrentPlotter(mode="ai", launcher=self)
        self.ai_window.showMaximized()
        self.hide()

    def abrir_modulo_bobinas(self):
        if self.coil_window is None:
            self.coil_window = EddyCurrentPlotter(mode="coil", launcher=self)
        self.coil_window.showMaximized()
        self.hide()


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

    launcher = ModuleLauncherWindow()
    launcher.show()
    sys.exit(app.exec_())
