"""Research feature gate: historical uplift is insufficient for live deployment."""
from dataclasses import dataclass
from typing import Optional
RESEARCH_DEFAULT='jockey_track_win'
REQUIRED_FEATURES=('jockey_track_starts','jockey_track_top3_rate','jockey_track_win_rate')
@dataclass(frozen=True)
class PreoffProof:
    racecard_sha256: Optional[str]
    observed_at: Optional[str]
    model_sha256: Optional[str]
    all_runners_verified: bool
    feature_history_embargo_days: int
    future_trial_count: int
    independent_future_improvement_verified: bool
def can_activate_live(proof: PreoffProof):
    missing=[]
    if not proof.racecard_sha256 or len(proof.racecard_sha256)!=64: missing.append('発走前出馬表SHA256なし')
    if not proof.observed_at or '+' not in proof.observed_at: missing.append('発走前観測時刻未検証')
    if not proof.model_sha256 or len(proof.model_sha256)!=64: missing.append('モデルSHA256なし')
    if not proof.all_runners_verified: missing.append('全頭未確認')
    if proof.feature_history_embargo_days<7: missing.append('走歴隔離期間不足')
    if proof.future_trial_count<=0 or not proof.independent_future_improvement_verified: missing.append('独立将来検証で改善未確認')
    return not missing,tuple(missing)
