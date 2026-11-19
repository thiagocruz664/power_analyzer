"""Servicio de descubrimiento dinámico de herramientas de trabajo por dispositivo."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QWidget
from app.device_manager.device import Device
from app.ui.widgets.base_tool import DeviceToolWidget

logger = logging.getLogger("PowerAnalyzer.ToolDiscovery")


@dataclass
class DiscoveredTool:
    """Metadatos de una herramienta de trabajo descubierta."""

    tool_id: str
    display_name: str
    file_path: Path
    module_name: str
    widget_class: type[DeviceToolWidget]

    def create_instance(self, parent: QWidget | None = None) -> DeviceToolWidget:
        """Instancia la clase de widget de la herramienta."""
        return self.widget_class(parent=parent)


class ToolDiscoveryService:
    """Descubre, valida y resuelve dinámicamente las herramientas de trabajo por dispositivo."""

    def __init__(self, widgets_base_dir: Path | None = None) -> None:
        if widgets_base_dir is None:
            self.widgets_base_dir = Path(__file__).resolve().parent / "widgets"
        else:
            self.widgets_base_dir = Path(widgets_base_dir)

    def find_device_directory(
        self, device: Device, base_dir: Path | None = None
    ) -> Path | None:
        """Localiza automáticamente el subdirectorio de widgets correspondiente a un dispositivo."""
        root = base_dir or self.widgets_base_dir
        if not root.is_dir():
            logger.warning("El directorio base de widgets no existe: %s", root)
            return None

        model_name = (device.model or "").strip()
        device_name = (device.name or "").strip()

        candidates = [
            model_name.casefold(),
            model_name.lower().replace("-", "").replace("_", ""),
            device_name.casefold(),
            device_name.lower().replace("-", "").replace("_", ""),
        ]
        candidates = [c for c in candidates if c]

        for item in root.iterdir():
            if not item.is_dir():
                continue
            # Ignorar directorios internos o comunes
            if item.name.startswith((".", "_")) or item.name == "common":
                continue

            item_folded = item.name.casefold()
            item_normalized = item.name.lower().replace("-", "").replace("_", "")

            if item_folded in candidates or item_normalized in candidates:
                return item

        logger.info(
            "No se encontró un directorio de widgets para el dispositivo '%s' (modelo: '%s') en %s.",
            device_name,
            model_name,
            root,
        )
        return None

    def read_tool_header(self, file_path: Path) -> str | None:
        """Lee el comentario de la primera línea física para obtener el nombre visible.

        Esta lectura se realiza SIN importar ni ejecutar el módulo Python.
        """
        try:
            with file_path.open("r", encoding="utf-8-sig") as handle:
                first_line = handle.readline()
        except Exception as exc:
            logger.warning(
                "No se pudo leer el archivo '%s': %s", file_path.name, exc
            )
            return None

        if not first_line:
            logger.warning("El archivo '%s' está vacío; se omite.", file_path.name)
            return None

        stripped = first_line.strip()
        if not stripped.startswith("#"):
            logger.warning(
                "El archivo '%s' no contiene un comentario en la primera línea; se omite de las herramientas.",
                file_path.name,
            )
            return None

        display_name = stripped.lstrip("#").strip()
        if not display_name:
            logger.warning(
                "El archivo '%s' contiene un comentario vacío en la primera línea; se omite.",
                file_path.name,
            )
            return None

        return display_name

    def resolve_tool_class(
        self, file_path: Path, module_name: str
    ) -> type[DeviceToolWidget] | None:
        """Importa el módulo y resuelve la clase compatible con el contrato DeviceToolWidget."""
        try:
            if module_name in sys.modules:
                module = sys.modules[module_name]
            else:
                spec = importlib.util.spec_from_file_location(
                    module_name, file_path
                )
                if spec is None or spec.loader is None:
                    logger.warning(
                        "No se pudo cargar la especificación del módulo '%s'.",
                        file_path.name,
                    )
                    return None
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

            # 1. Buscar clase que herede de DeviceToolWidget definida en este módulo
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, DeviceToolWidget) and obj is not DeviceToolWidget:
                    if obj.__module__ == module.__name__:
                        return obj

            # 2. Función de fábrica explícita en el módulo
            if hasattr(module, "get_tool_widget_class") and callable(
                module.get_tool_widget_class
            ):
                cls = module.get_tool_widget_class()
                if inspect.isclass(cls) and issubclass(
                    cls, (DeviceToolWidget, QWidget)
                ):
                    return cls

            # 3. Clase con bandera is_tool_widget
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, QWidget) and getattr(
                    obj, "is_tool_widget", False
                ):
                    if obj.__module__ == module.__name__:
                        return obj

            # 4. Cualquier subclase de DeviceToolWidget presente en el módulo
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, DeviceToolWidget) and obj is not DeviceToolWidget:
                    return obj

            logger.warning(
                "El módulo '%s' no expone una clase compatible con DeviceToolWidget.",
                file_path.name,
            )
            return None

        except Exception as exc:
            logger.error(
                "Error al importar o resolver la herramienta '%s': %s",
                file_path.name,
                exc,
                exc_info=True,
            )
            return None

    def discover_tools_for_device(
        self, device: Device, base_dir: Path | None = None
    ) -> list[DiscoveredTool]:
        """Descubre automáticamente todas las herramientas disponibles para el dispositivo indicado."""
        device_dir = self.find_device_directory(device, base_dir)
        if device_dir is None:
            return []

        discovered: list[DiscoveredTool] = []

        # Buscar todos los archivos .py candidatos ordenados alfabéticamente
        py_files = sorted(
            [
                p
                for p in device_dir.iterdir()
                if p.is_file()
                and p.suffix == ".py"
                and not p.name.startswith((".", "_"))
            ],
            key=lambda p: p.name.lower(),
        )

        for file_path in py_files:
            display_name = self.read_tool_header(file_path)
            if not display_name:
                continue

            module_name = f"app.ui.widgets.{device_dir.name}.{file_path.stem}"
            widget_class = self.resolve_tool_class(file_path, module_name)
            if widget_class is None:
                continue

            tool_id = f"{device_dir.name}.{file_path.stem}"
            tool = DiscoveredTool(
                tool_id=tool_id,
                display_name=display_name,
                file_path=file_path,
                module_name=module_name,
                widget_class=widget_class,
            )
            discovered.append(tool)
            logger.info(
                "Herramienta descubierta para %s: '%s' (%s)",
                device.name,
                display_name,
                file_path.name,
            )

        return discovered
