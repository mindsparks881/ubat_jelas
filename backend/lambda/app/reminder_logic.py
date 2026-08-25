"""
FSD 2.6 — Reminder Setup decision tree.
Pure calculation, no external calls (per SDD API spec for /reminder).
"""
from datetime import datetime, timedelta
from typing import List, Optional

from .i18n import t

# Default clock times when no meal_relation is present.
DEFAULT_TIMES = {
    "OD": ["08:00"],
    "OM": ["08:00"],  # every morning (common on MY labels, distinct printed form of a single daily dose)
    "ON": ["21:00"],  # every night
    "BD": ["08:00", "20:00"],
    "TDS": ["08:00", "14:00", "20:00"],
    "QID": ["08:00", "12:00", "16:00", "20:00"],
}

# Default assumed meal times (editable client-side; PRD Section 11 flags
# "remember user's mealtimes" as an open/stretch question — MVP uses these
# fixed defaults).
DEFAULT_MEAL_TIMES = {
    "breakfast": "08:00",
    "lunch": "13:00",
    "dinner": "20:00",
}

AC_OFFSET_MIN = -30  # before food
PC_OFFSET_MIN = 30  # after food

# Dose-slot labels localized per session language (previously hardcoded
# English regardless of session_language — fixed).
LABELS = {
    "en": {
        "OD": ["Once-daily dose"],
        "OM": ["Morning dose"],
        "ON": ["Night dose"],
        "BD": ["Morning dose", "Night dose"],
        "TDS": ["Morning dose", "Afternoon dose", "Night dose"],
        "QID": ["Morning dose", "Midday dose", "Afternoon dose", "Night dose"],
    },
    "ms": {
        "OD": ["Dos harian"],
        "OM": ["Dos pagi"],
        "ON": ["Dos malam"],
        "BD": ["Dos pagi", "Dos malam"],
        "TDS": ["Dos pagi", "Dos tengah hari", "Dos malam"],
        "QID": ["Dos pagi", "Dos tengah hari", "Dos petang", "Dos malam"],
    },
}

MEAL_DISPLAY = {
    "en": {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner"},
    "ms": {"breakfast": "Sarapan", "lunch": "Makan tengah hari", "dinner": "Makan malam"},
}

RELATION_WORD = {
    "en": {"AC": "before", "PC": "after"},
    "ms": {"AC": "sebelum", "PC": "selepas"},
}

MEAL_DOSE_TEMPLATE = {
    "en": "{meal} dose ({relation} food)",
    "ms": "Dos {meal} ({relation} makan)",
}

MANUAL_REMINDER_LABEL = {
    "en": "Reminder {n}",
    "ms": "Peringatan {n}",
}


def _lang(session_language: str) -> str:
    return session_language if session_language in LABELS else "en"


def _shift(hhmm: str, minutes: int) -> str:
    base = datetime.strptime(hhmm, "%H:%M")
    shifted = base + timedelta(minutes=minutes)
    return shifted.strftime("%H:%M")


def compute_reminders(
    frequency_code: Optional[str],
    meal_relation: Optional[str],
    manual_times: Optional[List[str]],
    session_language: str = "en",
):
    """
    Returns (proposed_times: List[{"time","label"}], source: str, note: Optional[str])
    """
    lang = _lang(session_language)

    if frequency_code == "PRN":
        return [], "prn", t("prn_note", session_language)

    if frequency_code and frequency_code in DEFAULT_TIMES:
        base_times = DEFAULT_TIMES[frequency_code]
        default_labels = LABELS[lang][frequency_code]

        if meal_relation in ("AC", "PC"):
            # Anchor to meal times rather than fixed clock defaults.
            offset = AC_OFFSET_MIN if meal_relation == "AC" else PC_OFFSET_MIN
            meal_order = ["breakfast", "lunch", "dinner"]
            meal_display = MEAL_DISPLAY[lang]
            relation_word = RELATION_WORD[lang][meal_relation]
            template = MEAL_DOSE_TEMPLATE[lang]

            if frequency_code == "OM":
                anchor_keys = ["breakfast"]
            elif frequency_code == "ON":
                anchor_keys = ["dinner"]
            else:
                # BD/TDS/QID/OD: walk meals in order; if there are more doses
                # than known meals (e.g. QID = 4 doses, 3 meals), pad
                # remaining slots with the default clock time so no dose
                # silently disappears.
                anchor_keys = meal_order[: len(base_times)]

            times = []
            labels = []
            for i in range(len(base_times)):
                if i < len(anchor_keys):
                    times.append(_shift(DEFAULT_MEAL_TIMES[anchor_keys[i]], offset))
                    # Label reflects the actual meal it's anchored to, not the
                    # generic morning/afternoon/evening slot name, so the
                    # label never contradicts the displayed time.
                    labels.append(
                        template.format(meal=meal_display[anchor_keys[i]], relation=relation_word)
                    )
                else:
                    times.append(base_times[i])
                    labels.append(default_labels[i])
        else:
            times = base_times
            labels = default_labels

        proposed = [{"time": tm, "label": lb} for tm, lb in zip(times, labels)]
        return proposed, "auto", None

    # No frequency_code detected -> manual entry pathway (FSD: normal path, not an error)
    if manual_times:
        template = MANUAL_REMINDER_LABEL[lang]
        proposed = [
            {"time": tm, "label": template.format(n=i + 1)} for i, tm in enumerate(manual_times)
        ]
        return proposed, "manual", None

    return [], "manual", t("no_frequency_note", session_language)
