#!/usr/bin/env python3
"""
TRN file codec for OMF:2097.

Usage:
    trn_codec.py decode INPUT.TRN  OUTPUT.json
    trn_codec.py encode INPUT.json OUTPUT.TRN

Sprite pixel data and unknown binary blobs are preserved as base64 for round-trip
fidelity; they don't need to be human-edited.
"""

import base64
import json
import struct
import sys
from pathlib import Path

PILOT_BLOCK_LENGTH = 428
PILOT_XOR_KEY = PILOT_BLOCK_LENGTH & 0xFF  # 172 = 0xAC


# ---------------------------------------------------------------------------
# Color helpers (VGA 6-bit ↔ 8-bit)
# ---------------------------------------------------------------------------

def _c6to8(c: int) -> int:
    return (c << 2) | ((c & 0x30) >> 4)


def _c8to6(c: int) -> int:
    return (c >> 2) & 0x3F


# ---------------------------------------------------------------------------
# Sequential reader / writer
# ---------------------------------------------------------------------------

class _Reader:
    def __init__(self, data: bytes):
        self._d = data
        self._p = 0

    def seek(self, pos: int):
        self._p = pos

    def tell(self) -> int:
        return self._p

    def read(self, n: int) -> bytes:
        b = self._d[self._p:self._p + n]
        self._p += n
        return b

    def u8(self)  -> int: return struct.unpack_from('<B', self.read(1))[0]
    def i16(self) -> int: return struct.unpack_from('<h', self.read(2))[0]
    def u16(self) -> int: return struct.unpack_from('<H', self.read(2))[0]
    def i32(self) -> int: return struct.unpack_from('<i', self.read(4))[0]
    def u32(self) -> int: return struct.unpack_from('<I', self.read(4))[0]
    def f32(self) -> float: return struct.unpack_from('<f', self.read(4))[0]

    def fixed_str(self, n: int) -> str:
        return self.read(n).rstrip(b'\x00').decode('latin-1')

    def var_str(self):
        """Return None for len=0 (null pointer), str otherwise (may be empty)."""
        length = self.u16()
        if not length:
            return None
        return self.read(length).rstrip(b'\x00').decode('latin-1')

    def skip(self, n: int):
        self._p += n


class _Writer:
    def __init__(self):
        self._b = bytearray()

    def tell(self) -> int:
        return len(self._b)

    def write(self, b: bytes):
        self._b.extend(b)

    def u8(self, v: int):  self._b.extend(struct.pack('<B', v & 0xFF))
    def i16(self, v: int): self._b.extend(struct.pack('<h', v))
    def u16(self, v: int): self._b.extend(struct.pack('<H', v & 0xFFFF))
    def i32(self, v: int): self._b.extend(struct.pack('<i', v))
    def u32(self, v: int): self._b.extend(struct.pack('<I', v & 0xFFFFFFFF))
    def f32(self, v: float): self._b.extend(struct.pack('<f', v))

    def fill(self, byte: int, n: int):
        self._b.extend(bytes([byte & 0xFF]) * n)

    def fixed_str(self, s: str, n: int):
        b = (s or "").encode('latin-1')[:n]
        self._b.extend(b + bytes(n - len(b)))

    def var_str(self, s):
        """None → uint16(0); str (including '') → uint16(len+1) + bytes + \0."""
        if s is None:
            self.u16(0)
            return
        b = s.encode('latin-1') + b'\x00'
        self.u16(len(b))
        self.write(b)

    def patch_u32(self, pos: int, v: int):
        struct.pack_into('<I', self._b, pos, v & 0xFFFFFFFF)

    def getvalue(self) -> bytes:
        return bytes(self._b)


# ---------------------------------------------------------------------------
# Palette helpers
# ---------------------------------------------------------------------------

def _read_pal(r: _Reader, count: int) -> list:
    result = []
    for _ in range(count):
        raw = r.read(3)
        result.append([_c6to8(raw[0]), _c6to8(raw[1]), _c6to8(raw[2])])
    return result


def _write_pal(w: _Writer, colors: list):
    for c in colors:
        w.u8(_c8to6(c[0]))
        w.u8(_c8to6(c[1]))
        w.u8(_c8to6(c[2]))


# ---------------------------------------------------------------------------
# Sprite (logo)
# ---------------------------------------------------------------------------

