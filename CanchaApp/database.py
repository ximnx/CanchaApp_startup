# Importamos sqlite3 (incluido en Python), os para rutas y datetime para fechas de ejemplo
from datetime import date, timedelta
import os
import sqlite3
# Guardamos el archivo de la base de datos dentro de la carpeta CanchaApp
RUTA_BD = os.path.join(os.path.dirname(__file__), "canchaapp.db")


def obtener_conexion():
    """Abre y devuelve una conexión a la base de datos SQLite."""
    conexion = sqlite3.connect(RUTA_BD)
    # row_factory nos permite leer columnas por su nombre, ej: usuario["nombre"]
    conexion.row_factory = sqlite3.Row
    # Activamos la verificación de llaves foráneas en SQLite
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def crear_tablas():
    """Crea todas las tablas necesarias de CanchaApp si aún no existen."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # 1. Tabla de usuarios (jugadores y administradores de canchas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL UNIQUE,
            contrasena TEXT NOT NULL,
            tipo_usuario TEXT NOT NULL,
            foto TEXT NOT NULL DEFAULT '',
            codigo_recuperacion TEXT NOT NULL DEFAULT '',
            codigo_expira TEXT NOT NULL DEFAULT ''
        )
    """)

    # Si la base de datos ya existía, agregamos las columnas nuevas sin borrar datos
    columnas_usuarios = [
        fila["name"] for fila in cursor.execute("PRAGMA table_info(usuarios)").fetchall()
    ]
    if "foto" not in columnas_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN foto TEXT NOT NULL DEFAULT ''")
    if "codigo_recuperacion" not in columnas_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN codigo_recuperacion TEXT NOT NULL DEFAULT ''")
    if "codigo_expira" not in columnas_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN codigo_expira TEXT NOT NULL DEFAULT ''")

    # 2. Tabla de canchas sintéticas (cada cancha pertenece a un administrador)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS canchas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            direccion TEXT NOT NULL,
            precio INTEGER NOT NULL,
            tipo_futbol TEXT NOT NULL,
            imagen TEXT NOT NULL,
            administrador_id INTEGER NOT NULL,
            FOREIGN KEY (administrador_id) REFERENCES usuarios(id)
        )
    """)

    # 3. Tabla de horarios disponibles para cada cancha
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS horarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cancha_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            FOREIGN KEY (cancha_id) REFERENCES canchas(id)
        )
    """)

    # 4. Tabla de reservas hechas por jugadores en una cancha
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cancha_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            nombre_reserva TEXT NOT NULL DEFAULT '',
            identificacion TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (cancha_id) REFERENCES canchas(id)
        )
    """)

    # Si la tabla reservas ya existía sin datos del titular, agregamos las columnas sin borrar datos
    columnas_reservas = [
        fila["name"] for fila in cursor.execute("PRAGMA table_info(reservas)").fetchall()
    ]
    if "nombre_reserva" not in columnas_reservas:
        cursor.execute("ALTER TABLE reservas ADD COLUMN nombre_reserva TEXT NOT NULL DEFAULT ''")
    if "identificacion" not in columnas_reservas:
        cursor.execute("ALTER TABLE reservas ADD COLUMN identificacion TEXT NOT NULL DEFAULT ''")

    # 5. Tabla de equipos creados por jugadores (capitanes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            tipo_futbol TEXT NOT NULL,
            capitan_id INTEGER NOT NULL,
            descripcion TEXT NOT NULL,
            FOREIGN KEY (capitan_id) REFERENCES usuarios(id)
        )
    """)

    # 6. Tabla de partidos publicados por equipos que buscan rival
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            lugar TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    """)

    # 7. Tabla de solicitudes ("Quiero jugar") enviadas a un partido publicado
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partido_id INTEGER NOT NULL,
            equipo_id INTEGER NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            FOREIGN KEY (partido_id) REFERENCES partidos(id),
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    """)

    conexion.commit()
    conexion.close()


# ---------------- FUNCIONES DE USUARIOS (ETAPA 2) ----------------

def registrar_usuario(nombre, correo, contrasena_hash, tipo_usuario):
    """Guarda un nuevo usuario en la tabla usuarios usando parámetros seguros."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario)
        VALUES (?, ?, ?, ?)
        """,
        (nombre, correo, contrasena_hash, tipo_usuario)
    )
    conexion.commit()
    conexion.close()


