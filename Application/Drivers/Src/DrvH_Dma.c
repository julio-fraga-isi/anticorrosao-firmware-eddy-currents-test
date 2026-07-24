/**
 * @file DrvH_Dma.c
 * @brief High-level driver abstraction for DMA controller, calling CubeMX generated initialization.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#include "DrvH_Dma.h"
#include "dma.h"

/**
 * @brief  Initializes the DMA Controller by calling CubeMX generated configuration.
 * @return None
 */
void vDrvH_DmaInit(void)
{
  MX_DMA_Init();
}
