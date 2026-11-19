"""sym.py : name GU or MH4U code addresses from what the repo knows (no Ghidra needed).

  sym.py gu ADDR...    GU main offsets: 0xaff40, aff40 or main+0xaff40
  sym.py 4u ADDR...    MH4U v1.1 addresses (0x100000..)
Per address: the instruction there, the containing function's start and the offset in it, the repo's names for the
address and for that start, and the vtable slots holding the start.
- Names: the lists tools/ghidra_names.py collect writes (built here in memory, nothing written): `name` rows are the
  facts it calls confirmed (module/game.h defines unless rated S / W / guess, other files' defines marked (C), 4U
  names of notes/api-map.md C pairs, vtable slot names <class>_vt<N>, ctors); `comment` rows are everything else
  (unrated defines, hook sites, shared vtable slots). Also: every notes/api-map.md row naming the address, with its
  rating, and module/game.h's `[0x...]` 4U brackets (comments: on the define line, or in the comment right above
  when that comment names the define).
- Function start: the nearest known start (GU asm.func_start: call targets and code pointers in data; 4U call
  targets and vtable slot functions), unless the push walk-back (GU asm.func_start_push, 4U dis4u.func_bounds: the
  4U Ghidra project's seeds) finds a push {.., lr} after it that no branch of the code before reaches: a function
  only a jump table or a computed pointer reaches (GU's action handlers). A heuristic: a function without a push
  that the call graph misses, or a false known start (asm.starts takes every code pointer in data), misplaces it.
- Vtables: GU every vtable word holding the start (gulib/vt.py; class names from ghidra_names' monster vtables, other
  vtables unnamed); 4U the monster class vtable slots holding it, and a count of the other data words equal to it.
An empty list means the repo names nothing there, not that nothing is known about it.
"""
import bisect, collections, os, re, sys

import numpy as np

import paths
sys.path.insert(0, paths.GU_PY)
import asm, vt  # noqa: E402
import a4u, dis4u, ghidra_names as gn  # noqa: E402

GU_TEXT_END = vt.TEXT_END


def parse_addr(game, s):
    t = s.lower()
    if t.startswith('main+'):
        if game != 'gu': sys.exit('sym: %s: main+ is a GU main offset' % s)
        t = t[5:]
    try:
        a = int(t, 16)
    except ValueError:
        sys.exit('sym: %r is not an address (0x..., hex or main+0x...)' % s)
    lo, hi = (0, len(vt.IMG)) if game == 'gu' else (a4u.B, a4u.B + len(a4u.M))   # GU: bss included
    if not lo <= a < hi: sys.exit('sym: %s is outside %s (%#x..%#x)' % (s, 'GU main' if game == 'gu' else '4U', lo, hi))
    return a


_K = None


def knowledge():
    """{'gu' / '4u': {address: [(kind, text, sources)]}, 'report': ghidra_names' report lines, 'vtables': {game:
    {vtable address: class}}}: the rows ghidra_names.collect() writes (ghidra_names.rows, merged)"""
    global _K
    if _K is None:
        report = []
        R = gn.rows(report)
        _K = {'report': report, 'vtables': {}}
        for game, rows in (('gu', gn.merge(R['gu'], report, 'gu')), ('4u', gn.merge(R['mh4u'], report, 'mh4u'))):
            by = collections.defaultdict(list)
            for k, a, t, src in rows:
                by[a].append((k, t, src))
            _K[game] = by
            _K['vtables'][game] = {a: t[:-len('_vtable')] for k, a, t, _ in rows
                                   if k == 'label' and t.endswith('_vtable') and not t.endswith('_dti_vtable')}
    return _K


def game_h_brackets():
    """[(GU address, 4U address, define name)] from module/game.h's `[0x...]` 4U brackets (comment level)"""
    fn = re.compile(r'#define\s+([A-Za-z_]\w*)\b[^\n]*?\bFN\(.*?,\s*(0x[0-9a-fA-F]+)\)')
    br = re.compile(r'\[(?:4U )?(0x[0-9a-f]+)\]')
    out, comment = [], []
    for line in open(os.path.join(paths.ROOT, 'module', 'game.h'), encoding='utf-8'):
        m = fn.search(line); s = line.strip()
        if m:
            name, b = m.group(1), br.findall(line)
            if not b:   # a comment above may describe several defines: only one that names this define counts
                text = ' '.join(comment); b = br.findall(text)
                if len(b) != 1 or not re.search(r'\b%s\b' % name, text): b = []
            for x in b[:1]:
                if a4u.B <= int(x, 16) < a4u.TEXT_END: out.append((int(m.group(2), 16), int(x, 16), name))
            comment = []
        elif s.startswith(('/*', '*', '//', 'typedef')): comment.append(s)
        else: comment = []
    return out


