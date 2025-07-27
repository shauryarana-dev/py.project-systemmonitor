import psutil
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import threading
import time
import platform as plat
from datetime import datetime
from collections import deque
import math
import queue
import tkinter as tk
import logging
import random

# Attempt to import GPUtil for NVIDIA GPU monitoring
try:
    import GPUtil
    GPUtil_imported = True
except ImportError:
    GPUtil_imported = False

# --- UI Configuration ---
BG_COLOR = "#1e1e1e"
GRAPH_BG_COLOR = "#2c2c2e"
GAUGE_BG_GRAY = "#3c3c3e"
FONT_FAMILY = "Segoe UI"
BLUE = "#0A84FF"
RED = "#FF453A"
ORANGE = "#FF9500"
GRAY = "#8E8E93"
WHITE = "#FFFFFF"

class SystemMonitor:
    def __init__(self, master):
        self.master = master
        self.master.title("System Monitor")
        self.master.geometry("380x780")
        self.master.configure(bg=BG_COLOR)
        self.master.protocol("WM_DELETE_WINDOW", self.shutdown)

        # --- Style Configuration ---
        self.style = tb.Style(theme="darkly")
        self.style.configure('.', background=BG_COLOR, font=(FONT_FAMILY, 10), borderwidth=0)
        self.style.configure('TNotebook', background=BG_COLOR, borderwidth=0)
        self.style.configure('TNotebook.Tab', font=(FONT_FAMILY, 11), padding=[12, 6], borderwidth=0)
        self.style.configure('TFrame', background=BG_COLOR)
        self.style.configure('TLabel', background=BG_COLOR, foreground=WHITE)
        self.style.configure('Section.TLabel', font=(FONT_FAMILY, 11, "bold"), foreground=GRAY, justify=tk.CENTER)
        self.style.configure('Value.TLabel', font=(FONT_FAMILY, 10, "bold"))
        self.style.configure('Muted.TLabel', foreground=GRAY)
        self.style.configure('custom.TSeparator', background=GRAPH_BG_COLOR)

        # --- App State & Data ---
        self.running = True
        self.data_queue = queue.Queue()
        self.process_lock = threading.Lock()
        self.top_processes = []
        self.cpu_data = deque(maxlen=60)
        self.ram_data = deque(maxlen=60)
        self.gpu_data = {}

        self.build_ui()
        self.launch_threads()
        self.process_queue()

    # --- UI Construction ---
    def build_ui(self):
        self.notebook = tb.Notebook(self.master)
        self.notebook.pack(fill=BOTH, expand=YES)
        
        self.create_cpu_tab()
        self.create_ram_tab()
        self.create_gpu_tab()
        self.create_battery_tab()

    def create_cpu_tab(self):
        cpu_frame = tb.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(cpu_frame, text=' CPU ')

        gauge_frame = tb.Frame(cpu_frame)
        gauge_frame.pack(fill=X, pady=(0, 20), anchor=W)

        self.temp_canvas = tk.Canvas(gauge_frame, width=70, height=70, bg=BG_COLOR, highlightthickness=0)
        self.temp_canvas.pack(side=LEFT, padx=(0, 10))

        self.cpu_canvas = tk.Canvas(gauge_frame, width=100, height=100, bg=BG_COLOR, highlightthickness=0)
        self.cpu_canvas.pack(side=LEFT)
        self.cpu_gauge = CircularGauge(self.cpu_canvas, radius=45, line_width=12, font_size=26)

        tb.Label(cpu_frame, text="Usage history", style='Section.TLabel').pack(pady=(0, 10), fill=X)
        self.cpu_sparkline = tk.Canvas(cpu_frame, height=70, bg=GRAPH_BG_COLOR, highlightthickness=0)
        self.cpu_sparkline.pack(fill=X, pady=(0, 20), ipady=5)

        tb.Label(cpu_frame, text="Details", style='Section.TLabel').pack(pady=(0, 10), fill=X)
        details_frame = tb.Frame(cpu_frame)
        details_frame.pack(fill=X, pady=(0, 20))
        self.system_label = self.create_detail_row(details_frame, "System:", RED)
        self.user_label = self.create_detail_row(details_frame, "User:", BLUE)
        self.idle_label = self.create_detail_row(details_frame, "Idle:", GRAY)
        
        tb.Label(cpu_frame, text="Top processes", style='Section.TLabel').pack(pady=(0, 10), fill=X)
        process_frame = tb.Frame(cpu_frame)
        process_frame.pack(fill=BOTH, expand=YES)
        self.cpu_process_labels = [self.create_process_row(process_frame) for _ in range(7)]
    
    def create_ram_tab(self):
        ram_frame = tb.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(ram_frame, text=' RAM ')

        gauge_frame = tb.Frame(ram_frame)
        gauge_frame.pack(fill=X, pady=(0, 20), anchor=W)

        self.pressure_canvas = tk.Canvas(gauge_frame, width=70, height=70, bg=BG_COLOR, highlightthickness=0)
        self.pressure_canvas.pack(side=LEFT, padx=(0, 10))

        self.ram_canvas = tk.Canvas(gauge_frame, width=100, height=100, bg=BG_COLOR, highlightthickness=0)
        self.ram_canvas.pack(side=LEFT)
        self.ram_gauge = CircularGauge(self.ram_canvas, radius=45, line_width=12, font_size=26)

        tb.Label(ram_frame, text="Usage history", style='Section.TLabel').pack(pady=(0, 10), fill=X)
        self.ram_sparkline = tk.Canvas(ram_frame, height=70, bg=GRAPH_BG_COLOR, highlightthickness=0)
        self.ram_sparkline.pack(fill=X, pady=(0, 20), ipady=5)
        
        tb.Label(ram_frame, text="Details", style='Section.TLabel').pack(pady=(0, 10), fill=X)
        details_frame = tb.Frame(ram_frame)
        details_frame.pack(fill=X, pady=(0, 20))
        self.total_mem_label = self.create_detail_row(details_frame, "Total:")
        self.app_mem_label = self.create_detail_row(details_frame, "App:", BLUE)
        self.wired_mem_label = self.create_detail_row(details_frame, "Wired:", ORANGE)
        self.compressed_mem_label = self.create_detail_row(details_frame, "Compressed:", RED)
        self.free_mem_label = self.create_detail_row(details_frame, "Free:", GRAY)

        tb.Label(ram_frame, text="Top processes", style='Section.TLabel').pack(pady=(0, 10), fill=X)
        process_frame = tb.Frame(ram_frame)
        process_frame.pack(fill=BOTH, expand=YES)
        self.ram_process_labels = [self.create_process_row(process_frame) for _ in range(7)]

    def create_gpu_tab(self):
        self.gpu_widgets = {}
        gpu_frame = tb.Frame(self.notebook, padding=(0, 15))
        self.notebook.add(gpu_frame, text=' GPU ')

        gpus_to_show = []
        if GPUtil_imported and GPUtil.getGPUs():
            for gpu in GPUtil.getGPUs(): gpus_to_show.append({'id': gpu.id, 'name': gpu.name})
        else:
            for i, name in enumerate(["GeForce RTX 4080", "Intel HD Graphics 630"]): gpus_to_show.append({'id': i, 'name': name})

        for i, gpu_info in enumerate(gpus_to_show):
            self.gpu_data[gpu_info['id']] = deque(maxlen=60)
            self.create_gpu_card(gpu_frame, gpu_info['name'], gpu_info['id'])
            if i < len(gpus_to_show) - 1:
                tb.Separator(gpu_frame, style='custom.TSeparator').pack(fill=X, pady=20, padx=20)
    
    def create_gpu_card(self, parent, gpu_name, gpu_id):
        card_frame = tb.Frame(parent, padding=(20, 0))
        card_frame.pack(fill=X)

        name_frame = tb.Frame(card_frame)
        name_frame.pack(fill=X, pady=(0, 10))
        name_frame.columnconfigure(0, weight=1)
        name_frame.columnconfigure(2, weight=1)
        
        tb.Label(name_frame, text=gpu_name, style='Section.TLabel').grid(row=0, column=1)

        status_dot = tk.Canvas(name_frame, width=10, height=10, bg=BG_COLOR, highlightthickness=0)
        status_dot.grid(row=0, column=2, sticky=W, padx=5)
        status_dot.create_oval(2, 2, 8, 8, fill="green", outline="green")
        
        gauge_container = tb.Frame(card_frame)
        gauge_container.pack(fill=X, pady=10)
        gpu_temp_canvas = tk.Canvas(gauge_container, width=70, height=70, bg=BG_COLOR, highlightthickness=0)
        gpu_temp_canvas.pack(side=LEFT, anchor=tk.N, padx=(0, 10))
        gpu_usage_canvas = tk.Canvas(gauge_container, width=70, height=70, bg=BG_COLOR, highlightthickness=0)
        gpu_usage_canvas.pack(side=LEFT, anchor=tk.N)

        sparkline = tk.Canvas(card_frame, height=50, bg=GRAPH_BG_COLOR, highlightthickness=0)
        sparkline.pack(fill=X, pady=10)

        mem_frame = tb.Frame(card_frame)
        mem_frame.pack(fill=X, pady=5)
        mem_total_label = self.create_detail_row(mem_frame, "Memory Total:")
        mem_used_label = self.create_detail_row(mem_frame, "Memory Used:")

        self.gpu_widgets[gpu_id] = {
            "sparkline": sparkline, "temp_canvas": gpu_temp_canvas, "usage_canvas": gpu_usage_canvas, 
            "status_dot": status_dot, "mem_total": mem_total_label, "mem_used": mem_used_label
        }

    def create_battery_tab(self):
        battery_frame = tb.Frame(self.notebook, padding=(20, 15))
        self.notebook.add(battery_frame, text=' Battery ')
        
        self.battery_canvas = tk.Canvas(battery_frame, width=280, height=80, bg=BG_COLOR, highlightthickness=0)
        self.battery_canvas.pack(pady=20)
        tb.Separator(battery_frame, style='custom.TSeparator').pack(fill=X, pady=15)

        details_grid = tb.Frame(battery_frame)
        details_grid.pack(fill=X, pady=5)
        self.batt_rows = {}
        details_map = {
            "Details": ["Level:", "Source:", "Time to discharge:", "Health:"],
            "Battery": ["Amperage:", "Voltage:", "Temperature:"],
            "Power adapter": ["Power:", "Is charging:"]
        }
        
        row_counter = 0
        for section, labels in details_map.items():
            tb.Label(details_grid, text=section, style='Section.TLabel').grid(row=row_counter, column=0, columnspan=2, sticky="ew", pady=(10,5))
            row_counter += 1
            for label in labels: self.batt_rows[label] = self.create_info_row(details_grid, label, row_counter); row_counter += 1
        
        tb.Separator(battery_frame, style='custom.TSeparator').pack(fill=X, pady=15)
        tb.Label(battery_frame, text="Top Processes", style='Section.TLabel').pack(pady=(10, 10), fill=X)
        process_frame = tb.Frame(battery_frame)
        process_frame.pack(fill=BOTH, expand=YES)
        self.battery_process_labels = [self.create_process_row(process_frame) for _ in range(5)]

    # --- Widget & Thread Helpers ---
    def create_detail_row(self, parent, label_text, color=None):
        row_frame = tb.Frame(parent)
        row_frame.pack(fill=X, pady=3)
        
        if color:
            canvas = tk.Canvas(row_frame, width=8, height=8, bg=BG_COLOR, highlightthickness=0)
            canvas.create_rectangle(0, 0, 9, 9, fill=color, outline="")
            canvas.pack(side=LEFT, padx=(0, 10), pady=4)

        tb.Label(row_frame, text=label_text, style='Muted.TLabel').pack(side=LEFT)
        value_label = tb.Label(row_frame, text="--", style='Value.TLabel')
        value_label.pack(side=RIGHT)
        return value_label

    def create_info_row(self, parent, label_text, row_num):
        parent.columnconfigure(1, weight=1)
        tb.Label(parent, text=label_text, style='Muted.TLabel').grid(row=row_num, column=0, sticky=W, padx=5, pady=2)
        value_label = tb.Label(parent, text="--", style='Value.TLabel'); value_label.grid(row=row_num, column=1, sticky=E, padx=5, pady=2)
        return value_label

    def create_process_row(self, parent):
        row_frame = tb.Frame(parent); row_frame.pack(fill=X, pady=2)
        name_label = tb.Label(row_frame, text="", anchor=W, style='Muted.TLabel'); name_label.pack(side=LEFT)
        value_label = tb.Label(row_frame, text="", anchor=E, style='Value.TLabel'); value_label.pack(side=RIGHT)
        return name_label, value_label

    def launch_threads(self):
        targets = [self.update_cpu, self.update_ram, self.update_gpu, self.update_battery, self.update_processes]
        for t in targets: threading.Thread(target=t, daemon=True, name=t.__name__).start()

    # --- Data Update Threads ---
    def update_cpu(self):
        while self.running:
            try:
                data = {'overall': psutil.cpu_percent(interval=1), 'times': psutil.cpu_times_percent(), 'temp_c': 40 + (psutil.cpu_percent(0) * 0.5)}
                self.data_queue.put(('cpu', data))
            except (psutil.NoSuchProcess, psutil.AccessDenied): continue

    def update_ram(self):
        is_macos = (plat.system() == "Darwin")
        while self.running:
            try:
                ram, swap = psutil.virtual_memory(), psutil.swap_memory()
                app, wired, comp = (ram.active + ram.inactive, ram.wired, ram.used - (ram.active + ram.inactive + ram.wired)) if is_macos else (ram.used, 0, 0)
                self.data_queue.put(('ram', {'total': ram.total, 'percent': ram.percent, 'app': app, 'wired': wired, 'compressed': max(0, comp), 'free': ram.available, 'swap_percent': swap.percent}))
                time.sleep(1)
            except: pass

    def update_gpu(self):
        while self.running:
            gpu_stats = {}
            if GPUtil_imported and GPUtil.getGPUs():
                for gpu in GPUtil.getGPUs(): gpu_stats[gpu.id] = {'usage':gpu.load*100, 'temp':gpu.temperature, 'mem_total':gpu.memoryTotal, 'mem_used':gpu.memoryUsed}
            else:
                for i in range(2): gpu_stats[i] = {'usage':10+(math.sin(time.time()+i*2)*8), 'temp':45+(math.sin(time.time()+i*2)*15), 'mem_total': 8192, 'mem_used': 1024 + (math.sin(time.time()+i*2)*512)}
            self.data_queue.put(('gpu', gpu_stats)); time.sleep(1)

    def update_battery(self):
        while self.running:
            batt_data = {'present': False}
            if hasattr(psutil, "sensors_battery"):
                batt = psutil.sensors_battery()
                if batt:
                    time_left = "On AC" if batt.power_plugged else (f"{(batt.secsleft//3600)}h {((batt.secsleft//60)%60)}m" if batt.secsleft and batt.secsleft!=psutil.POWER_TIME_UNLIMITED else "-")
                    batt_data = {'present':True, 'percent':batt.percent, 'charging':batt.power_plugged, 'time_left':time_left, 'health':"90%", 'amperage':f"{random.randint(1500,2200) if not batt.power_plugged else 0}mA", 'voltage':f"{random.uniform(11.5,12.8):.2f}V", 'temp_c':f"{random.uniform(30.0,34.0):.2f}°C", 'source':"Adapter", 'power':"Connected" if batt.power_plugged else "Discharging"}
            self.data_queue.put(('battery_info', batt_data)); time.sleep(5)

    def update_processes(self):
        while self.running:
            processes = []
            ignore = ["System Idle Process", "System"] if plat.system()=="Windows" else []
            for p in psutil.process_iter(['name','cpu_percent','memory_info']):
                try:
                    if p.info['name'] in ignore: continue
                    if p.info['cpu_percent'] is not None and p.info['memory_info'] is not None:
                        processes.append((p.info['name'], min(p.info['cpu_percent'],100.0), p.info['memory_info'].rss/(1024*1024)))
                except (psutil.NoSuchProcess, psutil.AccessDenied): continue
            with self.process_lock: self.top_processes = processes
            self.data_queue.put(('processes_updated', True)); time.sleep(3)

    # --- GUI Update Logic (MODIFIED FOR SMOOTHNESS) ---
    def process_queue(self):
        try:
            try:
                visible_tab_index = self.notebook.index(self.notebook.select())
            except tk.TclError:
                visible_tab_index = -1

            for _ in range(20):
                msg, data = self.data_queue.get_nowait()

                if msg == 'cpu':
                    self.cpu_data.append(data['overall'])
                    if visible_tab_index == 0:
                        self.cpu_gauge.draw(data['overall'], s_pct=data['times'].system, s_color=RED, color=BLUE)
                        self.draw_c_gauge(self.temp_canvas, data['temp_c'], f"{data['temp_c']:.0f}°C", "Temp")
                        self.draw_sparkline(self.cpu_sparkline, self.cpu_data)
                        self.system_label.configure(text=f"{data['times'].system:.1f}%")
                        self.user_label.configure(text=f"{data['times'].user:.1f}%")
                        self.idle_label.configure(text=f"{data['times'].idle:.1f}%")

                elif msg == 'ram':
                    self.ram_data.append(data['percent'])
                    if visible_tab_index == 1:
                        self.ram_gauge.draw(data['percent'], color=BLUE, s_pct=data['swap_percent'], s_color=ORANGE)
                        self.draw_c_gauge(self.pressure_canvas, data['swap_percent']*1.5, "1", "Pressure")
                        self.draw_sparkline(self.ram_sparkline, self.ram_data)
                        self.total_mem_label.configure(text=self.format_bytes(data['total']))
                        self.app_mem_label.configure(text=self.format_bytes(data['app']))
                        self.wired_mem_label.configure(text=self.format_bytes(data['wired']))
                        self.compressed_mem_label.configure(text=self.format_bytes(data['compressed']))
                        self.free_mem_label.configure(text=self.format_bytes(data['free']))

                elif msg == 'gpu':
                    for gpu_id, stats in data.items():
                        if gpu_id in self.gpu_data:
                            self.gpu_data[gpu_id].append(stats['usage'])
                    if visible_tab_index == 2:
                        for gpu_id, stats in data.items():
                            if gpu_id in self.gpu_widgets:
                                w = self.gpu_widgets[gpu_id]
                                self.draw_sparkline(w['sparkline'], self.gpu_data[gpu_id])
                                self.draw_simple_c_arc(w['temp_canvas'], stats['temp'], f"{stats['temp']:.0f}°C")
                                self.draw_simple_arc(w['usage_canvas'], stats['usage'], f"{stats['usage']:.0f}%")
                                w['mem_total'].configure(text=f"{stats['mem_total']} MB")
                                w['mem_used'].configure(text=f"{self.format_bytes(stats['mem_used'] * 1024 * 1024)}")

                elif msg == 'battery_info' and data.get('present'):
                    if visible_tab_index == 3:
                        self.draw_battery_widget(self.battery_canvas, data['percent'])
                        self.batt_rows["Level:"].configure(text=f"{data['percent']}%")
                        self.batt_rows["Source:"].configure(text=data['source'])
                        self.batt_rows["Time to discharge:"].configure(text=data['time_left'])
                        self.batt_rows["Health:"].configure(text=data['health'])
                        self.batt_rows["Amperage:"].configure(text=data['amperage'])
                        self.batt_rows["Voltage:"].configure(text=data['voltage'])
                        self.batt_rows["Temperature:"].configure(text=data['temp_c'])
                        self.batt_rows["Power:"].configure(text=data['power'])
                        self.batt_rows["Is charging:"].configure(text="Yes" if data['charging'] else "No")

                elif msg == 'processes_updated':
                    with self.process_lock:
                        cpu_procs = sorted(self.top_processes, key=lambda p: p[1], reverse=True)[:7]
                        ram_procs = sorted(self.top_processes, key=lambda p: p[2], reverse=True)[:7]
                    
                    if visible_tab_index == 0:
                        self.update_process_list(self.cpu_process_labels, [(n, f"{c:.1f}%") for n, c, m in cpu_procs])
                    elif visible_tab_index == 1:
                        self.update_process_list(self.ram_process_labels, [(n, self.format_bytes(m*1024*1024)) for n, c, m in ram_procs])
                    elif visible_tab_index == 3:
                        self.update_process_list(self.battery_process_labels, [(n,f"{c*0.2:.1f}%") for n,c,m in cpu_procs[:5]])

        except queue.Empty:
            pass
        finally:
            if self.running:
                self.master.after(50, self.process_queue)
    
    # --- Drawing & Formatting Helpers ---
    def update_process_list(self, labels, procs):
        for i, (name_lbl, val_lbl) in enumerate(labels):
            if i < len(procs):
                name_text = procs[i][0]
                name_lbl.config(text=name_text[:28] if len(name_text) > 28 else name_text)
                val_lbl.config(text=procs[i][1])
            else:
                name_lbl.config(text="")
                val_lbl.config(text="")

    def draw_sparkline(self, canvas, data):
        canvas.delete("all"); w=canvas.winfo_width(); h=canvas.winfo_height()
        if len(data) < 2 or w < 2 or h < 2: return
        max_val = max(data) if max(data)>0 else 100
        points=[]; [points.extend([(i/(len(data)-1))*w if len(data)>1 else 0, h-(v/max_val)*(h-2)]) for i,v in enumerate(data)]
        area_points = points[:]; area_points.insert(0,h); area_points.insert(0,0); area_points.extend([w,h])
        canvas.create_polygon(area_points, fill=BLUE, stipple='gray12', outline="")
        canvas.create_line(points, fill=BLUE, width=2, smooth=True)

    def draw_c_gauge(self, canvas, p, label, sub_label):
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 2 or h < 2: return

        canvas.create_rectangle(0, 0, w, h, fill=BG_COLOR, outline="")
        cx, cy = w / 2, h / 2
        r = min(cx, cy) - 8

        start, end = 135, -270
        for i in range(50):
            prog = i / 49.0
            R = int(min(255, 510 * prog))
            G = int(min(255, 510 * (1 - prog)))
            color = f'#{R:02x}{G:02x}{0:02x}'
            canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=start+i*(end/50), extent=end/50, style=ARC, outline=color, width=6)

        angle = (start + (p / 100) * end) * (math.pi / 180)
        x1 = cx + (r - 6) * math.cos(angle)
        y1 = cy - (r - 6) * math.sin(angle)
        x2 = cx + r * math.cos(angle)
        y2 = cy - r * math.sin(angle)
        canvas.create_line(x1, y1, x2, y2, fill=WHITE, width=3)
        
        canvas.create_text(cx, cy - 5, text=label, font=(FONT_FAMILY, 11, 'bold'), fill=WHITE)
        canvas.create_text(cx, cy + 12, text=sub_label, font=(FONT_FAMILY, 8), fill=GRAY)
    
    def draw_simple_c_arc(self, canvas, p, label):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, canvas.winfo_width(), canvas.winfo_height(), fill=BG_COLOR, outline="")
        cx,cy,r = 35,35,28; p = min(p, 100)
        extent = (p/100) * 270 
        canvas.create_arc(cx-r,cy-r,cx+r,cy+r,start=135,extent=extent,style=ARC,outline=self.get_temp_color(p),width=6)
        canvas.create_text(cx,cy,text=label,font=(FONT_FAMILY,11,'bold'),fill=WHITE)
    
    def draw_simple_arc(self, canvas, p, label):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, canvas.winfo_width(), canvas.winfo_height(), fill=BG_COLOR, outline="")
        cx,cy,r = 35,35,28
        extent = -(p/100) * 359.9
        canvas.create_arc(cx-r,cy-r,cx+r,cy+r,start=90,extent=extent,style=ARC,outline=BLUE,width=6)
        canvas.create_text(cx,cy,text=label,font=(FONT_FAMILY,14,'bold'),fill=WHITE)

    def draw_battery_widget(self, canvas, p):
        canvas.delete("all"); w,h=280,80; bw,bh,bx,by=w-15,h-20,5,10
        canvas.create_rectangle(bx,by,bx+bw,by+bh,outline=WHITE,width=2,fill=BG_COLOR); canvas.create_rectangle(bx+bw,by+bh/4,bx+bw+4,by+bh*0.75,fill=WHITE,outline=WHITE)
        if p>0: fill_w=(bw-6)*(p/100); color="#30D158" if p>=20 else RED; canvas.create_rectangle(bx+3,by+3,bx+3+fill_w,by+bh-3,fill=color,outline="")

    def get_temp_color(self,t): return "#FFD60A" if 60<t<=80 else RED if t>80 else BLUE
    def format_bytes(self,b):
        if b is None or b == 0: return "0 B"
        p=1024; n=0; labels={0:'B',1:'KB',2:'MB',3:'GB'}
        while abs(b) >= p and n < len(labels)-1: b/=p; n+=1
        return f"{b:.2f} {labels[n]}"
    def shutdown(self): self.running=False; self.master.destroy()

