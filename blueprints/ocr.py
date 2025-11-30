from flask import Blueprint, request, jsonify
from flask.views import MethodView
from flask_jwt_extended import jwt_required, get_jwt_identity

ocr_bp = Blueprint('ocr', __name__)

class OCRAPI(MethodView):
    @jwt_required()
    def post(self):
        from app import ocr_service
        try:
            user_id = get_jwt_identity()
            print(f"[OCR] User ID: {user_id}")
            
            data = request.json
            print(f"[OCR] Request data keys: {data.keys() if data else 'None'}")
            
            if not data:
                print("[OCR] Error: No JSON data provided")
                return jsonify({"error": "No JSON data provided"}), 400
            
            base64File = data.get("file")
            print(f"[OCR] Base64 file length: {len(base64File) if base64File else 0}")

            if not base64File:
                print("[OCR] Error: No file provided")
                return jsonify({"error": "No file provided"}), 400

            print("[OCR] Calling OCR service...")
            text = ocr_service.extract_text(base64File)
            print(f"[OCR] Extracted text length: {len(text)}")
            return jsonify({'data': text, 'user_id': user_id}), 200
        except Exception as e:
            print(f"[OCR] Exception: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

ocr_view = OCRAPI.as_view("ocr_api")
ocr_bp.add_url_rule("", view_func=ocr_view, methods=["POST"])
