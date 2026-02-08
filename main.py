import ttkbootstrap as ttk
import logging
from src.gui import ImageMetadataApp

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = ImageMetadataApp()
    app.mainloop()
