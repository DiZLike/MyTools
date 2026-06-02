"""
Обработчик одного клиентского соединения.
"""
import socket
import receiver
import handlers


def handle_client(conn: socket.socket, addr) -> None:
    client_name = "Unknown"
    buffer = b""
    print(f"Подключение от: {addr}")
    
    with conn:
        while True:
            messages, buffer = receiver.receive_messages(conn, buffer)
            
            if not messages and not buffer:
                break
                
            for message in messages:
                client_name = handlers.handle_message(conn, message)
    
    print(f"Клиент {client_name} отключился")