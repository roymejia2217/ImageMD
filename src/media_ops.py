import piexif
import os
import shutil
import logging
import re
from datetime import datetime
import subprocess
import ffmpeg
from PIL import Image as PILImage
from PIL.ExifTags import TAGS

# Etiquetas EXIF
DATETIME_ORIGINAL = 36867
DATETIME_DIGITIZED = 36868
DATETIME_MODIFIED = 306

class MediaMetadataManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.ffmpeg_available = shutil.which("ffmpeg") is not None
        if not self.ffmpeg_available:
            self.logger.warning("FFmpeg not found. Video metadata updates will be limited to filesystem timestamps.")

    def get_metadata_date(self, filepath: str, skip_deep_scan: bool = False) -> datetime | None:
        """
        Lee la fecha de los metadatos del archivo (EXIF para imágenes, Metadata para videos).
        Recurre a un escaneo profundo si los métodos estándar fallan, a menos que skip_deep_scan sea True.
        """
        date = None
        if self._is_supported_non_jpg(filepath):
            date = self._get_non_jpg_date(filepath, silent=True)
            if not date: # Intentar lógica JPG por si está mal nombrado
                date = self._get_jpg_date(filepath, silent=True)
        elif self._is_jpg_tiff(filepath):
            date = self._get_jpg_date(filepath, silent=True)
            if not date: # Intentar lógica PNG por si está mal nombrado
                date = self._get_non_jpg_date(filepath, silent=True)
            return date
        elif self._is_video(filepath):
            date = self._get_video_date(filepath)
        
        # Verificación de cordura: Si la fecha es extremadamente antigua (probablemente corrupta o timestamp 0 por defecto), ignorarla.
        # Se asume que fechas <= 1970 no son válidas para este contexto.
        if date and date.year <= 1970:
            self.logger.warning(f"Ignored implausible date {date} from standard metadata for {filepath}")
            date = None
            
        if date:
            return date
            
        if skip_deep_scan:
            return None
            
        # Respaldo: Escaneo Profundo
        return self._deep_scan_date(filepath)

    def _deep_scan_date(self, filepath: str) -> datetime | None:
        """
        Realiza un escaneo profundo del encabezado del archivo (primeros 64KB) buscando cadenas de fecha.
        Útil para encontrar XMP incrustado, fechas en texto crudo o metadatos oscuros.
        """
        try:
            with open(filepath, 'rb') as f:
                header = f.read(65536) # Leer 64KB
                
            # Patrones Regex para bytes
            # 1. YYYY:MM:DD HH:MM:SS (Estilo EXIF estándar en bytes)
            p1 = re.compile(rb'(\d{4})[:.-](\d{2})[:.-](\d{2})[ \tT](\d{2})[:.-](\d{2})[:.-](\d{2})')
            
            # 2. YYYY-MM-DDTHH:MM:SS (Estilo ISO a menudo en XMP)
            p2 = re.compile(rb'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})')

            matches = []
            
            for p in [p1, p2]:
                for m in p.finditer(header):
                    try:
                        groups = [int(g) for g in m.groups()]
                        dt = datetime(*groups)
                        # Filtro de cordura: Año entre 1990 y actual+1
                        current_year = datetime.now().year
                        if 1990 <= dt.year <= current_year + 1:
                            matches.append(dt)
                    except ValueError:
                        continue
            
            if matches:
                # Retornar la fecha plausible más antigua encontrada (a menudo "Original" es la más antigua)
                # Pero a veces 'Modified' es posterior. Usualmente bloques de metadatos inician con creación.
                # Ordenar por fecha nos permite elegir una estrategia.
                # Elijamos la más antigua como "Fecha de Creación".
                matches.sort()
                self.logger.info(f"Deep scan found date for {os.path.basename(filepath)}: {matches[0]}")
                return matches[0]

        except Exception as e:
            self.logger.debug(f"Deep scan failed for {filepath}: {e}")
            
        return None

    def update_metadata_date(self, filepath: str, new_date: datetime) -> bool:
        """
        Actualiza la fecha de metadatos para imágenes o videos.
        También actualiza timestamps del sistema de archivos.
        Retorna True si al menos el timestamp del sistema de archivos fue actualizado (mejor esfuerzo).
        """
        meta_success = False
        fs_success = False
        
        if self._is_supported_non_jpg(filepath):
            meta_success = self._update_non_jpg_date(filepath, new_date, silent=True)
        elif self._is_jpg_tiff(filepath):
            meta_success = self._update_jpg_date(filepath, new_date, silent=True)
        elif self._is_video(filepath):
            meta_success = self._update_video_date(filepath, new_date)
        
        # Siempre actualizar timestamps del sistema de archivos si es posible
        if os.path.exists(filepath):
            try:
                ts = new_date.timestamp()
                os.utime(filepath, (ts, ts))
                fs_success = True
            except Exception as e:
                self.logger.error(f"Error updating filesystem timestamp for {filepath}: {e}")
        
        # Log final si todo falló
        if not meta_success and not fs_success:
            self.logger.error(f"Total failure updating metadata or filesystem for {filepath}")

        return meta_success or fs_success

    def _is_jpg_tiff(self, filepath: str) -> bool:
        return filepath.lower().endswith(('.jpg', '.jpeg', '.tiff', '.tif'))

    def _is_supported_non_jpg(self, filepath: str) -> bool:
        return filepath.lower().endswith(('.png', '.webp', '.bmp'))

    def _is_video(self, filepath: str) -> bool:
        return filepath.lower().endswith(('.mp4', '.mov', '.mkv', '.avi'))

    # --- Lógica JPG/TIFF (piexif) ---
    def _get_jpg_date(self, filepath: str, silent: bool = False) -> datetime | None:
        try:
            exif_dict = piexif.load(filepath)
            date_str = None
            
            # Priorizar DateTimeOriginal
            if "Exif" in exif_dict and piexif.ExifIFD.DateTimeOriginal in exif_dict["Exif"]:
                date_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode('utf-8')
            elif "0th" in exif_dict and piexif.ImageIFD.DateTime in exif_dict["0th"]:
                 date_str = exif_dict["0th"][piexif.ImageIFD.DateTime].decode('utf-8')
            
            if date_str:
                try:
                    return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    return None
        except Exception as e:
            if not silent:
                # Verificar si es un PNG disfrazado de JPG
                if "neither JPEG nor TIFF" in str(e):
                    self.logger.warning(f"File {filepath} has JPG extension but might be PNG/Invalid. Skipping metadata read.")
                else:
                    self.logger.warning(f"Error reading JPG metadata {filepath}: {e}")
        return None

    def _update_jpg_date(self, filepath: str, new_date: datetime, silent: bool = False) -> bool:
        try:
            date_str = new_date.strftime("%Y:%m:%d %H:%M:%S")
            try:
                exif_dict = piexif.load(filepath)
            except Exception as e:
                if not silent:
                    self.logger.warning(f"Could not load existing EXIF for {filepath}, creating new: {e}")
                # Crear estructura mínima si la carga falló pero aún queremos escribir
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

            if "Exif" not in exif_dict: exif_dict["Exif"] = {}
            if "0th" not in exif_dict: exif_dict["0th"] = {}

            # Verificación de seguridad: asegurar no sobrescribir con vacío si sospechamos corrupción
            # pero aquí asumimos que si llamamos update, QUEREMOS forzar la fecha.
            
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str
            exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str

            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, filepath)
            return True
        except Exception as e:
            if not silent:
                self.logger.error(f"Error updating JPG metadata {filepath}: {e}")
            return False

    # --- Lógica No-JPG (PNG, WEBP, BMP via librería exif + respaldo Pillow) ---
    def _get_non_jpg_date(self, filepath: str, silent: bool = False) -> datetime | None:
        # Método: Intentar Pillow (Soporta PNG, WEBP, BMP)
        try:
            with PILImage.open(filepath) as img:
                exif_data = img.getexif()
                if exif_data:
                    # 36867 es DateTimeOriginal, 306 es DateTime
                    for tag_id in [36867, 306, 36868]:
                        date_str = exif_data.get(tag_id)
                        if date_str:
                            try:
                                return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                            except ValueError:
                                continue
        except Exception as e:
            if not silent:
                self.logger.warning(f"Error reading PNG metadata (Pillow) {filepath}: {e}")
        
        return None

    def _update_non_jpg_date(self, filepath: str, new_date: datetime, silent: bool = False) -> bool:
        date_str = new_date.strftime("%Y:%m:%d %H:%M:%S")
        
        # Método: Intentar Pillow (Soporta PNG, WEBP, BMP)
        try:
            with PILImage.open(filepath) as img:
                exif = img.getexif()
                # 306: DateTime, 36867: DateTimeOriginal, 36868: DateTimeDigitized
                exif[306] = date_str
                exif[36867] = date_str
                exif[36868] = date_str
                
                # Usar formato original si es posible, de lo contrario por defecto PNG si desconocido/no guardable
                save_format = img.format if img.format else 'PNG'
                
                img.save(filepath, format=save_format, exif=exif)
            return True
        except Exception as e:
            if not silent:
                self.logger.error(f"Error updating metadata {filepath}: {e}")
            return False

    # --- Lógica de Video ---
    def _get_video_date(self, filepath: str) -> datetime | None:
        if not self.ffmpeg_available:
            return None
        
        try:
            probe = ffmpeg.probe(filepath)
            # Intentar encontrar creation_time en etiquetas de formato o stream
            creation_time = None
            
            if 'format' in probe and 'tags' in probe['format']:
                creation_time = probe['format']['tags'].get('creation_time')
            
            if not creation_time:
                for stream in probe['streams']:
                    if 'tags' in stream:
                        creation_time = stream['tags'].get('creation_time')
                        if creation_time: break
            
            if creation_time:
                # FFmpeg a menudo retorna ISO 8601 como '2023-01-01T12:00:00.000000Z'
                # o '2023-01-01 12:00:00'
                try:
                    # Analizar y asegurar que sea naive para comparación consistente
                    dt = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                    return dt.replace(tzinfo=None)
                except ValueError:
                    try:
                        return datetime.strptime(creation_time, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        pass
        except Exception as e:
            self.logger.warning(f"Error reading video metadata {filepath}: {e}")
        return None

    def _update_video_date(self, filepath: str, new_date: datetime) -> bool:
        if not self.ffmpeg_available:
            self.logger.error("FFmpeg not available for video update.")
            return False

        temp_output = filepath + ".temp.mp4"
        try:
            # Forzar escritura de hora como UTC (Z) para que FFmpeg no la desplace.
            # Si queremos que 19:00 aparezca en el archivo como 19:00,
            # lo formateamos como ISO UTC.
            date_str = new_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # Usando ffmpeg-python para copiar stream y actualizar metadatos
            (
                ffmpeg
                .input(filepath)
                .output(temp_output, **{'metadata': f'creation_time={date_str}', 'c': 'copy', 'map': 0})
                .overwrite_output()
                .run(quiet=True)
            )
            
            # Si exitoso, reemplazar original
            if os.path.exists(temp_output):
                try:
                    shutil.copystat(filepath, temp_output)
                except:
                    pass
                os.remove(filepath)
                os.rename(temp_output, filepath)
                return True
                
        except ffmpeg.Error as e:
            self.logger.error(f"FFmpeg error updating {filepath}: {e.stderr.decode('utf8') if e.stderr else e}")
            if os.path.exists(temp_output):
                os.remove(temp_output)
        except Exception as e:
            self.logger.error(f"Error updating video metadata {filepath}: {e}")
            if os.path.exists(temp_output):
                os.remove(temp_output)
                
        return False