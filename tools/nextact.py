"""nextact.py : choose a monster's next AI action while the game runs (test aid; module/nextact.c, build switch
TEST_NEXT_ACTION).

Pause the game, pick the monster and the action here, unpause: the module swaps the monster's next AI pick for it (once).
The request is a one-line file on the emulator's SD card (<Ryujinx root>/sdcard/mhgu_de_next_action.txt); what the
monsters pick, and when a request applied, comes from the module's "nextact:" lines in the latest Ryujinx log. Action
lists and names: tools/actions.py (a port's monsters/<package>/actions.toml, GU's own from its AI table).

  nextact.py                          the GUI (Textual): monsters seen in the log, their actions, Enter = request
  nextact.py set 0x60d 7 74           write a request without the GUI
  options: --ryujinx DIR              the Ryujinx root (default: the parent of GOG_MOD_ROOT, else ~/.config/Ryujinx)
"""
import argparse, glob, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import actions   # noqa: E402

REQ_NAME = 'mhgu_de_next_action.txt'
PICK = re.compile(r'nextact: slot (-?\d+) em ([0-9a-f]+): AI pick (\d+)/(\d+)(?: -> (\d+)/(\d+) \(request (\d+)\))?')
CARD = re.compile(r'nextact: SD card (.*)$')


def ryujinx_root(arg):
    if arg: return os.path.expanduser(arg)
    mods = os.environ.get('GOG_MOD_ROOT')
    return os.path.dirname(os.path.abspath(os.path.expanduser(mods))) if mods else os.path.expanduser('~/.config/Ryujinx')


def write_request(root, em, cat, num):
    """the request file; returns its seq (seconds, so a new one never equals an old one)"""
    seq = int(time.time())
    card = os.path.join(root, 'sdcard')
    os.makedirs(card, exist_ok=True)
    with open(os.path.join(card, REQ_NAME), 'w', encoding='ascii', newline='\n') as f:
        f.write('seq=%d em=0x%x cat=%d num=%d\n' % (seq, em, cat, num))
    return seq


def monster_name(em):
    m = actions.entry_of(em)
    return m['name'] if m else 'GU ' + actions.arc_name(em)


