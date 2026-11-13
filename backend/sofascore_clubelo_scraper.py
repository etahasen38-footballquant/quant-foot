"""
QuantFoot Production ETL & Scraper Engine (Python 3.10+)
--------------------------------------------------------
1. ClubElo Resmi CSV API'den (http://api.clubelo.com/YYYY-MM-DD) Avrupa'nın tüm liglerindeki
   kulüplerin günlük Elo derecelerini çeker.
2. Sofascore JSON uç noktalarından (/api/v1/event/{event_id}/lineups) maç sonu oyuncu
   reytinglerini (1.0 - 10.0) ve mevki bazlı istatistikleri (xG, xA, dripling, top kapma, PSxG) çeker.
3. Tier 1..6 (1750 -> 1200) lig baz ofsetleri ve Anti-Farming (zayıf ligde aşırı şişmeyi önleme)
   formülleriyle maç sonu Takım Elo, Oyuncu Elo ve Sigmoidal DMV (Piyasa Değeri) güncellemesini yapar.
"""

import math
import time
import json
import urllib.request
from datetime import datetime, date
from dataclasses import dataclass
from typing import Dict, List, Optional

# Avrupa Lig Kademeleri (Tier 1 - Tier 6), Baz Elo ve Tek Maç Maksimum Değer Değişimi Tavanları
LEAGUE_TIERS: Dict[str, dict] = {
    # UEFA Kupaları (Yüksek Etki)
    "UCL_KO": {"name": "UEFA Champions League Knockout", "tier": 0, "base_elo": 1850, "w_comp": 1.65, "max_mv_clip": 0.0160},
    "UCL_LP": {"name": "UEFA Champions League League Phase", "tier": 0, "base_elo": 1800, "w_comp": 1.25, "max_mv_clip": 0.0110},
    "UEL":    {"name": "UEFA Europa League", "tier": 0, "base_elo": 1680, "w_comp": 0.85, "max_mv_clip": 0.0065},
    "UECL":   {"name": "UEFA Conference League", "tier": 0, "base_elo": 1580, "w_comp": 0.60, "max_mv_clip": 0.0045},
    # Tier 1: Top 5 Avrupa Ligi (Baz Elo: 1750)
    "ENG1":   {"name": "Premier League", "sofascore_id": 17, "tier": 1, "base_elo": 1750, "w_comp": 0.28, "max_mv_clip": 0.0022, "anti_farm_cap": 2150},
    "ESP1":   {"name": "LaLiga", "sofascore_id": 8, "tier": 1, "base_elo": 1750, "w_comp": 0.26, "max_mv_clip": 0.0020, "anti_farm_cap": 2150},
    "ITA1":   {"name": "Serie A", "sofascore_id": 23, "tier": 1, "base_elo": 1750, "w_comp": 0.26, "max_mv_clip": 0.0020, "anti_farm_cap": 2120},
    "GER1":   {"name": "Bundesliga", "sofascore_id": 35, "tier": 1, "base_elo": 1750, "w_comp": 0.26, "max_mv_clip": 0.0020, "anti_farm_cap": 2120},
    "FRA1":   {"name": "Ligue 1", "sofascore_id": 34, "tier": 1, "base_elo": 1720, "w_comp": 0.24, "max_mv_clip": 0.0018, "anti_farm_cap": 2080},
    # Tier 2: Avrupa #6 - #10 (Baz Elo: 1620)
    "POR1":   {"name": "Liga Portugal", "sofascore_id": 238, "tier": 2, "base_elo": 1620, "w_comp": 0.22, "max_mv_clip": 0.0016, "anti_farm_cap": 1940},
    "NED1":   {"name": "Eredivisie", "sofascore_id": 37, "tier": 2, "base_elo": 1620, "w_comp": 0.20, "max_mv_clip": 0.0015, "anti_farm_cap": 1920},
    "BEL1":   {"name": "Belgian Pro League", "sofascore_id": 38, "tier": 2, "base_elo": 1620, "w_comp": 0.20, "max_mv_clip": 0.0015, "anti_farm_cap": 1900},
    "TUR1":   {"name": "Trendyol Süper Lig", "sofascore_id": 52, "tier": 2, "base_elo": 1600, "w_comp": 0.20, "max_mv_clip": 0.0015, "anti_farm_cap": 1900},
    "CZE1":   {"name": "Chance Liga", "sofascore_id": 172, "tier": 2, "base_elo": 1580, "w_comp": 0.18, "max_mv_clip": 0.0014, "anti_farm_cap": 1860},
    # Tier 3: Avrupa #11 - #16 (Baz Elo: 1520)
    "GRE1":   {"name": "Stoiximan Super League", "sofascore_id": 185, "tier": 3, "base_elo": 1520, "w_comp": 0.16, "max_mv_clip": 0.0012, "anti_farm_cap": 1820},
    "NOR1":   {"name": "Eliteserien", "sofascore_id": 20, "tier": 3, "base_elo": 1520, "w_comp": 0.16, "max_mv_clip": 0.0012, "anti_farm_cap": 1820},
    "DEN1":   {"name": "Danish Superliga", "sofascore_id": 39, "tier": 3, "base_elo": 1520, "w_comp": 0.16, "max_mv_clip": 0.0012, "anti_farm_cap": 1800},
    "AUT1":   {"name": "Austrian Bundesliga", "sofascore_id": 45, "tier": 3, "base_elo": 1520, "w_comp": 0.16, "max_mv_clip": 0.0012, "anti_farm_cap": 1800},
    "SCO1":   {"name": "Scottish Premiership", "sofascore_id": 36, "tier": 3, "base_elo": 1500, "w_comp": 0.15, "max_mv_clip": 0.0012, "anti_farm_cap": 1790},
    # Tier 4-6: Doğu & Kuzey Avrupa (Baz Elo: 1250 - 1450)
    "CRO1":   {"name": "HNL Croatia", "sofascore_id": 170, "tier": 4, "base_elo": 1450, "w_comp": 0.14, "max_mv_clip": 0.0010, "anti_farm_cap": 1740},
    "FIN1":   {"name": "Veikkausliiga", "sofascore_id": 41, "tier": 5, "base_elo": 1350, "w_comp": 0.12, "max_mv_clip": 0.0008, "anti_farm_cap": 1620},
    "EST1":   {"name": "Meistriliiga", "sofascore_id": 212, "tier": 6, "base_elo": 1220, "w_comp": 0.10, "max_mv_clip": 0.0006, "anti_farm_cap": 1480},
}