def _decode_sprite(r: _Reader) -> dict:
    data_len = r.u16()
    pos_x    = r.i16()
    pos_y    = r.i16()
    width    = r.u16()
    height   = r.u16()
    index    = r.u8()
    missing  = r.u8()
    data_b64 = ""
    if not missing and data_len:
        data_b64 = base64.b64encode(r.read(data_len)).decode('ascii')
    return {"len": data_len, "pos_x": pos_x, "pos_y": pos_y,
            "width": width, "height": height,
            "index": index, "missing": missing, "data_b64": data_b64}


def _encode_sprite(w: _Writer, s: dict):
    w.u16(s.get("len", 0))
    w.i16(s.get("pos_x", 0))
    w.i16(s.get("pos_y", 0))
    w.u16(s.get("width", 0))
    w.u16(s.get("height", 0))
    w.u8(s.get("index", 0))
    missing = s.get("missing", 1)
    w.u8(missing)
    if not missing:
        b64 = s.get("data_b64", "")
        if b64:
            w.write(base64.b64decode(b64))


# ---------------------------------------------------------------------------
# Pilot block
# ---------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _from_b64(p: dict, key: str, length: int) -> bytes:
    raw = p.get(key, "")
    b = base64.b64decode(raw) if raw else b''
    if len(b) < length:
        b = b + bytes(length - len(b))
    return b[:length]


def _decode_pilot(r: _Reader) -> dict:
    # Rolling XOR: key starts at PILOT_XOR_KEY and increments each byte (uint8 wrap)
    raw = bytearray(r.read(PILOT_BLOCK_LENGTH))
    key = PILOT_XOR_KEY
    for i in range(PILOT_BLOCK_LENGTH):
        raw[i] ^= key
        key = (key + 1) & 0xFF
    mr = _Reader(bytes(raw))

    p = {}
    p["unknown_a"] = mr.u32()
    p["name"]      = mr.fixed_str(18)
    p["wins"]      = mr.u16()
    p["losses"]    = mr.u16()
    p["rank"]      = mr.u8()
    p["har_id"]    = mr.u8()

    sa = mr.u16(); sb = mr.u16(); sc = mr.u16(); sd = mr.u8(); mr.skip(1)
    p["arm_power"]        = (sa >> 0) & 0x1F
    p["leg_power"]        = (sa >> 5) & 0x1F
    p["arm_speed"]        = (sa >> 10) & 0x1F
    p["leg_speed"]        = (sb >> 0) & 0x1F
    p["armor"]            = (sb >> 5) & 0x1F
    p["stun_resistance"]  = (sb >> 10) & 0x1F
    p["agility"]          = (sc >> 0) & 0x7F
    p["power"]            = (sc >> 7) & 0x7F
    p["endurance"]        = sd & 0x7F

    p["offense"]  = mr.u16()
    p["defense"]  = mr.u16()
    p["money"]    = mr.i32()
    p["color_3"]  = mr.u8()
    p["color_2"]  = mr.u8()
    p["color_1"]  = mr.u8()

    p["trn_name"]          = mr.fixed_str(13)
    p["trn_desc"]          = mr.fixed_str(31)
    p["trn_image"]         = mr.fixed_str(13)
    p["trn_rank_money"]    = mr.f32()
    p["trn_winnings_mult"] = mr.f32()
    mr.skip(40)  # runtime pointers

    p["pilot_id"]    = mr.u8()
    p["unknown_k"]   = mr.u8()
    p["force_arena"] = mr.u16()
    p["difficulty"]  = (mr.u8() >> 3) & 0x3
    p["unk_block_b"] = _b64(mr.read(2))
    p["movement"]    = mr.u8()
    p["unk_block_c"] = _b64(mr.read(6))
    p["enhancements"] = _b64(mr.read(11))

    mr.skip(1)
    req_flags = mr.u8()
    mr.skip(1)
    p["secret"]          = 1 if (req_flags & 0x02) else 0
    p["only_fight_once"] = 1 if (req_flags & 0x08) else 0

    reqs = [mr.u16() for _ in range(5)]
    p["req_rank"]       = reqs[0] & 0xFF
    p["req_max_rank"]   = (reqs[0] >> 8) & 0xFF
    p["req_fighter"]    = reqs[1] & 0x1F
    p["req_difficulty"] = (reqs[2] >> 8) & 0x0F
    p["req_enemy"]      = reqs[2] & 0xFF
    p["req_vitality"]   = reqs[3] & 0x7F
    p["req_accuracy"]   = (reqs[3] >> 7) & 0x7F
    p["req_avg_dmg"]    = reqs[4] & 0x7F
    p["req_scrap"]      = 1 if (reqs[4] & 0x80) else 0
    p["req_destroy"]    = 1 if ((reqs[4] >> 8) & 0x01) else 0

    att = [mr.u16() for _ in range(3)]
    p["att_normal"] = (att[0] >> 4) & 0x7F
    p["att_hyper"]  = att[1] & 0x7F
    p["att_jump"]   = (att[1] >> 7) & 0x7F
    p["att_def"]    = att[2] & 0x7F
    p["att_sniper"] = (att[2] >> 7) & 0x7F

    p["unk_block_d"] = _b64(mr.read(4))

    p["ap_close"]   = mr.i16()
    p["ap_throw"]   = mr.i16()
    p["ap_special"] = mr.i16()
    p["ap_jump"]    = mr.i16()
    p["ap_high"]    = mr.i16()
    p["ap_low"]     = mr.i16()
    p["ap_middle"]  = mr.i16()
    p["pref_jump"]  = mr.i16()
    p["pref_fwd"]   = mr.i16()
    p["pref_back"]  = mr.i16()

    p["unknown_e"] = mr.u32()
    p["learning"]  = mr.f32()
    p["forget"]    = mr.f32()
    p["sound_1"]   = mr.i16()
    p["sound_2"]   = mr.i16()
    p["sound_3"]   = mr.i16()
    p["unk_block_f"]          = _b64(mr.read(8))
    p["enemies_inc_unranked"] = mr.u16()
    p["enemies_ex_unranked"]  = mr.u16()
    p["unk_d_a"]              = mr.u16()
    p["har_trades"]           = mr.u32()
    p["winnings"]             = mr.u32()
    p["total_value"]          = mr.u32()
    p["current_health"]       = mr.i16()
    p["maximum_health"]       = mr.i16()
    p["unk_f_b"]              = mr.f32()
    mr.skip(8)

    # Palette indices 0-47 (stored as VGA 6-bit in file)
    p["palette_0_47"] = _read_pal(mr, 48)

    p["is_player"] = mr.u16()
    p["photo_id"]  = mr.u16() & 0x3FF

    # Quotes follow in the main (non-XOR'd) stream
    p["quotes"] = [r.var_str() for _ in range(10)]
    return p


