# SmartLab - Computer Resource Management System

SmartLab is a web-based laboratory management platform designed to streamline how college computer labs monitor hardware resources, manage system tasks and track maintenance. Built with **Python**, **Flask**, and **MySQL**, it integrates core **Operating System (OS)** and **Database Management System (DBMS)** concepts into a practical tool for lab administrators.

## 📌 Project Overview

Managing a multi-system computer lab manually can make tracking resource usage, running processes and scheduled maintenance difficult. SmartLab bridges this gap by centralizing hardware monitoring and process scheduling in one system. 
The platform leverages `psutil` for real-time CPU and RAM monitoring while simulating classic OS process scheduling algorithms (FCFS, SJF, and Round Robin) to calculate turnaround time, waiting time, and visualize task execution via Gantt charts.

## ✨ Features

* **🖥️ Computer Management Service:** Track system details, manage remote computer access and perform basic system operations (e.g., shutdown).
* **📊 Resource Monitoring Service:** Real-time tracking of CPU, RAM and active system processes using `psutil`
* **⏱️ Task Scheduling & Simulation:** Simulates process scheduling using Operating System algorithms:
  * First-Come, First-Served (**FCFS**)
  * Shortest Job First (**SJF**)
  * Round Robin (**RR**)
* **🔐 Access Control & Authentication:** Secure admin login sessions and user data access control.
* **💾 DBMS Integration:** Stores and organizes computer hardware info, running tasks, usage logs and maintenance records in a structured MySQL database.
  
## 🛠️️ Tech Stack

* **Backend:** Python, Flask[cite: 3]
* **Database:** MySQL[cite: 3]
* **System Monitoring:** `psutil`[cite: 2, 3]
* **Coursework Context:** OS  + DBMS 

## 📁 System Architecture

+-------------------------------------------------------------------+
|                     ADMINISTRATOR (User Persona)                  |
+-------------------------------------------------------------------+
                                  |
                                  v
                   +-----------------------------+
                   |     SMARTLAB WEB APP        |
                   |      (Python + Flask)       |
                   +-----------------------------+
                                  |
   +------------------+-----------+-----------+-------------------+
   |                  |                       |                   |
   v                  v                       v                   v
+------------+  +------------+          +------------+     +------------+
| Computer   |  | Resource   |          | Task       |     | User & Data|
| Management |  | Monitoring |          | Scheduling |     | Access     |
| Service    |  | Service    |          | Service    |     | Control    |
+------------+  +------------+          +------------+     +------------+
   | (Remote    | (CPU/RAM    | (FCFS/SJF | (Auth &       |
   |  Ops)      |  psutil)    |  Gantt)   |  Sessions)    |
   +------------+--+----------+-----------+---------------+
                   |
                   v
        +-----------------------+
        |   DATABASE LAYER      |
        |      (MySQL)          |
        +-----------------------+


## 🚀 Getting Started
### Prerequisites

* Python 3.x installed
* MySQL Server installed and running
