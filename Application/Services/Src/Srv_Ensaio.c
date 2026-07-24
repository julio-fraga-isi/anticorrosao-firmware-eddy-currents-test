/**
 * @file Srv_Ensaio.c
 * @brief Service layer for trial (ensaio) execution, parsing, and callback handlers.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "Srv_Ensaio.h"
#include <string.h>

/* Private variables (static for encapsulation) */
static uint16_t ui16AdcBuffer[ADC_BUFFER_SIZE] __attribute__((aligned(32)));
static uint8_t ui8TxDmaBuffer[TX_DMA_BUFFER_SIZE] __attribute__((aligned(32)));

static volatile uint8_t ui8EnsaioPeriodMs = DEFAULT_ENSAIO_PERIOD_MS;
static volatile bool bEnsaioAtivo = false;
static volatile bool bSingleTriggerRequested = false;
static volatile uint16_t ui16EnsaioDtNs = DEFAULT_ENSAIO_DT_NS;
static volatile bool bAdcConversionComplete = false;
static uint8_t ui8UartRxByte = 0;

/* Private helper function prototypes */
static void vSrv_EnsaioProcessStateZero(uint8_t *pui8RxState, uint8_t *pui8RxDtIdx);
static void vSrv_EnsaioProcessStateOne(uint8_t *pui8RxState);
static void vSrv_EnsaioProcessStateTwo(uint8_t *pui8RxState, uint8_t *pui8RxDtBytes, uint8_t *pui8RxDtIdx);
static uint16_t usSrv_EnsaioCalcularCRC16(const uint8_t *pui8Data, uint32_t ui32Length);

/**
 * @brief  Initializes the trial service variables and starts command reception.
 * @return None
 */
void vSrv_EnsaioInit(void)
{
  vDrvH_UartReceiveIt(&ui8UartRxByte, 1U);
}

/**
 * @brief  Executes a regular RL acquisition trial and transmits results.
 * @return None
 */
void vSrv_EnsaioRunRL(void)
{
  bAdcConversionComplete = false;
  
  /* 1. Delay for coil discharge (48,000 clock cycles at 480 MHz = 100 us) */
  vConfigAppDelayCycles(TIMING_COIL_DISCHARGE_CYCLES);

  /* 2. Invalidate D-Cache of the receive buffer before ADC DMA writes to it */
  SCB_InvalidateDCache_by_Addr((uint32_t*)ui16AdcBuffer, ADC_BUFFER_SIZE * 2U);
  
  /* Disable interrupts temporarily for precise sync */
  uint32_t ui32Primask = __get_PRIMASK();
  __disable_irq();

  /* 3. Start ADC via DMA (waits for hardware trigger from TIM3) */
  vDrvH_AdcStartDma(ui16AdcBuffer, ADC_BUFFER_SIZE);

  /* Ensure TIM3 counter starts at 0 */
  vDrvH_Tim3SetCounter(0U);

  /* Force immediate TIM2 register update and emit TRGO update to start TIM3 */
  TIM_HandleTypeDef *pxTim2 = pxDrvH_Tim2GetHandle();
  vDrvH_Tim2SetCounter(0U);
  pxTim2->Instance->EGR = TIM_EGR_UG;
  __HAL_TIM_CLEAR_FLAG(pxTim2, TIM_FLAG_UPDATE);
  
  /* Capture exact start cycle using DWT */
  uint32_t ui32StartCycles = DWT->CYCCNT;

  /* 4. Start TIM2 in One-Pulse PWM mode to generate physical 56 us excitation pulse */
  vDrvH_Tim2StartPwm();
  
  /* Restore interrupts */
  __set_PRIMASK(ui32Primask);
  
  /* 5. Wait for conversion complete callback with 100 ms timeout */
  uint32_t ui32StartTick = HAL_GetTick();
  while (!bAdcConversionComplete && (HAL_GetTick() - ui32StartTick < TRIAL_TIMEOUT_MS))
  {
    /* Spin until conversion completes in ISR */
  }
  
  /* Capture exact end cycle */
  uint32_t ui32EndCycles = DWT->CYCCNT;
  uint32_t ui32ElapsedCycles = ui32EndCycles - ui32StartCycles;

  /* 6. Safely stop and disable timers and ADC */
  vDrvH_AdcStopDma();
  
  vDrvH_Tim3Disable();
  vDrvH_Tim3SetCounter(0U);
  
  vDrvH_Tim2Disable();
  vDrvH_Tim2SetCounter(100U);
  
  if (!bAdcConversionComplete)
  {
    memset(ui16AdcBuffer, 0, sizeof(ui16AdcBuffer));
    ui32ElapsedCycles = 0U;
  }
  else
  {
    /* Invalidate D-Cache again so the CPU reads modified values */
    SCB_InvalidateDCache_by_Addr((uint32_t*)ui16AdcBuffer, ADC_BUFFER_SIZE * 2U);
  }

  /* 7. Transmit binary packet: header + data + elapsed cycles + CRC16 */
  ui8TxDmaBuffer[0] = HEADER_BYTE_1;
  ui8TxDmaBuffer[1] = HEADER_BYTE_2;
  ui8TxDmaBuffer[2] = HEADER_BYTE_1;
  ui8TxDmaBuffer[3] = HEADER_BYTE_2;
  memcpy(&ui8TxDmaBuffer[4], ui16AdcBuffer, ADC_BUFFER_SIZE * 2U);
  memcpy(&ui8TxDmaBuffer[4 + (ADC_BUFFER_SIZE * 2U)], &ui32ElapsedCycles, 4U);

  /* Calculate CRC-16 on payload (512 bytes data + 4 bytes cycles = 516 bytes) */
  uint16_t ui16Crc = usSrv_EnsaioCalcularCRC16(&ui8TxDmaBuffer[4], ADC_BUFFER_SIZE * 2U + 4U);
  memcpy(&ui8TxDmaBuffer[4 + (ADC_BUFFER_SIZE * 2U) + 4U], &ui16Crc, 2U);

  /* Clean D-Cache for DMA transmission (aligned to 32 bytes) */
  SCB_CleanDCache_by_Addr((uint32_t*)ui8TxDmaBuffer, TX_DMA_BUFFER_SIZE);

  /* Wait for previous transmit to complete */
  while (!bDrvH_UartIsReadyToTransmit())
  {
    /* Spin wait */
  }
  vDrvH_UartTransmitDma(ui8TxDmaBuffer, TX_DMA_TRANSMIT_SIZE);
}



