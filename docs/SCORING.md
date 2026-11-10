# Scoring

Class always sorts first (P0 > P1 > P2 > needs_review); the score orders listings within a class and picks the "★" reasons in alerts.
Weights and tables: `config/scoring.yaml`.

| Factor | Weight | Rule |
|---|---|---|
| Rooms | 40 | 3 → 100, 2.5 → 80, 2 → 60, 1.5 → 35, 1 → 20 |
| Size | 20 | m² / 90, capped |
| Rent headroom | 15 | € below the AV-Wohnen limit / 150, capped; unknown rent = 30 |
| Facilities | 15 | elevator, balcony/loggia/terrace, fitted kitchen, bath with window, district heating / floor heating |
| Location | 5 | preferred district = 100; neutral (no preference) = 50 |
| Availability | 5 | constant until the move-in window is configured |
