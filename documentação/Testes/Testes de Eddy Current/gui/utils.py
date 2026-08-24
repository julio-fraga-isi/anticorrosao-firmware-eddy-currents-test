import numpy as np
import unicodedata

def normalizar_nome_classe(classe_str):
    """
    Normaliza a string de classe/degradação para garantir correspondência exata,
    removendo acentos, espaços extras e ajustando capitalização.
    """
    if not classe_str:
        return "Sem Dados"
    
    # Remove acentos e converte para minúsculas
    classe_normalizada = "".join(
        c for c in unicodedata.normalize("NFD", classe_str.strip())
        if unicodedata.category(c) != "Mn"
    ).lower()
    
    if "saudavel" in classe_normalizada:
        return "Saudável"
    elif "leve" in classe_normalizada:
        return "Leve"
    elif "moderada" in classe_normalizada:
        return "Moderada"
    elif "avancada" in classe_normalizada or "avançada" in classe_normalizada:
        return "Avançada"
    elif "corroido" in classe_normalizada:
        return "Corroído"
    elif "ar livre" in classe_normalizada or "arlivre" in classe_normalizada:
        return "Ar Livre"
    elif "nao definido" in classe_normalizada or "naodefinido" in classe_normalizada or classe_normalizada == "nd":
        return "Não Definido"
    
    return "Sem Dados"

def calcular_crc16(data: bytes) -> int:
    """
    Calcula o CRC-16-CCITT (polinômio 0x1021, valor inicial 0xFFFF).
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def calcular_tau_e_auc(valores, dt_us):
    """
    Calcula a área sob a curva (AUC) e a constante de tempo (Tau) de decaimento
    para um transitório indutivo.
    """
    if valores is None or len(valores) == 0:
        return 0.0, 0.0
        
    valores_arr = np.array(valores)
    peak_idx = np.argmax(valores_arr)
    decay = valores_arr[peak_idx:]
    
    if len(decay) < 10:
        return 0.0, 0.0

    # 1. Estima o offset usando os últimos 10% da curva de decaimento
    n_final = max(5, int(len(decay) * 0.1))
    offset = np.mean(decay[-n_final:])
    
    # 2. Calcula a área sob a curva (AUC) com offset subtraído
    decay_adj = np.clip(decay - offset, 0, None)
    auc = np.sum(decay_adj) * dt_us
    
    # 3. Calcula Tau através de ajuste linear nos primeiros 30% do decaimento
    decay_log = np.clip(decay - offset, 1e-5, None)
    n_fit = int(len(decay_log) * 0.3)
    if n_fit < 3:
        n_fit = 3
        
    y_log = np.log(decay_log[:n_fit])
    t_fit = np.arange(n_fit) * dt_us
    
    try:
        B, A = np.polyfit(t_fit, y_log, 1)
        tau = -1.0 / B if B != 0 else 0.0
    except Exception:
        tau = 0.0
        
    return tau, auc


class AdaptiveRealtimeStabilizer:
    """
    Filtro Adaptativo Inteligente de Estabilidade em Tempo Real (Fast-Attack & Zero-Jitter Lock)
    - Elimina atrasos de convergência (resposta imediata em ~100ms quando a condição física muda).
    - Elimina 100% de oscilações e pulos de ruído quando o sensor está estático sobre a amostra.
    """
    def __init__(self, deadband_rel=0.015, step_threshold_rel=0.035, fast_alpha=0.85, slow_alpha=0.15):
        self.deadband_rel = deadband_rel
        self.step_threshold_rel = step_threshold_rel
        self.fast_alpha = fast_alpha
        self.slow_alpha = slow_alpha
        
        self.v_estavel = None
        self.tau_estavel = None
        self.auc_estavel = None
        self.recent_window = []

    def reset(self):
        self.v_estavel = None
        self.tau_estavel = None
        self.auc_estavel = None
        self.recent_window = []

    def process(self, v_raw, dt_us, deadband_override=None):
        if v_raw is None or len(v_raw) == 0:
            return None, 0.0, 0.0

        v_curr = np.array(v_raw, dtype=float)
        
        # 1. Detecção Precoce de Degrau / Mudança de Peça (Fast-Track Instantâneo)
        if self.v_estavel is not None and self.v_estavel.shape == v_curr.shape:
            max_v = max(1.0, float(np.max(self.v_estavel)))
            diff_raw = float(np.max(np.abs(v_curr - self.v_estavel))) / max_v
            if diff_raw > self.step_threshold_rel:
                # Mudança física real detectada: reseta o buffer de mediana e salta imediatamente
                self.recent_window = [v_curr]
                self.v_estavel = np.copy(v_curr)
                self.tau_estavel, self.auc_estavel = calcular_tau_e_auc(self.v_estavel, dt_us)
                return self.v_estavel, self.tau_estavel, self.auc_estavel

        # 2. Buffer rápido de mediana (5 amostras) para rejeitar picos de ruído transitório
        if len(self.recent_window) > 0 and self.recent_window[0].shape != v_curr.shape:
            self.recent_window = []
        self.recent_window.append(v_curr)
        if len(self.recent_window) > 5:
            self.recent_window = self.recent_window[-5:]
        
        if len(self.recent_window) >= 3:
            v_filtered = np.median(self.recent_window, axis=0)
        else:
            v_filtered = v_curr

        # 3. Inicialização
        if self.v_estavel is None or self.v_estavel.shape != v_filtered.shape:
            self.v_estavel = np.copy(v_filtered)
            tau_c, auc_c = calcular_tau_e_auc(self.v_estavel, dt_us)
            self.tau_estavel = tau_c
            self.auc_estavel = auc_c
            return self.v_estavel, self.tau_estavel, self.auc_estavel

        # 4. Controle de Zona Morta (Deadband / Zero-Jitter Lock)
        max_v = max(1.0, float(np.max(self.v_estavel)))
        diff_max = float(np.max(np.abs(v_filtered - self.v_estavel))) / max_v
        
        db = deadband_override if deadband_override is not None else self.deadband_rel

        if diff_max < db:
            # REGIME ESTÁTICO (Ruído de quantização/ADC): Congelamento Total (Zero Jitter)
            return self.v_estavel, self.tau_estavel, self.auc_estavel
        else:
            # AJUSTE FINO SUAVE
            self.v_estavel = self.slow_alpha * v_filtered + (1.0 - self.slow_alpha) * self.v_estavel

        # 5. Cálculo e Estabilização das Métricas Tau e AUC
        tau_calc, auc_calc = calcular_tau_e_auc(self.v_estavel, dt_us)
        
        if self.tau_estavel is None or self.tau_estavel <= 0:
            self.tau_estavel = tau_calc
        else:
            diff_tau = abs(tau_calc - self.tau_estavel) / max(0.1, self.tau_estavel)
            if diff_tau < db:
                pass  # Congela
            else:
                self.tau_estavel = self.slow_alpha * tau_calc + (1.0 - self.slow_alpha) * self.tau_estavel

        if self.auc_estavel is None or self.auc_estavel <= 0:
            self.auc_estavel = auc_calc
        else:
            diff_auc = abs(auc_calc - self.auc_estavel) / max(1.0, self.auc_estavel)
            if diff_auc < db:
                pass  # Congela
            else:
                self.auc_estavel = self.slow_alpha * auc_calc + (1.0 - self.slow_alpha) * self.auc_estavel

        return self.v_estavel, self.tau_estavel, self.auc_estavel

