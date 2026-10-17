"""Public disposable demo data. Never use these values for a real service."""

ACCOUNT = b"life_fixture"
PASSWORD = b"demo-pass"
WRONG_PASSWORD = b"bad-demo"
NAME = b"LifeFixture"

# Native PASSWDLEN is 16 including the terminating NUL.
assert all(0 < len(value) <= 15 and value.isascii()
           for value in (ACCOUNT, PASSWORD, WRONG_PASSWORD, NAME))
