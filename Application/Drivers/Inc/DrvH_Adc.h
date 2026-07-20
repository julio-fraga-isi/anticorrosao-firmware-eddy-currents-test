/**
 * @file DrvH_Adc.h
 * @brief High-level driver abstraction for ADC peripheral.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef DRVH_ADC_H
#define DRVH_ADC_H

#ifdef __cplusplus
extern "C" {
#endif

#include "Config_App.h"

/**
 * @brief  Initializes the ADC1 instance and its regular channel.
 * @return None
 */
void vDrvH_AdcInit(void);

/**
 * @brief  Starts the ADC conversion in DMA mode.
 * @param[in]  pui16Buffer  Pointer to the destination buffer (aligned to 32 bytes).
 * @param[in]  ui16Size     Number of conversions to perform.
 * @return None
 */
void vDrvH_AdcStartDma(uint16_t *pui16Buffer, uint16_t ui16Size);

/**
 * @brief  Stops the ADC conversion in DMA mode.
 * @return None
 */
void vDrvH_AdcStopDma(void);

/**
 * @brief  Sets the ADC Continuous Conversion Mode.
 * @param[in]  bEnable  true to enable, false to disable.
 * @return None
 */
void vDrvH_AdcSetContinuousMode(bool bEnable);

/**
 * @brief  Gets the last converted regular channel value.
 * @return The 16-bit converted value (0 to 65535).
 */
uint16_t ui16DrvH_AdcGetValue(void);

/**
 * @brief  Starts a single regular channel conversion by Software.
 * @return None
 */
void vDrvH_AdcStart(void);

/**
 * @brief  Polls the regular channel conversion until complete or timed out.
 * @param[in]  ui32TimeoutMs  Timeout duration in milliseconds.
 * @return HAL_StatusTypeDef (HAL_OK, HAL_ERROR, HAL_TIMEOUT, HAL_BUSY).
 */
HAL_StatusTypeDef pxDrvH_AdcPollForConversion(uint32_t ui32TimeoutMs);

/**
 * @brief  Starts the ADC calibration.
 * @return None
 */
void vDrvH_AdcStartCalibration(void);

/**
 * @brief  Gets a pointer to the internal ADC handle.
 * @return Pointer to ADC_HandleTypeDef structure.
 */
ADC_HandleTypeDef* pxDrvH_AdcGetHandle(void);

/**
 * @brief  Gets a pointer to the internal DMA handle associated with the ADC.
 * @return Pointer to DMA_HandleTypeDef structure.
 */
DMA_HandleTypeDef* pxDrvH_AdcGetDmaHandle(void);

#ifdef __cplusplus
}
#endif

#endif /* DRVH_ADC_H */
