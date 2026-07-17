/**
 * @file App_Anticorrosao.c
 * @brief Application layer logic for the Anticorrosao device.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "App_Anticorrosao.h"

/**
 * @brief  Initializes the application layer, including drivers, DWT, and services.
 * @return None
 */
void vApp_AnticorrosaoInit(void)
{
  /* 1. Initialize High-Level Drivers */
  vDrvH_GpioInit();
  vDrvH_DmaInit();
  vDrvH_AdcInit();
  vDrvH_UartInit();
  vDrvH_Tim2Init();
  vDrvH_Tim3Init();

  /* 2. Initialize cycle counter (DWT CYCCNT) for precise delay and timing measurements */
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->LAR = DWT_LAR_UNLOCK_KEY;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

  /* 3. Run ADC Calibration (crucial for stability and precision) */
  vDrvH_AdcStartCalibration();

  /* 4. Initialize Board BSP Peripherals (LEDs and user button) */
  BSP_LED_Init(LED_GREEN);
  BSP_LED_Init(LED_BLUE);
  BSP_LED_Init(LED_RED);
  BSP_PB_Init(BUTTON_USER, BUTTON_MODE_EXTI);

  /* 5. Initialize Trial Service */
  vSrv_EnsaioInit();
}

/**
 * @brief  Main application task executed inside the infinite loop.
 * @return None
 */
void vApp_AnticorrosaoTask(void)
{
  static uint32_t ui32LastTriggerTick = 0U;
  uint32_t ui32CurrentTick = HAL_GetTick();

  /* 1. Execute single trigger trial requested via UART command ('t') */
  if (bSrv_EnsaioIsSingleRequested())
  {
    vSrv_EnsaioClearSingleRequest();
    
    BSP_LED_On(LED_RED);
    vSrv_EnsaioRunRL();
    BSP_LED_Off(LED_RED);
  }

  /* 2. Execute continuous trial run at the configured sampling period */
  if (bSrv_EnsaioIsActive() && (ui32CurrentTick - ui32LastTriggerTick >= ui8Srv_EnsaioGetPeriodMs()))
  {
    ui32LastTriggerTick = ui32CurrentTick;
    
    BSP_LED_On(LED_RED);
    vSrv_EnsaioRunRL();
    BSP_LED_Off(LED_RED);
  }
}
