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

/**
 * @brief  Writes the logic level to the excitation pin.
 * @param[in]  bLevel  Level to write (true = High, false = Low).
 * @return None
 */
void vDrvH_GpioSetExcitacaoPin(bool bLevel)
{
  HAL_GPIO_WritePin(EXCITACAO_PIN_GPIO_Port, EXCITACAO_PIN_Pin, bLevel ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

/**
 * @brief  Configures the excitation pin (PA0) as general-purpose output (GPIO mode).
 * @return None
 */
void vDrvH_GpioSetPinModeOutput(void)
{
  /* MODER register of GPIOA: bits 0 and 1 represent PA0.
   * Clear bits (3UL << 0) and write (1UL << 0) to configure as Output (01).
   */
  GPIOA->MODER = (GPIOA->MODER & ~(3UL << 0)) | (1UL << 0);
}

/**
 * @brief  Configures the excitation pin (PA0) as Alternate Function (TIM2 PWM mode).
 * @return None
 */
void vDrvH_GpioSetPinModeAlternate(void)
{
  /* MODER register of GPIOA: bits 0 and 1 represent PA0.
   * Clear bits (3UL << 0) and write (2UL << 0) to configure as Alternate Function (10).
   */
  GPIOA->MODER = (GPIOA->MODER & ~(3UL << 0)) | (2UL << 0);
}