class ClubEloClient:
    """ClubElo resmi CSV API istemcisi (http://api.clubelo.com/YYYY-MM-DD)."""

    @staticmethod
    def fetch_daily_rankings(target_date: Optional[str] = None) -> List[dict]:
        dt = target_date or date.today().strftime("%Y-%m-%d")
        url = f"http://api.clubelo.com/{dt}"
        req = urllib.request.Request(url, headers={"User-Agent": "QuantFoot-ETL/4.0"})
        clubs = []
        with urllib.request.urlopen(req, timeout=15) as resp:
            lines = resp.read().decode("utf-8", errors="replace").splitlines()
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) >= 5 and parts[0].strip():
                    clubs.append({
                        "rank": int(parts[0]) if parts[0].isdigit() else None,
                        "club": parts[1].strip(),
                        "country": parts[2].strip(),
                        "level": int(parts[3]) if parts[3].isdigit() else 1,
                        "elo": float(parts[4]),
                    })
        return clubs


class SofascoreMatchExtractor:
    """Sofascore JSON uç noktalarından maç kadrolarını ve oyuncu reytinglerini (1.0-10.0) çeker."""

    BASE_URL = "https://www.sofascore.com/api/v1"

    @classmethod
    def fetch_match_lineups_and_ratings(cls, event_id: int) -> dict:
        url = f"{cls.BASE_URL}/event/{event_id}/lineups"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return cls.parse_lineup_payload(data, event_id)

    @staticmethod
    def parse_lineup_payload(payload: dict, event_id: int) -> dict:
        parsed_players = []
        for side in ("home", "away"):
            side_block = payload.get(side, {})
            for entry in side_block.get("players", []):
                p_info = entry.get("player", {})
                stats = entry.get("statistics", {})
                rating = stats.get("rating")
                minutes = stats.get("minutesPlayed", 0)
                if rating is None or minutes <= 0:
                    continue
                parsed_players.append({
                    "event_id": event_id,
                    "side": side,
                    "sofascore_player_id": p_info.get("id"),
                    "name": p_info.get("name"),
                    "position": entry.get("position") or p_info.get("position", "CM"),
                    "minutes_played": int(minutes),
                    "sofascore_rating": float(rating),
                    "goals": int(stats.get("goals", 0)),
                    "assists": int(stats.get("goalAssist", 0)),
                    "expected_goals": float(stats.get("expectedGoals", 0.0)),
                    "expected_assists": float(stats.get("expectedAssists", 0.0)),
                    "key_passes": int(stats.get("keyPass", 0)),
                    "successful_dribbles": int(stats.get("wonContest", 0)),
                    "tackles_won": int(stats.get("totalTackle", 0)),
                    "interceptions": int(stats.get("interceptionWon", 0)),
                    "saves": int(stats.get("saves", 0)),
                    "goals_prevented": float(stats.get("goalsPrevented", 0.0)),
                })
        return {"event_id": event_id, "players": parsed_players}


