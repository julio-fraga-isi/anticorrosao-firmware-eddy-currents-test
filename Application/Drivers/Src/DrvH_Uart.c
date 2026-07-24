/**
 * @file DrvH_Uart.c
 * @brief High-level driver abstraction for UART, wrapping CubeMX generated configuration and handles.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "DrvH_Uart.h"
#include "usart.h"

/* Extern references to CubeMX generated handles that are not exposed in its header */
extern DMA_HandleTypeDef hdma_usart3_tx;

/**
 * @brief  Initializes the USART3 instance by calling CubeMX generated configuration.
 * @return None
 */
void vDrvH_UartInit(void)
{
  MX_USART3_UART_Init();
}

/**
 * @brief  Transmits a buffer using DMA.
 * @param[in]  pui8Data  Pointer to the source buffer (aligned to 32 bytes).
 * @param[in]  ui16Size  Number of bytes to transmit.
 * @return None
 */
void vDrvH_UartTransmitDma(uint8_t *pui8Data, uint16_t ui16Size)
{
  HAL_UART_Transmit_DMA(&huart3, pui8Data, ui16Size);
}

/**
 * @brief  Starts receiving bytes via UART interrupts.
 * @param[in]  pui8Byte  Pointer to the destination byte variable.
 * @param[in]  ui16Size  Number of bytes to receive (usually 1).
 * @return None
 */
void vDrvH_UartReceiveIt(uint8_t *pui8Byte, uint16_t ui16Size)
{
  HAL_UART_Receive_IT(&huart3, pui8Byte, ui16Size);
}

/**
 * @brief  Checks if the UART instance is ready to transmit new data.
 * @return true if ready, false if busy.
 */
bool bDrvH_UartIsReadyToTransmit(void)
{
  return (huart3.gState == HAL_UART_STATE_READY);
}

/**
 * @brief  Gets a pointer to the internal UART handle.
 * @return Pointer to UART_HandleTypeDef structure.
 */
UART_HandleTypeDef* pxDrvH_UartGetHandle(void)
{
  return &huart3;
}

/**
 * @brief  Gets a pointer to the internal DMA handle associated with the UART TX.
 * @return Pointer to DMA_HandleTypeDef structure.
 */
DMA_HandleTypeDef* pxDrvH_UartGetDmaHandle(void)
{
  return &hdma_usart3_tx;
}
