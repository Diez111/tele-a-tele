# tele-a-tele

Este proyecto es un script en Python que automatiza la tarea de leer mensajes de un grupo de Telegram, identificar enlaces de Google Drive asociados a juegos, descargar las partes, verificar duplicados y enviarlas organizadamente a otro grupo de Telegram.

## Instalación

  Puedes instalar manualmente las dependencias ejecutando:

```bash
pip install re os asyncio requests json sys telethon
```

## Uso

1. **Configuración Inicial**

   - El script solicita la API ID y API Hash de Telegram.
   - Se requiere un número de teléfono válido en formato internacional.
   - La configuración se guarda automáticamente en `config.json`.

2. **Ejecución**

   - Ejecuta el script con:
     ```bash
     python tele-atele-google-drive.py
     ```
   - Selecciona el grupo origen y el destino (o "Mensajes guardados").
   - Filtra mensajes duplicados antes de reenviar.
   - Descarga y envía archivos organizados por partes.

## Licencia

Este proyecto está licenciado bajo la licencia **GPL-3.0**, lo que significa que puedes modificar y distribuir el código siempre que mantengas la misma licencia y divulgues el código fuente de cualquier modificación.

Más información sobre GPL-3.0 en: [https://www.gnu.org/licenses/gpl-3.0.html](https://www.gnu.org/licenses/gpl-3.0.html)

