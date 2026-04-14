from datetime import date
import time

def get_first(d: dict, keys: list[str]):
    """Erstes vorhandenes, nicht-None-Feld (Garmin nutzt wechselnde Key-Namen)."""
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None

def to_float(v):
    """Skalare für JSON: None bleibt None; bool unverändert; sonst float."""
    if v is None:
        return None
    try:
        if isinstance(v, bool):
            return v
        return float(v)
    except Exception:
        return None

def parse_vo2_block(block) -> float | None:
    if not isinstance(block, dict):
        return None
    v = block.get("vo2MaxPreciseValue") or block.get("vo2MaxValue")
    return to_float(v)

def parse_vo2_from_training_status(ts):
    if not isinstance(ts, dict):
        return None, None, None
    mrv = ts.get("mostRecentVo2Max") or ts.get("mostRecentVO2Max")
    if not isinstance(mrv, dict):
        return None, None, None
    return (
        parse_vo2_block(mrv.get("running")),
        parse_vo2_block(mrv.get("cycling")),
        parse_vo2_block(mrv.get("generic")),
    )

def parse_vo2_from_max_metrics(mm) -> tuple[float | None, float | None]:
    run, cyc = None, None
    if not isinstance(mm, dict):
        return run, cyc

    def walk(o):
        nonlocal run, cyc
        if isinstance(o, dict):
            st = str(o.get("sportType") or o.get("sport") or "").upper()
            has_vo2 = any(k.lower().startswith("vo2") for k in o if isinstance(k, str))
            if has_vo2 and st:
                v = parse_vo2_block(o)
                if v is not None:
                    if "CYCL" in st:
                        cyc = cyc or v
                    if "RUN" in st:
                        run = run or v
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(mm)
    return run, cyc

def parse_hr_zones(blob):
    if not isinstance(blob, dict):
        return None
    ud = blob.get("userData")
    if isinstance(ud, dict):
        z = ud.get("heartRateZones")
        if isinstance(z, (list, dict)):
            return z
    z = blob.get("heartRateZones")
    return z if isinstance(z, (list, dict)) else None

def parse_demographics(profile: dict) -> dict:
    o = {}
    if not isinstance(profile, dict):
        return o
    ud = profile.get("userData")
    if not isinstance(ud, dict):
        ud = profile
    bd = ud.get("birthDate")
    if bd:
        o["birth_date"] = str(bd)[:10]
        try:
            bdate = date.fromisoformat(str(bd)[:10])
            t = date.today()
            o["age_years"] = t.year - bdate.year - ((t.month, t.day) < (bdate.month, bdate.day))
        except Exception:
            pass
    if ud.get("gender") is not None:
        o["gender"] = ud.get("gender")
    if ud.get("height") is not None and to_float(ud.get("height")) is not None:
        o["height_cm"] = to_float(ud.get("height"))
    if ud.get("weight") is not None and to_float(ud.get("weight")) is not None:
        o["weight_kg"] = to_float(ud.get("weight"))
    mhr = ud.get("maxHeartRate") or ud.get("maxHeartRateUsed")
    if mhr is not None:
        try:
            o["max_hr_bpm"] = int(float(mhr))
        except Exception:
            pass
    mus = ud.get("measurementSystem") or profile.get("measurementSystem")
    if mus is not None:
        o["unit_system"] = mus
    tz = ud.get("timeZone") or profile.get("timeZone")
    if tz is not None:
        o["time_zone"] = tz
    return o

def parse_fitness_age(fa) -> float | None:
    if not isinstance(fa, dict):
        return None
    v = fa.get("fitnessAge") or fa.get("chronologicalAge")
    if v is None and isinstance(fa.get("fitnessAgeData"), dict):
        v = fa["fitnessAgeData"].get("fitnessAge")
    return to_float(v)

def parse_lactate_hrs(lt) -> dict:
    o = {}
    if not isinstance(lt, dict):
        return o
    shr = lt.get("speed_and_heart_rate")
    if not isinstance(shr, dict):
        return o
    hr, hrc = shr.get("heartRate"), shr.get("heartRateCycling")
    if hr is not None:
        try:
            o["lactate_threshold_hr_running_bpm"] = int(float(hr))
        except Exception:
            pass
    if hrc is not None:
        try:
            o["lactate_threshold_hr_cycling_bpm"] = int(float(hrc))
        except Exception:
            pass
    return o

