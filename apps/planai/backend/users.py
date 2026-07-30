from storage import load_users


def login(username, password):
    users = load_users()
    username = str(username or "").strip()

    user = users.get(username)

    if not user:
        return None

    if user.get("password") != password:
        return None

    return {
        "username": username,
        "role": user.get("role", "USER")
    }