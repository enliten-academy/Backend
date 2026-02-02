# app.py
import os
import uuid
import random
import datetime
from typing import Dict, Any
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

test_bp = Blueprint('test', __name__)

SESSIONS_COL = "examSessions"
USERS_COL = "users"

def now_utc():
    """Return an offset-aware UTC datetime."""
    return datetime.datetime.now(datetime.timezone.utc)

def ensure_utc_datetime(dt):
    if dt is None:
        return now_utc()

    # Firestore Timestamp support (object with to_datetime())
    try:
        to_dt = getattr(dt, "to_datetime", None)
        if callable(to_dt):
            dt = to_dt()
    except Exception:
        pass

    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            # assume UTC for naive datetimes
            return dt.replace(tzinfo=datetime.timezone.utc)
        # convert any aware datetime to UTC
        return dt.astimezone(datetime.timezone.utc)

    # fallback
    return now_utc()

def to_iso(dt):
    """Return ISO 8601 string in Zulu (UTC) form for aware or naive datetimes."""
    d = ensure_utc_datetime(dt)
    # isoformat produces +00:00 for UTC, replace with Z for compactness
    return d.isoformat().replace("+00:00", "Z")

def exam_questions(exam_group, category=None, subcategory=None, total=10):
    q = current_app.db.collection('sharedQuestions')
    if category:
        q = q.where("category", "==", category)
    if subcategory:
        q = q.where("subcategory", "==", subcategory)
    field_path = f"sharedWith.{exam_group}"
    q = q.where(field_path, "==", True)
    docs = q.stream()
    candidates = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        candidates.append(d)
    if not candidates:
        return []
    random.shuffle(candidates)
    return candidates[:total] if len(candidates) >= total else candidates

def sanitize_question_for_client(qdoc: Dict[str, Any]):
    return {
        "id": qdoc["id"],
        "text": qdoc.get("text"),
        "options": qdoc.get("options"),
        "category": qdoc.get("category"),
        "subcategory": qdoc.get("subcategory")
    }

def get_elapsed_and_remaining(started_at: datetime.datetime, time_limit_minutes: int):
    started_dt = ensure_utc_datetime(started_at)
    now = now_utc()
    elapsed = now - started_dt
    elapsed_seconds = int(elapsed.total_seconds())
    remaining_seconds = max(0, time_limit_minutes * 60 - elapsed_seconds)
    return elapsed_seconds, remaining_seconds


def finalize_session_and_save(session_ref, session_doc):
    questions = session_doc.get("questions", []) or []
    answers = session_doc.get("answers", {}) or {}
    total = len(questions)

    attempted = 0
    correct = 0
    incorrect = 0
    unanswered = 0

    for q in questions:
        qid = q.get("id")
        correct_opt = q.get("correctOption")
        ans = answers.get(qid)
        if not ans:
            unanswered += 1
        else:
            attempted += 1
            if ans.get("selected") == correct_opt:
                correct += 1
            else:
                incorrect += 1

    score_percent = round((correct / total) * 100, 2) if total > 0 else 0.0

    started_dt = ensure_utc_datetime(session_doc.get("started_at"))
    finished_at = now_utc()

    delta = finished_at - started_dt
    hrs, rem = divmod(int(delta.total_seconds()), 3600)
    mins = rem // 60
    time_spent_str = f"{hrs}h {mins}m"

    analysis = {
        "date": finished_at,
        "examDate": started_dt,
        "score": score_percent,
        "totalQuestions": total,
        "attempted": attempted,
        "correct": correct,
        "incorrect": incorrect,
        "unanswered": unanswered,
        "timeSpent": time_spent_str,
        "category": session_doc.get("category"),
        "subcategory": session_doc.get("subcategory"),
        "status": "completed"
    }

    user_id = session_doc.get("user_id")
    history_ref = current_app.db.collection(USERS_COL).document(user_id).collection("assessmentHistory").document()
    history_ref.set(analysis)

    session_ref.update({
        "status": "submitted",
        "analysis": analysis
    })

    # Serialize dates
    analysis_serializable = dict(analysis)
    analysis_serializable["date"] = to_iso(analysis_serializable["date"])
    analysis_serializable["examDate"] = to_iso(analysis_serializable["examDate"])

    return analysis_serializable

