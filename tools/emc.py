"""emc.py : EMC (rEnemyCmd, enemy AI bytecode) reader.  Same format/version in MH4U and MHGU ("EMC\\0", 0x20120804).

Layout (from em089_cmd): header 16 bytes (magic, version, ngroups, 0), then ngroups x {u32 count, u32 offset, 0, 0}.
Each group points at `count` script entries {u32 length, u32 offset, 0, 0}; a script is a byte string (padded to 16).
Group 0 = top-level AI selectors (em089: 33), group 1 = action scripts (em089: 146), groups 2.. = small extra lists.

Bytecode (partly inferred, NOT from the interpreter): `00 cat num` starts native action (category, number) handled by
the monster class (em089: vtable slot 44 dispatch on work bytes +0x1ca/+0x1cb); `14 nn` runs action script nn of
group 1; `02 00 / 02 01 w ... / 02 ff` = weighted random choice; ops like 6f/77/78/1d/0b/0c/2e/57 are condition
blocks with sub-codes 00 (if) / 01 v (case) / 02 (else) / ff (end).

  emc.py FILE              summary + every script as hex
  emc.py FILE refs         native-action (cat,num) and script references per script (heuristic tokenizer)
"""
import struct, sys, collections


def parse(d):
    assert d[:4] == b'EMC\0', 'not EMC'
    ver, ngroups = struct.unpack_from('<II', d, 4)
    groups = []
    for g in range(ngroups):
        cnt, off = struct.unpack_from('<II', d, 0x10 + 16 * g)
        scripts = []
        for i in range(cnt):
            ln, so = struct.unpack_from('<II', d, off + 16 * i)
            scripts.append(d[so:so + ln])
        groups.append(scripts)
    return ver, groups


def build(groups, ver=0x20120804):
    """[[script bytes] per group] -> EMC in the games' own layout (GU em067_00 / 4U em092 rebuild byte-identical):
    header, group rows {count, offset, 0, 0}, then per group its script table {length, offset, 0, 0} followed by its
    scripts, each padded to 16; an empty group points at the next table."""
    out = bytearray(struct.pack('<4sIII', b'EMC\0', ver, len(groups), 0)) + bytes(16 * len(groups))
    for g, scripts in enumerate(groups):
        tab = len(out)
        struct.pack_into('<II', out, 0x10 + 16 * g, len(scripts), tab)
        out += bytes(16 * len(scripts))
        for i, s in enumerate(scripts):
            struct.pack_into('<II', out, tab + 16 * i, len(s), len(out))
            out += s + bytes(-len(s) % 16)
    return bytes(out)


def to_gu(b):
    """4U EMC has 23 groups, GU 21; 4U's last two are empty. Keep every offset: rows 21-22 become padding."""
    magic, ver, ng, _ = struct.unpack_from('<4sIII', b, 0)
    assert magic == b'EMC\0' and ver == 0x20120804 and ng == 23
    for g in (21, 22):
        assert struct.unpack_from('<I', b, 16 + 16 * g)[0] == 0, 'group %d not empty' % g
    b = bytearray(b)
    struct.pack_into('<I', b, 8, 21)
    b[16 + 16 * 21:16 + 16 * 23] = bytes(32)
    return bytes(b)


# GU's instruction length table, main 0x1732c8c, 167 ops (C): byte < 0x80 = argument count; 0x8n..0xBn = block ops
# (00 opens with n args, 01 = case with a 1..4-byte value, 02 else, ff end). The arc builders cut scripts with it.
LEN_TABLE, LEN_COUNT = 0x1732c8c, 167


def tokens(s, lens):
    """a script's instructions, by GU's length table (an op past the table = the end, 0xff)"""
    out, i = [], 0
    while i < len(s):
        op = s[i]
        if op >= len(lens):
            out.append(s[i:]); break
        v = lens[op]
        n = 1 + v if v < 0x80 else 2 + (v & 0xf) if s[i + 1] == 0 else 2 + (v >> 4) - 7 if s[i + 1] == 1 else 2
        out.append(s[i:i + n]); i += n
    assert b''.join(out) == s, 'EMC script does not tokenize'
    return out


def em_only(s, em, lens, op=0x46):
    """the script with every switch block of `op` (4U 0x46 = em number, GU 0x91 / 0x92 = variant) reduced to em's
    body (its case, else the else body)"""
    out, frames = bytearray(), []                   # per open block: [taking, taken]
    for t in tokens(s, lens):
        if t[0] == op:
            if t[1] == 0x00: frames.append([False, False])
            elif t[1] == 0x01: frames[-1][0] = t[2] == em and not frames[-1][1]; frames[-1][1] |= frames[-1][0]
            elif t[1] == 0x02: frames[-1][0] = not frames[-1][1]; frames[-1][1] = True
            else: frames.pop()
            continue
        if all(f[0] for f in frames): out += t
    assert not frames, 'unbalanced switch block'
    return bytes(out)


def refs(code):
    """heuristic: `00 cat num` with cat < 14 at a token start, and `14 nn`."""
    nat, calls = [], []
    i = 0
    while i < len(code):
        b = code[i]
        if b == 0x00 and i + 2 < len(code) and code[i + 1] < 14:
            nat.append((code[i + 1], code[i + 2])); i += 3; continue
        if b == 0x14 and i + 1 < len(code):
            calls.append(code[i + 1]); i += 2; continue
        if b == 0x02 and i + 1 < len(code):
            i += 3 if code[i + 1] == 0x01 else 2; continue
        if i + 1 < len(code) and code[i + 1] in (0x00, 0x01):
            # generic block op: op sub arg [arg]
            i += 3; continue
        i += 2 if i + 1 < len(code) and code[i + 1] in (0x02, 0xff) else 1
    return nat, calls


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    ver, groups = parse(d)
    print('EMC version %08x, %d groups: %s' % (ver, len(groups), [len(g) for g in groups]))
    if sys.argv[2:] == ['refs']:
        allnat = collections.Counter()
        for gi, g in enumerate(groups):
            for si, s in enumerate(g):
                nat, calls = refs(s)
                allnat.update(nat)
                if nat or calls:
                    print('g%d s%-3d native %s  scripts %s' % (gi, si, ' '.join('%d:%d' % x for x in nat),
                                                               ' '.join(map(str, calls))))
        print('native actions referenced:', ' '.join('%d:%d' % k for k in sorted(allnat)))
    else:
        for gi, g in enumerate(groups):
            for si, s in enumerate(g):
                print('g%d s%-3d len %4d  %s' % (gi, si, len(s), s.hex(' ')))
