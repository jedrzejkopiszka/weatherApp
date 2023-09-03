from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from flask_migrate import Migrate
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
import configparser
import requests
from collections import defaultdict
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


app = Flask(__name__)

config = configparser.ConfigParser()
config.read('config.ini')
app.config['SECRET_KEY'] = 'some_random_secret_key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'  # SQLite DB
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

BASE_URL = "http://api.openweathermap.org/data/2.5/weather?"
FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast?"
API_KEY = config['DEFAULT']['api_key']

db = SQLAlchemy(app)
migrate = Migrate(app, db)


favourites = db.Table('favourites',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('city_id', db.Integer, db.ForeignKey('city.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    favorite_cities = db.relationship('City', secondary=favourites, backref=db.backref('users', lazy='dynamic'))

class City(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Register')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            return jsonify({'status': 'failure', 'message': 'User already exists'})
        
        hashed_password = generate_password_hash(password, method='sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'status': 'success'})
    else :
        return render_template('register.html', form=form)

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return jsonify({'status': 'success'})
        return jsonify({'status': 'failure', 'message': 'Invalid credentials'})
    else :
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
    is_logged_in = current_user.is_authenticated if hasattr(current_user, 'is_authenticated') else False
    cities = []
    if is_logged_in:
        user_id = current_user.id
        user = User.query.get(user_id)
        cities = [fav_city.name for fav_city in user.favorite_cities]
    if is_logged_in == False or len(cities) == 0:
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

@app.route('/add_favourite', methods=['POST'])
@login_required
def add_favourite():
    user_id = current_user.id
    user = User.query.get(user_id)
    city = request.get_json().get('city_name')

    if not city:
        return jsonify({'error': 'City name is missing'}), 400
    
    city_in_favorites = any(fav_city.name == city for fav_city in user.favorite_cities)
    if city_in_favorites:
        return jsonify({'isFavorite': True})
    
    new_fav_city = City.query.filter_by(name=city).first()
    if not new_fav_city:
        new_fav_city = City(name=city) 
        db.session.add(new_fav_city)
        db.session.commit()
    
    current_user.favorite_cities.append(new_fav_city)
    db.session.commit()
    return jsonify({'isFavorite': False})

@app.route('/get_local_news', methods=['POST'])
def get_local_news():
    city = request.get_json().get('city_name')
    news_url = "https://newsapi.org/v2/everything"
    news_API_KEY = config['DEFAULT']['news_api_key']

    query = f"+{city}"
    currentTimeDate = datetime.now() - relativedelta(months=1)
    today_minus_month = currentTimeDate.strftime('%Y-%m-%d')
    sorting = 'relevancy'
    searchIn = 'title,description'
    params = {"apiKey" : news_API_KEY,
               "q" : query,
               "from": today_minus_month,
               "sortBy" : sorting,
               "searchIn" : searchIn,
               "pageSize" : 5}
    
    response = requests.get(news_url, params=params)
    
    if response.status_code == 200:
        list_of_articles = response.json()["articles"]
        articles_data = []
        for article in list_of_articles:
            json = jsonify({
                'title' : article['title'],
                'url' : article['url'],
                'urltoImage' : article['urlToImage']
            }).get_json()

            articles_data.append(json)
        return jsonify({'error':None, 'articles': articles_data})
    else:
        return jsonify({'error': 'Unknown error occured', 'articles':[]})

if __name__ == '__main__':
    app.run(debug=False)