def parse_ftp_watts(ftp) -> int | None:
    if isinstance(ftp, list) and ftp:
        ftp = ftp[0]
    if not isinstance(ftp, dict):
        return None
    w = ftp.get("ftp") or ftp.get("functionalThresholdPower") or ftp.get("value")
    if w is None:
        return None
    try:
        return int(round(float(w)))
    except Exception:
        return None

def activity_needs_details(activity: dict) -> bool:
    """Helper to determine if we should fetch extra details."""
    def _ext(*keys):
        return get_first(activity, list(keys))
        
    return any(v is None for v in [
        _ext("normalizedPower", "normPower", "normalizedPowerValue"),
        _ext("intensityFactor", "if"),
        _ext("trainingStressScore", "tss"),
        _ext("vo2MaxValue", "vO2MaxValue", "vo2Max", "VO2MaxValue"),
        _ext("intensityMinutes", "intensityMinutesValue"),
        _ext("averagePower", "avgPower"),
        _ext("maxPower", "maximumPower"),
        _ext("work", "workInJoules", "totalWork", "totalWorkInJoules"),
        _ext("averageCadence", "avgCadence"),
        _ext("aerobicTrainingEffect", "trainingEffect", "aerobicEffect"),
        _ext("anaerobicTrainingEffect", "anaerobicEffect"),
        _ext("trainingEffect"),
        _ext("trainingEffectLabel"),
        _ext("exerciseLoad")
    ])

def parse_activity(activity: dict, details: dict | None = None, hr_zones_data=None) -> dict:
    if details is None:
        details = {}

    def _ms_to_kmh_float(ms):
        if ms is None:
            return None
        try:
            return round(float(ms) * 3.6, 6)
        except Exception:
            return None

    activity_id = str(activity.get('activityId', ''))
    distance_km = (activity.get('distance') or 0) / 1000
    elapsed_s = activity.get('duration') or 0
    moving_s = get_first(activity, ["movingDuration", "movingDurationInSeconds", "movingTimeInSeconds"]) or elapsed_s
    duration_min = elapsed_s / 60 if elapsed_s else 0
    speed_kmh = (activity.get('averageSpeed') or 0) * 3.6
    max_speed_kmh = _ms_to_kmh_float(get_first(activity, ["maxSpeed", "maximumSpeed"]))

    # Extraction priority: details > summary
    def _extract(*keys):
        val = get_first(details, list(keys))
        if val is None:
            val = get_first(activity, list(keys))
        return val

    avg_power = _extract("averagePower", "avgPower")
    max_power = _extract("maxPower", "maximumPower")
    np_power = _extract("normalizedPower", "normPower", "normalizedPowerValue")
    work_val = _extract("work", "workInJoules", "totalWork", "totalWorkInJoules")
    avg_cadence = _extract("averageCadence", "avgCadence")
    te_aer = _extract("aerobicTrainingEffect", "trainingEffect", "aerobicEffect")
    te_ana = _extract("anaerobicTrainingEffect", "anaerobicEffect")
    training_effect_primary = _extract("trainingEffect")
    te_label = _extract("trainingEffectLabel")
    exercise_load = _extract("exerciseLoad")
    intensity_factor = _extract("intensityFactor", "if")
    tss = _extract("trainingStressScore", "tss")
    vo2 = _extract("vo2MaxValue", "vO2MaxValue", "vo2Max", "VO2MaxValue")
    
    intensity_minutes = _extract("intensityMinutes", "intensityMinutesValue")
    if intensity_minutes is None:
        mod = _extract("moderateIntensityMinutes")
        vig = _extract("vigorousIntensityMinutes")
        try:
            if mod is not None or vig is not None:
                intensity_minutes = (int(mod or 0) + int(vig or 0))
        except Exception:
            pass

    work_kj = None
    try:
        if work_val is not None:
            w = float(work_val)
            work_kj = (w / 1000.0) if w > 5000 else w
        elif avg_power is not None and moving_s:
            work_kj = (float(avg_power) * float(moving_s)) / 1000.0
    except Exception:
        pass

    te_main = training_effect_primary if training_effect_primary is not None else te_aer

    return {
        "activity_id": activity_id,
        "date": activity.get("startTimeLocal", "")[:10],
        "activity_type": activity.get("activityType", {}).get("typeKey", "Unknown"),
        "distance_km": round(distance_km, 6) if distance_km else None,
        "duration_min": round(duration_min, 4) if duration_min else None,
        "moving_time_min": (float(moving_s) / 60.0) if moving_s else None,
        "elapsed_time_min": (float(elapsed_s) / 60.0) if elapsed_s else None,
        "avg_speed_kmh": round(speed_kmh, 4) if speed_kmh else None,
        "max_speed_kmh": max_speed_kmh,
        "avg_hr": to_float(activity.get("averageHR")),
        "max_hr": to_float(activity.get("maxHR")),
        "avg_power_w": to_float(avg_power),
        "max_power_w": to_float(max_power),
        "normalized_power_w": to_float(np_power),
        "work_kj": to_float(work_kj),
        "avg_cadence_rpm": to_float(avg_cadence),
        "training_effect": to_float(te_main),
        "aerobic_training_effect": to_float(te_aer),
        "anaerobic_training_effect": to_float(te_ana),
        "training_effect_label": te_label,
        "exercise_load": to_float(exercise_load),
        "intensity_factor": to_float(intensity_factor),
        "training_stress_score": to_float(tss),
        "vo2max_estimate": to_float(vo2),
        "intensity_minutes": to_float(intensity_minutes),
        "calories": to_float(activity.get("calories")),
        "elevation_gain": to_float(activity.get("elevationGain")),
        "hr_zones": hr_zones_data,
    }


