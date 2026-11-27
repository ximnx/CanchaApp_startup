"""Operaciones de base de datos para usuarios, perfil, favoritos y suscripciones."""

from datetime import timedelta

from config import MESES_GRATIS_BETA, hoy_colombia
from db.connection import obtener_conexion


def registrar_usuario(nombre, correo, contrasena_hash, tipo_usuario, telefono=""):
    """Guarda un nuevo usuario y, si es administrador, inicializa su plan Beta gratuito."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario, telefono)
        VALUES (?, ?, ?, ?, ?)
        """,
        (nombre, correo, contrasena_hash, tipo_usuario, telefono),
    )
    usuario_id = cursor.lastrowid
    if tipo_usuario == "administrador":
        hoy = hoy_colombia()
        fin_beta = (hoy + timedelta(days=30 * MESES_GRATIS_BETA)).isoformat()
        cursor.execute(
            """
            INSERT OR IGNORE INTO suscripciones (administrador_id, estado, fecha_inicio, fecha_fin)
            VALUES (?, 'beta', ?, ?)
            """,
            (usuario_id, hoy.isoformat(), fin_beta),
        )
    conexion.commit()
    conexion.close()
    return usuario_id


def buscar_usuario_por_correo(correo):
    """Busca un usuario por su correo electrónico."""
    conexion = obtener_conexion()
    usuario = conexion.execute(
        "SELECT * FROM usuarios WHERE correo = ?",
        (correo,),
    ).fetchone()
    conexion.close()
    return usuario


def buscar_usuario_por_id(usuario_id):
    """Busca un usuario por su identificador."""
    conexion = obtener_conexion()
    usuario = conexion.execute(
        "SELECT * FROM usuarios WHERE id = ?",
        (usuario_id,),
    ).fetchone()
    conexion.close()
    return usuario


def actualizar_perfil_usuario(usuario_id, nuevo_nombre, ruta_foto, deportes_favoritos=None, telefono=None):
    """Actualiza el nombre, fotografía, teléfono y deportes favoritos del usuario."""
    conexion = obtener_conexion()
    campos = ["nombre = ?", "foto = ?"]
    valores = [nuevo_nombre, ruta_foto]

    if deportes_favoritos is not None:
        campos.append("deportes_favoritos = ?")
        valores.append(",".join(deportes_favoritos))
    if telefono is not None:
        campos.append("telefono = ?")
        valores.append(telefono)

    valores.append(usuario_id)
    conexion.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE id = ?", valores)
    conexion.commit()
    conexion.close()


def actualizar_telefono_usuario(usuario_id, telefono):
    """Actualiza el celular del usuario (usado al reservar si aún no lo tenía)."""
    conexion = obtener_conexion()
    conexion.execute("UPDATE usuarios SET telefono = ? WHERE id = ?", (telefono, usuario_id))
    conexion.commit()
    conexion.close()


def guardar_codigo_recuperacion(usuario_id, codigo, fecha_expira):
    """Guarda el código temporal de recuperación y su vencimiento."""
    conexion = obtener_conexion()
    conexion.execute(
        """
        UPDATE usuarios
        SET codigo_recuperacion = ?, codigo_expira = ?
        WHERE id = ?
        """,
        (codigo, fecha_expira, usuario_id),
    )
    conexion.commit()
    conexion.close()


def actualizar_contrasena_usuario(usuario_id, nueva_contrasena_hash):
    """Actualiza el hash de contraseña y limpia el código usado."""
    conexion = obtener_conexion()
    conexion.execute(
        """
        UPDATE usuarios
        SET contrasena = ?, codigo_recuperacion = '', codigo_expira = ''
        WHERE id = ?
        """,
        (nueva_contrasena_hash, usuario_id),
    )
    conexion.commit()
    conexion.close()


# ---------------- SUSCRIPCIÓN BASE (FASE 8) ----------------

def obtener_suscripcion_admin(administrador_id):
    """Devuelve el estado de suscripción del administrador (creando Beta si no existe)."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    fila = cursor.execute(
        "SELECT * FROM suscripciones WHERE administrador_id = ?",
        (administrador_id,),
    ).fetchone()
    if not fila:
        hoy = hoy_colombia()
        fin_beta = (hoy + timedelta(days=30 * MESES_GRATIS_BETA)).isoformat()
        cursor.execute(
            """
            INSERT OR IGNORE INTO suscripciones (administrador_id, estado, fecha_inicio, fecha_fin)
            VALUES (?, 'beta', ?, ?)
            """,
            (administrador_id, hoy.isoformat(), fin_beta),
        )
        conexion.commit()
        fila = cursor.execute(
            "SELECT * FROM suscripciones WHERE administrador_id = ?",
            (administrador_id,),
        ).fetchone()
    conexion.close()
    return fila


# ---------------- FAVORITOS DE CANCHAS ----------------

def alternar_favorito(usuario_id, cancha_id):
    """Agrega o quita una cancha de los favoritos del usuario."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    existente = cursor.execute(
        "SELECT id FROM favoritos WHERE usuario_id = ? AND cancha_id = ?",
        (usuario_id, cancha_id),
    ).fetchone()

    if existente:
        cursor.execute("DELETE FROM favoritos WHERE id = ?", (existente["id"],))
        guardado = False
    else:
        cursor.execute(
            "INSERT INTO favoritos (usuario_id, cancha_id) VALUES (?, ?)",
            (usuario_id, cancha_id),
        )
        guardado = True

    conexion.commit()
    conexion.close()
    return guardado


def obtener_ids_favoritos(usuario_id):
    """Devuelve un conjunto (set) con los IDs de canchas favoritas del usuario."""
    if not usuario_id:
        return set()
    conexion = obtener_conexion()
    filas = conexion.execute(
        "SELECT cancha_id FROM favoritos WHERE usuario_id = ?",
        (usuario_id,),
    ).fetchall()
    conexion.close()
    return {fila["cancha_id"] for fila in filas}

