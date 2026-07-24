/**
 * @file DrvH_Tim.h
 * @brief High-level driver abstraction for TIM2 (excitation) and TIM3 (trigger metronome) peripherals.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef DRVH_TIM_H
#define DRVH_TIM_H

#ifdef __cplusplus
extern "C" {
#endif

#include "Config_App.h"

/**
 * @brief  Initializes the TIM2 instance in One-Pulse PWM mode.
 * @return None
 */
void vDrvH_Tim2Init(void);

/**
 * @brief  Initializes the TIM3 instance in Slave Trigger mode.
 * @return None
 */
void vDrvH_Tim3Init(void);

/**
 * @brief  Starts the TIM2 PWM generation on Channel 1.
 * @return None
 */
void vDrvH_Tim2StartPwm(void);

/**
 * @brief  Disables the TIM2 counter.
 * @return None
 */
void vDrvH_Tim2Disable(void);

/**
 * @brief  Sets the TIM2 counter value.
 * @param[in]  ui32Counter  Counter value.
 * @return None
 */
void vDrvH_Tim2SetCounter(uint32_t ui32Counter);

/**
 * @brief  Enables the TIM3 counter.
 * @return None
 */
void vDrvH_Tim3Enable(void);

/**
 * @brief  Disables the TIM3 counter.
 * @return None
 */
void vDrvH_Tim3Disable(void);

/**
 * @brief  Sets the TIM3 counter value.
 * @param[in]  ui32Counter  Counter value.
 * @return None
 */
void vDrvH_Tim3SetCounter(uint32_t ui32Counter);

/**
 * @brief  Sets the TIM3 Auto-Reload (ARR) register to control the trigger period.
 * @param[in]  ui32PeriodTicks  Auto-reload register value (period - 1).
 * @return None
 */
void vDrvH_Tim3SetPeriod(uint32_t ui32PeriodTicks);

/**
 * @brief  Gets a pointer to the internal TIM2 handle.
 * @return Pointer to TIM_HandleTypeDef structure.
 */
TIM_HandleTypeDef* pxDrvH_Tim2GetHandle(void);

/**
 * @brief  Gets a pointer to the internal TIM3 handle.
 * @return Pointer to TIM_HandleTypeDef structure.
 */
TIM_HandleTypeDef* pxDrvH_Tim3GetHandle(void);

#ifdef __cplusplus
}
#endif

#endif /* DRVH_TIM_H */
