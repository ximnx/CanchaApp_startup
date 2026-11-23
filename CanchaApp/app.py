# Importamos funciones estándar de Python para fechas, rutas, tiempo y correo
from datetime import date, datetime, timedelta
from email.message import EmailMessage
import os
import secrets
import smtplib
import time

# Importamos las funciones básicas de Flask
from flask import Flask, render_template, request, redirect, url_for, session, flash

# Importamos funciones de Werkzeug para contraseñas seguras y nombres de archivo seguros
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Importamos nuestras funciones de base de datos desde database.py
from database import (
    crear_tablas,
    cargar_datos_iniciales,
    registrar_usuario,
    buscar_usuario_por_correo,
    buscar_usuario_por_id,
    actualizar_perfil_usuario,
    guardar_codigo_recuperacion,
    actualizar_contrasena_usuario,
    crear_cancha,
    obtener_todas_las_canchas,
    obtener_canchas_por_administrador,
    obtener_cancha_por_id,
    agregar_horario,
    obtener_horarios_de_cancha,
    eliminar_horario,
    existe_horario,
    existe_reserva_confirmada,
    usuario_tiene_reserva_activa,
    crear_reserva,
    obtener_horarios_confirmados_de_cancha,
    obtener_reservas_por_usuario,
    obtener_reservas_por_administrador,
    obtener_reserva_por_id,
    actualizar_estado_reserva,
    existe_equipo_por_nombre,
    crear_equipo,
    obtener_todos_los_equipos,
    obtener_equipos_por_capitan,
    obtener_equipo_por_id,
    crear_partido,
    obtener_todos_los_partidos,
    obtener_partido_por_id,
    existe_solicitud,
    obtener_rival_aceptado,
    crear_solicitud,
    obtener_solicitudes_recibidas,
    obtener_solicitudes_enviadas,
    obtener_solicitud_por_id,
    actualizar_estado_solicitud,
)

# Creamos nuestra aplicación de Flask
app = Flask(__name__)


def cargar_archivo_env():
    """Carga las variables guardadas en el archivo .env (como el correo y clave de Gmail)."""
    ruta_env = os.path.join(os.path.dirname(__file__), ".env")
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
            if clave and valor:
                os.environ.setdefault(clave, valor)


cargar_archivo_env()

# Clave secreta que usa Flask para proteger las sesiones y los mensajes flash
app.secret_key = "canchaapp_clave_secreta_universitaria"

# Carpeta donde se guardan las fotos subidas de las canchas
CARPETA_IMAGENES = os.path.join(os.path.dirname(__file__), "static", "imagenes")
EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}

# Lista fija de horas disponibles (reservas de 1 hora para mantener el proyecto sencillo)
HORAS_DISPONIBLES = [
    "07:00", "08:00", "09:00", "10:00", "11:00", "12:00",
    "13:00", "14:00", "15:00", "16:00", "17:00", "18:00",
    "19:00", "20:00", "21:00", "22:00"
]

TIPOS_FUTBOL = ["Fútbol 5", "Fútbol 7", "Fútbol 11"]
CATEGORIAS_EQUIPO = ["Masculino", "Femenino", "Mixto"]

# Código secreto que los dueños de CanchaApp entregan para registrar administradores
CODIGO_ADMINISTRADOR = "FUTBOL7"

# Creamos las tablas y cargamos 2 canchas de ejemplo si la base de datos está vacía
crear_tablas()
cargar_datos_iniciales(generate_password_hash("admin123"))


# ---------------- FUNCIONES DE APOYO ----------------

def formatear_precio(precio):
    """Convierte un número como 90000 en '$90.000' para mostrarlo bonito en HTML."""
    return f"${int(precio):,}".replace(",", ".")


# Registramos formatear_precio como filtro para usarlo en los archivos HTML
app.jinja_env.filters["precio_cop"] = formatear_precio


def verificar_disponibilidad(ocupado):
    """Devuelve un texto claro según si un horario está ocupado o disponible."""
    if ocupado:
        return "No disponible"
    else:
        return "Disponible"


def archivo_imagen_valido(nombre_archivo):
    """Verifica si un archivo tiene una extensión de imagen permitida."""
    if "." not in nombre_archivo:
        return False
    extension = nombre_archivo.rsplit(".", 1)[1].lower()
    return extension in EXTENSIONES_PERMITIDAS


