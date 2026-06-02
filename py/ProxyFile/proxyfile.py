import socket
import threading
import protocol
import client


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((protocol.DEFAULT_HOST, protocol.DEFAULT_PORT))
        server.listen(socket.SOMAXCONN)
        print(f"Сервер запущен: {protocol.DEFAULT_HOST}:{protocol.DEFAULT_PORT}")

        try:
            while True:
                conn, addr = server.accept()
                thread = threading.Thread(
                    target=client.handle_client, 
                    args=(conn, addr), 
                    daemon=True
                )
                thread.start()
        except KeyboardInterrupt:
            print("\nСервер остановлен")


if __name__ == "__main__":
    main()