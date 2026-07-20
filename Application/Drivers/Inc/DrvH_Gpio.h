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



#ifdef __cplusplus
}
#endif

#endif /* DRVH_GPIO_H */
