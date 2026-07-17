/**
 * @file DrvH_Adc.c
 * @brief High-level driver abstraction for ADC, wrapping CubeMX generated configuration and handles.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "DrvH_Adc.h"
#include "adc.h"

/* Extern references to CubeMX generated handles that are not exposed in its header */
extern DMA_HandleTypeDef hdma_adc1;

/**
 * @brief  Initializes the ADC1 instance by calling CubeMX generated configuration.
 * @return None
 */
void vDrvH_AdcInit(void)
{
  MX_ADC1_Init();
}

/**
 * @brief  Starts the ADC conversion in DMA mode.
 * @param[in]  pui16Buffer  Pointer to the destination buffer (aligned to 32 bytes).
 * @param[in]  ui16Size     Number of conversions to perform.
 * @return None
 */
void vDrvH_AdcStartDma(uint16_t *pui16Buffer, uint16_t ui16Size)
{
  HAL_ADC_Start_DMA(&hadc1, (uint32_t*)pui16Buffer, ui16Size);
}

/**
 * @brief  Stops the ADC conversion in DMA mode.
 * @return None
 */
void vDrvH_AdcStopDma(void)
{
  HAL_ADC_Stop_DMA(&hadc1);
}

/**
 * @brief  Sets the ADC Continuous Conversion Mode.
 * @param[in]  bEnable  true to enable, false to disable.
 * @return None
 */
void vDrvH_AdcSetContinuousMode(bool bEnable)
{
  hadc1.Init.ContinuousConvMode = bEnable ? ENABLE : DISABLE;
  hadc1.Init.ConversionDataManagement = bEnable ? ADC_CONVERSIONDATA_DMA_ONESHOT : ADC_CONVERSIONDATA_DR;
  HAL_ADC_Init(&hadc1);
}

/**
 * @brief  Gets the last converted regular channel value.
 * @return The 16-bit converted value (0 to 65535).
 */
uint16_t ui16DrvH_AdcGetValue(void)
{
  return (uint16_t)HAL_ADC_GetValue(&hadc1);
}

/**
 * @brief  Starts a single regular channel conversion by Software.
 * @return None
 */
void vDrvH_AdcStart(void)
{
  HAL_ADC_Start(&hadc1);
}

/**
 * @brief  Polls the regular channel conversion until complete or timed out.
 * @param[in]  ui32TimeoutMs  Timeout duration in milliseconds.
 * @return HAL_StatusTypeDef (HAL_OK, HAL_ERROR, HAL_TIMEOUT, HAL_BUSY).
 */
HAL_StatusTypeDef pxDrvH_AdcPollForConversion(uint32_t ui32TimeoutMs)
{
  return HAL_ADC_PollForConversion(&hadc1, ui32TimeoutMs);
}

/**
 * @brief  Starts the ADC calibration.
 * @return None
 */
void vDrvH_AdcStartCalibration(void)
{
  HAL_ADCEx_Calibration_Start(&hadc1, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED);
}

/**
 * @brief  Gets a pointer to the internal ADC handle.
 * @return Pointer to ADC_HandleTypeDef structure.
 */
ADC_HandleTypeDef* pxDrvH_AdcGetHandle(void)
{
  return &hadc1;
}

/**
 * @brief  Gets a pointer to the internal DMA handle associated with the ADC.
 * @return Pointer to DMA_HandleTypeDef structure.
 */
DMA_HandleTypeDef* pxDrvH_AdcGetDmaHandle(void)
{
  return &hdma_adc1;
}
