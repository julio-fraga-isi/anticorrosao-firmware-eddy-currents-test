import os
import csv
import numpy as np
from gui.utils import normalizar_nome_classe, calcular_tau_e_auc

class DatasetManager:
    def __init__(self):
        # Cache keyed by CSV filepath:
        # { filepath: { 'mtime': float, 'size': int, 'records': list } }
        self._cache = {}

    def get_records(self, filepath):
        if not os.path.exists(filepath):
            return []

        try:
            stat = os.stat(filepath)
        except Exception:
            return []
            
        cached = self._cache.get(filepath)
        
        # Check if cache is valid (same size and modification time)
        if cached and cached['mtime'] == stat.st_mtime and cached['size'] == stat.st_size:
            return cached['records']

        # Cache miss: reload the whole CSV
        records = self._load_csv(filepath)
        self._cache[filepath] = {
            'mtime': stat.st_mtime,
            'size': stat.st_size,
            'records': records
        }
        return records

    def _load_csv(self, filepath):
        records = []
        conteudo_csv = None
        
        # Fallback encoding logic
        try:
            with open(filepath, "r", newline="", encoding="utf-8") as f:
                conteudo_csv = f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, "r", newline="", encoding="latin-1") as f:
                    conteudo_csv = f.read()
            except Exception:
                return []
        except Exception:
            return []

        import io
        f_string = io.StringIO(conteudo_csv)
        reader = csv.reader(f_string, delimiter=";")
        try:
            headers = next(reader)
        except StopIteration:
            return []

        try:
            id_idx = headers.index("id_amostra") if "id_amostra" in headers else 0
            material_idx = headers.index("material") if "material" in headers else 1
            classe_idx = headers.index("classe") if "classe" in headers else 2
            dt_idx = headers.index("dt_us") if "dt_us" in headers else -1
            p_start_idx = headers.index("p_0") if "p_0" in headers else 4
        except ValueError:
            # Fallback if headers are missing or mismatched
            id_idx, material_idx, classe_idx, dt_idx, p_start_idx = 0, 1, 2, -1, 4

        for row in reader:
            if not row or len(row) < 260:
                continue

            id_amostra = row[id_idx].strip()
            material = row[material_idx].strip() if len(row) > material_idx else "A36 Comum"
            classe = normalizar_nome_classe(row[classe_idx])

            if len(row) >= 261:
                try:
                    row_dt = float(row[4].strip()) if row[4].strip() else 0.21875
                except ValueError:
                    row_dt = 0.21875
                p_start = 5
            else:
                row_dt = 0.21875
                p_start = 4

            try:
                curva = [int(val) for val in row[p_start:p_start+256]]
            except ValueError:
                continue

            # Calculate tau and auc
            tau, auc = calcular_tau_e_auc(curva, row_dt)
            if tau > 0:
                # Determina se os dados são filtrados baseado no ruído de cauda
                is_filtered = False
                if len(curva) >= 60:
                    tail_noise = np.var(np.diff(np.diff(curva[-60:])))
                    is_filtered = (tail_noise < 5500.0)

                records.append({
                    'id_amostra': id_amostra,
                    'material': material,
                    'classe': classe,
                    'dt_us': row_dt,
                    'curva': curva,
                    'tau': tau,
                    'auc': auc,
                    'is_filtered': is_filtered
                })

        return records

    def append_record(self, filepath, id_amostra, material, classe, dt_us, curva, timestamp):
        # Calculate features first
        tau, auc = calcular_tau_e_auc(curva, dt_us)
        
        # Write to file
        dir_name = os.path.dirname(filepath)
        if dir_name and not os.path.exists(dir_name):
            try:
                os.makedirs(dir_name, exist_ok=True)
            except Exception:
                pass

        escrever_cabecalho = not os.path.exists(filepath)
        try:
            with open(filepath, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=";")
                if escrever_cabecalho:
                    cabecalho = ["id_amostra", "material", "classe", "timestamp", "dt_us"] + [f"p_{i}" for i in range(256)]
                    writer.writerow(cabecalho)
                
                linha = [id_amostra, material, classe, timestamp, f"{dt_us:.5f}"] + [str(x) for x in curva]
                writer.writerow(linha)
        except Exception as e:
            raise e

        # Determine if filtered
        is_filtered = False
        if len(curva) >= 60:
            tail_noise = np.var(np.diff(np.diff(curva[-60:])))
            is_filtered = (tail_noise < 100000.0)

        # Update cache in memory
        record = {
            'id_amostra': id_amostra,
            'material': material,
            'classe': normalizar_nome_classe(classe),
            'dt_us': dt_us,
            'curva': curva,
            'tau': tau,
            'auc': auc,
            'is_filtered': is_filtered
        }

        try:
            stat = os.stat(filepath)
            if filepath in self._cache:
                self._cache[filepath]['records'].append(record)
                self._cache[filepath]['size'] = stat.st_size
                self._cache[filepath]['mtime'] = stat.st_mtime
            else:
                self._cache[filepath] = {
                    'mtime': stat.st_mtime,
                    'size': stat.st_size,
                    'records': [record]
                }
        except Exception:
            # If stat fails, invalidate cache to force reload on next read
            self.invalidate_cache(filepath)

    def invalidate_cache(self, filepath):
        if filepath in self._cache:
            del self._cache[filepath]
            
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
                amostras_filtradas.extend(grupo)
                continue
                
            taus = [a['tau'] for a in grupo]
            aucs = [a['auc'] for a in grupo]
            
            q1_tau, q3_tau = np.percentile(taus, [25, 75])
            iqr_tau = q3_tau - q1_tau
            lim_inf_tau = q1_tau - 1.5 * iqr_tau
            lim_sup_tau = q3_tau + 1.5 * iqr_tau
            
            q1_auc, q3_auc = np.percentile(aucs, [25, 75])
            iqr_auc = q3_auc - q1_auc
            lim_inf_auc = q1_auc - 1.5 * iqr_auc
            lim_sup_auc = q3_auc + 1.5 * iqr_auc
            
            for a in grupo:
                is_ok_tau = (lim_inf_tau <= a['tau'] <= lim_sup_tau)
                is_ok_auc = (lim_inf_auc <= a['auc'] <= lim_sup_auc)
                if is_ok_tau and is_ok_auc:
                    amostras_filtradas.append(a)
                    
        return amostras_filtradas