def buscar_usuario_por_correo(correo):
    """Busca un usuario por su correo electrónico. Devuelve el usuario o None."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE correo = ?", (correo,))
    usuario = cursor.fetchone()
    conexion.close()
    return usuario


def buscar_usuario_por_id(usuario_id):
    """Busca un usuario por su ID. Devuelve el usuario o None."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    usuario = cursor.fetchone()
    conexion.close()
    return usuario


def actualizar_perfil_usuario(usuario_id, nuevo_nombre, ruta_foto):
    """Actualiza el nombre y la ruta de la foto de perfil de un usuario."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET nombre = ?, foto = ?
        WHERE id = ?
        """,
        (nuevo_nombre, ruta_foto, usuario_id)
    )
    conexion.commit()
    conexion.close()


def guardar_codigo_recuperacion(usuario_id, codigo, fecha_expira):
    """Guarda el código temporal de recuperación y su fecha de vencimiento."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET codigo_recuperacion = ?, codigo_expira = ?
        WHERE id = ?
        """,
        (codigo, fecha_expira, usuario_id)
    )
    conexion.commit()
    conexion.close()


def actualizar_contrasena_usuario(usuario_id, nueva_contrasena_hash):
    """Actualiza la contraseña (hash) del usuario y borra el código de recuperación usado."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE usuarios
        SET contrasena = ?, codigo_recuperacion = '', codigo_expira = ''
        WHERE id = ?
        """,
        (nueva_contrasena_hash, usuario_id)
    )
    conexion.commit()
    conexion.close()


# ---------------- FUNCIONES DE CANCHAS Y HORARIOS (ETAPA 3) ----------------

def crear_cancha(nombre, direccion, precio, tipo_futbol, imagen, administrador_id):
    """Registra una nueva cancha sintética asociada a su administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO canchas (nombre, direccion, precio, tipo_futbol, imagen, administrador_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (nombre, direccion, precio, tipo_futbol, imagen, administrador_id)
    )
    cancha_id = cursor.lastrowid
    conexion.commit()
    conexion.close()
    return cancha_id


def obtener_todas_las_canchas(tipo_futbol=None):
    """Devuelve la lista de canchas registradas. Permite filtrar por tipo de fútbol."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if tipo_futbol:
        cursor.execute(
            """
            SELECT canchas.*, usuarios.nombre AS nombre_administrador
            FROM canchas
            JOIN usuarios ON canchas.administrador_id = usuarios.id
            WHERE canchas.tipo_futbol = ?
            ORDER BY canchas.id DESC
            """,
            (tipo_futbol,)
        )
    else:
        cursor.execute(
            """
            SELECT canchas.*, usuarios.nombre AS nombre_administrador
            FROM canchas
            JOIN usuarios ON canchas.administrador_id = usuarios.id
            ORDER BY canchas.id DESC
            """
        )

    canchas = cursor.fetchall()
    conexion.close()
    return canchas


def obtener_canchas_por_administrador(administrador_id):
    """Devuelve únicamente las canchas que pertenecen a un administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT * FROM canchas
        WHERE administrador_id = ?
        ORDER BY id DESC
        """,
        (administrador_id,)
    )
    canchas = cursor.fetchall()
    conexion.close()
    return canchas


def obtener_cancha_por_id(cancha_id):
    """Busca una cancha específica por su ID junto con el nombre de su administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT canchas.*, usuarios.nombre AS nombre_administrador
        FROM canchas
        JOIN usuarios ON canchas.administrador_id = usuarios.id
        WHERE canchas.id = ?
        """,
        (cancha_id,)
    )
    cancha = cursor.fetchone()
    conexion.close()
    return cancha


def actualizar_cancha(cancha_id, administrador_id, nombre, direccion, precio, tipo_futbol, imagen):
    """Actualiza los datos de una cancha solo si pertenece al administrador indicado."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE canchas
        SET nombre = ?, direccion = ?, precio = ?, tipo_futbol = ?, imagen = ?
        WHERE id = ? AND administrador_id = ?
        """,
        (nombre, direccion, precio, tipo_futbol, imagen, cancha_id, administrador_id)
    )
    actualizadas = cursor.rowcount
    conexion.commit()
    conexion.close()
    return actualizadas > 0


