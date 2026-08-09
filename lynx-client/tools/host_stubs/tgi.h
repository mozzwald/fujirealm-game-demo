#ifndef STUB_TGI_H
#define STUB_TGI_H
void tgi_install(void *drv); void tgi_init(void);
unsigned char tgi_busy(void); void tgi_clear(void);
void tgi_updatedisplay(void); void tgi_setframerate(unsigned char r);
void tgi_setpalette(const unsigned char *p);
void tgi_setcollisiondetection(unsigned char on);
void tgi_setcolor(unsigned char c); void tgi_setbgcolor(unsigned char c);
void tgi_bar(int x1,int y1,int x2,int y2);
void tgi_line(int x1,int y1,int x2,int y2);
void tgi_sprite(const void *scb);
#endif
