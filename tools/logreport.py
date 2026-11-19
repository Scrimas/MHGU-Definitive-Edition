"""logreport.py : summary of a Ryujinx log of any port's test session, so the tester only has to play and close.

usage: python3 tools/logreport.py [LOG] [--port PREFIX]    (default: the newest ~/.config/Ryujinx/Logs/*.log)

The mod's lines come through `KernelSvc OutputDebugString: <prefix>: ...`. The prefixes and the action-start formats
are read from the source (logf("<prefix>: ...") in module/ and monsters/*/module/, struct port_bgm's first field), so
a log of an older build can hold prefixes or formats the source no longer has: those prefixes are listed with their
counts, and --port PREFIX summarizes any prefix (its action starts only where the current formats match).
Reports: session end (the last line's time), the crash block (raw lines from the first Unhandled exception /
InvalidAccessHandler), the top |E| errors (gogreport's NOISE left out), the installed cheats (the maintainer's cheats
can fake bugs), the core (mhgu-de:) lines by first word (two when it is an em tag) with its key lines (data, installs,
quests, spawns, errors) and the file IDs served per monster (tzreport's check), then per port prefix: lines by first word,
action starts per monster (a start format names the monster in up to two words, then `action C/N`, and logs a motion),
`motion ffff` lines (absent motion, porting guide), and the longest gaps between one monster's consecutive action
starts inside one quest (quest_prep quest to the next): frozen-AI candidates only, as a sleep, a long action or a
hunter away from the monster also makes a gap; a port that stops logging (line cap) makes none. Monster-specific
reports stay in monsters/<name>/tools/ (gogreport.py, tzreport.py).
"""
import argparse, collections, glob, os, re, sys

import paths
sys.path.insert(0, os.path.join(paths.monster('gogmazios'), 'tools'))
from gogreport import NOISE  # noqa: E402

LOGS = os.path.join(os.path.expanduser('~'), '.config', 'Ryujinx', 'Logs', '*.log')
CORE = 'mhgu-de'
DEBUG = 'KernelSvc OutputDebugString: '
CRASH = ('Unhandled exception', 'InvalidAccessHandler')
CRASH_LINES = 40
TS = re.compile(r'^(\d+):(\d\d):(\d\d(?:\.\d+)?) ')
LOGF = re.compile(r'\blogf\(\s*"((?:[^"\\]|\\.)*)"')
BGM = re.compile(r'struct port_bgm\s+\w+\s*=\s*\{\s*"([^"]+)"')
PLACEHOLDER = {'%s': r'\S+', '%x': '[0-9a-f]+', '%u': r'\d+', '%d': r'-?\d+'}
CORE_KEY = re.compile(r'module_init|\bdata\b|installed|NOT present|quest_prep quest|em_create|quest-end tally|hunt-all|'
                      r'NOT relocated|ERROR|failed|could not|damaged|refused|not merged|unreadable')
GAPS = 3


def source_formats():
    """({prefix}, {prefix: [regex of an action-start body]}) from the module source the build compiles"""
    files = glob.glob(os.path.join(paths.ROOT, 'module', '*.[ch]'))
    files += glob.glob(os.path.join(paths.ROOT, 'monsters', '*', 'module', '*.[ch]'))
    prefixes, starts = set(), collections.defaultdict(list)
    for f in sorted(files):
        src = open(f, encoding='utf-8', errors='replace').read()
        prefixes.update(BGM.findall(src))
        for s in LOGF.findall(src):
            p = re.match(r'([A-Za-z0-9_-]+): ', s)
            if not p: continue
            prefixes.add(p.group(1))
            # a start line: the monster in up to two words, its action, and a motion logged with it
            m = re.match(r'((?:\S+ ){0,2})action %u/%u\b(.*)', s[p.end():])
            if m and 'motion %x' in m.group(2):
                tag = ''.join(PLACEHOLDER.get(t, re.escape(t)) for t in re.split(r'(%[sxud])', m.group(1)))
                rx = re.compile(r'(%s)action (\d+)/(\d+)\b' % tag)
                if rx.pattern not in [r.pattern for r in starts[p.group(1)]]: starts[p.group(1)].append(rx)
    return prefixes, starts


def seconds(line):
    m = TS.match(line)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def first_word(body):
    w = body.split()
    if not w: return '(empty)'
    return ' '.join(w[:2]) if re.fullmatch(r'em\d{3}(_\d{2})?', w[0]) and len(w) > 1 else w[0]


def counts(c, n=15):
    return ', '.join('%s x%d' % kv for kv in c.most_common(n)) + (' (+%d more)' % (len(c) - n) if len(c) > n else '')


