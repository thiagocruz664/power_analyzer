# Power Analyzer

Aplicación multiplataforma (Windows/Linux) desarrollada en Python y PySide6 para la recepción, decodificación y visualización de mediciones de analizadores de redes eléctricas a través de TCP.

## Estructura del Proyecto

```
power_analyzer/
├── app/
│   ├── main.py
│   ├── device_manager/
│   │   ├── device.py
│   │   └── device_repository.py
│   ├── tes3600/
│   │   ├── decoder.py
│   │   ├── models/
│   │   │   └── measurement.py
│   │   ├── network/
│   │   │   ├── protocol.py
│   │   │   ├── tcp_client.py
│   │   │   └── transport_factory.py
│   │   └── services/
│   │       ├── connection_service.py
│   │       └── measurement_service.py
│   └── ui/
│       ├── main_window.py
│       └── widgets/
│           ├── common/
│           │   ├── new_device_dialog.py
│           │   └── select_device_dialog.py
│           └── tes3600/
│               └── real_time_measurement.py
├── assets/
│   └── icons/
├── tests/
├── requirements.txt
└── README.md
```

Consulte `ARCHITECTURE.md` para detalles de diseño y responsabilidades de cada módulo.
