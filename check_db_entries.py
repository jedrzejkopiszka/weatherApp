from app import app, db, User  # make sure to import your db and User model

with app.app_context():
    users = User.query.all()
    for user in users:
        print(user.username, user.password)