def parse_daily_health(target_date: str, stats: dict, sleep: dict, hrv: dict) -> dict:
    if stats is None: stats = {}
    if sleep is None: sleep = {}
    if hrv is None: hrv = {}
    
    hrv_avg = None
    if hrv and "hrvSummary" in hrv and hrv["hrvSummary"]:
        val = hrv["hrvSummary"].get("lastNightAvg")
        if val is not None:
            hrv_avg = round(float(val), 1)

    sleep_score = None
    sleep_hours = None
    sleep_start_local = None
    sleep_end_local = None

    if "dailySleepDTO" in sleep:
        sleep_dto = sleep["dailySleepDTO"]
        sleep_time_seconds = sleep_dto.get("sleepTimeSeconds") or 0
        sleep_hours = round(sleep_time_seconds / 3600.0, 4)

        sleep_start_local = get_first(sleep_dto, ["sleepStartTimestampLocal", "sleepStartTimeLocal"])
        sleep_end_local = get_first(sleep_dto, ["sleepEndTimestampLocal", "sleepEndTimeLocal"])

        if "sleepScores" in sleep_dto and "overall" in sleep_dto["sleepScores"]:
            v = sleep_dto["sleepScores"]["overall"].get("value")
            sleep_score = to_float(v)
        elif "sleepScore" in sleep_dto:
            score_data = sleep_dto["sleepScore"]
            sleep_score = to_float(score_data.get("value")) if isinstance(score_data, dict) else to_float(score_data)

    intensity_minutes = get_first(stats, ["intensityMinutes", "intensityMinutesValue"])
    if intensity_minutes is None:
        mod = get_first(stats, ["moderateIntensityMinutes"])
        vig = get_first(stats, ["vigorousIntensityMinutes"])
        try:
            if mod is not None or vig is not None:
                intensity_minutes = int(mod or 0) + int(vig or 0)
        except Exception:
            pass

    active_cal = get_first(stats, ["activeKilocalories", "activeCalories"])
    total_cal = get_first(stats, ["totalKilocalories", "totalCalories", "burnedKilocalories"])
    max_stress = get_first(stats, ["maxStressLevel", "maxStress"])
    bb_high = get_first(stats, ["bodyBatteryHighestValue", "bodyBatteryHigh", "bodyBatteryMax", "bodyBatteryHighest"])
    bb_low = get_first(stats, ["bodyBatteryLowestValue", "bodyBatteryLow", "bodyBatteryMin", "bodyBatteryLowest"])

    return {
        "date": target_date,
        "resting_hr": int(stats["restingHeartRate"]) if stats.get("restingHeartRate") is not None else None,
        "avg_hrv": hrv_avg,
        "avg_stress": to_float(stats.get("averageStressLevel")),
        "max_stress": to_float(max_stress),
        "body_battery_high": to_float(bb_high),
        "body_battery_low": to_float(bb_low),
        "sleep_hours": sleep_hours,
        "sleep_start_local": sleep_start_local,
        "sleep_end_local": sleep_end_local,
        "sleep_score": sleep_score,
        "steps": int(stats["totalSteps"]) if stats.get("totalSteps") is not None else None,
        "intensity_minutes": to_float(intensity_minutes),
        "active_calories": to_float(active_cal),
        "total_calories": to_float(total_cal),
    }

