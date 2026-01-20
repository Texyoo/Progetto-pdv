from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import datetime, timedelta, date
import pandas as pd
import os
import json
from collections import defaultdict

# =====================================================
#  RUOLI DI SISTEMA
# =====================================================

ROLE_ADMIN = "ADMIN"
ROLE_SPONSOR = "SPONSOR"
ROLE_USER = "USER"
ROLE_AREA_MANAGER = "AREA_MANAGER"

# =====================================================
#  CONFIGURAZIONE BASE APP
# =====================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = "cambia_questa_chiave_in_produzione"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

GANTT_FILE = os.path.join(BASE_DIR, "Gantt modificato.xlsx")
STATE_FILE = os.path.join(BASE_DIR, "project_state.json")

DB_DIR = os.path.join(BASE_DIR, "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "users.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

SELF_REGISTRATION_ENABLED = True

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(50), default="USER")
    function_name = db.Column(db.String(120), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_sponsor(self) -> bool:
        return self.role == ROLE_SPONSOR


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class ProjectState(db.Model):
    __tablename__ = "project_state"

    id = db.Column(db.Integer, primary_key=True)
    data_json = db.Column(
        db.Text,
        nullable=False,
        default='{"project_start": null, "started": [], "completed": []}'
    )
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def ensure_initial_admin():
    email_admin = "Alessandro.camera95@gmail.com"

    existing = User.query.filter_by(email=email_admin).first()
    if existing:
        print("Admin iniziale già presente.")
        return

    admin = User(
        full_name="Alessandro Camera",
        email=email_admin,
        role=ROLE_ADMIN,
        function_name=None,
    )
    admin.set_password("Admin123!")
    db.session.add(admin)
    db.session.commit()
    print("Admin iniziale creato.")
with app.app_context():
    db.create_all()
    ensure_initial_admin()


# =====================================================
#  ROUTES: AUTENTICAZIONE
# =====================================================

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Accesso eseguito correttamente.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Credenziali non valide.", "danger")

    return render_template(
        "login.html",
        self_registration_enabled=SELF_REGISTRATION_ENABLED
    )


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sei stato disconnesso.", "info")
    return redirect(url_for("login"))






# =====================================================
#  FUNZIONI AZIENDALI (per il Gantt)
# =====================================================

FUNZIONI_AZIENDALI = [
    "SPONSOR",
    "DIREZIONE VENDITE",
    "UFFICIO PERSONALE",
    "AMMINISTRAZIONE  TESORERIA",
    "UFFICIO I.T.",
    "MERCHANDISING-ACQUISTI-VENDITE",
    "MERCHANDISING",
    "ASSISTENTE DIREZIONE-VENDITE",
    "RESPONSABILE SICUREZZA LOGISTICA",
    "VENDITA",
    "UFFICIO ACQUISTI",
    "UFFICIO ACQUISTI-MERCHANDISING-CO.GE.",
    "VENDITA - MERCHANDISING",
    "FORNITORI-MERCHANDISING",
    "RESPONSABILE SICUREZZA LOGISTICA-MERCHANDISING",
    "RESP.SICUREZZA LOGISTICA-U.T.",
    "Responsabile sicurezza logistica-fornitore G4",
    "MARKETING-VENDITE",
    "MARKETING",
    "RESPONSABILE SICUREZZA-LOGISTICA",
    "RESPONSABILE SICUREZZA -LOGISTICA",
    "UFFICIO ACQUISTI VENDITE",
    "VENDITA - MARKETING",
    "RESP. SICUREZZA LOGISTICA - FORNITORE G4",
    "UFFICIO TECNICO- VENDITA",
    "RESP. SICUREZZA LOGISTICA -VENDITE",
    "VENDITE-AF.GENERALI-MARKETING",
    "VENDITA-U.T.",
    "UFFICIO TECNICO",
    "FORNITORE-MERCHANDISING",
    "AMMINISTRAZIONE-TESORERIA-FORNITOREG4",
    "RESPONSABILE SICUREZZA CHECK POINT",
    "RESP.SICUREZZA LOGISTICA FORNITORE MORE ONE",
    "RESPONSABILE SICUREZZA LOGISTICA-CHECK POINT",
    "AMMINISTRAZIONE-TESORERIA-FORNITORE G4",
    "OMNIPOS",
    "AMMINISTRAZIONE-TESORERIA-FORNITORE",
    "SEGRETERIA DIREZIONE COMMERCIALE",
    "MARKETING-ASSISTENTE DIREZIONE VENDITA",
]

# =====================================================
#  MODELLO USER
# =====================================================



# =====================================================
#  GANTT: CARICAMENTO TASK
# =====================================================

def load_gantt_tasks():
    if not os.path.exists(GANTT_FILE):
        raise FileNotFoundError(f"File Gantt non trovato: {GANTT_FILE}")

    df = pd.read_excel(GANTT_FILE)

    df = df.dropna(
        subset=[
            "Cosa fare per aprire il PDV",
            "Assegnata a (funzione aziendale)",
            "Inizio",
            "Numero di giorni necessari",
        ]
    )

    df["Inizio"] = pd.to_datetime(df["Inizio"])
    df["Numero di giorni necessari"] = df["Numero di giorni necessari"].astype(int)

    sponsor_mask = df["Assegnata a (funzione aziendale)"] == "SPONSOR"
    if sponsor_mask.any():
        base_date = df.loc[sponsor_mask, "Inizio"].min()
    else:
        base_date = df["Inizio"].min()

    tasks = []
    for idx, row in df.iterrows():
        start = row["Inizio"]
        if start < base_date:
            continue

        task_name = str(row["Cosa fare per aprire il PDV"]).strip()
        funzione = str(row["Assegnata a (funzione aziendale)"]).strip()
        days = int(row["Numero di giorni necessari"])

        offset = (start - base_date).days

        tasks.append(
            {
                "id": int(idx) + 1,
                "task": task_name,
                "function": funzione,
                "days": days,
                "offset": offset,
            }
        )

    tasks.sort(key=lambda x: (x["offset"], x["id"]))
    return tasks


try:
    GANTT_TASKS = load_gantt_tasks()
    print(f"Gantt caricato: {len(GANTT_TASKS)} attività.")
except Exception as e:
    print("ERRORE nel caricamento del Gantt:", e)
    GANTT_TASKS = []

# =====================================================
#  BACKWARD SCHEDULING: ancora alla task "Apertura"
# =====================================================

def get_total_plan_days():
    return max((t["offset"] + t["days"]) for t in GANTT_TASKS) if GANTT_TASKS else 0


def find_opening_task():
    """
    Trova la task di "Apertura punto vendita".
    Se nel tuo Excel si chiama diversamente, aggiorna le KEYWORDS.
    """
    KEYWORDS = [
        "apertura punto vendita",
        "apertura pdv",
        "apertura punto vendita (",
        "apertura",
    ]

    for t in GANTT_TASKS:
        name = (t.get("task") or "").strip().lower()
        if any(k in name for k in KEYWORDS) and (t.get("function") == "SPONSOR"):
            return t

    # fallback: anche senza function sponsor
    for t in GANTT_TASKS:
        name = (t.get("task") or "").strip().lower()
        if any(k in name for k in KEYWORDS):
            return t

    return None


def compute_plan_start_from_opening_date(opening_date: date) -> date:
    """
    opening_date = data apertura inserita dallo sponsor (fine logica).
    Calcola project_start (inizio calcolato) in modo che la task 'Apertura' finisca in opening_date.
    """
    opening_task = find_opening_task()
    if not opening_task:
        # fallback: comportamento precedente (ancora l'ultima attività reale)
        total_days = get_total_plan_days()
        return opening_date - timedelta(days=total_days - 1) if total_days else opening_date

    # fine_task = project_start + offset + (days-1)  => vogliamo fine_task == opening_date
    return opening_date - timedelta(days=(opening_task["offset"] + opening_task["days"] - 1))

def compute_task_dates(project_start: date, opening_date: date, task: dict):
    """
    Calcola start/end di un task.
    Se il task finirebbe dopo opening_date, lo forziamo a FINIRE in opening_date
    mantenendo la durata (quindi lo spostiamo indietro).
    """
    start_date = project_start + timedelta(days=task["offset"])
    end_date = start_date + timedelta(days=task["days"] - 1)

    forced = False
    if opening_date and end_date > opening_date:
        forced = True
        end_date = opening_date
        start_date = end_date - timedelta(days=task["days"] - 1)

    return start_date, end_date, forced


# =====================================================
#  STATO PROGETTO
# =====================================================

DEFAULT_STATE = {"project_start": None, "started": [], "completed": []}

def load_state():
    row = ProjectState.query.get(1)
    if not row:
        return DEFAULT_STATE.copy()

    try:
        data = json.loads(row.data_json) if row.data_json else {}
    except Exception:
        data = {}

    data.setdefault("project_start", None)
    data.setdefault("started", [])
    data.setdefault("completed", [])
    return data


def save_state(state):
    state.setdefault("project_start", None)
    state.setdefault("started", [])
    state.setdefault("completed", [])

    row = ProjectState.query.get(1)
    if not row:
        row = ProjectState(id=1)
        db.session.add(row)

    row.data_json = json.dumps(state, ensure_ascii=False)
    db.session.commit()

def get_task_status(task_id, started_ids, completed_ids, start_date=None, end_date=None):
    """
    Calcola lo stato del task.
    - completed -> completata
    - started -> in_corso
    - altrimenti -> non_iniziata
    - se non completata e end_date passata -> in_ritardo
    """
    # Normalizza task_id per evitare mismatch int/str
    task_id_str = str(task_id)
    started = set(str(x) for x in (started_ids or []))
    completed = set(str(x) for x in (completed_ids or []))

    if task_id_str in completed:
        return "completata"
    if task_id_str in started:
        return "in_corso"

    # Se c'è una scadenza e non è completato, valuta ritardo
    if end_date:
        try:
            today = date.today()
            if isinstance(end_date, datetime):
                end_d = end_date.date()
            else:
                end_d = end_date

            if end_d < today:
                return "in_ritardo"
        except Exception:
            pass

    return "non_iniziata"


# =====================================================
#  ADMIN: GESTIONE UTENTI
# =====================================================

@app.route("/admin/users")
@login_required
def admin_users():
    if not current_user.is_admin:
        flash("Non hai i permessi per accedere a questa sezione.", "danger")
        return redirect(url_for("dashboard"))

    users = User.query.order_by(User.created_at.asc()).all()

    return render_template(
        "admin_users.html",
        users=users,
        funzioni=FUNZIONI_AZIENDALI,
        self_registration_enabled=SELF_REGISTRATION_ENABLED,
    )

# =====================================================
#  ADMIN: CREA UTENTE
# =====================================================

@app.route("/admin/create_user", methods=["POST"])
@login_required
def admin_create_user():
    if current_user.role != ROLE_ADMIN:
        flash("Accesso negato.", "danger")
        return redirect(url_for("dashboard"))

    full_name = request.form.get("full_name")
    email = request.form.get("email")
    password = request.form.get("password")
    confirm = request.form.get("confirm")
    role = request.form.get("role")
    function_name = request.form.get("function_name") or None

    if password != confirm:
        flash("Le password non coincidono.", "danger")
        return redirect(url_for("admin_users"))

    if role in [ROLE_ADMIN, ROLE_AREA_MANAGER]:
        function_name = None

    exists = User.query.filter_by(email=email).first()
    if exists:
        flash("Esiste già un utente con questa email.", "danger")
        return redirect(url_for("admin_users"))

    new_user = User(
        full_name=full_name,
        email=email,
        role=role,
        function_name=function_name,
    )
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    flash("Utente creato con successo.", "success")
    return redirect(url_for("admin_users"))

# =====================================================
#  ADMIN: MODIFICA UTENTE
# =====================================================

@app.route("/admin/update_user/<int:user_id>", methods=["POST"])
@login_required
def admin_update_user(user_id):
    if not current_user.is_admin:
        flash("Non hai i permessi per modificare utenti.", "danger")
        return redirect(url_for("admin_users"))

    user = User.query.get_or_404(user_id)

    full_name = request.form.get("full_name")
    email = request.form.get("email")
    role = request.form.get("role")
    function_name = request.form.get("function_name") or None

    if role in [ROLE_ADMIN, ROLE_AREA_MANAGER]:
        function_name = None

    existing = User.query.filter(
        User.email == email,
        User.id != user_id
    ).first()
    if existing:
        flash("Email già usata da un altro utente.", "danger")
        return redirect(url_for("admin_users"))

    user.full_name = full_name
    user.email = email
    user.role = role
    user.function_name = function_name

    db.session.commit()

    flash("Utente aggiornato con successo!", "success")
    return redirect(url_for("admin_users"))

# =====================================================
#  ADMIN: ELIMINA UTENTE
# =====================================================

@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash("Accesso negato.", "danger")
        return redirect(url_for("dashboard"))

    user = User.query.get(user_id)
    if not user:
        flash("Utente non trovato.", "danger")
        return redirect(url_for("admin_users"))

    db.session.delete(user)
    db.session.commit()

    flash("Utente eliminato con successo.", "success")
    return redirect(url_for("admin_users"))

# =====================================================
#  ADMIN: TOGGLE SELF-REGISTRATION
# =====================================================

@app.route("/admin/toggle_registration", methods=["POST"])
@login_required
def toggle_registration():
    global SELF_REGISTRATION_ENABLED

    if current_user.role != ROLE_ADMIN:
        flash("Accesso negato.", "danger")
        return redirect(url_for("dashboard"))

    SELF_REGISTRATION_ENABLED = not SELF_REGISTRATION_ENABLED

    flash(
        "Registrazione libera " +
        ("ATTIVATA" if SELF_REGISTRATION_ENABLED else "DISATTIVATA"),
        "success"
    )

    return redirect(url_for("admin_users"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if not SELF_REGISTRATION_ENABLED:
        flash("La registrazione libera è disattivata.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        function_name = request.form.get("function_name")

        if password != confirm:
            flash("Le password non coincidono.", "danger")
            return redirect(url_for("register"))

        exists = User.query.filter_by(email=email).first()
        if exists:
            flash("Email già registrata.", "danger")
            return redirect(url_for("register"))

        new_user = User(
            full_name=full_name,
            email=email,
            role=ROLE_USER,
            function_name=function_name,
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash("Registrazione completata. Ora puoi effettuare il login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", funzioni=FUNZIONI_AZIENDALI)

# =====================================================
#  DASHBOARD (GANTT PERSONALE)
# =====================================================

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if current_user.is_admin and not current_user.function_name:
        return redirect(url_for("admin_users"))

    if current_user.role == ROLE_AREA_MANAGER:
        return redirect(url_for("dashboard_supervisione"))

    nome = current_user.full_name
    funzione = current_user.function_name

    if not funzione:
        flash(
            "Non hai una funzione aziendale assegnata. "
            "Contatta un amministratore per completare il profilo.",
            "warning",
        )
        return render_template(
            "dashboard.html",
            full_name=nome,
            function_name="(non assegnata)",
            project_start=None,
            opening_date=None,
            tasks=[],
            calendario=[],
            attivita_oggi=[],
            prossime_attivita=[],
            prossima_data=None,
            is_sponsor=False,
        )

    state = load_state()
    opening_str = state.get("project_start")  # ORA: data apertura
    started_ids = set(state.get("started", []))
    completed_ids = set(state.get("completed", []))

    project_start = None
    opening_date = None

    if opening_str:
        opening_date = datetime.strptime(opening_str, "%Y-%m-%d").date()
        project_start = compute_plan_start_from_opening_date(opening_date)

    # SPONSOR: salva data apertura
    if request.method == "POST" and current_user.is_sponsor:
        new_date_str = request.form.get("project_start")
        try:
            opening_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            state["project_start"] = new_date_str
            save_state(state)

            project_start = compute_plan_start_from_opening_date(opening_date)

            flash("Data apertura punto vendita aggiornata.", "success")
        except Exception:
            flash("Data non valida.", "danger")

    user_tasks_with_dates = []
    calendario = []
    attivita_oggi = []
    prossime_attivita = []
    prossima_data = None

    if project_start:
        user_tasks = [t for t in GANTT_TASKS if t["function"] == funzione]

        cal_map = defaultdict(list)
        for t in user_tasks:
            start_date, end_date, forced = compute_task_dates(project_start, opening_date, t)

            status = get_task_status(
                t["id"],
                started_ids,
                completed_ids,
                start_date=start_date,
                end_date=end_date,
            )

            info = {
                "id": t["id"],
                "task": t["task"],
                "days": t["days"],
                "start_date": start_date,
                "end_date": end_date,
                "status": status,
                "completed": t["id"] in completed_ids,
            }
            user_tasks_with_dates.append(info)

            for i in range(t["days"]):
                giorno = start_date + timedelta(days=i)
                cal_map[giorno].append(info)

        for d in sorted(cal_map.keys()):
            calendario.append({"date": d, "tasks": cal_map[d]})

        oggi = date.today()

        for t in user_tasks_with_dates:
            if t["completed"]:
                continue

            if t["start_date"] <= oggi <= t["end_date"]:
                attivita_oggi.append(t)
            elif t["start_date"] > oggi:
                prossime_attivita.append(t)

        prossime_attivita.sort(key=lambda x: x["start_date"])
        if prossime_attivita:
            prossima_data = prossime_attivita[0]["start_date"]

    return render_template(
        "dashboard.html",
        full_name=nome,
        function_name=funzione,
        project_start=project_start,   # inizio calcolato
        opening_date=opening_date,     # data apertura
        tasks=user_tasks_with_dates,
        calendario=calendario,
        attivita_oggi=attivita_oggi,
        prossime_attivita=prossime_attivita,
        prossima_data=prossima_data,
        is_sponsor=current_user.is_sponsor,
    )

# =====================================================
#  TOGGLE TASK
# =====================================================

@app.route("/toggle_task", methods=["POST"])
@login_required
def toggle_task():
    funzione = current_user.function_name
    if not funzione:
        flash("Non hai una funzione aziendale assegnata.", "warning")
        return redirect(url_for("dashboard"))

    task_id = int(request.form.get("task_id"))
    state = load_state()
    started = set(state.get("started", []))
    completed = set(state.get("completed", []))

    task = next((t for t in GANTT_TASKS if t["id"] == task_id), None)
    if not task:
        flash("Attività non trovata.", "danger")
        return redirect(url_for("dashboard"))

    if task_id not in started and task_id not in completed:
        started.add(task_id)
        if task["days"] == 1:
            completed.add(task_id)
    elif task_id in started and task_id not in completed:
        completed.add(task_id)
    elif task_id in completed:
        completed.discard(task_id)
        started.discard(task_id)

    state["started"] = sorted(list(started))
    state["completed"] = sorted(list(completed))
    save_state(state)

    return redirect(url_for("dashboard"))

# =====================================================
#  TIMELINE
# =====================================================

@app.route("/timeline")
@login_required
def timeline():
    state = load_state()
    opening_str = state.get("project_start")  # ORA: data apertura

    started_ids = set(state.get("started", []))
    completed_ids = set(state.get("completed", []))

    functions_list = sorted({t["function"] for t in GANTT_TASKS})
    selected_function = request.args.get("function", "")

    sort_by = request.args.get("sort_by", "start_date")
    sort_dir = request.args.get("sort_dir", "asc")

    ALLOWED_SORT = {"days", "start_date", "end_date", "status"}
    if sort_by not in ALLOWED_SORT:
        sort_by = "start_date"

    reverse = sort_dir == "desc"

    if not opening_str:
        return render_template(
            "timeline.html",
            project_start=None,
            opening_date=None,
            tasks=[],
            functions_list=functions_list,
            selected_function=selected_function,
            sort_by=sort_by,
            sort_dir=sort_dir,
            date=date,
        )

    opening_date = datetime.strptime(opening_str, "%Y-%m-%d").date()
    project_start = compute_plan_start_from_opening_date(opening_date)

    tasks_with_dates = []
    for t in GANTT_TASKS:
        if selected_function and t["function"] != selected_function:
            continue

        start_date, end_date, forced = compute_task_dates(project_start, opening_date, t)

        status = get_task_status(
            t["id"],
            started_ids,
            completed_ids,
            start_date=start_date,
            end_date=end_date,
        )

        tasks_with_dates.append(
            {
                "id": t["id"],
                "task": t["task"],
                "function": t["function"],
                "days": t["days"],
                "start_date": start_date,
                "end_date": end_date,
                "status": status,
                "completed": t["id"] in completed_ids,
            }
        )

    tasks_with_dates.sort(key=lambda x: x[sort_by], reverse=reverse)

    return render_template(
        "timeline.html",
        project_start=project_start,
        opening_date=opening_date,
        tasks=tasks_with_dates,
        functions_list=functions_list,
        selected_function=selected_function,
        sort_by=sort_by,
        sort_dir=sort_dir,
        date=date,
    )

# =====================================================
#  SUPERVISIONE (SPONSOR + AREA_MANAGER)
# =====================================================

@app.route("/supervisione", methods=["GET"])
@login_required
def dashboard_supervisione():
    if not (current_user.is_sponsor or current_user.role == ROLE_AREA_MANAGER):
        flash("Non hai i permessi per accedere alla supervisione.", "danger")
        return redirect(url_for("dashboard"))

    state = load_state()
    opening_str = state.get("project_start")  # ORA: data apertura
    started_ids = set(state.get("started", []))
    completed_ids = set(state.get("completed", []))

    owners_map = defaultdict(list)
    for u in User.query.filter(User.function_name.isnot(None)).all():
        owners_map[u.function_name].append(u.full_name)

    if not opening_str:
        flash("Lo SPONSOR non ha ancora impostato la data di apertura del punto vendita.", "warning")
        return render_template(
            "sponsor_dashboard.html",
            project_start=None,
            project_end=None,
            days=[],
            selected_date=None,
            activities_for_selected=[],
            kpis=None,
        )

    opening_date = datetime.strptime(opening_str, "%Y-%m-%d").date()
    project_start = compute_plan_start_from_opening_date(opening_date)

    tasks_with_dates = []
    day_map = defaultdict(list)

    for t in GANTT_TASKS:
        start_date, end_date, forced = compute_task_dates(project_start, opening_date, t)
        status = get_task_status(t["id"], started_ids, completed_ids)

        owner_list = owners_map.get(t["function"], [])
        responsabile = ", ".join(owner_list) if owner_list else None

        info = {
            "id": t["id"],
            "task": t["task"],
            "function": t["function"],
            "days": t["days"],
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "completed": t["id"] in completed_ids,
            "responsabile": responsabile,
        }
        tasks_with_dates.append(info)

        d = start_date
        while d <= end_date:
            day_map[d].append(info)
            d += timedelta(days=1)

    # fine reale = max end_date; (potrebbe essere > opening_date se il Gantt ha task post-apertura)
    project_end = max((t["end_date"] for t in tasks_with_dates), default=project_start)

    sel_str = request.args.get("date")
    today = date.today()
    selected_date = None

    if sel_str:
        try:
            selected_date = datetime.strptime(sel_str, "%Y-%m-%d").date()
        except Exception:
            selected_date = None

    if (not selected_date) or selected_date < project_start or selected_date > project_end:
        if project_start <= today <= project_end:
            selected_date = today
        else:
            selected_date = project_start

    activities_for_selected = day_map.get(selected_date, [])

    days_list = []
    d = project_start
    while d <= project_end:
        entries = day_map.get(d, [])
        if not entries:
            day_status = "vuoto"
        else:
            statuses = {e["status"] for e in entries}
            if statuses == {"completata"}:
                day_status = "completata"
            elif "in_ritardo" in statuses:
                day_status = "in_ritardo"
            elif "in_corso" in statuses:
                day_status = "in_corso"
            else:
                if d < today:
                    day_status = "in_ritardo"
                else:
                    day_status = "non_iniziata"

        days_list.append({"date": d, "status": day_status, "has_tasks": bool(entries)})
        d += timedelta(days=1)

    total_tasks = len(GANTT_TASKS)
    completed_tasks = len(completed_ids)
    in_progress_tasks = len(started_ids - completed_ids)
    not_started_tasks = total_tasks - completed_tasks - in_progress_tasks
    if not_started_tasks < 0:
        not_started_tasks = 0

    progress = round((completed_tasks / total_tasks) * 100, 1) if total_tasks else 0.0

    kpis = {
        "total": total_tasks,
        "completed": completed_tasks,
        "in_progress": in_progress_tasks,
        "not_started": not_started_tasks,
        "progress": progress,
    }

    return render_template(
        "sponsor_dashboard.html",
        project_start=project_start,
        project_end=project_end,
        days=days_list,
        selected_date=selected_date,
        activities_for_selected=activities_for_selected,
        kpis=kpis,
    )
# =====================================================
#  AVVIO APP (solo locale)
# =====================================================
if __name__ == "__main__":
    print("Avvio app PREMIUM con Gantt collegato e gestione utenti...")

    # Debug utile solo in locale
    print("ROUTES REGISTRATE:")
    for r in app.url_map.iter_rules():
        print(r)

    app.run(debug=True)

# =====================================================
#  AVVIO APP
# =====================================================