/**
 * @brief  Checks if continuous trials are active.
 * @return true if active, false otherwise.
 */
bool bSrv_EnsaioIsActive(void)
{
  return bEnsaioAtivo;
}

/**
 * @brief  Checks if a single trial trigger has been requested.
 * @return true if requested, false otherwise.
 */
bool bSrv_EnsaioIsSingleRequested(void)
{
  return bSingleTriggerRequested;
}

/**
 * @brief  Clears the single trial trigger request flag.
 * @return None
 */
void vSrv_EnsaioClearSingleRequest(void)
{
  bSingleTriggerRequested = false;
}

/**
 * @brief  Gets the continuous trials period in milliseconds.
 * @return Period in milliseconds.
 */
uint8_t ui8Srv_EnsaioGetPeriodMs(void)
{
  return ui8EnsaioPeriodMs;
}

/**
 * @brief  Callback triggered by ADC conversion complete interrupt.
 * @param[in]  pxHadc  Pointer to the ADC handle structure.
 * @return None
 */
void vSrv_EnsaioAdcConvCpltCallback(ADC_HandleTypeDef* pxHadc)
{
  if (pxHadc->Instance == ADC1)
  {
    bAdcConversionComplete = true;
    vDrvH_AdcStopDma();
    
    /* Disable metronome timer (TIM3) */
    vDrvH_Tim3Disable();
    vDrvH_Tim3SetCounter(0U);
  }
}

/**
 * @brief  Callback triggered by UART receive complete interrupt.
 * @param[in]  pxHuart  Pointer to the UART handle structure.
 * @return None
 */
