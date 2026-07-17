/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "adc.h"
#include "dma.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define EXCITACAO_PIN_Pin GPIO_PIN_0
#define EXCITACAO_PIN_GPIO_Port GPIOA
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
#define ADC_BUFFER_SIZE 256
uint16_t adc_buffer[ADC_BUFFER_SIZE] __attribute__((aligned(32)));
volatile uint8_t adc_conversion_complete = 0;
uint8_t tx_dma_buffer[544] __attribute__((aligned(32))); // 4 bytes cabeçalho + 512 bytes dados, alinhado ao cache do Cortex-M7

// Variáveis para controle da Frequência de Disparo Síncrona via UART (padrão: 33 ms = ~30 Hz)
volatile uint8_t ensaio_period_ms = 33;
volatile uint8_t ensaio_ativo = 0;             // 0 = Pausado (Padrão), 1 = Rodando Contínuo
volatile uint8_t single_trigger_requested = 0; // Flag para disparo de leitura única
volatile uint16_t ensaio_dt_ns = 218;          // Intervalo de amostragem padrão (218 ns)
uint8_t uart_rx_byte;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
void ExecutarEnsaioRL(void);
void ExecutarEnsaioRL_ETS(void);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef* hadc) {
  if (hadc->Instance == ADC1) {
    adc_conversion_complete = 1;
    HAL_ADC_Stop_DMA(hadc);
    
    // Desabilita o Timer 3 (metrônomo) para parar triggers pós-fim de bloco
    __HAL_TIM_DISABLE(&htim3);
    __HAL_TIM_SET_COUNTER(&htim3, 0);
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
  if (huart->Instance == USART3) {
    static uint8_t rx_state = 0;
    static uint8_t rx_period = 0;
    static uint8_t rx_dt_bytes[2] = {0};
    static uint8_t rx_dt_idx = 0;
    
    if (rx_state == 0) {
      if (uart_rx_byte == 'f') {
        rx_state = 1;
      } else if (uart_rx_byte == 'p') {
        ensaio_ativo = 0; // Pausa a aquisição contínua
      } else if (uart_rx_byte == 'r') {
        ensaio_ativo = 1; // Retoma a aquisição contínua
      } else if (uart_rx_byte == 't') {
        single_trigger_requested = 1; // Solicita disparo único seguro fora da interrupção
      } else if (uart_rx_byte == 'd') {
        rx_state = 2; // Recebe o valor de dt (ns) em 2 bytes
        rx_dt_idx = 0;
      }
    } else if (rx_state == 1) {
      rx_period = uart_rx_byte;
      // Garante limites de segurança do período (entre 5 ms e 250 ms)
      if (rx_period >= 5 && rx_period <= 250) {
        ensaio_period_ms = rx_period;
      }
      rx_state = 0;
    } else if (rx_state == 2) {
      rx_dt_bytes[rx_dt_idx++] = uart_rx_byte;
      if (rx_dt_idx >= 2) {
        uint16_t novo_dt = (uint16_t)(rx_dt_bytes[0] | (rx_dt_bytes[1] << 8));
        // Limites de segurança do dt (entre 100 ns e 10000 ns)
        if (novo_dt >= 100 && novo_dt <= 10000) {
          ensaio_dt_ns = novo_dt;
          // Recalcula o ARR do TIM3 (Timer 3 roda a 240 MHz, ticks = dt_ns * 240 / 1000)
          uint32_t timer_ticks = ((uint32_t)ensaio_dt_ns * 240) / 1000;
          if (timer_ticks > 0) {
            htim3.Instance->ARR = timer_ticks - 1;
          } else {
            htim3.Instance->ARR = 0;
          }
        }
        rx_state = 0;
      }
    } else {
      rx_state = 0;
    }
    
    // Rearma a interrupção para continuar escutando comandos da GUI
    HAL_UART_Receive_IT(huart, &uart_rx_byte, 1);
  }
}

static inline void DelayCycles(uint32_t cycles) {
  uint32_t start = DWT->CYCCNT;
  while ((DWT->CYCCNT - start) < cycles);
}

void ExecutarEnsaioRL(void) {
  adc_conversion_complete = 0;
  
  // 1. Atraso de 100 µs (48.000 ciclos de clock a 480 MHz) para descarga total da bobina
  // O TIM2 inativo em One-Pulse desliga a saída de hardware e mantém em 0V.
  DelayCycles(48000);

  // 2. Invalida o D-Cache do buffer de recepção antes que o ADC DMA grave nele
  SCB_InvalidateDCache_by_Addr((uint32_t*)adc_buffer, ADC_BUFFER_SIZE * 2);
  
  // Desabilita interrupções temporariamente para sincronia perfeita e prevenção de preempção no disparo
  uint32_t primask = __get_PRIMASK();
  __disable_irq();

  // 3. Inicia ADC via DMA (ele fica em prontidão aguardando o trigger de hardware do TIM3)
  HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buffer, ADC_BUFFER_SIZE);

  // Garante que o contador do TIM3 comece em 0
  __HAL_TIM_SET_COUNTER(&htim3, 0);

  // Garante que o contador do TIM2 comece em 0 e gera um evento de update por software (UG)
  // Isso força uma atualização imediata dos registradores e emite um pulso TRGO (TIM_TRGO_UPDATE)
  // que dispara o TIM3 (Slave) no instante exato de início do ensaio.
  __HAL_TIM_SET_COUNTER(&htim2, 0);
  htim2.Instance->EGR = TIM_EGR_UG;
  __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_UPDATE);
  
  // Captura o ciclo de início exato antes do disparo de hardware
  uint32_t start_cycles = DWT->CYCCNT;

  // 4. Inicia o TIM2 em modo PWM (One-Pulse)
  // Isso gera fisicamente o pulso de 56 µs no pino PA0 em absoluto sincronismo
  HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1);
  
  // Restaura interrupções
  __set_PRIMASK(primask);
  
  // 5. Aguarda a conclusão (com timeout robusto de 100 ms)
  uint32_t start_tick = HAL_GetTick();
  while (!adc_conversion_complete && (HAL_GetTick() - start_tick < 100)) {
    // Aguarda a conversão do ADC pelo DMA (sinalizada pelo callback de interrupção)
  }
  
  // Captura o ciclo de término exato do ensaio
  uint32_t end_cycles = DWT->CYCCNT;
  uint32_t elapsed_cycles = end_cycles - start_cycles;

  // 6. Finaliza os periféricos por segurança após a aquisição
  HAL_ADC_Stop_DMA(&hadc1);
  
  // Desabilita o Timer 3
  __HAL_TIM_DISABLE(&htim3);
  __HAL_TIM_SET_COUNTER(&htim3, 0);
  
  // Para o contador mas mantém a saída ativa em 0V com baixa impedância (evita pino flutuante e ringing)
  __HAL_TIM_DISABLE(&htim2);
  __HAL_TIM_SET_COUNTER(&htim2, 100);
  
  if (!adc_conversion_complete) {
    // Se falhar, zera o buffer por segurança
    memset(adc_buffer, 0, sizeof(adc_buffer));
    elapsed_cycles = 0;
  } else {
    // Invalida o D-Cache novamente após a gravação pelo DMA para a CPU ler os valores novos
    SCB_InvalidateDCache_by_Addr((uint32_t*)adc_buffer, ADC_BUFFER_SIZE * 2);
  }

  // 7. Transmite em Binário via DMA com cabeçalho de sincronização
  tx_dma_buffer[0] = 0xAA;
  tx_dma_buffer[1] = 0x55;
  tx_dma_buffer[2] = 0xAA;
  tx_dma_buffer[3] = 0x55;
  memcpy(&tx_dma_buffer[4], adc_buffer, ADC_BUFFER_SIZE * 2);
  
  // Insere a duração exata medida pelo DWT (4 bytes) logo após os dados do ADC (512 bytes)
  memcpy(&tx_dma_buffer[4 + (ADC_BUFFER_SIZE * 2)], &elapsed_cycles, 4);

  // Limpa o D-Cache do buffer de transmissão (544 bytes para cobrir toda a linha de cache de 32 bytes)
  SCB_CleanDCache_by_Addr((uint32_t*)tx_dma_buffer, 544);

  // Aguarda qualquer transmissão anterior via DMA terminar
  while (huart3.gState != HAL_UART_STATE_READY);
  HAL_UART_Transmit_DMA(&huart3, tx_dma_buffer, (ADC_BUFFER_SIZE * 2) + 8);
}