def ins(game, a):
    return asm.INS.get(a, ('?', '')) if game == 'gu' else dis4u.INS(a)


_U4_STARTS = None


def u4_known_starts():
    """sorted 4U call targets (bl) and vtable slot functions: certain function starts"""
    global _U4_STARTS
    if _U4_STARTS is None:
        w = np.frombuffer(a4u.M, dtype='<u4', count=(a4u.TEXT_END - a4u.B) // 4)
        i = np.nonzero(((w & 0x0F000000) == 0x0B000000) & ((w >> 28) != 0xF))[0]
        off = (w[i] & 0xFFFFFF).astype(np.int64)
        off[off >= 0x800000] -= 0x1000000
        t = a4u.B + i.astype(np.int64) * 4 + 8 + off * 4
        s = set(int(x) for x in t[(t >= a4u.B) & (t < a4u.TEXT_END)])
        s |= {a for a, rs in knowledge()['4u'].items() if any(k == 'entry' for k, _, _ in rs)}
        _U4_STARTS = sorted(s)
    return _U4_STARTS


def ends_flow(w):
    """an unconditional ARM instruction after which execution never falls through: b, bx, ldm / pop with pc,
    ldr pc, mov pc, lr"""
    if w >> 28 != 0xE: return False
    return ((w & 0x0F000000) == 0x0A000000 or (w & 0x0FFFFFF0) == 0x012FFF10 or (w & 0x0E108000) == 0x08108000
            or (w & 0x0C50F000) == 0x0410F000 or w == 0xE1A0F00E)


def func_start(game, a):
    """(start, how it was found) of the function containing code address a"""
    if game == 'gu':
        k, p = asm.func_start(a), asm.func_start_push(a)
        st = asm.starts(); i = bisect.bisect_left(st, k)
        how = 'call target / code pointer, asm.starts' if i < len(st) and st[i] == k else 'push {.., lr} walk-back'
        word = asm.u32
    else:
        p = dis4u.func_bounds(a)
        st = u4_known_starts(); i = bisect.bisect_right(st, a) - 1
        k, how = (st[i], 'call target / vtable slot function') if i >= 0 else (p, 'push {.., lr} walk-back')
        word = a4u.u
    m, o = ins(game, p)
    if k < p <= a and (m == 'push' and 'lr' in o or m == 'str' and o.startswith('lr, [sp, #-')):
        # a push the code before it never branches past opens a function only a jump table / pointer reaches;
        # one it does branch to is a late (shrink-wrapped) prologue of the same function. Literal pool words (read
        # by ldr / vldr [pc]) are data, whatever they decode to; a b right after lr is popped is a tail call.
        lits = set()
        for x in range(k, p, 4):
            w = word(x)
            if (w & 0x0F7F0000) == 0x051F0000:
                lits.add(x + 8 + ((w & 0xFFF) if w & 0x00800000 else -(w & 0xFFF)))
            elif (w & 0x0F3F0E00) == 0x0D1F0A00:
                y = x + 8 + 4 * ((w & 0xFF) if w & 0x00800000 else -(w & 0xFF))
                lits.update((y, y + 4))
        # code that runs into the push (no unconditional return / branch before it, past literals and zero padding)
        # makes it a late prologue too
        x = p - 4
        while x >= k and (x in lits or word(x) == 0): x -= 4
        if x < k or not ends_flow(word(x)):
            return k, '%s; the push {.., lr} at %#x follows code that runs into it (%#x): same function' % (how, p, x)
        for x in range(k, p, 4):
            w = word(x)
            pw = word(x - 4)
            tail = (w & 0xFF000000) == 0xEA000000 and (
                (pw & 0x0E1FC000) == 0x081D4000 or pw == 0xE49DE004)    # ldm sp, {.., lr} / ldr lr, [sp], #4
            if x not in lits and not tail and (w >> 28) != 0xF and (w & 0x0E000000) == 0x0A000000:
                off = w & 0xFFFFFF
                if p <= x + 8 + 4 * (off - 0x1000000 if off & 0x800000 else off) <= a:
                    return k, '%s; the push {.., lr} at %#x is reached by the branch at %#x: same function' % (how, p, x)
        return p, 'push {.., lr} walk-back: no branch from %#x (%s) reaches it' % (k, how)
    return k, how


def table_only_starts():
    """GU functions asm.starts() misses: a push {.., lr} that func_start takes as its own start (reached only through
    a jump table or pointer); ghidra_names seeds them"""
    known = set(asm.starts())
    return sorted(a for a, (m, o) in asm.INS.items()
                  if m == 'push' and 'lr' in o and a not in known and func_start('gu', a)[0] == a)


def vtable_slots(game, f):
    """['class slot N (word at X)'] for every vtable / data word holding function f"""
    names = knowledge()['vtables'][game]
    out = []
    if game == 'gu':
        for i, idx, _ in vt.holders(f):
            head = i - 4 * idx
            out.append('%s slot %d (word %#x)' % (names[head], idx, i) if head in names else
                       'unnamed vtable %#x slot %d (word %#x; head by walk-back)' % (head, idx, i))
        return out
    w = np.frombuffer(a4u.M, dtype='<u4')
    heads = sorted(names)
    other = 0      # 4U words are absolute, so a plain number can equal the address too: counted, not listed
    for k in np.nonzero(w == f)[0]:
        x = a4u.B + 4 * int(k)
        if x < a4u.TEXT_END: continue
        j = bisect.bisect_right(heads, x) - 1
        if j >= 0 and x < heads[j] + 4 * gn.U4_SLOTS:
            out.append('%s slot %d (word %#x)' % (names[heads[j]], (x - heads[j]) // 4, x))
        else:
            other += 1
    if other: out.append('%d other data word(s) equal %#x (pointers or plain numbers, not in a monster vtable)' % (other, f))
    return out


def names_at(game, a):
    """['name|comment|dropped: text [sources]'] the repo gives address a"""
    K = knowledge(); out = []
    for k, t, src in K[game].get(a, []):
        if k == 'entry': continue
        out.append('%-7s %s  [%s]' % ('name' if k in ('func', 'label') else 'comment', t, ','.join(src)))
    tag = ('gu define', 'gu name') if game == 'gu' else ('mh4u name',)
    for r in K['report']:
        if r.startswith(tag) and 'dropped' in r and re.search(r'\b%#x\b' % a, r):
            out.append('dropped %s (ghidra_names: one name at several addresses)' % r.split(': ', 1)[1].split()[0])
    side = 1 if game == 'gu' else 0
    for u4, gu, conf, cells in gn.api_rows():
        mine, other = (gu, u4) if game == 'gu' else (u4, gu)
        if '%#x' % a in mine:
            k = mine.index('%#x' % a)
            pair = other[k] if len(mine) == len(other) else '/'.join(other) or '-'
            out.append('api-map %s: %s %#x <-> %s %s | %s' % (conf, 'GU' if side else '4U', a, '4U' if side else 'GU',
                                                              pair, cells[4][:90]))
    for g, x, name in game_h_brackets():
        if (g if game == 'gu' else x) == a:
            out.append('comment game.h bracket: GU %s %#x <-> 4U %#x' % (name, g, x))
    return out


def describe(game, a):
    m, o = ins(game, a)
    lines = ['%s %#x: %s %s' % (game, a, m, o)]
    code = a < (GU_TEXT_END if game == 'gu' else a4u.TEXT_END) and (game == 'gu' or a >= a4u.B)
    if not code:
        lines.append('  data address: no function')
        lines += ['  ' + n for n in names_at(game, a)] or ['  names: none in the repo']
        return lines
    s, how = func_start(game, a)
    lines.append('  function %#x +%#x (%s)' % (s, a - s, how))
    here = names_at(game, a)
    lines += ['  ' + n for n in here]
    if s != a:
        at = names_at(game, s)
        lines += ['  at the start %#x: %s' % (s, n) for n in at]
        if not here and not at: lines.append('  names: none in the repo')
    elif not here:
        lines.append('  names: none in the repo')
    lines += ['  vtable: ' + v for v in vtable_slots(game, s)] or ['  vtable: none holds %#x' % s]
    return lines


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] not in ('gu', '4u'):
        sys.exit(__doc__)
    g = sys.argv[1]
    addrs = [parse_addr(g, x) for x in sys.argv[2:]]
    for x in addrs:
        print('\n'.join(describe(g, x)))
