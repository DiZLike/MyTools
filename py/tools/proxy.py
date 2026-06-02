import socket
import struct
import threading
import time
import select
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from collections import deque

import psutil
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console, Group
from rich.prompt import Prompt, IntPrompt
from rich.text import Text
from rich import box
from rich.logging import RichHandler

# ============= Constants =============

# SOCKS5 constants
SOCKS_VERSION = 5
NO_AUTH = 0
USER_PASS_AUTH = 2
NO_ACCEPTABLE_METHODS = 0xFF

# Commands
CMD_CONNECT = 1
CMD_BIND = 2
CMD_UDP_ASSOCIATE = 3

# Address types
ATYP_IPV4 = 1
ATYP_DOMAIN = 3
ATYP_IPV6 = 4

# Response codes
REP_SUCCESS = 0
REP_GENERAL_FAILURE = 1
REP_CONNECTION_NOT_ALLOWED = 2
REP_NETWORK_UNREACHABLE = 3
REP_HOST_UNREACHABLE = 4
REP_CONNECTION_REFUSED = 5
REP_TTL_EXPIRED = 6
REP_COMMAND_NOT_SUPPORTED = 7
REP_ADDRESS_TYPE_NOT_SUPPORTED = 8

# ============= Logging Setup =============

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("socks5")

# ============= Data Structures =============

