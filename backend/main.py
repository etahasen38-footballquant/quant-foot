"""
QuantFoot FastAPI Production Backend + Otomatik Maç Sonu Cron Servisi
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sofascore_clubelo_scraper import LEAGUE_TIERS, ClubEloClient, SofascoreMatchExtractor, QuantFootValuationEngine

app = FastAPI(title="QuantFoot API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MatchUpdateRequest(BaseModel):
    player_elo: float
    current_mv_eur: int
    age: float
    sofascore_rating: float
    minutes: int = 90
    opp_team_elo: float = 1850.0
    team_score_s: float = 0.75
    team_expected_e: float = 0.50
    comp_code: str = "ENG1"


@app.get("/api/leagues")
def list_leagues():
    return LEAGUE_TIERS


@app.post("/api/valuation/post-match")
def calculate_post_match_valuation(req: MatchUpdateRequest):
    return QuantFootValuationEngine.update_player_after_match(
        player_elo=req.player_elo,
        current_mv_eur=req.current_mv_eur,
        age=req.age,
        sofascore_rating=req.sofascore_rating,
        minutes=req.minutes,
        opp_team_elo=req.opp_team_elo,
        team_score_s=req.team_score_s,
        team_expected_e=req.team_expected_e,
        comp_code=req.comp_code,
    )


@app.get("/api/scrape/sofascore-match/{event_id}")
def scrape_sofascore_event(event_id: int):
    try:
        return SofascoreMatchExtractor.fetch_match_lineups_and_ratings(event_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
