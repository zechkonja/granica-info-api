from flask import Flask, jsonify, request, send_file  
from flask_cors import CORS    
from datetime import datetime, timedelta    
import json    
import os  
import re  
from pathlib import Path  
  
# Screenshots directory setup - ABSOLUTE PATH  
SCREENSHOTS_DIR = Path('/Users/nemanjanikolic/Documents/granica/current_state')  
  
# Border IDs  
BORDER_IDS = ['batrovci-bajakovo', 'bajakovo-batrovci', 'sid-tovarnik', 'tovarnik-sid']    
  
# Create directories if they don't exist  
for border_id in BORDER_IDS:    
    (SCREENSHOTS_DIR / border_id).mkdir(parents=True, exist_ok=True)  
    
app = Flask(__name__)    
    
CORS(app, resources={    
    r"/api/*": {    
        "origins": ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173", "https://granicainfo.netlify.app"],    
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],    
        "allow_headers": ["Content-Type", "Authorization"],    
        "supports_credentials": True    
    }    
})    
    
def load_data():    
    """Load border crossing data from JSON file"""    
    try:    
        with open('border_data.json', 'r', encoding='utf-8') as f:    
            return json.load(f)    
    except FileNotFoundError:    
        return {}    
    
def load_model_predictions():    
    """Load ML model predictions"""    
    try:    
        with open('model_predictions.json', 'r', encoding='utf-8') as f:    
            return json.load(f)    
    except FileNotFoundError:    
        return {}    
  
def parse_camera_filename(filename):  
    """  
    Parse camera filename in format: BAJ_01_2026-02-01_00-04-45.jpg  
    or BAJ_02_A_2026-02-01_03-11-05.jpg  
    Returns dict with parsed info or None if invalid  
    """  
    # Pattern: PREFIX_NUMBER_[LETTER_]DATE_TIME.ext  
    pattern = r'^([A-Z]+)_(\d+)_?([A-Z])?_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.(jpg|jpeg|png)$'  
    match = re.match(pattern, filename, re.IGNORECASE)  
      
    if not match:  
        return None  
      
    prefix, camera_num, letter, date_str, time_str, ext = match.groups()  
      
    # Parse timestamp  
    try:  
        timestamp_str = f"{date_str} {time_str.replace('-', ':')}"  
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')  
    except:  
        return None  
      
    return {  
        'prefix': prefix,  
        'camera_number': camera_num,  
        'letter': letter or '',  
        'date': date_str,  
        'time': time_str,  
        'timestamp': timestamp,  
        'filename': filename,  
        'extension': ext  
    }  
  
@app.route('/api/cameras/<border_id>', methods=['GET', 'OPTIONS'])  
def get_border_cameras(border_id):  
    """Get latest camera screenshots for a border - reads all images from folder"""  
    if request.method == 'OPTIONS':  
        return '', 204  
      
    if border_id not in BORDER_IDS:  
        return jsonify({'error': 'Invalid border ID'}), 404  
      
    border_dir = SCREENSHOTS_DIR / border_id  
      
    if not border_dir.exists():  
        return jsonify({  
            'border_id': border_id,  
            'cameras': [],  
            'message': 'No camera images available',  
            'last_updated': None  
        })  
      
    # Get all image files that match the naming pattern (any prefix)  
    all_files = []  
    for file_path in border_dir.iterdir():  
        if file_path.is_file():  
            parsed = parse_camera_filename(file_path.name)  
            if parsed:  # Accept any valid image, regardless of prefix  
                parsed['file_path'] = file_path  
                all_files.append(parsed)  
      
    if not all_files:  
        return jsonify({  
            'border_id': border_id,  
            'cameras': [],  
            'message': 'No camera images available',  
            'last_updated': None  
        })  
      
    # Sort by timestamp (newest first)  
    all_files.sort(key=lambda x: x['timestamp'], reverse=True)  
      
    # Group by prefix + camera number to get unique cameras  
    cameras_dict = {}  
    for file_info in all_files:  
        # Create unique key: prefix_number_letter (e.g., "BAJ_01", "BAT_02_A")  
        cam_key = f"{file_info['prefix']}_{file_info['camera_number']}{file_info['letter']}"  
        if cam_key not in cameras_dict:  
            cameras_dict[cam_key] = file_info  
      
    # Convert to list and sort by prefix and camera number  
    cameras_list = list(cameras_dict.values())  
    cameras_list.sort(key=lambda x: (x['prefix'], x['camera_number'], x['letter']))  
      
    # Take up to 4 most recent unique cameras (2 from each side if available)  
    latest_cameras = cameras_list[:4]  
      
    # Build response  
    cameras = []  
    for idx, cam_info in enumerate(latest_cameras, 1):  
        # Create descriptive camera name  
        cam_label = f"{cam_info['prefix']} {cam_info['camera_number']}"  
        if cam_info['letter']:  
            cam_label += f" {cam_info['letter']}"  
          
        cameras.append({  
            'id': f"camera_{cam_info['prefix']}_{cam_info['camera_number']}_{cam_info['letter']}",  
            'name': f"Camera {cam_label}",  
            'url': f'/api/camera-image/{border_id}/{cam_info["filename"]}',  
            'filename': cam_info['filename'],  
            'timestamp': cam_info['timestamp'].isoformat(),  
            'camera_number': cam_info['camera_number'],  
            'camera_letter': cam_info['letter'],  
            'camera_prefix': cam_info['prefix']  
        })  
      
    return jsonify({  
        'border_id': border_id,  
        'cameras': cameras,  
        'last_updated': cameras[0]['timestamp'] if cameras else None  
    })  
  
