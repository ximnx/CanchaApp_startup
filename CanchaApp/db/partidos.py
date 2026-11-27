"""Operaciones de base de datos para equipos, integrantes, partidos, solicitudes y notificaciones."""

from db.connection import obtener_conexion


# ---------------- EQUIPOS E INTEGRANTES ----------------

def existe_equipo_por_nombre(nombre, excluir_id=None):
    """Comprueba si ya existe un equipo con ese nombre (opcionalmente excluyendo un ID)."""
    conexion = obtener_conexion()
    if excluir_id:
        fila = conexion.execute(
            "SELECT id FROM equipos WHERE LOWER(nombre) = LOWER(?) AND id != ?",
            (nombre, excluir_id),
        ).fetchone()
    else:
        fila = conexion.execute(
            "SELECT id FROM equipos WHERE LOWER(nombre) = LOWER(?)",
            (nombre,),
        ).fetchone()
    conexion.close()
    return fila is not None


def actualizar_equipo(equipo_id, capitan_id, nombre, categoria, tipo_futbol, descripcion, deporte):
    """Actualiza un equipo solo si pertenece al capitán indicado."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE equipos
        SET nombre = ?, categoria = ?, tipo_futbol = ?, descripcion = ?, deporte = ?
        WHERE id = ? AND capitan_id = ?
        """,
        (nombre, categoria, tipo_futbol, descripcion, deporte, equipo_id, capitan_id),
    )
    actualizados = cursor.rowcount
    conexion.commit()
    conexion.close()
    return actualizados > 0


def crear_equipo(nombre, categoria, tipo_futbol, capitan_id, descripcion, deporte="Fútbol"):
    """Registra un nuevo equipo y devuelve su ID."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO equipos (nombre, categoria, tipo_futbol, capitan_id, descripcion, deporte)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (nombre, categoria, tipo_futbol, capitan_id, descripcion, deporte),
    )
    equipo_id = cursor.lastrowid
    conexion.commit()
    conexion.close()
    return equipo_id


def obtener_todos_los_equipos(categoria=None, deporte=None, tipo_futbol=None):
    """Devuelve equipos filtrados opcionalmente por deporte, categoría y modalidad."""
    conexion = obtener_conexion()
    consulta = """
        SELECT equipos.*, usuarios.nombre AS nombre_capitan
        FROM equipos
        JOIN usuarios ON equipos.capitan_id = usuarios.id
        WHERE 1 = 1
    """
    parametros = []

    if deporte:
        consulta += " AND equipos.deporte = ?"
        parametros.append(deporte)
    if categoria:
        consulta += " AND equipos.categoria = ?"
        parametros.append(categoria)
    if tipo_futbol:
        consulta += " AND equipos.tipo_futbol = ?"
        parametros.append(tipo_futbol)

    consulta += " ORDER BY equipos.id DESC"
    equipos = conexion.execute(consulta, parametros).fetchall()
    conexion.close()
    return equipos


def obtener_equipos_por_capitan(capitan_id):
    """Devuelve los equipos donde el usuario es capitán."""
    conexion = obtener_conexion()
    equipos = conexion.execute(
        "SELECT * FROM equipos WHERE capitan_id = ? ORDER BY id DESC",
        (capitan_id,),
    ).fetchall()
    conexion.close()
    return equipos


def obtener_equipo_por_id(equipo_id):
    """Busca un equipo específico por su ID."""
    conexion = obtener_conexion()
    equipo = conexion.execute(
        "SELECT * FROM equipos WHERE id = ?",
        (equipo_id,),
    ).fetchone()
    conexion.close()
    return equipo


def agregar_integrante_equipo(equipo_id, nombre_integrante, posicion=""):
    """Agrega un integrante a un equipo."""
    conexion = obtener_conexion()
    conexion.execute(
        """
        INSERT INTO equipo_integrantes (equipo_id, nombre_integrante, posicion)
        VALUES (?, ?, ?)
        """,
        (equipo_id, nombre_integrante, posicion),
    )
    conexion.commit()
    conexion.close()


def obtener_integrantes_equipo(equipo_id):
    """Lista los integrantes registrados en un equipo."""
    conexion = obtener_conexion()
    integrantes = conexion.execute(
        "SELECT * FROM equipo_integrantes WHERE equipo_id = ? ORDER BY id ASC",
        (equipo_id,),
    ).fetchall()
    conexion.close()
    return integrantes


def eliminar_integrante_equipo(integrante_id, capitan_id):
    """Elimina un integrante verificando que el equipo pertenezca al capitán."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    if not cursor.execute(
        """
        SELECT equipo_integrantes.id
        FROM equipo_integrantes
        JOIN equipos ON equipo_integrantes.equipo_id = equipos.id
        WHERE equipo_integrantes.id = ? AND equipos.capitan_id = ?
        """,
        (integrante_id, capitan_id),
    ).fetchone():
        conexion.close()
        return False

    cursor.execute("DELETE FROM equipo_integrantes WHERE id = ?", (integrante_id,))
    conexion.commit()
    conexion.close()
    return True


