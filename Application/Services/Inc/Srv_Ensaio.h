/**
 * @file Srv_Ensaio.h
 * @brief Service layer for trial (ensaio) execution, parsing, and callback handlers.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef SRV_ENSAIO_H
#define SRV_ENSAIO_H

#ifdef __cplusplus
extern "C" {
#endif

#include "Config_App.h"
#include "DrvH_Adc.h"
#include "DrvH_Dma.h"
#include "DrvH_Gpio.h"
#include "DrvH_Tim.h"
#include "DrvH_Uart.h"

/**
 * @brief  Initializes the trial service variables and starts command reception.
 * @return None
 */
void vSrv_EnsaioInit(void);

/**
 * @brief  Executes a regular RL acquisition trial and transmits results.
 * @return None
 */
void vSrv_EnsaioRunRL(void);



/**
 * @brief  Checks if continuous trials are active.
 * @return true if active, false otherwise.
 */
bool bSrv_EnsaioIsActive(void);

/**
 * @brief  Checks if a single trial trigger has been requested.
 * @return true if requested, false otherwise.
 */
bool bSrv_EnsaioIsSingleRequested(void);

/**
 * @brief  Clears the single trial trigger request flag.
 * @return None
 */
void vSrv_EnsaioClearSingleRequest(void);

/**
 * @brief  Gets the continuous trials period in milliseconds.
 * @return Period in milliseconds.
 */
uint8_t ui8Srv_EnsaioGetPeriodMs(void);

/**
 * @brief  Callback triggered by ADC conversion complete interrupt.
 * @param[in]  pxHadc  Pointer to the ADC handle structure.
 * @return None
 */
void vSrv_EnsaioAdcConvCpltCallback(ADC_HandleTypeDef* pxHadc);

/**
 * @brief  Callback triggered by UART receive complete interrupt.
 * @param[in]  pxHuart  Pointer to the UART handle structure.
 * @return None
 */
void vSrv_EnsaioUartRxCpltCallback(UART_HandleTypeDef *pxHuart);

#ifdef __cplusplus
}
#endif

#endif /* SRV_ENSAIO_H */
