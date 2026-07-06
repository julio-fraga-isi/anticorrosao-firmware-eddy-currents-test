# -*- coding: utf-8 -*-
"""
Osciloscópio Virtual em Tempo Real (Eddy Currents)
Dispara leituras periódicas na placa NUCLEO e plota os sinais do ADC 
em tempo real na tela, exibindo o cálculo de Tau e AUC live.
"""

import serial
import serial.tools.list_ports
import numpy as np
import matplotlib.pyplot as plt
import time
import sys

# Configurações da Porta Serial
PORTA_SERIAL = 'COM3' 
BAUD_RATE = 115200
TIMEOUT_LEITURA = 1.0

def auto_detectar_porta():
    global PORTA_SERIAL
    portas = list(serial.tools.list_ports.comports())
    for p in portas:
        desc = p.description.lower()
        if "stmicroelectronics" in desc or "stlink" in desc or "st-link" in desc:
            PORTA_SERIAL = p.device
            return True
    return False

def iniciar_plotter():
    if auto_detectar_porta():
        print(f"[INFO] ST-Link auto-detectado na porta: {PORTA_SERIAL}")
    else:
        print(f"[INFO] ST-Link não detectado. Tentando porta padrão: {PORTA_SERIAL}")

    try:
        ser = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=TIMEOUT_LEITURA)
        print(f"[OK] Conectado na porta {PORTA_SERIAL}.")
    except Exception as e:
        print(f"[ERRO] Falha ao conectar na serial {PORTA_SERIAL}: {e}")
        return

    # Ativa o modo interativo do matplotlib
    plt.ion()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    
    # Configurações do Gráfico 1: Sinal do ADC Completo
    x_completo = np.arange(256)
    y_completo = np.zeros(256)
    line1, = ax1.plot(x_completo, y_completo, 'b-', linewidth=2, label="Sinal Bruto")
    ax1.set_title("Osciloscópio Virtual: Sinal Completo do ADC", fontsize=12, fontweight='bold')
    ax1.set_xlabel("Índice de Amostragem")
    ax1.set_ylabel("Counts (16-bit)")
    ax1.set_ylim(-1000, 68000)
    ax1.grid(True)
    ax1.legend()

    # Configurações do Gráfico 2: Decaimento Transiente (Zoom)
    x_decaimento = np.arange(150) * 0.5625 # dt = 0.5625 us
    y_decaimento = np.zeros(150)
    line2, = ax2.plot(x_decaimento, y_decaimento, 'r-', linewidth=2, label="Decaimento Alinhado")
    ax2.set_title("Transiente de Decaimento (Subtraído Offset)", fontsize=12, fontweight='bold')
    ax2.set_xlabel("Tempo (us)")
    ax2.set_ylabel("Delta Counts")
    ax2.set_ylim(-500, 45000)
    ax2.grid(True)
    ax2.legend()
    
    fig.tight_layout()
    
    print("\n[OK] Plotter iniciado. Aproxime a bobina de materiais metálicos para observar.")
    print("Feche a janela do gráfico para encerrar o programa.")

    last_trigger_time = 0
    intervalo_trigger = 0.15 # 150ms entre disparos (cerca de 7 FPS)

    try:
        while plt.fignum_exists(fig.number):
            agora = time.time()
            if agora - last_trigger_time >= intervalo_trigger:
                # 1. Solicita nova leitura da placa
                ser.reset_input_buffer()
                ser.write(b't')
                last_trigger_time = agora
                
                # 2. Aguarda e lê a linha de resposta
                linha = ser.readline().decode('utf-8', errors='ignore').strip()
                if not linha:
                    continue
                
                # 3. Decodifica os valores
                try:
                    valores = [int(v) for v in linha.split(",")]
                    if len(valores) != 256:
                        continue
                    
                    valores = np.array(valores)
                    
                    # Processa as métricas para exibir no título
                    peak_idx = np.argmax(valores)
                    decay = valores[peak_idx:]
                    n_final = max(5, int(len(decay) * 0.1))
                    offset = np.mean(decay[-n_final:])
                    
                    # AUC
                    decay_adj = np.clip(decay - offset, 0, None)
                    auc = np.sum(decay_adj) * 0.5625 # dt = 0.5625 us
                    
                    # Tau (Fit linear dos primeiros 30%)
                    decay_log = np.clip(decay - offset, 1e-5, None)
                    n_fit = int(len(decay_log) * 0.3)
                    y_log = np.log(decay_log[:n_fit])
                    t_fit = np.arange(n_fit) * 0.5625
                    
                    try:
                        B, A = np.polyfit(t_fit, y_log, 1)
                        tau = -1.0 / B if B != 0 else 0
                    except:
                        tau = 0
                    
                    # 4. Atualiza os dados do gráfico
                    line1.set_ydata(valores)
                    
                    # Prepara os dados de decaimento com offset subtraído
                    y_dec = np.zeros(150)
                    comprimento_decaimento = min(150, len(decay_adj))
                    y_dec[:comprimento_decaimento] = decay_adj[:comprimento_decaimento]
                    line2.set_ydata(y_dec)
                    
                    # 5. Atualiza o título dinamicamente com as métricas em tempo real
                    ax1.set_title(f"Osciloscópio Virtual | AUC: {auc:.1f} V.us | Tau: {tau:.2f} us", fontsize=12, fontweight='bold')
                    
                    # Redesenha a tela
                    fig.canvas.draw()
                    fig.canvas.flush_events()
                    
                except ValueError:
                    pass
            
            # Pequeno delay para liberar a CPU
            plt.pause(0.01)
            
    except KeyboardInterrupt:
        print("\nPlotter interrompido pelo teclado.")
    finally:
        ser.close()
        print("Conexão serial fechada. Programa encerrado.")

if __name__ == "__main__":
    iniciar_plotter()
