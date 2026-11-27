"""Envío de correo de recuperación de contraseña para Ready Match."""

from email.message import EmailMessage
import os
import smtplib

from config import cargar_archivo_env


def enviar_correo_recuperacion(destinatario, codigo):
    """Envía el código temporal de recuperación vía Gmail SMTP leyendo .env."""
    cargar_archivo_env()

    correo_remitente = os.environ.get("CORREO_APP", "").strip()
    clave_aplicacion = os.environ.get("CLAVE_CORREO_APP", "").replace(" ", "").strip()

    if not correo_remitente or not clave_aplicacion:
        print(f"[Ready Match - Gmail sin configurar] Código de recuperación para {destinatario}: {codigo}")
        return False

    mensaje = EmailMessage()
    mensaje["Subject"] = "Código de recuperación de contraseña - Ready Match"
    mensaje["From"] = f"Ready Match <{correo_remitente}>"
    mensaje["To"] = destinatario
    mensaje.set_content(
        f"Hola,\n\n"
        f"Recibimos una solicitud para cambiar tu contraseña en Ready Match.\n"
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
        print(f"[Ready Match - Error SMTP] No se pudo enviar el correo: {error}")
        return False
