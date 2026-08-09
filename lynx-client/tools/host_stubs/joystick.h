#ifndef STUB_JOY_H
#define STUB_JOY_H
unsigned char joy_install(void *drv); unsigned char joy_read(unsigned char j);
#define JOY_UP(v)     ((v) & 0x01)
#define JOY_DOWN(v)   ((v) & 0x02)
#define JOY_LEFT(v)   ((v) & 0x04)
#define JOY_RIGHT(v)  ((v) & 0x08)
#define JOY_BTN_A(v)  ((v) & 0x10)
#define JOY_BTN_B(v)  ((v) & 0x20)
#endif
