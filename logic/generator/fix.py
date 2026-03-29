from logic.generator.manual_constraint import resolve_manual_shift
from datetime import date
import datetime

def get_iso_week(year, month, day):
    return datetime.date(year, month, day).isocalendar()[1]

def setup_fix_hints_and_penalties(
    model, 
    x, 
    employees, 
    days, 
    schedule, 
    shop, 
    all_shifts, 
    SHIFT_OPEN, 
    SHIFT_CLOSE, 
    START_SHIFT_MAP, 
    END_SHIFT_MAP
):
    """
    Applies CP-SAT Warm Start hints and adds penalties to minimize changes
    from the current generated schedule.
    Heavily penalizes changes outside the weeks where manual edits were made.
    """
    edited_weeks = set()
    
    for emp in employees:
        for d in days:
            day_state = schedule.get_day(emp, d)
            if day_state.is_locked:
                week_num = get_iso_week(schedule.year, schedule.month, d)
                edited_weeks.add(week_num)
                
    nominal_hours = shop.get_full_time_nominal_hours()
    nominal_minutes = nominal_hours * 60
    
    from logic.utils.time_utils import get_effective_daily_hours
                
    penalties = []
    
    start_map_rev = {v: k for k, v in START_SHIFT_MAP.items()}
    end_map_rev = {v: k for k, v in END_SHIFT_MAP.items()}
    
    for e, emp in enumerate(employees):
    
        shift_minutes = int(get_effective_daily_hours(emp, shop) * 60)
        leave_days = 0
        sick_days = 0
        
        for d in days:
            ds = schedule.get_day(emp, d)
            if ds.is_leave:
                leave_days += 1
            if getattr(ds, "is_sick", False):
                sick_days += 1
                
        leave_minutes = int(leave_days * emp.daily_hours * 60)
        sick_minutes = int(sick_days * emp.daily_hours * 60)
        
        target_minutes = int(nominal_minutes * emp.employment_fraction - leave_minutes - sick_minutes)
        
        total_worked = sum(
            x[e, d, s] * shift_minutes
            for d in days
            for s in all_shifts
            if s != 14
        )
        
        # TWARDY LIMIT: absolutny priorytet zachowania nominalnego czasu.
        # Nie pozwól solverowi wyjść poza nominał ani o minutę
        model.Add(total_worked <= target_minutes)
        
        # MIĘKKI LIMIT: Kara za niedobór godzin (under_target)
        under_target = model.NewIntVar(0, 50000, f"fix_under_e{e}")
        model.Add(target_minutes - total_worked == under_target)
        penalties.append(under_target * 1000)
        
        for d in days:
            day_state = schedule.get_day(emp, d)
            
            # TWARDY BLOK DLA URLOPÓW I L4: zerujemy pracujące zmiany
            if day_state.is_leave or getattr(day_state, "is_sick", False):
                for s in all_shifts:
                    if s != 14:
                        model.Add(x[e, d, s] == 0)
                continue
            
            week_num = get_iso_week(schedule.year, schedule.month, d)
            is_edited_week = week_num in edited_weeks
            
            weight = 500 if is_edited_week else 50000
            
            if day_state.is_locked:
                continue
                
            current_shift = None
            start = getattr(day_state, "start", None)
            end = getattr(day_state, "end", None)
            
            if start and end:
                hours = shop.get_open_hours_for_day(d)
                if hours:
                    open_time, close_time = hours
                    shift_name = resolve_manual_shift(start, end, open_time, close_time, start_map_rev, end_map_rev)
                    if shift_name == "OPEN":
                        current_shift = SHIFT_OPEN
                    elif shift_name == "CLOSE":
                        current_shift = SHIFT_CLOSE
                    elif shift_name is not None:
                        current_shift = shift_name
            
            for s in all_shifts:
                is_currently_assigned = (s == current_shift)
                
                val = 1 if is_currently_assigned else 0
                model.AddHint(x[e, d, s], val)
                
                if val == 1:
                    penalties.append(weight * (1 - x[e, d, s]))
                else:
                    penalties.append(weight * x[e, d, s])
                    
    return penalties