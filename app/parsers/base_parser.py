from abc import ABC, abstractmethod
from pathlib import Path


class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        pass

    @abstractmethod
    def parse(self, file_path: str) -> dict:
        pass

    @staticmethod
    def validate_file_exists(file_path: str) -> Path:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No existe el archivo: {file_path}")
        return path