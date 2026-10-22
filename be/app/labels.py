LABELS = [
    {"value": 1, "name": "spinal_cord", "group": "cord", "color": "#E8D44D"},
    {"value": 2, "name": "spinal_canal", "group": "canal", "color": "#4A90C2"},
]

for value, name in [
    *[(11 + i, f"vertebrae_C{i + 1}") for i in range(7)],
    *[(21 + i, f"vertebrae_T{i + 1}") for i in range(12)],
    *[(41 + i, f"vertebrae_L{i + 1}") for i in range(6)],
    (50, "sacrum"),
]:
    LABELS.append({"value": value, "name": name, "group": "vertebra", "color": "#8E6BBF"})

for value, name in [
    *[(63 + i, f"disc_C{i + 2}_C{i + 3}") for i in range(5)],
    (71, "disc_C7_T1"),
    *[(72 + i, f"disc_T{i + 1}_T{i + 2}") for i in range(11)],
    (91, "disc_T12_L1"), (92, "disc_L1_L2"), (93, "disc_L2_L3"),
    (94, "disc_L3_L4"), (95, "disc_L4_L5"), (96, "disc_L5_L6"), (100, "disc_L5_S1"),
]:
    LABELS.append({"value": value, "name": name, "group": "disc", "color": "#2BB5C0"})

LABELS.sort(key=lambda x: x["value"])