# ---------------- PARTIDOS Y SOLICITUDES DE RIVAL ----------------

def crear_partido(equipo_id, fecha, hora, lugar, descripcion, nivel="Intermedio", deporte="Fútbol"):
    """Publica un partido en busca de rival."""
    conexion = obtener_conexion()
    conexion.execute(
        """
        INSERT INTO partidos (equipo_id, fecha, hora, lugar, descripcion, nivel, deporte)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (equipo_id, fecha, hora, lugar, descripcion, nivel, deporte),
    )
    conexion.commit()
    conexion.close()


def obtener_todos_los_partidos(
    tipo_futbol=None,
    categoria=None,
    deporte=None,
    nivel=None,
    fecha=None,
    busqueda=None,
):
    """Consulta partidos publicados aplicando filtros reales combinables."""
    conexion = obtener_conexion()
    consulta = """
        SELECT partidos.*,
               equipos.nombre AS nombre_equipo,
               equipos.categoria AS categoria,
               equipos.tipo_futbol AS tipo_futbol,
               equipos.capitan_id AS capitan_id,
               equipos.deporte AS deporte_equipo,
               usuarios.nombre AS nombre_capitan
        FROM partidos
        JOIN equipos ON partidos.equipo_id = equipos.id
        JOIN usuarios ON equipos.capitan_id = usuarios.id
        WHERE 1 = 1
    """
    parametros = []

    if deporte:
        consulta += " AND partidos.deporte = ?"
        parametros.append(deporte)
    if tipo_futbol:
        consulta += " AND equipos.tipo_futbol = ?"
        parametros.append(tipo_futbol)
    if categoria:
        consulta += " AND equipos.categoria = ?"
        parametros.append(categoria)
    if nivel:
        consulta += " AND partidos.nivel = ?"
        parametros.append(nivel)
    if fecha:
        consulta += " AND partidos.fecha = ?"
        parametros.append(fecha)
    if busqueda:
        patron = f"%{busqueda.lower()}%"
        consulta += " AND (LOWER(partidos.lugar) LIKE ? OR LOWER(equipos.nombre) LIKE ?)"
        parametros.extend([patron, patron])

    consulta += " ORDER BY partidos.fecha ASC, partidos.hora ASC, partidos.id DESC"
    partidos = conexion.execute(consulta, parametros).fetchall()
    conexion.close()
    return partidos


def obtener_partido_por_id(partido_id):
    """Obtiene una publicación de partido con su equipo y capitán."""
    conexion = obtener_conexion()
    partido = conexion.execute(
        """
        SELECT partidos.*,
               equipos.nombre AS nombre_equipo,
               equipos.capitan_id AS capitan_id
        FROM partidos
        JOIN equipos ON partidos.equipo_id = equipos.id
        WHERE partidos.id = ?
        """,
        (partido_id,),
    ).fetchone()
    conexion.close()
    return partido


def existe_solicitud(partido_id, equipo_id):
    """Comprueba si ese equipo ya envió solicitud a ese partido."""
    conexion = obtener_conexion()
    fila = conexion.execute(
        "SELECT id FROM solicitudes WHERE partido_id = ? AND equipo_id = ?",
        (partido_id, equipo_id),
    ).fetchone()
    conexion.close()
    return fila is not None


def obtener_rival_aceptado(partido_id):
    """Devuelve el nombre del equipo rival aceptado para un partido, o None."""
    conexion = obtener_conexion()
    fila = conexion.execute(
        """
        SELECT equipos.nombre AS nombre_rival
        FROM solicitudes
        JOIN equipos ON solicitudes.equipo_id = equipos.id
        WHERE solicitudes.partido_id = ? AND solicitudes.estado = 'aceptada'
        """,
        (partido_id,),
    ).fetchone()
    conexion.close()
    return fila["nombre_rival"] if fila else None


def crear_solicitud(partido_id, equipo_id):
    """Registra una solicitud para jugar un partido en estado 'pendiente'."""
    conexion = obtener_conexion()
    conexion.execute(
        "INSERT INTO solicitudes (partido_id, equipo_id, estado) VALUES (?, ?, 'pendiente')",
        (partido_id, equipo_id),
    )
    conexion.commit()
    conexion.close()


def obtener_solicitudes_recibidas(capitan_id):
    """Devuelve solicitudes que otros equipos enviaron a los partidos de este capitán."""
    conexion = obtener_conexion()
    solicitudes = conexion.execute(
        """
        SELECT solicitudes.*,
               partidos.fecha AS fecha,
               partidos.hora AS hora,
               partidos.lugar AS lugar,
               partidos.deporte AS deporte,
               equipo_publicador.nombre AS mi_equipo,
               equipo_retador.nombre AS equipo_retador,
               equipo_retador.categoria AS categoria_retador,
               equipo_retador.tipo_futbol AS tipo_retador,
               usuario_retador.nombre AS capitan_retador
        FROM solicitudes
        JOIN partidos ON solicitudes.partido_id = partidos.id
        JOIN equipos AS equipo_publicador ON partidos.equipo_id = equipo_publicador.id
        JOIN equipos AS equipo_retador ON solicitudes.equipo_id = equipo_retador.id
        JOIN usuarios AS usuario_retador ON equipo_retador.capitan_id = usuario_retador.id
        WHERE equipo_publicador.capitan_id = ?
        ORDER BY
            CASE solicitudes.estado
                WHEN 'pendiente' THEN 1
                WHEN 'aceptada' THEN 2
                ELSE 3
            END,
            partidos.fecha ASC,
            partidos.hora ASC
        """,
        (capitan_id,),
    ).fetchall()
    conexion.close()
    return solicitudes


def obtener_solicitudes_enviadas(capitan_id):
    """Devuelve solicitudes enviadas por los equipos de este capitán."""
    conexion = obtener_conexion()
    solicitudes = conexion.execute(
        """
        SELECT solicitudes.*,
               partidos.fecha AS fecha,
               partidos.hora AS hora,
               partidos.lugar AS lugar,
               partidos.deporte AS deporte,
               equipo_publicador.nombre AS equipo_publicador,
               equipo_retador.nombre AS mi_equipo
        FROM solicitudes
        JOIN partidos ON solicitudes.partido_id = partidos.id
        JOIN equipos AS equipo_publicador ON partidos.equipo_id = equipo_publicador.id
        JOIN equipos AS equipo_retador ON solicitudes.equipo_id = equipo_retador.id
        WHERE equipo_retador.capitan_id = ?
        ORDER BY solicitudes.id DESC
        """,
        (capitan_id,),
    ).fetchall()
    conexion.close()
    return solicitudes


def obtener_solicitud_por_id(solicitud_id):
    """Busca una solicitud junto con ambos capitanes y los datos del partido."""
    conexion = obtener_conexion()
    solicitud = conexion.execute(
        """
        SELECT solicitudes.*,
               equipo_publicador.capitan_id AS capitan_publicador_id,
               equipo_publicador.nombre AS nombre_publicador,
               equipo_retador.capitan_id AS capitan_retador_id,
               equipo_retador.nombre AS nombre_retador,
               partidos.fecha AS fecha,
               partidos.hora AS hora,
               partidos.lugar AS lugar
        FROM solicitudes
        JOIN partidos ON solicitudes.partido_id = partidos.id
        JOIN equipos AS equipo_publicador ON partidos.equipo_id = equipo_publicador.id
        JOIN equipos AS equipo_retador ON solicitudes.equipo_id = equipo_retador.id
        WHERE solicitudes.id = ?
        """,
        (solicitud_id,),
    ).fetchone()
    conexion.close()
    return solicitud


def actualizar_estado_solicitud(solicitud_id, nuevo_estado):
    """Cambia el estado de una solicitud ('aceptada' o 'rechazada')."""
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE solicitudes SET estado = ? WHERE id = ?",
        (nuevo_estado, solicitud_id),
    )
    conexion.commit()
    conexion.close()


# ---------------- NOTIFICACIONES Y NOVEDADES ----------------

def crear_notificacion(usuario_id, titulo, mensaje, url="/", tipo="general", creada_en=""):
    """Guarda una notificación emergente pendiente para un usuario."""
    conexion = obtener_conexion()
    conexion.execute(
        """
        INSERT INTO notificaciones (usuario_id, titulo, mensaje, url, tipo, enviada, creada_en)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (usuario_id, titulo, mensaje, url, tipo, creada_en),
    )
    conexion.commit()
    conexion.close()


