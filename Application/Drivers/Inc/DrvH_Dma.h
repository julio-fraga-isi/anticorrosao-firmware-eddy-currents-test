/**
 * @file DrvH_Dma.h
 * @brief High-level driver abstraction for DMA controller.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef DRVH_DMA_H
#define DRVH_DMA_H

#ifdef __cplusplus
extern "C" {
#endif

#include "Config_App.h"

/**
 * @brief  Initializes the DMA Controller clocks and interrupt priorities.
 * @return None
 */
void vDrvH_DmaInit(void);

#ifdef __cplusplus
}
#endif

#endif /* DRVH_DMA_H */
