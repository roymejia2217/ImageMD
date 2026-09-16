import piexif
import os
import shutil
import logging
import re
from datetime import datetime, timezone
import ffmpeg
from PIL import Image as PILImage
from . import config
from .domain.temporal import DateCandidate, DateSource

# Etiquetas EXIF
DATETIME_ORIGINAL = 36867
DATETIME_DIGITIZED = 36868
DATETIME_MODIFIED = 306


class MediaMetadataManager:
    def __init__(
        self,
        *,
        ffmpeg_executable: str | None = None,
        ffprobe_executable: str | None = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.ffmpeg_executable = (
            config.FFMPEG_EXECUTABLE if ffmpeg_executable is None else ffmpeg_executable
        )
        self.ffprobe_executable = (
            config.FFPROBE_EXECUTABLE
            if ffprobe_executable is None
            else ffprobe_executable
        )
        self._ffmpeg_available = shutil.which(self.ffmpeg_executable) is not None
        self._ffprobe_available = shutil.which(self.ffprobe_executable) is not None
        if not self._ffmpeg_available:
            self.logger.warning(
                "FFmpeg not found. Video metadata updates will be limited to filesystem timestamps."
            )

    @property
    def ffmpeg_available(self) -> bool:
        return self._ffmpeg_available

    @ffmpeg_available.setter
    def ffmpeg_available(self, available: bool) -> None:
        # Keep the legacy test/integration toggle meaningful for both video operations.
        self._ffmpeg_available = bool(available)
        self._ffprobe_available = bool(available)

    @property
    def ffprobe_available(self) -> bool:
        return self._ffprobe_available

    @ffprobe_available.setter
    def ffprobe_available(self, available: bool) -> None:
        self._ffprobe_available = bool(available)

    def get_metadata_date(
        self, filepath: str, skip_deep_scan: bool = False
    ) -> datetime | None:
        """
        Lee la fecha de los metadatos del archivo (EXIF para imágenes, Metadata para videos).
        Recurre a un escaneo profundo si los métodos estándar fallan, a menos que skip_deep_scan sea True.
        """
        result = self._read_metadata_date(filepath, skip_deep_scan=skip_deep_scan)
        if result is None:
            return None
        date, _source = result
        # Compatibility: the legacy API has always returned wall-clock values
        # without timezone information, including video creation_time values.
        return date.replace(tzinfo=None) if date.tzinfo is not None else date

    def get_metadata_candidate(
        self,
        filepath: str,
        *,
        standard_confidence: int,
        deep_scan_confidence: int,
    ) -> DateCandidate | None:
        """Read metadata once and retain its origin and temporal semantics."""
        result = self._read_metadata_date(filepath, skip_deep_scan=False)
        if result is None:
            return None

        date, source = result
        confidence = (
            deep_scan_confidence
            if source is DateSource.DEEP_SCAN
            else standard_confidence
        )
        return DateCandidate(
            observed_at=date,
            source=source,
            confidence=confidence,
            evidence=f"source:{source.value}",
        )

    def _read_metadata_date(
        self, filepath: str, *, skip_deep_scan: bool
    ) -> tuple[datetime, DateSource] | None:
        """Run the existing metadata fallback order once, retaining provenance."""
        date = None
        source = DateSource.EXIF
        if self._is_supported_non_jpg(filepath):
            date = self._get_non_jpg_date(filepath, silent=True)
            if not date:  # Intentar lógica JPG por si está mal nombrado
                date = self._get_jpg_date(filepath, silent=True)
        elif self._is_jpg_tiff(filepath):
            date = self._get_jpg_date(filepath, silent=True)
            if not date:  # Intentar lógica PNG por si está mal nombrado
                date = self._get_non_jpg_date(filepath, silent=True)
            return (date, source) if date else None
        elif self._is_video(filepath):
            date = self._get_video_date(filepath)
            source = DateSource.VIDEO_METADATA

        # Verificación de cordura: Si la fecha es extremadamente antigua (probablemente corrupta o timestamp 0 por defecto), ignorarla.
        # Se asume que fechas <= 1970 no son válidas para este contexto.
        if date and date.year <= 1970:
            self.logger.warning(
                f"Ignored implausible date {date} from standard metadata for {filepath}"
            )
            date = None

        if date:
            return date, source

        if skip_deep_scan:
            return None

        # Respaldo: Escaneo Profundo
        date = self._deep_scan_date(filepath)
        return (date, DateSource.DEEP_SCAN) if date else None

    def _deep_scan_date(self, filepath: str) -> datetime | None:
        """
        Realiza un escaneo profundo del encabezado del archivo (primeros 64KB) buscando cadenas de fecha.
        Útil para encontrar XMP incrustado, fechas en texto crudo o metadatos oscuros.
        """
        try:
            with open(filepath, "rb") as f:
                header = f.read(65536)  # Leer 64KB

            # Patrones Regex para bytes
            # 1. YYYY:MM:DD HH:MM:SS (Estilo EXIF estándar en bytes)
            p1 = re.compile(
                rb"(\d{4})[:.-](\d{2})[:.-](\d{2})[ \tT](\d{2})[:.-](\d{2})[:.-](\d{2})"
            )

            # 2. YYYY-MM-DDTHH:MM:SS (Estilo ISO a menudo en XMP)
            p2 = re.compile(rb"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")

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
                self.logger.info(
                    f"Deep scan found date for {os.path.basename(filepath)}: {matches[0]}"
                )
                return matches[0]

        except Exception as e:
            self.logger.debug(f"Deep scan failed for {filepath}: {e}")

        return None

    def write_metadata_to_stage(
        self, source_path: str, staged_path: str, new_date: datetime
    ) -> bool:
        """Write updated metadata to a separate staged file, preserving source."""
        if not os.path.isabs(source_path) or not os.path.isabs(staged_path):
            self.logger.error("Source and staged paths must be absolute")
            return False

        source = os.path.realpath(source_path)
        staged = os.path.realpath(staged_path)
        if source == staged:
            self.logger.error("Source and staged paths must be different")
            return False

        try:
            if self._is_jpg_tiff(source_path):
                shutil.copy2(source_path, staged_path)
                return self._update_jpg_date(staged_path, new_date, silent=True)

            if self._is_supported_non_jpg(source_path):
                date_str = new_date.strftime("%Y:%m:%d %H:%M:%S")
                with PILImage.open(source_path) as image:
                    exif = image.getexif()
                    exif[DATETIME_MODIFIED] = date_str
                    exif[DATETIME_ORIGINAL] = date_str
                    exif[DATETIME_DIGITIZED] = date_str
                    save_format = image.format if image.format else "PNG"
                    image.save(staged_path, format=save_format, exif=exif)
                return True

            if self._is_video(source_path):
                if new_date.tzinfo is None or new_date.utcoffset() is None:
                    self.logger.error("Video metadata date must be timezone-aware")
                    return False
                if (
                    os.path.splitext(source_path)[1].lower()
                    != os.path.splitext(staged_path)[1].lower()
                ):
                    self.logger.error("Source and staged video extensions must match")
                    return False
                if not self.ffmpeg_available:
                    self.logger.error("FFmpeg not available for video update.")
                    return False

                utc_date = new_date.astimezone(timezone.utc)
                date_str = utc_date.strftime("%Y-%m-%dT%H:%M:%SZ")
                (
                    ffmpeg.input(source_path)
                    .output(
                        staged_path,
                        **{
                            "metadata": f"creation_time={date_str}",
                            "c": "copy",
                            "map": 0,
                        },
                    )
                    .overwrite_output()
                    .run(quiet=True, cmd=self.ffmpeg_executable)
                )
                return os.path.isfile(staged_path)
        except Exception as error:
            self.logger.error("Unable to write staged metadata: %s", error)
            return False

        self.logger.error("Unsupported media type for staged metadata")
        return False

    def update_metadata_date(self, filepath: str, new_date: datetime) -> bool:
        """Reject legacy in-place updates.

        Callers must obtain an approved decision and use
        ``write_metadata_to_stage`` through ``MetadataApplyService``.  Keeping
        this public compatibility entrypoint non-mutating prevents an older
        caller from bypassing backup, digest and atomic-replace guarantees.
        """
        del new_date
        self.logger.error(
            "Refusing direct metadata update for %s; use the transactional apply service",
            filepath,
        )
        return False

    def _is_jpg_tiff(self, filepath: str) -> bool:
        return filepath.lower().endswith((".jpg", ".jpeg", ".tiff", ".tif"))

    def _is_supported_non_jpg(self, filepath: str) -> bool:
        return filepath.lower().endswith((".png", ".webp", ".bmp"))

    def _is_video(self, filepath: str) -> bool:
        return filepath.lower().endswith((".mp4", ".mov", ".mkv", ".avi"))

    # --- Lógica JPG/TIFF (piexif) ---
    def _get_jpg_date(self, filepath: str, silent: bool = False) -> datetime | None:
        try:
            exif_dict = piexif.load(filepath)
            date_str = None

            # Priorizar DateTimeOriginal
            if (
                "Exif" in exif_dict
                and piexif.ExifIFD.DateTimeOriginal in exif_dict["Exif"]
            ):
                date_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode(
                    "utf-8"
                )
            elif "0th" in exif_dict and piexif.ImageIFD.DateTime in exif_dict["0th"]:
                date_str = exif_dict["0th"][piexif.ImageIFD.DateTime].decode("utf-8")

            if date_str:
                try:
                    return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    return None
        except Exception as e:
            if not silent:
                # Verificar si es un PNG disfrazado de JPG
                if "neither JPEG nor TIFF" in str(e):
                    self.logger.warning(
                        f"File {filepath} has JPG extension but might be PNG/Invalid. Skipping metadata read."
                    )
                else:
                    self.logger.warning(f"Error reading JPG metadata {filepath}: {e}")
        return None

    def _update_jpg_date(
        self, filepath: str, new_date: datetime, silent: bool = False
    ) -> bool:
        try:
            date_str = new_date.strftime("%Y:%m:%d %H:%M:%S")
            try:
                exif_dict = piexif.load(filepath)
            except Exception as e:
                if not silent:
                    self.logger.warning(
                        f"Could not load existing EXIF for {filepath}, creating new: {e}"
                    )
                # Crear estructura mínima si la carga falló pero aún queremos escribir
                exif_dict = {
                    "0th": {},
                    "Exif": {},
                    "GPS": {},
                    "1st": {},
                    "thumbnail": None,
                }

            if "Exif" not in exif_dict:
                exif_dict["Exif"] = {}
            if "0th" not in exif_dict:
                exif_dict["0th"] = {}

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
                self.logger.warning(
                    f"Error reading PNG metadata (Pillow) {filepath}: {e}"
                )

        return None

    def _update_non_jpg_date(
        self, filepath: str, new_date: datetime, silent: bool = False
    ) -> bool:
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
                save_format = img.format if img.format else "PNG"

                img.save(filepath, format=save_format, exif=exif)
            return True
        except Exception as e:
            if not silent:
                self.logger.error(f"Error updating metadata {filepath}: {e}")
            return False

    # --- Lógica de Video ---
    def _get_video_date(self, filepath: str) -> datetime | None:
        if not self.ffprobe_available:
            return None

        try:
            probe = ffmpeg.probe(filepath, cmd=self.ffprobe_executable)
            # Intentar encontrar creation_time en etiquetas de formato o stream
            creation_time = None

            if "format" in probe and "tags" in probe["format"]:
                creation_time = probe["format"]["tags"].get("creation_time")

            if not creation_time:
                for stream in probe["streams"]:
                    if "tags" in stream:
                        creation_time = stream["tags"].get("creation_time")
                        if creation_time:
                            break

            if creation_time:
                # FFmpeg a menudo retorna ISO 8601 como '2023-01-01T12:00:00.000000Z'
                # o '2023-01-01 12:00:00'
                try:
                    # Preserve offsets in the candidate API. The legacy API
                    # strips tzinfo at its compatibility boundary.
                    dt = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
                    return dt
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
                ffmpeg.input(filepath)
                .output(
                    temp_output,
                    **{"metadata": f"creation_time={date_str}", "c": "copy", "map": 0},
                )
                .overwrite_output()
                .run(quiet=True, cmd=self.ffmpeg_executable)
            )

            # Si exitoso, reemplazar original
            if os.path.exists(temp_output):
                try:
                    shutil.copystat(filepath, temp_output)
                except OSError:
                    pass
                os.remove(filepath)
                os.rename(temp_output, filepath)
                return True

        except ffmpeg.Error as e:
            self.logger.error(
                f"FFmpeg error updating {filepath}: {e.stderr.decode('utf8') if e.stderr else e}"
            )
            if os.path.exists(temp_output):
                os.remove(temp_output)
        except Exception as e:
            self.logger.error(f"Error updating video metadata {filepath}: {e}")
            if os.path.exists(temp_output):
                os.remove(temp_output)

        return False
