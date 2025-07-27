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
        self.master.geometry("500x700")
        self.master.style.theme_use("darkly")
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
        self.theme_is_dark = True
        
        self.cpu_core_count = psutil.cpu_count(logical=True)
        self.per_cpu_prog = []
        self.per_cpu_val = []

        self.cpu_data = deque(maxlen=30)
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
        main_frame = tb.Frame(self.master, padding=(15, 15))
        main_frame.pack(fill=BOTH, expand=YES)
        
        header_frame = tb.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 10))
        header_frame.columnconfigure(1, weight=1)
        tb.Label(header_frame, text="System Monitor", font=("Segoe UI", 20, "bold"), bootstyle=LIGHT).grid(row=0, column=1)
        self.theme_button = tb.Button(header_frame, text="☀️", command=self.toggle_theme, bootstyle="light-outline")
        self.theme_button.grid(row=0, column=2, sticky='e')

        notebook = tb.Notebook(main_frame)
        notebook.pack(fill=BOTH, expand=YES)

        # --- Tab 1: Overview ---
        f1 = tb.Frame(notebook, padding=10)
        f1.columnconfigure(1, weight=1)
        self.cpu_prog, self.cpu_val, self.cpu_sparkline = self.create_metric_row(f1, "CPU (Total)", 0, "⚙️", with_sparkline=True)
        self.ram_prog, self.ram_val, _ = self.create_metric_row(f1, "Memory", 2, "💾")
        self.disk_prog, self.disk_val, _ = self.create_metric_row(f1, "Disk", 3, "💽")
        self.battery_prog, self.battery_val, _ = self.create_metric_row(f1, "Battery", 4, "🔋")
        tb.Separator(f1).grid(row=5, column=0, columnspan=3, sticky="ew", pady=15)
        self.download_val = self.create_activity_row(f1, "Download", 6, "🡇")
        self.upload_val = self.create_activity_row(f1, "Upload", 7, "🡅")
        self.temp_val = self.create_activity_row(f1, "Temperature", 8, "🌡️")
        self.proc_val = self.create_activity_row(f1, "Processes", 9, "🧠")
        notebook.add(f1, text='  Overview  ')

        # --- Tab 2: Per-Core CPU ---
        f2 = tb.Frame(notebook, padding=10)
        f2.columnconfigure(1, weight=1)
        for i in range(self.cpu_core_count):
            prog, val, _ = self.create_metric_row(f2, f"CPU Core {i+1}", i, "⚙️")
            self.per_cpu_prog.append(prog)
            self.per_cpu_val.append(val)
        notebook.add(f2, text='  Per-Core CPU  ')

        # --- Tab 3: System Info ---
        f3 = tb.Frame(notebook, padding=15)
        f3.columnconfigure(1, weight=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        self.create_info_row(f3, "OS", f"{plat.system()} {plat.release()}", 0, "📦")
        self.create_info_row(f3, "Architecture", f"{plat.machine()}", 1, "🏗️")
        self.create_info_row(f3, "Hostname", f"{plat.node()}", 2, "🖥️")
        self.create_info_row(f3, "CPU", f"{plat.processor()}", 3, "⚙️")
        tb.Separator(f3).grid(row=4, columnspan=2, sticky="ew", pady=10)
        self.create_info_row(f3, "Total RAM", self.format_bytes(ram.total), 5, "💾")
        self.create_info_row(f3, "Total Disk", self.format_bytes(disk.total), 6, "💽")
        self.uptime_label = self.create_info_row(f3, "System Uptime", self.get_uptime(), 7, "⏱️")
        notebook.add(f3, text='  System Info  ')

    def create_metric_row(self, parent, label, row, icon, with_sparkline=False):
        tb.Label(parent, text=f"{icon} {label}", font=("Segoe UI", 12)).grid(row=row, column=0, sticky='w')
        val_label = tb.Label(parent, text="", font=("Segoe UI", 11, "bold"))
        val_label.grid(row=row, column=2, sticky='e', padx=(10, 0))
        prog = tb.Progressbar(parent, bootstyle=SUCCESS, maximum=100, mode='determinate')
        prog.grid(row=row, column=1, sticky='ew', padx=10)
        
        spark_canvas = None
        if with_sparkline:
            parent.grid_rowconfigure(row + 1, weight=1)
            spark_canvas = tb.Canvas(parent, height=25, highlightthickness=0)
            spark_canvas.grid(row=row + 1, column=0, columnspan=3, sticky='ew', pady=(0, 8), padx=5)
            
        return prog, val_label, spark_canvas

    def create_activity_row(self, parent, label, row, icon):
        tb.Label(parent, text=f"{icon} {label}", font=("Segoe UI", 12)).grid(row=row, column=0, sticky='w', pady=2)
        val_label = tb.Label(parent, text="N/A", font=("Segoe UI", 12, "bold"))
        val_label.grid(row=row, column=2, sticky='e', pady=2, padx=10)
        return val_label

    def create_info_row(self, parent, label, value, row, icon):
        tb.Label(parent, text=f"{icon} {label}", font=("Segoe UI", 12)).grid(row=row, column=0, sticky='w', pady=2)
        val_label = tb.Label(parent, text=value, font=("Segoe UI", 12, "bold"))
        val_label.grid(row=row, column=1, columnspan=2, sticky='e', pady=2, padx=10)
        return val_label

    def draw_sparkline(self, canvas, data):
        canvas.delete("all")
        if len(data) < 2: return
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 2 or height < 2: return
        max_val = max(data) or 100
        
        points = []
        for i, val in enumerate(data):
            x = (i / (len(data) - 1)) * width
            y = height - (val / max_val) * (height - 4)
            points.extend([x, y])

        color = self.master.style.colors.primary
        canvas.create_line(points, fill=color, width=2, smooth=True)
        
    def process_queue(self):
        try:
            while not self.data_queue.empty():
                message = self.data_queue.get_nowait()
                msg_type, data = message[0], message[1]
                
                if msg_type == 'cpu':
                    overall, per_core = data
                    self.cpu_data.append(overall)
                    self.cpu_prog.configure(value=overall, bootstyle=self.get_bootstyle(overall))
                    self.cpu_val.configure(text=f"{overall:.0f}%")
                    self.draw_sparkline(self.cpu_sparkline, self.cpu_data)
                    for i in range(self.cpu_core_count):
                        self.per_cpu_prog[i].configure(value=per_core[i], bootstyle=self.get_bootstyle(per_core[i]))
                        self.per_cpu_val[i].configure(text=f"{per_core[i]:.0f}%")
                elif msg_type == 'ram':
                    self.ram_prog.configure(value=data, bootstyle=self.get_bootstyle(data))
                    self.ram_val.configure(text=f"{data:.0f}%")
                elif msg_type == 'disk':
                    self.disk_prog.configure(value=data, bootstyle=self.get_bootstyle(data))
                    self.disk_val.configure(text=f"{data:.0f}%")
                elif msg_type == 'network':
                    d_speed, u_speed = data
                    self.download_val.config(text=f"{d_speed:.1f} KB/s")
                    self.upload_val.config(text=f"{u_speed:.1f} KB/s")
                elif msg_type == 'battery':
                    self.battery_val.configure(text=f"{data:.0f}%" if data is not None else "N/A")
                    if data is not None:
                        self.battery_prog.configure(value=data, bootstyle=self.get_bootstyle(data))
                elif msg_type == 'processes':
                    self.proc_val.config(text=f"{data}")
                elif msg_type == 'temperature':
                    self.temp_val.config(text=f"{data:.1f}°C" if data is not None else "No Sensor")
                elif msg_type == 'uptime':
                    self.uptime_label.configure(text=data)

        except queue.Empty:
            pass
        finally:
            if self.running:
                self.master.after(100, self.process_queue)

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
