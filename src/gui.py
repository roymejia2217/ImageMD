from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import (
    BOTH,
    DISABLED,
    END,
    HORIZONTAL,
    INFO,
    LEFT,
    NORMAL,
    PRIMARY,
    RIGHT,
    SUCCESS,
    VERTICAL,
    X,
    Y,
)
from threading import Thread
import concurrent.futures
import os
import queue
from zoneinfo import ZoneInfo
from .config import (
    ALL_EXTENSIONS,
    APP_NAME,
    AUTOMATIC_WRITE_CONFIDENCE,
    BACKUP_SUFFIX,
    DATE_TOLERANCE_SECONDS,
    DEEP_SCAN_CONFIDENCE,
    FILENAME_CONFIDENCE,
    HELP_MSG_CORRUPT,
    HELP_MSG_MATCH,
    HELP_MSG_MATCH_DATE,
    HELP_MSG_MISMATCH,
    HELP_MSG_PRIORITY,
    STANDARD_METADATA_CONFIDENCE,
    STATUS_CORRUPT,
    STATUS_FS_MATCH,
    STATUS_MATCH,
    STATUS_MATCH_DATE,
    STATUS_MISMATCH,
    STATUS_NO_DATE,
    STATUS_NO_META,
    STATUS_REVIEW,
    THEME_NAME,
    TIMEZONE_NAME,
    TXT_BTN_PROCESS,
    TXT_BTN_SELECT,
    TXT_COL_DATE_META,
    TXT_COL_DATE_NAME,
    TXT_COL_FILE,
    TXT_COL_STATUS,
    TXT_NO_ISSUES,
    TXT_STATUS_DONE,
    TXT_STATUS_PROCESSING,
    TXT_STATUS_READY,
    TXT_STATUS_SCANNING,
)
from .date_utils import DateExtractor
from .media_ops import MediaMetadataManager
from .repair import ImageRepairTool
from .application.apply_metadata import ApplyKind, ApplyPolicy, MetadataApplyService
from .application.date_decision import DecisionKind, TemporalPolicy
from .application.repair_png import PngRepairService, RepairKind, RepairPolicy
from .application.scan_media import MediaScanService, ScanPolicy
from .application.scan_presentation import ScanPresentationKind, present_scan


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
        self.temporal_policy = TemporalPolicy(
            timezone=ZoneInfo(TIMEZONE_NAME),
            tolerance_seconds=DATE_TOLERANCE_SECONDS,
            automatic_write_confidence=AUTOMATIC_WRITE_CONFIDENCE,
        )
        self.apply_service = MetadataApplyService(
            self.media_manager, ApplyPolicy(self.temporal_policy, BACKUP_SUFFIX)
        )
        self.scan_service = MediaScanService(
            self.date_extractor,
            self.media_manager,
            self.temporal_policy,
            ScanPolicy(
                FILENAME_CONFIDENCE,
                STANDARD_METADATA_CONFIDENCE,
                DEEP_SCAN_CONFIDENCE,
            ),
        )
        self.repair_service = PngRepairService(policy=RepairPolicy(BACKUP_SUFFIX))

        self.files_data = []
        self.ui_queue = queue.Queue()

        # Pool de hilos para escaneo de alto rendimiento
        # Usando un número razonable de trabajadores (CPU * 2 es heurística común para mezcla I/O)
        self.max_workers = min(32, (os.cpu_count() or 4) * 4)

        self.setup_ui()
        self.start_ui_updater()

        if not self.media_manager.ffmpeg_available:
            self.status_log(
                "Advertencia: FFmpeg no detectado. Soporte de video limitado.",
                "warning",
            )

    def setup_ui(self):
        # Marco Superior: Controles
        control_frame = ttk.Frame(self, padding=10)
        control_frame.pack(fill=X)

        self.btn_select = ttk.Button(
            control_frame,
            text=TXT_BTN_SELECT,
            command=self.select_folder,
            bootstyle=PRIMARY,
        )
        self.btn_select.pack(side=LEFT, padx=5)

        self.btn_process = ttk.Button(
            control_frame,
            text=TXT_BTN_PROCESS,
            command=self.start_processing,
            bootstyle=SUCCESS,
            state=DISABLED,
        )
        self.btn_process.pack(side=LEFT, padx=5)

        self.lbl_status = ttk.Label(control_frame, text=TXT_STATUS_READY)
        self.lbl_status.pack(side=LEFT, padx=15)

        # Leyenda/Ayuda
        help_btn = ttk.Button(
            control_frame,
            text="?",
            command=self.show_help,
            bootstyle="secondary-outline",
            width=3,
        )
        help_btn.pack(side=RIGHT, padx=5)

        # Marco Principal: Vista de Árbol
        tree_frame = ttk.Frame(self, padding=10)
        tree_frame.pack(fill=BOTH, expand=True)

        columns = ("filename", "date_name", "date_meta", "status")
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="extended"
        )

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
        self.progress = ttk.Progressbar(
            self, orient=HORIZONTAL, mode="determinate", bootstyle=INFO
        )
        self.progress.pack(fill=X, padx=10, pady=5)

    def status_log(self, message, level="info"):
        print(f"[{level.upper()}] {message}")  # Registro en consola
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
        if filename.lower().endswith(".png"):
            if self.repair_tool.is_corrupted_png(filepath):
                is_corrupted = True

        scan = self.scan_service.scan(filename, filepath)
        filename_candidate = scan.preferred_candidate
        metadata_candidate = scan.observed_candidate
        date_from_name = filename_candidate.observed_at if filename_candidate else None
        date_from_meta = metadata_candidate.observed_at if metadata_candidate else None
        presentation = present_scan(scan, is_corrupted=is_corrupted)
        status_by_kind = {
            ScanPresentationKind.CORRUPT: STATUS_CORRUPT,
            ScanPresentationKind.MATCH: STATUS_MATCH,
            ScanPresentationKind.MISMATCH: STATUS_MISMATCH,
            ScanPresentationKind.NO_METADATA: STATUS_NO_META,
            ScanPresentationKind.REVIEW_REQUIRED: STATUS_REVIEW,
            ScanPresentationKind.NO_DATE: STATUS_NO_DATE,
        }

        return {
            "filepath": filepath,
            "filename": filename,
            "date_name": date_from_name,
            "date_candidate": filename_candidate,
            "decision": scan.decision,
            "date_meta": date_from_meta,
            "status": status_by_kind[presentation.kind],
            "action_needed": presentation.action_needed,
            "needs_repair": presentation.needs_repair,
            "iid": None,
        }

    def load_files_parallel(self, folder):
        self.tree.delete(*self.tree.get_children())
        self.files_data = []
        self.btn_process.config(state=DISABLED)
        self.lbl_status.config(text=TXT_STATUS_SCANNING)
        self.progress["value"] = 0

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
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                # Enviar todas las tareas
                future_to_file = {
                    executor.submit(self.process_single_file_scan, fp): fp
                    for fp in files_to_scan
                }

                count = 0
                for future in concurrent.futures.as_completed(future_to_file):
                    try:
                        data = future.result()
                        results.append(data)
                        self.ui_queue.put(("add_item", data))
                    except Exception as e:
                        print(f"Error escaneando archivo: {e}")

                    count += 1
                    if (
                        count % 5 == 0 or count == total
                    ):  # Actualizar progreso cada pocos items
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
                    self.progress["value"] = msg[1]
                    self.lbl_status.config(text=f"{TXT_STATUS_SCANNING} {msg[1]}")
                elif cmd == "set_max":
                    self.progress["maximum"] = msg[1]
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
        d_name_str = (
            item_data["date_name"].strftime("%Y-%m-%d %H:%M:%S")
            if item_data["date_name"]
            else "---"
        )
        d_meta_str = (
            item_data["date_meta"].strftime("%Y-%m-%d %H:%M:%S")
            if item_data["date_meta"]
            else "---"
        )

        tags = ("secondary",)
        st = item_data["status"]

        if STATUS_CORRUPT in st:
            tags = ("danger",)
        elif STATUS_MATCH in st or STATUS_MATCH_DATE in st or STATUS_FS_MATCH in st:
            tags = ("success",)
        elif item_data["action_needed"]:
            tags = ("warning",)

        item_id = self.tree.insert(
            "",
            END,
            values=(item_data["filename"], d_name_str, d_meta_str, st),
            tags=tags,
        )
        item_data["iid"] = item_id

    def finalize_scan(self):
        total = len(self.files_data)
        self.lbl_status.config(text=f"Total: {total}")

        items_to_fix = [x for x in self.files_data if x["action_needed"]]
        if items_to_fix:
            self.btn_process.config(
                state=NORMAL, text=f"{TXT_BTN_PROCESS} ({len(items_to_fix)})"
            )
        else:
            self.btn_process.config(state=DISABLED, text=TXT_NO_ISSUES)

    def process_single_file_fix(self, item):
        """Trabajador para arreglar un archivo único."""
        res_status = item["status"]

        decision = item["decision"]

        # 1. Reparar con staging, verificación y backup.
        if item.get("needs_repair"):
            repaired = self.repair_service.repair(item["filepath"])
            if repaired.kind is RepairKind.REPAIRED:
                res_status = "Reparado"
                decision = self.scan_service.scan(
                    item["filename"], item["filepath"]
                ).decision
            else:
                return "Error Reparación"

        # 2. Aplicar exclusivamente una decisión aprobada por el planificador.
        if decision.kind is DecisionKind.PROPOSE_UPDATE:
            applied = self.apply_service.apply(item["filepath"], decision)
            if applied.kind is ApplyKind.APPLIED:
                res_status = (
                    "Corregido"
                    if not item.get("needs_repair")
                    else "Reparado y corregido"
                )
            elif not item.get("needs_repair"):
                res_status = "Error Meta"
        elif decision.kind is DecisionKind.REQUIRE_REVIEW and not item.get(
            "needs_repair"
        ):
            res_status = "Revisión requerida"

        return res_status

    def start_processing(self):
        self.btn_process.config(state=DISABLED)
        items_to_fix = [x for x in self.files_data if x["action_needed"]]
        total = len(items_to_fix)
        self.progress["value"] = 0
        self.progress["maximum"] = total
        self.lbl_status.config(text=TXT_STATUS_PROCESSING)

        def process_manager():
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                future_to_item = {
                    executor.submit(self.process_single_file_fix, item): item
                    for item in items_to_fix
                }

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
        d_name_str = (
            item["date_name"].strftime("%Y-%m-%d %H:%M:%S")
            if item["date_name"]
            else "---"
        )
        d_meta_str = d_name_str if status == "Corregido" else "Error"
        if status == "Reparado":
            d_meta_str = "---"

        self.tree.item(
            item["iid"], values=(item["filename"], d_name_str, d_meta_str, status)
        )

        tags = ("secondary",)
        if status == "Corregido" or status == "Reparado":
            tags = ("success",)
        elif "Error" in status:
            tags = ("danger",)

        self.tree.item(item["iid"], tags=tags)