@app.route('/api/camera-image/<border_id>/<filename>', methods=['GET'])  
def serve_camera_image(border_id, filename):  
    """Serve camera image file"""  
    if border_id not in BORDER_IDS:  
        return jsonify({'error': 'Invalid border ID'}), 404  
      
    # Validate filename format for security  
    parsed = parse_camera_filename(filename)  
    if not parsed:  
        return jsonify({'error': 'Invalid filename format'}), 400  
      
    border_dir = SCREENSHOTS_DIR / border_id  
    image_path = border_dir / filename  
      
    if not image_path.exists() or not image_path.is_file():  
        return jsonify({'error': 'Image not found'}), 404  
      
    # Determine mimetype based on extension  
    ext = parsed['extension'].lower()  
    if ext in ['jpg', 'jpeg']:  
        mimetype = 'image/jpeg'  
    elif ext == 'png':  
        mimetype = 'image/png'  
    else:  
        mimetype = 'application/octet-stream'  
      
    return send_file(image_path, mimetype=mimetype)  
    
@app.route('/api/current/<route_id>', methods=['GET', 'OPTIONS'])    
def get_current_situation(route_id):    
    """Get current border crossing situation"""    
    if request.method == 'OPTIONS':    
        return '', 204    
    
    data = load_data()    
    
    if route_id in data:    
        border_info = data[route_id]    
        response = {    
            'status': border_info.get('status', 'unknown'),    
            'wait_time': border_info.get('wait_time', 'N/A'),    
            'car_count': border_info.get('car_count', 0),    
            'last_updated': border_info.get('last_updated', datetime.now().strftime('%H:%M')),    
            'message': border_info.get('message', '')    
        }    
        return jsonify(response)    
    
    return jsonify({'error': 'Route not found'}), 404    
    