void vSrv_EnsaioUartRxCpltCallback(UART_HandleTypeDef *pxHuart)
{
  if (pxHuart->Instance == USART3)
  {
    static uint8_t ui8RxState = 0;
    static uint8_t ui8RxDtBytes[2] = {0};
    static uint8_t ui8RxDtIdx = 0;
    static uint32_t ui32LastByteTick = 0U;
    uint32_t ui32CurrentTick = HAL_GetTick();

    /* Reset state machine if packet timeout (100ms) occurs between bytes */
    if (ui8RxState != 0U && (ui32CurrentTick - ui32LastByteTick > 100U))
    {
      ui8RxState = 0U;
      ui8RxDtIdx = 0U;
    }
    ui32LastByteTick = ui32CurrentTick;
    
    if (ui8RxState == 0U)
    {
      vSrv_EnsaioProcessStateZero(&ui8RxState, &ui8RxDtIdx);
    }
    else if (ui8RxState == 1U)
    {
      vSrv_EnsaioProcessStateOne(&ui8RxState);
    }
    else if (ui8RxState == 2U)
    {
      vSrv_EnsaioProcessStateTwo(&ui8RxState, ui8RxDtBytes, &ui8RxDtIdx);
    }
    else
    {
      ui8RxState = 0U;
    }
    
    vDrvH_UartReceiveIt(&ui8UartRxByte, 1U);
  }
}

/* Helper functions for the UART state machine (keep nesting level <= 3) */

static void vSrv_EnsaioProcessStateZero(uint8_t *pui8RxState, uint8_t *pui8RxDtIdx)
{
  if (ui8UartRxByte == 'f')
  {
    *pui8RxState = 1U;
  }
  else if (ui8UartRxByte == 'p')
  {
    bEnsaioAtivo = false;
  }
  else if (ui8UartRxByte == 'r')
  {
    bEnsaioAtivo = true;
  }
  else if (ui8UartRxByte == 't')
  {
    bSingleTriggerRequested = true;
  }
  else if (ui8UartRxByte == 'd')
  {
    *pui8RxState = 2U;
    *pui8RxDtIdx = 0U;
  }
}

static void vSrv_EnsaioProcessStateOne(uint8_t *pui8RxState)
{
  uint8_t ui8RxPeriod = ui8UartRxByte;
  
  if ((ui8RxPeriod >= MIN_ENSAIO_PERIOD_MS) && (ui8RxPeriod <= MAX_ENSAIO_PERIOD_MS))
  {
    ui8EnsaioPeriodMs = ui8RxPeriod;
  }
  *pui8RxState = 0U;
}

static void vSrv_EnsaioProcessStateTwo(uint8_t *pui8RxState, uint8_t *pui8RxDtBytes, uint8_t *pui8RxDtIdx)
{
  pui8RxDtBytes[*pui8RxDtIdx] = ui8UartRxByte;
  (*pui8RxDtIdx)++;
  
  if (*pui8RxDtIdx >= 2U)
  {
    uint16_t ui16NovoDt = (uint16_t)(pui8RxDtBytes[0] | ((uint16_t)pui8RxDtBytes[1] << 8));
    
    if ((ui16NovoDt >= MIN_ENSAIO_DT_NS) && (ui16NovoDt <= MAX_ENSAIO_DT_NS))
    {
      ui16EnsaioDtNs = ui16NovoDt;
      /* TIM3 runs at 240 MHz, ticks = dt_ns * 240 / 1000 */
      uint32_t ui32TimerTicks = ((uint32_t)ui16EnsaioDtNs * 240U) / 1000U;
      
      if (ui32TimerTicks > 0U)
      {
        vDrvH_Tim3SetPeriod(ui32TimerTicks - 1U);
      }
      else
      {
        vDrvH_Tim3SetPeriod(0U);
      }
    }
    *pui8RxState = 0U;
  }
}

static uint16_t usSrv_EnsaioCalcularCRC16(const uint8_t *pui8Data, uint32_t ui32Length)
{
  uint16_t ui16Crc = 0xFFFFU;
  for (uint32_t ui32I = 0U; ui32I < ui32Length; ui32I++)
  {
    ui16Crc ^= (uint16_t)pui8Data[ui32I] << 8U;
    for (uint32_t ui32Bit = 0U; ui32Bit < 8U; ui32Bit++)
    {
      if ((ui16Crc & 0x8000U) != 0U)
      {
        ui16Crc = (ui16Crc << 1U) ^ 0x1021U;
      }
      else
      {
        ui16Crc <<= 1U;
      }
    }
  }
  return ui16Crc;
}

/* Weak overrides connecting HAL interrupts directly to the Service Layer */

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef* hadc)
{
  vSrv_EnsaioAdcConvCpltCallback(hadc);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  vSrv_EnsaioUartRxCpltCallback(huart);
}