def main():
    ap = argparse.ArgumentParser(description='Summary of a Ryujinx log of a port test session.')
    ap.add_argument('log', nargs='?', help='the log (default: the newest in ~/.config/Ryujinx/Logs)')
    ap.add_argument('--port', help='only this prefix (any prefix, also one the source no longer logs)')
    a = ap.parse_args()
    path = a.log or max(glob.glob(LOGS), key=os.path.getmtime, default=None)
    if not path or not os.path.isfile(path): sys.exit('logreport: no log %s' % (path or LOGS))
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    prefixes, starts = source_formats()

    dbg = []   # (line index, seconds, timestamp text, prefix, body)
    for i, l in enumerate(lines):
        k = l.find(DEBUG)
        m = re.match(r'([A-Za-z0-9_-]+): (.*)', l[k + len(DEBUG):]) if k >= 0 else None
        if m: dbg.append((i, seconds(l), l[:12], m.group(1), m.group(2)))
    by = collections.defaultdict(list)
    for d in dbg: by[d[3]].append(d)

    print('log:', path)
    end = next((l for l in reversed(lines) if TS.match(l)), '')
    print('session end %s (the last line), %d lines, %d debug lines with a prefix' % (end[:12] or '?', len(lines), len(dbg)))
    crash = [i for i, l in enumerate(lines) if any(c in l for c in CRASH)]
    if crash:
        print('\nCRASH: %d marker line(s); up to %d raw lines from the first (line %d):' % (
            len(crash), CRASH_LINES, crash[0] + 1))
        for l in lines[crash[0]:crash[0] + CRASH_LINES]: print('  | ' + l)
    else:
        print('crash: none (no %s line)' % ' / '.join(CRASH))
    errors = collections.Counter(re.sub(r'0x[0-9a-f]+', 'X', l[13:].strip())[:120]
                                 for l in lines if '|E|' in l and not any(n in l for n in NOISE))
    print('errors (|E|, not %s): %d' % (' / '.join(NOISE), sum(errors.values())))
    for e, n in errors.most_common(5): print('  x%d %s' % (n, e))
    cheats = re.findall(r"Installing cheat '<?(.*?)>?'$", '\n'.join(l for l in lines if 'Installing cheat' in l), re.M)
    print('cheats installed: %d%s' % (len(cheats), (': ' + '; '.join(cheats)) if cheats else ''))

    # quest windows from the core's quest_prep line under any prefix: an older core logged it under another one
    quests = [d for d in dbg if d[4].startswith('quest_prep quest ')]
    print('quest windows: %d (quest_prep quest lines%s)' % (len(quests), ', prefix ' + ' / '.join(
        sorted({d[3] for d in quests})) if quests else ': none, so no gaps between action starts'))
    if a.port is None:
        core = by.get(CORE, [])
        print('\ncore (%s:): %d lines%s' % (CORE, len(core), '; by first word: ' + counts(collections.Counter(
            first_word(d[4]) for d in core), 25) if core else ''))
        key = collections.OrderedDict()
        for d in core:
            if CORE_KEY.search(d[4]): key.setdefault(d[4], []).append(d[2])
        for body, ts in key.items():
            print('  %s %s%s' % (ts[0], body, ' (x%d)' % len(ts) if len(ts) > 1 else ''))
        files = collections.Counter(); empty = collections.Counter()
        for d in core:
            m = re.match(r'(\S+) file [0-9a-f]+ \(hash .*-> (\S+) lr=', d[4])
            if m:
                files[m.group(1)] += 1; empty[m.group(1)] += m.group(2) == '0'
        for n in files:
            print('  %s: %d file IDs served, %d returned no resource' % (n, files[n], empty[n]))
        other = sorted(p for p in by if p not in prefixes and p != CORE)
        if other:
            print('prefixes the current source does not log (an older build? --port to see one): %s' % ', '.join(
                '%s x%d' % (p, len(by[p])) for p in other))

    for p in [a.port] if a.port else sorted((p for p in prefixes if p != CORE), key=lambda p: -len(by.get(p, []))):
        ls = by.get(p, [])
        if not ls:
            if a.port: print('\n%s: no line in this log' % p)
            continue
        print('\n%s: %d lines; by first word: %s' % (p, len(ls), counts(collections.Counter(first_word(d[4]) for d in ls))))
        win = lambda j: sum(q[0] < ls[j][0] for q in quests)
        acts = collections.defaultdict(list)   # monster -> [(index in ls, seconds, ts, (c, n))]
        for j, d in enumerate(ls):
            for rx in starts.get(p, []):
                m = rx.match(d[4])
                if m:
                    acts[m.group(1).strip() or p].append((j, d[1], d[2], (int(m.group(2)), int(m.group(3)))))
                    break
        if starts.get(p) and not acts:
            print('  action starts: none matched the source\'s formats (%s)' % '; '.join(r.pattern for r in starts[p]))
        for mon, st in acts.items():
            c = collections.Counter(x[3] for x in st)
            print('  %s: %d action starts, %d distinct, %s .. %s, last %d/%d' % (mon, len(st), len(c), st[0][2], st[-1][2],
                                                                             *st[-1][3]))
            print('    ' + ' '.join('%d/%d x%d' % (k[0], k[1], c[k]) for k in sorted(c)))
            # gaps: consecutive starts of one monster inside one quest window (window 0 = before any quest)
            gaps = sorted(((y[1] - x[1], x, y) for x, y in zip(st, st[1:])
                           if x[1] is not None and y[1] is not None and win(x[0]) and win(x[0]) == win(y[0])),
                          key=lambda g: -g[0])
            for g, x, y in gaps[:GAPS]:
                print('    gap %.1f s after %d/%d at %s (next start %d/%d at %s, %d %s lines between): frozen-AI candidate'
                      % (g, *x[3], x[2], *y[3], y[2], y[0] - x[0] - 1, p))
        absent = [d for d in ls if re.search(r'\bmotion ffff\b', d[4])]
        if starts.get(p) or absent:
            print('  motion ffff (absent motion): %d line(s)%s' % (len(absent), ':' if absent else ''))
        for d in absent[:8]: print('    %s %s' % (d[2], d[4][:150]))


if __name__ == '__main__':
    main()
