#ifndef STUB_LYNX_H
#define STUB_LYNX_H
#include <stdlib.h>
/* Enough of the cc65 Lynx target to let gcc analyse render.c / main.c. */
#define BPP_4              0xC0
#define TYPE_BACKNONCOLL   0x04
#define TYPE_NONCOLL       0x01
#define LITERAL            0x80
#define REHV               0x10
#define NO_COLLIDE         0x20
typedef struct {
    unsigned char sprctl0, sprctl1, sprcoll;
    unsigned char *next;
    unsigned char *data;
    signed int hpos, vpos;
    unsigned int hsize, vsize;
    unsigned char penpal[8];
} SCB_REHV_PAL;
struct __suzy { unsigned char joystick; unsigned char switches; };
extern struct __suzy _suzy;
/* The real header exposes these as macros over hardware; tests do not use them. */
#define SUZY _suzy
#define BUTTON_OPTION1 0x08
#define BUTTON_OPTION2 0x04
#define BUTTON_PAUSE   0x01
extern char lynx_160_102_16_tgi[];
extern char lynx_stdjoy_joy[];
extern char lynx_comlynx_ser[];
#endif
