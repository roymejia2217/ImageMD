import logging
from src.gui import ImageMetadataApp


def main() -> None:
    """Launch the desktop application through an installable entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    app = ImageMetadataApp()
    app.mainloop()


if __name__ == "__main__":
    main()
