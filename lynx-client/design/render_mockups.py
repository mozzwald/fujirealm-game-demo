#!/usr/bin/env python3
"""Render faithful Lynx-resolution mockups from the real FujiRealm A8 art."""
import re, csv, base64, io, os
from pathlib import Path
from PIL import Image

# Repo root, two levels up from lynx-client/design/.
ROOT = Path(__file__).resolve().parents[2]
INC  = str(ROOT / "atari8-client" / "generated" / "fujirealm_art.inc")
OUT  = os.environ.get("MOCKUP_OUT", str(Path(__file__).resolve().parent))

# ---- parse the .inc dta tables ----------------------------------------
def parse_labeled_bytes(text, label, count):
    # find "label\n dta ...." consecutive dta lines
    idx = text.index("\n", text.index(label+"\n"))
    vals = []
    for line in text[idx:].splitlines():
        s = line.strip()
        if s.startswith("dta"):
            for tok in s[3:].split(","):
                tok = tok.strip()
                m = re.match(r"\$([0-9A-Fa-f]+)", tok)
                if m: vals.append(int(m.group(1),16))
        elif s and not s.startswith("dta") and vals:
            break
        if len(vals) >= count and count:
            return vals[:count]
    return vals[:count] if count else vals

txt = open(INC).read()
font = parse_labeled_bytes(txt, "font_data", 128*8)          # 128 glyphs x 8 bytes
tl = parse_labeled_bytes(txt, "tile2x2_tl_overworld", 40)
tr = parse_labeled_bytes(txt, "tile2x2_tr_overworld", 40)
bl = parse_labeled_bytes(txt, "tile2x2_bl_overworld", 40)
br = parse_labeled_bytes(txt, "tile2x2_br_overworld", 40)
assert len(font)==1024, len(font)

# ---- Atari byte -> RGB (curated for the bytes actually used) ----------
ATARI = {
    0x00:(0,0,0),      0x02:(35,35,35),   0x06:(78,78,78),  0x08:(120,120,120),
    0x0c:(200,200,200),0x0e:(228,228,228),
    0xc8:(86,168,54),  0x24:(112,74,33),  0x4a:(214,110,92),
    0x84:(44,64,150),  0x98:(112,150,214),0xc2:(40,110,36),
    0x46:(150,86,60),  0x0a:(160,160,160),
}
def rgb(b): return ATARI.get(b,(255,0,255))

# overworld palette registers  (COLOR4,COLOR0,COLOR1,COLOR2,COLOR3)
OVER = {"C4":0x00,"C0":0xc8,"C1":0x24,"C2":0x0e,"C3":0x4a}

def glyph_pixels(code):
    """return 8x8 list of pixel VALUES 0..3, and whether bit7 (COLOR3) set."""
    hi = code & 0x80
    ch = code & 0x7f
    base = ch*8
    rows=[]
    for r in range(8):
        byte = font[base+r]
        px=[]
        for p in range(4):
            v = (byte >> (6-2*p)) & 0x03
            px.append(v); px.append(v)   # ANTIC4 -> each pair spans 2 hires px?
        # ANTIC4: 4 color-pixels across the byte, each 2 screen px wide = 8 wide
        rows.append([ (byte >> (6-2*p)) & 3 for p in range(4)])
    return rows, hi

def pen_to_rgb(v, hi, pal):
    if v==0: return rgb(pal["C4"])
    if v==1: return rgb(pal["C0"])
    if v==2: return rgb(pal["C1"])
    return rgb(pal["C3"] if hi else pal["C2"])

def draw_char(img, ox, oy, code, pal, scale=1, palmap=None):
    rows,hi = glyph_pixels(code)
    for r in range(8):
        for c in range(4):        # 4 colour-pixels, each 2 wide
            v=rows[r][c]
            col = palmap(v,hi) if palmap else pen_to_rgb(v,hi,pal)
            if col is None: continue
            for dx in range(2*scale):
                for dy in range(scale):
                    img.putpixel((ox+(c*2)*scale+dx, oy+r*scale+dy), col)

def draw_tile(img, ox, oy, tid, pal, scale=1, palmap=None):
    draw_char(img, ox,          oy,          tl[tid], pal, scale, palmap)
    draw_char(img, ox+8*scale,  oy,          tr[tid], pal, scale, palmap)
    draw_char(img, ox,          oy+8*scale,  bl[tid], pal, scale, palmap)
    draw_char(img, ox+8*scale,  oy+8*scale,  br[tid], pal, scale, palmap)

