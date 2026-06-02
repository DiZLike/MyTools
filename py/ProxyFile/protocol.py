# Команды протокола
CLIENT_NAME = "CLIENT_NAME"

# Ответы сервера
OK = "OK\n".encode("utf-8")
CON_ERROR = "CON_ERROR\n".encode("utf-8")

# Разделители
MESSAGE_DELIMITER = "\n"
COMMAND_DELIMITER = ":"

# Настройки сети
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4545
BUFFER_SIZE = 4096


def encode_message(message: str) -> bytes:
    """
    Кодирует строку в байты для отправки по сети.
    """
    return (message + MESSAGE_DELIMITER).encode("utf-8")


def decode_message(data: bytes) -> str:
    """
    Декодирует байты в строку.
    """
    return data.decode("utf-8")


def parse_command(message: str) -> tuple[str, str | None]:
    """
    Разбирает сообщение на команду и аргумент.
    """
    if COMMAND_DELIMITER in message:
        command, arg = message.split(COMMAND_DELIMITER, 1)
        return command.strip(), arg.strip()
    return message.strip(), None


def create_message(command: str, arg: str | None = None) -> str:
    """
    Создает сообщение в формате протокола.
    """
    if arg:
        return f"{command}{COMMAND_DELIMITER} {arg}"
    return command