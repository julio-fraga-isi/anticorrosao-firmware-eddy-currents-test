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
    if not valores or len(valores) == 0:
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
