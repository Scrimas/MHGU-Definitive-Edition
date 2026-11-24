#!/usr/bin/env python3
"""window_matrix.py : the installer's window on small and scaled screens, under headless compositors. Linux only.

  python3 installer/tools/window_matrix.py OUT NAME=BINARY [NAME=BINARY ...] [--on kwin,hypr] [--cases 1920x1080@2]

Each NAME=BINARY is an installer build (installer/target/release/mhgu-de-installer; a .exe runs under Wine only). The
setups: kwin (KWin's virtual output), kwinx11 (the same, the installer through KWin's Xwayland), hypr (Hyprland nested
in a headless KWin), sway (wlroots headless), mutter (GNOME's, --headless), wine (the .exe on KWin's Xwayland, the
Windows DPI = scale x 96). A case is WxH@scale in physical pixels, 'r' at the end for a portrait panel shown landscape
(the Steam Deck's); --cases replaces each setup's own list. Per run, in OUT: <setup>~<name>~<case>.png (the installer's
own snapshot: the whole window, also what is off the screen), .log (the installer's output; WAYLAND_DEBUG on Wayland),
.q.txt (what Hyprland, sway or X11 report), then a table on stdout:

  screen  where the window may go (logical px): the compositor's bounds when it sends some, else the output
  window  what Hyprland, sway or X11 show, else the snapshot;  fits  inside the screen
  float   Hyprland's and sway's own answer;  rule  min == max at the first frame, what makes Hyprland float a window

Every run gets a throwaway HOME, the offline fake release of installer/tests/cli_test.py and a private D-Bus, and its
processes are killed afterwards (all that carry its CASE_OUT). Nothing reaches the running desktop: Hyprland's seat is
a libseat backend that does not exist (LIBSEAT_BACKEND), and its hyprctl answers only from the nested instance.

Needs on PATH, per setup (a setup whose programs are missing is skipped): dbus-run-session, kwin_wayland; xdotool
(kwinx11, wine); Hyprland 0.57+ (Lua config) and hyprctl; sway and swaymsg; mutter and gdctl; wine and wineboot. On
NixOS the installer finds its libraries through NIX_LD_LIBRARY_PATH (nix-ld), and `nix shell nixpkgs#sway
nixpkgs#mutter` brings the compositors this system lacks.
"""
import glob, json, os, re, shlex, shutil, signal, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SETUPS = {
    'kwin': '960x540@1 1366x768@1 1920x1080@1 1920x1080@1.25 1920x1080@2 1920x1200@2 1280x800@1.25 1280x800@1.5 '
            '1280x800@1.75 800x1280@1.5r 2560x1600@2 3840x2160@1.5',
    'kwinx11': '960x540@1 1920x1080@1 1920x1080@1.25 1920x1080@2 1280x800@1.5',
    'hypr': '960x540@1 1920x1080@1 1920x1080@1.25 1920x1080@2 1920x1200@2 1280x800@1.6 2560x1600@2',
    'sway': '960x540@1 1920x1080@1 1920x1080@1.25 1920x1080@2 1280x800@1.5 2560x1600@2',
    'mutter': '960x540@1 1366x768@1 1920x1080@1 1920x1080@2 2560x1600@2',
    'wine': '960x540@1 1920x1080@1 1920x1080@1.25 1920x1080@2 1280x800@1.5',
}
NEEDS = {'kwin': ['kwin_wayland'], 'kwinx11': ['kwin_wayland', 'xdotool'], 'hypr': ['kwin_wayland', 'Hyprland', 'hyprctl'],
         'sway': ['sway', 'swaymsg'], 'mutter': ['mutter', 'gdctl'],
         'wine': ['kwin_wayland', 'xdotool', 'wine', 'wineboot']}
KWIN = ['dbus-run-session', '--', 'kwin_wayland', '--virtual', '--no-lockscreen', '--no-global-shortcuts',
        '--no-kactivities']
# the desktop this runs in: none of it may reach a test session
DROP = ('WAYLAND_DISPLAY', 'DISPLAY', 'WAYLAND_SOCKET', 'HYPRLAND_INSTANCE_SIGNATURE', 'HYPRLAND_CMD', 'SWAYSOCK',
        'I3SOCK', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION', 'QT_QPA_PLATFORM', 'GDK_BACKEND',
        'SDL_VIDEODRIVER', 'NIXOS_OZONE_WL', 'XAUTHORITY', 'WINEPREFIX')
TITLE = 'MHGU Definitive Edition Installer'


def parse_case(c):
    wh, s = c.rstrip('r').split('@')
    w, h = map(int, wh.split('x'))
    return w, h, float(s), c.endswith('r')


