import argparse
import os
import logging
from src.repair import ImageRepairTool


def main():
    parser = argparse.ArgumentParser(description="Repair corrupted PNG images.")
    parser.add_argument("path", help="Path to file or directory to scan/repair")
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate repair without modifying files"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Increase output verbosity"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s"
    )
    logger = logging.getLogger("RepairTool")
    # Forzar nivel INFO para visualizar el progreso explícitamente.
    logger.setLevel(logging.INFO)

    tool = ImageRepairTool()
    tool.logger = logger

    target = args.path
    if os.path.isfile(target):
        logger.info(f"Scanning single file: {target}")
        if tool.is_corrupted_png(target):
            logger.info(f"DETECTED: {target} is corrupted.")
            tool.repair_file(target, dry_run=args.dry_run)
        else:
            logger.info("File appears valid or not reparable.")

    elif os.path.isdir(target):
        logger.info(f"Scanning directory: {target}")
        count = 0
        repaired = 0
        for root, dirs, files in os.walk(target):
            for file in files:
                if file.lower().endswith(".png"):
                    fp = os.path.join(root, file)
                    if tool.is_corrupted_png(fp):
                        logger.info(f"DETECTED: {fp}")
                        if tool.repair_file(fp, dry_run=args.dry_run):
                            repaired += 1
                        count += 1

        if count == 0:
            logger.info("No corrupted PNGs found.")
        else:
            logger.info(
                f"Found {count} corrupted files. Successfully repaired {repaired}."
            )
    else:
        logger.error("Invalid path.")


if __name__ == "__main__":
    main()
