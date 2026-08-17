import uuid
from datetime import date, datetime

from app.engine.export.xer_writer import build_xer
from app.models.activity import Activity
from app.models.activity_code import ActivityCodeType, ActivityCodeValue, TaskActivityCode
from app.models.activity_relationship import ActivityRelationship, LinkType
from app.models.calendar import Calendar
from app.models.project import Project
from app.models.resource import Resource
from app.models.resource_assignment import ResourceAssignment
from app.models.wbs_node import WbsNode
from app.parser.xer_parser import parse_xer

WORK_WEEK = [
    # 08:00-16:00 = 8h/day, matching the fixture's declared hours_per_day — the
    # parser recomputes hours_per_day from these shift times on re-import, so
    # the two must agree for a clean round-trip assertion.
    {"day_of_week": dow, "shifts": [{"start": "08:00:00", "end": "16:00:00"}] if 1 <= dow <= 5 else []}
    for dow in range(7)
]


def _project(**kwargs) -> Project:
    defaults = dict(id=uuid.uuid4(), tenant_id=uuid.uuid4(), name="Test Project", code="PRJ1")
    defaults.update(kwargs)
    return Project(**defaults)


def _calendar(**kwargs) -> Calendar:
    defaults = dict(
        id=uuid.uuid4(), clndr_id="CAL1", name="Standard 5 Day", hours_per_day=8.0, work_week=WORK_WEEK, exceptions=[]
    )
    defaults.update(kwargs)
    return Calendar(**defaults)


def _activity(**kwargs) -> Activity:
    defaults = dict(
        id=uuid.uuid4(),
        external_id="A100",
        name="Mobilization",
        task_type="TT_Task",
        status_code="TK_NotStart",
        percent_complete=0,
        target_duration_hours=8.0,
        remaining_duration_hours=8.0,
        early_start=date(2026, 1, 5),
        early_finish=date(2026, 1, 5),
    )
    defaults.update(kwargs)
    return Activity(**defaults)


def _rel(pred: Activity, succ: Activity, link_type: LinkType = LinkType.FS, lag_hours: int = 0) -> ActivityRelationship:
    return ActivityRelationship(
        id=uuid.uuid4(), predecessor_id=pred.id, successor_id=succ.id, link_type=link_type, lag_days=0, lag_hours=lag_hours
    )


def test_round_trips_through_our_own_parser():
    project = _project(p6_proj_id="PROJ1", p6_proj_short_name="PROJ1")
    cal = _calendar()
    wbs = WbsNode(id=uuid.uuid4(), wbs_id="WBS1", parent_wbs_id=None, wbs_short_name="Phase 1", wbs_name="Phase 1", seq_num=1)
    a100 = _activity(external_id="A100", clndr_id=cal.id, wbs_path="WBS1", p6_task_id="1001")
    a200 = _activity(external_id="A200", name="Foundation", clndr_id=cal.id, wbs_path="WBS1", p6_task_id="1002")

    xer_bytes = build_xer(
        project, [a100, a200], [_rel(a100, a200)], [cal], [wbs], [], [], [], [], [], datetime(2026, 1, 5, 8, 0)
    )
    parsed = parse_xer(xer_bytes)

    assert parsed.meta.proj_id == "PROJ1"
    assert parsed.meta.clndr_id == "CAL1"

    assert len(parsed.calendars) == 1
    parsed_cal = parsed.calendars[0]
    assert parsed_cal.clndr_id == "CAL1"
    assert parsed_cal.hours_per_day == 8.0
    monday = next(d for d in parsed_cal.default_work_week if d.day_of_week == 1)
    assert monday.is_working
    sunday = next(d for d in parsed_cal.default_work_week if d.day_of_week == 0)
    assert not sunday.is_working

    assert len(parsed.wbs_nodes) == 1
    assert parsed.wbs_nodes[0].wbs_id == "WBS1"

    assert len(parsed.activities) == 2
    by_code = {a.task_code: a for a in parsed.activities}
    assert by_code["A100"].task_id == "1001"
    assert by_code["A200"].task_id == "1002"
    assert by_code["A100"].wbs_id == "WBS1"

    assert len(parsed.relationships) == 1
    rel = parsed.relationships[0]
    assert rel.pred_task_id == "1001"
    assert rel.task_id == "1002"
    assert rel.pred_type == "PR_FS"


