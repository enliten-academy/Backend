from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import datetime
import uuid
import base64
from services.exam_evaluator import ExamEvaluator

mains_bp = Blueprint('mains', __name__)

# Collection names
MAINSTEST_COL = "mainstest"
QUESTIONS_SUBCOL = "questions"
ANSWERS_SUBCOL = "answers"
EVALUATIONS_SUBCOL = "evaluations"

# Initialize exam evaluator
exam_evaluator = ExamEvaluator()

def now_utc():
    """Return an offset-aware UTC datetime."""
    return datetime.datetime.now(datetime.timezone.utc)

def ensure_utc_datetime(dt):
    """Convert any datetime to UTC-aware datetime."""
    if dt is None:
        return now_utc()
    try:
        to_dt = getattr(dt, "to_datetime", None)
        if callable(to_dt):
            dt = to_dt()
    except Exception:
        pass
    
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    
    return now_utc()

def to_iso(dt):
    """Return ISO 8601 string in Zulu (UTC) form."""
    d = ensure_utc_datetime(dt)
    return d.isoformat().replace("+00:00", "Z")


@mains_bp.route("/upload_question", methods=["POST"])
@jwt_required()
def upload_question():
    """    Upload a question PDF and optionally model answer PDF for mains test.   """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
        
        data = request.get_json(force=True)
        question_pdf = data.get("question_pdf")
        model_answer_pdf = data.get("answer_pdf")
        exam_name = data.get("exam_name")
        exam_start_datetime = data.get("exam_start_datetime")
        time_duration = data.get("time_duration")
        total_questions = data.get("total_questions")
        total_marks = data.get("total_marks", 100)
        
        if not all([question_pdf, exam_name, exam_start_datetime, time_duration, total_questions]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: question_pdf, exam_name, exam_start_datetime, time_duration, total_questions'
            }), 400
        
        try:
            base64.b64decode(question_pdf)
            if model_answer_pdf:
                base64.b64decode(model_answer_pdf)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': 'Invalid base64 encoded PDF'
            }), 400
        
        # Parse exam start datetime
        try:
            if isinstance(exam_start_datetime, str):
                exam_start_dt = datetime.datetime.fromisoformat(exam_start_datetime.replace('Z', '+00:00'))
            else:
                exam_start_dt = ensure_utc_datetime(exam_start_datetime)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Invalid exam_start_datetime format. Use ISO 8601 format: {str(e)}'
            }), 400
        
        # Validate time_duration, total_questions, and total_marks are integers
        try:
            time_duration = int(time_duration)
            total_questions = int(total_questions)
            total_marks = int(total_marks)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': 'time_duration, total_questions, and total_marks must be integers'
            }), 400
        
        # Generate unique test ID
        test_id = str(uuid.uuid4())
        
        # Create the main test document
        test_doc = {
            "test_id": test_id,
            "user_id": user_id,
            "created_at": now_utc(),
            "status": "active"
        }
        
        # Create the question document
        question_doc = {
            "question_pdf": question_pdf,
            "model_answer_pdf": model_answer_pdf,  # Can be None
            "exam_name": exam_name,
            "exam_start_datetime": exam_start_dt,
            "time_duration": time_duration,  # in minutes
            "total_questions": total_questions,
            "total_marks": total_marks,
            "uploaded_at": now_utc(),
            "uploaded_by": user_id
        }
        
        # Save to Firestore
        # Main document
        main_ref = current_app.db.collection(MAINSTEST_COL).document(test_id)
        main_ref.set(test_doc)
        
        # Question subcollection
        question_ref = main_ref.collection(QUESTIONS_SUBCOL).document("question_data")
        question_ref.set(question_doc)
        
        return jsonify({
            'status': 'success',
            'message': 'Question PDF uploaded successfully',
            'data': {
                'test_id': test_id,
                'exam_name': exam_name,
                'exam_start_datetime': to_iso(exam_start_dt),
                'time_duration': time_duration,
                'total_questions': total_questions,
                'total_marks': total_marks,
                'has_model_answer': model_answer_pdf is not None
            }
        }), 201
        
    except Exception as e:
        current_app.logger.exception(f"Error uploading question PDF: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@mains_bp.route("/save_answer", methods=["POST"])
@jwt_required()
def save_answer():
    """   Submit answer PDF for a mains test.  """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
        
        data = request.get_json(force=True)
        
        # Validate required fields
        test_id = data.get("test_id")
        answer_pdf = data.get("answer_pdf")
        bookmarked_pages = data.get("bookmarked_pages", [])
        test_end_time = data.get("test_end_time")
        
        if not all([test_id, answer_pdf]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: test_id, answer_pdf'
            }), 400
        
        # Validate PDF is base64 encoded
        try:
            base64.b64decode(answer_pdf)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': 'Invalid base64 encoded PDF'
            }), 400
        
        # Verify test exists and belongs to user
        test_ref = current_app.db.collection(MAINSTEST_COL).document(test_id)
        test_snap = test_ref.get()
        
        if not test_snap.exists:
            return jsonify({
                'status': 'error',
                'message': 'Test not found'
            }), 404
        
        test_data = test_snap.to_dict()
        if test_data.get("user_id") != user_id:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized access to this test'
            }), 403
        
        # Parse test end time
        if test_end_time:
            try:
                if isinstance(test_end_time, str):
                    end_dt = datetime.datetime.fromisoformat(test_end_time.replace('Z', '+00:00'))
                else:
                    end_dt = ensure_utc_datetime(test_end_time)
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid test_end_time format. Use ISO 8601 format: {str(e)}'
                }), 400
        else:
            end_dt = now_utc()
        
        # Validate bookmarked_pages is a list
        if not isinstance(bookmarked_pages, list):
            return jsonify({
                'status': 'error',
                'message': 'bookmarked_pages must be an array of page numbers'
            }), 400
        
        # Create the answer document
        answer_doc = {
            "answer_pdf": answer_pdf,
            "bookmarked_pages": bookmarked_pages,
            "test_end_time": end_dt,
            "submitted_at": now_utc(),
            "submitted_by": user_id
        }
        
        # Save to Firestore
        answer_ref = test_ref.collection(ANSWERS_SUBCOL).document("answer_data")
        answer_ref.set(answer_doc)
        
        # Update main test document status
        test_ref.update({
            "status": "submitted",
            "submitted_at": now_utc()
        })
        
        # Trigger evaluation
        evaluation_data = None
        try:
            # Get question data
            question_ref = test_ref.collection(QUESTIONS_SUBCOL).document("question_data")
            question_snap = question_ref.get()
            
            if question_snap.exists:
                question_data = question_snap.to_dict()
                question_pdf = question_data.get("question_pdf")
                model_answer_pdf = question_data.get("model_answer_pdf")
                test_total_marks = question_data.get("total_marks", 100)
                
                if question_pdf:
                    evaluation_data = exam_evaluator.evaluate_with_direct_ocr(
                        question_pdf_base64=question_pdf,
                        answer_pdf_base64=answer_pdf,
                        model_answer_pdf_base64=model_answer_pdf,
                        total_marks=test_total_marks
                    )
                    
                    if evaluation_data and "error" not in evaluation_data:
                        # Save evaluation
                        eval_ref = test_ref.collection(EVALUATIONS_SUBCOL).document("latest")
                        eval_ref.set({
                            **evaluation_data,
                            "evaluated_at": now_utc(),
                            "user_id": user_id,
                            "test_id": test_id
                        })
                        
                        # Update test status to graded
                        test_ref.update({
                            "status": "graded",
                            "marks_obtained": evaluation_data.get("marks_obtained"),
                            "total_marks": evaluation_data.get("total_marks"),
                            "percentage": evaluation_data.get("percentage"),
                            "grade": evaluation_data.get("grade")
                        })
        except Exception as eval_e:
            current_app.logger.exception(f"Error during automatic evaluation: {str(eval_e)}")
        
        return jsonify({
            'status': 'success',
            'message': 'Answer PDF submitted successfully' + (' and evaluated' if evaluation_data else ''),
            'data': {
                'test_id': test_id,
                'test_end_time': to_iso(end_dt),
                'bookmarked_pages': bookmarked_pages,
                'evaluation': evaluation_data
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f"Error submitting answer PDF: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@mains_bp.route("/test/<test_id>", methods=["GET"])
@jwt_required()
def get_test(test_id):
    """    Get test details including question and answer data.    """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
        
        # Get main test document
        test_ref = current_app.db.collection(MAINSTEST_COL).document(test_id)
        test_snap = test_ref.get()
        
        if not test_snap.exists:
            return jsonify({
                'status': 'error',
                'message': 'Test not found'
            }), 404
        
        test_data = test_snap.to_dict()
        if test_data.get("user_id") != user_id:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized access to this test'
            }), 403
        
        # Get question data
        question_ref = test_ref.collection(QUESTIONS_SUBCOL).document("question_data")
        question_snap = question_ref.get()
        question_data = question_snap.to_dict() if question_snap.exists else None
        
        # Get answer data
        answer_ref = test_ref.collection(ANSWERS_SUBCOL).document("answer_data")
        answer_snap = answer_ref.get()
        answer_data = answer_snap.to_dict() if answer_snap.exists else None
        
        # Prepare response
        response_data = {
            "test_id": test_id,
            "status": test_data.get("status"),
            "created_at": to_iso(test_data.get("created_at")),
        }
        
        if question_data:
            response_data["question"] = {
                "question_pdf": question_data.get("question_pdf"),
                "model_answer_pdf": question_data.get("model_answer_pdf"),
                "exam_name": question_data.get("exam_name"),
                "exam_start_datetime": to_iso(question_data.get("exam_start_datetime")),
                "time_duration": question_data.get("time_duration"),
                "total_questions": question_data.get("total_questions"),
                "total_marks": question_data.get("total_marks", 100),
                "uploaded_at": to_iso(question_data.get("uploaded_at"))
            }
        
        if answer_data:
            response_data["answer"] = {
                "answer_pdf": answer_data.get("answer_pdf"),
                "bookmarked_pages": answer_data.get("bookmarked_pages", []),
                "test_end_time": to_iso(answer_data.get("test_end_time")),
                "submitted_at": to_iso(answer_data.get("submitted_at"))
            }
        
        # Get evaluation data
        eval_ref = test_ref.collection(EVALUATIONS_SUBCOL).document("latest")
        eval_snap = eval_ref.get()
        if eval_snap.exists:
            eval_data = eval_snap.to_dict()
            if "evaluated_at" in eval_data:
                eval_data["evaluated_at"] = to_iso(eval_data["evaluated_at"])
            response_data["evaluation"] = eval_data
        
        return jsonify({
            'status': 'success',
            'data': response_data
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f"Error getting test: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@mains_bp.route("/tests", methods=["GET"])
@jwt_required()
def get_all_tests():
    """    Get all tests for the current user.    """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
        
        # Query all tests for this user
        tests_query = current_app.db.collection(MAINSTEST_COL).where("user_id", "==", user_id)
        tests_snaps = tests_query.stream()
        
        tests = []
        for test_snap in tests_snaps:
            test_data = test_snap.to_dict()
            test_id = test_snap.id
            
            # Get question data
            question_ref = test_snap.reference.collection(QUESTIONS_SUBCOL).document("question_data")
            question_snap = question_ref.get()
            question_data = question_snap.to_dict() if question_snap.exists else {}
            
            # Get answer data (check if submitted)
            answer_ref = test_snap.reference.collection(ANSWERS_SUBCOL).document("answer_data")
            answer_snap = answer_ref.get()
            has_answer = answer_snap.exists
            
            # Get evaluation data (check if graded)
            eval_ref = test_snap.reference.collection(EVALUATIONS_SUBCOL).document("latest")
            eval_snap = eval_ref.get()
            eval_data = eval_snap.to_dict() if eval_snap.exists else {}
            
            tests.append({
                "test_id": test_id,
                "exam_name": question_data.get("exam_name"),
                "exam_start_datetime": to_iso(question_data.get("exam_start_datetime")) if question_data.get("exam_start_datetime") else None,
                "time_duration": question_data.get("time_duration"),
                "total_questions": question_data.get("total_questions"),
                "total_marks": question_data.get("total_marks", 100),
                "marks_obtained": test_data.get("marks_obtained") or eval_data.get("marks_obtained"),
                "grade": test_data.get("grade") or eval_data.get("grade"),
                "status": test_data.get("status"),
                "created_at": to_iso(test_data.get("created_at")),
                "has_answer": has_answer,
                "has_evaluation": eval_snap.exists
            })
        
        # Sort by created_at descending
        tests.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return jsonify({
            'status': 'success',
            'data': tests
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f"Error getting tests: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500

@mains_bp.route("/bookmark", methods=["POST"])
@jwt_required()
def toggle_bookmark():
    """   Toggle bookmark for a specific page in a test. """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
        
        data = request.get_json(force=True)
        
        # Validate required fields
        test_id = data.get("test_id")
        page_number = data.get("page_number")
        bookmark = data.get("bookmark")
        
        if test_id is None or page_number is None or bookmark is None:
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: test_id, page_number, bookmark'
            }), 400
        
        # Validate page_number is an integer
        try:
            page_number = int(page_number)
            if page_number < 1:
                raise ValueError("Page number must be positive")
        except (ValueError, TypeError) as e:
            return jsonify({
                'status': 'error',
                'message': f'Invalid page_number: must be a positive integer'
            }), 400
        
        # Validate bookmark is a boolean
        if not isinstance(bookmark, bool):
            return jsonify({
                'status': 'error',
                'message': 'bookmark must be a boolean (true or false)'
            }), 400
        
        # Verify test exists and belongs to user
        test_ref = current_app.db.collection(MAINSTEST_COL).document(test_id)
        test_snap = test_ref.get()
        
        if not test_snap.exists:
            return jsonify({
                'status': 'error',
                'message': 'Test not found'
            }), 404
        
        test_data = test_snap.to_dict()
        if test_data.get("user_id") != user_id:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized access to this test'
            }), 403
        
        # Get or create answer document
        answer_ref = test_ref.collection(ANSWERS_SUBCOL).document("answer_data")
        answer_snap = answer_ref.get()
        
        if answer_snap.exists:
            answer_data = answer_snap.to_dict()
            bookmarked_pages = answer_data.get("bookmarked_pages", [])
        else:
            # Create answer document if it doesn't exist
            bookmarked_pages = []
        
        # Update bookmarked pages
        if bookmark:
            # Add bookmark if not already present
            if page_number not in bookmarked_pages:
                bookmarked_pages.append(page_number)
                bookmarked_pages.sort()  # Keep sorted
                action = "added"
            else:
                action = "already_bookmarked"
        else:
            # Remove bookmark if present
            if page_number in bookmarked_pages:
                bookmarked_pages.remove(page_number)
                action = "removed"
            else:
                action = "not_bookmarked"
        
        # Save updated bookmarks
        if answer_snap.exists:
            # Update existing document
            answer_ref.update({
                "bookmarked_pages": bookmarked_pages,
                "last_updated": now_utc()
            })
        else:
            # Create new document with bookmarks
            answer_ref.set({
                "bookmarked_pages": bookmarked_pages,
                "created_at": now_utc(),
                "last_updated": now_utc()
            })
        
        return jsonify({
            'status': 'success',
            'message': f'Bookmark {action}',
            'data': {
                'test_id': test_id,
                'page_number': page_number,
                'bookmarked': bookmark and action != "not_bookmarked",
                'bookmarked_pages': bookmarked_pages,
                'action': action
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f"Error toggling bookmark: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500


@mains_bp.route("/bookmarks/<test_id>", methods=["GET"])
@jwt_required()
def get_bookmarks(test_id):
    """   Get all bookmarked pages for a test.  """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
        
        # Verify test exists and belongs to user
        test_ref = current_app.db.collection(MAINSTEST_COL).document(test_id)
        test_snap = test_ref.get()
        
        if not test_snap.exists:
            return jsonify({
                'status': 'error',
                'message': 'Test not found'
            }), 404
        
        test_data = test_snap.to_dict()
        if test_data.get("user_id") != user_id:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized access to this test'
            }), 403
        
        # Get answer document
        answer_ref = test_ref.collection(ANSWERS_SUBCOL).document("answer_data")
        answer_snap = answer_ref.get()
        
        if answer_snap.exists:
            answer_data = answer_snap.to_dict()
            bookmarked_pages = answer_data.get("bookmarked_pages", [])
        else:
            bookmarked_pages = []
        
        return jsonify({
            'status': 'success',
            'data': {
                'test_id': test_id,
                'bookmarked_pages': bookmarked_pages,
                'total_bookmarks': len(bookmarked_pages)
            }
        }), 200
        
    except Exception as e:
        current_app.logger.exception(f"Error getting bookmarks: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500

@mains_bp.route("/evaluate_test", methods=["POST"])
@jwt_required()
def evaluate_test():
    """    Manually trigger evaluation for a test.    """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
        
        data = request.get_json(force=True)
        test_id = data.get("test_id")
        
        if not test_id:
            return jsonify({'status': 'error', 'message': 'test_id is required'}), 400
            
        test_ref = current_app.db.collection(MAINSTEST_COL).document(test_id)
        test_snap = test_ref.get()
        
        if not test_snap.exists:
            return jsonify({'status': 'error', 'message': 'Test not found'}), 404
            
        test_data = test_snap.to_dict()
        if test_data.get("user_id") != user_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
            
        # Get answer data
        answer_ref = test_ref.collection(ANSWERS_SUBCOL).document("answer_data")
        answer_snap = answer_ref.get()
        if not answer_snap.exists:
            return jsonify({'status': 'error', 'message': 'No answer submitted for this test'}), 400
            
        answer_data = answer_snap.to_dict()
        answer_pdf = answer_data.get("answer_pdf")
        
        # Get question data
        question_ref = test_ref.collection(QUESTIONS_SUBCOL).document("question_data")
        question_snap = question_ref.get()
        if not question_snap.exists:
            return jsonify({'status': 'error', 'message': 'Question data missing'}), 404
            
        question_data = question_snap.to_dict()
        question_pdf = question_data.get("question_pdf")
        model_answer_pdf = question_data.get("model_answer_pdf")
        total_marks = question_data.get("total_marks", 100)
        
        # Perform evaluation
        evaluation_data = exam_evaluator.evaluate_with_direct_ocr(
            question_pdf_base64=question_pdf,
            answer_pdf_base64=answer_pdf,
            model_answer_pdf_base64=model_answer_pdf,
            total_marks=total_marks
        )
        
        if evaluation_data and "error" not in evaluation_data:
            # Save evaluation
            eval_ref = test_ref.collection(EVALUATIONS_SUBCOL).document("latest")
            eval_ref.set({
                **evaluation_data,
                "evaluated_at": now_utc(),
                "user_id": user_id,
                "test_id": test_id
            })
            
            # Update test status
            test_ref.update({
                "status": "graded",
                "marks_obtained": evaluation_data.get("marks_obtained"),
                "total_marks": evaluation_data.get("total_marks"),
                "percentage": evaluation_data.get("percentage"),
                "grade": evaluation_data.get("grade")
            })
            
            return jsonify({
                'status': 'success',
                'message': 'Evaluation completed successfully',
                'data': evaluation_data
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': evaluation_data.get("error", "Evaluation failed")
            }), 500
        
    except Exception as e:
        current_app.logger.exception(f"Error in evaluate_test: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@mains_bp.route("/result/<test_id>", methods=["GET"])
@jwt_required()
def get_result(test_id):
    """    Get evaluation results for a test.   """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'No user ID found'}), 401
            
        test_ref = current_app.db.collection(MAINSTEST_COL).document(test_id)
        test_snap = test_ref.get()
        if not test_snap.exists:
            return jsonify({'status': 'error', 'message': 'Test not found'}), 404
            
        test_data = test_snap.to_dict()
        if test_data.get("user_id") != user_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
            
        eval_ref = test_ref.collection(EVALUATIONS_SUBCOL).document("latest")
        eval_snap = eval_ref.get()
        if not eval_snap.exists:
            return jsonify({'status': 'error', 'message': 'Evaluation not found'}), 404
            
        eval_data = eval_snap.to_dict()
        if "evaluated_at" in eval_data:
            eval_data["evaluated_at"] = to_iso(eval_data["evaluated_at"])
            
        return jsonify({
            'status': 'success',
            'data': eval_data
        }), 200
    except Exception as e:
        current_app.logger.exception(f"Error getting evaluation: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
