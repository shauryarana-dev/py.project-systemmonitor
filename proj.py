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

class SystemMonitor:
    def __init__(self, master):
        self.master = master
        self.master.title("System Monitor")
        self.master.geometry("520x750")
        self.master.style.theme_use("darkly")
        self.master.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.running = True
        self.theme_is_dark = True

        self.cpu_core_count = psutil.cpu_count(logical=True)
        self.per_cpu_prog = []
        self.per_cpu_val = []

        self.cpu_data = deque(maxlen=30)
        self.data_queue = queue.Queue()

        self.build_ui()
        self.launch_threads()
        self.process_queue()

    def build_ui(self):
        main_frame = tb.Frame(self.master, padding=(15, 15))
        main_frame.pack(fill=BOTH, expand=YES)

        header_frame = tb.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 10))
        header_frame.columnconfigure(1, weight=1)
        tb.Label(header_frame, text="🖥️ System Monitor", font=("Segoe UI", 22, "bold"), bootstyle=LIGHT).grid(row=0, column=1)
        self.theme_button = tb.Button(header_frame, text="☀️", command=self.toggle_theme, bootstyle="light-outline")
        self.theme_button.grid(row=0, column=2, sticky='e')

        notebook = tb.Notebook(main_frame)
        notebook.pack(fill=BOTH, expand=YES)

        # --- Tab 1: Overview ---
        f1 = tb.Frame(notebook, padding=10)
        f1.columnconfigure(1, weight=1)
        self.cpu_prog, self.cpu_val, self.cpu_sparkline = self.create_metric_row(f1, "CPU Usage", 0, "⚙️", with_sparkline=True)
        self.ram_prog, self.ram_val, _ = self.create_metric_row(f1, "Memory Usage", 2, "💾")
        self.disk_prog, self.disk_val, _ = self.create_metric_row(f1, "Disk Usage", 3, "💽")
        self.battery_prog, self.battery_val, _ = self.create_metric_row(f1, "Battery Level", 4, "🔋")
        tb.Separator(f1).grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)
        self.download_val = self.create_activity_row(f1, "Download Speed", 6, "🡇")
        self.upload_val = self.create_activity_row(f1, "Upload Speed", 7, "🡅")
        self.temp_val = self.create_activity_row(f1, "CPU Temperature", 8, "🌡️")
        self.proc_val = self.create_activity_row(f1, "Running Processes", 9, "🧠")
        notebook.add(f1, text='📊 Dashboard')

        # --- Tab 2: Per-Core CPU ---
        f2 = tb.Frame(notebook, padding=10)
        f2.columnconfigure(1, weight=1)
        for i in range(self.cpu_core_count):
            prog, val, _ = self.create_metric_row(f2, f"Core {i+1}", i, "⚙️")
            self.per_cpu_prog.append(prog)
            self.per_cpu_val.append(val)
        notebook.add(f2, text='🧩 CPU Cores')

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
        notebook.add(f3, text='🛠️ System Info')
        
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
        for target in [self.update_cpu, self.update_ram, self.update_disk, self.update_network,
                       self.update_battery, self.update_processes, self.update_temperature, self.update_uptime]:
            threading.Thread(target=target, daemon=True).start()

    def get_bootstyle(self, value):
        if value <= 40: return SUCCESS
        elif value <= 75: return WARNING
        else: return DANGER

    def toggle_theme(self):
        self.theme_is_dark = not self.theme_is_dark
        self.master.style.theme_use("darkly" if self.theme_is_dark else "litera")
        self.theme_button.configure(bootstyle="light-outline" if self.theme_is_dark else "dark-outline")
        self.theme_button.configure(text="☀️" if self.theme_is_dark else "🌙")

    def format_bytes(self, size_bytes):
        if size_bytes == 0: return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        try:
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 1)
            return f"{s} {size_name[i]}"
        except ValueError:
            return "0B"

    def get_uptime(self):
        # Corrected uptime logic
        uptime_delta = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m"

    # --- Data Fetching Threads ---
    def update_cpu(self):
        while self.running:
            overall = psutil.cpu_percent(interval=1)
            per_core = psutil.cpu_percent(interval=0, percpu=True)
            self.data_queue.put(('cpu', (overall, per_core)))

    def update_ram(self):
        while self.running:
            time.sleep(1); self.data_queue.put(('ram', psutil.virtual_memory().percent))

    def update_disk(self):
        while self.running:
            time.sleep(5); self.data_queue.put(('disk', psutil.disk_usage('/').percent))

    def update_network(self):
        old_recv = psutil.net_io_counters().bytes_recv
        old_sent = psutil.net_io_counters().bytes_sent
        while self.running:
            time.sleep(1)
            new_recv = psutil.net_io_counters().bytes_recv
            new_sent = psutil.net_io_counters().bytes_sent
            d_speed = (new_recv - old_recv) / 1024
            u_speed = (new_sent - old_sent) / 1024
            old_recv, old_sent = new_recv, new_sent
            self.data_queue.put(('network', (d_speed, u_speed)))

    def update_battery(self):
        while self.running:
            time.sleep(10)
            val = None
            try:
                if hasattr(psutil, "sensors_battery"):
                    batt = psutil.sensors_battery()
                    if batt: val = batt.percent
            except Exception: pass
            self.data_queue.put(('battery', val))

    def update_processes(self):
        while self.running:
            time.sleep(3); self.data_queue.put(('processes', len(psutil.pids())))
            
    def update_temperature(self):
        while self.running:
            time.sleep(5)
            temp_val = None
            try:
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures()
                    if 'coretemp' in temps: temp_val = temps['coretemp'][0].current
                    elif 'cpu_thermal' in temps: temp_val = temps['cpu_thermal'][0].current
            except Exception: pass
            self.data_queue.put(('temperature', temp_val))
                
    def update_uptime(self):
        while self.running:
            self.data_queue.put(('uptime', self.get_uptime()))
            time.sleep(60)

    def shutdown(self):
        self.running = False
        self.master.destroy()

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except (ImportError, AttributeError):
        pass
    root = tb.Window()
    app = SystemMonitor(root)
    root.mainloop()