def _encode_pilot(w: _Writer, p: dict):
    mw = _Writer()

    mw.u32(p.get("unknown_a", 0))
    mw.fixed_str(p.get("name", ""), 18)
    mw.u16(p.get("wins", 0))
    mw.u16(p.get("losses", 0))
    mw.u8(p.get("rank", 0))
    mw.u8(p.get("har_id", 0))

    sa = ((p.get("arm_power", 0)       & 0x1F) << 0  |
          (p.get("leg_power", 0)       & 0x1F) << 5  |
          (p.get("arm_speed", 0)       & 0x1F) << 10)
    sb = ((p.get("leg_speed", 0)       & 0x1F) << 0  |
          (p.get("armor", 0)           & 0x1F) << 5  |
          (p.get("stun_resistance", 0) & 0x1F) << 10)
    sc = ((p.get("agility", 0)         & 0x7F) << 0  |
          (p.get("power", 0)           & 0x7F) << 7)
    sd = p.get("endurance", 0) & 0x7F
    mw.u16(sa); mw.u16(sb); mw.u16(sc); mw.u8(sd); mw.fill(0, 1)

    mw.u16(p.get("offense", 100))
    mw.u16(p.get("defense", 100))
    mw.i32(p.get("money", 0))
    mw.u8(p.get("color_3", 0))
    mw.u8(p.get("color_2", 0))
    mw.u8(p.get("color_1", 0))

    mw.fixed_str(p.get("trn_name", ""), 13)
    mw.fixed_str(p.get("trn_desc", ""), 31)
    mw.fixed_str(p.get("trn_image", ""), 13)
    mw.f32(p.get("trn_rank_money", 0.0))
    mw.f32(p.get("trn_winnings_mult", 0.0))
    mw.fill(0, 40)

    mw.u8(p.get("pilot_id", 0))
    mw.u8(p.get("unknown_k", 0))
    mw.u16(p.get("force_arena", 0))
    mw.u8((p.get("difficulty", 0) & 0x3) << 3)
    mw.write(_from_b64(p, "unk_block_b", 2))
    mw.u8(p.get("movement", 0))
    mw.write(_from_b64(p, "unk_block_c", 6))
    mw.write(_from_b64(p, "enhancements", 11))

    mw.fill(0, 1)
    req_flags = (0x02 if p.get("secret") else 0) | (0x08 if p.get("only_fight_once") else 0)
    mw.u8(req_flags)
    mw.fill(0, 1)

    reqs = [0] * 5
    reqs[0] = ((p.get("req_max_rank", 0)   & 0xFF) << 8) | (p.get("req_rank", 0)   & 0xFF)
    reqs[1] =   p.get("req_fighter", 0)    & 0x1F
    reqs[2] = ((p.get("req_difficulty", 0) & 0x0F) << 8) | (p.get("req_enemy", 0)  & 0xFF)
    reqs[3] = ((p.get("req_accuracy", 0)   & 0x7F) << 7) | (p.get("req_vitality", 0) & 0x7F)
    reqs[4] = ((p.get("req_destroy", 0)    & 0x01) << 8) | ((p.get("req_scrap", 0) & 0x01) << 7) | (p.get("req_avg_dmg", 0) & 0x7F)
    for rv in reqs:
        mw.u16(rv)

    att = [0] * 3
    att[0] = (p.get("att_normal", 0) & 0x7F) << 4
    att[1] = ((p.get("att_jump",   0) & 0x7F) << 7) | (p.get("att_hyper", 0) & 0x7F)
    att[2] = ((p.get("att_sniper", 0) & 0x7F) << 7) | (p.get("att_def",   0) & 0x7F)
    for av in att:
        mw.u16(av)

    mw.write(_from_b64(p, "unk_block_d", 4))

    mw.i16(p.get("ap_close",   0)); mw.i16(p.get("ap_throw",  0))
    mw.i16(p.get("ap_special", 0)); mw.i16(p.get("ap_jump",   0))
    mw.i16(p.get("ap_high",    0)); mw.i16(p.get("ap_low",    0))
    mw.i16(p.get("ap_middle",  0))
    mw.i16(p.get("pref_jump",  0)); mw.i16(p.get("pref_fwd",  0)); mw.i16(p.get("pref_back", 0))

    mw.u32(p.get("unknown_e", 0))
    mw.f32(p.get("learning", 0.0))
    mw.f32(p.get("forget",   0.0))
    mw.i16(p.get("sound_1", 0)); mw.i16(p.get("sound_2", 0)); mw.i16(p.get("sound_3", 0))
    mw.write(_from_b64(p, "unk_block_f", 8))
    mw.u16(p.get("enemies_inc_unranked", 0))
    mw.u16(p.get("enemies_ex_unranked",  0))
    mw.u16(p.get("unk_d_a",    0))
    mw.u32(p.get("har_trades", 0))
    mw.u32(p.get("winnings",   0))
    mw.u32(p.get("total_value",0))
    mw.i16(p.get("current_health", 0))
    mw.i16(p.get("maximum_health", 0))
    mw.f32(p.get("unk_f_b", 0.0))
    mw.fill(0, 8)

    palette = p.get("palette_0_47", [[0, 0, 0]] * 48)
    _write_pal(mw, palette)

    mw.u16(p.get("is_player", 0))
    mw.u16(p.get("photo_id",  0) & 0x3FF)

    block = bytearray(mw.getvalue())
    assert len(block) == PILOT_BLOCK_LENGTH, f"pilot block {len(block)} != {PILOT_BLOCK_LENGTH}"
    key = PILOT_XOR_KEY
    for i in range(PILOT_BLOCK_LENGTH):
        block[i] ^= key
        key = (key + 1) & 0xFF
    w.write(bytes(block))

    for q in p.get("quotes", [""] * 10):
        w.var_str(q)


