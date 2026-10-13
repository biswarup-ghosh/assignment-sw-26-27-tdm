INSERT INTO season (name, start_date, end_date)
VALUES ('2026/2027', '2026-09-01', '2027-07-31');

INSERT INTO vehicle (name, generation)
VALUES ('RUP-EV-26', 'Gen 3');

INSERT INTO driver (full_name)
VALUES ('Marco Rossi'), ('Giulia Bianchi');

INSERT INTO track_location (name, country)
VALUES ('Test Area Padova', 'Italy');

INSERT INTO track_layout (track_location_id, name, activity_type, length_m)
VALUES (1, 'Autocross A', 'autocross', 800.0),
       (1, 'Endurance Loop', 'endurance', 1200.0);

INSERT INTO test (season_id, vehicle_id, track_location_id, test_date, status)
VALUES (1, 1, 1, '2026-10-12', 'done');

INSERT INTO run (test_id, driver_id, track_layout_id, ambient_temp_c, asphalt_temp_c, expected_laps, completed_laps)
VALUES (1, 1, 1, 22.5, 34.0, 3, 3),
       (1, 2, 2, 21.0, 31.5, 3, 3);

INSERT INTO lap (run_id, lap_number, lap_time_s)
VALUES (1, 1, 62.3), (1, 2, 61.8), (1, 3, 62.0),
       (2, 1, 95.1), (2, 2, 94.6), (2, 3, 94.9);