# -*- coding: utf-8 -*-
"""
Visualizador de Sinais do ADC (Saudável vs Corroído)
Plota as curvas brutas coletadas diretamente para verificar se há alguma diferença
no sinal lido pelo ADC ao aproximar os cupons.
"""

import numpy as np
import matplotlib.pyplot as plt
import csv
import os

def gerar_visualizacao():
    filepath = "dataset_cupons_indutancia.csv"
    if not os.path.exists(filepath):
        print(f"[ERRO] Arquivo {filepath} não encontrado.")
        return

    curvas = {}
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader) # Pula cabeçalho
        for row in reader:
            if not row:
                continue
            classe = row[1].lower()
            valores = np.array([float(x) for x in row[3:]])
            if "saud" in classe:
                curvas['saudavel'] = valores
            elif "corr" in classe:
                curvas['corroido'] = valores

    if len(curvas) < 2:
        print("[ERRO] É necessário ter pelo menos uma curva de cada classe ('saudavel' e 'corroido') no CSV.")
        return

    # Alinha as curvas pelo pico
    curva_s = curvas.get('saudavel')
    curva_c = curvas.get('corroido')
    
    pico_s = np.argmax(curva_s)
    pico_c = np.argmax(curva_c)
    
    # Extrai o decaimento a partir do pico
    decaimento_s = curva_s[pico_s:pico_s + 150]
    decaimento_c = curva_c[pico_c:pico_c + 150]
    
    tempo = np.arange(len(decaimento_s)) * 0.10417 # usando o dt de 9.6 MSPS em us

    plt.figure(figsize=(12, 8))
    
    # Subplot 1: Curvas Completas do ADC
    plt.subplot(2, 1, 1)
    plt.plot(curva_s, label="Saudável", color="blue", alpha=0.8, linewidth=2)
    plt.plot(curva_c, label="Corroído", color="red", alpha=0.8, linewidth=2)
    plt.axvline(pico_s, color="blue", linestyle="--", alpha=0.5, label="Pico Saudável")
    plt.axvline(pico_c, color="red", linestyle="--", alpha=0.5, label="Pico Corroído")
    plt.title("Sinais Brutos do ADC (Buffer Completo de 256 Amostras)")
    plt.xlabel("Índice de Amostragem")
    plt.ylabel("Contas do ADC (16-bit)")
    plt.grid(True)
    plt.legend()

    # Subplot 2: Decaimento Alinhado (Zoom)
    plt.subplot(2, 2, 3)
    plt.plot(tempo, decaimento_s, label="Saudável", color="blue", linewidth=2)
    plt.plot(tempo, decaimento_c, label="Corroído", color="red", linewidth=2)
    plt.title("Decaimento Alinhado (Zoom)")
    plt.xlabel("Tempo (us)")
    plt.ylabel("Contas do ADC")
    plt.grid(True)
    plt.legend()

    # Subplot 3: Diferença entre os Sinais (Saudável - Corroído)
    diferenca = decaimento_s - decaimento_c
    plt.subplot(2, 2, 4)
    plt.plot(tempo, diferenca, color="purple", linewidth=2, label="Diferença (S - C)")
    plt.axhline(0, color="black", linestyle="--", alpha=0.5)
    plt.title("Diferença entre Sinais (Saudável - Corroído)")
    plt.xlabel("Tempo (us)")
    plt.ylabel("Diferença (Counts)")
    plt.grid(True)
    plt.legend()

    plt.tight_layout()
    output_filename = "visualizacao_sinais_real.png"
    plt.savefig(output_filename, dpi=150)
    print(f"[OK] Gráfico de comparação bruta salvo em: {output_filename}")
    plt.close()

if __name__ == "__main__":
    gerar_visualizacao()
