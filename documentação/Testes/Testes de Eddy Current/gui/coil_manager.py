import os
import csv
import io
import json
from datetime import datetime
import numpy as np
from PyQt5 import QtCore, QtWidgets, QtGui

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D

from gui.utils import normalizar_nome_classe, calcular_tau_e_auc

# Dicionário padrão atualizado conforme a tabela oficial da imagem do usuário
DEFAULT_COILS = {
    "000": {
        "id": "000", "inductance_uh": 360.0, "resistance_ohm": 1.73,
        "diameter_mm": 24.7, "diameter_winding_mm": 24.7,
        "height_mm": 5.7, "height_winding_mm": 5.7,
        "turns": 100, "awg": "27", "wire_diameter_mm": 0.361, "core": "AR",
        "description": "Bobina sem núcleo (Ar Livre, 100 espiras, AWG 27)."
    },
    "001": {
        "id": "001", "inductance_uh": 0.0, "resistance_ohm": 0.0,
        "diameter_mm": 30.8, "diameter_winding_mm": 30.8,
        "height_mm": 13.0, "height_winding_mm": 13.0,
        "turns": 0, "awg": "-", "wire_diameter_mm": 0.0, "core": "PLA",
        "description": "Carretel impresso PLA (Altura 13mm, Dia 30.8mm)."
    },
    "002": {
        "id": "002", "inductance_uh": 0.0, "resistance_ohm": 0.0,
        "diameter_mm": 22.7, "diameter_winding_mm": 22.7,
        "height_mm": 13.0, "height_winding_mm": 13.0,
        "turns": 0, "awg": "-", "wire_diameter_mm": 0.0, "core": "PLA",
        "description": "Carretel impresso PLA (Altura 13mm, Dia 22.7mm)."
    },
    "003": {
        "id": "003", "inductance_uh": 0.0, "resistance_ohm": 0.0,
        "diameter_mm": 14.7, "diameter_winding_mm": 14.7,
        "height_mm": 13.0, "height_winding_mm": 13.0,
        "turns": 0, "awg": "-", "wire_diameter_mm": 0.0, "core": "PLA",
        "description": "Carretel impresso PLA (Altura 13mm, Dia 14.7mm)."
    },
    "004": {
        "id": "004", "inductance_uh": 248.0, "resistance_ohm": 1.36,
        "diameter_mm": 30.8, "diameter_winding_mm": 30.8,
        "height_mm": 8.5, "height_winding_mm": 8.5,
        "turns": 100, "awg": "27", "wire_diameter_mm": 0.361, "core": "PLA",
        "description": "Bobina impressa PLA (Altura 8.5mm, Dia 30.8mm, 100 espiras)."
    },
    "005": {
        "id": "005", "inductance_uh": 230.0, "resistance_ohm": 1.27,
        "diameter_mm": 22.7, "diameter_winding_mm": 22.7,
        "height_mm": 8.5, "height_winding_mm": 8.5,
        "turns": 100, "awg": "27", "wire_diameter_mm": 0.361, "core": "PLA",
        "description": "Bobina impressa PLA (Altura 8.5mm, Dia 22.7mm, 100 espiras)."
    },
    "006": {
        "id": "006", "inductance_uh": 167.0, "resistance_ohm": 1.21,
        "diameter_mm": 14.7, "diameter_winding_mm": 14.7,
        "height_mm": 8.5, "height_winding_mm": 8.5,
        "turns": 100, "awg": "27", "wire_diameter_mm": 0.361, "core": "PLA",
        "description": "Bobina impressa PLA (Altura 8.5mm, Dia 14.7mm, 100 espiras)."
    },
    "007": {
        "id": "007", "inductance_uh": 0.0, "resistance_ohm": 0.0,
        "diameter_mm": 30.8, "diameter_winding_mm": 30.8,
        "height_mm": 3.1, "height_winding_mm": 3.1,
        "turns": 0, "awg": "-", "wire_diameter_mm": 0.0, "core": "PLA",
        "description": "Carretel impresso PLA (Altura 3.1mm, Dia 30.8mm)."
    },
    "008": {
        "id": "008", "inductance_uh": 0.0, "resistance_ohm": 0.0,
        "diameter_mm": 22.7, "diameter_winding_mm": 22.7,
        "height_mm": 3.1, "height_winding_mm": 3.1,
        "turns": 0, "awg": "-", "wire_diameter_mm": 0.0, "core": "PLA",
        "description": "Carretel impresso PLA (Altura 3.1mm, Dia 22.7mm)."
    },
    "009": {
        "id": "009", "inductance_uh": 0.0, "resistance_ohm": 0.0,
        "diameter_mm": 14.7, "diameter_winding_mm": 14.7,
        "height_mm": 3.1, "height_winding_mm": 3.1,
        "turns": 0, "awg": "-", "wire_diameter_mm": 0.0, "core": "PLA",
        "description": "Carretel impresso PLA (Altura 3.1mm, Dia 14.7mm)."
    },
    "681": {
        "id": "681", "inductance_uh": 697.0, "resistance_ohm": 2.30,
        "diameter_mm": 12.7, "diameter_winding_mm": 11.0,
        "height_mm": 10.9, "height_winding_mm": 2.9,
        "turns": 0, "awg": "NA", "wire_diameter_mm": 0.0, "core": "FER",
        "description": "Sensor de Ferrite comercial (Dia 12.7mm, Enrolamento 11mm, L=697uH, R=2.30 Ohm)."
    },
    "101": {
        "id": "101", "inductance_uh": 99.75, "resistance_ohm": 0.29,
        "diameter_mm": 9.9, "diameter_winding_mm": 8.0,
        "height_mm": 11.8, "height_winding_mm": 5.8,
        "turns": 0, "awg": "NA", "wire_diameter_mm": 0.0, "core": "FER",
        "description": "Sensor de Ferrite comercial (Dia 9.9mm, Enrolamento 8mm, L=99.75uH, R=0.29 Ohm)."
    }
}

