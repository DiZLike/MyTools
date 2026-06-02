"""
Обработчики команд протокола.
"""
import socket
import protocol


def handle_client_name(conn: socket.socket, arg: str | None) -> str:
    if arg:
        conn.sendall(protocol.OK)
        print(f"Подключился: {arg}")
        return arg
    
    conn.sendall(protocol.CON_ERROR)
    return "Unknown"


def handle_message(conn: socket.socket, message: str) -> str:
    command, arg = protocol.parse_command(message)
    
    if command == protocol.CLIENT_NAME:
        return handle_client_name(conn, arg)
    
    conn.sendall(protocol.CON_ERROR)
    return "Unknown"