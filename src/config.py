# src/config.py
import os

# --- Información de la Aplicación ---
APP_NAME = "ImageMD"
INITIAL_SIZE = (1100, 700)  # Predeterminado, el código maneja el redimensionamiento
THEME_NAME = "darkly"

# La zona se inyecta por entorno para que la política temporal sea desplegable y
# auditable; el valor por defecto conserva el contexto histórico del proyecto.
TIMEZONE_NAME = os.environ.get("IMAGEMD_TIMEZONE", "America/Guayaquil")
FFMPEG_EXECUTABLE = os.environ.get("IMAGEMD_FFMPEG_EXECUTABLE", "ffmpeg")
FFPROBE_EXECUTABLE = os.environ.get("IMAGEMD_FFPROBE_EXECUTABLE", "ffprobe")
FILENAME_CONFIDENCE = 95
STANDARD_METADATA_CONFIDENCE = 90
DEEP_SCAN_CONFIDENCE = 30
AUTOMATIC_WRITE_CONFIDENCE = 90
DATE_TOLERANCE_SECONDS = 60
BACKUP_SUFFIX = ".bak"

# --- Extensiones Soportadas ---
IMG_EXTENSIONS = {".jpg", ".jpeg", ".tiff", ".tif", ".png", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
ALL_EXTENSIONS = IMG_EXTENSIONS | VIDEO_EXTENSIONS

# --- Configuración de Análisis de Fechas ---
# Mapeo de meses para español e inglés (extensible)
MONTH_MAP = {
    # Español
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
    # Inglés
    "jan": 1,
    "apr": 4,
    "aug": 8,
    "dec": 12,
}

# --- Constantes de Texto UI ---
TXT_BTN_SELECT = "Abrir"
TXT_BTN_PROCESS = "Procesar"
TXT_STATUS_READY = "Listo"
TXT_STATUS_SCANNING = "Analizando..."
TXT_STATUS_PROCESSING = "Procesando..."
TXT_STATUS_DONE = "Finalizado"
TXT_COL_FILE = "Archivo"
TXT_COL_DATE_NAME = "Fecha (Nombre)"
TXT_COL_DATE_META = "Fecha (Meta)"
TXT_COL_STATUS = "Estado"
TXT_NO_ISSUES = "Sin acciones pendientes"

# --- Mensajes de Estado ---
STATUS_MATCH = "Correcto"
STATUS_MATCH_DATE = "Fecha OK"
STATUS_CORRUPT = "DAÑADO"
STATUS_MISMATCH = "Difiere"
STATUS_NO_META = "Sin Meta"
STATUS_FS_MATCH = "FS OK"
STATUS_FS_MISMATCH = "FS Difiere"
STATUS_1970 = "Epoch 1970"
STATUS_NO_DATE = "---"
STATUS_REVIEW = "Revisión requerida"

# --- Textos de Ayuda ---
HELP_MSG_MATCH = "Fechas idénticas."
HELP_MSG_MATCH_DATE = "Fecha igual, hora conservada."
HELP_MSG_MISMATCH = "Se usará fecha del nombre."
HELP_MSG_CORRUPT = "Archivo dañado."
HELP_MSG_PRIORITY = "Prioridad: Fecha en Nombre > Metadatos"