class CoilCharacterizationManager:
    def __init__(self, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = base_dir
        self.config_filepath = os.path.join(self.base_dir, "bobinas_cadastradas.json")
        self.coils = {}
        self.load_coils_from_json()

    def load_coils_from_json(self):
        """
        Carrega as bobinas do arquivo JSON local ou força sincronização com DEFAULT_COILS.
        """
        if os.path.exists(self.config_filepath):
            try:
                with open(self.config_filepath, "r", encoding="utf-8") as f:
                    self.coils = json.load(f)
                for k, v in DEFAULT_COILS.items():
                    if k not in self.coils:
                        self.coils[k] = v
                self.save_coils_to_json()
            except Exception:
                self.coils = dict(DEFAULT_COILS)
                self.save_coils_to_json()
        else:
            self.coils = dict(DEFAULT_COILS)
            self.save_coils_to_json()

    def save_coils_to_json(self):
        try:
            with open(self.config_filepath, "w", encoding="utf-8") as f:
                json.dump(self.coils, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar bobinas no JSON: {e}")

    def register_coil(self, coil_id, inductance_uh, resistance_ohm, diameter_mm, height_mm,
                      turns=0, awg="27", wire_diameter_mm=0.361, core="PLA", description="",
                      diameter_winding_mm=None, height_winding_mm=None):
        cid = str(coil_id).strip()
        if diameter_winding_mm is None:
            diameter_winding_mm = float(diameter_mm)
        if height_winding_mm is None:
            height_winding_mm = float(height_mm)

        self.coils[cid] = {
            "id": cid,
            "inductance_uh": float(inductance_uh),
            "resistance_ohm": float(resistance_ohm),
            "diameter_mm": float(diameter_mm),
            "diameter_winding_mm": float(diameter_winding_mm),
            "height_mm": float(height_mm),
            "height_winding_mm": float(height_winding_mm),
            "turns": int(turns),
            "awg": str(awg).strip(),
            "wire_diameter_mm": float(wire_diameter_mm),
            "core": str(core).strip(),
            "description": str(description).strip()
        }
        self.save_coils_to_json()
        return self.coils[cid]

    def delete_coil(self, coil_id):
        cid = str(coil_id).strip()
        if cid in self.coils:
            del self.coils[cid]
            self.save_coils_to_json()
            return True
        return False

    def get_coil_info(self, coil_id):
        return self.coils.get(str(coil_id).strip(), None)

    def get_all_coils(self):
        return self.coils

    def generate_standard_filename(self, coil_id, distance_mm, material, classe, timestamp=None):
        if timestamp is None:
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        else:
            ts_str = timestamp.replace("-", "").replace(":", "").replace(" ", "_")

        coil_info = self.get_coil_info(coil_id)
        d_str = f"{coil_info['diameter_mm']:.1f}" if coil_info else "0"
        l_str = f"{coil_info['height_mm']:.1f}" if coil_info else "0"
        
        mat_clean = material.replace(" ", "_")
        cls_clean = classe.replace(" ", "_")
        dist_str = f"{float(distance_mm):.1f}"

        filename = f"ensaio_bobina_{coil_id}_d{d_str}_l{l_str}_dist_{dist_str}mm_{mat_clean}_{cls_clean}_{ts_str}.csv"
        return filename

    def save_characterization_record(self, output_dir, id_amostra, coil_info, distance_mm, material, classe, dt_us, curves, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Garante que curves seja uma lista de curvas de 256 pontos
        if isinstance(curves, (list, tuple, np.ndarray)) and len(curves) == 256 and (len(curves) == 0 or not isinstance(curves[0], (list, tuple, np.ndarray))):
            curves_list = [curves]
        elif isinstance(curves, (list, tuple, np.ndarray)) and len(curves) > 0:
            curves_list = curves
        else:
            curves_list = [curves]

        os.makedirs(output_dir, exist_ok=True)
        filename = self.generate_standard_filename(
            coil_id=coil_info["id"],
            distance_mm=distance_mm,
            material=material,
            classe=classe,
            timestamp=timestamp
        )
        filepath = os.path.join(output_dir, filename)

        header = [
            "id_amostra", "id_bobina", "indutancia_uh", "resistencia_ohm",
            "diametro_mm", "altura_mm", "espiras", "fio_awg", "nucleo",
            "distancia_mm", "material", "classe", "timestamp", "dt_us"
        ] + [f"p_{i}" for i in range(256)]

        rows = []
        for idx, single_curve in enumerate(curves_list):
            sample_label = f"{id_amostra}_{idx+1}" if len(curves_list) > 1 else str(id_amostra)
            row = [
                sample_label,
                coil_info["id"],
                f"{coil_info['inductance_uh']:.2f}",
                f"{coil_info['resistance_ohm']:.2f}",
                f"{coil_info['diameter_mm']:.1f}",
                f"{coil_info['height_mm']:.1f}",
                coil_info["turns"],
                coil_info["awg"],
                coil_info["core"],
                f"{float(distance_mm):.1f}",
                material,
                classe,
                timestamp,
                f"{dt_us:.5f}"
            ] + [str(int(round(x))) for x in single_curve]
            rows.append(row)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(header)
            writer.writerows(rows)

        return filepath

    def read_characterization_csv(self, filepath):
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", newline="", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(filepath, "r", newline="", encoding="latin-1") as f:
                content = f.read()
        except Exception:
            return None

        f_string = io.StringIO(content)
        reader = csv.reader(f_string, delimiter=";")
        
        try:
            headers = next(reader)
        except StopIteration:
            return None

        rows = [row for row in reader if row and len(row) >= 14]
        if not rows:
            return None

        first_row = rows[0]
        try:
            id_amostra = first_row[headers.index("id_amostra")] if "id_amostra" in headers else first_row[0]
            id_bobina = first_row[headers.index("id_bobina")] if "id_bobina" in headers else "681"
            indutancia_uh = float(first_row[headers.index("indutancia_uh")]) if "indutancia_uh" in headers else 697.0
            resistencia_ohm = float(first_row[headers.index("resistencia_ohm")]) if "resistencia_ohm" in headers else 2.3
            diametro_mm = float(first_row[headers.index("diametro_mm")]) if "diametro_mm" in headers else 12.7
            altura_mm = float(first_row[headers.index("altura_mm")]) if "altura_mm" in headers else 10.9
            distancia_mm = float(first_row[headers.index("distancia_mm")]) if "distancia_mm" in headers else 0.0
            material = first_row[headers.index("material")] if "material" in headers else "Ar Livre"
            classe = normalizar_nome_classe(first_row[headers.index("classe")] if "classe" in headers else "Ar Livre")
            timestamp = first_row[headers.index("timestamp")] if "timestamp" in headers else ""
            dt_us = float(first_row[headers.index("dt_us")]) if "dt_us" in headers else 0.22656
            p_start = headers.index("p_0") if "p_0" in headers else 14
        except Exception:
            return None

        r_total_est = 100.0 + resistencia_ohm + 3.46
        all_curves = []
        all_taus = []
        all_aucs = []
        all_l_efetivas = []

        for row in rows:
            try:
                curva_row = [int(float(val)) for val in row[p_start:p_start+256]]
                tau_row, auc_row = calcular_tau_e_auc(curva_row, dt_us)
                l_ef_row = tau_row * r_total_est if tau_row > 0 else indutancia_uh
                
                all_curves.append(curva_row)
                all_taus.append(tau_row)
                all_aucs.append(auc_row)
                all_l_efetivas.append(l_ef_row)
            except Exception:
                continue

        if not all_curves:
            return None

        curva_media = np.mean(np.array(all_curves), axis=0).round().astype(int).tolist()
        tau_medio = float(np.mean(all_taus))
        auc_medio = float(np.mean(all_aucs))
        l_efetiva_media = float(np.mean(all_l_efetivas))

        std_tau = float(np.std(all_taus)) if len(all_taus) > 1 else 0.0
        std_auc = float(np.std(all_aucs)) if len(all_aucs) > 1 else 0.0

        return {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "num_samples": len(all_curves),
            "id_amostra": id_amostra,
            "id_bobina": id_bobina,
            "indutancia_uh": indutancia_uh,
            "resistencia_ohm": resistencia_ohm,
            "diametro_mm": diametro_mm,
            "altura_mm": altura_mm,
            "distancia_mm": distancia_mm,
            "material": material,
            "classe": classe,
            "timestamp": timestamp,
            "dt_us": dt_us,
            "curva": curva_media,
            "tau": tau_medio,
            "auc": auc_medio,
            "l_efetiva_uh": l_efetiva_media,
            "std_tau": std_tau,
            "std_auc": std_auc,
            "all_taus": all_taus,
            "all_aucs": all_aucs,
            "all_l_efetivas": all_l_efetivas,
            "all_curves": all_curves
        }

    def read_multiple_csvs(self, filepaths):
        results = []
        for fp in filepaths:
            rec = self.read_characterization_csv(fp)
            if rec is not None:
                results.append(rec)
        return results


class CoilRegistrationDialog(QtWidgets.QDialog):
    """
    Caixa de diálogo interativa para cadastrar, editar e excluir bobinas/sensores.
    """
    def __init__(self, coil_manager: CoilCharacterizationManager, parent=None, initial_coil_id=None):
        super().__init__(parent)
        self.coil_manager = coil_manager
        self.setWindowTitle("Cadastro e Edição de Bobinas / Sensores")
        self.resize(540, 640)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e24; color: #e1e1e6; }
            QLabel { color: #e1e1e6; font-size: 10pt; }
            QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTextEdit {
                background-color: #121214; color: #ffffff; border: 1px solid #3a3a3c;
                border-radius: 4px; padding: 4px; font-size: 10pt;
            }
            QPushButton { font-weight: bold; padding: 6px 12px; border-radius: 4px; }
        """)

        layout = QtWidgets.QVBoxLayout(self)

        top_group = QtWidgets.QGroupBox("Modo de Edição / Cadastro")
        top_group.setStyleSheet("QGroupBox { font-weight: bold; color: #29b6f6; }")
        top_layout = QtWidgets.QFormLayout(top_group)

        self.combo_select = QtWidgets.QComboBox()
        self.update_combo_list()
        self.combo_select.currentTextChanged.connect(self.on_select_coil_changed)
        top_layout.addRow("Selecionar para Editar:", self.combo_select)

        layout.addWidget(top_group)

        form_group = QtWidgets.QGroupBox("Parâmetros Físicos do Sensor")
        form_group.setStyleSheet("QGroupBox { font-weight: bold; color: #00e676; }")
        form_layout = QtWidgets.QFormLayout(form_group)

        self.edit_id = QtWidgets.QLineEdit()
        form_layout.addRow("ID / Código do Sensor:", self.edit_id)

        self.spin_inductance = QtWidgets.QDoubleSpinBox()
        self.spin_inductance.setRange(0.0, 10000.0)
        self.spin_inductance.setSuffix(" uH")
        self.spin_inductance.setValue(697.0)
        form_layout.addRow("Indutância Medida (L0):", self.spin_inductance)

        self.spin_resistance = QtWidgets.QDoubleSpinBox()
        self.spin_resistance.setRange(0.0, 200.0)
        self.spin_resistance.setSuffix(" Ohm")
        self.spin_resistance.setValue(2.30)
        form_layout.addRow("Resistência Medida (R):", self.spin_resistance)

        self.spin_diameter = QtWidgets.QDoubleSpinBox()
        self.spin_diameter.setRange(0.1, 500.0)
        self.spin_diameter.setSuffix(" mm")
        self.spin_diameter.setValue(12.7)
        form_layout.addRow("Diâmetro Total:", self.spin_diameter)

        self.spin_diameter_winding = QtWidgets.QDoubleSpinBox()
        self.spin_diameter_winding.setRange(0.1, 500.0)
        self.spin_diameter_winding.setSuffix(" mm")
        self.spin_diameter_winding.setValue(11.0)
        form_layout.addRow("Diâmetro Enrolamento:", self.spin_diameter_winding)

        self.spin_height = QtWidgets.QDoubleSpinBox()
        self.spin_height.setRange(0.1, 500.0)
        self.spin_height.setSuffix(" mm")
        self.spin_height.setValue(10.9)
        form_layout.addRow("Altura Total:", self.spin_height)

        self.spin_height_winding = QtWidgets.QDoubleSpinBox()
        self.spin_height_winding.setRange(0.1, 500.0)
        self.spin_height_winding.setSuffix(" mm")
        self.spin_height_winding.setValue(2.9)
        form_layout.addRow("Altura Enrolamento:", self.spin_height_winding)

        self.spin_turns = QtWidgets.QSpinBox()
        self.spin_turns.setRange(0, 100000)
        self.spin_turns.setValue(100)
        form_layout.addRow("Nº de Espiras (N):", self.spin_turns)

        self.edit_awg = QtWidgets.QLineEdit("27")
        form_layout.addRow("Bitola do Fio (AWG):", self.edit_awg)

        self.spin_wire_d = QtWidgets.QDoubleSpinBox()
        self.spin_wire_d.setRange(0.0, 20.0)
        self.spin_wire_d.setSuffix(" mm")
        self.spin_wire_d.setValue(0.361)
        form_layout.addRow("Diâmetro do Fio:", self.spin_wire_d)

        self.combo_core = QtWidgets.QComboBox()
        self.combo_core.addItems(["PLA", "AR", "FER", "Alumínio", "Aço", "Outro"])
        form_layout.addRow("Material do Núcleo:", self.combo_core)

        self.edit_description = QtWidgets.QTextEdit()
        self.edit_description.setMaximumHeight(50)
        form_layout.addRow("Descrição / Notas:", self.edit_description)

        layout.addWidget(form_group)

        btn_box = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("💾 Salvar / Atualizar Sensor")
        self.btn_save.setStyleSheet("background-color: #27ae60; color: white;")
        self.btn_save.clicked.connect(self.save_coil)
        btn_box.addWidget(self.btn_save)

        self.btn_delete = QtWidgets.QPushButton("🗑️ Excluir")
        self.btn_delete.setStyleSheet("background-color: #c0392b; color: white;")
        self.btn_delete.clicked.connect(self.delete_coil)
        btn_box.addWidget(self.btn_delete)

        self.btn_cancel = QtWidgets.QPushButton("Cancelar")
        self.btn_cancel.setStyleSheet("background-color: #7f8c8d; color: white;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

        if initial_coil_id and initial_coil_id in self.coil_manager.coils:
            idx = self.combo_select.findText(initial_coil_id)
            if idx >= 0:
                self.combo_select.setCurrentIndex(idx)
        else:
            self.on_select_coil_changed(self.combo_select.currentText())

    def update_combo_list(self):
        self.combo_select.clear()
        self.combo_select.addItem("[ Nova Bobina / Sensor ]")
        for cid in sorted(self.coil_manager.coils.keys()):
            self.combo_select.addItem(cid)

    def on_select_coil_changed(self, text):
        if text == "[ Nova Bobina / Sensor ]" or not text:
            self.edit_id.setEnabled(True)
            self.edit_id.clear()
            self.edit_id.setText(f"BOB_{len(self.coil_manager.coils)+1:03d}")
            self.spin_inductance.setValue(250.0)
            self.spin_resistance.setValue(1.50)
            self.spin_diameter.setValue(15.0)
            self.spin_diameter_winding.setValue(15.0)
            self.spin_height.setValue(8.5)
            self.spin_height_winding.setValue(8.5)
            self.spin_turns.setValue(100)
            self.edit_awg.setText("27")
            self.spin_wire_d.setValue(0.361)
            self.combo_core.setCurrentIndex(0)
            self.edit_description.clear()
            self.btn_delete.setEnabled(False)
        else:
            info = self.coil_manager.get_coil_info(text)
            if info:
                self.edit_id.setText(info["id"])
                self.edit_id.setEnabled(False)
                self.spin_inductance.setValue(info.get("inductance_uh", 0.0))
                self.spin_resistance.setValue(info.get("resistance_ohm", 0.0))
                self.spin_diameter.setValue(info.get("diameter_mm", 15.0))
                self.spin_diameter_winding.setValue(info.get("diameter_winding_mm", info.get("diameter_mm", 15.0)))
                self.spin_height.setValue(info.get("height_mm", 10.0))
                self.spin_height_winding.setValue(info.get("height_winding_mm", info.get("height_mm", 10.0)))
                self.spin_turns.setValue(info.get("turns", 0))
                self.edit_awg.setText(info.get("awg", "-"))
                self.spin_wire_d.setValue(info.get("wire_diameter_mm", 0.0))
                idx = self.combo_core.findText(info.get("core", "PLA"))
                if idx >= 0:
                    self.combo_core.setCurrentIndex(idx)
                self.edit_description.setText(info.get("description", ""))
                self.btn_delete.setEnabled(True)

    def save_coil(self):
        cid = self.edit_id.text().strip()
        if not cid or cid == "[ Nova Bobina / Sensor ]":
            QtWidgets.QMessageBox.warning(self, "ID Inválido", "Por favor, informe um ID válido para o sensor.")
            return

        self.coil_manager.register_coil(
            coil_id=cid,
            inductance_uh=self.spin_inductance.value(),
            resistance_ohm=self.spin_resistance.value(),
            diameter_mm=self.spin_diameter.value(),
            diameter_winding_mm=self.spin_diameter_winding.value(),
            height_mm=self.spin_height.value(),
            height_winding_mm=self.spin_height_winding.value(),
            turns=self.spin_turns.value(),
            awg=self.edit_awg.text().strip(),
            wire_diameter_mm=self.spin_wire_d.value(),
            core=self.combo_core.currentText(),
            description=self.edit_description.toPlainText().strip()
        )
        self.accept()

    def delete_coil(self):
        cid = self.edit_id.text().strip()
        if not cid or cid not in self.coil_manager.coils:
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Deseja realmente excluir a bobina '{cid}' do cadastro?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.coil_manager.delete_coil(cid)
            self.accept()


class Coil3DPlotDialog(QtWidgets.QDialog):
    """
    Diálogo modal interativo com gráfico 3D Matplotlib: Indutância Efetiva x AUC x Distância (Lift-Off).
    """
    def __init__(self, records, parent=None):
        super().__init__(parent)
        self.records = records or []
        self.setWindowTitle("📊 Gráfico 3D: Indutância Efetiva × AUC × Distância (Lift-Off)")
        self.resize(920, 720)
        self.setStyleSheet("""
            QDialog { background-color: #121214; color: #e1e1e6; }
            QLabel { color: #e1e1e6; font-size: 10pt; font-weight: bold; }
            QComboBox { background-color: #1e1e24; color: #ffffff; border: 1px solid #3a3a3c; border-radius: 4px; padding: 4px; font-size: 10pt; }
            QPushButton { font-weight: bold; padding: 6px 12px; border-radius: 4px; background-color: #8e44ad; color: white; }
        """)

        layout = QtWidgets.QVBoxLayout(self)

        top_bar = QtWidgets.QHBoxLayout()
        top_bar.addWidget(QtWidgets.QLabel("Agrupar/Colorir por:"))
        
        self.combo_group_by = QtWidgets.QComboBox()
        self.combo_group_by.addItems(["Material / Cupom", "ID da Bobina / Sensor", "Classe de Corrosão"])
        self.combo_group_by.currentIndexChanged.connect(self.plot_3d)
        top_bar.addWidget(self.combo_group_by)

        top_bar.addStretch()

        self.lbl_info = QtWidgets.QLabel(f"Total de Medições 3D: {len(self.records)}")
        top_bar.addWidget(self.lbl_info)

        layout.addLayout(top_bar)

        self.fig = Figure(figsize=(8, 6), dpi=100, facecolor='#121214')
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet("background-color: #1e1e24; color: #ffffff;")

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self.txt_point_info = QtWidgets.QLabel("💡 Dica: Clique com o mouse em qualquer ponto no gráfico 3D para ver os detalhes completos.")
        self.txt_point_info.setStyleSheet("background-color: #1e1e24; color: #00e676; padding: 8px; border-radius: 4px; font-family: monospace; font-size: 9.5pt;")
        layout.addWidget(self.txt_point_info)

        self.canvas.mpl_connect('pick_event', self.on_pick_point)

        self.plot_3d()

    def plot_3d(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111, projection='3d', facecolor='#121214')
        
        ax.set_facecolor('#121214')
        if hasattr(ax, 'xaxis') and hasattr(ax.xaxis, 'pane'):
            ax.xaxis.pane.set_facecolor((0.11, 0.11, 0.14, 1.0))
            ax.yaxis.pane.set_facecolor((0.11, 0.11, 0.14, 1.0))
            ax.zaxis.pane.set_facecolor((0.11, 0.11, 0.14, 1.0))
        elif hasattr(ax, 'w_xaxis'):
            ax.w_xaxis.set_pane_color((0.11, 0.11, 0.14, 1.0))
            ax.w_yaxis.set_pane_color((0.11, 0.11, 0.14, 1.0))
            ax.w_zaxis.set_pane_color((0.11, 0.11, 0.14, 1.0))
        
        ax.tick_params(colors='#e1e1e6')
        ax.set_xlabel('Distância - d (mm)', color='#00e676', labelpad=10, fontweight='bold')
        ax.set_ylabel('AUC (Counts·µs)', color='#ab47bc', labelpad=10, fontweight='bold')
        ax.set_zlabel('L Efetiva (µH)', color='#29b6f6', labelpad=10, fontweight='bold')
        ax.set_title("Espaço Tridimensional L x AUC x Distância", color='#ffffff', fontsize=12, pad=15, fontweight='bold')

        if not self.records:
            ax.text(0.5, 0.5, 0.5, "Nenhum teste importado", color='#ff5252', horizontalalignment='center')
            self.canvas.draw()
            return

        group_mode = self.combo_group_by.currentText()
        group_mode = self.combo_group_by.currentText()
        groups = {}
        total_pts = 0

        for rec in self.records:
            if "Material" in group_mode:
                key = rec.get("material", "Outro")
            elif "Bobina" in group_mode:
                key = f"Bobina {rec.get('id_bobina', '?')}"
            else:
                key = rec.get("classe", "Saudável").capitalize()

            if key not in groups:
                groups[key] = {"d": [], "auc": [], "l": [], "pt_info": []}

            all_a = rec.get("all_aucs", [rec.get("auc", 0.0)])
            all_l = rec.get("all_l_efetivas", [rec.get("l_efetiva_uh", 0.0)])
            all_t = rec.get("all_taus", [rec.get("tau", 0.0)])
            d_val = rec.get("distancia_mm", 0.0)
            n_tot = len(all_a)

            for i_sample, (a_val, l_val, t_val) in enumerate(zip(all_a, all_l, all_t)):
                groups[key]["d"].append(d_val)
                groups[key]["auc"].append(a_val)
                groups[key]["l"].append(l_val)
                groups[key]["pt_info"].append({
                    "rec": rec,
                    "sample_idx": i_sample,
                    "total_samples": n_tot,
                    "auc": a_val,
                    "l_efetiva_uh": l_val,
                    "tau": t_val
                })
                total_pts += 1

        self.lbl_info.setText(f"Total de Arquivos: {len(self.records)} | Pontos 3D Plotados: {total_pts}")

        palette = ['#00e676', '#29b6f6', '#ff9800', '#ab47bc', '#ff5252', '#e91e63', '#00bcd4', '#ffeb3b']
        self.pick_map = {}

        for idx, (g_name, data) in enumerate(groups.items()):
            color = palette[idx % len(palette)]
            
            sc = ax.scatter(
                data["d"], data["auc"], data["l"],
                c=color, label=g_name, s=60, edgecolors='#ffffff', alpha=0.85, picker=True
            )
            
            min_z = min(data["l"]) * 0.95 if data["l"] else 0
            for x, y, z in zip(data["d"], data["auc"], data["l"]):
                ax.plot([x, x], [y, y], [min_z, z], color=color, linestyle=':', alpha=0.25)

            for i_pt, pt_info in enumerate(data["pt_info"]):
                self.pick_map[(sc, i_pt)] = pt_info

        ax.legend(facecolor='#1e1e24', edgecolor='#3a3a3c', labelcolor='#ffffff', loc='upper left')
        self.canvas.draw()

    def on_pick_point(self, event):
        artist = event.artist
        ind = event.ind[0] if len(event.ind) > 0 else None
        if ind is not None and (artist, ind) in self.pick_map:
            info = self.pick_map[(artist, ind)]
            rec = info["rec"]
            n_tot = info["total_samples"]
            s_idx = info["sample_idx"]
            
            sample_label = f"{rec['id_amostra']} (Amostra {s_idx+1}/{n_tot})" if n_tot > 1 else str(rec['id_amostra'])

            info_str = (
                f"📌 PONTO 3D SELECIONADO: Arquivo: {rec['filename']} | Amostra: {sample_label} | "
                f"Bobina: ID {rec['id_bobina']} | Mat: {rec['material']} ({rec['classe']}) | "
                f"Dist (d): {rec['distancia_mm']:.2f} mm | AUC: {info['auc']:.1f} | L Efetiva: {info['l_efetiva_uh']:.2f} uH | Tau: {info['tau']:.4f} us"
            )
            self.txt_point_info.setText(info_str)
