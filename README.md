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


## EduPredict AI
El asistente académico utiliza WebLLM para ejecutar un modelo de lenguaje directamente en el navegador del alumno.
No necesita una clave API ni agrega costos por consulta al servidor. La primera carga descarga el modelo
(aproximadamente 900 MB) y requiere internet; después el navegador puede reutilizar la descarga guardada.
Se necesita un navegador y un dispositivo compatibles con WebGPU. El rendimiento depende del equipo.
Las conversaciones se mantienen temporalmente en la página y no se guardan en la base de datos.
Las respuestas pueden contener errores y deben verificarse con los materiales de clase.
