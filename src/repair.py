import os
import logging
import shutil
from PIL import Image

class ImageRepairTool:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.png_magic = b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A'

    def is_corrupted_png(self, filepath: str) -> bool:
        """
        Verifica si un archivo PNG está corrupto de la forma específica conocida causada por la librería 'exif'.
        """
        if not filepath.lower().endswith('.png'):
            return False

        # Primero, intentar apertura estándar
        try:
            with Image.open(filepath) as img:
                img.verify()
            return False # Archivo válido
        except Exception:
            pass # Falló apertura, proceder a revisar estructura

        # Verificar IHDR desplazado
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            
            ihdr_pos = data.find(b'IHDR')
            if ihdr_pos > 12: # Estándar es 12. Si > 12, está desplazado.
                # También verificar si inicia con firma parcial o marcador JPEG
                # Pero la presencia de IHDR desplazado es un fuerte indicador para esta reparación específica.
                return True
        except Exception:
            pass
            
        return False

    def repair_file(self, filepath: str, dry_run: bool = False) -> bool:
        """
        Intenta reparar el archivo.
        Retorna True si es exitoso.
        """
        if not self.is_corrupted_png(filepath):
            self.logger.info(f"File {filepath} does not appear to be a reparable corrupted PNG.")
            return False

        self.logger.info(f"Attempting repair on {filepath}...")

        try:
            with open(filepath, 'rb') as f:
                data = f.read()

            ihdr_pos = data.find(b'IHDR')
            if ihdr_pos == -1:
                self.logger.error("IHDR chunk not found.")
                return False

            # Calcular inicio del chunk IHDR (Longitud es 4 bytes antes del Tipo)
            start_pos = ihdr_pos - 4
            if start_pos < 0:
                self.logger.error("Invalid IHDR position.")
                return False

            # Construir nuevos datos
            # Descartamos todo antes del chunk IHDR y anteponemos la firma PNG correcta
            new_data = self.png_magic + data[start_pos:]

            if dry_run:
                self.logger.info("Dry run: Repair valid but not written.")
                return True

            # Respaldo
            backup_path = filepath + ".bak"
            shutil.copy2(filepath, backup_path)
            self.logger.info(f"Backup created at {backup_path}")

            # Escribir Reparación
            with open(filepath, 'wb') as f:
                f.write(new_data)

            # Verificar
            try:
                with Image.open(filepath) as img:
                    img.verify()
                self.logger.info(f"SUCCESS: {filepath} repaired successfully.")
                return True
            except Exception as e:
                self.logger.error(f"Repair verification failed: {e}. Restoring backup.")
                shutil.move(backup_path, filepath) # Restaurar
                return False

        except Exception as e:
            self.logger.error(f"Repair process failed: {e}")
            return False
