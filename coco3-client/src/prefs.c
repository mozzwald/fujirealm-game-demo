#include "prefs.h"
#include <coco.h>
#include <cmoc.h>
#include <fujinet-fuji.h>

/* Same creator/app id every FujiRealm client uses -- identifies the game, not
 * the platform. */
#define FUJINET_CREATOR_ID 0x3022
#define FUJINET_APP_ID 2
#define APPKEY_SOUND 4
#define SOUND_MAGIC 0x5D /* not the old scrolling setting's $A5 in this key */

unsigned char pref_sound_load(void)
{
    unsigned char buf[MAX_APPKEY_LEN + 2];
    uint16_t count;

    fuji_set_appkey_details(FUJINET_CREATOR_ID, FUJINET_APP_ID, DEFAULT);
    if (fuji_read_appkey(APPKEY_SOUND, &count, buf) && count == 2 &&
        buf[0] == SOUND_MAGIC && buf[1] <= 1) {
        return buf[1];
    }
    return 1;
}

void pref_sound_save(unsigned char on)
{
    unsigned char rec[2];

    rec[0] = SOUND_MAGIC;
    rec[1] = on;
    fuji_set_appkey_details(FUJINET_CREATOR_ID, FUJINET_APP_ID, DEFAULT);
    fuji_write_appkey(APPKEY_SOUND, 2, rec);
}

void pref_items_seen_save(unsigned long token, unsigned char seen)
{
    unsigned char rec[ITEMS_LEN];

    rec[0] = ITEMS_MAGIC;
    memcpy(rec + 1, &token, 4);
    rec[5] = seen;
    fuji_set_appkey_details(FUJINET_CREATOR_ID, FUJINET_APP_ID, DEFAULT);
    fuji_write_appkey(APPKEY_ITEMS_SEEN, ITEMS_LEN, rec);
}
