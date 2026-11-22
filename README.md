# EduPredict

Sistema de seguimiento personal del rendimiento académico.

## Requisitos
Python 3.11 o superior y una base PostgreSQL (Neon funciona).

## Instalación local
1. Abre la carpeta en VS Code.
2. Crea un entorno: `py -m venv .venv`
3. Actívalo en PowerShell: `.venv\Scripts\Activate.ps1`
4. Instala: `pip install -r requirements.txt`
5. Copia `.env.example` a `.env` y completa las variables.
6. Inicializa tablas y administrador: `flask --app app init-db`
7. Ejecuta: `flask --app app run`
8. Abre `http://127.0.0.1:5000`

No compartas el archivo `.env`. Las calificaciones son para seguimiento personal y no son calificaciones oficiales.


## EduPredict AI (opcional)
La aplicación incluye un asistente conversacional para alumnos. Para activarlo:
1. Crea una clave de Gemini API desde Google AI Studio, si cumples sus requisitos de edad y uso. Si no, pide a tu madre, padre o tutor que revise y gestione esta configuración contigo.
2. En Render, abre el servicio de EduPredict y entra a **Environment**.
3. Agrega la variable `GEMINI_API_KEY` con la clave. No la pegues en el código ni la subas a GitHub.
4. Guarda los cambios y vuelve a desplegar.

El módulo usa `gemini-3.5-flash-lite`, cuyo nivel gratuito tiene límites que pueden cambiar. El chat no guarda el historial en la base de datos y no consulta las calificaciones del alumno. Los mensajes escritos se envían a Google para generar respuestas; en el nivel gratuito, Google indica que puede usar el contenido para mejorar sus productos. No introduzcas datos personales, contraseñas ni información privada. Consulta los términos y condiciones vigentes del proveedor antes de activarlo.
