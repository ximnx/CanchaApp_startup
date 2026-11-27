"""Validación/subida segura de imágenes y utilidades de formato."""

import os
import secrets
import time

from werkzeug.utils import secure_filename

from config import CARPETA_IMAGENES, EXTENSIONES_PERMITIDAS


def formatear_precio(precio):
    """Convierte un entero como 90000 en '$90.000'."""
    return f"${int(precio):,}".replace(",", ".")


def clase_deporte(deporte):
    """Convierte el nombre del deporte en una clase CSS segura ('futbol', 'baloncesto', 'voleibol')."""
    mapa = {
        "Fútbol": "futbol",
        "Baloncesto": "baloncesto",
        "Voleibol": "voleibol",
    }
    return mapa.get(deporte or "Fútbol", "futbol")


def partes_fecha_calendario(fecha_iso):
    """Devuelve (mes_corto, dia) para el bloque tipo calendario, ej: '2026-11-27' -> ('NOV', '27')."""
    meses = ("", "ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
    try:
        partes = str(fecha_iso).split("-")
        mes_num = int(partes[1])
        dia = str(int(partes[2]))
        return meses[mes_num], dia
    except (IndexError, ValueError):
        return "---", "--"


def verificar_disponibilidad(ocupado, bloqueado=False):
    """Devuelve la etiqueta de estado de un turno."""
    if bloqueado:
        return "Bloqueado"
    return "Ocupado" if ocupado else "Disponible"


def _firma_imagen_valida(archivo):
    """Comprueba los bytes de cabecera reales (JPEG, PNG o WEBP)."""
    posicion = archivo.stream.tell()
    encabezado = archivo.stream.read(16)
    archivo.stream.seek(posicion)

    if len(encabezado) < 12:
        return False
    if encabezado[:3] == b"\xff\xd8\xff":
        return True
    if encabezado[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if encabezado[:4] == b"RIFF" and encabezado[8:12] == b"WEBP":
        return True
    return False


def archivo_imagen_valido(archivo):
    """Verifica extensión permitida y contenido real de imagen."""
    if not archivo or not archivo.filename or "." not in archivo.filename:
        return False
    extension = archivo.filename.rsplit(".", 1)[1].lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        return False
    return _firma_imagen_valida(archivo)


def guardar_imagen_subida(archivo, prefijo, usuario_id):
    """Guarda de forma segura una imagen validada y devuelve su ruta relativa en static/."""
    if not archivo or not archivo.filename:
        return None, None
    if not archivo_imagen_valido(archivo):
        return None, "Formato de imagen no válido. Usa un archivo real JPG, PNG o WEBP."

    nombre_seguro = secure_filename(archivo.filename)
    if not nombre_seguro or "." not in nombre_seguro:
        nombre_seguro = "imagen.jpg"

    nombre_final = f"{prefijo}_{usuario_id}_{int(time.time())}_{secrets.token_hex(3)}_{nombre_seguro}"
    os.makedirs(CARPETA_IMAGENES, exist_ok=True)
    archivo.save(os.path.join(CARPETA_IMAGENES, nombre_final))
    return f"imagenes/{nombre_final}", None
