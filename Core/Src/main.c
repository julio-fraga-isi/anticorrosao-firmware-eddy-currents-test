/**
  ******************************************************************************
  * @file           : nucleo_firmware_template.c
  * @brief          : Template de firmware para NUCLEO-H753ZI para ensaio RL
  *                   Este código ilustra a integração do ADC + DMA + Timer
  ******************************************************************************
  */

#include "main.h"
#include <stdio.h>
#include <string.h>

/* Configurações do Buffer do ADC */
#define ADC_BUFFER_SIZE 256
uint16_t adc_buffer[ADC_BUFFER_SIZE];
volatile uint8_t adc_conversion_complete = 0;

/* Handles de Periféricos (devem ser inicializados pelo STM32CubeMX) */
extern ADC_HandleTypeDef hadc1;
extern DMA_HandleTypeDef hdma_adc1;
extern TIM_HandleTypeDef htim1;
extern UART_HandleTypeDef huart3; // Porta UART conectada ao ST-LINK USB

/* Função para enviar strings via UART3 */
void UART_Print(const char* str) {
    HAL_UART_Transmit(&huart3, (uint8_t*)str, strlen(str), HAL_MAX_DELAY);
}

/* Callback chamado quando a transferência do DMA do ADC é concluída */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef* hadc) {
    if (hadc->Instance == ADC1) {
        adc_conversion_complete = 1;
        HAL_ADC_Stop_DMA(&hadc1);
    }
}

/* Função para disparar a excitação e amostragem transiente */
void ExecutarEnsaioRL(void) {
    adc_conversion_complete = 0;
    
    // 1. Garante que o pino de excitação (PA0) comece em nível baixo (0V)
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_RESET);
    HAL_Delay(10); // Aguarda desmagnetização/estabilização
    
    // 2. Inicia a conversão ADC via DMA
    // O ADC está configurado para disparar por hardware trigger (TIM1 TRGO)
    HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buffer, ADC_BUFFER_SIZE);
    
    // 3. Inicia o Timer 1.
    // O TIM1 gerará um pulso na saída PWM (ou interrupção) que excita a bobina 
    // e disparará a trigger TRGO para sincronizar o ADC.
    //
    // Como alternativa simplificada de baixo jitter:
    // Nós podemos levantar o pino GPIO e iniciar o ADC por software imediatamente:
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_SET); // Borda de subida (Início do transiente)
    
    // Se o ADC não estiver usando trigger por Timer, iniciamos a conversão direta:
    // (Em STM32H7, a conversão por software direta é rápida o suficiente se o clock for alto)
    // HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buffer, ADC_BUFFER_SIZE);
    
    // 4. Aguarda a conclusão da aquisição pelo DMA (com timeout robusto de 100 ms)
    uint32_t start_tick = HAL_GetTick();
    while (!adc_conversion_complete && (HAL_GetTick() - start_tick < 100)) {
        // Aguarda a conversão
    }
    
    // 5. Retorna o pino de excitação a nível baixo (0V)
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_RESET);
    
    if (adc_conversion_complete) {
        // Envia a curva em formato CSV (valores separados por vírgula) via UART
        char tx_buffer[32];
        for (int i = 0; i < ADC_BUFFER_SIZE; i++) {
            sprintf(tx_buffer, "%d", adc_buffer[i]);
            UART_Print(tx_buffer);
            if (i < ADC_BUFFER_SIZE - 1) {
                UART_Print(",");
            }
        }
        UART_Print("\r\n"); // Fim da linha da curva
    } else {
        UART_Print("[ERRO] Timeout na aquisição do ADC\r\n");
    }
}

/* 
 * Coloque este trecho dentro da função main(), no loop infinito while(1) 
 * na seção USER CODE 3:
 */
void ExemploLoopInfinito(void) {
    uint8_t rx_byte = 0;
    
    // Aguarda receber o caractere 't' da UART3 (PC) para iniciar
    if (HAL_UART_Receive(&huart3, &rx_byte, 1, 100) == HAL_OK) {
        if (rx_byte == 't') {
            ExecutarEnsaioRL();
        }
    }
}