def kwin_config(home, w, h, s, rot):
    """KWin's virtual output takes its scale from its stored config only (--scale multiplies the mode)"""
    out = {'connectorName': 'Virtual-0', 'scale': s, 'transform': 'Rotated270' if rot else 'Normal',
           'mode': {'basic': {'width': w, 'height': h, 'refreshRate': 60000}, 'flags': 1}}
    setup = {'lidClosed': False, 'outputs': [{'enabled': True, 'outputIndex': 0, 'position': {'x': 0, 'y': 0},
                                              'priority': 0, 'replicationSource': ''}]}
    json.dump([{'name': 'outputs', 'data': [out]}, {'name': 'setups', 'data': [setup]}],
              open(os.path.join(home, '.config', 'kwinoutputconfig.json'), 'w', encoding='utf-8'))


def kill_case(o):
    """every process started for this run (a compositor's session leaves the process group): CASE_OUT is in its env"""
    mark = ('CASE_OUT=' + o).encode()
    for sig in (signal.SIGTERM, signal.SIGKILL):
        found = False
        for pid in filter(str.isdigit, os.listdir('/proc')):
            try:
                if mark in open('/proc/%s/environ' % pid, 'rb').read().split(b'\0'):
                    os.kill(int(pid), sig)
                    found = True
            except OSError:
                pass
        if not found:
            return
        time.sleep(1)


