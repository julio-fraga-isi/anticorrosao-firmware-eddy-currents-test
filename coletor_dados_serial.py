# -*- coding: utf-8 -*-
"""
Coletor de Dados Serial para Ensaio de Indutância
Lê as curvas de transiente enviadas pela NUCLEO-H753ZI e as salva em CSV.
"""

import serial
import serial.tools.list_ports
import csv
import time
import os

# Configurações da Porta Serial (ajuste a porta COM conforme seu gerenciador de dispositivos)
PORTA_SERIAL = 'COM3' 
BAUD_RATE = 115200
TIMEOUT_LEITURA = 2.0

def conectar_serial():
    global PORTA_SERIAL
    # Auto-detecta a porta do ST-Link
    portas = list(serial.tools.list_ports.comports())
    st_link_port = None
    for p in portas:
        desc = p.description.lower()
        if "stmicroelectronics" in desc or "stlink" in desc or "st-link" in desc:
            st_link_port = p.device
            break
            
    if st_link_port:
        PORTA_SERIAL = st_link_port
        print(f"[INFO] ST-Link auto-detectado na porta: {PORTA_SERIAL}")
    else:
        print(f"[INFO] ST-Link não detectado automaticamente. Tentando porta padrão: {PORTA_SERIAL}")

    try:
        ser = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=TIMEOUT_LEITURA)
        print(f"[OK] Conectado na porta {PORTA_SERIAL} a {BAUD_RATE} bps.")
        return ser
    except Exception as e:
        print(f"[ERRO] Falha ao conectar na porta {PORTA_SERIAL}: {e}")
        return None

def main():
    ser = conectar_serial()
    if not ser:
        print("Certifique-se de que a placa está conectada e o driver ST-Link virtual COM port está instalado.")
        return

    # Nome do arquivo de dataset
    arquivo_csv = "dataset_cupons_indutancia.csv"
    
    # Cria o cabeçalho se o arquivo não existir
    if not os.path.exists(arquivo_csv):
        with open(arquivo_csv, "w", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            # Exemplo de cabeçalho: classe da amostra, timestamp e 256 pontos da curva transiente
            cabecalho = ["id_amostra", "classe", "timestamp"] + [f"p_{i}" for i in range(256)]
            writer.writerow(cabecalho)

    print("\n--- Modo de Captura de Sinais de Indutância ---")
    print("Classes válidas: 'saudavel' ou 'corroido'")
    
    try:
        while True:
            id_amostra = input("\nDigite o ID ou Número do Cupom (ou 'sair' para encerrar): ").strip()
            if id_amostra.lower() == 'sair':
                break
                
            classe = input("Digite a classe ('s' para saudavel, 'c' para corroido): ").strip().lower()
            if classe == 's':
                classe_nome = "saudavel"
            elif classe == 'c':
                classe_nome = "corroido"
            else:
                print("Classe inválida! Digite 's' ou 'c'.")
                continue

            print(f"Aproxime o sensor do cupom {id_amostra} ({classe_nome}) e pressione ENTER na placa (ou envie sinal)...")
            
            # Limpa o buffer de entrada do serial
            ser.reset_input_buffer()
            
            # Envia um byte de requisição para a NUCLEO disparar o ensaio
            ser.write(b't') # 't' de trigger/teste
            
            print("Aguardando curva de resposta da placa...")
            linha = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if not linha:
                print("[AVISO] Timeout: Nenhuma resposta da placa recebida.")
                continue
                
            # A placa deve responder com os valores separados por vírgula (ex: 2048,2040,...,0)
            try:
                valores = [int(v) for v in linha.split(",")]
                if len(valores) == 0:
                    raise ValueError("Linha vazia")
                    
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                
                # Prepara a linha para salvar
                linha_dados = [id_amostra, classe_nome, timestamp] + valores
                
                # Salva no arquivo CSV
                with open(arquivo_csv, "a", newline="") as f:
                    writer = csv.writer(f, delimiter=";")
                    writer.writerow(linha_dados)
                    
                print(f"[SUCESSO] Curva salva! Recebidos {len(valores)} pontos da curva.")
                
            except PermissionError:
                print(f"\n[ERRO] Não foi possível salvar! O arquivo '{arquivo_csv}' está aberto em outro programa (provavelmente o Excel).")
                print("Feche o arquivo no outro programa e tente realizar a leitura deste cupom novamente.")
            except Exception as ex:
                print(f"[ERRO] Falha ao decodificar ou salvar os dados: {ex}")
                print(f"Dados brutos recebidos: {linha[:100]}...")

    except KeyboardInterrupt:
        print("\nCaptura interrompida pelo usuário.")
    finally:
        ser.close()
        print("Conexão serial fechada. Programa encerrado.")

if __name__ == "__main__":
    main()
