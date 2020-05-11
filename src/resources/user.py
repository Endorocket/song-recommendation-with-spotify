import datetime
from typing import List

from bson import ObjectId
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse

from config.bcrypt import bcrypt
from enums.role import Role
from enums.status import Status
from models.event import EventModel
from models.user import UserModel
from utils.email_validator import email


class User(Resource):
    @classmethod
    def get(cls, user_id: str):
        if not ObjectId.is_valid(user_id):
            return {"status": Status.INVALID_FORMAT, "message": "Id is not valid ObjectId"}, 400

        user: UserModel = UserModel.find_by_id(ObjectId(user_id))
        if not user:
            return {"status": Status.USER_NOT_FOUND, "message": "User not found."}, 404

        return {"status": Status.OK, "user": user.json()}, 200


class UserCurrent(Resource):
    @classmethod
    @jwt_required
    def get(cls):
        user_id = get_jwt_identity()
        user: UserModel = UserModel.find_by_id(ObjectId(user_id))
        if not user:
            return {"status": Status.USER_NOT_FOUND, "message": "User not found."}, 404

        return {"status": Status.OK, "user": user.json()}, 200

    @classmethod
    @jwt_required
    def delete(cls):
        user_id = get_jwt_identity()
        user = UserModel.find_by_id(ObjectId(user_id))
        if not user:
            return {"status": Status.USER_NOT_FOUND, "message": "Current user not found"}, 404

        user.delete_from_db()

        events_deleted = 0
        events: List[EventModel] = EventModel.find_all_by_admin_id(admin_id=user.id)
        for event in events:
            if len(list(filter(lambda participant: participant.role == Role.ADMIN, event.participants))) == 1:
                event.delete()
                events_deleted += 1

        return {"status": Status.SUCCESS, "message": "User deleted" if events_deleted < 1 else "User deleted with events with no longer admin left"}, 200


class UserRegister(Resource):
    @classmethod
    def post(cls):
        parser = reqparse.RequestParser()
        parser.add_argument('username', type=str, required=True)
        parser.add_argument('email', type=email, required=True)
        parser.add_argument('password', type=str, required=True, )
        parser.add_argument('avatar_url', type=str, required=False)
        data = parser.parse_args()

        if len(data['username']) < 4 or len(data['password']) < 7:
            return {"status": Status.INVALID_FORMAT, "message": "username must be at least 5 chars long, password mininmum 7 characters!"}, 400

        user = UserModel(username=data['username'], email=data['email'], password=data['password'], avatar_url=data['avatar_url'])

        if UserModel.find_by_username(user.username):
            return {"status": Status.DUPLICATED, "message": "A user with that username already exists."}, 400

        if UserModel.find_by_email(user.email):
            return {"status": Status.DUPLICATED, "message": "A user with that email already exists."}, 400

        pw_hash = bcrypt.generate_password_hash(user.password).decode('utf-8')
        user.password = pw_hash

        user.save_to_db()

        return {"status": Status.SUCCESS,
                "message": "Account created successfully.",
                "user": user.json()
                }, 201


class UserLogin(Resource):
    @classmethod
    def post(cls):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        data = parser.parse_args()

        user: UserModel = UserModel.find_by_email(data['email'])

        if user and user.password and bcrypt.check_password_hash(user.password, data['password']):
            expires = datetime.timedelta(days=7)
            access_token = create_access_token(identity=str(user.id), fresh=True, expires_delta=expires)
            return {"access_token": access_token}, 200

        return {"status": Status.INVALID_DATA, "message": "Invalid credentials!"}, 401
