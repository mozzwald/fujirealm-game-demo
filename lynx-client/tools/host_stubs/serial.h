#ifndef STUB_SER_H
#define STUB_SER_H
#define SER_ERR_OK 0
#define SER_ERR_NO_DATA 1
#define SER_ERR_OVERFLOW 2
#define SER_BAUD_62500 1
#define SER_BITS_8 0
#define SER_STOP_1 0
#define SER_PAR_ODD 0
#define SER_HS_NONE 0
struct ser_params { unsigned char baudrate, databits, stopbits, parity, handshake; };
unsigned char ser_install(void *drv);
unsigned char ser_open(const struct ser_params *p);
unsigned char ser_get(char *b);
unsigned char ser_put(unsigned char b);
unsigned char ser_status(unsigned char *s);
#endif
