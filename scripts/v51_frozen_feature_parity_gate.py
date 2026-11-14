"""Verify frozen V51 feature definitions match the actual training generator."""
import json
from pathlib import Path
from scripts.jra_historical_horse_id_ablation import FEATURES, create_feature_rows, HistoricalStats

def validate(model="operations/prediction_policy/standard_v51_model.json"):
    m=json.loads(Path(model).read_text())
    if m["feature_names"]!=FEATURES or len(FEATURES)!=31:
        raise ValueError("FROZEN_V51_FEATURE_PARITY_FAILED")
    if len(m["feature_mean"])!=31 or len(m["feature_scale"])!=31:
        raise ValueError("FROZEN_V51_MODEL_SHAPE_INVALID")
    return {"feature_count":31,"source":"scripts/jra_historical_horse_id_ablation.py",
            "source_function":"create_feature_rows","frozen_feature_names_match":True}

if __name__=="__main__":
    print(json.dumps(validate()))