@app.route('/api/predict', methods=['POST', 'OPTIONS'])    
def get_prediction():    
    """Get AI prediction for trip"""    
    if request.method == 'OPTIONS':    
        return '', 204    
    
    data = request.json    
    
    current_location = data.get('currentLocation')    
    location_coords = data.get('locationCoords')    
    border_pass = data.get('borderPass')    
    departure_time_str = data.get('departureTime')    
    
    # Parse departure time    
    try:    
        departure_time = datetime.fromisoformat(departure_time_str)    
        hour = departure_time.hour    
        day_of_week = departure_time.weekday()  # 0=Monday, 6=Sunday    
    except:    
        hour = datetime.now().hour    
        day_of_week = datetime.now().weekday()    
    
    # Determine time category based on hour    
    if 6 <= hour < 10:    
        time_category = 'morning_rush'    
    elif 10 <= hour < 14:    
        time_category = 'midday'    
    elif 14 <= hour < 18:    
        time_category = 'afternoon'    
    elif 18 <= hour < 22:    
        time_category = 'evening_rush'    
    else:    
        time_category = 'night'    
    
    # Load model predictions    
    predictions = load_model_predictions()    
    prediction_key = f"{border_pass}_{time_category}"    
    
    if prediction_key in predictions:    
        model_data = predictions[prediction_key]    
    else:    
        # Default prediction based on time and day    
        is_weekend = day_of_week >= 5    
        is_rush_hour = time_category in ['morning_rush', 'evening_rush']    
    
        if is_weekend:    
            estimated_wait = '30-45 min' if is_rush_hour else '15-25 min'    
            traffic_level = 'Moderate' if is_rush_hour else 'Light'    
            confidence = 75    
            car_count = 20 if is_rush_hour else 10    
        else:    
            estimated_wait = '45-60 min' if is_rush_hour else '10-20 min'    
            traffic_level = 'Heavy' if is_rush_hour else 'Light'    
            confidence = 80    
            car_count = 30 if is_rush_hour else 8    
    
        model_data = {    
            'estimated_wait': estimated_wait,    
            'traffic_level': traffic_level,    
            'best_time': '14:00-16:00' if hour < 14 else 'Early morning (6:00-8:00)',    
            'confidence_score': confidence,    
            'car_count': car_count,    
            'early_car_count': max(5, car_count - 15),    
            'later_car_count': max(8, car_count - 10)    
        }    
    
    # Get alternative border info    
    alternative_border = None    
    alternative_car_count = None    
        
    if border_pass == 'bajakovo-batrovci':    
        alternative_border = 'Tovarnik - Šid'    
        alternative_key = f"tovarnik-sid_{time_category}"    
        if alternative_key in predictions:    
            alternative_car_count = predictions[alternative_key].get('car_count', 12)    
        else:    
            alternative_car_count = max(5, model_data.get('car_count', 20) - 8)    
              
    elif border_pass == 'batrovci-bajakovo':    
        alternative_border = 'Šid - Tovarnik'    
        alternative_key = f"sid-tovarnik_{time_category}"    
        if alternative_key in predictions:    
            alternative_car_count = predictions[alternative_key].get('car_count', 10)    
        else:    
            alternative_car_count = max(5, model_data.get('car_count', 18) - 6)    
              
    elif border_pass == 'tovarnik-sid':    
        alternative_border = 'Bajakovo - Batrovci'    
        alternative_key = f"bajakovo-batrovci_{time_category}"    
        if alternative_key in predictions:    
            alternative_car_count = predictions[alternative_key].get('car_count', 15)    
        else:    
            alternative_car_count = model_data.get('car_count', 15) + 5    
              
    elif border_pass == 'sid-tovarnik':    
        alternative_border = 'Batrovci - Bajakovo'    
        alternative_key = f"batrovci-bajakovo_{time_category}"    
        if alternative_key in predictions:    
            alternative_car_count = predictions[alternative_key].get('car_count', 12)    
        else:    
            alternative_car_count = model_data.get('car_count', 12) + 3    
    
    recommendation = generate_recommendation(    
        model_data['traffic_level'],    
        departure_time_str,    
        day_of_week    
    )    
    
    response = {    
        'estimated_wait': model_data['estimated_wait'],    
        'wait_time': model_data['estimated_wait'],    
        'traffic_level': model_data['traffic_level'],    
        'best_time': model_data['best_time'],    
        'confidence_score': model_data['confidence_score'],    
        'confidence': 'high' if model_data['confidence_score'] > 80 else 'medium',    
        'recommendation': recommendation,    
        'car_count': model_data.get('car_count', 0),    
        'early_car_count': model_data.get('early_car_count', 8),    
        'later_car_count': model_data.get('later_car_count', 12),    
        'alternative_border': alternative_border,    
        'alternative_car_count': alternative_car_count,    
        'departure_info': {    
            'time': departure_time_str,    
            'location': current_location    
        }    
    }    
    
    return jsonify(response)    
    
def generate_recommendation(traffic_level, departure_time, day_of_week):    
    """Generate smart recommendation based on traffic level"""    
    weekend_note = " (Weekend traffic expected)" if day_of_week >= 5 else ""    
    
    recommendations = {    
        'light': f"Great time to travel! Minimal wait expected at the border.{weekend_note}",    
        'moderate': f"Moderate traffic expected. Have your documents ready to speed up crossing.{weekend_note}",    
        'heavy': f"Heavy traffic predicted. Consider arriving earlier or delaying by 2-3 hours if possible.{weekend_note}",    
        'free': f"Excellent conditions! Border crossing should be very quick.{weekend_note}"    
    }    
    
    return recommendations.get(traffic_level.lower(),    
                               "Prepare your documents and stay updated on border conditions.")    
    
@app.route('/api/health', methods=['GET', 'OPTIONS'])      
def health_check():      
    """Health check endpoint"""      
    if request.method == 'OPTIONS':      
        return '', 204      
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})      
    
