"""
Приём и разбор сообщений из сокета.
"""
import socket
import protocol


def receive_messages(conn: socket.socket, buffer: bytes) -> tuple[list[str], bytes]:
    messages: list[str] = []
    
    try:
        data = conn.recv(protocol.BUFFER_SIZE)
        if not data:
            return messages, buffer
            
        buffer += data
        
        while protocol.MESSAGE_DELIMITER.encode() in buffer:
            line, buffer = buffer.split(protocol.MESSAGE_DELIMITER.encode(), 1)
            line = line.rstrip(b"\r")
            
            try:
                message = protocol.decode_message(line)
                if message:
                    messages.append(message)
            except UnicodeDecodeError:
                continue
                
    except ConnectionError:
        pass
        
    return messages, buffer