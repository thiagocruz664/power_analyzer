# ARCHITECTURE.md

## 1. Objetivo del sistema

Power Analyzer es una aplicación de escritorio desarrollada en Python y PySide6, compatible con Windows y Linux, destinada a recibir, procesar y visualizar mediciones provenientes de instrumentos de medición eléctrica.

La arquitectura debe permitir incorporar distintos modelos de instrumentos sin obligar a que compartan protocolos de comunicación, estructuras de datos, servicios de adquisición o funcionalidades de interfaz.

Cada modelo tendrá una integración independiente, mientras que la aplicación mantendrá una estructura común para gestionar los dispositivos configurados y organizar la interfaz.

El primer instrumento integrado es el TES3600. La arquitectura debe permitir incorporar otros modelos en el futuro sin modificar innecesariamente las integraciones existentes.

## 2. Principios de diseño

### 2.1. Independencia entre modelos

Cada modelo de instrumento tendrá su propio directorio dentro de `app/`.

La integración de cada modelo será responsable de sus particularidades, incluyendo:

- Configuración de comunicación.
- Conexión y desconexión.
- Protocolo de transporte y formato de mensajes.
- Validación de tramas.
- Decodificación de datos.
- Estructuras de medición.
- Servicios de adquisición.
- Funcionalidades específicas del instrumento.

No se debe asumir que todos los instrumentos utilizan TCP, transmiten mensajes de longitud variable, tienen las mismas magnitudes o requieren las mismas operaciones de adquisición.

### 2.2. Separación entre transporte y decodificación

La recepción de mensajes y la interpretación de las tramas son responsabilidades diferentes.

El protocolo de comunicación de un modelo define cómo se reciben y validan los mensajes transmitidos. El decodificador interpreta los bytes correspondientes a la trama del instrumento y obtiene sus mediciones.

Por ejemplo, en la integración actual del TES3600, el mensaje recibido contiene una longitud, una marca temporal y la trama original del instrumento. El protocolo separa estos componentes y el decodificador interpreta la trama TES3600.

Estas responsabilidades no deben mezclarse.

### 2.3. Independencia de la interfaz

La interfaz gráfica no debe implementar protocolos de comunicación ni decodificar tramas.

Los widgets reciben los datos procesados por los servicios correspondientes y se encargan de representarlos.

Las funcionalidades específicas de un modelo se ubican en sus propios widgets. Las funcionalidades globales de la aplicación permanecen separadas.

### 2.4. Extensibilidad sin abstracciones innecesarias

No se deben crear capas comunes, clases abstractas o interfaces genéricas sin una necesidad concreta.

Los componentes específicos de un modelo deben permanecer dentro de su integración. La lógica común de gestión de dispositivos debe limitarse a las responsabilidades que realmente comparten todos los modelos.

La arquitectura debe favorecer la reutilización cuando sea útil, sin obligar a instrumentos diferentes a utilizar la misma implementación interna.

## 3. Arquitectura general

La aplicación se organiza en tres áreas principales:

1. **Gestión de dispositivos:** mantiene los modelos compatibles, los dispositivos configurados y la información necesaria para seleccionarlos.
2. **Integraciones de instrumentos:** contienen la lógica específica de cada modelo, desde la comunicación hasta la representación de sus mediciones.
3. **Interfaz gráfica:** proporciona la ventana principal, la navegación, los diálogos globales y los widgets específicos de cada instrumento.

Flujo conceptual de adquisición:

    Instrumento de medición
            ↓
    Transporte y protocolo del modelo
            ↓
    Servicio de conexión y adquisición
            ↓
    Decodificador específico del modelo
            ↓
    Estructuras de medición del modelo
            ↓
    Widgets de visualización

Este flujo representa la separación de responsabilidades. Su implementación concreta puede variar según las características del instrumento.

## 4. Organización de directorios

La estructura objetivo es la siguiente:

    power_analyzer/
    ├── app/
    │   ├── main.py
    │   │
    │   ├── device_manager/
    │   │   ├── device.py
    │   │   ├── device_registry.py
    │   │   └── device_repository.py
    │   │
    │   ├── tes3600/
    │   │   ├── __init__.py
    │   │   ├── device.py
    │   │   ├── config.py
    │   │   ├── services/
    │   │   │   ├── connection_service.py
    │   │   │   └── measurement_service.py
    │   │   ├── network/
    │   │   │   ├── tcp_client.py
    │   │   │   ├── protocol.py
    │   │   │   └── transport_factory.py
    │   │   ├── decoder.py
    │   │   └── models/
    │   │       └── measurement.py
    │   │
    │   └── ui/
    │       ├── __init__.py
    │       ├── main_window.py
    │       ├── navigation.py
    │       └── widgets/
    │           ├── common/
    │           │   ├── new_device_dialog.py
    │           │   ├── select_device_dialog.py
    │           │   └── device_configuration.py
    │           ├── shared/
    │           │   └── ...
    │           └── tes3600/
    │               ├── real_time_measurement.py
    │               ├── register_measurement.py
    │               └── ...
    │
    ├── assets/
    │   └── icons/
    ├── tests/
    │   ├── device_manager/
    │   └── tes3600/
    ├── requirements.txt
    └── README.md

