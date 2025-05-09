from src import main


def test_greeting():
    assert main.greeting("world") == "Hello world"
