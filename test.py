import nflreadpy as nfl

stats = nfl.load_player_stats([2023, 2024, 2025, 2026], summary_level="reg").to_pandas()

gibbs = stats[stats["player_display_name"] == "Jahmyr Gibbs"]
print(gibbs[["season", "games", "carries", "rushing_yards", "rushing_tds", "receptions", "receiving_yards", "receiving_tds"]].to_string(index=False))