def run(setup, name, binary, case, n, out, fixture):
    w, h, s, rot = parse_case(case)
    o = os.path.join(out, '%s~%s~%s' % (setup, name, case))
    for f in glob.glob(glob.escape(o) + '.*'):
        shutil.rmtree(f) if os.path.isdir(f) else os.remove(f)
    home = os.path.join(out, 'home')
    shutil.rmtree(home, ignore_errors=True)
    for d in ('.config/Ryujinx', '.local/share', '.cache'):    # Ryujinx: one place found, the list to install
        os.makedirs(os.path.join(home, d))
    os.makedirs(o + '.d')
    e = {k: v for k, v in os.environ.items() if k not in DROP}
    e.update(HOME=home, USER='tester', XDG_CONFIG_HOME=home + '/.config', XDG_DATA_HOME=home + '/.local/share',
             XDG_CACHE_HOME=home + '/.cache', CASE_ROLE='app', CASE_BIN=binary, CASE_OUT=o, CASE_SCALE='%g' % s,
             CASE_FIXTURE=fixture, REAL_SIG=os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', ''))
    me = [sys.executable, os.path.abspath(__file__), '--session']
    sock = 'wl-matrix-%d-%d' % (os.getpid(), n)
    if setup in ('kwin', 'kwinx11', 'wine'):
        kwin_config(home, w, h, s, rot)
        cmd = KWIN + ['--socket', sock, '--width', str(w), '--height', str(h)]
        if setup != 'kwin':
            cmd.append('--xwayland')
            e['CASE_X11'] = '1'
        if setup == 'wine':
            e.update(CASE_ROLE='wine', WINEPREFIX=os.path.join(out, 'wineprefix'))
        cmd += ['--exit-with-session', shlex.join(me)]
    elif setup == 'hypr':
        kwin_config(home, 3840, 2400, 1, False)    # the host: room for the nested Hyprland's window
        conf = o + '.d/hyprland.lua'
        open(conf, 'w', encoding='utf-8').write('\n'.join([
            'hl.monitor({ output = "WAYLAND-1", mode = "%dx%d@60", position = "0x0", scale = "%g" })' % (w, h, s),
            'hl.config({ misc = { disable_hyprland_logo = true, disable_splash_rendering = true,',
            '                     force_default_wallpaper = 0 }, animations = { enabled = false } })',
            'hl.on("hyprland.start", function()', '    hl.dispatch(hl.dsp.exec_cmd("%s"))' % shlex.join(me), 'end)', '']))
        e.update(CASE_HYPR=conf, LIBSEAT_BACKEND='none')    # no such backend: libseat opens no seat at all
        cmd = KWIN + ['--socket', sock, '--width', '3840', '--height', '2400', '--exit-with-session',
                      shlex.join(me + ['--hyprland'])]
    elif setup == 'sway':
        conf = o + '.d/sway.conf'
        open(conf, 'w', encoding='utf-8').write('output HEADLESS-1 mode --custom %dx%d scale %g%s\nxwayland disable\n'
                                                'exec %s\n' % (w, h, s, ' transform 270' if rot else '', shlex.join(me)))
        render = sorted(glob.glob('/dev/dri/renderD*'))
        e.update(WLR_BACKENDS='headless', WLR_LIBINPUT_NO_DEVICES='1', WLR_HEADLESS_OUTPUTS='1')
        if render:
            e['WLR_RENDER_DRM_DEVICE'] = render[0]
        cmd = ['dbus-run-session', '--', 'sway', '-c', conf]
    else:
        e['CASE_ROLE'] = 'mutter'
        cmd = ['dbus-run-session', '--', 'mutter', '--headless', '--wayland', '--no-x11', '--wayland-display', sock,
               '--virtual-monitor', '%dx%d' % (w, h), '--'] + me
    p = subprocess.Popen(cmd, env=e, stdout=open(o + '.session.log', 'w'), stderr=subprocess.STDOUT,
                         start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < 75 and not os.path.exists(o + '.done') and p.poll() is None:
        time.sleep(0.3)
    if not os.path.exists(o + '.done'):
        print('    %s: no result (session exit %s after %.0f s, see %s.session.log)'
              % (os.path.basename(o), p.poll(), time.time() - t0, o), flush=True)
    kill_case(o)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, sig)
            p.wait(5)
            break
        except ProcessLookupError:
            break
        except subprocess.TimeoutExpired:
            pass


def session():
    """inside a compositor: the installer, offline, its snapshot after 3 s (gui/src/main.rs), what the compositor
    reports at 2.2 s, then CASE_OUT.done"""
    if sys.argv[2:3] == ['--hyprland']:
        if not os.environ.get('WAYLAND_DISPLAY') or os.environ.get('LIBSEAT_BACKEND') != 'none':
            sys.exit('Hyprland runs only nested in the test KWin, without a seat')
        os.environ.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        os.execvp('Hyprland', ['Hyprland', '-c', os.environ['CASE_HYPR']])
    role, o, s = os.environ['CASE_ROLE'], os.environ['CASE_OUT'], os.environ['CASE_SCALE']
    fx = os.environ['CASE_FIXTURE']
    e = dict(os.environ, MHGU_DE_SNAPSHOT=o + '.png', MHGU_DE_RELEASES=fx + '/releases',
             MHGU_DE_INSTALLER_RELEASES=fx + '/installer-releases', MHGU_DE_CACHE=o + '.d/cache',
             MHGU_DE_CONFIG=o + '.d/config', MHGU_DE_BACKUPS=o + '.d/backups')
    q = open(o + '.q.txt', 'w')
    if role == 'mutter' and s != '1':
        show = subprocess.run(['gdctl', 'show'], capture_output=True, text=True).stdout
        mon = re.search(r'Monitor (\S+)', show)
        subprocess.run(['gdctl', 'set', '--logical-monitor', '--primary', '--monitor', mon.group(1) if mon else '',
                        '--scale', s], stdout=q, stderr=q)
    if os.environ.get('CASE_X11'):
        e.pop('WAYLAND_DISPLAY', None)
        e['WINIT_X11_SCALE_FACTOR'] = s
    else:
        e['WAYLAND_DEBUG'] = '1'
    cmd = [os.environ['CASE_BIN']]
    if role == 'wine':
        e.pop('WINIT_X11_SCALE_FACTOR')
        e.update(WINEDEBUG='-all', WINEDLLOVERRIDES='mscoree,mshtml=')    # no Mono / Gecko installer dialogs
        if not os.path.isdir(e['WINEPREFIX']):
            subprocess.run(['wineboot', '-i'], env=e, capture_output=True)
        subprocess.run(['wine', 'reg', 'add', r'HKCU\Control Panel\Desktop', '/v', 'LogPixels', '/t', 'REG_DWORD',
                        '/d', str(round(96 * float(s))), '/f'], env=e, capture_output=True)
        for k in ('MHGU_DE_SNAPSHOT', 'MHGU_DE_RELEASES', 'MHGU_DE_INSTALLER_RELEASES', 'MHGU_DE_CACHE',
                  'MHGU_DE_CONFIG', 'MHGU_DE_BACKUPS'):
            e[k] = 'Z:' + e[k].replace('/', '\\')    # Wine's Z: is /
        cmd = ['wine'] + cmd
    elif os.environ.get('NIX_LD_LIBRARY_PATH'):
        e['LD_LIBRARY_PATH'] = os.environ['NIX_LD_LIBRARY_PATH']    # NixOS: winit's dlopen'ed Wayland, EGL, fonts
    p = subprocess.Popen(cmd, env=e, stdout=open(o + '.log', 'w'), stderr=subprocess.STDOUT)
    time.sleep(2.2)
    if os.environ.get('CASE_X11'):
        q.write(subprocess.run(['xdotool', 'getdisplaygeometry'], capture_output=True, text=True).stdout)
        q.write(subprocess.run(['xdotool', 'search', '--name', TITLE, 'getwindowgeometry', '--shell'],
                               capture_output=True, text=True).stdout)
    elif os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', os.environ['REAL_SIG']) != os.environ['REAL_SIG']:
        q.write('\n===\n'.join(subprocess.run(['hyprctl', '-j', a], capture_output=True, text=True).stdout
                                for a in ('monitors', 'clients')))
    elif os.environ.get('SWAYSOCK'):
        q.write('\n===\n'.join(subprocess.run(['swaymsg', '-t', a], capture_output=True, text=True).stdout
                                for a in ('get_outputs', 'get_tree')))
    q.close()
    try:
        p.wait(60)
    except subprocess.TimeoutExpired:
        p.kill()
    open(o + '.done', 'w').close()


LINE = re.compile(r'(->)?\s*([a-z_0-9]+)[#@](\d+)\.(\w+)\((.*)\)\s*$')
OBJ = re.compile(r'([a-z_0-9]+)[#@](\d+)')


def ints(a):
    return [int(x) for x in re.findall(r'-?\d+', a)]


def wayland(log):
    """from WAYLAND_DEBUG: the compositor's bounds, the min / max size at the first frame, other output"""
    st = dict(surface=None, xdg=None, top=None, min=None, max=None, bounds=None, attach=False, at_map=None, other=[])
    for raw in open(log, errors='replace'):
        m = LINE.search(raw)
        if not m:
            if raw.strip() and not raw.startswith('['):
                st['other'].append(raw.strip())
            continue
        req, iface, oid, name, args = m.groups()
        if req and name == 'get_xdg_surface':
            objs = OBJ.findall(args)
            st['xdg'], st['surface'] = objs[0][1], objs[1][1]
        elif req and name == 'get_toplevel' and oid == st['xdg']:
            st['top'] = OBJ.findall(args)[0][1]
        elif iface == 'xdg_toplevel' and oid == st['top']:
            if req and name in ('set_min_size', 'set_max_size'):
                st[name[4:7]] = tuple(ints(args))
            elif not req and name == 'configure_bounds':
                st['bounds'] = tuple(ints(args))
        elif req and iface == 'wl_surface' and oid == st['surface']:
            if name == 'attach' and 'nil' not in args:
                st['attach'] = True
            elif name == 'commit' and st['attach'] and st['at_map'] is None:
                st['at_map'] = (st['min'], st['max'])
    return st


def row(base):
    setup, name, case = os.path.basename(base).split('~')
    w, h, s, rot = parse_case(case)
    scr = (max(w, h) / s, min(w, h) / s) if rot else (w / s, h / s)
    try:
        px = struct.unpack('>II', open(base + '.png', 'rb').read(24)[16:24])
        win = (px[0] / s, px[1] / s)
    except OSError:
        win = None
    q = open(base + '.q.txt', errors='replace').read() if os.path.exists(base + '.q.txt') else ''
    x11 = setup in ('kwinx11', 'wine')
    st = wayland(base + '.log') if not x11 else dict(bounds=None, at_map=None, other=[])
    scr, fl, fits, note = st['bounds'] or scr, '-', '-', ''

    def inside(at, size, area):
        return at[0] >= 0 and at[1] >= 0 and at[0] + size[0] <= area[0] + 0.5 and at[1] + size[1] <= area[1] + 0.5
    try:
        if x11:
            dw, dh = ints(q.splitlines()[0])
            g = dict(re.findall(r'(\w+)=(-?\d+)', q))
            at, size = (int(g['X']), int(g['Y'])), (int(g['WIDTH']), int(g['HEIGHT']))
            scr, win = (dw / s, dh / s), (size[0] / s, size[1] / s)
            fits, note = 'yes' if inside(at, size, (dw, dh)) else 'NO', 'at %d,%d px' % at
        elif setup == 'hypr':
            mons, cls = (json.loads(x) for x in q.split('==='))
            m, c = mons[0], [c for c in cls if TITLE in c['title']][0]
            r = m['reserved']
            scr = (m['width'] / m['scale'] - r[0] - r[2], m['height'] / m['scale'] - r[1] - r[3])
            win, fl = tuple(c['size']), 'yes' if c['floating'] else 'TILED'
            at = (c['at'][0] - m['x'] - r[0], c['at'][1] - m['y'] - r[1])
            fits, note = 'yes' if inside(at, win, scr) else 'NO', 'at %d,%d' % tuple(c['at'])
        elif setup == 'sway':
            outs, tree = (json.loads(x) for x in q.split('==='))
            found = []

            def walk(node, floating):
                if node.get('type') in ('con', 'floating_con') and TITLE in (node.get('name') or ''):
                    found.append((node, floating))
                for k in node.get('nodes', []):
                    walk(k, floating)
                for k in node.get('floating_nodes', []):
                    walk(k, True)
            walk(tree, False)
            (node, floating), orr = found[0], outs[0]['rect']
            r, deco = node['rect'], node.get('deco_rect') or {}
            scr, win, fl = (orr['width'], orr['height']), (r['width'], r['height']), 'yes' if floating else 'TILED'
            # a floating window's title bar (deco_rect, on the screen's coordinates) is part of it
            top = min(r['y'], deco['y']) if floating and deco.get('height') else r['y']
            at = (r['x'] - orr['x'], top - orr['y'])
            fits = 'yes' if inside(at, (win[0], r['y'] + r['height'] - top), scr) else 'NO'
            note = 'at %d,%d with its title bar' % at
        elif win:
            fits = 'yes' if win[0] <= scr[0] + 0.5 and win[1] <= scr[1] + 0.5 else 'NO'
    except (ValueError, IndexError, KeyError) as err:    # a run without a window: the row says so
        note = 'no state (%s)' % err
    mn, mx = st['at_map'] or (None, None)
    fixed = bool(mn and mx and mn[0] > 1 and mn[1] > 1 and (mn[0] == mx[0] or mn[1] == mx[1]))
    rule = '-' if x11 else ('fixed' if fixed else 'NOT fixed')
    fmt = lambda t: 'x'.join('%g' % round(x) for x in t) if t else '-'
    return setup, case, name, fmt(scr), fmt(win), fits, fl, rule, (note + ' ' + ' | '.join(st['other'][:2]))[:100]


def main():
    if sys.argv[1:2] == ['--session']:
        return session()
    args, on, cases = sys.argv[1:], list(SETUPS), None
    for opt in ('--on', '--cases'):
        if opt in args:
            i = args.index(opt)
            val = args[i + 1].split(',')
            del args[i:i + 2]
            on, cases = (val, cases) if opt == '--on' else (on, val)
    if len(args) < 2 or any('=' not in a for a in args[1:]) or set(on) - set(SETUPS):
        sys.exit(__doc__)
    out, builds = os.path.abspath(args[0]), [a.split('=', 1) for a in args[1:]]
    for name, binary in builds:
        if not os.path.isfile(binary):
            sys.exit('%s: no such installer build: %s' % (name, binary))
    os.makedirs(out, exist_ok=True)
    fixture = os.path.join(out, 'fixture')
    if not os.path.isdir(fixture):
        sys.path.insert(0, os.path.join(HERE, '..', 'tests'))
        from cli_test import make_release, publish
        os.makedirs(os.path.join(fixture, 'releases'))
        os.makedirs(os.path.join(fixture, 'installer-releases'))
        # 2.0.0: the first release the installer takes, so the window shows a list to install
        publish(os.path.join(fixture, 'releases'), [make_release(os.path.join(fixture, 'releases'), 'v2.0.0', '2.0.0')])
        json.dump([dict(tag_name='v0.0.0', prerelease=False, draft=False, html_url='', published_at='', assets=[])],
                  open(os.path.join(fixture, 'installer-releases', 'releases.json'), 'w', encoding='utf-8'))
    n = 0
    for setup in on:
        missing = [p for p in ['dbus-run-session'] + NEEDS[setup] if not shutil.which(p)]
        runs = [(nm, b) for nm, b in builds if b.lower().endswith('.exe') == (setup == 'wine')]
        if missing or not runs:
            print('%s: skipped (%s)' % (setup, 'missing ' + ', '.join(missing) if missing else 'no build for it'))
            continue
        for name, binary in runs:
            for case in cases or SETUPS[setup].split():
                n += 1
                print('[%d] %s %s %s' % (n, setup, name, case), flush=True)
                run(setup, name, os.path.abspath(binary), case, n, out, fixture)
    rows = [row(f[:-5]) for f in sorted(glob.glob(os.path.join(out, '*~*~*.done')))]
    hdr = ('setup', 'output', 'build', 'screen', 'window', 'fits', 'float', 'rule', 'note')
    rows.sort(key=lambda r: (r[0], int(r[1].split('x')[0]), r[1], r[2]))
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))]
    for r in [hdr] + rows:
        print('  '.join(str(r[i]).ljust(w[i]) for i in range(len(hdr))).rstrip())


main()
