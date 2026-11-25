
USE smartlab_db;

-- ---------------------------------------------------------------------
-- LABS (3)
-- ---------------------------------------------------------------------
INSERT INTO labs (lab_id, lab_name, location, capacity, status) VALUES
('LAB-01', 'CSE Lab 1', 'Block A - Ground Floor', 40, 'Active'),
('LAB-02', 'CSE Lab 2', 'Block A - First Floor', 40, 'Active'),
('LAB-03', 'CSE Lab 3', 'Block B - Second Floor', 30, 'Active');

-- ---------------------------------------------------------------------
-- COMPUTERS (18)
-- ---------------------------------------------------------------------
INSERT INTO computers (computer_id, lab_id, ip_address, processor, ram_gb, storage_gb, os_name, status) VALUES
('PC-01','LAB-01','192.168.1.101','Intel i5-10400',8,512,'Windows 11','Available'),
('PC-02','LAB-01','192.168.1.102','Intel i5-10400',8,512,'Windows 11','Available'),
('PC-03','LAB-01','192.168.1.103','Intel i5-10400',8,512,'Windows 11','Available'),
('PC-04','LAB-01','192.168.1.104','Intel i5-10400',8,512,'Windows 11','Under Maintenance'),
('PC-05','LAB-01','192.168.1.105','Intel i5-10400',8,512,'Windows 11','Available'),
('PC-06','LAB-01','192.168.1.106','Intel i5-10400',8,512,'Windows 11','Available'),
('PC-07','LAB-02','192.168.2.101','Intel i5-9400',8,256,'Windows 10','Under Maintenance'),
('PC-08','LAB-02','192.168.2.102','Intel i5-9400',8,256,'Windows 10','Maintenance Required'),
('PC-09','LAB-02','192.168.2.103','Intel i5-9400',8,256,'Windows 10','Available'),
('PC-10','LAB-02','192.168.2.104','Intel i5-9400',8,256,'Windows 10','Under Maintenance'),
('PC-11','LAB-02','192.168.2.105','Intel i5-9400',8,256,'Windows 10','Available'),
('PC-12','LAB-02','192.168.2.106','Intel i5-9400',8,256,'Windows 10','Available'),
('PC-13','LAB-03','192.168.3.101','Intel i3-10100',4,256,'Windows 10','Maintenance Required'),
('PC-14','LAB-03','192.168.3.102','Intel i3-10100',4,256,'Windows 10','Available'),
('PC-15','LAB-03','192.168.3.103','Intel i3-10100',4,256,'Windows 10','Available'),
('PC-16','LAB-03','192.168.3.104','Intel i3-10100',4,256,'Windows 10','Maintenance Required'),
('PC-17','LAB-03','192.168.3.105','Intel i3-10100',4,256,'Windows 10','Available'),
('PC-18','LAB-03','192.168.3.106','Intel i3-10100',4,256,'Windows 10','Offline');

-- ---------------------------------------------------------------------
-- TECHNICIANS (4)
-- ---------------------------------------------------------------------
INSERT INTO technicians (name, specialization, availability, contact) VALUES
('Ramesh Kumar', 'Hardware', 'Busy', '9990001111'),
('Sunita Verma', 'Software', 'Busy', '9990002222'),
('Arjun Rao', 'Networking', 'Busy', '9990003333'),
('Priya Nair', 'General', 'Available', '9990004444');

-- ---------------------------------------------------------------------
-- RESOURCES (6 types) -- available_quantity starts equal to total;
-- the resource_allocations inserts below will trigger automatic
-- decrement to the correct "currently available" figures.
-- ---------------------------------------------------------------------
INSERT INTO resources (resource_name, resource_type, total_quantity, available_quantity, status) VALUES
('Lab Technician Pool',   'Technician',          4, 4, 'Active'),   -- resource_id 1
('RAM Module 8GB',        'RAM',                 3, 3, 'Active'),   -- resource_id 2
('Network Cable Tester',  'Network Tester',      2, 2, 'Active'),   -- resource_id 3
('Standard Keyboard',     'Keyboard',            3, 3, 'Active'),   -- resource_id 4
('Optical Mouse',         'Mouse',               3, 3, 'Active'),   -- resource_id 5
('Windows 10/11 OS Kit',  'OS Installation Kit', 1, 1, 'Active');   -- resource_id 6

-- ---------------------------------------------------------------------
-- MAINTENANCE REQUESTS (8)
-- ---------------------------------------------------------------------
INSERT INTO maintenance_requests (request_id, computer_id, problem_description, fault_type, severity, status) VALUES
(1, 'PC-04', 'System failed to boot into OS after Windows update.', 'Software', 'Critical', 'Converted to Task'),
(2, 'PC-07', 'No network connectivity, LAN port possibly faulty.', 'Network', 'High', 'Converted to Task'),
(3, 'PC-10', 'RAM errors causing frequent blue screens.', 'Hardware', 'Medium', 'Converted to Task'),
(4, 'PC-13', 'Several keys on the keyboard are unresponsive.', 'Peripheral', 'Low', 'Converted to Task'),
(5, 'PC-16', 'Needs fresh OS + lab software suite installation.', 'Software', 'Low', 'Converted to Task'),
(6, 'PC-08', 'Screen flickers intermittently, mouse also unresponsive.', 'Peripheral', 'Medium', 'Converted to Task'),
(7, 'PC-04', 'Previous OS corruption issue (resolved).', 'Software', 'Critical', 'Closed'),
(8, 'PC-10', 'Previous RAM upgrade request (resolved).', 'Hardware', 'Medium', 'Closed');