def obtener_notificaciones_pendientes(usuario_id):
    """Devuelve las notificaciones aún no enviadas al dispositivo del usuario."""
    conexion = obtener_conexion()
    filas = conexion.execute(
        """
        SELECT * FROM notificaciones
        WHERE usuario_id = ? AND enviada = 0
        ORDER BY id ASC
        """,
        (usuario_id,),
    ).fetchall()
    conexion.close()
    return filas


def obtener_notificaciones_recientes(usuario_id, limite=10):
    """Devuelve las notificaciones más recientes del usuario para el panel del encabezado."""
    conexion = obtener_conexion()
    filas = conexion.execute(
        """
        SELECT * FROM notificaciones
        WHERE usuario_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (usuario_id, limite),
    ).fetchall()
    conexion.close()
    return filas


def marcar_notificaciones_enviadas(usuario_id, lista_ids):
    """Marca como enviadas una lista de notificaciones del usuario."""
    if not lista_ids:
        return
    conexion = obtener_conexion()
    marcadores = ",".join("?" for _ in lista_ids)
    conexion.execute(
        f"UPDATE notificaciones SET enviada = 1 WHERE usuario_id = ? AND id IN ({marcadores})",
        [usuario_id] + list(lista_ids),
    )
    conexion.commit()
    conexion.close()


def actualizar_ultimo_recordatorio(usuario_id, fecha_iso):
    """Guarda la fecha y hora del último recordatorio periódico generado."""
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE usuarios SET ultimo_recordatorio = ? WHERE id = ?",
        (fecha_iso, usuario_id),
    )
    conexion.commit()
    conexion.close()


def obtener_resumen_novedades(fecha_hoy):
    """Obtiene novedades reales de canchas, turnos libres y partidos abiertos."""
    conexion = obtener_conexion()
    ultima_cancha = conexion.execute(
        "SELECT nombre, tipo_futbol, deporte, precio FROM canchas ORDER BY id DESC LIMIT 1"
    ).fetchone()
    total_turnos = conexion.execute(
        "SELECT COUNT(*) AS total FROM horarios WHERE fecha >= ? AND bloqueado = 0",
        (fecha_hoy,),
    ).fetchone()["total"]
    partido_abierto = conexion.execute(
        """
        SELECT partidos.fecha, partidos.hora, partidos.lugar, partidos.deporte,
               equipos.nombre AS nombre_equipo
        FROM partidos
        JOIN equipos ON partidos.equipo_id = equipos.id
        WHERE partidos.fecha >= ?
          AND partidos.id NOT IN (SELECT partido_id FROM solicitudes WHERE estado = 'aceptada')
        ORDER BY partidos.fecha ASC, partidos.hora ASC
        LIMIT 1
        """,
        (fecha_hoy,),
    ).fetchone()
    conexion.close()
    return {
        "ultima_cancha": ultima_cancha,
        "total_turnos": total_turnos,
        "partido_abierto": partido_abierto,
    }
