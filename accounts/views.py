from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response


def serialize_user(user):
    full_name = user.get_full_name().strip() or user.username

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": full_name,
    }


@api_view(["POST"])
def register(request):
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")
    full_name = request.data.get("name", "").strip()
    email = request.data.get("email", "").strip()

    if not username or not password:
        return Response(
            {"error": "Username and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username is already registered."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    first_name = full_name
    last_name = ""

    if " " in full_name:
        first_name, last_name = full_name.split(" ", 1)

    user = User.objects.create_user(
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )

    return Response(serialize_user(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
def login(request):
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")
    user = authenticate(username=username, password=password)

    if user is None:
        return Response(
            {"error": "Invalid username or password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(serialize_user(user))