-- ---------------------------------------------------------------------
-- MAINTENANCE TASKS
-- Active/pending demo set: J-101..J-106 (feeds scheduling + resource demo)
-- Historical/completed set: J-090, J-091 (feeds maintenance history page)
-- ---------------------------------------------------------------------
INSERT INTO maintenance_tasks
 (task_id, request_id, computer_id, arrival_time, service_time, priority, status, technician_id, started_at, completion_time, completed_at) VALUES
('J-101', 1, 'PC-04',  0, 40, 1, 'Waiting for Resource',1, NULL, NULL, NULL),
('J-102', 2, 'PC-07',  5, 20, 2, 'Waiting for Resource',3, NULL, NULL, NULL),
('J-103', 3, 'PC-10', 10, 25, 3, 'Waiting for Resource',1, NULL, NULL, NULL),
('J-104', 4, 'PC-13', 15, 10, 4, 'Pending',             NULL, NULL, NULL, NULL),
('J-105', 5, 'PC-16', 20, 15, 4, 'Pending',             NULL, NULL, NULL, NULL),
('J-106', 6, 'PC-08', 25, 30, 3, 'Pending',             NULL, NULL, NULL, NULL);

INSERT INTO maintenance_tasks
 (task_id, request_id, computer_id, arrival_time, service_time, priority, status, technician_id, started_at, completion_time, completed_at) VALUES
('J-090', 7, 'PC-04', 0, 35, 1, 'Completed', 2, '2026-08-10 09:00:00', 35, '2026-08-10 09:35:00'),
('J-091', 8, 'PC-10', 0, 25, 3, 'Completed', 1, '2026-08-22 11:00:00', 25, '2026-08-22 11:25:00');

-- ---------------------------------------------------------------------
-- TASK_RESOURCES (maximum requirement per task)
-- ---------------------------------------------------------------------
INSERT INTO task_resources (task_id, resource_id, maximum_required, currently_allocated) VALUES
('J-101', 1, 3, 1),   -- Technician: max 3, currently 1  -> need 2
('J-101', 3, 2, 1),   -- Network Tester: max 2, currently 1 -> need 1
('J-102', 1, 2, 1),   -- Technician: max 2, currently 1 -> need 1
('J-102', 2, 1, 1),   -- RAM: max 1, currently 1 -> need 0
('J-103', 1, 2, 1),   -- Technician: max 2, currently 1 -> need 1
('J-103', 2, 2, 1),   -- RAM: max 2, currently 1 -> need 1
('J-103', 3, 1, 1),   -- Network Tester: max 1, currently 1 -> need 0
('J-104', 1, 1, 0),   -- Technician: max 1, currently 0 -> need 1
('J-104', 2, 1, 0),   -- RAM: max 1, currently 0 -> need 1
('J-104', 3, 1, 0),   -- Network Tester: max 1, currently 0 -> need 1
('J-105', 4, 1, 0),   -- Keyboard: max 1
('J-106', 5, 1, 0),   -- Mouse: max 1
('J-106', 6, 1, 0);   -- OS Installation Kit: max 1

-- ---------------------------------------------------------------------
-- RESOURCE_ALLOCATIONS (already-allocated portions; triggers will
-- automatically decrement resources.available_quantity)
-- ---------------------------------------------------------------------
INSERT INTO resource_allocations (task_id, resource_id, quantity, status) VALUES
('J-101', 1, 1, 'Allocated'),   -- Technician x1 to J-101
('J-101', 3, 1, 'Allocated'),   -- Network Tester x1 to J-101
('J-102', 1, 1, 'Allocated'),   -- Technician x1 to J-102
('J-102', 2, 1, 'Allocated'),   -- RAM x1 to J-102
('J-103', 1, 1, 'Allocated'),   -- Technician x1 to J-103
('J-103', 2, 1, 'Allocated'),   -- RAM x1 to J-103
('J-103', 3, 1, 'Allocated');   -- Network Tester x1 to J-103

-- After the above inserts (and triggers), resources table reflects:
--   Technician        : total 4, allocated 3 -> available 1
--   RAM Module 8GB    : total 3, allocated 2 -> available 1
--   Network Cable Tst : total 2, allocated 2 -> available 0
--   Keyboard/Mouse/OSKit: untouched, fully available

-- ---------------------------------------------------------------------
-- HISTORICAL RESOURCE ALLOCATIONS (released, for completed tasks)
-- ---------------------------------------------------------------------
INSERT INTO resource_allocations (task_id, resource_id, quantity, status, allocated_at, released_at) VALUES
('J-090', 1, 1, 'Released', '2026-08-10 09:00:00', '2026-08-10 09:35:00'),
('J-091', 1, 1, 'Released', '2026-08-22 11:00:00', '2026-08-22 11:25:00'),
('J-091', 2, 1, 'Released', '2026-08-22 11:00:00', '2026-08-22 11:25:00');

-- ---------------------------------------------------------------------
-- MAINTENANCE HISTORY (for completed tasks)
-- ---------------------------------------------------------------------
INSERT INTO maintenance_history (task_id, computer_id, technician_id, started_at, completed_at, remarks, resources_used) VALUES
('J-090', 'PC-04', 2, '2026-08-10 09:00:00', '2026-08-10 09:35:00',
 'Reinstalled OS and restored user profile. System boots normally.', 'Technician x1'),
('J-091', 'PC-10', 1, '2026-08-22 11:00:00', '2026-08-22 11:25:00',
 'Replaced faulty RAM module, ran memory diagnostic - passed.', 'Technician x1, RAM Module 8GB x1');