class QuantFootValuationEngine:
    """
    Mevki bazlı Sofascore/Mackolik reytinglerinden (1.0 - 10.0) Elo ve Sigmoidal DMV hesaplar.
    Sıradan ulusal lig maçlarını ±%0.14 - ±%0.22 ile sınırlar; UCL maçlarına ±%1.60 tavan tanır.
    """

    V_CEILING = 235_000_000  # Küresel Sigmoidal Tavan (235M €)

    @staticmethod
    def expected_rating(player_elo: float, opp_team_elo: float) -> float:
        return max(6.45, min(7.40, 6.80 + 0.35 * math.tanh((player_elo - opp_team_elo) / 280.0)))

    @classmethod
    def update_player_after_match(
        cls,
        player_elo: float,
        current_mv_eur: int,
        age: float,
        sofascore_rating: float,
        minutes: int,
        opp_team_elo: float,
        team_score_s: float,
        team_expected_e: float,
        comp_code: str,
        alpha_pos: float = 0.25,
    ) -> dict:
        comp = LEAGUE_TIERS.get(comp_code, LEAGUE_TIERS["ENG1"])
        r_exp = cls.expected_rating(player_elo, opp_team_elo)
        r_diff = sofascore_rating - r_exp
        tau = (min(minutes, 90) / 90.0) ** 0.75

        # Anti-farming kontrolü: Zayıf ligde kendi lig tavanını aşan oyuncu/takım için pozitif kazanç sönümlenir
        anti_farm_cap = comp.get("anti_farm_cap", 2200)
        anti_farm_mult = 1.0
        if comp.get("tier", 0) >= 2 and player_elo > anti_farm_cap and r_diff > 0:
            anti_farm_mult = max(0.15, math.exp(-(player_elo - anti_farm_cap) / 80.0))

        perf_signal = tau * anti_farm_mult * ((1.0 - alpha_pos) * (r_diff / 2.2) + alpha_pos * (team_score_s - team_expected_e))
        delta_elo = round(14.0 * comp["w_comp"] * perf_signal, 2)

        age_sens = 1.15 if age < 23.0 else (0.75 if age > 30.0 else 1.00)
        max_clip = comp["max_mv_clip"]
        raw_pct = perf_signal * max_clip * age_sens
        clipped_pct = max(-max_clip, min(max_clip, raw_pct))

        delta_mv = int(round(current_mv_eur * clipped_pct))
        new_mv = min(225_000_000, max(100_000, current_mv_eur + delta_mv))

        return {
            "expected_rating": round(r_exp, 2),
            "actual_rating": round(sofascore_rating, 2),
            "elo_before": player_elo,
            "elo_after": round(player_elo + delta_elo, 2),
            "elo_delta": delta_elo,
            "mv_before_eur": current_mv_eur,
            "mv_after_eur": new_mv,
            "mv_delta_eur": new_mv - current_mv_eur,
            "pct_change": round(clipped_pct * 100, 3),
        }


if __name__ == "__main__":
    print("QuantFoot ETL Engine Hazır. Örnek Maç Sonu Değer Güncellemesi:")
    sample_lig = QuantFootValuationEngine.update_player_after_match(
        player_elo=1988, current_mv_eur=198_000_000, age=27.9,
        sofascore_rating=7.90, minutes=90, opp_team_elo=1780,
        team_score_s=0.85, team_expected_e=0.76, comp_code="ESP1"
    )
    sample_ucl = QuantFootValuationEngine.update_player_after_match(
        player_elo=1988, current_mv_eur=198_000_000, age=27.9,
        sofascore_rating=9.10, minutes=90, opp_team_elo=2046,
        team_score_s=0.90, team_expected_e=0.45, comp_code="UCL_KO"
    )
    print("1) Sıradan LaLiga Maçı (7.90 Reyting):", json.dumps(sample_lig, indent=2))
    print("2) UCL Çeyrek Final Maçı (9.10 Reyting):", json.dumps(sample_ucl, indent=2))
