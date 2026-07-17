/**
 * @file App_Anticorrosao.h
 * @brief Application layer logic for the Anticorrosao device.
 * @note Fits the ISI SIM Firmware Development Standard.
 */

#ifndef APP_ANTICORROSAO_H
#define APP_ANTICORROSAO_H

#ifdef __cplusplus
extern "C" {
#endif

#include "Config_App.h"
#include "Srv_Ensaio.h"

/**
 * @brief  Initializes the application layer, including drivers, DWT, and services.
 * @return None
 */
void vApp_AnticorrosaoInit(void);

/**
 * @brief  Main application task executed inside the infinite loop.
 * @return None
 */
void vApp_AnticorrosaoTask(void);

#ifdef __cplusplus
}
#endif

#endif /* APP_ANTICORROSAO_H */
