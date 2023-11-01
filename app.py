from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory
from flask_apscheduler import APScheduler
from flask_mail import Mail, Message
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
from itsdangerous import URLSafeTimedSerializer
import os
import re


app = Flask(__name__)

#config = configparser.ConfigParser()
#config.read('config.ini')
app.config['SECRET_KEY'] = os.environ.get('app_secret_key')#, config['DEFAULT']['app_secret_key'])
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://') #, config['DEFAULT']['DATABASE_URL']).replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True

app.config['SCHEDULER_API_ENABLED'] = True
app.config['SCHEDULER_TIMEZONE'] = 'utc'

app.config['MAIL_SERVER'] = 'smtp.poczta.onet.pl'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.environ.get('wp_email')#, config['DEFAULT']['wp_email'])
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('wp_email')#, config['DEFAULT']['wp_email'])
app.config['MAIL_PASSWORD'] = os.environ.get('wp_password')#, config['DEFAULT']['wp_password'])
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['SECURITY_PASSWORD_SALT'] = os.environ.get('security_password_salt')#, config['DEFAULT']['SECURITY_PASSWORD_SALT'])

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

BASE_URL = "http://api.openweathermap.org/data/2.5/weather?"
FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast?"
API_KEY = os.environ.get('api_key')#, config['DEFAULT']['api_key'])
GEONAMES_USERNAME = os.environ.get('geonames_username')#, config['DEFAULT']['geonames_username'])

db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)

favourites = db.Table('favourites',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('city_id', db.Integer, db.ForeignKey('city.id'), primary_key=True)
)

