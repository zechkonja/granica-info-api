from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import json

app = Flask(__name__)

CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
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
            'density': border_info.get('density', 0),
            'queue_length': border_info.get('queue_length', 'N/A'),
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
        else:
            estimated_wait = '45-60 min' if is_rush_hour else '10-20 min'
            traffic_level = 'Heavy' if is_rush_hour else 'Light'
            confidence = 80

        model_data = {
            'estimated_wait': estimated_wait,
            'traffic_level': traffic_level,
            'best_time': '14:00-16:00' if hour < 14 else 'Early morning (6:00-8:00)',
            'confidence_score': confidence
        }

    recommendation = generate_recommendation(
        model_data['traffic_level'],
        departure_time_str,
        day_of_week
    )

    response = {
        'estimated_wait': model_data['estimated_wait'],
        'traffic_level': model_data['traffic_level'],
        'best_time': model_data['best_time'],
        'confidence_score': model_data['confidence_score'],
        'confidence': 'high' if model_data['confidence_score'] > 80 else 'medium',
        'recommendation': recommendation,
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

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin', '*'))
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
