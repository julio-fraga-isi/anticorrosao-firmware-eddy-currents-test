# -*- coding: utf-8 -*-
"""
Gerador de Dataset Sintético para Ensaio de Indutância
Gera curvas transientes sintéticas para simular cupons saudáveis e corroídos,
permitindo testar o analisador de dados localmente.
"""

import numpy as np
import csv
import time

def gerar_curvas_sinteticas(n_amostras_por_classe=20):
    n_pontos = 256
    dt_us = 0.277 # 3.6 MSPS
    tempo = np.arange(n_pontos) * dt_us
    
    arquivo_csv = "dataset_sintetico.csv"
    
    with open(arquivo_csv, "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        
        # Cabeçalho
        cabecalho = ["id_amostra", "classe", "timestamp"] + [f"p_{i}" for i in range(n_pontos)]
        writer.writerow(cabecalho)
        
        # 1. Gerar Amostras Saudáveis (Decaimento mais Rápido: menor Tau / menor Indutância)
        # Tau em torno de 40 us
        for i in range(n_amostras_por_classe):
            tau = np.random.normal(40.0, 2.5) # média 40 us, desvio padrão 2.5 us
            amplitude = np.random.normal(3000.0, 50.0) # Vstart em Counts (12-bit ADC max 4095)
            offset = np.random.normal(150.0, 10.0)
            ruido = np.random.normal(0, 15.0, size=n_pontos) # ruído Gaussiano
            
            # Equação do transiente: V(t) = V0 * e^(-t/tau) + offset + ruido
            curva = amplitude * np.exp(-tempo / tau) + offset + ruido
            curva = np.clip(curva, 0, 4095).astype(int) # Limita à resolução do ADC de 12 bits
            
            id_amostra = f"CUPOM_S_{i+1:02d}"
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            linha = [id_amostra, "saudavel", timestamp] + list(curva)
            writer.writerow(linha)

        # 2. Gerar Amostras Corroídas (Decaimento mais Lento: maior Tau / maior Indutância)
        # Tau em torno de 70 us
        for i in range(n_amostras_por_classe):
            tau = np.random.normal(70.0, 3.5) # média 70 us, desvio padrão 3.5 us
            amplitude = np.random.normal(3000.0, 50.0)
            offset = np.random.normal(150.0, 10.0)
            ruido = np.random.normal(0, 15.0, size=n_pontos)
            
            curva = amplitude * np.exp(-tempo / tau) + offset + ruido
            curva = np.clip(curva, 0, 4095).astype(int)
            
            id_amostra = f"CUPOM_C_{i+1:02d}"
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            linha = [id_amostra, "corroido", timestamp] + list(curva)
            writer.writerow(linha)
            
    print(f"[SUCESSO] Dataset sintético criado com {2 * n_amostras_por_classe} amostras em: {arquivo_csv}")

if __name__ == "__main__":
    gerar_curvas_sinteticas()
