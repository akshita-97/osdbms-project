# SmartLab -- Computer Lab Maintenance System

A Flask + MySQL web application for managing a college computer lab:
labs, computers, reported faults, technicians and maintenance history.

This is the **initial phase** of the project: a clean web UI on top of a
small relational database. Everything runs on one laptop (no cloud, no Docker).

## What it does

| Page | What you can do |
|------|-----------------|
| **Dashboard** | Summary cards (labs, computers, open requests, technicians) and recent activity |
| **Labs & Computers** | Add / edit / delete labs, add / delete computers, change a computer's status, filter by lab |
| **Maintenance** | Report a fault, approve or reject it, assign a technician and start work, mark it completed, manage technicians |
| **History** | Every completed repair, with technician, time taken and remarks (filter by computer) |

A maintenance request moves through these steps, and the computer and
technician statuses are updated automatically at each step:

```
Pending Review --> Approved --> In Progress --> Completed (shows up in History)
       \--> Rejected
```

## Quick start (VS Code, about 5 minutes)

You need **Python 3.10+** and **MySQL Server 8.x** installed and running.

1. **Open the folder** in VS Code: *File -> Open Folder...* -> select the `smartlab` folder.
2. **Open a terminal** (*Terminal -> New Terminal*) and run:

   ```bat
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

   (macOS / Linux: `source venv/bin/activate`)
3. **Set your MySQL password:** open the `.env` file and change
   `DB_PASSWORD=your_mysql_password_here` to your real MySQL password. Save it.
4. **Create the database and demo data** (one command, no MySQL client needed):

   ```bat
   python setup_db.py
   ```
5. **Run the app:** press **F5** in VS Code (choose *SmartLab: Run app*) or run
   `python app.py`, then open **http://127.0.0.1:5000**.

If VS Code asks which Python interpreter to use, pick the one inside `venv`.

> Windows shortcut: double-click `setup_windows.bat` once (it does steps 2-4),
> then `run_windows.bat` whenever you want to start the app.

Re-run `python setup_db.py` at any time to reset the database to the clean demo data.

## Demo walkthrough

1. **Dashboard** -- see the seeded labs, computers and requests at a glance.
2. **Labs & Computers** -- add a lab, add a computer to it, change a computer's status.
3. **Maintenance** -- report a new fault, then *Approve* it, *Assign & Start* it with a
   technician, and *Mark Completed* with remarks. Watch the computer status and the
   technician's availability change along the way.
4. **History** -- your completed repair now appears here.

## Database (MySQL, 4 tables)

```
labs (lab_id PK, lab_name, location, capacity, status)
   |
   | 1 lab : many computers
   v
computers (computer_id PK, lab_id FK, ip_address, processor, ram_gb,
           storage_gb, os_name, status)
   |
   | 1 computer : many requests
   v
maintenance_requests (request_id PK, computer_id FK, technician_id FK, problem_description,
                      fault_type, severity, status, reported_at, started_at,
                      completed_at, remarks)
   ^
   | 1 technician : many requests
   |
technicians (technician_id PK, name, specialization, availability, contact)
```

Things worth pointing out when you present it:

- **Foreign keys** link the tables (a computer must belong to a lab, a request must be about a real computer).
- **ENUM and CHECK constraints** keep data valid (e.g. capacity can't be negative, status must be one of the allowed values).
- **Transactions**: approving, starting and completing a request each update several tables at once; if one update fails, all of them are rolled back (`execute_transaction` in `db/database.py`).
- **Parameterized queries** everywhere (`%s` placeholders), so the app is safe from SQL injection.
- **Validation rules** in `services/maintenance_service.py`, e.g. you can't delete a lab that still has computers, and you can't start work without a free technician.

## Project structure

```
smartlab/
├── app.py                 Flask entry point
├── config.py              Reads settings from .env
├── setup_db.py            One-command database creation + demo data
├── requirements.txt       Flask, mysql-connector-python, python-dotenv
├── .env                   Your database password goes here (don't share it)
├── setup_windows.bat / run_windows.bat
├── .vscode/               Run, debug and test settings for VS Code
├── database/
│   ├── schema.sql         Tables, constraints, indexes
│   └── seed.sql           Demo data
├── db/database.py         MySQL helper functions
├── services/maintenance_service.py   Business logic + validation
├── routes/                dashboard.py, computers.py, maintenance.py
├── templates/             HTML pages (Jinja2)
├── static/                CSS and a little JavaScript
└── tests/                 Page smoke tests
```

## Run the tests

```bat
python -m unittest discover -s tests -t . -v
```

(or use the *Testing* panel in VS Code). The tests skip themselves if MySQL isn't reachable.

## Troubleshooting

- **"Can't reach the database" page / warning on start:** make sure the MySQL service is
  running (Windows: *Services* app -> *MySQL80* -> Start), that `DB_PASSWORD` in `.env` is
  correct, and that you ran `python setup_db.py`.
- **`ModuleNotFoundError`:** the virtual environment isn't active or the requirements
  aren't installed. Run `venv\Scripts\activate` and `pip install -r requirements.txt`.
