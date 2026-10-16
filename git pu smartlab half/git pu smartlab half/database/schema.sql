
DROP DATABASE IF EXISTS smartlab_db;
CREATE DATABASE smartlab_db;
USE smartlab_db;

CREATE TABLE labs (
    lab_id       VARCHAR(10)  PRIMARY KEY,
    lab_name     VARCHAR(100) NOT NULL,
    location     VARCHAR(100) NOT NULL,
    capacity     INT          NOT NULL CHECK (capacity >= 0),
    status       ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE computers (
    computer_id  VARCHAR(10)  PRIMARY KEY,
    lab_id       VARCHAR(10)  NOT NULL,
    ip_address   VARCHAR(45),
    processor    VARCHAR(100),
    ram_gb       INT          CHECK (ram_gb >= 0),
    storage_gb   INT          CHECK (storage_gb >= 0),
    os_name      VARCHAR(50),
    status       ENUM('Available','In Use','Maintenance Required',
                       'Under Maintenance','Offline') NOT NULL DEFAULT 'Available',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lab_id) REFERENCES labs(lab_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
);


CREATE TABLE maintenance_requests (
    request_id   INT AUTO_INCREMENT PRIMARY KEY,
    computer_id  VARCHAR(10) NOT NULL,
    problem_description TEXT NOT NULL,
    fault_type   ENUM('Hardware','Software','Network','Performance','Peripheral','Other') NOT NULL,
    severity     ENUM('Critical','High','Medium','Low') NOT NULL,
    reported_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status       ENUM('Pending Review','Approved','Rejected','Converted to Task','Closed')
                 NOT NULL DEFAULT 'Pending Review',
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE maintenance_tasks (
    task_id         VARCHAR(15) PRIMARY KEY,   
    request_id      INT NOT NULL,
    computer_id     VARCHAR(10) NOT NULL,
    arrival_time    INT NOT NULL,               
    service_time    INT NOT NULL CHECK (service_time > 0),   
    priority        INT NOT NULL CHECK (priority BETWEEN 1 AND 4), 
    status          ENUM('Pending','Scheduled','Waiting for Resource',
                          'Resources Allocated','In Progress','Completed','Cancelled')
                    NOT NULL DEFAULT 'Pending',
    technician_id   INT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at      TIMESTAMP NULL,
    completion_time INT NULL,                  
    completed_at    TIMESTAMP NULL,
    FOREIGN KEY (request_id) REFERENCES maintenance_requests(request_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE technicians (
    technician_id  INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    specialization ENUM('Hardware','Software','Networking','General') NOT NULL,
    availability   ENUM('Available','Busy','Off Duty') NOT NULL DEFAULT 'Available',
    contact        VARCHAR(30)
);

ALTER TABLE maintenance_tasks
    ADD CONSTRAINT fk_task_technician
    FOREIGN KEY (technician_id) REFERENCES technicians(technician_id)
    ON DELETE SET NULL ON UPDATE CASCADE;

CREATE TABLE resources (
    resource_id        INT AUTO_INCREMENT PRIMARY KEY,
    resource_name       VARCHAR(100) NOT NULL,
    resource_type       ENUM('Technician','RAM','Keyboard','Mouse','Network Tester',
                              'OS Installation Kit','Other') NOT NULL,
    total_quantity      INT NOT NULL CHECK (total_quantity >= 0),
    available_quantity  INT NOT NULL CHECK (available_quantity >= 0),
    status              ENUM('Active','Retired') NOT NULL DEFAULT 'Active',
    CHECK (available_quantity <= total_quantity)
);

CREATE TABLE task_resources (
    task_id             VARCHAR(15) NOT NULL,
    resource_id         INT NOT NULL,
    maximum_required    INT NOT NULL CHECK (maximum_required > 0),
    currently_allocated INT NOT NULL DEFAULT 0 CHECK (currently_allocated >= 0),
    PRIMARY KEY (task_id, resource_id),
    FOREIGN KEY (task_id) REFERENCES maintenance_tasks(task_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (resource_id) REFERENCES resources(resource_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CHECK (currently_allocated <= maximum_required)
);

CREATE TABLE resource_allocations (
    allocation_id  INT AUTO_INCREMENT PRIMARY KEY,
    task_id        VARCHAR(15) NOT NULL,
    resource_id    INT NOT NULL,
    quantity       INT NOT NULL CHECK (quantity > 0),
    allocated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    released_at    TIMESTAMP NULL,
    status         ENUM('Allocated','Released') NOT NULL DEFAULT 'Allocated',
    FOREIGN KEY (task_id) REFERENCES maintenance_tasks(task_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (resource_id) REFERENCES resources(resource_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE maintenance_history (
    history_id     INT AUTO_INCREMENT PRIMARY KEY,
    task_id        VARCHAR(15) NOT NULL,
    computer_id    VARCHAR(10) NOT NULL,
    technician_id  INT NULL,
    started_at     TIMESTAMP NULL,
    completed_at   TIMESTAMP NULL,
    remarks        TEXT,
    resources_used TEXT,           
    FOREIGN KEY (task_id) REFERENCES maintenance_tasks(task_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (computer_id) REFERENCES computers(computer_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (technician_id) REFERENCES technicians(technician_id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(30)  NOT NULL UNIQUE,
    full_name      VARCHAR(100) NULL,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at  TIMESTAMP NULL
);

CREATE INDEX idx_computers_lab            ON computers(lab_id);
CREATE INDEX idx_requests_computer        ON maintenance_requests(computer_id);
CREATE INDEX idx_requests_status          ON maintenance_requests(status);
CREATE INDEX idx_tasks_status             ON maintenance_tasks(status);
CREATE INDEX idx_tasks_computer           ON maintenance_tasks(computer_id);
CREATE INDEX idx_allocations_task         ON resource_allocations(task_id);
CREATE INDEX idx_history_computer         ON maintenance_history(computer_id);


DELIMITER $$

CREATE TRIGGER trg_after_allocation_insert
AFTER INSERT ON resource_allocations
FOR EACH ROW
BEGIN
    IF NEW.status = 'Allocated' THEN
        UPDATE resources
        SET available_quantity = available_quantity - NEW.quantity
        WHERE resource_id = NEW.resource_id;
    END IF;
END$$


CREATE TRIGGER trg_after_allocation_release
AFTER UPDATE ON resource_allocations
FOR EACH ROW
BEGIN
    IF NEW.status = 'Released' AND OLD.status = 'Allocated' THEN
        UPDATE resources
        SET available_quantity = available_quantity + NEW.quantity
        WHERE resource_id = NEW.resource_id;
    END IF;
END$$

CREATE TRIGGER trg_after_task_completed
AFTER UPDATE ON maintenance_tasks
FOR EACH ROW
BEGIN
    IF NEW.status = 'Completed' AND OLD.status <> 'Completed' THEN
        UPDATE computers
        SET status = 'Available'
        WHERE computer_id = NEW.computer_id;
    END IF;
END$$

DELIMITER ;
