# Progetto PDV - Webapp gestione attività

Applicazione web sviluppata in **Python con framework Flask** per la gestione e il monitoraggio delle attività dei punti vendita.

## Funzionalità principali

- Gestione utenti con ruoli
- Dashboard di monitoraggio attività
- Timeline / Gantt delle attività
- Aggiornamento stato avanzamento lavori
- Supervisione progetto

## Tecnologie utilizzate

- Python
- Flask
- HTML / CSS
- SQLite / PostgreSQL (in base all'ambiente di deploy)
- Gunicorn (per deploy su server)

## Avvio del progetto in locale

Clonare il repository:

```bash
git clone https://github.com/Texyoo/Progetto-pdv.git
cd Progetto-pdv
```

Installazione dipendenze
pip install -r requirements.txt

Avvio applicazione
python app.py

L'applicazione sarà disponibile su:

http://127.0.0.1:5000

Deploy

Il progetto è stato deployato online utilizzando Render.

Accesso

L'accesso alla piattaforma avviene tramite autenticazione con credenziali utente.