def enviar_correo_recuperacion(destinatario, codigo):
    """
    Envía el código de recuperación por Gmail (SMTP) si las variables de entorno
    CORREO_APP y CLAVE_CORREO_APP están configuradas. Si no, lo muestra en consola.
    """
    correo_remitente = os.environ.get("CORREO_APP", "").strip()
    clave_aplicacion = os.environ.get("CLAVE_CORREO_APP", "").replace(" ", "").strip()

    if not correo_remitente or not clave_aplicacion:
        print(f"[CanchaApp - Gmail sin configurar] Código de recuperación para {destinatario}: {codigo}")
        return False

    mensaje = EmailMessage()
    mensaje["Subject"] = "Código de recuperación de contraseña - CanchaApp"
    mensaje["From"] = correo_remitente
    mensaje["To"] = destinatario
    mensaje.set_content(
        f"Hola,\n\n"
        f"Recibimos una solicitud para cambiar tu contraseña en CanchaApp.\n"
        f"Tu código de recuperación es: {codigo}\n\n"
        f"Este código vence en 15 minutos.\n"
        f"Si no solicitaste este cambio, puedes ignorar este correo.\n"
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as servidor:
            servidor.login(correo_remitente, clave_aplicacion)
            servidor.send_message(mensaje)
        return True
    except Exception as error:
        print(f"[CanchaApp - Error SMTP] No se pudo enviar el correo: {error}")
        print(f"[CanchaApp - Respaldo consola] Código para {destinatario}: {codigo}")
        return False


# ---------------- RUTA PRINCIPAL ----------------

@app.route("/")
def inicio():
    canchas_destacadas = obtener_todas_las_canchas()[:3]
    return render_template("index.html", canchas=canchas_destacadas)


# ---------------- REGISTRO DE USUARIOS ----------------

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("contrasena", "")
        tipo_usuario = request.form.get("tipo_usuario", "")
        codigo_admin = request.form.get("codigo_admin", "").strip()

        if not nombre or not correo or not contrasena or not tipo_usuario:
            flash("Por favor completa todos los campos del formulario.", "error")
            return render_template("registro.html")

        if "@" not in correo or "." not in correo:
            flash("Por favor ingresa un correo electrónico válido.", "error")
            return render_template("registro.html")

        if len(contrasena) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("registro.html")

        if tipo_usuario not in ("jugador", "administrador"):
            flash("Tipo de usuario no válido.", "error")
            return render_template("registro.html")

        # Si el usuario quiere ser administrador, debe ingresar el código secreto
        if tipo_usuario == "administrador" and codigo_admin != CODIGO_ADMINISTRADOR:
            flash("Código de administrador incorrecto. Solicítalo a los dueños de CanchaApp.", "error")
            return render_template("registro.html")

        if buscar_usuario_por_correo(correo):
            flash("Ya existe una cuenta registrada con ese correo.", "error")
            return render_template("registro.html")

        contrasena_hash = generate_password_hash(contrasena)
        registrar_usuario(nombre, correo, contrasena_hash, tipo_usuario)

        flash("¡Cuenta creada con éxito! Ahora puedes iniciar sesión.", "exito")
        return redirect(url_for("login"))

    return render_template("registro.html")


# ---------------- INICIO DE SESIÓN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("contrasena", "")

        if not correo or not contrasena:
            flash("Por favor ingresa tu correo y contraseña.", "error")
            return render_template("login.html")

        usuario = buscar_usuario_por_correo(correo)

        if usuario and check_password_hash(usuario["contrasena"], contrasena):
            session["usuario_id"] = usuario["id"]
            session["usuario_nombre"] = usuario["nombre"]
            session["tipo_usuario"] = usuario["tipo_usuario"]
            session["usuario_foto"] = usuario["foto"]

            flash(f"¡Hola, {usuario['nombre']}! Has iniciado sesión.", "exito")

            if usuario["tipo_usuario"] == "administrador":
                return redirect(url_for("panel_administrador"))
            else:
                return redirect(url_for("inicio"))
        else:
            flash("Correo o contraseña incorrectos.", "error")
            return render_template("login.html")

    return render_template("login.html")


# ---------------- RECUPERACIÓN DE CONTRASEÑA ----------------

@app.route("/olvide_contrasena", methods=["GET", "POST"])
def olvide_contrasena():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()

        if not correo or "@" not in correo or "." not in correo:
            flash("Por favor ingresa un correo electrónico válido.", "error")
            return render_template("olvide_contrasena.html")

        usuario = buscar_usuario_por_correo(correo)

        # Solo generamos y enviamos el código si el correo existe en la base de datos
        if usuario:
            codigo = str(secrets.randbelow(900000) + 100000)
            fecha_expira = (datetime.now() + timedelta(minutes=15)).isoformat()
            guardar_codigo_recuperacion(usuario["id"], codigo, fecha_expira)
            enviar_correo_recuperacion(correo, codigo)

        # Recordamos el correo solo para facilitar el siguiente paso en el formulario
        session["correo_recuperacion"] = correo
        flash(
            "Si el correo está registrado, enviamos un código de 6 dígitos para recuperar tu contraseña.",
            "exito"
        )
        return redirect(url_for("restablecer_contrasena"))

    return render_template("olvide_contrasena.html")


@app.route("/restablecer_contrasena", methods=["GET", "POST"])
def restablecer_contrasena():
    correo_sugerido = session.get("correo_recuperacion", "")

    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        codigo = request.form.get("codigo", "").strip()
        nueva_contrasena = request.form.get("nueva_contrasena", "")
        confirmar_contrasena = request.form.get("confirmar_contrasena", "")

        if not correo or not codigo or not nueva_contrasena or not confirmar_contrasena:
            flash("Por favor completa todos los campos.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        if len(nueva_contrasena) < 6:
            flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        if nueva_contrasena != confirmar_contrasena:
            flash("Las contraseñas no coinciden.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        usuario = buscar_usuario_por_correo(correo)
        if not usuario or not usuario["codigo_recuperacion"] or usuario["codigo_recuperacion"] != codigo:
            flash("Correo o código de recuperación incorrecto.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        # Verificamos que el código no haya expirado
        if not usuario["codigo_expira"] or datetime.now() > datetime.fromisoformat(usuario["codigo_expira"]):
            flash("El código ha vencido. Por favor solicita uno nuevo.", "error")
            return redirect(url_for("olvide_contrasena"))

        nueva_hash = generate_password_hash(nueva_contrasena)
        actualizar_contrasena_usuario(usuario["id"], nueva_hash)
        session.pop("correo_recuperacion", None)

        flash("¡Contraseña actualizada con éxito! Ya puedes iniciar sesión.", "exito")
        return redirect(url_for("login"))

    return render_template("restablecer_contrasena.html", correo=correo_sugerido)


# ---------------- CERRAR SESIÓN ----------------

@app.route("/cerrar_sesion")
def cerrar_sesion():
    session.clear()
    flash("Has cerrado sesión correctamente.", "exito")
    return redirect(url_for("inicio"))


# ---------------- PERFIL DE USUARIO (EDITAR NOMBRE Y FOTO) ----------------

@app.route("/perfil", methods=["GET", "POST"])
def mi_perfil():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para ver tu perfil.", "error")
        return redirect(url_for("login"))

    usuario = buscar_usuario_por_id(session["usuario_id"])
    if not usuario:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        nuevo_nombre = request.form.get("nombre", "").strip()

        if len(nuevo_nombre) < 2:
            flash("Por favor escribe un nombre válido (mínimo 2 caracteres).", "error")
            return render_template("perfil.html", usuario=usuario)

        # Conservamos la foto actual si el usuario no sube una nueva
        ruta_foto = usuario["foto"]
        archivo = request.files.get("foto")

        if archivo and archivo.filename:
            if archivo_imagen_valido(archivo.filename):
                nombre_seguro = secure_filename(archivo.filename)
                nombre_final = f"perfil_{session['usuario_id']}_{int(time.time())}_{nombre_seguro}"
                os.makedirs(CARPETA_IMAGENES, exist_ok=True)
                archivo.save(os.path.join(CARPETA_IMAGENES, nombre_final))
                ruta_foto = f"imagenes/{nombre_final}"
            else:
                flash("Formato de imagen no permitido. Usa JPG, PNG o WEBP.", "error")
                return render_template("perfil.html", usuario=usuario)

        actualizar_perfil_usuario(session["usuario_id"], nuevo_nombre, ruta_foto)

        # Actualizamos los datos en la sesión para que se reflejen al instante en el menú
        session["usuario_nombre"] = nuevo_nombre
        session["usuario_foto"] = ruta_foto

        flash("¡Perfil actualizado correctamente!", "exito")
        return redirect(url_for("mi_perfil"))

    return render_template("perfil.html", usuario=usuario)


@app.route("/perfil/quitar_foto", methods=["POST"])
def quitar_foto_perfil():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para modificar tu perfil.", "error")
        return redirect(url_for("login"))

    usuario = buscar_usuario_por_id(session["usuario_id"])
    if usuario:
        actualizar_perfil_usuario(usuario["id"], usuario["nombre"], "")
        session["usuario_foto"] = ""
        flash("Foto de perfil eliminada.", "exito")

    return redirect(url_for("mi_perfil"))


# ---------------- CONSULTAR CANCHAS Y RESERVAR (ETAPAS 3 Y 4) ----------------

@app.route("/canchas")
def ver_canchas():
    tipo_seleccionado = request.args.get("tipo", "").strip()
    if tipo_seleccionado not in TIPOS_FUTBOL:
        tipo_seleccionado = ""

    canchas = obtener_todas_las_canchas(tipo_seleccionado if tipo_seleccionado else None)
    return render_template(
        "canchas.html",
        canchas=canchas,
        tipos_futbol=TIPOS_FUTBOL,
        tipo_seleccionado=tipo_seleccionado
    )


@app.route("/cancha/<int:cancha_id>")
def detalle_cancha(cancha_id):
    cancha = obtener_cancha_por_id(cancha_id)
    if not cancha:
        flash("La cancha que buscas no existe.", "error")
        return redirect(url_for("ver_canchas"))

    fecha_hoy = date.today().isoformat()
    horarios_bd = obtener_horarios_de_cancha(cancha_id)
    confirmados = obtener_horarios_confirmados_de_cancha(cancha_id)

    # Preparamos solo horarios desde hoy en adelante, indicando si ya están ocupados
    horarios_vista = []
    fechas_disponibles = []
    horas_en_cancha = []

    for horario in horarios_bd:
        if horario["fecha"] < fecha_hoy:
            continue

        ocupado = (horario["fecha"], horario["hora"]) in confirmados
        horarios_vista.append({
            "fecha": horario["fecha"],
            "hora": horario["hora"],
            "ocupado": ocupado,
            "texto_estado": verificar_disponibilidad(ocupado)
        })

        if not ocupado:
            if horario["fecha"] not in fechas_disponibles:
                fechas_disponibles.append(horario["fecha"])
            if horario["hora"] not in horas_en_cancha:
                horas_en_cancha.append(horario["hora"])

    horas_en_cancha.sort()

    return render_template(
        "reservas.html",
        cancha=cancha,
        horarios=horarios_vista,
        fechas_disponibles=fechas_disponibles,
        horas_en_cancha=horas_en_cancha,
        fecha_hoy=fecha_hoy
    )


@app.route("/reservar", methods=["POST"])
def solicitar_reserva():
    # Regla: debe haber iniciado sesión para reservar
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para realizar una reserva.", "error")
        return redirect(url_for("login"))

    # Regla: las reservas las realizan los jugadores
    if session.get("tipo_usuario") != "jugador":
        flash("Solo los usuarios con perfil de jugador pueden solicitar reservas.", "error")
        return redirect(url_for("ver_canchas"))

    cancha_id = request.form.get("cancha_id", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()

    if not cancha_id.isdigit() or not fecha or not hora:
        flash("Por favor selecciona una fecha y una hora válidas.", "error")
        return redirect(url_for("ver_canchas"))

    cancha_id_num = int(cancha_id)
    cancha = obtener_cancha_por_id(cancha_id_num)
    if not cancha:
        flash("La cancha seleccionada no existe.", "error")
        return redirect(url_for("ver_canchas"))

    # Regla: no se pueden reservar fechas pasadas
    fecha_hoy = date.today().isoformat()
    if fecha < fecha_hoy:
        flash("No puedes reservar en una fecha pasada.", "error")
        return redirect(url_for("detalle_cancha", cancha_id=cancha_id_num))

    # Verificamos que la fecha y hora existan en los horarios ofrecidos por la cancha
    if not existe_horario(cancha_id_num, fecha, hora):
        flash("La fecha y hora elegidas no están disponibles en esta cancha.", "error")
        return redirect(url_for("detalle_cancha", cancha_id=cancha_id_num))

    # Regla: no permitir reservar un turno que ya fue confirmado
    if existe_reserva_confirmada(cancha_id_num, fecha, hora):
        flash("Ese horario ya está reservado y confirmado. Por favor elige otro.", "error")
        return redirect(url_for("detalle_cancha", cancha_id=cancha_id_num))

    # Evitar solicitudes duplicadas del mismo jugador para el mismo turno
    if usuario_tiene_reserva_activa(session["usuario_id"], cancha_id_num, fecha, hora):
        flash("Ya enviaste una solicitud de reserva para ese mismo día y hora.", "error")
        return redirect(url_for("detalle_cancha", cancha_id=cancha_id_num))

    crear_reserva(session["usuario_id"], cancha_id_num, fecha, hora)
    flash(
        f"¡Solicitud enviada! Reservaste {cancha['nombre']} para el {fecha} a las {hora}. "
        "El administrador la revisará pronto.",
        "exito"
    )
    return redirect(url_for("mis_reservas"))


@app.route("/mis_reservas")
def mis_reservas():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para ver tus reservas.", "error")
        return redirect(url_for("login"))

    if session.get("tipo_usuario") != "jugador":
        flash("Esta sección es para jugadores. Revisa tus solicitudes en el Panel Admin.", "error")
        return redirect(url_for("panel_administrador"))

    reservas = obtener_reservas_por_usuario(session["usuario_id"])
    return render_template("mis_reservas.html", reservas=reservas)


# ---------------- EQUIPOS (ETAPA 5) ----------------

@app.route("/equipos")
def ver_equipos():
    # Permite filtrar opcionalmente por categoría (Masculino, Femenino, Mixto)
    categoria_seleccionada = request.args.get("categoria", "").strip()
    if categoria_seleccionada not in CATEGORIAS_EQUIPO:
        categoria_seleccionada = ""

    equipos = obtener_todos_los_equipos(
        categoria_seleccionada if categoria_seleccionada else None
    )
    return render_template(
        "equipos.html",
        equipos=equipos,
        categorias=CATEGORIAS_EQUIPO,
        tipos_futbol=TIPOS_FUTBOL,
        categoria_seleccionada=categoria_seleccionada
    )


@app.route("/equipos/crear", methods=["POST"])
def registrar_equipo():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para crear un equipo.", "error")
        return redirect(url_for("login"))

    if session.get("tipo_usuario") != "jugador":
        flash("Solo los usuarios con perfil de jugador pueden crear equipos.", "error")
        return redirect(url_for("ver_equipos"))

    nombre = request.form.get("nombre", "").strip()
    categoria = request.form.get("categoria", "").strip()
    tipo_futbol = request.form.get("tipo_futbol", "").strip()
    descripcion = request.form.get("descripcion", "").strip()

    if not nombre or not descripcion:
        flash("Por favor escribe el nombre y una descripción para tu equipo.", "error")
        return redirect(url_for("ver_equipos"))

    if categoria not in CATEGORIAS_EQUIPO:
        flash("Categoría de equipo no válida.", "error")
        return redirect(url_for("ver_equipos"))

    if tipo_futbol not in TIPOS_FUTBOL:
        flash("Tipo de fútbol no válido.", "error")
        return redirect(url_for("ver_equipos"))

    if existe_equipo_por_nombre(nombre):
        flash("Ya existe un equipo con ese nombre. Elige otro nombre.", "error")
        return redirect(url_for("ver_equipos"))

    crear_equipo(nombre, categoria, tipo_futbol, session["usuario_id"], descripcion)
    flash(f"¡Equipo '{nombre}' creado con éxito!", "exito")
    return redirect(url_for("ver_equipos"))


# ---------------- BUSCAR RIVALES Y SOLICITUDES (ETAPA 6) ----------------

@app.route("/rivales")
def buscar_rivales():
    tipo_seleccionado = request.args.get("tipo", "").strip()
    categoria_seleccionada = request.args.get("categoria", "").strip()

    if tipo_seleccionado not in TIPOS_FUTBOL:
        tipo_seleccionado = ""
    if categoria_seleccionada not in CATEGORIAS_EQUIPO:
        categoria_seleccionada = ""

    partidos_bd = obtener_todos_los_partidos(
        tipo_seleccionado if tipo_seleccionado else None,
        categoria_seleccionada if categoria_seleccionada else None
    )

    # Agregamos a cada publicación próxima (desde hoy en adelante) si ya tiene rival aceptado
    fecha_hoy = date.today().isoformat()
    partidos_vista = []
    for partido in partidos_bd:
        if partido["fecha"] < fecha_hoy:
            continue
        partidos_vista.append({
            "partido": partido,
            "rival_aceptado": obtener_rival_aceptado(partido["id"])
        })

    mis_equipos = []
    solicitudes_recibidas = []
    solicitudes_enviadas = []

    if session.get("usuario_id") and session.get("tipo_usuario") == "jugador":
        mis_equipos = obtener_equipos_por_capitan(session["usuario_id"])
        solicitudes_recibidas = obtener_solicitudes_recibidas(session["usuario_id"])
        solicitudes_enviadas = obtener_solicitudes_enviadas(session["usuario_id"])

    return render_template(
        "rivales.html",
        partidos_vista=partidos_vista,
        mis_equipos=mis_equipos,
        solicitudes_recibidas=solicitudes_recibidas,
        solicitudes_enviadas=solicitudes_enviadas,
        tipos_futbol=TIPOS_FUTBOL,
        categorias=CATEGORIAS_EQUIPO,
        horas_disponibles=HORAS_DISPONIBLES,
        tipo_seleccionado=tipo_seleccionado,
        categoria_seleccionada=categoria_seleccionada,
        fecha_hoy=fecha_hoy
    )


@app.route("/rivales/publicar", methods=["POST"])
def publicar_partido():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para publicar que buscas rival.", "error")
        return redirect(url_for("login"))

    if session.get("tipo_usuario") != "jugador":
        flash("Solo los jugadores pueden publicar partidos para buscar rival.", "error")
        return redirect(url_for("buscar_rivales"))

    equipo_id = request.form.get("equipo_id", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    lugar = request.form.get("lugar", "").strip()
    descripcion = request.form.get("descripcion", "").strip()

    if not equipo_id.isdigit() or not fecha or hora not in HORAS_DISPONIBLES or not lugar or not descripcion:
        flash("Por favor completa todos los campos de la publicación.", "error")
        return redirect(url_for("buscar_rivales"))

    fecha_hoy = date.today().isoformat()
    if fecha < fecha_hoy:
        flash("No puedes publicar un partido en una fecha pasada.", "error")
        return redirect(url_for("buscar_rivales"))

    # Verificamos que el equipo pertenezca al capitán conectado
    equipo = obtener_equipo_por_id(int(equipo_id))
    if not equipo or equipo["capitan_id"] != session["usuario_id"]:
        flash("Solo puedes publicar partidos con tus propios equipos.", "error")
        return redirect(url_for("buscar_rivales"))

    crear_partido(int(equipo_id), fecha, hora, lugar, descripcion)
    flash(f"¡Publicación creada! {equipo['nombre']} ya está buscando rival.", "exito")
    return redirect(url_for("buscar_rivales"))


@app.route("/rivales/solicitar/<int:partido_id>", methods=["POST"])
def enviar_solicitud_rival(partido_id):
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para enviar una solicitud de partido.", "error")
        return redirect(url_for("login"))

    if session.get("tipo_usuario") != "jugador":
        flash("Solo los jugadores pueden retar a otros equipos.", "error")
        return redirect(url_for("buscar_rivales"))

    equipo_id = request.form.get("equipo_id", "").strip()
    if not equipo_id.isdigit():
        flash("Debes seleccionar uno de tus equipos para enviar la solicitud.", "error")
        return redirect(url_for("buscar_rivales"))

    equipo = obtener_equipo_por_id(int(equipo_id))
    if not equipo or equipo["capitan_id"] != session["usuario_id"]:
        flash("El equipo seleccionado no te pertenece.", "error")
        return redirect(url_for("buscar_rivales"))

    partido = obtener_partido_por_id(partido_id)
    if not partido:
        flash("La publicación seleccionada no existe.", "error")
        return redirect(url_for("buscar_rivales"))

    if partido["capitan_id"] == session["usuario_id"]:
        flash("No puedes enviarte una solicitud a tu propia publicación.", "error")
        return redirect(url_for("buscar_rivales"))

    if obtener_rival_aceptado(partido_id):
        flash("Este partido ya tiene un rival confirmado.", "error")
        return redirect(url_for("buscar_rivales"))

    if existe_solicitud(partido_id, int(equipo_id)):
        flash("Ya enviaste una solicitud con ese equipo para este partido.", "error")
        return redirect(url_for("buscar_rivales"))

    crear_solicitud(partido_id, int(equipo_id))
    flash(
        f"¡Solicitud enviada! Retaste a {partido['nombre_equipo']} con tu equipo {equipo['nombre']}.",
        "exito"
    )
    return redirect(url_for("buscar_rivales"))


@app.route("/rivales/solicitud/<int:solicitud_id>", methods=["POST"])
def responder_solicitud_rival(solicitud_id):
    if "usuario_id" not in session or session.get("tipo_usuario") != "jugador":
        flash("Debes iniciar sesión como jugador para responder solicitudes.", "error")
        return redirect(url_for("login"))

    accion = request.form.get("accion", "").strip()
    if accion not in ("aceptar", "rechazar"):
        flash("Acción no válida.", "error")
        return redirect(url_for("buscar_rivales"))

    solicitud = obtener_solicitud_por_id(solicitud_id)
    if not solicitud or solicitud["capitan_publicador_id"] != session["usuario_id"]:
        flash("No puedes responder una solicitud que no pertenece a tu publicación.", "error")
        return redirect(url_for("buscar_rivales"))

    if solicitud["estado"] != "pendiente":
        flash("Esta solicitud ya fue respondida anteriormente.", "error")
        return redirect(url_for("buscar_rivales"))

    if accion == "aceptar":
        if obtener_rival_aceptado(solicitud["partido_id"]):
            flash("Ya aceptaste otro equipo rival para este partido.", "error")
            return redirect(url_for("buscar_rivales"))

        actualizar_estado_solicitud(solicitud_id, "aceptada")
        flash(
            f"¡Partido acordado! Aceptaste la solicitud de {solicitud['nombre_retador']}.",
            "exito"
        )
    else:
        actualizar_estado_solicitud(solicitud_id, "rechazada")
        flash("Solicitud rechazada correctamente.", "exito")

    return redirect(url_for("buscar_rivales"))


# ---------------- PANEL DE ADMINISTRADOR, CANCHAS Y RESERVAS ----------------

@app.route("/administrador")
def panel_administrador():
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para acceder a esta página.", "error")
        return redirect(url_for("login"))

    if session.get("tipo_usuario") != "administrador":
        flash("Acceso denegado: esta sección es solo para administradores de canchas.", "error")
        return redirect(url_for("inicio"))

    mis_canchas = obtener_canchas_por_administrador(session["usuario_id"])

    canchas_con_horarios = []
    for cancha in mis_canchas:
        horarios = obtener_horarios_de_cancha(cancha["id"])
        canchas_con_horarios.append({
            "cancha": cancha,
            "horarios": horarios
        })

    reservas_recibidas = obtener_reservas_por_administrador(session["usuario_id"])
    fecha_hoy = date.today().isoformat()

    return render_template(
        "administrador.html",
        canchas_con_horarios=canchas_con_horarios,
        reservas_recibidas=reservas_recibidas,
        horas_disponibles=HORAS_DISPONIBLES,
        tipos_futbol=TIPOS_FUTBOL,
        fecha_hoy=fecha_hoy
    )


@app.route("/administrador/agregar_cancha", methods=["POST"])
def agregar_cancha():
    if "usuario_id" not in session or session.get("tipo_usuario") != "administrador":
        flash("Solo los administradores pueden registrar canchas.", "error")
        return redirect(url_for("inicio"))

    nombre = request.form.get("nombre", "").strip()
    direccion = request.form.get("direccion", "").strip()
    precio_texto = request.form.get("precio", "").strip()
    tipo_futbol = request.form.get("tipo_futbol", "").strip()
    imagen_predeterminada = request.form.get("imagen_predeterminada", "imagenes/cancha1.jpg")

    if not nombre or not direccion or not precio_texto or tipo_futbol not in TIPOS_FUTBOL:
        flash("Por favor completa correctamente todos los datos de la cancha.", "error")
        return redirect(url_for("panel_administrador"))

    if not precio_texto.isdigit() or int(precio_texto) <= 0:
        flash("El precio por hora debe ser un número mayor que cero (sin puntos ni comas).", "error")
        return redirect(url_for("panel_administrador"))

    precio = int(precio_texto)

    ruta_imagen = "imagenes/cancha1.jpg"
    if imagen_predeterminada in ("imagenes/cancha1.jpg", "imagenes/cancha2.jpg"):
        ruta_imagen = imagen_predeterminada

    archivo = request.files.get("foto")
    if archivo and archivo.filename:
        if archivo_imagen_valido(archivo.filename):
            nombre_seguro = secure_filename(archivo.filename)
            nombre_final = f"cancha_{session['usuario_id']}_{int(time.time())}_{nombre_seguro}"
            os.makedirs(CARPETA_IMAGENES, exist_ok=True)
            archivo.save(os.path.join(CARPETA_IMAGENES, nombre_final))
            ruta_imagen = f"imagenes/{nombre_final}"
        else:
            flash("Formato de imagen no permitido. Usa JPG, PNG o WEBP.", "error")
            return redirect(url_for("panel_administrador"))

    crear_cancha(nombre, direccion, precio, tipo_futbol, ruta_imagen, session["usuario_id"])
    flash(f"¡Cancha '{nombre}' registrada con éxito!", "exito")
    return redirect(url_for("panel_administrador"))


@app.route("/administrador/agregar_horario", methods=["POST"])
def agregar_horario_cancha():
    if "usuario_id" not in session or session.get("tipo_usuario") != "administrador":
        flash("Solo los administradores pueden agregar horarios.", "error")
        return redirect(url_for("inicio"))

    cancha_id = request.form.get("cancha_id", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()

    if not cancha_id.isdigit() or not fecha or hora not in HORAS_DISPONIBLES:
        flash("Por favor selecciona una fecha y hora válidas.", "error")
        return redirect(url_for("panel_administrador"))

    fecha_hoy = date.today().isoformat()
    if fecha < fecha_hoy:
        flash("No puedes agregar horarios en fechas pasadas.", "error")
        return redirect(url_for("panel_administrador"))

    cancha = obtener_cancha_por_id(int(cancha_id))
    if not cancha or cancha["administrador_id"] != session["usuario_id"]:
        flash("No puedes modificar los horarios de una cancha que no te pertenece.", "error")
        return redirect(url_for("panel_administrador"))

    creado = agregar_horario(int(cancha_id), fecha, hora)
    if creado:
        flash(f"Horario agregado: {fecha} a las {hora} en {cancha['nombre']}.", "exito")
    else:
        flash("Ese horario ya estaba registrado para esta cancha.", "error")

    return redirect(url_for("panel_administrador"))


@app.route("/administrador/eliminar_horario/<int:horario_id>", methods=["POST"])
def eliminar_horario_cancha(horario_id):
    if "usuario_id" not in session or session.get("tipo_usuario") != "administrador":
        flash("Solo los administradores pueden eliminar horarios.", "error")
        return redirect(url_for("inicio"))

    eliminado = eliminar_horario(horario_id, session["usuario_id"])
    if eliminado:
        flash("Horario eliminado correctamente.", "exito")
    else:
        flash("No se pudo eliminar ese horario.", "error")

    return redirect(url_for("panel_administrador"))


@app.route("/administrador/reserva/<int:reserva_id>", methods=["POST"])
def gestionar_reserva(reserva_id):
    if "usuario_id" not in session or session.get("tipo_usuario") != "administrador":
        flash("Solo los administradores pueden gestionar reservas.", "error")
        return redirect(url_for("inicio"))

    accion = request.form.get("accion", "").strip()
    if accion not in ("confirmar", "rechazar"):
        flash("Acción no válida.", "error")
        return redirect(url_for("panel_administrador"))

    reserva = obtener_reserva_por_id(reserva_id)

    # Regla de seguridad: solo puede gestionar reservas de sus propias canchas
    if not reserva or reserva["administrador_id"] != session["usuario_id"]:
        flash("No puedes modificar reservas de una cancha que no te pertenece.", "error")
        return redirect(url_for("panel_administrador"))

    if reserva["estado"] != "pendiente":
        flash("Esta reserva ya fue respondida anteriormente.", "error")
        return redirect(url_for("panel_administrador"))

    if accion == "confirmar":
        # Regla clave: no confirmar dos reservas para la misma cancha, fecha y horario
        if existe_reserva_confirmada(reserva["cancha_id"], reserva["fecha"], reserva["hora"]):
            flash(
                "No se puede confirmar: ya existe una reserva confirmada para esa misma cancha, fecha y hora.",
                "error"
            )
            return redirect(url_for("panel_administrador"))

        actualizar_estado_reserva(reserva_id, "confirmada")
        flash(
            f"Reserva confirmada para {reserva['nombre_cancha']} ({reserva['fecha']} a las {reserva['hora']}).",
            "exito"
        )
    else:
        actualizar_estado_reserva(reserva_id, "rechazada")
        flash("Reserva rechazada correctamente.", "exito")

    return redirect(url_for("panel_administrador"))


# ---------------- MANEJO DE PÁGINAS NO ENCONTRADAS (404) ----------------

@app.errorhandler(404)
def pagina_no_encontrada(error):
    flash("La página que buscas no existe.", "error")
    return redirect(url_for("inicio"))


if __name__ == "__main__":
    app.run(debug=True)
