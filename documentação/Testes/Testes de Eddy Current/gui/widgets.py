import os
from PyQt5 import QtWidgets, QtCore

class ExclusaoSeletivaDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
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