# ---- load a window of the overworld map -------------------------------
CODE = {"":0,"T":2,"H":3,"R":10,"U":12,"W":11,"#":7}
def load_map():
    rows=[]
    with open(ROOT+"/maps/overworld.csv") as f:
        rd=list(csv.reader(f))
    for line in rd[1:]:
        rows.append([c for c in line[1:]])
    return rows
M = load_map()
def tile_at(x,y):
    if y<0 or y>=len(M) or x<0 or x>=len(M[0]): return 7
    c=M[y][x]
    if c in CODE: return CODE[c]
    if c in ("V","G","F","N","X","C","P","E"): return 0  # entities sit on grass
    return 0

# ---- enhanced per-tile-type Lynx palette (16-colour world) ------------
# Each returns rgb per pen value 0..3 (bit7 handled). Lynx: each sprite has
# its own 4-pen palette drawn from one 16-colour global CLUT.
GRASS_A=(74,132,58); GRASS_B=(96,164,72); GRASS_D=(52,104,44)
def L_grass(v,hi): return {0:GRASS_A,1:GRASS_B,2:GRASS_D,3:GRASS_B}[v]
def L_tree(v,hi):
    return {0:GRASS_A,1:(58,120,44),2:(96,60,28),3:(120,180,80) if not hi else (150,90,60)}[v]
def L_water(v,hi):
    return {0:(38,86,150),1:(58,120,196),2:(30,64,120),3:(150,200,235)}[v]
def L_road(v,hi):
    return {0:(150,124,84),1:(176,150,104),2:(120,96,64),3:(196,176,130)}[v]
def L_build(v,hi):
    return {0:GRASS_A,1:(120,110,100),2:(80,72,66),3:(190,70,50)}[v]
def L_herb(v,hi):
    return {0:GRASS_A,1:GRASS_B,2:(60,120,44),3:(230,90,110)}[v]
ENH = {0:L_grass,2:L_tree,3:L_herb,10:L_road,11:L_water,12:L_build,7:lambda v,hi:(24,40,20)}

def draw_tile_enh(img, ox,oy, tid, scale=1):
    pm = ENH.get(tid, L_grass)
    draw_char(img, ox,          oy,          tl[tid], OVER, scale, pm)
    draw_char(img, ox+8*scale,  oy,          tr[tid], OVER, scale, pm)
    draw_char(img, ox,          oy+8*scale,  bl[tid], OVER, scale, pm)
    draw_char(img, ox+8*scale,  oy+8*scale,  br[tid], OVER, scale, pm)

# ---- simple hand sprites (player + beaver) overlaid -------------------
def blit_sprite(img, ox, oy, rows, pal, scale=1, trans='.'):
    for r,row in enumerate(rows):
        for c,ch in enumerate(row):
            if ch==trans or ch==' ': continue
            col=pal.get(ch)
            if col is None: continue
            for dx in range(scale):
                for dy in range(scale):
                    px,py=ox+c*scale+dx, oy+r*scale+dy
                    if 0<=px<img.width and 0<=py<img.height:
                        img.putpixel((px,py),col)

PLAYER = [
 "....gggg....","...gg..gg...",".gggwwwwggg.","..gwsssswg..",
 "..gws..sswg.","..gwssssswg.","...ggwwgg...","..bb.gg.bb..",
 "..b.gyyyg.b.","...gy..yg...","...gy..yg...","...gg..gg...",
]
PPAL={'g':(40,80,32),'w':(228,200,150),'s':(60,40,20),'b':(120,74,33),'y':(220,180,60)}
BEAVER=[
 "..........","..kk..kk..",".kwwkkww k","..kk..kk..",".kkbbbbkk.",
 "kbbbbbbbbk","kb w  w bk","kbbbbbbbbk",".kbb bbk..","..kk..kk..",
]
BPAL={'k':(60,36,20),'w':(230,230,230),'b':(150,96,52)}