# ---------------------------------------------------------------------------
# TRN decode / encode
# ---------------------------------------------------------------------------

def decode_trn(path: str) -> dict:
    r = _Reader(Path(path).read_bytes())
    trn = {"filename": Path(path).name}

    enemy_count               = r.u16()
    trn["unknown_b"]          = r.u16()
    victory_text_offset       = r.u32()
    trn["bk_name"]            = r.fixed_str(14)
    trn["winnings_multiplier"]    = r.f32()
    trn["unknown_a"]          = r.i32()
    trn["registration_fee"]   = r.i32()
    trn["assumed_initial_value"] = r.i32()
    trn["tournament_id"]      = r.i32()

    r.seek(300)
    offsets = [r.u32() for _ in range(enemy_count + 1)]

    trn["enemies"] = []
    for i in range(enemy_count):
        r.seek(offsets[i])
        trn["enemies"].append(_decode_pilot(r))

    # Locale logos start right after the last pilot
    r.seek(offsets[enemy_count])
    logos = [_decode_sprite(r) for _ in range(10)]

    # TRN palette: 40 colors at VGA indices 128-167
    trn["palette_128_167"] = _read_pal(r, 40)
    trn["pic_file"] = r.var_str()

    locales = []
    for i in range(10):
        locales.append({
            "logo": logos[i],
            "title": r.var_str(),
            "description": r.var_str(),
            "end_texts": [],
        })

    if r.tell() != victory_text_offset:
        raise ValueError(
            f"Victory text offset mismatch: expected {victory_text_offset}, got {r.tell()}"
        )

    for i in range(10):
        end_texts = []
        for _ in range(11):   # one per HAR
            end_texts.append([r.var_str() for _ in range(10)])  # 10 pages each
        locales[i]["end_texts"] = end_texts

    trn["locales"] = locales
    return trn


