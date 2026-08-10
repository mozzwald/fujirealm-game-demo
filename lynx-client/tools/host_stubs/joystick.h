#ifndef STUB_JOY_H
#define STUB_JOY_H
unsigned char joy_install(void *drv); unsigned char joy_read(unsigned char j);
/* The bit values are the Lynx driver's (cc65 include/lynx.h), not arbitrary:
 * the name picker hands joy_read()'s byte to nameentry.c as a mask, and a
 * compile-time check in main.c compares the two layouts. Stub bits of our own
 * invention would make that check test nothing. */
#define JOY_UP_MASK     0x80
#define JOY_DOWN_MASK   0x40
#define JOY_LEFT_MASK   0x20
#define JOY_RIGHT_MASK  0x10
#define JOY_BTN_A_MASK  0x01
#define JOY_BTN_B_MASK  0x02
#define JOY_UP(v)     ((v) & JOY_UP_MASK)
#define JOY_DOWN(v)   ((v) & JOY_DOWN_MASK)
#define JOY_LEFT(v)   ((v) & JOY_LEFT_MASK)
#define JOY_RIGHT(v)  ((v) & JOY_RIGHT_MASK)
#define JOY_BTN_A(v)  ((v) & JOY_BTN_A_MASK)
#define JOY_BTN_B(v)  ((v) & JOY_BTN_B_MASK)
#endif