@app.route('/api/traffic-factors', methods=['GET', 'OPTIONS'])      
def get_traffic_factors():      
    """Get currently active traffic factors and special events"""      
    if request.method == 'OPTIONS':      
        return '', 204      
          
    now = datetime.now()      
    current_month = now.month      
    current_day = now.day      
          
    active_factors = []      
          
    # EES System - Always active (started in 2024)      
    active_factors.append({      
        'id': 'ees',      
        'icon': '🛂',      
        'title': 'EES System Active',      
        'description': 'Entry/Exit System may cause longer wait times than usual at border crossings.',      
        'impact': 'moderate',      
        'active_since': '2024-01-01'      
    })      
          
    # Serbian Public Holiday - February 15 (Statehood Day - Dan državnosti)      
    if current_month == 2 and (13 <= current_day <= 16):      
        active_factors.append({      
            'id': 'serbian-holiday',      
            'icon': '🇷🇸',      
            'title': 'Serbian Public Holiday',      
            'description': 'Feb 15 - Dan državnosti Srbije (Statehood Day). Expect heavier traffic than normal.',      
            'impact': 'high',      
            'date': '2024-02-15'      
        })      
          
    # Valentine's Day traffic - February 14      
    if current_month == 2 and (13 <= current_day <= 15):      
        active_factors.append({      
            'id': 'valentines-day',      
            'icon': '💝',      
            'title': 'Valentine\'s Day Weekend',      
            'description': 'Increased cross-border travel for Valentine\'s Day celebrations.',      
            'impact': 'moderate',      
            'date': '2024-02-14'      
        })      
          
    # Croatian holidays      
    if current_month == 5 and (29 <= current_day <= 31):      
        active_factors.append({      
            'id': 'croatian-holiday',      
            'icon': '🇭🇷',      
            'title': 'Croatian Statehood Day',      
            'description': 'May 30 - Dan državnosti Hrvatske. Higher traffic expected on border crossings.',      
            'impact': 'high',      
            'date': '2024-05-30'      
        })      
          
    if current_month == 6 and (24 <= current_day <= 26):      
        active_factors.append({      
            'id': 'croatian-anti-fascist',      
            'icon': '🇭🇷',      
            'title': 'Anti-Fascist Struggle Day',      
            'description': 'June 25 - Dan antifašističke borbe. Increased traffic at borders.',      
            'impact': 'moderate',      
            'date': '2024-06-25'      
        })      
          
    # Summer vacation period (July-August)      
    if current_month in [7, 8]:      
        active_factors.append({      
            'id': 'summer-vacation',      
            'icon': '🏖️',      
            'title': 'Summer Vacation Season',      
            'description': 'Peak holiday travel season. Expect significantly longer wait times, especially on weekends.',      
            'impact': 'very-high',      
            'period': 'July-August'      
        })      
          
    # Christmas period (December 20 - January 7)      
    if (current_month == 12 and current_day >= 20) or (current_month == 1 and current_day <= 7):      
        active_factors.append({      
            'id': 'christmas',      
            'icon': '🎄',      
            'title': 'Christmas & New Year Period',      
            'description': 'Dec 20 - Jan 7: Significantly increased traffic at all border crossings.',      
            'impact': 'very-high',      
            'period': 'Dec 20 - Jan 7'      
        })      
          
    # Orthodox Christmas (January 7)      
    if current_month == 1 and (6 <= current_day <= 8):      
        active_factors.append({      
            'id': 'orthodox-christmas',      
            'icon': '☦️',      
            'title': 'Orthodox Christmas',      
            'description': 'Jan 7 - Православни Божић. Heavy cross-border traffic expected.',      
            'impact': 'high',      
            'date': '2024-01-07'      
        })      
          
    # Easter period (calculate based on year - using approximate dates)      
    if current_month == 4 and (1 <= current_day <= 15):      
        active_factors.append({      
            'id': 'easter',      
            'icon': '🐣',      
            'title': 'Easter Holiday Period',      
            'description': 'Increased travel for Easter holidays. Expect moderate to heavy traffic.',      
            'impact': 'high',      
            'period': 'Easter Week'      
        })      
          
    # Weekend warning (Friday-Sunday)      
    if now.weekday() >= 4:  # Friday, Saturday, Sunday      
        active_factors.append({      
            'id': 'weekend',      
            'icon': '📅',      
            'title': 'Weekend Traffic',      
            'description': 'Weekends typically see 30-50% more traffic at border crossings.',      
            'impact': 'moderate',      
            'recurring': True      
        })      
          
    response = {      
        'active_factors': active_factors,      
        'count': len(active_factors),      
        'last_updated': now.isoformat(),      
        'severity_level': calculate_overall_severity(active_factors)      
    }      
          
    return jsonify(response)      
      
def calculate_overall_severity(factors):      
    """Calculate overall traffic severity based on active factors"""      
    if not factors:      
        return 'normal'      
          
    severity_weights = {      
        'very-high': 4,      
        'high': 3,      
        'moderate': 2,      
        'low': 1      
    }      
          
    total_weight = sum(severity_weights.get(f.get('impact', 'low'), 1) for f in factors)      
          
    if total_weight >= 8:      
        return 'critical'      
    elif total_weight >= 5:      
        return 'high'      
    elif total_weight >= 3:      
        return 'moderate'      
    else:      
        return 'normal'    
    
@app.after_request      
def after_request(response):      
    response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))      
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')      
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')      
    response.headers.add('Access-Control-Allow-Credentials', 'true')      
    return response      
      
if __name__ == '__main__':      
    app.run(debug=True, port=5001, host='0.0.0.0')  