def eliminar_cancha(cancha_id, administrador_id):
    """Elimina una cancha junto con sus horarios y reservas si pertenece al administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Verificamos primero que la cancha exista y pertenezca a este administrador
    cursor.execute(
        "SELECT id FROM canchas WHERE id = ? AND administrador_id = ?",
        (cancha_id, administrador_id)
    )
    if not cursor.fetchone():
        conexion.close()
        return False

    # Eliminamos primero los registros dependientes por las llaves foráneas
    cursor.execute("DELETE FROM reservas WHERE cancha_id = ?", (cancha_id,))
    cursor.execute("DELETE FROM horarios WHERE cancha_id = ?", (cancha_id,))
    cursor.execute(
        "DELETE FROM canchas WHERE id = ? AND administrador_id = ?",
        (cancha_id, administrador_id)
    )
    conexion.commit()
    conexion.close()
    return True


def agregar_horario(cancha_id, fecha, hora):
    """Agrega un horario disponible a una cancha si no está repetido."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Verificamos si ese mismo horario ya existe para esa cancha
    cursor.execute(
        """
        SELECT id FROM horarios
        WHERE cancha_id = ? AND fecha = ? AND hora = ?
        """,
        (cancha_id, fecha, hora)
    )
    if cursor.fetchone():
        conexion.close()
        return False

    cursor.execute(
        """
        INSERT INTO horarios (cancha_id, fecha, hora)
        VALUES (?, ?, ?)
        """,
        (cancha_id, fecha, hora)
    )
    conexion.commit()
    conexion.close()
    return True


def obtener_horarios_de_cancha(cancha_id):
    """Devuelve los horarios disponibles de una cancha ordenados por fecha y hora."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT * FROM horarios
        WHERE cancha_id = ?
        ORDER BY fecha ASC, hora ASC
        """,
        (cancha_id,)
    )
    horarios = cursor.fetchall()
    conexion.close()
    return horarios


def eliminar_horario(horario_id, administrador_id):
    """Elimina un horario solo si pertenece a una cancha del administrador indicado."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        DELETE FROM horarios
        WHERE id = ?
          AND cancha_id IN (SELECT id FROM canchas WHERE administrador_id = ?)
        """,
        (horario_id, administrador_id)
    )
    eliminados = cursor.rowcount
    conexion.commit()
    conexion.close()
    return eliminados > 0


def cargar_datos_iniciales(contrasena_admin_hash):
    """
    Si todavía no hay canchas en la base de datos, crea un administrador de ejemplo
    y dos canchas sintéticas con horarios próximos para que la aplicación no inicie vacía.
    """
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT COUNT(*) AS total FROM canchas")
    total_canchas = cursor.fetchone()["total"]
    conexion.close()

    if total_canchas > 0:
        return

    # Buscamos o creamos un administrador de ejemplo
    admin_ejemplo = buscar_usuario_por_correo("admin@canchaapp.co")
    if not admin_ejemplo:
        registrar_usuario(
            "Administrador Demo",
            "admin@canchaapp.co",
            contrasena_admin_hash,
            "administrador"
        )
        admin_ejemplo = buscar_usuario_por_correo("admin@canchaapp.co")

    admin_id = admin_ejemplo["id"]

    # Creamos dos canchas sintéticas de ejemplo
    cancha1_id = crear_cancha(
        "Cancha Sintética El Golazo",
        "Calle 45 # 23-10, Bogotá",
        90000,
        "Fútbol 5",
        "imagenes/cancha1.jpg",
        admin_id
    )
    cancha2_id = crear_cancha(
        "Complejo Deportivo La 10",
        "Carrera 70 # 32-15, Medellín",
        130000,
        "Fútbol 7",
        "imagenes/cancha2.jpg",
        admin_id
    )

    # Agregamos horarios para mañana y pasado mañana
    manana = (date.today() + timedelta(days=1)).isoformat()
    pasado_manana = (date.today() + timedelta(days=2)).isoformat()

    for hora in ["17:00", "18:00", "19:00", "20:00"]:
        agregar_horario(cancha1_id, manana, hora)
        agregar_horario(cancha2_id, manana, hora)

    for hora in ["18:00", "19:00", "20:00"]:
        agregar_horario(cancha1_id, pasado_manana, hora)
        agregar_horario(cancha2_id, pasado_manana, hora)


