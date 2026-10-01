#include "ovl_api.h"
#include "art.h"
#include "gime.h"
#include <cmoc.h>

extern const unsigned char ovl_image[];
extern const unsigned ovl_image_len;
extern const unsigned char art_image[];

void art_store(void)
{
    static const unsigned char black[16] = {
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    };
    unsigned ofs;

    gime_set_palette(black); /* 128K: this overwrites the screen shown now */
    *(unsigned char *)0xFFAC = ART_BLOCK;
    for (ofs = 0; ofs < GFX_BLOCK_BYTES; ofs += 1024) {
        GFX_ENTER();
        memcpy(GFX_WINDOW + ofs, art_image + ofs, 1024);
        GFX_LEAVE();
    }
}

void ovl_store(const struct ovl_handoff *h)
{
    gime_init_task1();
    *(unsigned char *)0xFFAC = OVL_BLOCK;
    GFX_ENTER();
    memcpy(GFX_WINDOW, ovl_image, ovl_image_len);
    memcpy(GFX_WINDOW + OVL_HANDOFF_OFS, h, sizeof(*h));
    GFX_LEAVE();
}
