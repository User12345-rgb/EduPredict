import os
from datetime import datetime, date
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint, CheckConstraint

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "CAMBIA-ESTA-CLAVE-ANTES-DE-PUBLICAR")
database_url = os.getenv("DATABASE_URL", "").strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
if database_url and database_url.startswith("postgresql://") and "+psycopg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///edupredict_local.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "false").lower() == "true"

db = SQLAlchemy(app)
csrf = CSRFProtect(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(15), nullable=False, default="alumno")
    approved = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Offering(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_name = db.Column(db.String(100), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    group_name = db.Column(db.String(40), nullable=False, default="General")
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    teacher = db.relationship("User")
    criteria = db.relationship("Criterion", cascade="all, delete-orphan", order_by="Criterion.id")
    __table_args__ = (CheckConstraint("semester >= 1 AND semester <= 6"),)


class Criterion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offering_id = db.Column(db.Integer, db.ForeignKey("offering.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    weight = db.Column(db.Float, nullable=False)


class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    offering_id = db.Column(db.Integer, db.ForeignKey("offering.id"), nullable=False)
    student = db.relationship("User")
    offering = db.relationship("Offering")
    __table_args__ = (UniqueConstraint("student_id", "offering_id", name="uq_student_offering"),)


class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("enrollment.id"), nullable=False)
    criterion_id = db.Column(db.Integer, db.ForeignKey("criterion.id"), nullable=False)
    value = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    enrollment = db.relationship("Enrollment")
    criterion = db.relationship("Criterion")
    __table_args__ = (
        UniqueConstraint("enrollment_id", "criterion_id", name="uq_enrollment_criterion"),
        CheckConstraint("value >= 0 AND value <= 10"),
    )


class GradeHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    grade_id = db.Column(db.Integer, nullable=False)
    student_id = db.Column(db.Integer, nullable=False)
    criterion_name = db.Column(db.String(80), nullable=False)
    old_value = db.Column(db.Float)
    new_value = db.Column(db.Float, nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)


class StudyNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    offering_id = db.Column(db.Integer, db.ForeignKey("offering.id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    done = db.Column(db.Boolean, default=False, nullable=False)
    student = db.relationship("User")
    offering = db.relationship("Offering")


class ProblemReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    username = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(40), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pendiente")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship("User")


# Crea únicamente tablas que no existan; no elimina ni reinicia datos.
with app.app_context():
    db.create_all()


def split_criterion(criterion):
    if "|||" in criterion.name:
        rubric, name = criterion.name.split("|||", 1)
        return rubric, name
    return "Rúbrica general", criterion.name


def group_criteria(criteria):
    groups = []
    for criterion in criteria:
        rubric, name = split_criterion(criterion)
        if not groups or groups[-1]["name"] != rubric:
            groups.append({"name": rubric, "criteria": []})
        groups[-1]["criteria"].append(criterion)
    return groups


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if user.role not in roles:
                flash("No tienes permiso para entrar a esa sección.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def weighted_result(enrollment):
    total_weight = sum(c.weight for c in enrollment.offering.criteria)
    entered = {g.criterion_id: g.value for g in Grade.query.filter_by(enrollment_id=enrollment.id).all()}
    earned = sum(c.weight * entered[c.id] / 100 for c in enrollment.offering.criteria if c.id in entered)
    completed_weight = sum(c.weight for c in enrollment.offering.criteria if c.id in entered)
    current = (earned / completed_weight * 100) if completed_weight else None
    projected = earned + sum(c.weight * 7 / 100 for c in enrollment.offering.criteria if c.id not in entered)
    final = earned if completed_weight >= total_weight - 0.001 else None
    return {
        "earned": earned, "completed_weight": completed_weight, "total_weight": total_weight,
        "current": current, "projected": projected, "final": final,
        "entered": entered
    }


@app.context_processor
def inject_globals():
    return {"me": current_user(), "year": date.today().year}


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/registro", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        display = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "alumno")
        if not username or not display or len(password) < 8:
            flash("Completa todos los campos. La contraseña debe tener al menos 8 caracteres.", "error")
        elif role not in ("alumno", "docente"):
            flash("Tipo de cuenta no válido.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Ese identificador ya está registrado.", "error")
        else:
            user = User(username=username, display_name=display,
                        password_hash=generate_password_hash(password),
                        role=role, approved=(role == "alumno"))
            db.session.add(user)
            db.session.commit()
            if role == "docente":
                flash("Solicitud registrada. Un administrador debe autorizar la cuenta antes de iniciar sesión.", "success")
            else:
                flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.approved:
                flash("Tu cuenta de docente está pendiente de autorización.", "error")
            else:
                session.clear()
                session["user_id"] = user.id
                return redirect(url_for("dashboard"))
        else:
            flash("Identificador o contraseña incorrectos.", "error")
    return render_template("login.html")


@app.route("/salir")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/panel")
@login_required
def dashboard():
    user = current_user()
    if user.role == "admin":
        pending = User.query.filter_by(role="docente", approved=False).order_by(User.created_at).all()
        reports = ProblemReport.query.order_by(ProblemReport.created_at.desc()).all()
        return render_template("admin.html", pending=pending, reports=reports)
    if user.role == "docente":
        offerings = Offering.query.filter_by(teacher_id=user.id).order_by(Offering.semester, Offering.subject_name).all()
        return render_template("teacher.html", offerings=offerings)
    enrollments = Enrollment.query.filter_by(student_id=user.id).all()
    rows = []
    for e in enrollments:
        rows.append((e, weighted_result(e)))
    available = Offering.query.order_by(Offering.semester, Offering.subject_name).all()
    notes = StudyNote.query.filter_by(student_id=user.id).order_by(StudyNote.due_date).all()
    return render_template("student.html", rows=rows, available=available, notes=notes)


@app.route("/admin/aprobar/<int:user_id>", methods=["POST"])
@role_required("admin")
def approve_teacher(user_id):
    user = db.session.get(User, user_id)
    if user and user.role == "docente":
        user.approved = True
        db.session.commit()
        flash("Cuenta de docente autorizada.", "success")
    return redirect(url_for("dashboard"))


@app.route("/docente/oferta", methods=["GET", "POST"])
@role_required("docente")
def create_offering():
    if request.method == "POST":
        name = request.form.get("subject_name", "").strip()
        semester = request.form.get("semester", type=int)
        group = request.form.get("group_name", "").strip() or "General"
        rubric_titles = request.form.getlist("rubric_title")
        names = request.form.getlist("criterion_name")
        weights_raw = request.form.getlist("weight")
        indexes = request.form.getlist("criterion_rubric_index")
        try:
            weights = [float(x) for x in weights_raw]
            indexes = [int(x) for x in indexes]
        except ValueError:
            weights, indexes = [], []
        valid_rows = len(names) == len(weights) == len(indexes) and len(names) > 0
        try:
            total = sum(weights)
        except TypeError:
            total = 0
        if not name or semester not in range(1, 7) or not rubric_titles or not valid_rows:
            flash("Revisa el nombre, semestre y las rúbricas.", "error")
        elif any(not t.strip() or len(t.strip()) > 35 for t in rubric_titles) or any(i < 0 or i >= len(rubric_titles) for i in indexes) or any(not n.strip() or len(n.strip()) > 40 for n in names) or any(w <= 0 for w in weights) or abs(total - 100) > 0.01:
            flash("Cada criterio debe tener nombre y porcentaje positivo; todos los porcentajes deben sumar 100%.", "error")
        else:
            offering = Offering(subject_name=name, semester=semester, group_name=group, teacher_id=current_user().id)
            for rubric_index, criterion_name, weight in zip(indexes, names, weights):
                rubric = rubric_titles[rubric_index].strip()
                offering.criteria.append(Criterion(name=f"{rubric}|||{criterion_name.strip()}", weight=weight))
            db.session.add(offering)
            db.session.commit()
            flash("Materia y rúbricas guardadas.", "success")
            return redirect(url_for("dashboard"))
    return render_template("offering_form.html", offering=None, rubric_groups=[])


@app.route("/docente/oferta/<int:offering_id>/editar", methods=["GET", "POST"])
@role_required("docente")
def edit_offering(offering_id):
    offering = db.session.get(Offering, offering_id)
    if not offering or offering.teacher_id != current_user().id:
        flash("No tienes permiso para modificar esa materia.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("subject_name", "").strip()
        semester = request.form.get("semester", type=int)
        group = request.form.get("group_name", "").strip() or "General"
        rubric_titles = request.form.getlist("rubric_title")
        names = request.form.getlist("criterion_name")
        weights_raw = request.form.getlist("weight")
        indexes_raw = request.form.getlist("criterion_rubric_index")
        ids_raw = request.form.getlist("criterion_id")
        try:
            weights = [float(x) for x in weights_raw]
            indexes = [int(x) for x in indexes_raw]
            ids = [int(x) if x else None for x in ids_raw]
        except ValueError:
            weights, indexes, ids = [], [], []
        valid_rows = len(names) == len(weights) == len(indexes) == len(ids) and len(names) > 0
        if not name or semester not in range(1, 7) or not rubric_titles or not valid_rows:
            flash("Revisa el nombre, semestre y las rúbricas.", "error")
        elif any(not t.strip() or len(t.strip()) > 35 for t in rubric_titles) or any(i < 0 or i >= len(rubric_titles) for i in indexes) or any(not n.strip() or len(n.strip()) > 40 for n in names) or any(w <= 0 for w in weights) or abs(sum(weights) - 100) > 0.01 or set(indexes) != set(range(len(rubric_titles))):
            flash("Los criterios deben tener nombre, porcentajes positivos y sumar 100%.", "error")
        else:
            existing = {c.id: c for c in offering.criteria}
            submitted_ids = {cid for cid in ids if cid is not None}
            invalid_ids = submitted_ids - set(existing)
            if invalid_ids:
                flash("Se detectó un criterio que no pertenece a esta materia.", "error")
            else:
                # No se permite quitar criterios que ya tengan calificaciones capturadas.
                protected = []
                for cid in set(existing) - submitted_ids:
                    if Grade.query.filter_by(criterion_id=cid).first():
                        protected.append(cid)
                if protected:
                    flash("No puedes quitar criterios que ya tienen calificaciones registradas. Puedes cambiar su nombre o porcentaje.", "error")
                else:
                    offering.subject_name = name
                    offering.semester = semester
                    offering.group_name = group
                    for cid in set(existing) - submitted_ids:
                        db.session.delete(existing[cid])
                    for rubric_index, criterion_name, weight, cid in zip(indexes, names, weights, ids):
                        rubric = rubric_titles[rubric_index].strip()
                        stored_name = f"{rubric}|||{criterion_name.strip()}"
                        if cid:
                            existing[cid].name = stored_name
                            existing[cid].weight = weight
                        else:
                            offering.criteria.append(Criterion(name=stored_name, weight=weight))
                    db.session.commit()
                    flash("Materia y rúbricas actualizadas.", "success")
                    return redirect(url_for("dashboard"))
    return render_template("offering_form.html", offering=offering, rubric_groups=group_criteria(offering.criteria))


@app.route("/alumno/inscribir/<int:offering_id>", methods=["POST"])
@role_required("alumno")
def enroll(offering_id):
    offering = db.session.get(Offering, offering_id)
    if not offering:
        flash("No se encontró esa materia.", "error")
    elif Enrollment.query.filter_by(student_id=current_user().id, offering_id=offering_id).first():
        flash("Ya estás inscrito en esa materia.", "error")
    else:
        db.session.add(Enrollment(student_id=current_user().id, offering_id=offering_id))
        db.session.commit()
        flash("Materia agregada a tu panel.", "success")
    return redirect(url_for("dashboard"))


@app.route("/alumno/calificaciones/<int:enrollment_id>", methods=["GET", "POST"])
@role_required("alumno")
def grades(enrollment_id):
    enrollment = db.session.get(Enrollment, enrollment_id)
    if not enrollment or enrollment.student_id != current_user().id:
        flash("No se encontró esa materia en tu cuenta.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        for criterion in enrollment.offering.criteria:
            raw = request.form.get(f"grade_{criterion.id}", "").strip()
            if raw == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                flash("Las calificaciones deben ser números.", "error")
                return redirect(url_for("grades", enrollment_id=enrollment.id))
            if value < 0 or value > 10:
                flash("Las calificaciones deben estar entre 0 y 10.", "error")
                return redirect(url_for("grades", enrollment_id=enrollment.id))
            grade = Grade.query.filter_by(enrollment_id=enrollment.id, criterion_id=criterion.id).first()
            old = grade.value if grade else None
            if grade:
                grade.value = value
            else:
                grade = Grade(enrollment_id=enrollment.id, criterion_id=criterion.id, value=value)
                db.session.add(grade)
                db.session.flush()
            db.session.add(GradeHistory(grade_id=grade.id, student_id=current_user().id,
                                        criterion_name=criterion.name, old_value=old, new_value=value))
        db.session.commit()
        flash("Calificaciones guardadas.", "success")
        return redirect(url_for("grades", enrollment_id=enrollment.id))
    result = weighted_result(enrollment)
    return render_template("grades.html", enrollment=enrollment, result=result, rubric_groups=group_criteria(enrollment.offering.criteria))


@app.route("/alumno/historial")
@role_required("alumno")
def history():
    entries = GradeHistory.query.filter_by(student_id=current_user().id).order_by(GradeHistory.changed_at.desc()).limit(100).all()
    return render_template("history.html", entries=entries)


@app.route("/alumno/nota", methods=["POST"])
@role_required("alumno")
def add_note():
    offering_id = request.form.get("offering_id", type=int)
    title = request.form.get("title", "").strip()
    due = request.form.get("due_date", "").strip()
    enrollment = Enrollment.query.filter_by(student_id=current_user().id, offering_id=offering_id).first()
    if not enrollment or not title:
        flash("Selecciona una materia inscrita y escribe una actividad.", "error")
    else:
        due_date = date.fromisoformat(due) if due else None
        db.session.add(StudyNote(student_id=current_user().id, offering_id=offering_id, title=title, due_date=due_date))
        db.session.commit()
        flash("Actividad agregada a tu plan.", "success")
    return redirect(url_for("dashboard"))


@app.route("/alumno/nota/<int:note_id>/completar", methods=["POST"])
@role_required("alumno")
def complete_note(note_id):
    note = db.session.get(StudyNote, note_id)
    if note and note.student_id == current_user().id:
        note.done = not note.done
        db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/reportar-problema", methods=["GET", "POST"])
def report_problem():
    if request.method == "POST":
        category = request.form.get("category", "Otro").strip()
        message = request.form.get("message", "").strip()
        allowed = {"Error técnico", "Problema con calificaciones", "Problema de cuenta", "Sugerencia", "Otro"}
        user = current_user()
        if category not in allowed or len(message) < 10 or len(message) > 2000:
            flash("Elige una categoría y describe el problema con al menos 10 caracteres (máximo 2000).", "error")
        else:
            report = ProblemReport(
                user_id=user.id if user else None,
                username=user.display_name if user else "Usuario sin sesión",
                category=category,
                message=message
            )
            db.session.add(report)
            db.session.commit()
            flash("Tu reporte fue enviado al administrador. Gracias por avisarnos.", "success")
            return redirect(url_for("report_problem"))
    return render_template("report_problem.html")


@app.route("/admin/reporte/<int:report_id>/resolver", methods=["POST"])
@role_required("admin")
def resolve_report(report_id):
    report = db.session.get(ProblemReport, report_id)
    if report:
        report.status = "Revisado" if report.status == "Pendiente" else "Pendiente"
        db.session.commit()
        flash("Estado del reporte actualizado.", "success")
    return redirect(url_for("dashboard"))


@app.route("/salud")
def health():
    return {"status": "ok"}


@app.cli.command("init-db")
def init_db():
    """Crea las tablas y, opcionalmente, el administrador inicial desde variables de entorno."""
    db.create_all()
    admin_user = os.getenv("ADMIN_USERNAME", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_user and admin_password and not User.query.filter_by(username=admin_user).first():
        db.session.add(User(username=admin_user, display_name="Administrador",
                            password_hash=generate_password_hash(admin_password),
                            role="admin", approved=True))
        db.session.commit()
    print("Base de datos preparada.")


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", message="La página que buscas no existe."), 404


@app.errorhandler(500)
def server_error(_):
    db.session.rollback()
    return render_template("error.html", message="Ocurrió un error interno. Revisa la terminal para ver el detalle."), 500


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
