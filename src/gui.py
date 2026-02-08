import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from threading import Thread
import concurrent.futures
import os
import queue
from datetime import datetime
from .config import *
from .date_utils import DateExtractor
from .media_ops import MediaMetadataManager
from .repair import ImageRepairTool

class ImageMetadataApp(ttk.Window):
    def __init__(self):
        super().__init__(themename=THEME_NAME)
        self.title(APP_NAME)
        
        # Dimensionamiento responsivo
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        w = min(1200, int(screen_width * 0.8))
        h = min(800, int(screen_height * 0.8))
        self.geometry(f"{w}x{h}")
        
        self.date_extractor = DateExtractor()
        self.media_manager = MediaMetadataManager()
        self.repair_tool = ImageRepairTool()
        
        self.files_data = []
        self.ui_queue = queue.Queue()
        
        # Pool de hilos para escaneo de alto rendimiento
        # Usando un número razonable de trabajadores (CPU * 2 es heurística común para mezcla I/O)
        self.max_workers = min(32, (os.cpu_count() or 4) * 4) 
        
        self.setup_ui()
        self.start_ui_updater()
        
        if not self.media_manager.ffmpeg_available:
            self.status_log("Advertencia: FFmpeg no detectado. Soporte de video limitado.", "warning")

    def setup_ui(self):
        # Marco Superior: Controles
        control_frame = ttk.Frame(self, padding=10)
        control_frame.pack(fill=X)
        
        self.btn_select = ttk.Button(control_frame, text=TXT_BTN_SELECT, command=self.select_folder, bootstyle=PRIMARY)
        self.btn_select.pack(side=LEFT, padx=5)
        
        self.btn_process = ttk.Button(control_frame, text=TXT_BTN_PROCESS, command=self.start_processing, bootstyle=SUCCESS, state=DISABLED)
        self.btn_process.pack(side=LEFT, padx=5)
        
        self.lbl_status = ttk.Label(control_frame, text=TXT_STATUS_READY)
        self.lbl_status.pack(side=LEFT, padx=15)

        # Leyenda/Ayuda
        help_btn = ttk.Button(control_frame, text="?", command=self.show_help, bootstyle="secondary-outline", width=3)
        help_btn.pack(side=RIGHT, padx=5)
        
        # Marco Principal: Vista de Árbol
        tree_frame = ttk.Frame(self, padding=10)
        tree_frame.pack(fill=BOTH, expand=True)
        
        columns = ("filename", "date_name", "date_meta", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        
        self.tree.heading("filename", text=TXT_COL_FILE)
        self.tree.heading("date_name", text=TXT_COL_DATE_NAME)
        self.tree.heading("date_meta", text=TXT_COL_DATE_META)
        self.tree.heading("status", text=TXT_COL_STATUS)
        
        self.tree.column("filename", width=350)
        self.tree.column("date_name", width=180)
        self.tree.column("date_meta", width=180)
        self.tree.column("status", width=150)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Configuración de Etiquetas
        self.tree.tag_configure("success", foreground="#00bc8c")
        self.tree.tag_configure("warning", foreground="#f39c12")
        self.tree.tag_configure("secondary", foreground="#adb5bd")
        self.tree.tag_configure("danger", foreground="#e74c3c")

        # Barra de Progreso
        self.progress = ttk.Progressbar(self, orient=HORIZONTAL, mode='determinate', bootstyle=INFO)
        self.progress.pack(fill=X, padx=10, pady=5)

    def status_log(self, message, level="info"):
        print(f"[{level.upper()}] {message}") # Registro en consola
        # Idealmente, esto iría a una barra de estado o ventana de registro

    def show_help(self):
        msg = (
            f"• {STATUS_MATCH}: {HELP_MSG_MATCH}\n"
            f"• {STATUS_MATCH_DATE}: {HELP_MSG_MATCH_DATE}\n"
            f"• {STATUS_MISMATCH}: {HELP_MSG_MISMATCH}\n"
            f"• {STATUS_CORRUPT}: {HELP_MSG_CORRUPT}\n\n"
            f"{HELP_MSG_PRIORITY}"
        )
        messagebox.showinfo("Ayuda", msg)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.load_files_parallel(folder)

    def process_single_file_scan(self, filepath):
        """
        Función trabajadora para escanear un archivo único.
        Retorna el diccionario de datos para el archivo.
        """
        filename = os.path.basename(filepath)
        
        # Verificar Corrupción (PNG)
        is_corrupted = False
        if filename.lower().endswith('.png'):
            if self.repair_tool.is_corrupted_png(filepath):
                is_corrupted = True

        date_from_name, name_has_time = self.date_extractor.extract_date(filename)
        
        date_from_meta = None
        status = STATUS_NO_DATE
        action_needed = False
        needs_repair = False

        if is_corrupted:
            status = STATUS_CORRUPT
            action_needed = True
            needs_repair = True
        else:
            skip_deep = True if date_from_name else False
            date_from_meta = self.media_manager.get_metadata_date(filepath, skip_deep_scan=skip_deep)
            if date_from_meta:
                date_from_meta = date_from_meta.replace(tzinfo=None)

            if date_from_name:
                date_from_name = date_from_name.replace(tzinfo=None)
                
                if date_from_meta:
                    d1 = date_from_name
                    d2 = date_from_meta
                    diff = abs((d1 - d2).total_seconds())
                    
                    if diff < 60:
                        status = STATUS_MATCH
                    else:
                        if not name_has_time:
                            if d1.date() == d2.date():
                                status = STATUS_MATCH_DATE
                            else:
                                status = STATUS_MISMATCH
                                action_needed = True
                        else:
                            status = STATUS_MISMATCH
                            action_needed = True
                else:
                    status = STATUS_NO_META
                    action_needed = True
            else:
                # Lógica de respaldo
                if date_from_meta:
                    try:
                        stats = os.stat(filepath)
                        mtime = datetime.fromtimestamp(stats.st_mtime)
                        diff_fs = abs((date_from_meta - mtime).total_seconds())
                        
                        if diff_fs < 60:
                            status = STATUS_FS_MATCH
                        else:
                            status = STATUS_FS_MISMATCH
                            action_needed = True
                            date_from_name = date_from_meta
                    except Exception as e:
                        print(f"[DEBUG] Error reading stats for {filepath}: {e}")
                else:
                    try:
                        stats = os.stat(filepath)
                        mtime = datetime.fromtimestamp(stats.st_mtime)
                        if mtime.year <= 1970:
                            status = STATUS_1970
                            action_needed = True
                            date_from_name = datetime(2020, 1, 1, 12, 0, 0)
                    except Exception as e:
                        print(f"[DEBUG] Error reading stats fallback for {filepath}: {e}")

        return {
            "filepath": filepath,
            "filename": filename,
            "date_name": date_from_name,
            "date_meta": date_from_meta,
            "status": status,
            "action_needed": action_needed,
            "needs_repair": needs_repair,
            "iid": None
        }

    def load_files_parallel(self, folder):
        self.tree.delete(*self.tree.get_children())
        self.files_data = []
        self.btn_process.config(state=DISABLED)
        self.lbl_status.config(text=TXT_STATUS_SCANNING)
        self.progress['value'] = 0
        
        def scan_manager():
            files_to_scan = []
            for root, dirs, files in os.walk(folder):
                for f in files:
                    _, ext = os.path.splitext(f)
                    if ext.lower() in ALL_EXTENSIONS:
                        files_to_scan.append(os.path.join(root, f))
            
            total = len(files_to_scan)
            self.ui_queue.put(("set_max", total))
            
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Enviar todas las tareas
                future_to_file = {executor.submit(self.process_single_file_scan, fp): fp for fp in files_to_scan}
                
                count = 0
                for future in concurrent.futures.as_completed(future_to_file):
                    try:
                        data = future.result()
                        results.append(data)
                        self.ui_queue.put(("add_item", data))
                    except Exception as e:
                        print(f"Error escaneando archivo: {e}")
                    
                    count += 1
                    if count % 5 == 0 or count == total: # Actualizar progreso cada pocos items
                        self.ui_queue.put(("progress", count))

            self.ui_queue.put(("scan_complete", results))

        Thread(target=scan_manager, daemon=True).start()

    def start_ui_updater(self):
        """Verifica la cola para actualizaciones de UI."""
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                cmd = msg[0]
                
                if cmd == "add_item":
                    self.insert_item(msg[1])
                elif cmd == "progress":
                    self.progress['value'] = msg[1]
                    self.lbl_status.config(text=f"{TXT_STATUS_SCANNING} {msg[1]}")
                elif cmd == "set_max":
                    self.progress['maximum'] = msg[1]
                elif cmd == "scan_complete":
                    self.files_data = msg[1]
                    self.finalize_scan()
                elif cmd == "update_status":
                    self.update_item_status_ui(msg[1], msg[2])
                elif cmd == "process_complete":
                     self.lbl_status.config(text=TXT_STATUS_DONE)
                     messagebox.showinfo(APP_NAME, "Proceso finalizado correctamente.")
                     self.btn_process.config(state=DISABLED)

        except queue.Empty:
            pass
        finally:
            self.after(100, self.start_ui_updater)

    def insert_item(self, item_data):
        d_name_str = item_data["date_name"].strftime("%Y-%m-%d %H:%M:%S") if item_data["date_name"] else "---"
        d_meta_str = item_data["date_meta"].strftime("%Y-%m-%d %H:%M:%S") if item_data["date_meta"] else "---"
        
        tags = ("secondary",)
        st = item_data["status"]
        
        if STATUS_CORRUPT in st: tags = ("danger",)
        elif STATUS_MATCH in st or STATUS_MATCH_DATE in st or STATUS_FS_MATCH in st: tags = ("success",)
        elif item_data["action_needed"]: tags = ("warning",)
        
        item_id = self.tree.insert("", END, values=(item_data["filename"], d_name_str, d_meta_str, st), tags=tags)
        item_data["iid"] = item_id

    def finalize_scan(self):
        total = len(self.files_data)
        self.lbl_status.config(text=f"Total: {total}")
        
        items_to_fix = [x for x in self.files_data if x["action_needed"]]
        if items_to_fix:
            self.btn_process.config(state=NORMAL, text=f"{TXT_BTN_PROCESS} ({len(items_to_fix)})")
        else:
            self.btn_process.config(state=DISABLED, text=TXT_NO_ISSUES)

    def process_single_file_fix(self, item):
        """Trabajador para arreglar un archivo único."""
        res_status = item["status"]
        
        # 1. Reparar
        if item.get("needs_repair"):
            if self.repair_tool.repair_file(item["filepath"]):
                res_status = "Reparado"
            else:
                return "Error Reparación"

        # 2. Actualizar Meta
        if item["date_name"]:
            if self.media_manager.update_metadata_date(item["filepath"], item["date_name"]):
                res_status = "Corregido"
            else:
                if not item.get("needs_repair"): # Si solo era arreglo de fecha y falló
                    res_status = "Error Meta"
        
        return res_status

    def start_processing(self):
        self.btn_process.config(state=DISABLED)
        items_to_fix = [x for x in self.files_data if x["action_needed"]]
        total = len(items_to_fix)
        self.progress['value'] = 0
        self.progress['maximum'] = total
        self.lbl_status.config(text=TXT_STATUS_PROCESSING)
        
        def process_manager():
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_item = {executor.submit(self.process_single_file_fix, item): item for item in items_to_fix}
                
                count = 0
                for future in concurrent.futures.as_completed(future_to_item):
                    item = future_to_item[future]
                    try:
                        new_status = future.result()
                        self.ui_queue.put(("update_status", item, new_status))
                    except Exception as e:
                        print(f"Error processing {item['filename']}: {e}")
                    
                    count += 1
                    self.ui_queue.put(("progress", count))
            
            self.ui_queue.put(("process_complete",))

        Thread(target=process_manager, daemon=True).start()

    def update_item_status_ui(self, item, status):
        d_name_str = item["date_name"].strftime("%Y-%m-%d %H:%M:%S") if item["date_name"] else "---"
        d_meta_str = d_name_str if status == "Corregido" else "Error"
        if status == "Reparado": d_meta_str = "---"

        self.tree.item(item["iid"], values=(item["filename"], d_name_str, d_meta_str, status))
        
        tags = ("secondary",)
        if status == "Corregido" or status == "Reparado": tags = ("success",)
        elif "Error" in status: tags = ("danger",)
        
        self.tree.item(item["iid"], tags=tags)