# ---------------- FUNCIONES DE RESERVAS (ETAPA 4) ----------------

def existe_horario(cancha_id, fecha, hora):
    """Comprueba si el administrador registró ese horario para esa cancha."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT id FROM horarios
        WHERE cancha_id = ? AND fecha = ? AND hora = ?
        """,
        (cancha_id, fecha, hora)
    )
    resultado = cursor.fetchone()
    conexion.close()
    return resultado is not None


def existe_reserva_confirmada(cancha_id, fecha, hora):
    """Comprueba si ya hay una reserva CONFIRMADA para la misma cancha, fecha y hora."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT id FROM reservas
        WHERE cancha_id = ? AND fecha = ? AND hora = ? AND estado = 'confirmada'
        """,
        (cancha_id, fecha, hora)
    )
    resultado = cursor.fetchone()
    conexion.close()
    return resultado is not None


def usuario_tiene_reserva_activa(usuario_id, cancha_id, fecha, hora):
    """Evita que el mismo jugador envíe varias solicitudes repetidas al mismo turno."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT id FROM reservas
        WHERE usuario_id = ? AND cancha_id = ? AND fecha = ? AND hora = ?
          AND estado IN ('pendiente', 'confirmada')
        """,
        (usuario_id, cancha_id, fecha, hora)
    )
    resultado = cursor.fetchone()
    conexion.close()
    return resultado is not None


def crear_reserva(usuario_id, cancha_id, fecha, hora, nombre_reserva, identificacion):
    """Guarda una nueva solicitud de reserva con los datos del titular y estado 'pendiente'."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO reservas (usuario_id, cancha_id, fecha, hora, estado, nombre_reserva, identificacion)
        VALUES (?, ?, ?, ?, 'pendiente', ?, ?)
        """,
        (usuario_id, cancha_id, fecha, hora, nombre_reserva, identificacion)
    )
    conexion.commit()
    conexion.close()


def obtener_horarios_confirmados_de_cancha(cancha_id):
    """Devuelve un conjunto de tuplas (fecha, hora) que ya están confirmadas en una cancha."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT fecha, hora FROM reservas
        WHERE cancha_id = ? AND estado = 'confirmada'
        """,
        (cancha_id,)
    )
    filas = cursor.fetchall()
    conexion.close()
    return {(fila["fecha"], fila["hora"]) for fila in filas}


def obtener_reservas_por_usuario(usuario_id):
    """Devuelve todas las reservas hechas por un jugador junto con los datos de la cancha."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT reservas.*, canchas.nombre AS nombre_cancha,
               canchas.direccion AS direccion_cancha,
               canchas.precio AS precio_cancha,
               canchas.tipo_futbol AS tipo_futbol
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        WHERE reservas.usuario_id = ?
        ORDER BY reservas.fecha DESC, reservas.hora DESC, reservas.id DESC
        """,
        (usuario_id,)
    )
    reservas = cursor.fetchall()
    conexion.close()
    return reservas


def obtener_reservas_por_administrador(administrador_id):
    """Devuelve todas las solicitudes de reserva de las canchas que pertenecen a un administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT reservas.*, canchas.nombre AS nombre_cancha,
               canchas.precio AS precio_cancha,
               usuarios.nombre AS nombre_jugador,
               usuarios.correo AS correo_jugador
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        JOIN usuarios ON reservas.usuario_id = usuarios.id
        WHERE canchas.administrador_id = ?
        ORDER BY
            CASE reservas.estado
                WHEN 'pendiente' THEN 1
                WHEN 'confirmada' THEN 2
                ELSE 3
            END,
            reservas.fecha ASC,
            reservas.hora ASC
        """,
        (administrador_id,)
    )
    reservas = cursor.fetchall()
    conexion.close()
    return reservas


def obtener_reserva_por_id(reserva_id):
    """Busca una reserva específica junto con el administrador dueño de la cancha."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT reservas.*, canchas.administrador_id AS administrador_id,
               canchas.nombre AS nombre_cancha
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        WHERE reservas.id = ?
        """,
        (reserva_id,)
    )
    reserva = cursor.fetchone()
    conexion.close()
    return reserva


