from app import app, db, User  # make sure to import your db and User model

with app.app_context():
    users = User.query.all()
    for user in users:
        print(user.id, user.username, user.password, user.favorite_cities)