def encode_trn(trn: dict) -> bytes:
    w = _Writer()
    enemies = trn.get("enemies", [])
    enemy_count = len(enemies)

    w.u16(enemy_count)
    w.u16(trn.get("unknown_b", 0))
    vt_offset_pos = w.tell()
    w.u32(0)   # victory_text_offset — patched later
    w.fixed_str(trn.get("bk_name", ""), 14)
    w.f32(trn.get("winnings_multiplier", 1.0))
    w.i32(trn.get("unknown_a", 0))
    w.i32(trn.get("registration_fee", 0))
    w.i32(trn.get("assumed_initial_value", 0))
    w.i32(trn.get("tournament_id", 0))

    # Pad to offset 300, then write offset table
    w.fill(0, 300 - w.tell())
    w.u32(1100)   # offset[0] = start of pilot data (always 1100)
    for _ in range(enemy_count):
        w.u32(0)  # offset[1..N] — patched after each pilot

    # Pad to offset 1100
    w.fill(0, 1100 - w.tell())

    # Write pilots; patch each next-offset into the table as we go
    for i, p in enumerate(enemies):
        _encode_pilot(w, p)
        w.patch_u32(300 + (i + 1) * 4, w.tell())

    # Locale logos (always 10)
    locales = list(trn.get("locales", []))
    _EMPTY_SPRITE = {"len": 0, "pos_x": 0, "pos_y": 0,
                     "width": 0, "height": 0, "index": 0, "missing": 1, "data_b64": ""}
    _EMPTY_LOCALE = {"logo": _EMPTY_SPRITE, "title": "", "description": "", "end_texts": []}
    while len(locales) < 10:
        locales.append(_EMPTY_LOCALE)

    for loc in locales:
        _encode_sprite(w, loc.get("logo", _EMPTY_SPRITE))

    # TRN palette
    _write_pal(w, trn.get("palette_128_167", [[0, 0, 0]] * 40))

    # PIC file + locale titles/descriptions
    w.var_str(trn.get("pic_file", ""))
    for loc in locales:
        w.var_str(loc.get("title", ""))
        w.var_str(loc.get("description", ""))

    # Patch victory text offset
    w.patch_u32(vt_offset_pos, w.tell())

    # Victory texts: 10 locales × 11 HARs × 10 pages
    for loc in locales:
        end_texts = loc.get("end_texts", [])
        for har in range(11):
            pages = end_texts[har] if har < len(end_texts) else []
            for page in range(10):
                w.var_str(pages[page] if page < len(pages) else "")

    return w.getvalue()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("decode", "encode"):
        print(__doc__)
        sys.exit(1)

    cmd, inp, out = sys.argv[1], sys.argv[2], sys.argv[3]

    if cmd == "decode":
        trn = decode_trn(inp)
        Path(out).write_text(json.dumps(trn, indent=2))
        print(f"decoded {inp} → {out}  ({len(trn['enemies'])} pilots)")
    else:
        trn = json.loads(Path(inp).read_text())
        data = encode_trn(trn)
        Path(out).write_bytes(data)
        print(f"encoded {inp} → {out}  ({len(data)} bytes)")


if __name__ == "__main__":
    main()
