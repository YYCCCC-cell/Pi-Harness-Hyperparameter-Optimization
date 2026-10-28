"""Versioned metadata projections. Optimizer access never loads heldout IDs."""
import hashlib

from hpo.config import load_validation_roster, read_json
from pilot.config import PINS, ROOT

VALIDATION_SHA256 = "32c2070c0f2e218c8bdaedf3351dc3d957ed917d49d9aa590a519cb89d580a5d"
HELDOUT_SHA256 = "368494f11133fd93217e2c45e5706a7a2984256dbe44f9d42683baed85cccb53"
COMPACT_HELDOUT_SHA256 = "6dcdb62058312bae864d57980e40048ce324d6f79efed41f9a33f214022c8581"


def _panel(relative, expected, role, count, profile='grouped_v2'):
    path = ROOT / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Panel changed; review and version before use")
    panel = read_json(path)
    ids = panel["task_ids"]
    members = [t for g in panel["groups"] for t in g["tasks"]]
    if (panel["role"] != role or panel["profile"] != profile or
            panel["benchmark_commit"] != PINS["skillsbench"] or
            len(ids) != count or len(set(ids)) != count or
            len(members) != len(set(members)) or set(members) != set(ids)):
        raise ValueError("Panel identity, group partition or cardinality mismatch")
    return panel


def validation_panel():
    panel = _panel("configs/hpo_validation_panel.v2.json", VALIDATION_SHA256, "validation", 8)
    original = load_validation_roster()
    if (not set(panel["task_ids"]) <= set(original["task_ids"]) or
            panel["source_split_sha256"] != original["source_split_sha256"]):
        raise ValueError("Subset must preserve original validation membership")
    return panel


def heldout_sha256(profile='grouped_v2'):
    if profile not in ('grouped_v2','compact_v3'):
        raise ValueError('Unknown heldout profile')
    return COMPACT_HELDOUT_SHA256 if profile=='compact_v3' else HELDOUT_SHA256


def heldout_panel(profile='grouped_v2'):
    compact=profile=='compact_v3'
    panel = _panel('evaluation/panels/heldout.v3.json' if compact else 'evaluation/panels/heldout.v2.json',
                   heldout_sha256(profile), 'heldout', 8 if compact else 16, profile)
    if compact:
        parent=heldout_panel()
        selected=set(panel['task_ids'])
        if (not selected <= set(parent['task_ids']) or
                panel['selection']['parent_sha256'] != HELDOUT_SHA256 or
                any(set(g['tasks']) & selected and not set(g['tasks']) <= selected for g in parent['groups'])):
            raise ValueError('Compact heldout must preserve whole parent families')
    validation = validation_panel()
    if (set(panel["task_ids"]) & set(load_validation_roster()["task_ids"]) or
            panel["source_family_audit_sha256"] != validation["source_family_audit_sha256"] or
            {g["group_id"] for g in panel["groups"]} & {g["group_id"] for g in validation["groups"]}):
        raise ValueError("Heldout panel overlaps validation tasks/families or audit changed")
    return panel


def authorize_tasks(live, tasks, access=None):
    if access is None:
        panel = load_validation_roster(live.get("validation_profile", "original"))
    else:
        if set(access) != {"role", "freeze_path", "freeze_sha256"} or access["role"] != "heldout":
            raise ValueError("Invalid evaluator access")
        from evaluation.frozen import load_frozen
        frozen = load_frozen(access["freeze_path"], access["freeze_sha256"])
        if live != frozen["identity"]["live"]:
            raise ValueError("Heldout runtime differs from frozen validation runtime")
        panel = heldout_panel(live.get('heldout_profile','grouped_v2'))
    if not tasks or len(tasks) != len(set(tasks)) or not set(tasks) <= set(panel["task_ids"]):
        raise ValueError("Task is outside the selected evaluator panel")
    return panel


def authorize_attempt(request):
    access = request.get("evaluation_access")
    authorize_tasks(request["live"], [request["task_id"]], access)
    if access is not None:
        from evaluation.frozen import load_frozen
        from pilot.config import digest
        identity = load_frozen(access["freeze_path"], access["freeze_sha256"])["identity"]
        if digest(request["settings"]) not in {w["config_id"] for w in identity["winners"]}:
            raise ValueError("Heldout settings are not among the frozen winners")
        expected_seed = int(hashlib.sha256(
            f"{identity['evaluation_seed']}:{request['task_id']}".encode()).hexdigest()[:8], 16)
        if request["evaluation_seed"] != expected_seed:
            raise ValueError("Heldout evaluation seed differs from frozen protocol")
