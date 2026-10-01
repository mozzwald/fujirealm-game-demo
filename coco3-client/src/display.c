#include "display.h"
#include "palette.h"
#include <coco.h>
#include <cmoc.h>
#include <fujinet-fuji.h>

/* Same creator/app id every FujiRealm client uses -- identifies the
 * game, not the platform. */
#define FUJINET_CREATOR_ID 0x3022
#define FUJINET_APP_ID 2
#define APPKEY_DISPLAY_TARGET 2

static unsigned char current_target = DISPLAY_RGB;

unsigned char display_target_saved(void)
{
    /* fuji_read_appkey needs 2 bytes beyond the key size. DEFAULT (64-byte)
     * keys: SIZE_256 is not fully supported yet. */
    unsigned char buf[MAX_APPKEY_LEN + 2];
    uint16_t count;

    fuji_set_appkey_details(FUJINET_CREATOR_ID, FUJINET_APP_ID, DEFAULT);

    /* DriveWire reports success reading a never-written key, so require the
     * exact 1-byte record holding 0 or 1. */
    if (fuji_read_appkey(APPKEY_DISPLAY_TARGET, &count, buf)
        && count == 1 && (buf[0] == DISPLAY_RGB || buf[0] == DISPLAY_COMPOSITE)) {
        current_target = buf[0];
        return current_target;
    }
    return DISPLAY_UNSET;
}

void display_target_set(unsigned char t)
{
    current_target = t;
    fuji_write_appkey(APPKEY_DISPLAY_TARGET, 1, &current_target);
}

void display_text_colors(void)
{
    unsigned char white = current_target == DISPLAY_COMPOSITE ? 48 : 63;

    attr(0, 0, 0, 0);                 /* foreground palette 8, background 0 */
    *(unsigned char *)0xFFB0 = 0;
    *(unsigned char *)0xFFB8 = white;
    *(unsigned char *)0xFF9A = 0; /* border */
}

unsigned char display_target_toggle(void)
{
    display_target_set(current_target ? DISPLAY_RGB : DISPLAY_COMPOSITE);
    return current_target;
}