def main_gui(root):
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

    class NextAct(App):
        TITLE = 'Next action'
        CSS = '#mons { width: 46; } #acts { width: 1fr; } #status { height: 3; } #events { height: 10; }'
        BINDINGS = [('q', 'quit', 'Quit'), ('/', 'focus_filter', 'Filter actions')]

        def __init__(self):
            super().__init__()
            self.log_path, self.log_pos = None, 0
            self.mons = {}            # em -> dict(slot, last, picks)
            self.sel = None
            self.pending = None       # (seq, em, cat, num)
            self.card = 'no "nextact:" line yet (module built without TEST_NEXT_ACTION, or no monster has picked)'
            self.acts = {}

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                yield DataTable(id='mons', cursor_type='row')
                with Vertical(id='acts'):
                    yield Input(placeholder='filter: name or cat/num', id='filter')
                    yield DataTable(id='actlist', cursor_type='row')
            yield Static(id='status')
            yield RichLog(id='events', max_lines=500)
            yield Footer()

        def on_mount(self):
            self.query_one('#mons', DataTable).add_columns('slot', 'em', 'monster', 'last pick', 'picks')
            self.query_one('#actlist', DataTable).add_columns('cat/num', 'name', 'needs', 'seen')
            self.set_interval(0.5, self.poll)
            self.poll()

        def action_focus_filter(self):
            self.query_one('#filter', Input).focus()

        def latest_log(self):
            logs = sorted(glob.glob(os.path.join(root, 'Logs', '*.log')), key=os.path.getmtime)
            return logs[-1] if logs else None

        def poll(self):
            path = self.latest_log()
            if path != self.log_path:
                self.log_path, self.log_pos, self.mons = path, 0, {}
                self.query_one('#events', RichLog).write('log: %s' % path)
            if path:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(self.log_pos)
                    for line in f:
                        self.feed(line)
                    self.log_pos = f.tell()
            self.redraw()

        def feed(self, line):
            m = CARD.search(line)
            if m:
                self.card = m.group(1)
                self.query_one('#events', RichLog).write('SD card ' + self.card)
                return
            m = PICK.search(line)
            if not m: return
            slot, em, cat, num = int(m.group(1)), int(m.group(2), 16), int(m.group(3)), int(m.group(4))
            d = self.mons.setdefault(em, dict(slot=slot, picks=0, seen=set()))
            d['slot'], d['picks'] = slot, d['picks'] + 1
            d['seen'].add((cat, num))
            if m.group(5):
                cat, num, seq = int(m.group(5)), int(m.group(6)), int(m.group(7))
                d['seen'].add((cat, num))
                self.query_one('#events', RichLog).write('slot %d %s: AI pick %s/%s -> %d/%d (request %d applied)'
                                                         % (slot, monster_name(em), m.group(3), m.group(4), cat, num, seq))
                if self.pending and self.pending[0] == seq: self.pending = None
            d['last'] = (cat, num)

        def redraw(self):
            t = self.query_one('#mons', DataTable)
            rows = sorted(self.mons.items(), key=lambda kv: kv[1]['slot'])
            if t.row_count != len(rows) or any(not t.is_valid_row_index(i) for i in range(len(rows))):
                t.clear()
                for em, d in rows:
                    t.add_row(str(d['slot']), '%x' % em, monster_name(em), '%d/%d' % d['last'], str(d['picks']),
                              key='%x' % em)
            else:
                for i, (em, d) in enumerate(rows):
                    t.update_cell_at((i, 3), '%d/%d' % d['last']); t.update_cell_at((i, 4), str(d['picks']))
            if self.sel is None and rows: self.select(rows[0][0])
            pend = ('waiting: %s %d/%d (request %d), applies at its next AI pick' % (
                monster_name(self.pending[1]), self.pending[2], self.pending[3], self.pending[0])
                if self.pending else 'no request waiting')
            self.query_one('#status', Static).update('SD card: %s\n%s\nEnter on an action = request it for the selected '
                                                     'monster (pause the game first)' % (self.card, pend))

        def select(self, em):
            self.sel = em
            if em not in self.acts:
                try:
                    pairs, names = actions.pairs(em), actions.names(em)
                except Exception as e:   # no arc / table for that ID: list only what the log showed
                    self.query_one('#events', RichLog).write('no AI table for %x (%s): seen pairs only' % (em, e))
                    pairs, names = [], {}
                self.acts[em] = (sorted(set(pairs) | set(names)), names)
            self.fill()

        def fill(self):
            t = self.query_one('#actlist', DataTable)
            t.clear()
            if self.sel is None: return
            pairs, names = self.acts[self.sel]
            seen = self.mons.get(self.sel, {}).get('seen', set())
            flt = self.query_one('#filter', Input).value.strip().lower()
            for p in sorted(set(pairs) | seen):
                a = names.get(p, {})
                label = '%d/%d' % p
                if flt and flt not in label and flt not in a.get('name', '').lower(): continue
                t.add_row(label, a.get('name', ''), a.get('needs', ''), 'yes' if p in seen else '', key=label)

        def on_input_changed(self, event):
            self.fill()

        def on_data_table_row_highlighted(self, event):
            if event.data_table.id == 'mons' and event.row_key is not None:
                em = int(event.row_key.value, 16)
                if em != self.sel: self.select(em)

        def on_data_table_row_selected(self, event):
            if event.data_table.id != 'actlist' or self.sel is None: return
            cat, num = map(int, event.row_key.value.split('/'))
            seq = write_request(root, self.sel, cat, num)
            self.pending = (seq, self.sel, cat, num)
            self.query_one('#events', RichLog).write('request %d: %s %d/%d written' % (seq, monster_name(self.sel),
                                                                                        cat, num))
            self.redraw()

    NextAct().run()


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--ryujinx')
    ap.add_argument('cmd', nargs='*')
    a = ap.parse_args(argv)
    root = ryujinx_root(a.ryujinx)
    if a.cmd[:1] == ['set'] and len(a.cmd) == 4:
        em, cat, num = int(a.cmd[1], 0), int(a.cmd[2], 0), int(a.cmd[3], 0)
        seq = write_request(root, em, cat, num)
        print('request %d: %s %d/%d -> %s' % (seq, monster_name(em), cat, num, os.path.join(root, 'sdcard', REQ_NAME)))
        return 0
    if a.cmd:
        print(__doc__)
        return 2
    main_gui(root)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