def test_activity_without_p6_task_id_falls_back_to_our_own_uuid():
    project = _project()
    cal = _calendar()
    native = _activity(external_id="NEW1", clndr_id=cal.id, p6_task_id=None)

    xer_bytes = build_xer(project, [native], [], [cal], [], [], [], [], [], [], None)
    parsed = parse_xer(xer_bytes)

    assert parsed.activities[0].task_id == str(native.id)


def test_writes_empty_resource_and_activity_code_tables_when_none_assigned():
    project = _project()
    xer_bytes = build_xer(project, [], [], [], [], [], [], [], [], [], None)
    text = xer_bytes.decode("utf-8")

    for table in ("RSRC", "TASKRSRC", "ACTVTYPE", "ACTVCODE", "TASKACTV"):
        assert f"%T\t{table}\n" in text


def test_resource_assignments_round_trip():
    project = _project()
    cal = _calendar()
    a = _activity(external_id="A1", clndr_id=cal.id, p6_task_id="1")
    resource = Resource(
        id=uuid.uuid4(), rsrc_id="LAB1", name="Laborer", short_name="LAB", rsrc_type="RT_Labor", unit_id="h"
    )
    assignment = ResourceAssignment(
        id=uuid.uuid4(),
        activity_id=a.id,
        resource_id=resource.id,
        remain_qty=8.0,
        target_qty=40.0,
        act_reg_qty=16.0,
        target_cost=0.0,
        act_reg_cost=0.0,
        remain_cost=0.0,
    )

    xer_bytes = build_xer(project, [a], [], [cal], [], [resource], [assignment], [], [], [], None)
    parsed = parse_xer(xer_bytes)

    assert len(parsed.resources) == 1
    assert parsed.resources[0].rsrc_id == "LAB1"
    assert len(parsed.assignments) == 1
    parsed_assignment = parsed.assignments[0]
    assert parsed_assignment.rsrc_id == "LAB1"
    assert parsed_assignment.task_id == "1"
    assert parsed_assignment.target_qty == 40.0
    assert parsed_assignment.act_reg_qty == 16.0


def test_relationship_lag_and_link_type_round_trip():
    project = _project()
    cal = _calendar()
    a = _activity(external_id="A1", clndr_id=cal.id, p6_task_id="1")
    b = _activity(external_id="A2", clndr_id=cal.id, p6_task_id="2")
    rel = _rel(a, b, link_type=LinkType.SS, lag_hours=16)

    xer_bytes = build_xer(project, [a, b], [rel], [cal], [], [], [], [], [], [], None)
    parsed = parse_xer(xer_bytes)

    assert len(parsed.relationships) == 1
    parsed_rel = parsed.relationships[0]
    assert parsed_rel.pred_type == "PR_SS"
    assert parsed_rel.lag_hr_cnt == 16.0


def test_activity_codes_round_trip():
    project = _project()
    cal = _calendar()
    a = _activity(external_id="A1", clndr_id=cal.id, p6_task_id="1")

    code_type = ActivityCodeType(id=uuid.uuid4(), actv_code_type_id="PHASE", name="Phase")
    code_value = ActivityCodeValue(
        id=uuid.uuid4(), code_type_id=code_type.id, actv_code_id="PH1", name="Phase 1",
        short_name="P1", parent_actv_code_id=None, seq_num=1,
    )
    assignment = TaskActivityCode(id=uuid.uuid4(), activity_id=a.id, code_value_id=code_value.id)

    xer_bytes = build_xer(project, [a], [], [cal], [], [], [], [code_type], [code_value], [assignment], None)
    parsed = parse_xer(xer_bytes)

    assert len(parsed.code_types) == 1
    assert parsed.code_types[0].actv_code_type_id == "PHASE"
    assert len(parsed.code_values) == 1
    assert parsed.code_values[0].actv_code_id == "PH1"
    assert parsed.code_values[0].actv_code_type_id == "PHASE"
    assert len(parsed.activity_codes) == 1
    assert parsed.activity_codes[0].task_id == "1"
    assert parsed.activity_codes[0].actv_code_id == "PH1"
