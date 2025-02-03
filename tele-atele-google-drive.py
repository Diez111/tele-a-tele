#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Este script automatiza la tarea de leer un grupo de Telegram, identificar mensajes relacionados con juegos
donde se comparten partes a través de enlaces de Google Drive.
Posteriormente, descarga las partes para cada juego, verifica duplicados y envía los archivos en paquete
al grupo destino manteniendo el orden de las partes.
"""

import re
import os
import asyncio
import requests
import json
import sys
import hashlib
from tqdm import tqdm

from telethon import TelegramClient

# ============================
# Configuración de Telegram
# ============================
API_ID = "API_ID"  # API ID de Telegram actualizado
API_HASH = "API_HASH"  # API Hash de Telegram actualizado
SESSION_NAME = "tele_atele_session"
# Se solicitará el número de teléfono interactivamente, por lo que se elimina el valor fijo.

# Configuración de los grupos
SOURCE_GROUP = "nombre_o_id_del_grupo_origen"       # Reemplaza con el nombre o id del grupo de origen
DESTINATION_GROUP = "nombre_o_id_del_grupo_destino"  # Reemplaza con el nombre o id del grupo de destino

# Directorio temporal para descargas
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Conjunto para verificar archivos duplicados (utilizamos el ID de Google Drive)
procesados = set()

# ============================
# Funciones Auxiliares
# ============================
def extract_drive_file_id(url):
    """
    Extrae el ID del archivo de Google Drive de la URL.
    Ejemplo de URL: https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    """
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def parse_message(message_text):
    """
    Parsea el texto del mensaje para extraer el nombre del juego, el número de parte y el enlace de Google Drive.
    Se espera que el mensaje tenga el formato:
    "Juego: <nombre_del_juego>, Parte: <numero> - <enlace_google_drive>"
    """
    # Buscamos el patrón del juego y la parte
    pattern = r"Juego:\s*(?P<juego>.*?),\s*Parte:\s*(?P<parte>\d+)"
    match = re.search(pattern, message_text, re.IGNORECASE)
    if not match:
        return None, None, None
    juego = match.group("juego").strip()
    parte = int(match.group("parte"))
    # Buscar el enlace de Google Drive en el mensaje (se toma el primer enlace que contenga drive.google.com)
    drive_url = None
    urls = re.findall(r'(https?://\S+)', message_text)
    for url in urls:
        if "drive.google.com" in url:
            drive_url = url
            break
    return juego, parte, drive_url

def validar_telefono(telefono):
    """Valida que el número de teléfono esté en formato internacional. Ejemplo: +12345678901"""
    import re
    pattern = re.compile(r'^\+\d{10,15}$')
    return pattern.match(telefono) is not None

def compute_fingerprint(msg):
    """
    Calcula una huella digital para el mensaje.
    Si hay texto (o caption) no vacío, se utiliza un MD5 del contenido.
    Si no, para documentos se usa un MD5 del nombre de archivo, y en su defecto se usa el ID.
    Para fotos o medios se utiliza el ID.
    """
    if msg.message and msg.message.strip():
         contenido = msg.message.strip().lower().encode("utf-8")
         return "txt:" + hashlib.md5(contenido).hexdigest()
    elif msg.document:
         try:
              for attr in msg.document.attributes:
                  if attr.__class__.__name__ == "DocumentAttributeFilename":
                      nombre = attr.file_name.strip().lower().encode("utf-8")
                      return "doc:" + hashlib.md5(nombre).hexdigest()
              return "doc:" + str(msg.document.id)
         except Exception:
              return "doc:" + str(msg.document.id)
    elif msg.photo:
         try:
              return "photo:" + str(msg.photo.id)
         except Exception:
              return "photo:" + str(msg.id)
    elif msg.media:
         return "media:" + str(msg.id)
    return None

def safe_input(prompt):
    """Realiza una entrada segura que atrapa KeyboardInterrupt para salir limpiamente."""
    try:
         return input(prompt)
    except KeyboardInterrupt:
         print("\nInterrupción detectada. Cerrando el programa...")
         sys.exit(0)

def cargar_config():
    """Carga la configuración desde 'config.json'. Si no existe, solicita al usuario y la guarda."""
    if os.path.exists("config.json"):
         with open("config.json", "r") as f:
              config = json.load(f)
         # Convertir API_ID a entero
         config["api_id"] = int(config["api_id"])
         return config
    else:
         config = {}
         config["api_id"] = int(safe_input("Ingrese su API ID de Telegram: ").strip())
         config["api_hash"] = safe_input("Ingrese su API HASH de Telegram: ").strip()
         config["phone"] = safe_input("Ingrese su número de teléfono en formato internacional (ej: +12345678901): ").strip()
         while not validar_telefono(config["phone"]):
              print("El número de teléfono ingresado es inválido. Asegúrese de incluir el código internacional y solo dígitos.")
              config["phone"] = safe_input("Ingrese su número de teléfono en formato internacional (ej: +12345678901): ").strip()
         with open("config.json", "w") as f:
              json.dump(config, f)
         return config

def download_from_google_drive(url, dest_folder=DOWNLOAD_DIR):
    """
    Descarga un archivo desde Google Drive dado su URL.
    Retorna la ruta del archivo descargado o None en caso de error.
    """
    file_id = extract_drive_file_id(url)
    if not file_id:
        print("No se pudo extraer el ID del archivo de la URL:", url)
        return None
    
    # Verificar duplicados
    if file_id in procesados:
        print("Archivo ya procesado (duplicado):", file_id)
        return None
    
    download_url = "https://docs.google.com/uc?export=download&id=" + file_id
    local_filename = os.path.join(dest_folder, file_id)
    
    try:
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        procesados.add(file_id)
        print(f"Descargado: {local_filename}")
        return local_filename
    except Exception as e:
        print("Error descargando el archivo:", e)
        return None

async def process_game(client, destino, juego, partes):
    """
    Procesa un juego: para cada parte, descarga y envía al grupo destino en orden.
    """
    print(f"Procesando juego: {juego} con {len(partes)} partes.")
    # Ordenar las partes por número
    partes.sort(key=lambda x: x["parte"])
    for parte_info in partes:
        drive_url = parte_info["url"]
        parte = parte_info["parte"]
        # Descargar archivo desde Google Drive
        archivo = download_from_google_drive(drive_url)
        if archivo:
            try:
                print(f"Enviando parte {parte} de {juego} al grupo destino...")
                # Enviar el archivo al grupo destino con un caption que indique juego y parte
                await client.send_file(destino, archivo, caption=f"{juego} - Parte {parte}")
            except Exception as e:
                print("Error enviando archivo al grupo destino:", e)
            finally:
                # Luego de enviar, eliminamos el archivo descargado
                try:
                    os.remove(archivo)
                except Exception as e:
                    print("Error al eliminar el archivo:", e)
        else:
            print(f"Saltando la parte {parte} de {juego} por error en descarga o por duplicado.")

async def forward_message(client, destino, source_entity, msg, idx, sem):
    """Reenvía un mensaje: si tiene contenido multimedia, lo descarga y lo vuelve a subir; si es solo texto, lo envía.
    Se utiliza un semáforo para controlar la concurrencia."""
    async with sem:
         try:
              # Si el mensaje contiene medios (fotos, documentos, etc.), se descarga y se reenvía el archivo.
              if msg.photo or msg.document or msg.media:
                   print(f"Procesando mensaje {idx} con archivo, descargando y reenviando...")
                   pbar = None
                   def progress_callback(current, total):
                       nonlocal pbar
                       if pbar is None:
                           pbar = tqdm(total=total, unit='B', unit_scale=True, desc=f"Archivo {idx}", 
                                       colour="green", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{percentage:3.0f}%]", leave=False)
                       pbar.update(current - pbar.n)
                       if current >= total:
                           pbar.close()
                   file_path = await client.download_media(msg, progress_callback=progress_callback)
                   if file_path:
                        caption = msg.message if msg.message else ""
                        # Enviar el archivo (foto, documento o media) junto con su caption
                        await client.send_file(destino, file_path, caption=caption)
                        try:
                             os.remove(file_path)
                        except Exception as e:
                             print(f"Error al eliminar archivo temporal {file_path}: {e}")
                        preview = caption[:30] if caption else "[Archivo sin caption]"
                   else:
                        preview = "[Error al descargar el archivo]"
              else:
                   # Si no tiene medios, se envía el mensaje de texto
                   if msg.message:
                        preview = msg.message[:30].replace("\n", " ")
                   else:
                        preview = "[Sin contenido]"
                   print(f"Enviando mensaje {idx}: {preview}")
                   await client.send_message(destino, msg.message)
              print(f"Mensaje {idx} enviado correctamente.")
         except Exception as e:
              print(f"Error reenviando mensaje {idx}: {e}")

# ============================
# Función Principal
# ============================
async def main():
    # Cargar configuración (API_ID, API_HASH y número de teléfono) desde config.json o solicitarlos
    config = cargar_config()
    # Inicializar cliente de Telegram con los datos de configuración
    client = TelegramClient(SESSION_NAME, config["api_id"], config["api_hash"])
    try:
         await client.start(phone=config["phone"])
    except Exception as e:
         print(f"Error al iniciar el cliente de Telegram: {e}")
         return
    
    # Obtener la lista de diálogos (grupos, canales, chats) y filtrar por aquellos que tienen título
    dialogs = await client.get_dialogs()
    grupos = [d.entity for d in dialogs if hasattr(d.entity, "title")]
    if not grupos:
         print("No se encontraron grupos disponibles.")
         return

    print("\nGrupos disponibles:")
    for idx, grupo in enumerate(grupos):
         print(f"{idx}: {grupo.title}")

    # Selección interactiva del grupo ORIGEN y del destino o 'guardados'
    try:
         source_index = int(safe_input("Ingrese el número del grupo ORIGEN: ").strip())
         destino_input = safe_input("Ingrese el número del grupo DESTINO o escriba 'guardados' para enviar a 'Mensajes guardados': ").strip().lower()
         source_entity = grupos[source_index]
         if destino_input == "guardados":
              destino = await client.get_entity("me")
         else:
              destino_index = int(destino_input)
              if destino_index < 0 or destino_index >= len(grupos):
                   print("Índice fuera de rango. Saliendo...")
                   return
              destino = grupos[destino_index]
    except ValueError:
         print("Entrada no válida. Debe ingresar un número o 'guardados'. Saliendo...")
         return
    
    # Obtener las huellas digitales de los mensajes existentes en destino para evitar duplicados
    print("Obteniendo mensajes existentes en el grupo destino para evitar duplicados...")
    dest_msgs = []
    async for m in client.iter_messages(destino, limit=200):
         dest_msgs.append(m)
    dest_text_set = set()
    for m in dest_msgs:
         if m.message and m.message.strip():
              dest_text_set.add(m.message.strip())

    print("Recuperando mensajes del grupo origen. Esto puede tardar dependiendo de la cantidad de mensajes...")
    mensajes = []
    # Recorrer TODOS los mensajes del grupo origen (sin límite)
    async for message in client.iter_messages(source_entity, limit=None):
         mensajes.append(message)
    print(f"Se han recuperado {len(mensajes)} mensajes.")
 
    # Ordenar los mensajes de forma ascendente (desde el más antiguo hasta el más moderno)
    mensajes.sort(key=lambda m: m.date)

    print("\nLista de mensajes:")
    for idx, mensaje in enumerate(mensajes):
         preview = ""
         if mensaje.message and mensaje.message.strip():
             preview = mensaje.message[:30].replace("\n", " ")
         elif mensaje.document:
              file_name = None
              try:
                   for attr in mensaje.document.attributes:
                        if attr.__class__.__name__ == "DocumentAttributeFilename":
                             file_name = attr.file_name
                             break
              except Exception:
                   pass
              if file_name:
                   preview = f"[Documento] {file_name}"
              else:
                   preview = "[Documento]"
         elif mensaje.photo:
              preview = "[Foto]"
         elif mensaje.media:
              preview = "[Media]"
         else:
              preview = "[Sin contenido]"
         print(f"{idx}: {preview}")
 
    seleccion = safe_input("Ingrese 'todos' para pasar todos los mensajes o ingrese los índices separados por coma (ej: 0,1,3-5): ").strip().lower()
    if seleccion == "todos":
         indices = list(range(len(mensajes)))
    else:
         indices = []
         for parte in seleccion.split(","):
             parte = parte.strip()
             if "-" in parte:
                 try:
                     inicio, fin = parte.split("-")
                     inicio = int(inicio)
                     fin = int(fin)
                     indices.extend(range(inicio, fin+1))
                 except Exception as e:
                     print(f"Error procesando el rango {parte}: {e}")
             else:
                 try:
                     indices.append(int(parte))
                 except Exception as e:
                     print(f"Error procesando el índice {parte}: {e}")
 
    # Pre-filtrar los índices seleccionados comparando solo los textos
    nuevos_indices = []
    for i in indices:
         if i < 0 or i >= len(mensajes):
              print(f"Índice {i} fuera de rango, omitiendo...")
         else:
              msg = mensajes[i]
              if msg.message and msg.message.strip():
                   txt = msg.message.strip()
                   if txt in dest_text_set:
                        print(f"Mensaje {i} duplicado en destino (texto idéntico). Omitiendo...")
                   else:
                        nuevos_indices.append(i)
                        dest_text_set.add(txt)
              else:
                   # Si el mensaje no tiene texto (por ejemplo, multimedia sin caption) se envía de todas formas.
                   nuevos_indices.append(i)
    print(f"Se reenviarán {len(nuevos_indices)} mensajes después de filtrar duplicados (solo por texto).")
    sem = asyncio.Semaphore(10)
    nuevos_indices.sort()
    pbar = tqdm(total=len(nuevos_indices), desc="Enviando mensajes", colour="green", unit="mensaje", 
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{percentage:3.0f}%]")
    for idx, i in enumerate(nuevos_indices):
         # Se envía cada mensaje de forma secuencial para preservar el orden.
         await forward_message(client, destino, source_entity, mensajes[i], i, sem)
         pbar.update(1)
    pbar.close()
    
    print("Procesamiento completado. Cerrando cliente...")
    await client.disconnect()

if __name__ == '__main__':
    try:
         asyncio.run(main())
    except KeyboardInterrupt:
         print("\nInterrupción detectada. Saliendo...")
         sys.exit(0)
