"""Experimental rank shadow forecasts using actually observed history only."""
import argparse
import datetime as dt
import json
from pathlib import Path
from completion_validation import sha
from enriched_features import load_observed_enriched, history_index, build_enriched
from features import timestamp
from ranking_model import RankModel, augment, picks, joint_distribution
from exact_rank_model import ExactRankTree, exact_set
from strategy import validate_field
from validation import Ledger, canonical
from preoff_snapshot import audit_snapshot
from rank_calibration import mix_joint, validate_artifact
from confidence_calibration import alpha_for


def forecast(db, rows, model_path, selection_path, calibration_path=None):
    artifact = json.loads(Path(model_path).read_text())
    selected = json.loads(Path(selection_path).read_text())
    if sha(model_path) != selected['model_sha256']:
        raise ValueError('rank model differs from selected artifact')
    model = (ExactRankTree.from_dict(artifact) if artifact.get('schema') == 'keiba-exact-rank-trees-v1'
             else RankModel.from_dict(artifact))
    now = dt.datetime.now(dt.timezone.utc)
    forbidden = ('pre_off_odds', 'final_win_odds', 'finish_position', 'payouts', 'win_payout_100',
                 'finish_time_seconds', 'margin_seconds', 'relative_speed_z', 'corner4_position', 'last_3f_rank')
    for row in rows:
        if any(row.get(key) not in (None, '') for key in forbidden):
            raise ValueError('odds/outcome fields cannot enter rank snapshots')
        if not row.get('features_asof'):
            raise ValueError('actual runner observation time required')
        if any(row.get(k) and timestamp(row[k]) > now for k in ('features_asof', 'going_asof')):
            raise ValueError('future observation time')
    cutoff = validate_field(rows, require_odds=False)
    input_quality = audit_snapshot(rows,now,cutoff)
    if now > cutoff:
        raise ValueError('rank forecast cutoff has passed')
    if timestamp(selected['selection_end']) >= cutoff:
        raise ValueError('rank model selection must precede forecast cutoff')
    history = load_observed_enriched(db, min(cutoff, now))
    prepared = [{**r, 'race_date':timestamp(r['off_timestamp']).astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()}
                for r in rows]
    features = build_enriched(history_index(history, assumed=False), prepared)
    race = augment(dict(rows=prepared, features=features))
    p, q = (joint_distribution(model.raw([race])[0], model.temperature) if isinstance(model, ExactRankTree)
            else model.predict(race['features']))
    numbers = [r['horse_number'] for r in prepared]
    winner, trio, ordered = picks(p, q, numbers)
    set_policy = selected.get('prediction_set_policy', 'marginal_recall')
    if set_policy == 'exact_set':
        trio, _ = exact_set(q, numbers)
    elif set_policy != 'marginal_recall':
        raise ValueError('unknown rank set decision policy')
    calibration_info=None
    if calibration_path:
        adjustment=json.loads(Path(calibration_path).read_text())
        alpha=(alpha_for(adjustment,p,sha(model_path),sha(selection_path))
               if adjustment.get('schema')=='keiba-rank-confidence-calibration-v1'
               else validate_artifact(adjustment,sha(model_path),sha(selection_path)))
        if timestamp(adjustment['selection_end'])>=cutoff:
            raise ValueError('calibration selection must precede forecast cutoff')
        p,q=mix_joint(p,q,alpha)
        calibration_info=dict(sha256=sha(calibration_path),alpha=alpha,
                              method='uniform_distinct_ordered_triple_mixture',
                              status='retrospective_evaluated_research_only')
    return dict(version='4.8-rank-shadow', deployment_status='experimental_rank_shadow',
        race_id=rows[0]['race_id'], off_timestamp=rows[0]['off_timestamp'], cutoff_timestamp=cutoff.isoformat(),
        created_at=now.isoformat(), history_time_policy='actual_source_and_identity_observation',
        model_sha256=sha(model_path), input_db_sha256=sha(db),
        runners=[dict(horse_number=r['horse_number'], horse_id=r['horse_id'],
                      p_first=float(p[i,0]), p_second=float(p[i,1]), p_third=float(p[i,2]),
                      p_top3=float(p[i].sum()), history_starts=features[i]['history_starts'])
                 for i,r in enumerate(prepared)],
        winner_pick=numbers[winner], top3_pick=[numbers[i] for i in trio],
        ordered_pick=[numbers[i] for i in ordered], unordered_decision_policy=set_policy,
        input_quality=input_quality,probability_calibration=calibration_info,
        inputs=dict(runners=prepared, features=race['features']),
        allocation=dict(bets=[], stake_yen=0), strict_production_validated=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'runners', 'model', 'selection', 'ledger', 'output'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--calibration')
    a = p.parse_args()
    result = forecast(a.db, json.loads(Path(a.runners).read_text()), a.model, a.selection,a.calibration)
    key = Ledger(a.ledger).freeze(result, json.loads(Path(a.model).read_text()), mode='forward')
    Path(a.output).write_text(canonical(dict(prediction_id=key, **result)))
    print(key)
