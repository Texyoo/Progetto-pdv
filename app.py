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
#  CONFIGURAZIONE BASE APP
# =====================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = "cambia_questa_chiave_in_produzione"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# File Gantt (come prima)
GANTT_FILE = os.path.join(BASE_DIR, "Gantt modificato.xlsx")
# Stato progetto (come prima)
STATE_FILE = os.path.join(BASE_DIR, "project_state.json")

# Database utenti (nuovo, cartella /database)
DB_DIR = os.path.join(BASE_DIR, "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "users.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Self-registration attiva (puoi mettere False per disattivarla dopo la demo)
SELF_REGISTRATION_ENABLED = True

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"  # se non loggato → redirect a login

# =====================================================
#  RUOLI DI SISTEMA
# =====================================================

ROLE_ADMIN = "ADMIN"
ROLE_SPONSOR = "SPONSOR"
ROLE_USER = "USER"
ROLE_AREA_MANAGER = "AREA_MANAGER"

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
#  MODELLO USER (DB UTENTI)
# =====================================================

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # ruolo di sistema: ADMIN / SPONSOR / USER / AREA_MANAGER
    role = db.Column(db.String(20), nullable=False, default=ROLE_USER)

    # funzione aziendale collegata al Gantt (può essere None per gli admin / capi area)
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


# =====================================================
#  GANTT: CARICAMENTO TASK
# =====================================================

def load_gantt_tasks():
    """
    Legge il file Excel e lo trasforma in una lista di dizionari:

    {
        "id": int,
        "task": str,
        "function": str,
        "days": int,
        "offset": int  # giorni rispetto alla PRIMA ATTIVITÀ SPONSOR
    }
    """
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

    # Base del progetto: prima attività SPONSOR
    sponsor_mask = df["Assegnata a (funzione aziendale)"] == "SPONSOR"
    if sponsor_mask.any():
        base_date = df.loc[sponsor_mask, "Inizio"].min()
    else:
        base_date = df["Inizio"].min()

    tasks = []
    for idx, row in df.iterrows():
        start = row["Inizio"]
        if start < base_date:
            # ignora eventuali attività "prima" del progetto
            continue

        task_name = str(row["Cosa fare per aprire il PDV"]).strip()
        funzione = str(row["Assegnata a (funzione aziendale)"]).strip()
        days = int(row["Numero di giorni necessari"])

        offset = (start - base_date).days  # 0 = prima attività SPONSOR

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
#  STATO PROGETTO (COME PRIMA)
# =====================================================

def load_state():
    """
    Stato globale del progetto:
    {
      "project_start": "YYYY-MM-DD" oppure None,
      "started": [task_id1, ...],
      "completed": [task_id1, ...]
    }
    """
    if not os.path.exists(STATE_FILE):
        return {"project_start": None, "started": [], "completed": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("started", [])
            data.setdefault("completed", [])
            return data
    except Exception:
        return {"project_start": None, "started": [], "completed": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_task_status(task_id, started_ids, completed_ids, start_date=None, end_date=None):
    """Restituisce lo stato logico dell'attività.

    Stati possibili:
    - "completata"
    - "in_corso"
    - "non_iniziata"
    - "in_ritardo" (se non completata e oltre la data di fine)
    """
    # Stato base in funzione dei flag memorizzati
    if task_id in completed_ids:
        base_status = "completata"
    elif task_id in started_ids:
        base_status = "in_corso"
    else:
        base_status = "non_iniziata"

    # Se non abbiamo le date, restituiamo lo stato base
    if start_date is None or end_date is None:
        return base_status

    today = date.today()
    if base_status != "completata" and today > end_date:
        return "in_ritardo"

    return base_status


# =====================================================
#  UTILITY: CREAZIONE ADMIN INIZIALE
# =====================================================

def ensure_initial_admin():
    """
    Crea l'utente admin iniziale se non esiste.
    Dati forniti da Alessandro:
      - Nome: Alessandro Camera
      - Email: Alessandro.camera95@gmail.com
      - Password: Admin123!
      - Ruolo: ADMIN
      - Nessuna funzione aziendale (non appare nel Gantt)
    """
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

    # ADMIN e AREA_MANAGER non hanno funzione aziendale collegata
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

    # ADMIN e AREA_MANAGER non hanno funzione aziendale
    if role in [ROLE_ADMIN, ROLE_AREA_MANAGER]:
        function_name = None

    # Verifica email già usata da un altro utente
    existing = User.query.filter(
        User.email == email,
        User.id != user_id
    ).first()
    if existing:
        flash("Email già usata da un altro utente.", "danger")
        return redirect(url_for("admin_users"))

    # Aggiorna dati
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
    # Admin puro senza funzione → pannello admin
    if current_user.is_admin and not current_user.function_name:
        return redirect(url_for("admin_users"))

    # Capo Area → dashboard supervisione
    if current_user.role == ROLE_AREA_MANAGER:
        return redirect(url_for("dashboard_supervisione"))

    nome = current_user.full_name
    funzione = current_user.function_name

    if not funzione:
        # Nessuna funzione assegnata → niente task
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
            tasks=[],
            calendario=[],
            attivita_oggi=[],
            prossime_attivita=[],
            prossima_data=None,
            is_sponsor=False,
        )

    state = load_state()
    project_start_str = state.get("project_start")
    started_ids = set(state.get("started", []))
    completed_ids = set(state.get("completed", []))

    project_start = None
    if project_start_str:
        project_start = datetime.strptime(project_start_str, "%Y-%m-%d").date()

    # SPONSOR può modificare la data di inizio progetto
    if request.method == "POST" and current_user.is_sponsor:
        new_date_str = request.form.get("project_start")
        try:
            _ = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            state["project_start"] = new_date_str
            save_state(state)
            project_start = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            flash("Data di inizio progetto aggiornata.", "success")
        except Exception:
            flash("Data non valida.", "danger")

    user_tasks_with_dates = []
    calendario = []
    attivita_oggi = []
    prossime_attivita = []
    prossima_data = None

    if project_start:
        # Attività solo della funzione dell'utente
        user_tasks = [t for t in GANTT_TASKS if t["function"] == funzione]

        cal_map = defaultdict(list)
        for t in user_tasks:
            start_date = project_start + timedelta(days=t["offset"])
            end_date = start_date + timedelta(days=t["days"] - 1)

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

            # Popoliamo il calendario giorno per giorno
            for i in range(t["days"]):
                giorno = start_date + timedelta(days=i)
                cal_map[giorno].append(info)

        for d in sorted(cal_map.keys()):
            calendario.append({"date": d, "tasks": cal_map[d]})

        # ==============================
        #     CALCOLO ATTIVITÀ OGGI
        #   (solo NON completate)
        # ==============================
        oggi = date.today()

        for t in user_tasks_with_dates:
            if t["completed"]:
                continue  # ignoriamo quelle già completate

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
        project_start=project_start,
        tasks=user_tasks_with_dates,
        calendario=calendario,
        attivita_oggi=attivita_oggi,
        prossime_attivita=prossime_attivita,
        prossima_data=prossima_data,
        is_sponsor=current_user.is_sponsor,
    )


# =====================================================
#  TOGGLE ATTIVITÀ (INIZIATA / COMPLETATA)
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

    # Primo click -> iniziata
    if task_id not in started and task_id not in completed:
        started.add(task_id)
        if task["days"] == 1:
            completed.add(task_id)
    # Secondo click -> completata
    elif task_id in started and task_id not in completed:
        completed.add(task_id)
    # Terzo click -> reset
    elif task_id in completed:
        completed.discard(task_id)
        started.discard(task_id)

    state["started"] = sorted(list(started))
    state["completed"] = sorted(list(completed))
    save_state(state)

    return redirect(url_for("dashboard"))


# =====================================================
#  TIMELINE GLOBALE
# =====================================================

@app.route("/timeline")
@login_required
def timeline():
    state = load_state()
    project_start_str = state.get("project_start")

    started_ids = set(state.get("started", []))
    completed_ids = set(state.get("completed", []))

    functions_list = sorted({t["function"] for t in GANTT_TASKS})
    selected_function = request.args.get("function", "")

    if not project_start_str:
        return render_template(
            "timeline.html",
            project_start=None,
            tasks=[],
            functions_list=functions_list,
            selected_function=selected_function,
            date=date,
        )

    project_start = datetime.strptime(project_start_str, "%Y-%m-%d").date()

    tasks_with_dates = []
    for t in GANTT_TASKS:
        if selected_function and t["function"] != selected_function:
            continue

        start_date = project_start + timedelta(days=t["offset"])
        end_date = start_date + timedelta(days=t["days"] - 1)

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

    tasks_with_dates.sort(key=lambda x: (x["function"], x["start_date"], x["id"]))

    return render_template(
        "timeline.html",
        project_start=project_start,
        tasks=tasks_with_dates,
        functions_list=functions_list,
        selected_function=selected_function,
        date=date,
    )


# =====================================================
#  DASHBOARD SUPERVISIONE (SPONSOR + CAPO AREA)
# =====================================================

@app.route("/supervisione", methods=["GET"])
@login_required
def dashboard_supervisione():
    # Solo Sponsor e Capi Area possono accedere
    if not (current_user.is_sponsor or current_user.role == ROLE_AREA_MANAGER):
        flash("Non hai i permessi per accedere alla supervisione.", "danger")
        return redirect(url_for("dashboard"))

    state = load_state()
    project_start_str = state.get("project_start")
    started_ids = set(state.get("started", []))
    completed_ids = set(state.get("completed", []))

        # Mappa: funzione aziendale -> elenco nominativi che la ricoprono
    owners_map = defaultdict(list)
    for u in User.query.filter(User.function_name.isnot(None)).all():
        owners_map[u.function_name].append(u.full_name)


    if not project_start_str:
        flash("Lo SPONSOR non ha ancora impostato la data di inizio progetto.", "warning")
        return render_template(
            "sponsor_dashboard.html",
            project_start=None,
            project_end=None,
            days=[],
            selected_date=None,
            activities_for_selected=[],
            kpis=None,
        )

    project_start = datetime.strptime(project_start_str, "%Y-%m-%d").date()

    # Calcoliamo date di inizio/fine e mappa giorni -> attività
    tasks_with_dates = []
    day_map = defaultdict(list)

    for t in GANTT_TASKS:
        start_date = project_start + timedelta(days=t["offset"])
        end_date = start_date + timedelta(days=t["days"] - 1)
        status = get_task_status(t["id"], started_ids, completed_ids)

        # Ricaviamo il/i responsabile/i per la funzione aziendale di questo task
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

        # tutti i giorni in cui l'attività è "attiva"
        d = start_date
        while d <= end_date:
            day_map[d].append(info)
            d += timedelta(days=1)

    if not tasks_with_dates:
        project_end = project_start
    else:
        project_end = max(t["end_date"] for t in tasks_with_dates)

    # Data selezionata dal calendario
    sel_str = request.args.get("date")
    today = date.today()
    selected_date = None

    if sel_str:
        try:
            selected_date = datetime.strptime(sel_str, "%Y-%m-%d").date()
        except Exception:
            selected_date = None

    # Se la data selezionata non è valida o fuori range, scegliamo:
    # - oggi se sta nel range
    # - altrimenti la data di inizio progetto
    if (
        not selected_date
        or selected_date < project_start
        or selected_date > project_end
    ):
        if project_start <= today <= project_end:
            selected_date = today
        else:
            selected_date = project_start

    activities_for_selected = day_map.get(selected_date, [])

    # Costruiamo l'elenco di TUTTI i giorni del progetto, con stato
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
            else:  # tutte non_iniziata
                if d < today:
                    day_status = "in_ritardo"
                else:
                    day_status = "non_iniziata"

        days_list.append(
            {
                "date": d,
                "status": day_status,
                "has_tasks": bool(entries),
            }
        )
        d += timedelta(days=1)

    # KPI globali
    total_tasks = len(GANTT_TASKS)
    completed_tasks = len(completed_ids)
    in_progress_tasks = len(started_ids - completed_ids)

    # Task "non iniziati" = totali - (completati + in corso)
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
#  AVVIO APP
# =====================================================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_initial_admin()
    print("Avvio app PREMIUM con Gantt collegato e gestione utenti...")
    app.run(debug=True)