# =====================================================================
def render(mode, tilesize):
    """mode: 'faithful' | 'enhanced' ; tilesize 16 or 8"""
    W,H=160,102
    img=Image.new("RGB",(W,H),(0,0,0))
    scale = 1 if tilesize==16 else 1   # we downscale for 8px by scale of chars
    hud_h = 12 if tilesize==16 else 12
    view_h = H-hud_h
    if tilesize==16:
        cols=W//16; rows=view_h//16
        step=16; cscale=1
    else:
        cols=W//8; rows=view_h//8
        step=8; cscale=0  # special: render 16px tile then downscale
    # camera near a water/tree/building area (around x=44,y=40)
    cx,cy=40,36
    if tilesize==16:
        for ty in range(rows):
            for tx in range(cols):
                tid=tile_at(cx+tx,cy+ty)
                if mode=='faithful':
                    draw_tile(img,tx*16,ty*16,tid,OVER,1)
                else:
                    draw_tile_enh(img,tx*16,ty*16,tid,1)
    else:
        # render each tile at 16px into temp, downscale to 8
        for ty in range(rows):
            for tx in range(cols):
                tid=tile_at(cx+tx,cy+ty)
                t=Image.new("RGB",(16,16))
                if mode=='faithful': draw_tile(t,0,0,tid,OVER,1)
                else: draw_tile_enh(t,0,0,tid,1)
                t=t.resize((8,8),Image.BILINEAR)
                img.paste(t,(tx*8,ty*8))
    # sprites: player center-ish, a couple beavers
    ppal=PPAL
    if tilesize==16:
        blit_sprite(img, (cols//2)*16+2, (rows//2)*16+2, PLAYER, PPAL,1)
        blit_sprite(img, (cols//2-2)*16+3, (rows//2-1)*16+3, BEAVER, BPAL,1)
        blit_sprite(img, (cols//2+2)*16+3, (rows//2+1)*16+3, BEAVER, BPAL,1)
    else:
        blit_sprite(img, (cols//2)*8+1, (rows//2)*8, PLAYER, PPAL,1)  # ~ still 12px
        blit_sprite(img, (cols//2-3)*8+1, (rows//2-1)*8+1, BEAVER, BPAL,1)
    # HUD
    hud_bg=(20,24,40) if mode=='enhanced' else (0,0,0)
    for y in range(view_h,H):
        for x in range(W):
            img.putpixel((x,y),hud_bg)
    # HUD text via font glyphs would need ASCII map; draw simple hp hearts + bars
    def bar(ox,val,col):
        for i in range(val):
            for dx in range(6):
                for dy in range(5):
                    img.putpixel((ox+i*8+dx, view_h+3+dy), col)
    # hearts (red), then a gold coin, xp bar (blue)
    heart=(220,60,60) if mode=='enhanced' else rgb(0x4a)
    for i in range(5):
        for dx in range(6):
            for dy in range(5):
                img.putpixel((3+i*7+dx, view_h+4+dy), heart)
    gold=(230,190,60)
    for dx in range(6):
        for dy in range(6):
            img.putpixel((120+dx,view_h+3+dy),gold)
    xpc=(90,140,230) if mode=='enhanced' else rgb(0x0e)
    for i in range(30):
        img.putpixel((3+i, H-2), xpc)
    return img

# ---- 4x5 HUD font (the Lynx client ships its own text font) -----------
TINY = {
"A":[".##.","#..#","####","#..#","#..#"],"B":["###.","#..#","###.","#..#","###."],
"C":[".###","#...","#...","#...",".###"],"D":["###.","#..#","#..#","#..#","###."],
"E":["####","#...","###.","#...","####"],"F":["####","#...","###.","#...","#..."],
"G":[".###","#...","#.##","#..#",".###"],"H":["#..#","#..#","####","#..#","#..#"],
"I":["###.",".#..",".#..",".#..","###."],"J":["..##","...#","...#","#..#",".##."],
"K":["#..#","#.#.","##..","#.#.","#..#"],"L":["#...","#...","#...","#...","####"],
"M":["#..#","####","####","#..#","#..#"],"N":["#..#","##.#","#.##","#..#","#..#"],
"O":[".##.","#..#","#..#","#..#",".##."],"P":["###.","#..#","###.","#...","#..."],
"Q":[".##.","#..#","#..#","#.##",".###"],"R":["###.","#..#","###.","#.#.","#..#"],
"S":[".###","#...",".##.","...#","###."],"T":["####","..#.","..#.","..#.","..#."],
"U":["#..#","#..#","#..#","#..#",".##."],"V":["#..#","#..#","#..#",".##.",".##."],
"W":["#..#","#..#","####","####","#..#"],"X":["#..#",".##.",".##.",".##.","#..#"],
"Y":["#..#",".##.","..#.","..#.","..#."],"Z":["####","...#",".##.","#...","####"],
"0":[".##.","#..#","#..#","#..#",".##."],"1":[".#..","##..",".#..",".#..","###."],
"2":["###.","...#",".##.","#...","####"],"3":["###.","...#",".##.","...#","###."],
"4":["#..#","#..#","####","...#","...#"],"5":["####","#...","###.","...#","###."],
"6":[".###","#...","###.","#..#",".##."],"7":["####","...#","..#.",".#..",".#.."],
"8":[".##.","#..#",".##.","#..#",".##."],"9":[".##.","#..#",".###","...#","###."],
" ":["....","....","....","....","...."],"!":[".#..",".#..",".#..","....",".#.."],
":":["....",".#..","....",".#..","...."],".":["....","....","....","....",".#.."],
"+":["....",".#..","###.",".#..","...."],"'":[".#..",".#..","....","....","...."],
"-":["....","....","###.","....","...."],",":["....","....","....",".#..","#..."],
}
def draw_text(img, ox, oy, s, ink):
    x=ox
    for ch in s.upper():
        g=TINY.get(ch, TINY[" "])
        for r in range(5):
            for c in range(4):
                if g[r][c]=="#":
                    px,py=x+c, oy+r
                    if 0<=px<img.width and 0<=py<img.height:
                        img.putpixel((px,py),ink)
        x+=5
    return x

HEART=["...","#.#","###","###",".#."]   # tiny 3x5-ish -> use 5-wide
HEART5=[".#.#.","#####","#####",".###.","..#.."]
def draw_heart(img,ox,oy,col):
    for r,row in enumerate(HEART5):
        for c,ch in enumerate(row):
            if ch=="#": img.putpixel((ox+c,oy+r),col)
COIN5=[".###.","#...#","#.#.#","#...#",".###."]
def draw_coin(img,ox,oy,col,edge):
    for r,row in enumerate(COIN5):
        for c,ch in enumerate(row):
            img.putpixel((ox+c,oy+r), col if ch=="#" else edge if (r in(0,4) or c in(0,4)) else col)

# ---- Option B (chosen): enhanced 16-colour, 10x5 view + 2-line HUD ----
def render_optionB():
    W,H=160,102
    img=Image.new("RGB",(W,H),(0,0,0))
    view_h=80                     # 10x5 tiles of 16px
    cols,rows=10,5
    cx,cy=37,35                   # frame a grassy bank with the river on the right
    for ty in range(rows):
        for tx in range(cols):
            draw_tile_enh(img,tx*16,ty*16,tile_at(cx+tx,cy+ty),1)
    # sprites, all on land (left/centre grass; river is on the right)
    blit_sprite(img, 5*16+2, 2*16+2, PLAYER, PPAL,1)   # hunter, centre
    blit_sprite(img, 2*16+3, 1*16+3, BEAVER, BPAL,1)   # beaver on grass
    blit_sprite(img, 3*16+3, 3*16+3, BEAVER, BPAL,1)   # beaver on grass
    # ---- HUD: navy panel, amber rule, stats row, message row ----
    navy=(18,22,38); rule=(240,169,42); ink=(232,236,248); msg=(120,200,150)
    for y in range(view_h,H):
        for x in range(W): img.putpixel((x,y),navy)
    for x in range(W): img.putpixel((x,view_h),rule)          # top rule
    # stats row (y 84): 5 hearts, gold coin + count, level
    hy=84
    for i in range(5): draw_heart(img, 3+i*7, hy, (232,72,72))
    draw_coin(img, 108, hy, (240,200,70),(150,110,20))
    draw_text(img, 116, hy, "12", (245,210,90))
    draw_text(img, 132, hy, "LV3", ink)
    # message row (y 94): a server MESSAGE packet, e.g. Farmer Dan quest bark
    for x in range(2,W-2): img.putpixel((x,view_h+11),(40,48,74))  # divider
    draw_text(img, 4, 94, "DAN: THE BEAVERS ARE BACK!", msg)
    return img

def save(img,name):
    p=f"{OUT}/{name}.png"
    img.resize((160*4,102*4),Image.NEAREST).save(p)
    img.save(f"{OUT}/{name}_1x.png")
    return p

imgs={}
imgs['faithful_16']=render('faithful',16)
imgs['enhanced_16']=render_optionB()
imgs['enhanced_8'] =render('enhanced',8)
for k,v in imgs.items():
    print(save(v,k))
print("done")