void ExecutarEnsaioRL_ETS(void) {
  // 1. Para o DMA temporariamente
  HAL_ADC_Stop_DMA(&hadc1);
  
  // 2. Reconfigura o ADC para modo Single (não contínuo) por Software
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
  HAL_ADC_Init(&hadc1);
  
  // 3. Modifica temporariamente o pino PA0 de Alternate Function (TIM2_CH1) para GPIO Output
  // Registrador MODER do GPIOA: bits 0 e 1 definem o modo do pino PA0.
  // Limpa os bits (3UL << 0) e escreve (1UL << 0) para configurar como Output (01).
  GPIOA->MODER = (GPIOA->MODER & ~(3UL << 0)) | (1UL << 0);
  
  // 4. Loop de amostragem em tempo equivalente (ETS)
  for (int step = 0; step < ADC_BUFFER_SIZE; step++) {
    // Garante pino em 0V para descarga da bobina
    HAL_GPIO_WritePin(EXCITACAO_PIN_GPIO_Port, EXCITACAO_PIN_Pin, GPIO_PIN_RESET);
    // Atraso de 100 µs (48.000 ciclos de clock a 480 MHz)
    // Garante descarga total
    DelayCycles(48000);
    
    // Dispara o pulso de excitação
    HAL_GPIO_WritePin(EXCITACAO_PIN_GPIO_Port, EXCITACAO_PIN_Pin, GPIO_PIN_SET);
    
    // Atraso incremental estável e preciso usando o Cycle Counter (DWT CYCCNT)
    // No clock de 480 MHz, cada ciclo equivale a ~2.08 ns.
    // Usando passos de 12 ciclos (~25 ns por passo) para atingir 40 MSPS equivalentes
    DelayCycles(step * 12);
    
    // Dispara e lê a conversão única
    HAL_ADC_Start(&hadc1);
    HAL_ADC_PollForConversion(&hadc1, 10);
    adc_buffer[step] = HAL_ADC_GetValue(&hadc1);
  }
  
  // 5. Retorna o pino a 0V e restaura PA0 para Alternate Function (TIM2_CH1) para o modo DMA
  HAL_GPIO_WritePin(EXCITACAO_PIN_GPIO_Port, EXCITACAO_PIN_Pin, GPIO_PIN_RESET);
  
  // Configura PA0 de volta como Alternate Function (10 binário = 2UL << 0)
  GPIOA->MODER = (GPIOA->MODER & ~(3UL << 0)) | (2UL << 0);
  
  // 6. Restaura o ADC para o modo contínuo DMA padrão
  hadc1.Init.ContinuousConvMode = ENABLE;
  hadc1.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DMA_ONESHOT;
  HAL_ADC_Init(&hadc1);
  
  // 7. Transmite os dados em Binário via DMA com cabeçalho de sincronização
  tx_dma_buffer[0] = 0xAA;
  tx_dma_buffer[1] = 0x55;
  tx_dma_buffer[2] = 0xAA;
  tx_dma_buffer[3] = 0x55;
  memcpy(&tx_dma_buffer[4], adc_buffer, ADC_BUFFER_SIZE * 2);

  // No modo ETS, cada passo incrementa 12 ciclos do clock de 480 MHz (~25 ns por passo).
  // Enviamos o valor constante de 3072 ciclos (12 * 256) para que o cálculo do dt
  // na GUI resulte em exatamente 0.025 µs (40 MSPS equivalentes).
  uint32_t ets_cycles = 12 * ADC_BUFFER_SIZE;
  memcpy(&tx_dma_buffer[4 + (ADC_BUFFER_SIZE * 2)], &ets_cycles, 4);

  // Limpa o D-Cache do buffer de transmissão
  SCB_CleanDCache_by_Addr((uint32_t*)tx_dma_buffer, 544);

  // Aguarda qualquer transmissão anterior via DMA terminar
  while (huart3.gState != HAL_UART_STATE_READY);
  HAL_UART_Transmit_DMA(&huart3, tx_dma_buffer, (ADC_BUFFER_SIZE * 2) + 8);
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* Enable the CPU Cache */

  /* Enable I-Cache---------------------------------------------------------*/
  SCB_EnableICache();

  /* Enable D-Cache---------------------------------------------------------*/
  SCB_EnableDCache();

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_ADC1_Init();
  MX_USART3_UART_Init();
  MX_TIM2_Init();
  MX_TIM3_Init();
  /* USER CODE BEGIN 2 */
  // Inicializa o contador de ciclos (DWT CYCCNT) para medição e delays com precisão de clock (2.08 ns)
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->LAR = 0xC5ACCE55; // Desbloqueia os registradores DWT no Cortex-M7
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk; // Habilita o contador de ciclos
  // Executa a Calibração de Offset do ADC1 (Essencial para máxima estabilidade e precisão)
  HAL_ADCEx_Calibration_Start(&hadc1, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED);
  
  // Inicia a recepção de comandos via interrupção (não-bloqueante)
  HAL_UART_Receive_IT(&huart3, &uart_rx_byte, 1);
  /* USER CODE END 2 */

  /* Initialize leds */
  BSP_LED_Init(LED_GREEN);
  BSP_LED_Init(LED_BLUE);
  BSP_LED_Init(LED_RED);

  /* Initialize USER push-button, will be used to trigger an interrupt each time it's pressed.*/
  BSP_PB_Init(BUTTON_USER, BUTTON_MODE_EXTI);

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  uint32_t last_trigger_tick = 0;
  
  while (1)
  {
    uint32_t current_tick = HAL_GetTick();
    
    // 1. Executa disparo único solicitado via UART (t) - de forma segura no thread principal
    if (single_trigger_requested) {
      single_trigger_requested = 0;
      
      BSP_LED_On(LED_RED);
      ExecutarEnsaioRL();
      BSP_LED_Off(LED_RED);
    }
    
    // 2. Executa disparo contínuo se ativado (r) no período configurado (f)
    if (ensaio_ativo && (current_tick - last_trigger_tick >= ensaio_period_ms)) {
      last_trigger_tick = current_tick;
      
      BSP_LED_On(LED_RED);
      ExecutarEnsaioRL();
      BSP_LED_Off(LED_RED);
    }
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Supply configuration update enable
  */
  HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);

  /** Configure the main internal regulator output voltage
  */
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE0);

  while(!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {}

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_DIV1;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 4;
  RCC_OscInitStruct.PLL.PLLN = 60;
  RCC_OscInitStruct.PLL.PLLP = 2;
  RCC_OscInitStruct.PLL.PLLQ = 4;
  RCC_OscInitStruct.PLL.PLLR = 2;
  RCC_OscInitStruct.PLL.PLLRGE = RCC_PLL1VCIRANGE_3;
  RCC_OscInitStruct.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
  RCC_OscInitStruct.PLL.PLLFRACN = 0;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2
                              |RCC_CLOCKTYPE_D3PCLK1|RCC_CLOCKTYPE_D1PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB3CLKDivider = RCC_APB3_DIV2;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV2;
  RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
