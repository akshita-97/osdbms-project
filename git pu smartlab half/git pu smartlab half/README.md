# SmartLab -- Intelligent Computer Lab Maintenance & Resource Allocation System

A Flask + MySQL web application
that manages a college computer lab's maintenance workload, using
classic OS concepts -- CPU-scheduling-style algorithms (FCFS, SJF,
Priority, optional Round Robin) -- as an **application-level
simulation** to plan the order of maintenance jobs and track the limited
maintenance resources (technicians, RAM modules, keyboards, network
testers, OS installation kits, etc.) they need.

> **Core idea:** Multiple maintenance jobs compete for limited lab
> resources, so the system uses OS scheduling concepts to decide which
> job runs next and tracks resource allocation and release for each job.
> It does NOT replace or modify the real operating system's scheduler.

Runs entirely on **one Windows laptop** -- no cloud, no Docker, no
external network dependency. See `docs/PROJECT_OVERVIEW.md` for the
full write-up and `docs/ALGORITHMS.md` / `docs/DATABASE.md` for the OS
and DBMS concept documentation your viva will ask about.

## Quick Start (VS Code) -- about 5 minutes

You need **Python 3.10+** and **MySQL Server 8.x** installed (details in
section 1). Then:

1. **Open the folder:** VS Code -> *File -> Open Folder...* -> select the `smartlab` folder.
   Install the recommended extensions when VS Code offers (Python, Debugpy).
2. **Open a terminal in VS Code** (*Terminal -> New Terminal*) and run:

   ```bat
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```

   (macOS/Linux: `source venv/bin/activate` and `cp .env.example .env`.)
3. **Put your MySQL password in `.env`:** open `.env`, set `DB_PASSWORD=...`, save.
4. **Create the database + demo data** (one command, no MySQL client needed):

   ```bat
   python setup_db.py
   ```

5. **Run it:** press **F5** (pick *SmartLab: Run app*) or run `python app.py`,
   then open **http://127.0.0.1:5000**.

On Windows you can instead double-click **`setup_windows.bat`** once, then
**`run_windows.bat`** whenever you want to start the app.

To check everything works, run the tests: `python -m unittest discover -s tests -t . -v`
(or the *Testing* panel in VS Code).

---

## 1. Prerequisites

- **Python 3.10+** (https://www.python.org/downloads/ -- during
  install, tick "Add Python to PATH")
- **MySQL Server 8.x** (https://dev.mysql.com/downloads/installer/ --
  the "MySQL Installer for Windows" is the easiest route; remember the
  root password you set)
- (Optional) **VS Code** or any editor

## 2. Installation (Windows Command Prompt / PowerShell)

```bat
:: 1. Go into the project folder (wherever you extracted/cloned it)
cd smartlab

:: 2. Create a virtual environment
python -m venv venv

:: 3. Activate it
venv\Scripts\activate

:: 4. Install dependencies
pip install -r requirements.txt
```

You should see `(venv)` at the start of your prompt once the
environment is activated.

## 3. Set Up MySQL

**Easiest way:** finish section 4 (`.env`) first, then run:

```bat
python setup_db.py
```

It creates `smartlab_db`, all tables, triggers and indexes, and loads the
demo data. Use `python setup_db.py --yes` to skip the confirmation prompt.
Re-run it any time to reset the database to a clean demo state (it drops
and recreates the database).

**Manual alternative** (if you prefer the MySQL client): open the
**MySQL Command Line Client** and run:

```sql
SOURCE C:/path/to/smartlab/database/schema.sql;
SOURCE C:/path/to/smartlab/database/seed.sql;
```

or from a normal Command Prompt:

```bat
mysql -u root -p < database\schema.sql
mysql -u root -p smartlab_db < database\seed.sql
```

> Note: `schema.sql` starts with `DROP DATABASE IF EXISTS smartlab_db;
> CREATE DATABASE smartlab_db;` so re-running it resets everything.

## 4. Configure Database Credentials

Copy the example environment file and edit it with your real MySQL
password:

```bat
copy .env.example .env
```

Open `.env` in a text editor and set at least:

```
DB_USER=root
DB_PASSWORD=your_actual_mysql_password
```

The other settings (`SECRET_KEY`, `DEFAULT_TIME_QUANTUM`, etc.) can be
left at their defaults for a normal demo run.

