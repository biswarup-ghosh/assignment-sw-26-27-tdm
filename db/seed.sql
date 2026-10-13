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

INSERT INTO tyre_compound (name, supplier)
VALUES ('Soft', 'Hoosier'), ('Medium', 'Hoosier');

INSERT INTO tyre_set (compound_id, code)
VALUES (1, 'SET-001'), (2, 'SET-002');

INSERT INTO test (season_id, vehicle_id, track_location_id, test_date, status)
VALUES (1, 1, 1, '2026-10-12', 'done');

INSERT INTO run (test_id, driver_id, track_layout_id, tyre_set_id,
                 ambient_temp_c, asphalt_temp_c, expected_laps, completed_laps)
VALUES (1, 1, 1, 1, 22.5, 34.0, 3, 3),
       (1, 2, 2, 2, 21.0, 31.5, 3, 3);

INSERT INTO lap (run_id, lap_number, lap_time_s)
VALUES (1, 1, 62.3), (1, 2, 61.8), (1, 3, 62.0),
       (2, 1, 95.1), (2, 2, 94.6), (2, 3, 94.9);

INSERT INTO tyre_measurement
    (run_id, phase, corner, pressure_kpa, temp_outer_c, temp_center_c, temp_inner_c)
VALUES
    (1, 'pre',  'FL', 85.0, 24.0, 24.0, 24.0),
    (1, 'pre',  'FR', 85.0, 24.0, 24.0, 24.0),
    (1, 'pre',  'RL', 80.0, 24.0, 24.0, 24.0),
    (1, 'pre',  'RR', 80.0, 24.0, 24.0, 24.0),
    (1, 'post', 'FL', 98.0, 62.0, 66.0, 70.0),
    (1, 'post', 'FR', 99.0, 71.0, 67.0, 63.0),
    (1, 'post', 'RL', 92.0, 60.0, 64.0, 66.0),
    (1, 'post', 'RR', 93.0, 65.0, 63.0, 59.0);