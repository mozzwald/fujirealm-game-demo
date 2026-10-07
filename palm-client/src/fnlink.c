/* SPDX-License-Identifier: GPL-3.0-only
 * FujiBus link for the four Palm transports offered by FN Texas Hold'em.
 * Legacy uses the new Serial Manager; named libraries use the old Ser* API.
 * The framing and single-request retry behavior follow its common/fnlink.c.
 */
#include <PalmOS.h>
#include <SerialMgrOld.h>

#include "fnlink.h"
#include "link_mode.h"
#include "net.h"

#define FN_BAUD 115200uL
#define FN_RX_BUFFER 1024

/* Handspring's keyboard daemon owns the UART until this selector releases it.
 * The USB Library has a separate endpoint and does not need the call. */
Err HsExtKeyboardEnable(Boolean enable)
    __attribute__((__callseq__("move.w #5,-(%%sp); trap #15; dc.w 0xA349")));

static UInt16 gPort;
static UInt8 gMode;
static Boolean gOpen;
static UInt8 gRxBuffer[FN_RX_BUFFER];
static UInt8 gFrame[FB_MAX_FRAME];

Err FnOpenMode(UInt8 mode)
{
    Err err;
    UInt16 ref;
    const char *name;
    SerSettingsType settings;

    if (gOpen)
        FnClose();
    if (mode == NET_LINK_LEGACY) {
        err = SrmOpen(serPortCradlePort, FN_BAUD, &gPort);
        if (err != errNone)
            return err;
        SrmSetReceiveBuffer(gPort, gRxBuffer, sizeof(gRxBuffer));
    } else {
        if (mode == NET_LINK_USB)
            name = "USB Library";
        else if (mode == NET_LINK_BUILTIN)
            name = "BuiltIn SerLib";
        else if (mode == NET_LINK_SERIAL)
            name = "Serial Library";
        else
            return sysErrParamErr;

        if (mode != NET_LINK_USB) {
            UInt32 version;
            if (FtrGet('hsEx', 0, &version) == errNone)
                HsExtKeyboardEnable(false);
        }
        err = SysLibFind(name, &ref);
        if (err != errNone && mode == NET_LINK_USB)
            err = SysLibLoad(sysFileTLibrary, 'HsUs', &ref);
        if (err != errNone)
            return err;
        err = SerOpen(ref, 0, FN_BAUD);
        if (err != errNone)
            return err;
        gPort = ref;
        err = SerGetSettings(ref, &settings);
        if (err == errNone) {
            settings.baudRate = FN_BAUD;
            settings.flags = serSettingsFlagBitsPerChar8 | serSettingsFlagStopBits1;
            err = SerSetSettings(ref, &settings);
        }
        if (err != errNone) {
            SerClose(ref);
            return err;
        }
        SerSetReceiveBuffer(ref, gRxBuffer, sizeof(gRxBuffer));
    }
    gMode = mode;
    gOpen = true;
    return errNone;
}

Err FnOpen(void)
{
    return gOpen ? errNone : FnOpenMode(NET_LINK_LEGACY);
}

void FnClose(void)
{
    if (!gOpen)
        return;
    if (gMode == NET_LINK_LEGACY) {
        SrmSetReceiveBuffer(gPort, NULL, 0);
        SrmClose(gPort);
    } else {
        SerSetReceiveBuffer(gPort, NULL, 0);
        SerClose(gPort);
    }
    gOpen = false;
}

static UInt16 ReceiveFrame(UInt32 deadline)
{
    UInt16 len = 0;
    UInt8 byte;
    Err err;

    while ((Int32)(TimGetTicks() - deadline) < 0) {
        UInt32 got;
        if (gMode == NET_LINK_LEGACY)
            got = SrmReceive(gPort, &byte, 1, SysTicksPerSecond() / 20, &err);
        else
            got = SerReceive(gPort, &byte, 1, SysTicksPerSecond() / 20, &err);
        if (got != 1) {
            if (err != errNone && err != serErrTimeOut) {
                if (gMode == NET_LINK_LEGACY)
                    SrmClearErr(gPort);
                else
                    SerClearErr(gPort);
            }
            continue;
        }
        if (len == 0 && byte != 0xC0)
            continue;
        if (byte == 0xC0 && len > 1) {
            gFrame[len++] = byte;
            return len;
        }
        if (byte == 0xC0)
            len = 0;
        if (len >= sizeof(gFrame))
            len = 0;
        gFrame[len++] = byte;
    }
    return 0;
}

Err FnCallDevice(UInt8 device, UInt8 command, const FbParam *params, UInt16 nparams,
                 const void *payload, UInt16 payloadLen,
                 void *reply, UInt16 replyMax, UInt16 *replyLen,
                 UInt16 attempts, UInt32 waitTicks)
{
    UInt8 request[FB_MAX_FRAME];
    UInt16 requestLen, frameLen, i;
    FbReply parsed;
    Err err;

    if (!gOpen && (err = FnOpen()) != errNone)
        return err;
    requestLen = fb_build_request(device, command, params, nparams,
                                  (const UInt8 *)payload, payloadLen, request, sizeof(request));
    if (requestLen == 0)
        return fnErrTooBig;

    for (i = 0; i < attempts; ++i) {
        if (gMode == NET_LINK_LEGACY) {
            SrmReceiveFlush(gPort, 0);
            SrmSend(gPort, request, requestLen, &err);
            if (err != errNone)
                continue;
            SrmSendWait(gPort);
        } else {
            UInt32 sent = 0;
            SerReceiveFlush(gPort, 0);
            while (sent < requestLen) {
                UInt32 n = SerSend(gPort, request + sent, requestLen - sent, &err);
                if (err != errNone || n == 0)
                    break;
                sent += n;
            }
            if (sent != requestLen)
                continue;
            if (SerSendWait(gPort, SysTicksPerSecond()) != errNone)
                continue;
        }
        frameLen = ReceiveFrame(TimGetTicks() + waitTicks);
        if (frameLen == 0 || !fb_parse_reply(gFrame, frameLen, &parsed) ||
            parsed.device != device)
            continue;
        if (parsed.command != FB_CMD_ACK)
            return fnErrRefused;
        if (replyLen)
            *replyLen = parsed.data_len < replyMax ? parsed.data_len : replyMax;
        if (reply && replyLen)
            MemMove(reply, parsed.data, *replyLen);
        return errNone;
    }
    return fnErrNoReply;
}
