from prompt_toolkit import Application
from prompt_toolkit.layout.containers import VSplit, HSplit, Window, FloatContainer, Float, ScrollOffsets
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import Frame, TextArea, SearchToolbar
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, merge_formatted_text
import psutil
import humanize
import datetime
import time
import os
import signal
import platform
import threading

# High visibility style setup
style = Style.from_dict({
    'header': 'bold #bb9af7',
    'row_even': '#7aa2f7',
    'row_odd': '#a9b1d6',
    'cursor': 'reverse #7aa2f7',
    'kill_selected': 'bg:#ff5555 #ffffff bold',
    'search': 'bold #24283b', 
    'footer': '#565f89',
    'info': '#83a598',
    'status_on': 'bold #b8bb26',
    'status_off': 'bold #ff5555',
})

class ProcessManager:
    def __init__(self):
        self.processes = []
        self.search_query = ""
        self.selected_index = 0
        self.confirmed_kill_pid = None
        self.is_running = True
        self.is_refresh_enabled = True # Added auto-refresh toggle
        self.lock = threading.Lock()
        
        # Periodic process scan in background
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    def _update_loop(self):
        while self.is_running:
            if self.is_refresh_enabled:
                new_list = []
                try:
                    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'username', 'status']):
                        try:
                            new_list.append(proc.info)
                        except: pass
                    new_list.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
                    with self.lock:
                        self.processes = new_list
                except: pass
            time.sleep(2.0)

    def get_filtered(self):
        with self.lock:
            q = self.search_query.lower()
            if not q:
                return self.processes
            return [p for p in self.processes if q in (p['name'] or "").lower() or q in str(p['pid']) or (p['username'] and q in p['username'].lower())]

    def terminate_process(self, pid):
        try:
            p = psutil.Process(pid)
            if platform.system() == "Windows":
                p.kill()
            else:
                p.terminate()
            return True
        except:
            return False

manager = ProcessManager()

search_field = TextArea(
    height=1,
    prompt=' Search: ',
    style='class:search',
    multiline=False,
    wrap_lines=False,
)

def _on_text_changed(buffer):
    manager.search_query = buffer.text
    manager.selected_index = 0
    manager.confirmed_kill_pid = None

search_field.buffer.on_text_changed += _on_text_changed

kb = KeyBindings()

@kb.add('q', eager=True)
@kb.add('c-c', eager=True)
def _(event):
    manager.is_running = False
    event.app.exit()

@kb.add('escape', eager=True)
def _(event):
    manager.confirmed_kill_pid = None
    event.app.invalidate()

@kb.add('space', eager=True)
def _(event):
    """Toggle auto-refresh when space is pressed."""
    manager.is_refresh_enabled = not manager.is_refresh_enabled
    event.app.invalidate()

@kb.add('up', eager=True)
@kb.add('c-p', eager=True)
def _(event):
    if manager.selected_index > 0:
        manager.selected_index -= 1
        manager.confirmed_kill_pid = None
    event.app.invalidate()

@kb.add('down', eager=True)
@kb.add('c-n', eager=True)
def _(event):
    filtered = manager.get_filtered()
    if manager.selected_index < len(filtered) - 1:
        manager.selected_index += 1
        manager.confirmed_kill_pid = None
    event.app.invalidate()

@kb.add('t', eager=True)
@kb.add('k', eager=True)
def _(event):
    filtered = manager.get_filtered()
    if 0 <= manager.selected_index < len(filtered):
        target_process = filtered[manager.selected_index]
        pid = target_process['pid']
        if manager.confirmed_kill_pid == pid:
            manager.terminate_process(pid)
            manager.confirmed_kill_pid = None
        else:
            manager.confirmed_kill_pid = pid
    event.app.invalidate()

def get_table_content():
    filtered = manager.get_filtered()
    table = []
    # Header row
    table.append(HTML('<header> PID     NAME                            CPU%   MEM%   USER\n</header>'))
    
    view_height = 25
    start = max(0, manager.selected_index - view_height // 2)
    end = start + view_height
    
    for i, p in enumerate(filtered[start:end], start=start):
        idx = i 
        line = (
             f" {p['pid']: <7} "
             f"{(p['name'] or '?')[:31]: <32} "
             f"{p['cpu_percent'] or 0: >4.1f}% "
             f"{p['memory_percent'] or 0: >4.1f}% "
             f"{(p['username'] or 'N/A')[:15]: <16}\n"
        )
        
        if idx == manager.selected_index:
            if manager.confirmed_kill_pid == p['pid']:
                table.append(HTML(f'<kill_selected>{line}</kill_selected>'))
            else:
                table.append(HTML(f'<cursor>{line}</cursor>'))
        elif idx % 2 == 0:
            table.append(HTML(f'<row_even>{line}</row_even>'))
        else:
            table.append(HTML(f'<row_odd>{line}</row_odd>'))
            
    return merge_formatted_text(table)

def get_header_text():
    # Show active refresh status in the top bar
    status = '<status_on>LIVE SCAN</status_on>' if manager.is_refresh_enabled else '<status_off>PAUSED</status_off>'
    return HTML(f'<header> tkill — {status}</header>')

container = FloatContainer(
    content=HSplit([
        Window(FormattedTextControl(get_header_text), height=1),
        search_field,
        Window(FormattedTextControl(get_table_content)),
        Window(FormattedTextControl(lambda: HTML('<footer class="footer"> [T/K] Kill  [Space] Toggle Refresh  [Escape] Cancel  [Q] Exit</footer>')), height=1),
    ]),
    floats=[]
)

layout = Layout(container)

app = Application(
    layout=layout,
    key_bindings=kb,
    style=style,
    full_screen=True, 
    refresh_interval=0.5,
)

if __name__ == "__main__":
    app.run()
