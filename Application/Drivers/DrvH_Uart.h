/**
 * @file DrvH_Uart.h
 * @brief High-level driver abstraction for USART3 peripheral.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef DRVH_UART_H
#define DRVH_UART_H

#ifdef __cplusplus
extern "C" {
#endif

#include "Config_App.h"

/**
 * @brief  Initializes the USART3 instance.
 * @return None
 */
void vDrvH_UartInit(void);

/**
 * @brief  Transmits a buffer using DMA.
 * @param[in]  pui8Data  Pointer to the source buffer (aligned to 32 bytes).
 * @param[in]  ui16Size  Number of bytes to transmit.
 * @return None
 */
void vDrvH_UartTransmitDma(uint8_t *pui8Data, uint16_t ui16Size);

/**
 * @brief  Starts receiving bytes via UART interrupts.
 * @param[in]  pui8Byte  Pointer to the destination byte variable.
 * @param[in]  ui16Size  Number of bytes to receive (usually 1).
 * @return None
 */
void vDrvH_UartReceiveIt(uint8_t *pui8Byte, uint16_t ui16Size);

/**
 * @brief  Checks if the UART instance is ready to transmit new data.
 * @return true if ready, false if busy.
 */
bool bDrvH_UartIsReadyToTransmit(void);

/**
 * @brief  Gets a pointer to the internal UART handle.
 * @return Pointer to UART_HandleTypeDef structure.
 */
UART_HandleTypeDef* pxDrvH_UartGetHandle(void);

/**
 * @brief  Gets a pointer to the internal DMA handle associated with the UART TX.
 * @return Pointer to DMA_HandleTypeDef structure.
 */
DMA_HandleTypeDef* pxDrvH_UartGetDmaHandle(void);

#ifdef __cplusplus
}
#endif

#endif /* DRVH_UART_H */