emails = db.Table('emails',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('city_id', db.Integer, db.ForeignKey('city.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    email_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    email_confirmed_on = db.Column(db.DateTime, nullable=True)
    favorite_cities = db.relationship('City', secondary=favourites, lazy='subquery',
                                      backref=db.backref('favourite_users', lazy=True))
    emails_enabled = db.relationship('City', secondary=emails, lazy='subquery',
                                     backref=db.backref('emails_enabled_users', lazy=True))

class City(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Register')

def send_email_verification_email(email):
    token = generate_confirmation_token(email)
    confirm_url = url_for('confirm_email', token=token, _external=True)
    html = render_template('email_confirmation.html', confirm_url=confirm_url)
    subject = "Please confirm your email"
    send_email(email, subject, html)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        existing_username = User.query.filter_by(username=username).first()
        existing_email = User.query.filter_by(email=email).first()

        if existing_username or existing_email:
            return jsonify({'status': 'failure', 'message': 'User already exists or e-mail already used'})
        
        email_verification_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not bool(re.match(email_verification_pattern, email)):
            return jsonify({'status': 'failure', 'message': 'E-mail not in supported format'})
        
        send_email_verification_email(email)

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password)
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
    with app.app_context():
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
        user = db.session.get(User, user_id)
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
    user = db.session.get(User, user_id)
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

@app.route('/send_scheduled_notifications', methods=['POST'])
@login_required
def add_city_to_weather_email():
    user_id = current_user.id
    user = db.session.get(User, user_id)
    city = request.get_json().get('city_name')

    if not city:
        return jsonify({'error': 'City name is missing'}), 400
    
    elif user.email_confirmed:
        new_email_city = City.query.filter_by(name=city).first()
        if not new_email_city:
            new_email_city = City(name=city) 
            db.session.add(new_email_city)
            db.session.commit() 

        city_in_emails = any(enabled_city.name == city for enabled_city in user.emails_enabled)
        if not city_in_emails:
            current_user.emails_enabled.append(new_email_city)
            db.session.commit()
            return jsonify({'hasUnconfirmedEmail': False})
        
        return jsonify({'error': 'E-mails already enabled for this city'}), 400
    
    else:
        return jsonify({'hasUnconfirmedEmail': True})
    
def get_users_and_cities():
    users = User.query.all() 
    user_city_map = {}
    for user in users:
        cities = [city.name for city in user.emails_enabled] 
        if len(cities) > 0 and user.email_confirmed:
            user_city_map[user.email] = cities
    return user_city_map

def generate_email_body(cities):
    email_body = f"<p>Dear User,</p><p>Here is the weather update for your cities:</p>"

    for city in cities:
        weather = get_weather_data(city)
        if 'error' not in weather:
            email_body += f"<p>- {weather['city']}: {weather['temperature']}°C, {weather['description']}</p>"
        else:
            email_body += f"<p>- Couldn't retrieve weather information for {city}</p>"
    
    email_body += "<p>Best regards,<br>Your WeatherApp Team</p>"
    return email_body

def send_emails():
    user_city_map = get_users_and_cities()
    for email, cities in user_city_map.items():
        subject = "Your Assigned Cities"
        body = generate_email_body(cities)
        send_weather_notification_email(email, subject, body)

@app.route('/get_local_news', methods=['POST'])
def get_local_news():
    city = request.get_json().get('city_name')
    news_url = "https://newsapi.org/v2/everything"
    news_API_KEY = os.environ.get('news_api_key')#, config['DEFAULT']['news_api_key'])

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

@app.route('/search_city')
def search_city():
    query = request.args.get('q')
    location_url = "http://api.geonames.org/searchJSON?"
    complete_url = location_url + "q=" + query + "&maxRows=5" + "&username="+ GEONAMES_USERNAME
    response = requests.get(complete_url)
    data = response.json()

    cities = [entry['name'] + ", " + entry['adminName1']+ ', ' + entry['countryName'] for entry in data['geonames']]
    
    return jsonify(cities)


def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])

def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
    except:
        return False
    return email

def send_email(to, subject, template):
    try:
        msg = Message(subject, recipients=[to], html=template)
        mail.send(msg)
        flash('Confirmation e-mail sent successfully!', 'success')
    except Exception as e:
        print("error", str(e))
        flash('Error sending confirmation e-mail. Please try again later.', 'danger')

def send_weather_notification_email(to, subject, template):
    with app.app_context():
        try:
            msg = Message(subject, recipients=[to], html=template)
            mail.send(msg)
        except Exception as e:
            print("error send_weather_notification_email", str(e))

scheduler.add_job(id='send_emails_task', func=send_emails, trigger='cron', hour=8, minute=0)

@app.route('/confirm/<token>', methods=['GET'])
def confirm_email(token):
    try:
        email = confirm_token(token)
    except:
        flash('The confirmation link is invalid or has expired.', 'danger') 
    user = User.query.filter_by(email=email).first()
    if user.email_confirmed:
        flash('E-mail already confirmed', 'warning')
    else:
        user.email_confirmed = True
        user.email_confirmed_on = datetime.now()
        db.session.add(user)
        db.session.commit()
        flash('Thank you for confirming your email address!', 'success')
        return redirect(url_for('index'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        new_password = request.form.get('password')
        
        if new_password:
            current_user.password = generate_password_hash(new_password)
        
        updated_favourites = request.form.getlist('favourites') 
        current_user.favorite_cities = City.query.filter(City.id.in_(updated_favourites)).all()

        updated_enabled = request.form.getlist('enabled') 
        current_user.emails_enabled = City.query.filter(City.id.in_(updated_enabled)).all()

        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings')) 
    
    favourites = current_user.favorite_cities
    enabled = current_user.emails_enabled
    return render_template('settings.html', user=current_user, favourites=favourites, enabled=enabled)

@app.route('/send_confirmation_email', methods=['GET'])
@login_required
def send_confirmation_email():
    if not current_user.email_confirmed:
        send_email_verification_email(current_user.email)
        flash('Confirmation email sent successfully!', 'success')
    else:
        flash('Email is already confirmed!', 'info')
    return redirect(url_for('settings')) 


if __name__ == '__main__':
    app.run(debug=False)