def actualizar_estado_reserva(reserva_id, nuevo_estado):
    """Cambia el estado de una reserva ('confirmada' o 'rechazada')."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE reservas
        SET estado = ?
        WHERE id = ?
        """,
        (nuevo_estado, reserva_id)
    )
    conexion.commit()
    conexion.close()


# ---------------- FUNCIONES DE EQUIPOS (ETAPA 5) ----------------

def existe_equipo_por_nombre(nombre):
    """Comprueba si ya existe un equipo registrado con ese mismo nombre."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id FROM equipos WHERE LOWER(nombre) = LOWER(?)",
        (nombre,)
    )
    resultado = cursor.fetchone()
    conexion.close()
    return resultado is not None


def crear_equipo(nombre, categoria, tipo_futbol, capitan_id, descripcion):
    """Guarda un nuevo equipo en la tabla equipos asociado a su capitán."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO equipos (nombre, categoria, tipo_futbol, capitan_id, descripcion)
        VALUES (?, ?, ?, ?, ?)
        """,
        (nombre, categoria, tipo_futbol, capitan_id, descripcion)
    )
    conexion.commit()
    conexion.close()


def obtener_todos_los_equipos(categoria=None):
    """Devuelve todos los equipos junto con el nombre de su capitán. Permite filtrar por categoría."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if categoria:
        cursor.execute(
            """
            SELECT equipos.*, usuarios.nombre AS nombre_capitan
            FROM equipos
            JOIN usuarios ON equipos.capitan_id = usuarios.id
            WHERE equipos.categoria = ?
            ORDER BY equipos.id DESC
            """,
            (categoria,)
        )
    else:
        cursor.execute(
            """
            SELECT equipos.*, usuarios.nombre AS nombre_capitan
            FROM equipos
            JOIN usuarios ON equipos.capitan_id = usuarios.id
            ORDER BY equipos.id DESC
            """
        )

    equipos = cursor.fetchall()
    conexion.close()
    return equipos


def obtener_equipos_por_capitan(capitan_id):
    """Devuelve los equipos donde el jugador indicado es el capitán."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT * FROM equipos
        WHERE capitan_id = ?
        ORDER BY id DESC
        """,
        (capitan_id,)
    )
    equipos = cursor.fetchall()
    conexion.close()
    return equipos


