# ImageMD

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![Status](https://img.shields.io/badge/Status-Stable-success)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Herramienta de escritorio de alto rendimiento diseñada para la reparación, análisis y normalización de metadatos en archivos de imagen y video. Especializada en la recuperación de marcas de tiempo a partir de nombres de archivo (WhatsApp, Signal, Telegram, iOS) y la reparación binaria de estructuras PNG corruptas.

## Arquitectura e Implementación

Esta aplicación cuenta con una arquitectura modular que separa estrictamente la lógica de presentación, negocio y acceso a datos.

*   **Interfaz Gráfica (GUI):** Implementada con `ttkbootstrap` (tema `darkly`) sobre Tkinter. Utiliza un patrón Productor-Consumidor con `queue.Queue` para gestionar eventos, desacoplando el renderizado de la UI del procesamiento lógico.
*   **Concurrencia:** El escaneo y procesamiento de archivos se ejecuta mediante `concurrent.futures.ThreadPoolExecutor`. El número de hilos se ajusta dinámicamente según la CPU disponible, garantizando que la interfaz permanezca responsiva durante operaciones intensivas de E/S.
*   **Motor de Fechas:** `src/date_utils.py` implementa un sistema de expresiones regulares optimizado para extraer fechas de nomenclaturas no estándar (WhatsApp ES/EN, Unix timestamps, etc.). Gestiona explícitamente la conversión de zonas horarias para asegurar compatibilidad con Python 3.12+.
*   **Gestión de Metadatos:** `src/media_ops.py` utiliza una estrategia de fallback en cascada: lectura estándar (Pillow/Piexif), seguida de FFmpeg para video, y finalmente un "Deep Scan" que analiza los primeros 64KB binarios del archivo en busca de patrones de fecha raw o XMP incrustado.
*   **Reparación de PNG:** `src/repair.py` realiza análisis a nivel de byte para detectar y corregir chunks `IHDR` desplazados, un tipo de corrupción común generada por guardados defectuosos en software de terceros.
*   **Configuración:** Centralizada en `src/config.py`, facilitando la localización (actualmente en español) y el mantenimiento de constantes.

## Estructura del Proyecto

```text
imagemd/
├── src/
│   ├── config.py       # Configuración central y localización (ES)
│   ├── date_utils.py   # Motor de regex y normalización de fechas
│   ├── gui.py          # Interfaz gráfica (Producer-Consumer/Threads)
│   ├── media_ops.py    # Abstracción I/O Metadatos (Piexif/Pillow/FFmpeg)
│   └── repair.py       # Reparación binaria de bajo nivel (PNG IHDR)
├── tests/
│   └── test_patterns.py # Pruebas unitarias de expresiones regulares
├── main.py             # Punto de entrada de la aplicación GUI
├── repair_tool.py      # CLI independiente para reparación de imágenes
├── imagemd.spec        # Especificación de compilación PyInstaller
└── requirements.txt    # Dependencias fijadas para reproducibilidad
```

## Dependencias

El proyecto asegura la reproducibilidad mediante versiones fijadas en `requirements.txt`:

*   **ttkbootstrap (1.19.0):** Framework de UI moderno.
*   **Pillow (12.0.0):** Manipulación de imágenes rasterizadas.
*   **piexif (1.1.3):** Manipulación específica de metadatos EXIF en JPEG.
*   **ffmpeg-python (0.2.0):** Wrapper para operaciones de video.

### Versión del Sistema

Para el procesamiento de video, la aplicación se vincula con la instalación local de FFmpeg

Se recomienda FFmpeg v8.0.1 `8.0.1-essentials_build-www.gyan.dev`, debido a que esta fue la versión que se utilizo para las pruebas de la aplicación.

## Ejecución y Distribución

### Código Fuente
Para ejecutar la aplicación directamente en un entorno de desarrollo Python:

```bash
python main.py
```

### Compilación Local
El repositorio incluye el archivo de configuración `imagemd.spec` necesario para generar un ejecutable optimizado. Si desea construir el binario por su cuenta:

```bash
pyinstaller imagemd.spec --clean
```

El ejecutable resultante (`ImageMD.exe`) se generará en la carpeta `dist/`

### Releases
Para uso inmediato sin configuración de entorno, descargue el ejecutable precompilado más reciente desde la sección de **Releases** de este repositorio.
