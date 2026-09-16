import re
from datetime import datetime, timezone
from .config import MONTH_MAP
from .domain.temporal import DateCandidate, DateSource


class DateExtractor:
    def __init__(self):
        self.month_map = MONTH_MAP

        self.patterns = [
            # 1. Imagen de Facebook con Unix Timestamp (ms)
            # Coincidencia: FB_IMG_1541718757550.jpg
            (re.compile(r"FB_IMG_(\d{13})", re.IGNORECASE), "UNIX_MS", True),
            # 2. WhatsApp Imagen/Video nuevo formato con hora
            # Coincidencia: WhatsApp Image 2025-05-09 at 07.17.11.jpeg
            (
                re.compile(
                    r"WhatsApp (?:Image|Video) (20\d{2})-(\d{2})-(\d{2}) at (\d{2})[\.:](\d{2})[\.:](\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d %H.%M.%S",
                True,
            ),
            # NUEVO: Formato WhatsApp Español
            # Coincidencia: Imagen de WhatsApp 2024-08-26 a las 17.24.54_97e752ef.jpg
            (
                re.compile(
                    r"Imagen de WhatsApp (20\d{2})-(\d{2})-(\d{2}) a las (\d{2})[\.:](\d{2})[\.:](\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d %H.%M.%S",
                True,
            ),
            # NUEVO: Captura de pantalla iOS (Inglés/Estándar)
            # Coincidencia: Screenshot 2023-01-25 at 19.00.00.png
            (
                re.compile(
                    r"Screenshot (20\d{2})-(\d{2})-(\d{2}) at (\d{2})[\.:](\d{2})[\.:](\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d %H.%M.%S",
                True,
            ),
            # NUEVO: Telegram / Genérico con separador guion bajo
            # Coincidencia: photo_2023-11-29_10-20-30.jpg, 2023-11-29_10-20-30.jpg
            (
                re.compile(
                    r"(?:^|[\s_])(20\d{2})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d_%H-%M-%S",
                True,
            ),
            # NUEVO: Signal Móvil (YYYY-MM-DD-HHMM)
            # Coincidencia: signal-2023-05-20-1430.jpg
            # Nota: Hora de 4 dígitos (HHMM)
            (
                re.compile(
                    r"signal-(20\d{2})-(\d{2})-(\d{2})-(\d{2})(\d{2})(?:\D|$)",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d-%H%M",
                True,
            ),
            # NUEVO: Signal Escritorio / Genérico (YYYY-MM-DD-HHMMSS)
            # Coincidencia: signal-2023-05-20-143055.jpg
            (
                re.compile(
                    r"(?:^|[\s_-])(20\d{2})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d-%H%M%S",
                True,
            ),
            # NUEVO: Captura de pantalla 'Screenshot from' YYYY-MM-DD HH-MM-SS
            # Coincidencia: Screenshot from 2020-05-20 11-26-28.png
            (
                re.compile(
                    r"Screenshot from (20\d{2})-(\d{2})-(\d{2})\s+(\d{2})-(\d{2})-(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d %H-%M-%S",
                True,
            ),
            # NUEVO: Adobe Scan DD MMM YYYY (Español/Inglés)
            # Coincidencia: Adobe Scan 04 abr 2024_1.jpg
            (
                re.compile(
                    r"Adobe Scan (\d{2}) ([a-zA-Z]{3}) (20\d{2})", re.IGNORECASE
                ),
                "DD_MMM_YYYY",
                False,
            ),
            # 3. Formato Portapapeles (YYYY-MM-DD_HH-MM)
            # Coincidencia: clipboard_2025-06-07_09-51.bmp
            (
                re.compile(
                    r"clipboard.*?(20\d{2})[-](\d{2})[-](\d{2})[_](\d{2})[-](\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d_%H-%M",
                True,
            ),
            # 4. Fecha-Hora separada por guiones (YYYY-MM-DD-HH-MM-SS)
            # Coincidencia: compressO-2025-08-09-20-16-36-904.mp4
            (
                re.compile(
                    r"(?:^|[\s_-])(20\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d-%H-%M-%S",
                True,
            ),
            # 5. Fecha separada por puntos, guion bajo, Hora separada por puntos
            # Coincidencia: com.whatsapp_Screenshot_2021.04.03_14.29.45.png
            (
                re.compile(
                    r"(?:^|[\s_.-])(20\d{2})\.(\d{2})\.(\d{2})_(\d{2})\.(\d{2})\.(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y.%m.%d_%H.%M.%S",
                True,
            ),
            # 6. Timestamp completo separado por guiones bajos
            # Coincidencia: Img_2024_05_13_13_45_01.jpeg
            (
                re.compile(
                    r"(?:^|[\s_.-])(20\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y_%m_%d_%H_%M_%S",
                True,
            ),
            # 7. Timestamp continuo de 14 dígitos (YYYYMMDDHHMMSS)
            # Coincidencia: icam365Record20251009095318851.mp4
            # Precedido por no-dígito o inicio.
            (
                re.compile(
                    r"(?:^|\D)(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y%m%d%H%M%S",
                True,
            ),
            # 8. Timestamp continuo de 12 dígitos (YYYYMMDDHHMM)
            # Coincidencia: 202509180735.mp4
            # Verificación estricta de límite al final para evitar coincidencias parciales de números más largos
            (
                re.compile(
                    r"(?:^|\D)(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\D|$)",
                    re.IGNORECASE,
                ),
                "%Y%m%d%H%M",
                True,
            ),
            # 9. Captura de pantalla con timestamp completo
            # Coincidencia: Screenshot_20250515_130301_WhatsApp.jpg, Screenshot_20250515-130301.png
            (
                re.compile(
                    r"Screenshot[-_]?(20\d{2})(\d{2})(\d{2})[-_]?(\d{2})(\d{2})(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y%m%d%H%M%S",
                True,
            ),
            # 6. Fecha-Hora con dígitos de tiempo continuos (e.g. YYYY-MM-DD-HHMMSSmmm)
            # Coincidencia: 2021-11-21-212055102.mp4, 2021-11-21 212055.jpg
            (
                re.compile(
                    r"(?:^|[\s_-])(20\d{2})[-_.](\d{2})[-_.](\d{2})[\s_-]+(\d{2})(\d{2})(\d{2})(?:\d+)?(?:[._-]|$)",
                    re.IGNORECASE,
                ),
                "%Y-%m-%d %H%M%S",
                True,
            ),
            # 7. WhatsApp estándar IMG-YYYYMMDD-WAXXXX (Sin hora)
            # Coincidencia: IMG-20230101-WA0001
            (
                re.compile(
                    r"(?:IMG|VID)[-_]?(20\d{2})(\d{2})(\d{2})[-_]WA", re.IGNORECASE
                ),
                "%Y%m%d",
                False,
            ),
            # 4. PXL (Google Pixel) con hora
            # Coincidencia: PXL_20230101_120000...
            (
                re.compile(
                    r"PXL[-_]?(20\d{2})(\d{2})(\d{2})[-_]?(\d{2})(\d{2})(\d{2})",
                    re.IGNORECASE,
                ),
                "%Y%m%d%H%M%S",
                True,
            ),
            # 5. Genérico YYYYMMDD_HHMMSS (Actualizado para permitir punto o fin de cadena)
            # Coincidencia: 20230101_120000.jpg, 20190619_104019.jpg
            # Cambio de verificación final de (?:[-_]|$) a (?:[._-]|$)
            (
                re.compile(
                    r"(?:^|[-_])(20\d{2})(\d{2})(\d{2})[-_]?(\d{2})(\d{2})(\d{2})(?:[._-]|$)",
                    re.IGNORECASE,
                ),
                "%Y%m%d%H%M%S",
                True,
            ),
            # 6. Genérico YYYY-MM-DD HH.MM.SS
            # Coincidencia: 2023-01-01 12.00.00.jpg
            (
                re.compile(
                    r"(20\d{2})[-_](\d{2})[-_](\d{2})[\s_-]+(\d{2})[\.:](\d{2})[\.:](\d{2})"
                ),
                "%Y-%m-%d %H.%M.%S",
                True,
            ),
            # 7. Respaldo: Solo Fecha YYYYMMDD (Sin hora)
            # Coincidencia: 20230101_...
            (
                re.compile(
                    r"(?:^|[-_])(20\d{2})(\d{2})(\d{2})(?:[._-]|$)", re.IGNORECASE
                ),
                "%Y%m%d",
                False,
            ),
        ]

    def extract_date(self, filename: str) -> tuple[datetime | None, bool]:
        """
        Intenta extraer una fecha/hora del nombre del archivo.
        Retorna: (objeto_datetime, tiene_componente_hora)
        tiene_componente_hora es True si el nombre contiene explícitamente HH:MM:SS.
        """
        observation = self._extract_observation(filename)
        if observation is None:
            return None, False
        observed_at, has_time, is_instant, _evidence = observation
        # Compatibility: extract_date historically returned Unix timestamps as
        # naive UTC datetimes. The candidate API below preserves instant semantics.
        if is_instant:
            observed_at = observed_at.replace(tzinfo=None)
        return observed_at, has_time

    def extract_candidate(
        self, filename: str, *, confidence: int
    ) -> DateCandidate | None:
        """Extract a date candidate while preserving its temporal semantics."""
        observation = self._extract_observation(filename)
        if observation is None:
            return None
        observed_at, _has_time, _is_instant, evidence = observation
        return DateCandidate(
            observed_at=observed_at,
            source=DateSource.FILENAME,
            confidence=confidence,
            evidence=evidence,
        )

    def _extract_observation(
        self, filename: str
    ) -> tuple[datetime, bool, bool, str] | None:
        """Parse once, retaining whether the value represents a UTC instant."""
        for pattern, date_fmt, has_time in self.patterns:
            match = pattern.search(filename)
            if match:
                try:
                    if date_fmt == "UNIX_MS":
                        ts_ms = int(match.group(1))
                        dt = datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc)

                        if dt.year < 2000:
                            continue
                        evidence = f"filename-pattern:{date_fmt}:{dt.isoformat()}"
                        return dt, True, True, evidence

                    elif date_fmt == "DD_MMM_YYYY":
                        groups = match.groups()
                        day = int(groups[0])
                        month_str = groups[1].lower()
                        year = int(groups[2])

                        month = self.month_map.get(month_str)
                        if not month:
                            continue

                        if not (1 <= month <= 12 and 1 <= day <= 31):
                            continue

                        # Usar 12:00:00 como hora predeterminada
                        dt = datetime(year, month, day, 12, 0, 0)
                        evidence = f"filename-pattern:{date_fmt}:{dt.isoformat()}"
                        return dt, False, False, evidence

                    groups = match.groups()
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])

                    if not (1 <= month <= 12 and 1 <= day <= 31):
                        continue

                    hour, minute, second = 12, 0, 0  # Predeterminado

                    if has_time:
                        if len(groups) >= 6:
                            hour, minute, second = (
                                int(groups[3]),
                                int(groups[4]),
                                int(groups[5]),
                            )
                        elif len(groups) == 5:  # Caso: YYYY, MM, DD, HH, MM (Falta SS)
                            hour, minute = int(groups[3]), int(groups[4])
                            second = 0

                        if not (
                            0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59
                        ):
                            continue

                    dt = datetime(year, month, day, hour, minute, second)
                    evidence = f"filename-pattern:{date_fmt}:{dt.isoformat()}"
                    return dt, has_time, False, evidence

                except (ValueError, IndexError):
                    continue
        return None
