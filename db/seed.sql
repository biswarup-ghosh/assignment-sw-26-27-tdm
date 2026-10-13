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

-- Parameter catalogue. Ids are assigned in this order:
-- 1 spring, 2 damper comp, 3 damper reb, 4 ARB front, 5 ARB rear, 6 camber,
-- 7 toe, 8 corner weight, 9 shim, 10 power limit, 11 TV gain, 12 max rpm
INSERT INTO setup_parameter (code, name, category, scope, unit)
VALUES ('spring_rate_n_mm',          'Spring rate',            'suspension', 'corner',  'N/mm'),
       ('damper_compression_clicks', 'Damper compression',     'suspension', 'corner',  'clicks'),
       ('damper_rebound_clicks',     'Damper rebound',         'suspension', 'corner',  'clicks'),
       ('arb_front_position',        'Front ARB position',     'suspension', 'vehicle', 'notch'),
       ('arb_rear_position',         'Rear ARB position',      'suspension', 'vehicle', 'notch'),
       ('camber_static_deg',         'Static camber',          'alignment',  'corner',  'deg'),
       ('toe_static_deg',            'Static toe',             'alignment',  'corner',  'deg'),
       ('corner_weight_kg',          'Corner weight',          'weight',     'corner',  'kg'),
       ('shim_thickness_mm',         'Shim thickness',         'suspension', 'corner',  'mm'),
       ('power_limit_kw',            'Power limit',            'control',    'vehicle', 'kW'),
       ('torque_vectoring_gain',     'Torque vectoring gain',  'control',    'vehicle', 'ratio'),
       ('max_rpm',                   'Maximum motor speed',    'control',    'vehicle', 'rpm');

INSERT INTO setup (vehicle_id, name, based_on_setup_id, change_reason, created_at)
VALUES (1, 'Baseline', NULL, 'Initial setup of the season', '2026-10-12 09:00:00'),
       (1, 'Stiffer front', 1,
           'Understeer in slow corners: stiffer front springs, more front camber, higher power limit',
           '2026-10-12 11:30:00');

-- Seeded values use parameters 1 (spring), 4 (front ARB), 6 (camber), 10 (power limit)
INSERT INTO setup_value (setup_id, parameter_id, corner, value)
VALUES (1, 1, 'FL', 40),   (1, 1, 'FR', 40),   (1, 1, 'RL', 50),   (1, 1, 'RR', 50),
       (1, 6, 'FL', -2.0), (1, 6, 'FR', -2.0), (1, 6, 'RL', -1.5), (1, 6, 'RR', -1.5),
       (1, 4, 'VEH', 3),   (1, 10, 'VEH', 60),
       (2, 1, 'FL', 45),   (2, 1, 'FR', 45),   (2, 1, 'RL', 50),   (2, 1, 'RR', 50),
       (2, 6, 'FL', -2.5), (2, 6, 'FR', -2.5), (2, 6, 'RL', -1.5), (2, 6, 'RR', -1.5),
       (2, 4, 'VEH', 3),   (2, 10, 'VEH', 80);

INSERT INTO test (season_id, vehicle_id, track_location_id, test_date, status)
VALUES (1, 1, 1, '2026-10-12', 'done');

INSERT INTO run (test_id, run_number, driver_id, track_layout_id, tyre_set_id, setup_id,
                 ambient_temp_c, asphalt_temp_c, expected_laps, completed_laps)
VALUES (1, 1, 1, 1, 1, 1, 22.5, 34.0, 3, 3),
       (1, 2, 2, 2, 2, 2, 21.0, 31.5, 3, 3);

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

INSERT INTO alignment_measurement (run_id, phase, corner, camber_deg, toe_deg)
VALUES (1, 'pre', 'FL', -2.0, 0.10), (1, 'pre', 'FR', -1.9, 0.10),
       (1, 'pre', 'RL', -1.5, 0.20), (1, 'pre', 'RR', -1.5, 0.20),
       (2, 'pre', 'FL', -2.4, 0.10), (2, 'pre', 'FR', -2.5, 0.10),
       (2, 'pre', 'RL', -1.5, 0.20), (2, 'pre', 'RR', -1.4, 0.20);