## 5. Run the Application

```bat
venv\Scripts\activate
python app.py
```

(In VS Code: press **F5** and choose *SmartLab: Run app*. Use *SmartLab: Run app
(debugger, breakpoints work)* if you want to set breakpoints.)

You should see:

```
[SmartLab] Database connection OK: Connected to MySQL successfully.
[SmartLab] Starting Flask development server on http://127.0.0.1:5000
```

Open **http://127.0.0.1:5000** in your browser.

If instead you see a warning about not being able to connect to
MySQL, double-check that:
1. The MySQL service is actually running (Windows Services app, or
   `net start MySQL80` from an admin Command Prompt).
2. `.env` has the correct `DB_PASSWORD`.
3. You actually ran `python setup_db.py`.

If MySQL is down while the app is running, pages show a friendly "Can't reach the
database" screen with the fix steps instead of a stack trace.

## 5b. Logging In (user accounts)

Every page now requires a login. On first visit you are sent to
**/login**; click **Create an account** to sign up with a username and
password (min. 8 characters). The account is saved in the MySQL `users`
table, so it stays after you close the app or restart MySQL. Passwords are
stored only as salted hashes. Use **Log out** at the bottom of the sidebar.

- Existing installs: just restart the app -- it creates the `users` table
  automatically; no need to re-run `setup_db.py`.
- Re-running `python setup_db.py` resets the lab data but **keeps** all user
  accounts.

## 6. Demo Walkthrough (matches docs/ALGORITHMS.md exactly)

1. **Dashboard** -- see the seeded labs/computers/tasks/resources at a
   glance.
2. **Maintenance** page -- see 6 sample maintenance requests already
   converted into tasks J-101..J-106; try reporting a new fault
   yourself and approving it, assigning a technician and completing it.
3. **Scheduling Queue** -- run FCFS, then SJF, then Priority on the
   same task set and compare the Gantt chart and average
   waiting/turnaround times (see `docs/ALGORITHMS.md` for the expected
   numbers).
4. **Resources** page -- see the 6 seeded resource types and their
   current availability.
5. Open a task's **Manage** page (from Maintenance or Resources) and
   walk it through **Allocate Resources -> Start Maintenance ->
   Complete Maintenance -> Release Resources**.
6. **History** page -- see the two completed historical maintenance
   records for PC-04 and PC-10.

## 7. Project Structure

```
smartlab/
├── app.py                   Flask entry point
├── config.py                Loads settings from .env
├── setup_db.py              One-command database creation + demo data
├── setup_windows.bat / run_windows.bat   Windows helpers
├── requirements.txt
├── .env.example
├── .vscode/                 Run/debug, test and task configs for VS Code
├── tests/                   Automated tests (algorithms + page smoke tests)
├── database/
│   ├── schema.sql            Full DDL (tables, constraints, triggers, indexes)
│   └── seed.sql               Realistic sample data
├── db/
│   └── database.py           mysql-connector-python helpers (parameterized SQL, transactions)
├── algorithms/                Plain-Python OS-concept implementations
│   ├── fcfs.py  sjf.py  priority.py  round_robin.py
├── services/                  Business logic + validation
│   ├── maintenance_service.py
│   ├── resource_service.py    scheduling_service.py
├── routes/                     Flask Blueprints (thin controllers)
│   ├── dashboard.py  computers.py  maintenance.py
│   ├── scheduling.py  resources.py
├── templates/                  Jinja2 HTML (one file per page)
├── static/
│   ├── css/style.css          Dependency-free styling
│   └── js/dashboard.js
└── docs/
    ├── PROJECT_OVERVIEW.md    ├── DATABASE.md
    ├── ALGORITHMS.md          └── TESTING.md
```

## 8. Notes / Limitations (be ready to explain these in your viva)

- Every lab computer in the database is a simulated record only; the
  app does not read any real hardware or OS data.
- The scheduling algorithms are an **application-level simulation**
  for ordering maintenance jobs; they do not touch or replace the real
  OS process scheduler.
- Resource allocation is a straightforward availability check: a task
  is allocated its full remaining need only if every required resource
  is currently available, otherwise it waits.

Full details: `docs/PROJECT_OVERVIEW.md`, Section "Limitations".