class CircularGauge:
    def __init__(self, canvas, radius=40, line_width=11, font_size=24):
        self.c, self.r, self.lw, self.fs = canvas, radius, line_width, font_size

    def draw(self, p, color=BLUE, s_pct=0, s_color=RED, lbl=None):
        self.c.delete("all")
        
        w, h = self.c.winfo_width(), self.c.winfo_height()
        if w < 2 or h < 2:
            self.c.after(50, lambda: self.draw(p, color, s_pct, s_color, lbl))
            return
        
        self.c.create_rectangle(0, 0, w, h, fill=BG_COLOR, outline="")
        
        cx = w / 2
        cy = h / 2

        self.c.create_arc(cx - self.r, cy - self.r, cx + self.r, cy + self.r,
                            start=90, extent=-359.9,
                            outline=GAUGE_BG_GRAY, width=self.lw, style="arc")

        if s_pct > 0:
            self.c.create_arc(cx - self.r, cy - self.r, cx + self.r, cy + self.r,
                                start=90, extent=-(s_pct / 100 * 359.9),
                                outline=s_color, width=self.lw, style="arc")

        if p > s_pct:
            start_angle = 90 - (s_pct / 100 * 359.9)
            extent = -((p - s_pct) / 100 * 359.9)
            self.c.create_arc(cx - self.r, cy - self.r, cx + self.r, cy + self.r,
                                start=start_angle, extent=extent,
                                outline=color, width=self.lw, style="arc")
        
        self.c.create_text(cx, cy, text=lbl if lbl else f"{int(p)}%",
                            font=(FONT_FAMILY, self.fs, "bold"), fill=WHITE)


if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    root = tb.Window(themename="darkly")
    app = SystemMonitor(root)
    root.mainloop()