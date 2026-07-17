/**
 * @file App_Anticorrosao.c
 * @brief Application layer logic for the Anticorrosao device.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "App_Anticorrosao.h"

/**
 * @brief  State machine enum for the application.
 */
typedef enum
{
  APP_ANTICORROSAO_STATE_INIT = 0,         /**< Initialize application services and parameters */
  APP_ANTICORROSAO_STATE_IDLE,             /**< Waiting for triggers or mode changes */
  APP_ANTICORROSAO_STATE_RUN_RL_SINGLE,    /**< Executing a single RL acquisition */
  APP_ANTICORROSAO_STATE_RUN_RL_CONTINUOUS /**< Executing periodic RL acquisitions */
} App_Anticorrosao_State_t;

/**
 * @brief  State machine event enum for the application.
 */
typedef enum
{
  APP_ANTICORROSAO_EVENT_NONE = 0,               /**< No event detected */
  APP_ANTICORROSAO_EVENT_INIT_DONE,              /**< Initialization phase finished */
  APP_ANTICORROSAO_EVENT_SINGLE_REQUESTED,       /**< Single RL test request received */
  APP_ANTICORROSAO_EVENT_CONTINUOUS_ACTIVE,      /**< Continuous mode active, wait for tick */
  APP_ANTICORROSAO_EVENT_CONTINUOUS_DEACTIVATED, /**< Continuous mode disabled */
  APP_ANTICORROSAO_EVENT_TICK_TIMEOUT            /**< Periodic tick timer expired */
} App_Anticorrosao_Event_t;

/* Private state variable, initialized to INIT */
static App_Anticorrosao_State_t pxAppState = APP_ANTICORROSAO_STATE_INIT;

/* Private function prototype for event detection */
static App_Anticorrosao_Event_t pxApp_AnticorrosaoDetectEvent(uint32_t ui32CurrentTick, uint32_t ui32LastTriggerTick);

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
}

/**
 * @brief  Main application task executed inside the infinite loop.
 * @return None
 */
void vApp_AnticorrosaoTask(void)
{
  static uint32_t ui32LastTriggerTick = 0U;
  uint32_t ui32CurrentTick = HAL_GetTick();

  /* Detect active event */
  App_Anticorrosao_Event_t pxEvent = pxApp_AnticorrosaoDetectEvent(ui32CurrentTick, ui32LastTriggerTick);

  switch (pxAppState)
  {
    case APP_ANTICORROSAO_STATE_INIT:
      if (pxEvent == APP_ANTICORROSAO_EVENT_INIT_DONE)
      {
        /* Initialize Trial Service */
        vSrv_EnsaioInit();

        /* Transition to IDLE state */
        pxAppState = APP_ANTICORROSAO_STATE_IDLE;
      }
      break;

    case APP_ANTICORROSAO_STATE_IDLE:
      if (pxEvent == APP_ANTICORROSAO_EVENT_SINGLE_REQUESTED)
      {
        pxAppState = APP_ANTICORROSAO_STATE_RUN_RL_SINGLE;
      }
      else if (pxEvent == APP_ANTICORROSAO_EVENT_CONTINUOUS_ACTIVE || pxEvent == APP_ANTICORROSAO_EVENT_TICK_TIMEOUT)
      {
        /* Force immediate execution of the first periodic trial */
        ui32LastTriggerTick = ui32CurrentTick - ui8Srv_EnsaioGetPeriodMs();
        pxAppState = APP_ANTICORROSAO_STATE_RUN_RL_CONTINUOUS;
      }
      else
      {
        /* Keep in IDLE state */
      }
      break;

    case APP_ANTICORROSAO_STATE_RUN_RL_SINGLE:
      /* Clear the trigger request */
      vSrv_EnsaioClearSingleRequest();

      /* Execute RL trial with LED indication */
      BSP_LED_On(LED_RED);
      vSrv_EnsaioRunRL();
      BSP_LED_Off(LED_RED);

      /* Transition back to IDLE */
      pxAppState = APP_ANTICORROSAO_STATE_IDLE;
      break;

    case APP_ANTICORROSAO_STATE_RUN_RL_CONTINUOUS:
      if (pxEvent == APP_ANTICORROSAO_EVENT_CONTINUOUS_DEACTIVATED)
      {
        pxAppState = APP_ANTICORROSAO_STATE_IDLE;
      }
      else if (pxEvent == APP_ANTICORROSAO_EVENT_TICK_TIMEOUT)
      {
        ui32LastTriggerTick = ui32CurrentTick;

        BSP_LED_On(LED_RED);
        vSrv_EnsaioRunRL();
        BSP_LED_Off(LED_RED);
      }
      else
      {
        /* Wait for periodic tick */
      }
      break;

    default:
      /* Recovery path for invalid states */
      pxAppState = APP_ANTICORROSAO_STATE_IDLE;
      break;
  }
}

/**
 * @brief  Helper function to detect events based on the system state.
 * @param[in]  ui32CurrentTick      Current system tick count.
 * @param[in]  ui32LastTriggerTick  Last system tick count when a test was triggered.
 * @return Detected event.
 */
static App_Anticorrosao_Event_t pxApp_AnticorrosaoDetectEvent(uint32_t ui32CurrentTick, uint32_t ui32LastTriggerTick)
{
  App_Anticorrosao_Event_t pxDetectedEvent = APP_ANTICORROSAO_EVENT_NONE;

  if (pxAppState == APP_ANTICORROSAO_STATE_INIT)
  {
    pxDetectedEvent = APP_ANTICORROSAO_EVENT_INIT_DONE;
  }
  else if (bSrv_EnsaioIsSingleRequested())
  {
    pxDetectedEvent = APP_ANTICORROSAO_EVENT_SINGLE_REQUESTED;
  }
  else if (bSrv_EnsaioIsActive())
  {
    if (ui32CurrentTick - ui32LastTriggerTick >= ui8Srv_EnsaioGetPeriodMs())
    {
      pxDetectedEvent = APP_ANTICORROSAO_EVENT_TICK_TIMEOUT;
    }
    else
    {
      pxDetectedEvent = APP_ANTICORROSAO_EVENT_CONTINUOUS_ACTIVE;
    }
  }
  else
  {
    if (pxAppState == APP_ANTICORROSAO_STATE_RUN_RL_CONTINUOUS)
    {
      pxDetectedEvent = APP_ANTICORROSAO_EVENT_CONTINUOUS_DEACTIVATED;
    }
  }

  return pxDetectedEvent;
}
