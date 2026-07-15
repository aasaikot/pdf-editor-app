import os
import io
import json
import tempfile
import re
from flask import Flask, render_template, request, send_file, jsonify
import pikepdf
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# ============================================================
# FIREBASE ADMIN SDK SETUP
# ============================================================

firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')

if firebase_creds_json:
    try:
        cred_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print(f"✅ Firebase connected! Project: {cred_dict.get('project_id')}")
    except Exception as e:
        print(f"❌ Firebase error: {e}")
        db = None
else:
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase connected with local file!")
    except:
        print("⚠️ Firebase not configured. Using mock mode.")
        db = None

# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_pdf():
    try:
        # Get form data
        form_data = {
            'surname': request.form.get('surname', '').strip(),
            'givenName': request.form.get('givenName', '').strip(),
            'nationalId': request.form.get('nationalId', '').strip(),
            'passportNo': request.form.get('passportNo', '').strip(),
            'phoneNo': request.form.get('phoneNo', '').strip(),
            'email': request.form.get('email', '').strip()
        }
        
        # Validate
        for key, value in form_data.items():
            if not value:
                return jsonify({'error': f'{key} is required'}), 400
        
        # Get PDF
        if 'pdf' not in request.files:
            return jsonify({'error': 'No PDF file uploaded'}), 400
        
        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({'error': 'No PDF file selected'}), 400
        
        # Save to Firestore
        if db:
            try:
                db.collection('savedForms').add({
                    **form_data,
                    'createdAt': firestore.SERVER_TIMESTAMP
                })
                print("✅ Saved to Firestore")
            except Exception as e:
                print(f"Firestore save error: {e}")
        
        # Process PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_input:
            pdf_file.save(temp_input.name)
            input_path = temp_input.name
        
        pdf = pikepdf.Pdf.open(input_path)
        
        replacements = {
            "NEPUR": form_data['surname'],
            "MD MUHIN AHMED": form_data['givenName'],
            "3258351703": form_data['nationalId'],
            "A05155542": form_data['passportNo'],
            "01351452093": form_data['phoneNo'],
            "WAN.GD.U1.6.7@GMAIL.COM": form_data['email']
        }
        
        for page in pdf.pages:
            if "/Contents" in page:
                contents = page["/Contents"]
                if not isinstance(contents, list):
                    contents = [contents]
                
                new_contents = []
                for cs in contents:
                    try:
                        data = cs.read_bytes()
                        try:
                            text = data.decode('utf-8', errors='ignore')
                            for old, new in replacements.items():
                                text = text.replace(old, new)
                            data = text.encode('utf-8')
                        except:
                            pass
                        new_contents.append(pdf.make_stream(data))
                    except:
                        new_contents.append(cs)
                
                page["/Contents"] = new_contents
        
        output = io.BytesIO()
        pdf.save(output)
        pdf.close()
        output.seek(0)
        
        os.unlink(input_path)
        
        return send_file(
            output,
            as_attachment=True,
            download_name='visa_edited.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'firebase': 'connected' if db else 'disconnected'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