La estructura muestra la organización objetivo. Los directorios y archivos se incorporarán cuando corresponda según la implementación real. No deben crearse archivos vacíos ni duplicar módulos únicamente para completar el árbol.

Cuando se incorpore otro instrumento, su integración tendrá un directorio propio dentro de `app/`, al mismo nivel que `tes3600/`.

Por ejemplo:

    app/
    ├── tes3600/
    ├── otro_modelo/
    └── ui/
        └── widgets/
            ├── tes3600/
            └── otro_modelo/

## 5. Responsabilidades de los componentes

### 5.1. Aplicación principal

**`app/main.py`**

Punto de entrada de la aplicación. Inicializa Qt y crea la ventana principal.

No debe contener lógica de comunicación con instrumentos ni decodificación de tramas.

### 5.2. Gestión de dispositivos

**`app/device_manager/device.py`**

Representa la información general de un dispositivo configurado, como su identificador, nombre asignado y referencia a la configuración correspondiente.

No debe contener la lógica interna de comunicación ni las estructuras de medición específicas de un instrumento.

**`app/device_manager/device_registry.py`**

Mantiene el registro de las integraciones de modelos que la aplicación tiene implementadas y puede utilizar.

No debe ofrecer modelos que no estén disponibles en el código.

**`app/device_manager/device_repository.py`**

Gestiona la persistencia de los dispositivos configurados, utilizando el mecanismo de almacenamiento establecido por la aplicación.

La información persistida debe permitir identificar el modelo de cada dispositivo y recuperar su configuración.

El registro de modelos y el repositorio de dispositivos son responsabilidades diferentes: el primero identifica las integraciones disponibles; el segundo administra las instancias configuradas por el usuario.

### 5.3. Integración de cada modelo

Cada directorio de modelo contiene la lógica necesaria para trabajar con un instrumento concreto.

**`device.py`**

Punto de entrada de la integración. Expone las operaciones necesarias para que la aplicación gestione el dispositivo y conozca las funcionalidades que ofrece.

**`config.py`**

Contiene los parámetros propios del modelo, incluyendo los valores de comunicación y las constantes de protocolo que correspondan.

**`services/connection_service.py`**

Gestiona la conexión y desconexión del instrumento, así como su estado y los errores asociados.

**`services/measurement_service.py`**

Coordina la adquisición de datos, la validación y decodificación que corresponda, y la entrega de las mediciones a los componentes consumidores.

**`network/tcp_client.py`**

Implementa el cliente TCP cuando el modelo utiliza este transporte. Gestiona las operaciones de conexión, recepción y cierre.

Si otro instrumento utiliza una comunicación diferente, su integración puede implementar el mecanismo apropiado sin depender de este cliente.

**`network/protocol.py`**

Define cómo interpretar los mensajes transmitidos por el sistema de comunicación del modelo: longitud, cabeceras, marcas temporales, delimitadores y demás campos del transporte, según corresponda.

No debe interpretar las magnitudes eléctricas de la trama del instrumento.

**`network/transport_factory.py`**

Cuando sea necesaria, selecciona o construye la implementación de transporte que corresponda a la configuración del modelo.

No debe convertirse en una fábrica global que presuponga que todos los instrumentos comparten el mismo transporte.

**`decoder.py`**

Interpreta las tramas del instrumento y extrae sus mediciones. Contiene las validaciones propias del formato de datos del modelo.

No debe depender de widgets ni de elementos de la interfaz gráfica.

**`models/measurement.py`**

Define las estructuras de medición específicas del instrumento cuando estas sean necesarias.

Cada modelo puede tener sus propias magnitudes, unidades, metadatos y estructuras de datos. No se exige que todos los instrumentos compartan un único modelo rígido de medición.

### 5.4. Interfaz gráfica

**`ui/main_window.py`**

Administra la ventana principal, la disposición general de la interfaz y la integración de los componentes de navegación y visualización.

No debe implementar protocolos de comunicación ni lógica de decodificación.

