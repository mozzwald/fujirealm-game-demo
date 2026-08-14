' sound.bas -- minimal PSG effects, channel 0 only, no PLAY (the music
' player would cost 28 of the 8-bit variable pool).
'
' sfx_start: sfx_id 1 step, 2 fire, 3 hit, 4 pickup/interact, 5 message.
' sfx_tick: called once per loop pass; silences the channel when done.


sfx_start: PROCEDURE
    IF sfx_id = 1 THEN
        sfx_t = 2
        SOUND 0, 1400, 4
    ELSEIF sfx_id = 2 THEN
        sfx_t = 5
        SOUND 0, 250, 10
    ELSEIF sfx_id = 3 THEN
        sfx_t = 6
        SOUND 0, 2400, 10
    ELSEIF sfx_id = 4 THEN
        sfx_t = 4
        SOUND 0, 500, 9
    ELSE
        sfx_t = 4
        SOUND 0, 380, 7
    END IF
END

sfx_tick: PROCEDURE
    IF sfx_t = 0 THEN RETURN
    sfx_t = sfx_t - 1
    IF sfx_t = 0 THEN SOUND 0, 1, 0
END
