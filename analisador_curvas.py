# -*- coding: utf-8 -*-
"""
Analisador de Curvas de Indutância de Cupons
Processa o CSV de leituras, extrai a área sob a curva (AUC) e a constante de tempo (tau),
e gera gráficos comparativos de classificação.
"""

import numpy as np
import matplotlib.pyplot as plt
import csv
import os

def analisar_dataset(filepath="dataset_cupons_indutancia.csv"):
    if not os.path.exists(filepath):
        print(f"[ERRO] Arquivo {filepath} não encontrado. Execute o coletor ou gerador sintético primeiro.")
        return

    dados_saudavel = []
    dados_corroido = []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f, delimiter=';')
        cabecalho = next(reader)
        for row in reader:
            if len(row) < 4:
                continue
            classe = row[1].lower()
            # Os pontos da curva começam na coluna de índice 3
            valores = [float(val) for val in row[3:]]
            
            if "saud" in classe:
                dados_saudavel.append(valores)
            elif "corr" in classe:
                dados_corroido.append(valores)

    dados_saudavel = np.array(dados_saudavel)
    dados_corroido = np.array(dados_corroido)

    n_saudavel = len(dados_saudavel)
    n_corroido = len(dados_corroido)

    print(f"=== Resumo do Dataset ===")
    print(f"Amostras Saudáveis: {n_saudavel}")
    print(f"Amostras Corroídas: {n_corroido}")
    print("=========================")

    if n_saudavel == 0 and n_corroido == 0:
        print("[ERRO] Nenhuma amostra encontrada no dataset.")
        return

    # Eixo do tempo (amostragem a 9.6 MSPS -> dT = 0.10417 us)
    dt_us = 0.10417
    n_pontos = dados_saudavel.shape[1] if n_saudavel > 0 else dados_corroido.shape[1]
    tempo = np.arange(n_pontos) * dt_us

    # Listas para guardar as variáveis de resposta
    auc_s, auc_c = [], []
    tau_s, tau_c = [], []

    def calcular_metricas(curva):
        # 1. Encontra o pico do sinal para alinhar o início do transiente
        peak_idx = np.argmax(curva)
        curva_decaimento = curva[peak_idx:]
        tempo_decaimento = tempo[:len(curva_decaimento)]
        
        # 2. Estima o nível de offset (tensão final de regime estável) usando os últimos 10% da curva
        n_final = max(5, int(len(curva_decaimento) * 0.1))
        offset = np.mean(curva_decaimento[-n_final:])
        
        # 3. Área sob a curva (AUC) integrada apenas a partir do pico com offset subtraído
        curva_adj = np.clip(curva_decaimento - offset, 0, None)
        auc = np.sum(curva_adj) * dt_us
        
        # 4. Ajuste exponencial log-linear para extração da constante de tempo (Tau)
        curva_log = np.clip(curva_decaimento - offset, 1e-5, None)
        
        # Usamos os primeiros 30% da curva de decaimento (região mais linear em log) para o fit
        n_fit = int(len(curva_log) * 0.3)
        y_log = np.log(curva_log[:n_fit])
        t_fit = tempo_decaimento[:n_fit]
        
        try:
            # Regressão linear: Y = A + B * t  =>  B = -1/tau
            B, A = np.polyfit(t_fit, y_log, 1)
            tau = -1.0 / B if B != 0 else 0
        except Exception:
            tau = 0
            
        return auc, tau

    # Processa classe saudável
    for curva in dados_saudavel:
        auc, tau = calcular_metricas(curva)
        auc_s.append(auc)
        tau_s.append(tau)

    # Processa classe corroída
    for curva in dados_corroido:
        auc, tau = calcular_metricas(curva)
        auc_c.append(auc)
        tau_c.append(tau)

    # Impressão dos resultados estatísticos
    print("\n--- Estatísticas Comparativas ---")
    if n_saudavel > 0:
        print(f"Saudável - AUC média: {np.mean(auc_s):.2f} (±{np.std(auc_s):.2f}) V.us")
        print(f"Saudável - Tau médio: {np.mean(tau_s):.2f} (±{np.std(tau_s):.2f}) us")
    if n_corroido > 0:
        print(f"Corroído - AUC média: {np.mean(auc_c):.2f} (±{np.std(auc_c):.2f}) V.us")
        print(f"Corroído - Tau médio: {np.mean(tau_c):.2f} (±{np.std(tau_c):.2f}) us")
    print("---------------------------------")

    # Geração dos Gráficos
    fig, axs = plt.subplots(2, 2, figsize=(12, 10))
    
    # Grafico 1: Curva Média de Tensão
    if n_saudavel > 0:
        mean_s = np.mean(dados_saudavel, axis=0)
        std_s = np.std(dados_saudavel, axis=0)
        axs[0, 0].plot(tempo, mean_s, label="Saudável (Média)", color="blue", lw=2)
        axs[0, 0].fill_between(tempo, mean_s - std_s, mean_s + std_s, color="blue", alpha=0.15)
        
    if n_corroido > 0:
        mean_c = np.mean(dados_corroido, axis=0)
        std_c = np.std(dados_corroido, axis=0)
        axs[0, 0].plot(tempo, mean_c, label="Corroído (Média)", color="red", lw=2)
        axs[0, 0].fill_between(tempo, mean_c - std_c, mean_c + std_c, color="red", alpha=0.15)
        
    axs[0, 0].set_title("Sinal Transiente de Indutância (Média ± DP)")
    axs[0, 0].set_xlabel("Tempo (us)")
    axs[0, 0].set_ylabel("Tensão do ADC (Counts / Tensão)")
    axs[0, 0].grid(True)
    axs[0, 0].legend()

    # Grafico 2: Boxplot da AUC
    plot_data_auc = []
    labels = []
    if n_saudavel > 0:
        plot_data_auc.append(auc_s)
        labels.append("Saudável")
    if n_corroido > 0:
        plot_data_auc.append(auc_c)
        labels.append("Corroído")
        
    axs[0, 1].boxplot(plot_data_auc, tick_labels=labels)
    axs[0, 1].set_title("Comparação da Área sob a Curva (AUC)")
    axs[0, 1].set_ylabel("AUC (Counts.us)")
    axs[0, 1].grid(True)

    # Grafico 3: Boxplot do Tau
    plot_data_tau = []
    if n_saudavel > 0:
        plot_data_tau.append(tau_s)
    if n_corroido > 0:
        plot_data_tau.append(tau_c)
        
    axs[1, 0].boxplot(plot_data_tau, tick_labels=labels)
    axs[1, 0].set_title("Comparação da Constante de Tempo (Tau)")
    axs[1, 0].set_ylabel("Tau (us)")
    axs[1, 0].grid(True)

    # Grafico 4: Gráfico de Dispersão AUC vs Tau
    if n_saudavel > 0:
        axs[1, 1].scatter(tau_s, auc_s, color="blue", label="Saudável", alpha=0.7, edgecolors='k')
    if n_corroido > 0:
        axs[1, 1].scatter(tau_c, auc_c, color="red", label="Corroído", alpha=0.7, edgecolors='k')
    axs[1, 1].set_title("Espaço de Características: AUC vs Tau")
    axs[1, 1].set_xlabel("Tau (us)")
    axs[1, 1].set_ylabel("AUC (Counts.us)")
    axs[1, 1].grid(True)
    axs[1, 1].legend()

    plt.tight_layout()
    
    # Salva o gráfico
    output_img = "comparativo_curvas.png"
    plt.savefig(output_img, dpi=150)
    print(f"\n[OK] Gráfico comparativo salvo com sucesso em: {output_img}")
    plt.close()

if __name__ == "__main__":
    import sys
    arquivo = "dataset_cupons_indutancia.csv"
    if len(sys.argv) > 1:
        arquivo = sys.argv[1]
    elif os.path.exists("dataset_sintetico.csv") and not os.path.exists("dataset_cupons_indutancia.csv"):
        arquivo = "dataset_sintetico.csv"
        print("[INFO] Arquivo 'dataset_cupons_indutancia.csv' não encontrado. Usando 'dataset_sintetico.csv' por padrão.")
    
    analisar_dataset(arquivo)
