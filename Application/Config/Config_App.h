/**
 * @file Config_App.h
 * @brief Configuration file for the application, including pin mapping, constant limits, and utilities.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef CONFIG_APP_H
#define CONFIG_APP_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"
#include <stdbool.h>

/* Firmware version */
#define FW_VERSION "1.0.0"

/* Pin mapping */
#define EXCITACAO_PIN_Pin GPIO_PIN_0
#define EXCITACAO_PIN_GPIO_Port GPIOA

/* Buffer settings */
#define ADC_BUFFER_SIZE 256U
#define TX_DMA_BUFFER_SIZE 544U

/* Protocol constants */
#define HEADER_BYTE_1 0xAAU
#define HEADER_BYTE_2 0x55U
#define HEADER_SIZE 4U
#define ELAPSED_CYCLES_SIZE 4U
#define ADC_DATA_SIZE (ADC_BUFFER_SIZE * 2U)
#define TX_DMA_TRANSMIT_SIZE (HEADER_SIZE + ADC_DATA_SIZE + ELAPSED_CYCLES_SIZE)

/* Verification limits */
#define MIN_ENSAIO_PERIOD_MS 5U
#define MAX_ENSAIO_PERIOD_MS 250U
#define MIN_ENSAIO_DT_NS 100U
#define MAX_ENSAIO_DT_NS 10000U
#define DEFAULT_ENSAIO_PERIOD_MS 33U
#define DEFAULT_ENSAIO_DT_NS 218U

/* Timers and Cycles */
#define TIM3_CLOCK_HZ 240000000UL
#define TIMING_COIL_DISCHARGE_CYCLES 48000UL
#define ETS_STEP_CYCLES 12UL
#define ADC_POLL_TIMEOUT_MS 10UL
#define TRIAL_TIMEOUT_MS 100UL

#define DWT_LAR_UNLOCK_KEY 0xC5ACCE55UL

/**
 * @brief  Delays the CPU for a specified number of clock cycles using DWT CYCCNT.
 * @param[in]  ui32Cycles  Number of cycles to delay (0 to 4294967295).
 * @return None
 */
static inline void vConfigAppDelayCycles(uint32_t ui32Cycles)
{
  uint32_t ui32Start = DWT->CYCCNT;
  while ((DWT->CYCCNT - ui32Start) < ui32Cycles);
}

#ifdef __cplusplus
}
#endif

#endif /* CONFIG_APP_H */
