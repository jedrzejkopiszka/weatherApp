from app import app, db, User, City  # make sure to import your db and User model

with app.app_context():
    users = User.query.all()
    for user in users:
        print(user.id, user.username, user.email, user.email_confirmed, user.password, user.favorite_cities, user.emails_enabled)
    print(len(users))
    print("all shown")

    cities = City.query.all()
    for city in cities:
        print(city.id, city.name)
    print("shown all")