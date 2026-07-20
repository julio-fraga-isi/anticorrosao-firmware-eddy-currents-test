/**
 * @file DrvH_Gpio.c
 * @brief High-level driver abstraction for GPIO, calling CubeMX generated initialization.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "DrvH_Gpio.h"
#include "gpio.h"

/**
 * @brief  Initializes GPIO Ports Clocks and Pins by calling CubeMX generated config.
 * @return None
 */
void vDrvH_GpioInit(void)
{
  MX_GPIO_Init();
}


