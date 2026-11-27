"""Configuración centralizada y catálogos deportivos de Ready Match."""

from datetime import datetime, timedelta, timezone
import os
import re
import secrets

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_BD = os.path.join(BASE_DIR, "canchaapp.db")
CARPETA_IMAGENES = os.path.join(BASE_DIR, "static", "imagenes")
EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}
TAMANO_MAX_ARCHIVO = 5 * 1024 * 1024  # 5 MB

# Reglas operativas y de negocio configurables
HORAS_MIN_CANCELACION = 3
SEMANAS_VENTANA_FIJAS = 8
MESES_GRATIS_BETA = 2  # Periodo gratuito inicial (1 o 2 meses)

# Zona horaria de Colombia (America/Bogota, UTC-5 fijo sin horario de verano)
def _obtener_zona_colombia():
    if ZoneInfo is not None:
        try:
            return ZoneInfo("America/Bogota")
        except ZoneInfoNotFoundError:
            pass
    return timezone(timedelta(hours=-5), name="America/Bogota")


ZONA_COLOMBIA = _obtener_zona_colombia()

DIAS_SEMANA = [
    (0, "Lunes", "Lun"),
    (1, "Martes", "Mar"),
    (2, "Miércoles", "Mié"),
    (3, "Jueves", "Jue"),
    (4, "Viernes", "Vie"),
    (5, "Sábado", "Sáb"),
    (6, "Domingo", "Dom"),
]

ESTADOS_PAGO = ("pendiente", "abonado", "pagado")


def ahora_colombia():
    """Devuelve la fecha y hora actual en la zona horaria America/Bogota."""
    return datetime.now(ZONA_COLOMBIA)


def hoy_colombia():
    """Devuelve la fecha (date) actual en Colombia."""
    return ahora_colombia().date()


def fecha_hora_colombia(fecha_iso, hora_hm):
    """Convierte fecha 'YYYY-MM-DD' y hora 'HH:MM' a datetime con zona America/Bogota."""
    return datetime.strptime(f"{fecha_iso} {hora_hm}", "%Y-%m-%d %H:%M").replace(tzinfo=ZONA_COLOMBIA)


def normalizar_celular_colombiano(telefono):
    """Limpia y normaliza un celular colombiano a 10 dígitos (3XXXXXXXXX). Devuelve '' si es inválido."""
    digitos = re.sub(r"\D", "", telefono or "")
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    if len(digitos) == 10 and digitos.startswith("3"):
        return digitos
    return ""


def telefono_whatsapp_co(telefono):
    """Devuelve el número en formato WhatsApp Colombia (573XXXXXXXXX) o '' si es inválido."""
    norm = normalizar_celular_colombiano(telefono)
    return f"57{norm}" if norm else ""

# Horarios estándar (turnos de 1 hora)
HORAS_DISPONIBLES = [
    "07:00", "08:00", "09:00", "10:00", "11:00", "12:00",
    "13:00", "14:00", "15:00", "16:00", "17:00", "18:00",
    "19:00", "20:00", "21:00", "22:00",
]

# Catálogo oficial de deportes y sus modalidades exclusivas
DEPORTES_CATALOGO = [
    {
        "slug": "futbol",
        "nombre": "Fútbol",
        "imagen": "imagenes/cancha2.jpg",
        "modalidades": ["Fútbol 5", "Fútbol 7", "Fútbol 8", "Fútbol 11"],
    },
    {
        "slug": "baloncesto",
        "nombre": "Baloncesto",
        "imagen": "imagenes/baloncesto.jpg",
        "modalidades": ["Media cancha", "Cancha completa", "3 contra 3", "5 contra 5"],
    },
    {
        "slug": "voleibol",
        "nombre": "Voleibol",
        "imagen": "imagenes/voleibol.jpg",
        "modalidades": ["Voleibol de sala", "Voleibol de playa", "4 contra 4", "6 contra 6"],
    },
]

DEPORTES_NOMBRES = [d["nombre"] for d in DEPORTES_CATALOGO]
DEPORTE_POR_SLUG = {d["slug"]: d for d in DEPORTES_CATALOGO}
DEPORTE_POR_NOMBRE = {d["nombre"]: d for d in DEPORTES_CATALOGO}
MODALIDADES_POR_DEPORTE = {d["nombre"]: d["modalidades"] for d in DEPORTES_CATALOGO}

TIPOS_CANCHA = [
    "Sintética",
    "Cubierta",
    "Aire libre",
    "Madera / Duela",
    "Arena / Playa",
]

CATEGORIAS_EQUIPO = ["Masculino", "Femenino", "Mixto"]
NIVELES_JUEGO = ["Recreativo", "Intermedio", "Competitivo"]

IMAGENES_PREDETERMINADAS = {
    "imagenes/cancha1.jpg",
    "imagenes/cancha2.jpg",
    "imagenes/baloncesto.jpg",
    "imagenes/voleibol.jpg",
}


def cargar_archivo_env():
    """Carga variables locales desde .env sin sobreescribir variables de entorno existentes."""
    ruta_env = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(ruta_env):
        return

    with open(ruta_env, "r", encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            if clave and valor and clave not in os.environ:
                os.environ[clave] = valor


def obtener_secret_key():
    """Lee SECRET_KEY desde .env; si falta, genera una clave temporal y advierte en consola."""
    clave = (os.environ.get("SECRET_KEY") or os.environ.get("SECRET_KEY_RM") or "").strip()
    if clave:
        return clave
    print(
        "[Ready Match - Advertencia] SECRET_KEY no está definida en .env. "
        "Se usará una clave temporal solo para esta ejecución. Configura SECRET_KEY en .env."
    )
    return secrets.token_hex(32)


def obtener_codigo_admin():
    """Lee CODIGO_ADMIN_RM desde .env; advierte en consola si no está configurado."""
    codigo = (os.environ.get("CODIGO_ADMIN_RM") or "").strip()
    if not codigo:
        print(
            "[Ready Match - Advertencia] CODIGO_ADMIN_RM no está definido en .env. "
            "El registro de nuevos administradores permanecerá bloqueado hasta configurarlo."
        )
    return codigo


def modalidad_valida(deporte, modalidad):
    """Comprueba que una modalidad pertenezca únicamente al deporte indicado."""
    return deporte in MODALIDADES_POR_DEPORTE and modalidad in MODALIDADES_POR_DEPORTE[deporte]


def deporte_de_modalidad(modalidad):
    """Devuelve el deporte al que pertenece una modalidad, o cadena vacía."""
    for deporte, lista in MODALIDADES_POR_DEPORTE.items():
        if modalidad in lista:
            return deporte
    return ""


def imagen_por_defecto_deporte(deporte):
    """Devuelve la fotografía predeterminada correspondiente a cada deporte."""
    info = DEPORTE_POR_NOMBRE.get(deporte)
    return info["imagen"] if info else "imagenes/cancha1.jpg"
