from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
import configparser
import requests
from collections import defaultdict
from datetime import datetime, timedelta


app = Flask(__name__)

BASE_URL = "http://api.openweathermap.org/data/2.5/weather?"
FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast?"

config = configparser.ConfigParser()
config.read('config.ini')
API_KEY = config['DEFAULT']['api_key']

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.config['SECRET_KEY'] = 'some_random_secret_key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)

class User(UserMixin):
    def __init__(self, id):
        self.id = id

users = {'admin': {'password': 'admin'}}

@login_manager.user_loader
def load_user(user_id):
    return User(user_id) if user_id in users else None

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = users.get(form.username.data)
        if user and user['password'] == form.password.data:
            user_obj = User(form.username.data)
            login_user(user_obj)
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'failure', 'message': 'Invalid credentials'})
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    return render_template('index.html', current_user=current_user)

@app.route('/get_weather', methods=['POST'])
@login_required
def get_weather():
    city = request.form['city']
    complete_url = BASE_URL + "q=" + city + "&appid=" + API_KEY
    response = requests.get(complete_url)
    data = response.json()

    if data.get("cod") != 404:
        main = data.get("main", {})
        coord = data.get("coord", {})
        weather = data["weather"][0] if data.get("weather") else {}
        return jsonify({
            'city': data.get('name'),
            'temperature': main.get("temp"),
            'description': weather.get("description"),
            'icon': weather.get("icon"),
            'lon': coord.get("lon"),
            'lat': coord.get("lat")
        })
    else:
        return jsonify({'error': 'Unknown error occured'})
    
def get_weather_data(city):
    complete_url = BASE_URL + "q=" + city + "&appid=" + API_KEY
    response = requests.get(complete_url)
    data = response.json()
    
    if data.get("cod") != 404:
        main = data.get("main", {})
        coord = data.get("coord", {})
        weather = data["weather"][0] if data.get("weather") else {}
        return jsonify({
            'city': data.get('name'),
            'temperature': main.get("temp"),
            'description': weather.get("description"),
            'icon': weather.get("icon"),
            'lon': coord.get("lon"),
            'lat': coord.get("lat")
        }).get_json()
    else:
        return jsonify({'error': 'Unknown error occured'})

@app.route('/get_multiple_weather', methods=['POST'])
def get_multiple_weather():
    cities = request.json.get('cities', [])
    weather_data = []
    for city in cities:
        data = get_weather_data(city) 
        weather_data.append(data)
    return jsonify(weather_data)

@app.route('/forecast', methods=['POST'])
@login_required
def get_forecast():
    city = request.form['city']
    response = requests.get(FORECAST_URL + "q=" + city + "&appid=" + API_KEY)

    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch forecast data for " + city})
    
    data = response.json()
    daily_max_temps = defaultdict(float)

    for forecast in data['list']:
        date_str = datetime.utcfromtimestamp(forecast['dt']).strftime('%Y-%m-%d')
        temp = forecast['main']['temp'] - 273.15  # Convert Kelvin to Celsius
        daily_max_temps[date_str] = max(daily_max_temps[date_str], temp)

    return jsonify(dict(daily_max_temps))


if __name__ == '__main__':
    app.run(debug=True)