def obtener_equipo_por_id(equipo_id):
    """Busca un equipo específico por su ID."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,))
    equipo = cursor.fetchone()
    conexion.close()
    return equipo


# ---------------- FUNCIONES DE PARTIDOS Y RIVALES (ETAPA 6) ----------------

def crear_partido(equipo_id, fecha, hora, lugar, descripcion):
    """Guarda una nueva publicación de un equipo buscando rival."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO partidos (equipo_id, fecha, hora, lugar, descripcion)
        VALUES (?, ?, ?, ?, ?)
        """,
        (equipo_id, fecha, hora, lugar, descripcion)
    )
    conexion.commit()
    conexion.close()


def obtener_todos_los_partidos(tipo_futbol=None, categoria=None):
    """Devuelve las publicaciones de partidos junto con los datos del equipo y su capitán."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    consulta = """
        SELECT partidos.*,
               equipos.nombre AS nombre_equipo,
               equipos.categoria AS categoria,
               equipos.tipo_futbol AS tipo_futbol,
               equipos.capitan_id AS capitan_id,
               usuarios.nombre AS nombre_capitan
        FROM partidos
        JOIN equipos ON partidos.equipo_id = equipos.id
        JOIN usuarios ON equipos.capitan_id = usuarios.id
        WHERE 1 = 1
    """
    parametros = []

    if tipo_futbol:
        consulta += " AND equipos.tipo_futbol = ?"
        parametros.append(tipo_futbol)

    if categoria:
        consulta += " AND equipos.categoria = ?"
        parametros.append(categoria)

    consulta += " ORDER BY partidos.fecha ASC, partidos.hora ASC, partidos.id DESC"

    cursor.execute(consulta, parametros)
    partidos = cursor.fetchall()
    conexion.close()
    return partidos


def obtener_partido_por_id(partido_id):
    """Busca un partido publicado junto con el equipo y el ID de su capitán."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT partidos.*,
               equipos.nombre AS nombre_equipo,
               equipos.capitan_id AS capitan_id
        FROM partidos
        JOIN equipos ON partidos.equipo_id = equipos.id
        WHERE partidos.id = ?
        """,
        (partido_id,)
    )
    partido = cursor.fetchone()
    conexion.close()
    return partido


def existe_solicitud(partido_id, equipo_id):
    """Comprueba si ese equipo ya envió una solicitud a ese partido."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT id FROM solicitudes
        WHERE partido_id = ? AND equipo_id = ?
        """,
        (partido_id, equipo_id)
    )
    resultado = cursor.fetchone()
    conexion.close()
    return resultado is not None


def obtener_rival_aceptado(partido_id):
    """Devuelve el nombre del equipo rival aceptado para un partido, o None si aún busca rival."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT equipos.nombre AS nombre_rival
        FROM solicitudes
        JOIN equipos ON solicitudes.equipo_id = equipos.id
        WHERE solicitudes.partido_id = ? AND solicitudes.estado = 'aceptada'
        """,
        (partido_id,)
    )
    fila = cursor.fetchone()
    conexion.close()
    if fila:
        return fila["nombre_rival"]
    return None


def crear_solicitud(partido_id, equipo_id):
    """Registra una solicitud 'Quiero jugar' con estado inicial 'pendiente'."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO solicitudes (partido_id, equipo_id, estado)
        VALUES (?, ?, 'pendiente')
        """,
        (partido_id, equipo_id)
    )
    conexion.commit()
    conexion.close()


def obtener_solicitudes_recibidas(capitan_id):
    """Devuelve las solicitudes que otros equipos enviaron a los partidos de este capitán."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT solicitudes.*,
               partidos.fecha AS fecha,
               partidos.hora AS hora,
               partidos.lugar AS lugar,
               equipo_publicador.nombre AS mi_equipo,
               equipo_retador.nombre AS equipo_retador,
               equipo_retador.categoria AS categoria_retador,
               equipo_retador.tipo_futbol AS tipo_futbol_retador,
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
            solicitudes.id DESC
        """,
        (capitan_id,)
    )
    solicitudes = cursor.fetchall()
    conexion.close()
    return solicitudes


def obtener_solicitudes_enviadas(capitan_id):
    """Devuelve las solicitudes 'Quiero jugar' que enviaron los equipos de este capitán."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT solicitudes.*,
               partidos.fecha AS fecha,
               partidos.hora AS hora,
               partidos.lugar AS lugar,
               equipo_publicador.nombre AS equipo_publicador,
               equipo_propio.nombre AS mi_equipo
        FROM solicitudes
        JOIN partidos ON solicitudes.partido_id = partidos.id
        JOIN equipos AS equipo_publicador ON partidos.equipo_id = equipo_publicador.id
        JOIN equipos AS equipo_propio ON solicitudes.equipo_id = equipo_propio.id
        WHERE equipo_propio.capitan_id = ?
        ORDER BY solicitudes.id DESC
        """,
        (capitan_id,)
    )
    solicitudes = cursor.fetchall()
    conexion.close()
    return solicitudes


def obtener_solicitud_por_id(solicitud_id):
    """Busca una solicitud junto con el capitán dueño del partido publicado."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        SELECT solicitudes.*,
               partidos.fecha AS fecha,
               partidos.hora AS hora,
               equipo_publicador.capitan_id AS capitan_publicador_id,
               equipo_retador.nombre AS nombre_retador
        FROM solicitudes
        JOIN partidos ON solicitudes.partido_id = partidos.id
        JOIN equipos AS equipo_publicador ON partidos.equipo_id = equipo_publicador.id
        JOIN equipos AS equipo_retador ON solicitudes.equipo_id = equipo_retador.id
        WHERE solicitudes.id = ?
        """,
        (solicitud_id,)
    )
    solicitud = cursor.fetchone()
    conexion.close()
    return solicitud


def actualizar_estado_solicitud(solicitud_id, nuevo_estado):
    """Actualiza el estado de una solicitud ('aceptada' o 'rechazada')."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE solicitudes
        SET estado = ?
        WHERE id = ?
        """,
        (nuevo_estado, solicitud_id)
    )
    conexion.commit()
    conexion.close()
