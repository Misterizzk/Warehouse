"""Dashboard projections reuse inventory aging and immutable inspection snapshots."""
import json
from datetime import date, datetime
from .inventory import Inventory
from .locations import Locations
from .domain import NORMAL_MAX,AGE_LIMIT

RANK={'Tanpa stok':-1,'Normal':0,'Data perlu diperbaiki':1,'Warning':2,'Melewati batas':3}


def aggregate(rows):
    active=[row for row in rows if row['stock']>0]
    return dict(status=max((r['status'] for r in active),key=lambda s:RANK[s],default='Tanpa stok'),
                batches=len(active),stock=sum(r['stock'] for r in active),
                invalid=sum(r['status']=='Data perlu diperbaiki' for r in active),rows=rows)


def aggregate_sections(cells):
    """Project top-down sections from the three independent storage levels."""
    sections = {}
    for cell in cells:
        key = (cell['column'], cell['row'])
        section = sections.setdefault(key, dict(column=key[0], row=key[1], cells=[], rows=[]))
        section['cells'].append(cell)
        section['rows'].extend(cell['rows'])
    for section in sections.values():
        section['cells'].sort(key=lambda cell: cell['level'])
        section.update(aggregate(section['rows']))
    return sections


def aggregate_columns(sections):
    """Summarize each side-elevation slide without changing section statuses."""
    columns = {}
    for (column, row), section in sorted(sections.items()):
        slide = columns.setdefault(column, dict(column=column, sections={}, cells=[], rows=[]))
        slide['sections'][row] = section
        slide['cells'].extend(section['cells'])
        slide['rows'].extend(section['rows'])
    for slide in columns.values():
        slide.update(aggregate(slide['rows']))
    return columns


def local_day(timestamp):
    """Inspection timestamps are stored with an offset; use the computer's local day."""
    return datetime.fromisoformat(timestamp).astimezone().date()


def last_checked_item(db, marker, area=''):
    """Snapshot from the last confirmed check, never recomputed from live inventory."""
    if not marker:
        return None
    record=db.execute('''SELECT r.*,s.officer,s.area AS session_area,
        s.status AS session_status,s.normal_max,s.age_limit
        FROM check_results r JOIN check_sessions s ON s.id=r.session_id
        WHERE r.session_id=? AND r.batch_id=?''',
        (marker['session_id'],marker['batch_id'])).fetchone()
    if record is None:
        return None
    item=json.loads(record['snapshot'])
    if area and item['location_code'].split('-')[0]!=area:
        return None
    item.update({key:record[key] for key in ('session_id','batch_id','checked_at','age','status',
        'note','officer','session_area','session_status','normal_max','age_limit')})
    # A repeated confirmation may highlight a saved result without changing its history.
    item['last_seen_at']=marker.get('time',record['checked_at'])
    return item


def overview(db,area='',today=None):
    """Activity scans respect area and local date; draft_count is global, across all dates."""
    today=today or date.today()
    all_rows=Inventory(db).list_batches(today=today)
    locations=[dict(row) for row in Locations(db).list()]
    areas=sorted({r['area'] for r in locations})
    rows=[r for r in all_rows if not area or r['area']==area]
    active=[r for r in rows if r['stock']>0]
    counts={s:sum(r['status']==s for r in active) for s in RANK if s!='Tanpa stok'}
    by_location={loc['code']:[] for loc in locations}
    for row in all_rows:by_location[row['location_code']].append(row)
    racks={}
    for loc in locations:
        if area and loc['area']!=area:continue
        key=(loc['area'],loc['rack'])
        racks.setdefault(key,dict(area=key[0],rack=key[1],cells=[],sections={},rows=[]))
        cell=dict(loc,**{k:v for k,v in aggregate(by_location[loc['code']]).items() if k!='batches'})
        cell['batches']=sum(r['stock']>0 for r in cell['rows'])
        racks[key]['cells'].append(cell)
        racks[key]['rows'].extend(cell['rows'])
    for rack in racks.values():
        rack.update(aggregate(rack['rows']))
        rack['sections'] = aggregate_sections(rack['cells'])
        rack['columns'] = aggregate_columns(rack['sections'])
    priorities=sorted((r for r in active if r['status']!='Normal'),
                      key=lambda r:(-RANK[r['status']],-r['age'] if isinstance(r['age'],int) else 0,r['id']))
    recent=[]
    checked_batches=set()
    result_count=0
    for record in db.execute('''SELECT r.*,s.officer,s.area AS session_area,s.status AS session_status
        FROM check_results r JOIN check_sessions s ON s.id=r.session_id
        ORDER BY r.checked_at DESC,r.rowid DESC'''):
        snapshot=json.loads(record['snapshot'])
        if area and snapshot['location_code'].split('-')[0]!=area:continue
        if local_day(record['checked_at'])==today:
            checked_batches.add(record['batch_id'])
            result_count+=1
        if len(recent)<5:
            recent.append(dict(record,material=snapshot['material'],location_code=snapshot['location_code']))
    marker=db.execute("SELECT value FROM metadata WHERE key='last_check'").fetchone()
    last=json.loads(marker[0]) if marker else None
    if last is None and recent:
        record=recent[0]
        last=dict(session_id=record['session_id'],batch_id=record['batch_id'],location_code=record['location_code'],time=record['checked_at'])
    current_location = None
    if last:
        current = db.execute('SELECT location_code FROM batches WHERE id=?', (last['batch_id'],)).fetchone()
        if current and (not area or current['location_code'].split('-')[0] == area):
            current_location = current['location_code']
    activity_today=dict(checked_batches=len(checked_batches),result_count=result_count,
        draft_count=db.execute("SELECT count(*) FROM check_sessions WHERE status='Draft'").fetchone()[0])
    return dict(today=today.isoformat(),areas=areas,rows=rows,active=active,counts=counts,racks=racks,
                priorities=priorities,recent=recent,last=last,total_stock=sum(r['stock'] for r in active),
                zero_stock=len(rows)-len(active),normal_max=NORMAL_MAX,age_limit=AGE_LIMIT,
                activity_today=activity_today,latest_item=last_checked_item(db,last,area),
                last_current_location_code=current_location)
