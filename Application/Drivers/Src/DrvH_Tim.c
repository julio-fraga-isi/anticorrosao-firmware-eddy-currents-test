/**
 * @file DrvH_Tim.c
 * @brief High-level driver abstraction for TIM2 and TIM3, wrapping CubeMX generated configuration and handles.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "DrvH_Tim.h"
#include "tim.h"

/**
 * @brief  Initializes the TIM2 instance by calling CubeMX generated configuration.
 * @return None
 */
void vDrvH_Tim2Init(void)
{
  MX_TIM2_Init();
}

/**
 * @brief  Initializes the TIM3 instance by calling CubeMX generated configuration.
 * @return None
 */
void vDrvH_Tim3Init(void)
{
  MX_TIM3_Init();
}

/**
 * @brief  Starts the TIM2 PWM generation on Channel 1.
 * @return None
 */
void vDrvH_Tim2StartPwm(void)
{
  HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1);
}

/**
 * @brief  Disables the TIM2 counter.
 * @return None
 */
void vDrvH_Tim2Disable(void)
{
  __HAL_TIM_DISABLE(&htim2);
}

/**
 * @brief  Sets the TIM2 counter value.
 * @param[in]  ui32Counter  Counter value.
 * @return None
 */
void vDrvH_Tim2SetCounter(uint32_t ui32Counter)
{
  __HAL_TIM_SET_COUNTER(&htim2, ui32Counter);
}

/**
 * @brief  Enables the TIM3 counter.
 * @return None
 */
void vDrvH_Tim3Enable(void)
{
  __HAL_TIM_ENABLE(&htim3);
}

/**
 * @brief  Disables the TIM3 counter.
 * @return None
 */
void vDrvH_Tim3Disable(void)
{
  __HAL_TIM_DISABLE(&htim3);
}

/**
 * @brief  Sets the TIM3 counter value.
 * @param[in]  ui32Counter  Counter value.
 * @return None
 */
void vDrvH_Tim3SetCounter(uint32_t ui32Counter)
{
  __HAL_TIM_SET_COUNTER(&htim3, ui32Counter);
}

/**
 * @brief  Sets the TIM3 Auto-Reload (ARR) register to control the trigger period.
 * @param[in]  ui32PeriodTicks  Auto-reload register value (period - 1).
 * @return None
 */
void vDrvH_Tim3SetPeriod(uint32_t ui32PeriodTicks)
{
  htim3.Instance->ARR = ui32PeriodTicks;
}

/**
 * @brief  Gets a pointer to the internal TIM2 handle.
 * @return Pointer to TIM_HandleTypeDef structure.
 */
TIM_HandleTypeDef* pxDrvH_Tim2GetHandle(void)
{
  return &htim2;
}

/**
 * @brief  Gets a pointer to the internal TIM3 handle.
 * @return Pointer to TIM_HandleTypeDef structure.
 */
TIM_HandleTypeDef* pxDrvH_Tim3GetHandle(void)
{
  return &htim3;
}