@test_bp.route("/start_exam", methods=["POST"])
@jwt_required()
def start_exam():
    
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'status': 'error','data': 'No user ID found'}), 401
    
    data = request.get_json(force=True)
    exam_group = data.get("exam")
    category = data.get("category")
    subcategory = data.get("subcategory")
    total = int(data.get("totalquestion", 10))
    time_min = int(data.get("time", 30))

    if not user_id or not exam_group:
        return jsonify({'status': 'error','data': "exam are required"}), 400

    full_questions = exam_questions(exam_group, category, subcategory, total)
    if not full_questions:
        return jsonify({'status': 'error','data': "no questions found for given filters"}), 404

    session_id = str(uuid.uuid4())
    session_doc = {
        "user_id": user_id,
        "exam": exam_group,
        "category": category,
        "subcategory": subcategory,
        "questions": full_questions,
        "answers": {},    
        "bookmarks": {},
        "started_at": now_utc(),
        "time_limit_minutes": time_min,
        "status": "in_progress"
    }
    current_app.db.collection(SESSIONS_COL).document(session_id).set(session_doc)

    questions_for_client = [sanitize_question_for_client(q) for q in full_questions]
    return jsonify({
        "status": "success",
        "data": {
        "session_id": session_id,
        "questions": questions_for_client,
        "time_limit_minutes": time_min
    }
    }), 200

@test_bp.route("/save_answer", methods=["POST"])
@jwt_required()
def save_answer():
    
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'status': 'error','data': 'No user ID found'}), 401
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    qid = data.get("question_id")
    selected = data.get("selected")

    if not session_id or not user_id or not qid or not selected:
        return jsonify({'status': 'error','data': "session_id, user_id, question_id, selected are required"}), 400

    session_ref = current_app.db.collection(SESSIONS_COL).document(session_id)
    session_snap = session_ref.get()
    if not session_snap.exists:
        return jsonify({'status': 'error','data': "session not found"}), 404

    session_doc = session_snap.to_dict()
    if session_doc.get("user_id") != user_id:
        return jsonify({'status': 'error','data': "user mismatch"}), 403

    # Check time limit before accepting answer
    started_at = session_doc.get("started_at")
    time_limit_min = int(session_doc.get("time_limit_minutes", 0))
    try:
        started_dt = started_at if isinstance(started_at, datetime.datetime) else started_at.to_datetime()
    except Exception:
        started_dt = started_at if isinstance(started_at, datetime.datetime) else now_utc()

    started_dt = ensure_utc_datetime(started_dt)

    _, remaining_seconds = get_elapsed_and_remaining(started_dt, time_limit_min)
    if remaining_seconds <= 0:
        # time expired -> auto-submit
        analysis = finalize_session_and_save(session_ref, session_doc)
        return jsonify({"auto_submitted": True, "analysis": analysis}), 200

    # Use transaction to write the single answer atomically
    def _tx_save(tx, ref):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise ValueError("session not found")
        s = snap.to_dict()
        if s.get("user_id") != user_id:
            raise ValueError("user mismatch")
        if s.get("status") == "submitted":
            raise ValueError("session already submitted")
        answers = s.get("answers", {}) or {}
        answers[qid] = {
            "selected": selected,
            "saved_at": now_utc(),
        }
        tx.update(ref, {"answers": answers})

    try:
        current_app.db.run_transaction(lambda tx: _tx_save(tx, session_ref))
    except ValueError as e:
        return jsonify({'status': 'error','data': str(e)}), 400
    except Exception:
        # Fallback non-transactional write (less safe)
        session_snap = session_ref.get()
        if not session_snap.exists:
            return jsonify({'status': 'error','data': "session not found"}), 404
        s = session_snap.to_dict()
        if s.get("status") == "submitted":
            return jsonify({'status': 'error','data': "session already submitted"}), 400
        answers = s.get("answers", {}) or {}
        answers[qid] = {
            "selected": selected,
            "saved_at": now_utc(),
        }
        session_ref.update({"answers": answers})

    return jsonify({"status": "success",
                    "data": {
                        "saved": True, 
                        "remaining_seconds": remaining_seconds}
                    }), 200

