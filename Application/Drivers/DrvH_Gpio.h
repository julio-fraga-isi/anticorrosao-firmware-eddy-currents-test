/**
 * @file DrvH_Gpio.h
 * @brief High-level driver abstraction for GPIO configuration and control.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef DRVH_GPIO_H
#define DRVH_GPIO_H

#ifdef __cplusplus
extern "C" {
#endif

#include "Config_App.h"

/**
 * @brief  Initializes GPIO Ports Clocks.
 * @return None
 */
void vDrvH_GpioInit(void);

/**
 * @brief  Writes the logic level to the excitation pin.
 * @param[in]  bLevel  Level to write (true = High, false = Low).
 * @return None
 */
void vDrvH_GpioSetExcitacaoPin(bool bLevel);

/**
 * @brief  Configures the excitation pin (PA0) as general-purpose output (GPIO mode).
 * @return None
 */
void vDrvH_GpioSetPinModeOutput(void);

/**
 * @brief  Configures the excitation pin (PA0) as Alternate Function (TIM2 PWM mode).
 * @return None
 */
void vDrvH_GpioSetPinModeAlternate(void);

#ifdef __cplusplus
}
#endif

#endif /* DRVH_GPIO_H */
