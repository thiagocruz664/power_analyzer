import json

from pathlib import Path
from PySide6.QtCore import QStandardPaths

from app.device_manager.device import Device


class DeviceRepository:
    def __init__(self):
        app_data = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )

        self.directory = Path(app_data)
        self.directory.mkdir(parents=True, exist_ok=True)

        self.file_path = self.directory / "devices.json"

    def get_all(self) -> list[Device]:
        if not self.file_path.exists():
            return []

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            return [Device.from_dict(item) for item in data]

        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"No se pudieron cargar los dispositivos: {exc}"
            ) from exc

    def get_by_id(self, device_id: str) -> Device | None:
        return next(
            (
                device
                for device in self.get_all()
                if device.id == device_id
            ),
            None,
        )

    def add(self, device: Device) -> None:
        devices = self.get_all()

        if any(
            item.name.casefold() == device.name.casefold()
            for item in devices
        ):
            raise ValueError(
                "Ya existe un dispositivo con ese nombre."
            )

        devices.append(device)
        self._save(devices)

    def delete(self, device_id: str) -> None:
        devices = self.get_all()
        remaining = [
            device for device in devices
            if device.id != device_id
        ]

        if len(remaining) == len(devices):
            raise ValueError("El dispositivo no existe.")

        self._save(remaining)

    def _save(self, devices: list[Device]) -> None:
        temporary_path = self.file_path.with_suffix(".tmp")

        try:
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(
                    [device.to_dict() for device in devices],
                    file,
                    indent=4,
                    ensure_ascii=False,
                )

            temporary_path.replace(self.file_path)

        except OSError as exc:
            raise RuntimeError(
                f"No se pudieron guardar los dispositivos: {exc}"
            ) from exc