@test_bp.route("/session/<session_id>", methods=["GET"])
@jwt_required()
def get_session(session_id):
    
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'status': 'error','data': 'No user ID found'}), 401

    session_ref = current_app.db.collection(SESSIONS_COL).document(session_id)
    snap = session_ref.get()
    if not snap.exists:
        return jsonify({'status': 'error','data': "session not found"}), 404

    s = snap.to_dict()
    if s.get("user_id") != user_id:
        return jsonify({'status': 'error','data': "user mismatch"}), 403

    started_at = s.get("started_at")
    time_limit_min = int(s.get("time_limit_minutes", 0))
    try:
        started_dt = started_at if isinstance(started_at, datetime.datetime) else started_at.to_datetime()
    except Exception:
        started_dt = now_utc()

    # Normalize to aware UTC
    started_dt = ensure_utc_datetime(started_dt)

    elapsed_seconds, remaining_seconds = get_elapsed_and_remaining(started_dt, time_limit_min)

    questions_for_client = [sanitize_question_for_client(q) for q in s.get("questions", [])]
    return jsonify({
        "status": "success",
        "data": {
        "session_id": session_id,
        "status": s.get("status"),
        "questions": questions_for_client,
        "answers": s.get("answers", {}),
        "bookmarks": s.get("bookmarks", {}),
        "started_at": to_iso(started_dt),
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": remaining_seconds
        }}), 200

@test_bp.route("/submit", methods=["POST"])
@jwt_required()
def submit_exam():
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'status': 'error','data': 'No user ID found'}), 401
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    if not session_id or not user_id:
        return jsonify({"error": "session_id and user_id are required"}), 400

    session_ref = current_app.db.collection(SESSIONS_COL).document(session_id)
    snap = session_ref.get()
    if not snap.exists:
        return jsonify({"error": "session not found"}), 404

    s = snap.to_dict()
    if s.get("user_id") != user_id:
        return jsonify({"error": "user mismatch"}), 403
    if s.get("status") == "submitted":
        # return existing analysis if already submitted
        analysis = s.get("analysis")
        if isinstance(analysis.get("date"), datetime.datetime):
            analysis["date"] = to_iso(analysis["date"])
        return jsonify({"already_submitted": True, "analysis": analysis}), 200

    # Check time limit; if expired, finalize anyway.
    started_at = s.get("started_at")
    time_limit_min = int(s.get("time_limit_minutes", 0))
    try:
        started_dt = started_at if isinstance(started_at, datetime.datetime) else started_at.to_datetime()
    except Exception:
        started_dt = now_utc()

    # Normalize to aware UTC
    started_dt = ensure_utc_datetime(started_dt)

    _, remaining_seconds = get_elapsed_and_remaining(started_dt, time_limit_min)
    if remaining_seconds <= 0:
        analysis = finalize_session_and_save(session_ref, s)
        return jsonify({"auto_submitted": True, "analysis": analysis}), 200

    # Otherwise finalize normally
    analysis = finalize_session_and_save(session_ref, s)
    return jsonify({"saved": True, "analysis": analysis}), 200

# Bookmark endpoint (unchanged)
@test_bp.route("/bookmark", methods=["POST"])
@jwt_required()
def set_bookmark():
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'status': 'error','data': 'No user ID found'}), 401

    data = request.get_json(force=True)
    session_id = data.get("session_id")
    qid = data.get("question_id")
    bookmark_value = data.get("bookmark")  # must be True or False

    if session_id is None or qid is None or bookmark_value is None:
        return jsonify({'status': 'error','data': "session_id, question_id, bookmark are required"}), 400

    session_ref = current_app.db.collection(SESSIONS_COL).document(session_id)

    def _tx_update(tx, ref):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise ValueError("session not found")
        s = snap.to_dict()
        if s.get("user_id") != user_id:
            raise ValueError("user mismatch")

        bookmarks = s.get("bookmarks", {}) or {}
        if bookmark_value is True:
            bookmarks[qid] = True
        else:
            bookmarks.pop(qid, None)

        tx.update(ref, {"bookmarks": bookmarks})

    try:
        # This mirrors your save_answer style
        current_app.db.run_transaction(lambda tx: _tx_update(tx, session_ref))
    except ValueError as e:
        # surface correct HTTP codes for common problems
        msg = str(e).lower()
        if "mismatch" in msg:
            return jsonify({'status': 'error','data': "user mismatch"}), 403
        return jsonify({'status': 'error','data': "session not found"}), 404
    except Exception as e:
        # fallback: non-transactional update (less safe)
        current_app.logger.exception(f"Bookmark update failed for session {session_id}: {e}")
        snap = session_ref.get()
        if not snap.exists:
            return jsonify({'status': 'error','data': "session not found"}), 404
        s = snap.to_dict()
        if s.get("user_id") != user_id:
            return jsonify({'status': 'error','data': "user mismatch"}), 403
        bookmarks = s.get("bookmarks", {}) or {}
        if bookmark_value is True:
            bookmarks[qid] = True
        else:
            bookmarks.pop(qid, None)
        try:
            session_ref.update({"bookmarks": bookmarks})
        except Exception:
            current_app.logger.exception("Fallback update failed")
            return jsonify({'status': 'error','data': "failed to update bookmark"}), 500

    return jsonify({'status': 'success','data':bool(bookmark_value)}), 200


