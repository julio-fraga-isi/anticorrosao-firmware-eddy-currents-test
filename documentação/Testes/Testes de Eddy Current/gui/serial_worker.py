import struct
import serial
import serial.tools.list_ports
from PyQt5 import QtCore
from gui.utils import calcular_crc16

class SerialWorker(QtCore.QThread):
    """Thread em segundo plano para comunicação serial sem travar a interface"""
    curva_recebida = QtCore.pyqtSignal(list, int)
    erro_serial = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.porta = None
        self.baud = 921600
        self.running = False
        self.trigger_requested = False
        self.ser = None
        self.mutex = QtCore.QMutex()

    def enviar_config_frequencia(self, period_ms):
        self.mutex.lock()
        try:
            if self.ser and self.ser.is_open:
                # Envia 'f' (0x66) seguido pelo período em ms (1 byte)
                self.ser.write(struct.pack('<BB', ord('f'), int(period_ms)))
                print(f"[SERIAL] Comando enviado: Frequência síncrona ajustada para {period_ms} ms (~{1000/period_ms:.1f} Hz)")
        except Exception as e:
            print(f"[ERRO SERIAL] Falha ao enviar comando de frequência: {e}")
        finally:
            self.mutex.unlock()

    def enviar_comando(self, cmd_byte):
        self.mutex.lock()
        try:
            if self.ser and self.ser.is_open:
                self.ser.write(cmd_byte)
                print(f"[SERIAL] Comando enviado: {cmd_byte.decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"[ERRO SERIAL] Falha ao enviar comando: {e}")
        finally:
            self.mutex.unlock()

    def enviar_config_dt(self, dt_ns):
        self.mutex.lock()
        try:
            if self.ser and self.ser.is_open:
                # Envia 'd' (0x64) seguido do dt em ns (uint16_t, formato little-endian)
                self.ser.write(struct.pack('<BH', ord('d'), int(dt_ns)))
                print(f"[SERIAL] Comando enviado: Intervalo dt físico ajustado para {dt_ns} ns")
        except Exception as e:
            print(f"[ERRO SERIAL] Falha ao enviar comando de dt: {e}")
        finally:
            self.mutex.unlock()

    def conectar(self, porta, baud=921600):
        self.porta = porta
        self.baud = baud
        self.running = True
        self.start()

    def desconectar(self):
        self.running = False
        self.wait()

    def disparar_leitura(self):
        self.mutex.lock()
        self.trigger_requested = True
        self.mutex.unlock()

    def run(self):
        try:
            # timeout de 100ms para permitir interrupção rápida de self.running
            self.ser = serial.Serial(self.porta, self.baud, timeout=0.1)
        except Exception as e:
            self.erro_serial.emit(str(e))
            return

        sync_state = 0
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

        while self.running:
            try:
                # Esvazia a variável trigger_requested se ela for acionada (não usada no disparo contínuo)
                self.mutex.lock()
                if self.trigger_requested:
                    self.trigger_requested = False
                self.mutex.unlock()

                # Busca pelo cabeçalho de sincronização [0xAA, 0x55, 0xAA, 0x55]
                b = self.ser.read(1)
                if not b:
                    continue
                
                if sync_state == 0 and b == b'\xaa':
                    sync_state = 1
                elif sync_state == 1 and b == b'\x55':
                    sync_state = 2
                elif sync_state == 2 and b == b'\xaa':
                    sync_state = 3
                elif sync_state == 3 and b == b'\x55':
                    # Sincronizado! Lê 518 bytes:
                    # 512 bytes (dados ADC) + 4 bytes (ciclos DWT) + 2 bytes (CRC-16)
                    data = self.ser.read(518)
                    if len(data) == 518:
                        # Extrai dados e CRC
                        valores_bytes = data[:512]
                        elapsed_cycles_bytes = data[512:516]
                        crc_recebido = struct.unpack('<H', data[516:518])[0]
                        
                        # Calcula e valida o CRC sobre a carga útil (512 bytes ADC + 4 bytes ciclos)
                        crc_calculado = calcular_crc16(valores_bytes + elapsed_cycles_bytes)
                        
                        if crc_recebido == crc_calculado:
                            valores = list(struct.unpack('<256H', valores_bytes))
                            elapsed_cycles = struct.unpack('<I', elapsed_cycles_bytes)[0]
                            self.curva_recebida.emit(valores, elapsed_cycles)
                        else:
                            print(f"[SERIAL] Erro de CRC! Recebido: {crc_recebido:#06x}, Calculado: {crc_calculado:#06x}")
                    sync_state = 0
                else:
                    sync_state = 0
            except Exception as e:
                self.erro_serial.emit(str(e))
                self.msleep(100)
        
        if self.ser:
            self.ser.close()
            self.ser = None
