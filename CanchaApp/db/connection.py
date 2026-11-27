"""Conexión SQLite protegida y migraciones consolidadas, seguras e idempotentes de Ready Match."""

from datetime import timedelta
import os
import sqlite3

from config import MESES_GRATIS_BETA, RUTA_BD, hoy_colombia


def _verificar_bd_existe(ruta=RUTA_BD, permitir_crear=False):
    """Impide crear una base vacía en silencio si el archivo esperado no existe."""
    if os.path.exists(ruta):
        return
    if permitir_crear or os.environ.get("INICIALIZAR_BD", "0") == "1":
        return
    raise FileNotFoundError(
        f"[Ready Match] No se encontró la base de datos en la ruta esperada: {ruta}\n"
        "La aplicación se detuvo para evitar crear una base vacía por accidente.\n"
        "Restaura una copia desde backups/ o inicia intencionalmente una base nueva con "
        "INICIALIZAR_BD=1 python app.py."
    )


def obtener_conexion(permitir_crear=False):
    """Abre y devuelve una conexión SQLite con Row factory y llaves foráneas activas."""
    _verificar_bd_existe(RUTA_BD, permitir_crear=permitir_crear)
    conexion = sqlite3.connect(RUTA_BD, timeout=15)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def _agregar_columna_si_falta(cursor, tabla, columna, definicion):
    """Agrega una columna a una tabla existente sin perder registros previos."""
    existentes = [fila["name"] for fila in cursor.execute(f"PRAGMA table_info({tabla})").fetchall()]
    if columna not in existentes:
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def crear_tablas(permitir_crear=False):
    """
    Aplica las migraciones consolidadas (01 a 10) de forma no destructiva e idempotente.
    Solo crea el archivo de base de datos si ya existe o si permitir_crear=True / INICIALIZAR_BD=1.
    """
    conexion = obtener_conexion(permitir_crear=permitir_crear)
    cursor = conexion.cursor()

    # Migración 01: Usuarios (jugadores y administradores) + columnas de perfil y celular
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL UNIQUE,
            contrasena TEXT NOT NULL,
            tipo_usuario TEXT NOT NULL,
            foto TEXT NOT NULL DEFAULT '',
            codigo_recuperacion TEXT NOT NULL DEFAULT '',
            codigo_expira TEXT NOT NULL DEFAULT '',
            ultimo_recordatorio TEXT NOT NULL DEFAULT '',
            deportes_favoritos TEXT NOT NULL DEFAULT '',
            telefono TEXT NOT NULL DEFAULT ''
        )
    """)
    _agregar_columna_si_falta(cursor, "usuarios", "foto", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "usuarios", "codigo_recuperacion", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "usuarios", "codigo_expira", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "usuarios", "ultimo_recordatorio", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "usuarios", "deportes_favoritos", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "usuarios", "telefono", "TEXT NOT NULL DEFAULT ''")

    # Migración 02: Canchas / establecimientos deportivos (tipo_futbol se conserva intacta)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS canchas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            direccion TEXT NOT NULL,
            precio INTEGER NOT NULL,
            tipo_futbol TEXT NOT NULL,
            imagen TEXT NOT NULL,
            administrador_id INTEGER NOT NULL,
            deporte TEXT NOT NULL DEFAULT 'Fútbol',
            tipo_cancha TEXT NOT NULL DEFAULT 'Sintética',
            descripcion TEXT NOT NULL DEFAULT '',
            caracteristicas TEXT NOT NULL DEFAULT '',
            telefono TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (administrador_id) REFERENCES usuarios(id)
        )
    """)
    _agregar_columna_si_falta(cursor, "canchas", "deporte", "TEXT NOT NULL DEFAULT 'Fútbol'")
    _agregar_columna_si_falta(cursor, "canchas", "tipo_cancha", "TEXT NOT NULL DEFAULT 'Sintética'")
    _agregar_columna_si_falta(cursor, "canchas", "descripcion", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "canchas", "caracteristicas", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "canchas", "telefono", "TEXT NOT NULL DEFAULT ''")

    # Migración 03: Deportes adicionales, tarifas por horario y favoritos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cancha_deportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cancha_id INTEGER NOT NULL,
            deporte TEXT NOT NULL,
            FOREIGN KEY (cancha_id) REFERENCES canchas(id)
        )
    """)

    # 2c. Tarifas por horario y día de la semana (Fase 3)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tarifas_cancha (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cancha_id INTEGER NOT NULL,
            dias_semana TEXT NOT NULL,
            hora_inicio TEXT NOT NULL,
            hora_fin TEXT NOT NULL,
            precio INTEGER NOT NULL,
            FOREIGN KEY (cancha_id) REFERENCES canchas(id)
        )
    """)

    # 2d. Favoritos de canchas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favoritos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cancha_id INTEGER NOT NULL,
            UNIQUE(usuario_id, cancha_id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (cancha_id) REFERENCES canchas(id)
        )
    """)

    # Migración 04: Horarios y bloqueos de turnos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS horarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cancha_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            bloqueado INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (cancha_id) REFERENCES canchas(id)
        )
    """)
    _agregar_columna_si_falta(cursor, "horarios", "bloqueado", "INTEGER NOT NULL DEFAULT 0")

    # Migración 05: Reservas, pagos, cancelaciones, índice anti-doble reserva y backfill de precio
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cancha_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'confirmada',
            nombre_reserva TEXT NOT NULL DEFAULT '',
            identificacion TEXT NOT NULL DEFAULT '',
            deporte_reserva TEXT NOT NULL DEFAULT '',
            modalidad_reserva TEXT NOT NULL DEFAULT '',
            origen TEXT NOT NULL DEFAULT 'web',
            estado_pago TEXT NOT NULL DEFAULT 'pendiente',
            monto_abonado INTEGER NOT NULL DEFAULT 0,
            precio_aplicado INTEGER NOT NULL DEFAULT 0,
            telefono_reserva TEXT NOT NULL DEFAULT '',
            cancelada_por_rol TEXT NOT NULL DEFAULT '',
            cancelada_por_id INTEGER,
            cancelada_en TEXT NOT NULL DEFAULT '',
            motivo_cancelacion TEXT NOT NULL DEFAULT '',
            reserva_fija_id INTEGER,
            recordatorio_enviado_en TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (cancha_id) REFERENCES canchas(id)
        )
    """)
    _agregar_columna_si_falta(cursor, "reservas", "nombre_reserva", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "identificacion", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "deporte_reserva", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "modalidad_reserva", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "origen", "TEXT NOT NULL DEFAULT 'web'")
    _agregar_columna_si_falta(cursor, "reservas", "estado_pago", "TEXT NOT NULL DEFAULT 'pendiente'")
    _agregar_columna_si_falta(cursor, "reservas", "monto_abonado", "INTEGER NOT NULL DEFAULT 0")
    _agregar_columna_si_falta(cursor, "reservas", "precio_aplicado", "INTEGER NOT NULL DEFAULT 0")
    _agregar_columna_si_falta(cursor, "reservas", "telefono_reserva", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "cancelada_por_rol", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "cancelada_por_id", "INTEGER")
    _agregar_columna_si_falta(cursor, "reservas", "cancelada_en", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "motivo_cancelacion", "TEXT NOT NULL DEFAULT ''")
    _agregar_columna_si_falta(cursor, "reservas", "reserva_fija_id", "INTEGER")
    _agregar_columna_si_falta(cursor, "reservas", "recordatorio_enviado_en", "TEXT NOT NULL DEFAULT ''")

    # Índice único parcial: impide dos reservas activas en la misma cancha, fecha y hora
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reservas_turno_activo
        ON reservas (cancha_id, fecha, hora)
        WHERE estado IN ('confirmada', 'pendiente')
    """)

    # Completar precio_aplicado en reservas antiguas que aún tengan 0
    cursor.execute("""
        UPDATE reservas
        SET precio_aplicado = COALESCE(
            (SELECT precio FROM canchas WHERE canchas.id = reservas.cancha_id),
            0
        )
        WHERE precio_aplicado = 0
    """)

    # Migración 06: Reservas fijas semanales y sus excepciones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas_fijas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cancha_id INTEGER NOT NULL,
            dia_semana INTEGER NOT NULL,
            hora TEXT NOT NULL,
            nombre_cliente TEXT NOT NULL,
            telefono_cliente TEXT NOT NULL DEFAULT '',
            usuario_id INTEGER,
            deporte_reserva TEXT NOT NULL DEFAULT 'Fútbol',
            modalidad_reserva TEXT NOT NULL DEFAULT '',
            fecha_inicio TEXT NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1,
            creada_en TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (cancha_id) REFERENCES canchas(id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas_fijas_excepciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reserva_fija_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            motivo TEXT NOT NULL DEFAULT '',
            creada_en TEXT NOT NULL DEFAULT '',
            UNIQUE(reserva_fija_id, fecha),
            FOREIGN KEY (reserva_fija_id) REFERENCES reservas_fijas(id)
        )
    """)

    # Migración 07: Suscripciones de administradores (base técnica Plan Beta)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suscripciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            administrador_id INTEGER NOT NULL UNIQUE,
            estado TEXT NOT NULL DEFAULT 'beta',
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT NOT NULL,
            FOREIGN KEY (administrador_id) REFERENCES usuarios(id)
        )
    """)

    # Migración 08: Equipos e integrantes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            tipo_futbol TEXT NOT NULL,
            capitan_id INTEGER NOT NULL,
            descripcion TEXT NOT NULL,
            deporte TEXT NOT NULL DEFAULT 'Fútbol',
            FOREIGN KEY (capitan_id) REFERENCES usuarios(id)
        )
    """)
    _agregar_columna_si_falta(cursor, "equipos", "deporte", "TEXT NOT NULL DEFAULT 'Fútbol'")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipo_integrantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id INTEGER NOT NULL,
            nombre_integrante TEXT NOT NULL,
            posicion TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    """)

    # Migración 09: Partidos, solicitudes y notificaciones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            lugar TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            nivel TEXT NOT NULL DEFAULT 'Intermedio',
            deporte TEXT NOT NULL DEFAULT 'Fútbol',
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    """)
    _agregar_columna_si_falta(cursor, "partidos", "nivel", "TEXT NOT NULL DEFAULT 'Intermedio'")
    _agregar_columna_si_falta(cursor, "partidos", "deporte", "TEXT NOT NULL DEFAULT 'Fútbol'")

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '/',
            tipo TEXT NOT NULL DEFAULT 'general',
            enviada INTEGER NOT NULL DEFAULT 0,
            creada_en TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    # Migración 10: Suscripción Beta inicial para administradores sin registro previo
    hoy = hoy_colombia()
    fin_beta = (hoy + timedelta(days=30 * MESES_GRATIS_BETA)).isoformat()
    admins = cursor.execute("SELECT id FROM usuarios WHERE tipo_usuario = 'administrador'").fetchall()
    for adm in admins:
        cursor.execute(
            """
            INSERT OR IGNORE INTO suscripciones (administrador_id, estado, fecha_inicio, fecha_fin)
            VALUES (?, 'beta', ?, ?)
            """,
            (adm["id"], hoy.isoformat(), fin_beta),
        )

    conexion.commit()
    conexion.close()