@test_bp.route("/exam_history", methods=["GET"])
@jwt_required()
def exam_history():
    
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'status': 'error','data': "No user ID found"}), 401

    ongoing = []
    completed = []

    # --- Ongoing sessions ---
    try:
        sess_q = current_app.db.collection(SESSIONS_COL).where("user_id", "==", user_id).where("status", "==", "in_progress")
        sess_snaps = sess_q.stream()
    except Exception:
        # fallback to fetch all sessions for user then filter
        sess_snaps = current_app.db.collection(SESSIONS_COL).where("user_id", "==", user_id).stream()

    for snap in sess_snaps:
        s = snap.to_dict() or {}
        if s.get("status") != "in_progress":
            continue

        # read started_at (can be Firestore Timestamp or datetime)
        started_at = s.get("started_at")
        try:
            started_dt = started_at if isinstance(started_at, datetime.datetime) else (started_at.to_datetime() if hasattr(started_at, "to_datetime") else None)
        except Exception:
            started_dt = None
        started_dt = ensure_utc_datetime(started_dt) if started_dt is not None else now_utc()

        time_limit_min = int(s.get("time_limit_minutes", 0))
        elapsed_seconds, remaining_seconds = get_elapsed_and_remaining(started_dt, time_limit_min)

        ongoing.append({
            "session_id": snap.id if hasattr(snap, "id") else getattr(snap, "reference", {}).get("id", None),
            "exam": s.get("exam"),
            "category": s.get("category"),
            "subcategory": s.get("subcategory"),
            "status": s.get("status"),
            "examDate": to_iso(started_dt),
            "started_at": to_iso(started_dt),
            "elapsed_seconds": elapsed_seconds,
            "remaining_seconds": remaining_seconds,
            "time_limit_minutes": time_limit_min,
            "questions_count": len(s.get("questions", []) or [])
        })

    # --- Completed exams (from user's assessmentHistory) ---
    hist_coll = current_app.db.collection(USERS_COL).document(user_id).collection("assessmentHistory")
    try:
        hist_snaps = hist_coll.stream()
    except Exception:
        hist_snaps = []

    for h in hist_snaps:
        doc = h.to_dict() or {}

        # finished date (stored as "date" by finalize_session_and_save)
        date_val = doc.get("date")
        try:
            date_dt = date_val if isinstance(date_val, datetime.datetime) else (date_val.to_datetime() if hasattr(date_val, "to_datetime") else None)
        except Exception:
            date_dt = None
        date_dt = ensure_utc_datetime(date_dt) if date_dt is not None else None

        # examDate: prefer stored "examDate", fallback to "date", then None
        exam_date_val = doc.get("examDate")
        try:
            exam_dt = exam_date_val if isinstance(exam_date_val, datetime.datetime) else (exam_date_val.to_datetime() if hasattr(exam_date_val, "to_datetime") else None)
        except Exception:
            exam_dt = None

        if exam_dt is None and date_dt is not None:
            # if no explicit examDate, use the finished date as fallback
            exam_dt = date_dt

        exam_dt = ensure_utc_datetime(exam_dt) if exam_dt is not None else None

        completed.append({
            "score": doc.get("score"),
            "examDate": to_iso(exam_dt) if exam_dt is not None else None,
            "date": to_iso(date_dt) if date_dt is not None else None,
            "totalQuestions": doc.get("totalQuestions"),
            "attempted": doc.get("attempted"),
            "correct": doc.get("correct"),
            "incorrect": doc.get("incorrect"),
            "unanswered": doc.get("unanswered"),
            "timeSpent": doc.get("timeSpent"),
            "category": doc.get("category"),
            "subcategory": doc.get("subcategory"),
            "status": doc.get("status", "completed")
        })

    # sort: ongoing by started_at desc, completed by date desc (string ISO sorts correctly)
    try:
        ongoing.sort(key=lambda x: x.get("started_at") or "", reverse=True)
    except Exception:
        pass
    try:
        completed.sort(key=lambda x: x.get("date") or "", reverse=True)
    except Exception:
        pass

    return jsonify({
                    "status": "success",
                    "data": {
                        "ongoing": ongoing, 
                        "completed": completed
                    }}), 200
