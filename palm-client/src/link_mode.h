#ifndef FUJIREALM_LINK_MODE_H
#define FUJIREALM_LINK_MODE_H

#include <PalmOS.h>

/* Select the port before the N: driver makes its first FujiBus call. */
Err FnOpenMode(UInt8 mode);

#endif