**`ui/navigation.py`**

Coordina la navegación de la aplicación y la selección de funcionalidades disponibles para el dispositivo activo.

Debe separar las funciones globales de las funciones específicas de cada modelo.

**`ui/widgets/common/`**

Contiene los diálogos y componentes globales, como el alta de dispositivos, la selección de dispositivos y la configuración general de sus conexiones.

Estos componentes deben permitir trabajar con los modelos registrados sin asumir que todos requieren los mismos parámetros.

**`ui/widgets/shared/`**

Contiene widgets reutilizables por distintos modelos cuando exista una necesidad real de compartirlos.

**`ui/widgets/<modelo>/`**

Contiene las vistas y herramientas específicas de cada instrumento.

En el TES3600, esto puede incluir medición en tiempo real, registro, FFT y análisis, de acuerdo con las funcionalidades efectivamente implementadas.

Los widgets deben consumir los servicios y las estructuras de datos del modelo correspondiente, sin implementar la adquisición por su cuenta.

### 5.5. Recursos y pruebas

**`assets/`**

Contiene iconos y demás recursos gráficos utilizados por la aplicación.

**`tests/`**

Organiza las pruebas por área funcional, manteniendo separadas las pruebas de gestión de dispositivos y las pruebas específicas de cada instrumento.

Las pruebas deben cubrir las responsabilidades implementadas sin depender innecesariamente de equipos físicos o conexiones reales.

## 6. Navegación según el dispositivo seleccionado

La navegación debe adaptarse al dispositivo activo.

Se distinguen tres grupos de funcionalidades:

1. **Globales:** administración de dispositivos, preferencias y configuración general.
2. **Compartidas:** herramientas que pueden utilizarse con distintos modelos cuando sus requisitos estén satisfechos.
3. **Específicas:** herramientas que dependen de las capacidades de un instrumento concreto.

Cada integración debe poder informar qué funcionalidades admite. La navegación utilizará esa información para mostrar las opciones correspondientes.

La disponibilidad de una herramienta no debe determinarse únicamente por el nombre del modelo ni mediante una lista creciente de condiciones específicas dentro de `main_window.py`.

La interfaz no debe mostrar funcionalidades que no estén implementadas o que requieran datos que el dispositivo no proporciona.

La gestión de las pestañas abiertas es una responsabilidad de la interfaz y debe mantenerse separada de la selección de funcionalidades en el menú lateral.

## 7. Incorporación de nuevos modelos

Para incorporar un nuevo instrumento se debe:

1. Crear su directorio dentro de `app/`.
2. Implementar la configuración y los mecanismos de comunicación correspondientes.
3. Implementar su protocolo y decodificador.
4. Definir sus estructuras de medición cuando sean necesarias.
5. Exponer el punto de entrada de la integración y sus funcionalidades disponibles.
6. Incorporar el modelo al registro de integraciones.
7. Añadir los widgets específicos que correspondan.
8. Implementar pruebas para sus protocolos, decodificación y servicios.

La integración de un modelo nuevo no debe requerir modificar el decodificador, los servicios internos o las estructuras de medición de los modelos existentes.

Solo se modificarán los componentes globales cuando sea necesario incorporar explícitamente el nuevo modelo al registro o ampliar una capacidad común de la aplicación.

## 8. Reglas de implementación

- Mantener las dependencias entre módulos explícitas.
- Evitar importaciones circulares.
- Mantener la lógica de comunicación fuera de la interfaz gráfica.
- Mantener los decodificadores independientes de los widgets.
- No asumir que todos los instrumentos usan TCP.
- No asumir que todas las tramas tienen el mismo tamaño o estructura.
- No imponer las mismas magnitudes ni estructuras de medición a todos los modelos.
- No introducir abstracciones genéricas sin una necesidad concreta.
- No duplicar código común cuando exista una oportunidad real y comprobada de reutilización.
- No modificar el comportamiento existente durante una reestructuración exclusivamente arquitectónica.
- Mantener las dependencias externas documentadas en `requirements.txt`.

## 9. Alcance actual

El modelo implementado es el TES3600.

La aplicación recibe mensajes mediante TCP, interpreta el formato de transporte, extrae la marca temporal y la trama original, decodifica los datos del instrumento y los entrega a los componentes de visualización.

La integración debe conservar el comportamiento actual durante las reorganizaciones internas.

La incorporación de nuevos modelos, la ampliación de funcionalidades de navegación y la creación de nuevas herramientas de medición se realizarán en etapas posteriores.

Este documento define la arquitectura objetivo y sirve como referencia para las modificaciones estructurales futuras.