@dataclass
class ClientStats:
    """Статистика одного клиента"""
    addr: Tuple[str, int]
    connected_at: float
    bytes_in: int = 0
    bytes_out: int = 0
    target_host: str = ""
    target_port: int = 0
    auth_user: Optional[str] = None
    samples: deque = field(default_factory=lambda: deque(maxlen=5))
    
    @property
    def speed_in(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        return (self.samples[-1][0] - self.samples[0][0]) / max(1, len(self.samples))
    
    @property
    def speed_out(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        return (self.samples[-1][1] - self.samples[0][1]) / max(1, len(self.samples))
    
    @property
    def duration(self) -> float:
        return time.time() - self.connected_at
    
    def add_sample(self):
        self.samples.append((self.bytes_in, self.bytes_out))


@dataclass
class GlobalStats:
    """Глобальная статистика сервера"""
    bytes_in: int = 0
    bytes_out: int = 0
    total_connections: int = 0
    active_connections: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    samples: deque = field(default_factory=lambda: deque(maxlen=5))
    
    @property
    def speed(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        total = (self.samples[-1][0] + self.samples[-1][1]) - (self.samples[0][0] + self.samples[0][1])
        return total / max(1, len(self.samples))
    
    def add_sample(self):
        self.samples.append((self.bytes_in, self.bytes_out))


# ============= Network Utils =============

def get_network_interfaces() -> List[dict]:
    """Получить список сетевых интерфейсов Windows"""
    interfaces = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    
    for name, stat in stats.items():
        if not stat.isup:
            continue
            
        info = {
            'name': name,
            'ip': None,
            'speed': stat.speed,
            'mtu': stat.mtu,
            'description': name
        }
        
        for addr in addrs.get(name, []):
            if addr.family == socket.AF_INET:
                info['ip'] = addr.address
                break
        
        if info['ip']:  # Только интерфейсы с IPv4
            interfaces.append(info)
    
    return interfaces


def select_interface() -> dict:
    """Интерактивный выбор сетевого интерфейса"""
    console = Console()
    interfaces = get_network_interfaces()
    
    if not interfaces:
        console.print("[red]Нет доступных сетевых интерфейсов![/red]")
        exit(1)
    
    table = Table(title="Доступные сетевые интерфейсы", box=box.ROUNDED)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Имя", style="green")
    table.add_column("IP адрес", style="yellow")
    table.add_column("Скорость", style="magenta")
    table.add_column("Описание", style="dim")
    
    for i, iface in enumerate(interfaces, 1):
        speed = f"{iface['speed']} Mbps" if iface['speed'] else "Unknown"
        desc = iface['description'][:40]
        table.add_row(str(i), iface['name'], iface['ip'], speed, desc)
    
    console.print(table)
    
    choice = IntPrompt.ask(
        "\n[bold cyan]Выберите интерфейс[/bold cyan]",
        choices=[str(i) for i in range(1, len(interfaces) + 1)]
    )
    
    selected = interfaces[choice - 1]
    console.print(f"\n[green]✓ Выбран интерфейс: {selected['name']} ({selected['ip']})[/green]")
    return selected


# ============= SOCKS5 Server =============

class SOCKS5Server:
    def __init__(self, listen_host: str, listen_port: int, interface_ip: str, 
                 auth_required: bool = False, username: str = "", password: str = ""):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.interface_ip = interface_ip
        self.auth_required = auth_required
        self.username = username
        self.password = password
        self.global_stats = GlobalStats()
        self.clients: Dict[str, ClientStats] = {}
        self.clients_lock = threading.Lock()
        self.running = False
        self.server_socket = None
        self.start_time = None
        
    def handle_client(self, client_socket: socket.socket, client_addr: Tuple[str, int]):
        """Обработка одного SOCKS5 клиента"""
        client_key = f"{client_addr[0]}:{client_addr[1]}"
        client_stats = ClientStats(addr=client_addr, connected_at=time.time())
        
        try:
            # ===== SOCKS5 Handshake =====
            # 1. Получаем методы аутентификации
            version, nmethods = struct.unpack('!BB', self.recv_exact(client_socket, 2))
            
            if version != SOCKS_VERSION:
                logger.warning(f"Invalid SOCKS version from {client_key}: {version}")
                client_socket.close()
                return
            
            methods = self.recv_exact(client_socket, nmethods)
            
            # 2. Выбираем метод аутентификации
            if self.auth_required and USER_PASS_AUTH in methods:
                client_socket.sendall(struct.pack('!BB', SOCKS_VERSION, USER_PASS_AUTH))
                
                # Аутентификация username/password
                auth_version, username_len = struct.unpack('!BB', self.recv_exact(client_socket, 2))
                username = self.recv_exact(client_socket, username_len).decode()
                password_len = struct.unpack('!B', self.recv_exact(client_socket, 1))[0]
                password = self.recv_exact(client_socket, password_len).decode()
                
                if username == self.username and password == self.password:
                    client_socket.sendall(struct.pack('!BB', 1, 0))  # Success
                    client_stats.auth_user = username
                    logger.info(f"Client {client_key} authenticated as {username}")
                else:
                    client_socket.sendall(struct.pack('!BB', 1, 1))  # Failure
                    logger.warning(f"Authentication failed for {client_key}")
                    client_socket.close()
                    return
            elif not self.auth_required and NO_AUTH in methods:
                client_socket.sendall(struct.pack('!BB', SOCKS_VERSION, NO_AUTH))
            else:
                client_socket.sendall(struct.pack('!BB', SOCKS_VERSION, NO_ACCEPTABLE_METHODS))
                logger.warning(f"No acceptable auth method for {client_key}")
                client_socket.close()
                return
            
            # ===== SOCKS5 Request =====
            # 3. Получаем запрос
            version, cmd, rsv, atyp = struct.unpack('!BBBB', self.recv_exact(client_socket, 4))
            
            if version != SOCKS_VERSION:
                self.send_response(client_socket, REP_GENERAL_FAILURE)
                return
            
            if cmd != CMD_CONNECT:
                logger.warning(f"Unsupported command {cmd} from {client_key}")
                self.send_response(client_socket, REP_COMMAND_NOT_SUPPORTED)
                return
            
            # 4. Парсим адрес назначения
            if atyp == ATYP_IPV4:
                target_host = socket.inet_ntoa(self.recv_exact(client_socket, 4))
            elif atyp == ATYP_DOMAIN:
                domain_len = struct.unpack('!B', self.recv_exact(client_socket, 1))[0]
                target_host = self.recv_exact(client_socket, domain_len).decode()
            elif atyp == ATYP_IPV6:
                target_host = socket.inet_ntop(socket.AF_INET6, self.recv_exact(client_socket, 16))
            else:
                self.send_response(client_socket, REP_ADDRESS_TYPE_NOT_SUPPORTED)
                return
            
            target_port = struct.unpack('!H', self.recv_exact(client_socket, 2))[0]
            
            client_stats.target_host = target_host
            client_stats.target_port = target_port
            
            logger.info(f"[{client_key}] Connect to {target_host}:{target_port}")
            
            # 5. Подключаемся через выбранный интерфейс
            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            remote_socket.bind((self.interface_ip, 0))
            remote_socket.settimeout(10)
            
            try:
                remote_socket.connect((target_host, target_port))
            except socket.timeout:
                logger.error(f"[{client_key}] Connection timeout to {target_host}:{target_port}")
                self.send_response(client_socket, REP_HOST_UNREACHABLE)
                remote_socket.close()
                return
            except ConnectionRefusedError:
                logger.error(f"[{client_key}] Connection refused by {target_host}:{target_port}")
                self.send_response(client_socket, REP_CONNECTION_REFUSED)
                remote_socket.close()
                return
            except socket.gaierror:
                logger.error(f"[{client_key}] Host unreachable: {target_host}")
                self.send_response(client_socket, REP_HOST_UNREACHABLE)
                remote_socket.close()
                return
            
            remote_socket.settimeout(None)
            
            # 6. Отправляем успешный ответ
            bind_addr = remote_socket.getsockname()
            self.send_response(client_socket, REP_SUCCESS, bind_addr)
            
            # 7. Добавляем клиента в список
            with self.clients_lock:
                self.clients[client_key] = client_stats
                self.global_stats.active_connections += 1
                self.global_stats.total_connections += 1
            
            # 8. Туннелируем трафик
            self.tunnel(client_socket, remote_socket, client_key)
            
        except Exception as e:
            logger.error(f"Error handling client {client_key}: {e}", exc_info=True)
            try:
                self.send_response(client_socket, REP_GENERAL_FAILURE)
            except:
                pass
        finally:
            client_socket.close()
            with self.clients_lock:
                if client_key in self.clients:
                    duration = time.time() - self.clients[client_key].connected_at
                    logger.info(f"[{client_key}] Disconnected (duration: {duration:.1f}s)")
                    del self.clients[client_key]
                    self.global_stats.active_connections -= 1
    
    def tunnel(self, client: socket.socket, remote: socket.socket, client_key: str):
        """Туннелирование трафика между клиентом и удалённым сервером"""
        sockets = [client, remote]
        
        try:
            while self.running:
                readable, _, exceptional = select.select(sockets, [], sockets, 1.0)
                
                if exceptional:
                    break
                
                for sock in readable:
                    data = sock.recv(8192)
                    if not data:
                        return
                    
                    if sock is client:
                        remote.sendall(data)
                        self.update_stats(client_key, out=len(data))
                    else:
                        client.sendall(data)
                        self.update_stats(client_key, incoming=len(data))
        except Exception as e:
            logger.debug(f"Tunnel closed for {client_key}: {e}")
        finally:
            remote.close()
    
    def update_stats(self, client_key: str, incoming: int = 0, out: int = 0):
        """Обновление статистики"""
        with self.global_stats.lock:
            self.global_stats.bytes_in += incoming
            self.global_stats.bytes_out += out
            
            with self.clients_lock:
                if client_key in self.clients:
                    self.clients[client_key].bytes_in += incoming
                    self.clients[client_key].bytes_out += out
    
    def recv_exact(self, sock: socket.socket, length: int) -> bytes:
        """Получить точное количество байт"""
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data
    
    def send_response(self, sock: socket.socket, code: int, bind_addr: Optional[Tuple[str, int]] = None):
        """Отправить SOCKS5 ответ"""
        if bind_addr:
            ip, port = bind_addr
            response = struct.pack('!BBBB', SOCKS_VERSION, code, 0, ATYP_IPV4)
            response += socket.inet_aton(ip)
            response += struct.pack('!H', port)
        else:
            response = struct.pack('!BBBB', SOCKS_VERSION, code, 0, ATYP_IPV4)
            response += socket.inet_aton('0.0.0.0')
            response += struct.pack('!H', 0)
        
        sock.sendall(response)
    
    def start(self):
        """Запуск сервера"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.listen_host, self.listen_port))
        self.server_socket.listen(50)
        self.server_socket.settimeout(1.0)
        
        self.running = True
        self.start_time = time.time()
        
        logger.info(f"SOCKS5 server started on {self.listen_host}:{self.listen_port}")
        logger.info(f"Using interface: {self.interface_ip}")
        
        while self.running:
            try:
                client_socket, client_addr = self.server_socket.accept()
                logger.info(f"New connection from {client_addr[0]}:{client_addr[1]}")
                thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_addr),
                    daemon=True
                )
                thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}")
    
    def stop(self):
        """Остановка сервера"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        logger.info("Server stopped")


# ============= UI with Rich =============

def format_bytes(bytes_count: int) -> str:
    """Форматирование байт в читаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} PB"


def format_speed(bytes_per_sec: float) -> str:
    """Форматирование скорости"""
    return f"{format_bytes(int(bytes_per_sec))}/s"


def format_duration(seconds: float) -> str:
    """Форматирование времени"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def create_layout(server: SOCKS5Server, interface_info: dict) -> Layout:
    """Создание Layout для Rich"""
    layout = Layout()
    
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=10)
    )
    
    layout["main"].split_row(
        Layout(name="clients", ratio=2),
        Layout(name="stats", ratio=1)
    )
    
    # Header
    uptime = format_duration(time.time() - server.start_time) if server.start_time else "00:00:00"
    header_text = Text()
    header_text.append("🌐 SOCKS5 Proxy Server", style="bold cyan")
    header_text.append(f"  |  Interface: {interface_info['name']} ({interface_info['ip']})", style="green")
    header_text.append(f"  |  Port: {server.listen_port}", style="yellow")
    header_text.append(f"  |  Uptime: {uptime}", style="magenta")
    if server.auth_required:
        header_text.append("  |  🔒 Auth Required", style="red")
    
    layout["header"].update(Panel(header_text, box=box.ROUNDED))
    
    # Clients table
    clients_table = Table(
        title="👥 Connected Clients",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan"
    )
    clients_table.add_column("Client", style="yellow", width=20)
    clients_table.add_column("Target", style="green", width=30)
    clients_table.add_column("Download", style="blue", width=12)
    clients_table.add_column("Upload", style="red", width=12)
    clients_table.add_column("Speed ↓", style="blue", width=10)
    clients_table.add_column("Speed ↑", style="red", width=10)
    clients_table.add_column("Duration", style="magenta", width=10)
    
    with server.clients_lock:
        for client_key, stats in server.clients.items():
            clients_table.add_row(
                client_key,
                f"{stats.target_host}:{stats.target_port}",
                format_bytes(stats.bytes_in),
                format_bytes(stats.bytes_out),
                format_speed(stats.speed_in),
                format_speed(stats.speed_out),
                format_duration(stats.duration)
            )
    
    if not server.clients:
        clients_table.add_row("No clients connected", "", "", "", "", "", "")
    
    layout["clients"].update(Panel(clients_table, box=box.ROUNDED))
    
    # Stats panel
    with server.global_stats.lock:
        stats_text = Text()
        stats_text.append("📊 Global Statistics\n\n", style="bold cyan")
        stats_text.append(f"↓ Download: ", style="dim")
        stats_text.append(f"{format_bytes(server.global_stats.bytes_in)}\n", style="blue")
        stats_text.append(f"↑ Upload: ", style="dim")
        stats_text.append(f"{format_bytes(server.global_stats.bytes_out)}\n", style="red")
        stats_text.append(f"↔ Total: ", style="dim")
        stats_text.append(f"{format_bytes(server.global_stats.bytes_in + server.global_stats.bytes_out)}\n", style="green")
        stats_text.append(f"⚡ Speed: ", style="dim")
        stats_text.append(f"{format_speed(server.global_stats.speed)}\n\n", style="yellow")
        stats_text.append(f"🔗 Active: ", style="dim")
        stats_text.append(f"{server.global_stats.active_connections}\n", style="bold")
        stats_text.append(f"📈 Total served: ", style="dim")
        stats_text.append(f"{server.global_stats.total_connections}", style="bold")
    
    layout["stats"].update(Panel(stats_text, box=box.ROUNDED))
    
    # Footer - Log panel (здесь будет отображаться последние логи)
    log_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    log_table.add_column(style="dim", width=10)
    log_table.add_column(width=80)
    
    # Здесь можно добавить реальные логи, но для примера оставим заглушку
    log_table.add_row("", "[dim]Log output will appear here...[/dim]")
    
    layout["footer"].update(Panel(log_table, title="📝 Log", box=box.ROUNDED))
    
    return layout


# ============= Main =============

def main():
    console = Console()
    
    # Приветствие
    console.print()
    console.print(Panel.fit(
        "[bold cyan]SOCKS5 Proxy Server[/bold cyan]\n"
        "[dim]Раздача интернета через указанный сетевой интерфейс[/dim]",
        box=box.DOUBLE
    ))
    console.print()
    
    # Выбор интерфейса
    interface = select_interface()
    console.print()
    
    # Настройка порта
    listen_port = IntPrompt.ask(
        "[bold cyan]Порт для прослушивания[/bold cyan]",
        default=1080
    )
    
    # Настройка аутентификации
    auth_needed = Prompt.ask(
        "[bold cyan]Требовать аутентификацию?[/bold cyan]",
        choices=["y", "n"],
        default="n"
    ) == "y"
    
    username = ""
    password = ""
    if auth_needed:
        username = Prompt.ask("[bold cyan]Логин[/bold cyan]")
        password = Prompt.ask("[bold cyan]Пароль[/bold cyan]", password=True)
    
    console.print()
    console.print("[green]✓ Запуск сервера...[/green]")
    console.print()
    
    # Создаём и запускаем сервер
    server = SOCKS5Server(
        listen_host="0.0.0.0",
        listen_port=listen_port,
        interface_ip=interface['ip'],
        auth_required=auth_needed,
        username=username,
        password=password
    )
    
    # Запускаем сервер в отдельном потоке
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    
    # Даём серверу время на запуск
    time.sleep(1)
    
    # Обновление семплов для статистики
    def update_samples():
        while server.running:
            time.sleep(1)
            server.global_stats.add_sample()
            with server.clients_lock:
                for stats in server.clients.values():
                    stats.add_sample()
    
    stats_thread = threading.Thread(target=update_samples, daemon=True)
    stats_thread.start()
    
    # Rich Live display
    try:
        with Live(create_layout(server, interface), refresh_per_second=2, screen=True) as live:
            while server.running:
                live.update(create_layout(server, interface))
                time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]🛑 Shutting down...[/yellow]")
        server.stop()
        console.print("[green]✓ Server stopped[/green]")


if __name__ == "__main__":
    main()