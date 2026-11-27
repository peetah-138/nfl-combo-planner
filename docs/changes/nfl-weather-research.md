# NFL weather research (research only)

Adds `tools/research/nfl_weather.py`: offline study of whether observed kickoff weather (wind, cold, rain/snow; dome excluded) beats Kalshi NFL total/yards/points/field-goal prices after fees. Uses public key-free endpoints only (Kalshi market data, Iowa Environmental Mesonet), at most 1 request/s. Not imported by the planner and nothing in the trading path.

Result (local, ~/dev/research/nfl-weather/RESULT.md): no pass. Wind lowers totals about 2 points in 20 seasons of data, but the sportsbook line already prices much of it, and the Kalshi era has too few bad-weather games (3 to 17 per type in the test window) to show an edge net of fees. All market types INCONCLUSIVE. Shadow-recording list is in RESULT.md.
